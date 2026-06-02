"""``replay_run`` — the Replay engine entry point.

Implements ``design/workflows/replay.md``:

    replay/replay_run
      → replay/reconstruct_replay_context   (resolve target + engine context)
      → run/execute_with_engine_context      (loop N times, --reruns)
      → memory/store_run_evidence            (loop, one per rerun)
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

from novetest.memory.project_store import ProjectStore
from novetest.memory.store import store_run_evidence
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.replay.classifier import classify_replay_consistency
from novetest.replay.context import ReplayContext, reconstruct_replay_context
from novetest.replay.errors import (
    REASON_ENGINE_NOT_READY,
    ReplayUnavailable,
)
from novetest.replay.persistence import write_replay_result
from novetest.run import (
    AdapterInvocationError,
    EngineNotSupportedError,
    assess_engine_readiness,
    execute_with_engine_context,
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
    # ``reconstruct_replay_context``). A missing/misconfigured engine is a
    # hard exit-4 surface — distinct from a runnable engine producing an
    # errored run (which the classifier maps to ``unable_to_replay``).
    readiness = await assess_engine_readiness(context.test_target.workspace_path)
    if readiness.state != "ready":
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_ENGINE_NOT_READY,
            detail=f"engine readiness state={readiness.state!r}",
        )

    replayed_records: list[RunRecord] = []
    for _ in range(max(reruns, 0)):
        run_id = generate_ulid()
        artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"
        try:
            record = await execute_with_engine_context(
                context.test_target,
                context.engine_context,
                artifact_dir=artifact_dir,
                run_id=run_id,
                timeout=timeout,
            )
        except EngineNotSupportedError as exc:
            # The recorded engine has no adapter — replay cannot proceed.
            return ReplayUnavailable(
                run_reference=original_ref,
                reason=REASON_ENGINE_NOT_READY,
                detail=str(exc),
            )
        except AdapterInvocationError:
            # This rerun could not produce a parseable native result. Skip
            # it; an attempt where every rerun fails this way yields zero
            # replay records and the classifier returns ``unable_to_replay``.
            continue

        persisted = _persist_replay_run(store, record)
        replayed_records.append(persisted)

    result = classify_replay_consistency(
        context.original_record,
        replayed_records,
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
