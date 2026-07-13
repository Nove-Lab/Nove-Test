"""``replay_run`` — the Replay engine entry point.

Implements ``design/workflows/replay.md``:

    replay/replay_run
      → replay/reconstruct_replay_context   (resolve target + engine context)
      → run/probe_engine                     (gate exactly the RECORDED engine)
      → run/execute_with_engine_context      (loop N times, --reruns)
      → memory/store_run_evidence            (loop, one per parsed rerun)
      → replay/classify_replay_consistency   (pure)
      → replay/persistence.write_replay_result

``run/execute_with_engine_context`` is the load-bearing reuse (REQ-REP-002):
each replay rerun flows through the SAME native engine path the original run
used. The Run engine is NOT modified by Replay.

``--reruns`` default is **1** (cheapest single-replay default; matches the
delivery-phasing example ``novetest replay <run_id_of_basic>`` which carries
no ``--reruns`` flag). Users investigating flakiness pass ``--reruns=5``.
Rationale + alternatives recorded in the handoff (§6.1).
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from novetest.memory import ProjectStore, store_run_evidence
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.replay.classifier import CrashedRerun, classify_replay_consistency
from novetest.replay.context import ReplayContext, reconstruct_replay_context
from novetest.replay.errors import (
    REASON_ENGINE_NOT_READY,
    ReplayUnavailable,
)
from novetest.replay.persistence import write_replay_result
from novetest.run import (
    AdapterInvocationError,
    EngineNotSupportedError,
    execute_with_engine_context,
    probe_engine,
)
from novetest.utils.ulid import generate_ulid


async def replay_run(
    store: ProjectStore,
    original_ref: RunReference,
    *,
    reruns: int = 1,
    timeout: float | None = 600.0,
) -> ReplayResult | ReplayUnavailable:
    """Reconstruct context, execute ``reruns`` replay runs, classify.

    Returns a ``ReplayResult`` (any classification, including the valid
    ``unable_to_replay`` outcome) on a completed attempt, or a
    ``ReplayUnavailable`` when the attempt could not start (original missing /
    tombstoned / workspace gone / engine not ready / unsupported engine).
    """
    context = reconstruct_replay_context(store, original_ref)
    if isinstance(context, ReplayUnavailable):
        return context

    # Engine readiness is the one async precondition (kept out of the sync
    # ``reconstruct_replay_context``). The gate probes exactly the RECORDED
    # engine (``context.engine_context``) — the engine every rerun re-executes
    # with — NOT the workspace's first auto-detected candidate: in a polyglot
    # workspace the two can differ and ``assess_engine_readiness`` would gate
    # the wrong engine (ANA-13, W2/S38). A missing/misconfigured recorded
    # engine is a hard exit-4 surface — distinct from a runnable engine
    # producing an errored run (which the classifier maps to
    # ``unable_to_replay``).
    try:
        readiness = await probe_engine(
            context.test_target.workspace_path,
            context.engine_context.ecosystem,
            context.engine_context.engine_name,
        )
    except EngineNotSupportedError as exc:
        # Recorded pairs are supported-matrix members by construction, but a
        # legacy/hand-edited ``record.json`` can carry a pair outside the
        # matrix (``RunRecord.from_dict`` does not re-validate it) — replay
        # cannot re-execute such a run. This gate is the ONLY
        # ``EngineNotSupportedError`` surface in replay: the rerun loop below
        # dispatches on this same gate-validated pair, and the adapter
        # dispatch table's keys equal the supported matrix (pinned run-side),
        # so the loop cannot raise it (W2/S40 deleted the unreachable
        # in-loop handler).
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_ENGINE_NOT_READY,
            detail=str(exc),
        )
    if readiness.state != "ready":
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_ENGINE_NOT_READY,
            detail=(
                f"recorded engine {context.engine_context.ecosystem}:"
                f"{context.engine_context.engine_name} readiness "
                f"state={readiness.state!r}"
            ),
        )

    rerun_attempts: list[RunRecord | CrashedRerun] = []
    for _ in range(max(reruns, 0)):
        run_id = generate_ulid()
        artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"
        try:
            # ``execute_with_engine_context`` returns
            # ``(RunRecord, adapter_warnings)`` per the 2026-06-06 envelope-
            # warnings-projection slice. Replay discards the warnings
            # tuple — adapter warnings are notice-grade signals scoped to
            # the per-invocation envelope, and ``novetest replay``'s
            # envelope projects a Replay Result block (not a Run Record
            # envelope). The original-run's warnings already surfaced on
            # the original-run's envelope; the replay reruns produce
            # their own per-invocation warnings that are not material to
            # the replay-consistency classification.
            record, _ = await execute_with_engine_context(
                context.test_target,
                context.engine_context,
                artifact_dir=artifact_dir,
                run_id=run_id,
                timeout=timeout,
            )
        except AdapterInvocationError as exc:
            # Q2 Option A (W2/S38 — ANA-14): a rerun that cannot produce a
            # parseable native result is an ERRORED ATTEMPT, not a non-event.
            # It counts in the classification inputs (and thus in
            # ``reruns_total`` = attempted reruns) via a synthetic errored
            # outcome; nothing is persisted — there is no ``RunRecord`` to
            # persist. The pre-S38 ``continue`` discard shrank
            # ``reruns_total`` and let a 50%-crash session classify
            # ``reproducible``.
            rerun_attempts.append(CrashedRerun(detail=str(exc)))
            continue

        persisted = _persist_replay_run(store, record)
        rerun_attempts.append(persisted)

    result = classify_replay_consistency(
        context.original_record,
        rerun_attempts,
        attempted_at=int(time.time() * 1000),
    )
    write_replay_result(store, original_ref, result)
    return result


def _persist_replay_run(store: ProjectStore, record: RunRecord) -> RunRecord:
    """Rewrite artifact paths Project-Store-relative and store the run.

    Mirrors ``orchestration/workflows/run.py``: the adapter writes native
    artifacts under ``<store>/run/artifacts/run_<id>/...`` with absolute
    paths; Memory persists them relative to the store root.
    """
    relative_paths = {
        name: str(Path(path).relative_to(store.path))
        for name, path in record.artifact_paths.items()
    }
    persisted_record = replace(record, artifact_paths=relative_paths)
    store_run_evidence(store, persisted_record)
    return persisted_record


# Re-export the ``ReplayContext`` type so callers importing the engine module
# can pattern-match without reaching into ``replay.context`` directly.
__all__ = ["ReplayContext", "replay_run"]
