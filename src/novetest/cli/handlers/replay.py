"""``novetest replay <run_id>`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``, including the outcome→(envelope, exit)
mapper ``_build_replay_envelope``. Reconstructs a prior run's context and
re-executes it, classifying reproducibility. Pure motion — the wire contract
is unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any

from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _resolve_run_reference,
    _store_corrupt_envelope,
)
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
)
from novetest.memory import ProjectStoreCorruptError
from novetest.models import ReplayResult, RunReference
from novetest.orchestration.projection import replay_outcome_payload
from novetest.replay import (
    REASON_ENGINE_NOT_READY,
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    ReplayUnavailable,
    replay_run,
)


def _build_replay_envelope(
    original_ref: RunReference, outcome: ReplayResult | ReplayUnavailable
) -> tuple[Envelope, int]:
    """Map a Replay outcome onto an ``(Envelope, exit_code)`` pair.

    Exit-code split (rationale in the handoff §5.3): a classify-able outcome
    (``ReplayResult`` of any classification, including the valid
    ``unable_to_replay``) is a success at exit 0. A ``ReplayUnavailable`` is
    a user/engine error: ``engine-not-ready`` / ``target-missing`` map to
    exit 4 (``EXIT_ENGINE_MISSING``, mirroring ``run`` / ``test``);
    ``original-not-found`` maps to exit 2 (``EXIT_USAGE``, mirroring
    ``inspect``); the remaining "structured unavailable" reasons
    (``tombstoned-original`` / ``context-reconstruction-failed`` /
    ``missing-derived-facts``) are non-error data outcomes at exit 0.
    """
    data: dict[str, Any] = {
        "original_run_reference": original_ref.to_dict(),
        "replay_outcome": replay_outcome_payload(outcome),
    }
    if isinstance(outcome, ReplayResult):
        return Envelope(command="replay", ok=True, data=data), EXIT_OK

    reason = outcome.reason
    if reason in (REASON_ENGINE_NOT_READY, REASON_TARGET_MISSING):
        exit_code = EXIT_ENGINE_MISSING
    elif reason == REASON_ORIGINAL_NOT_FOUND:
        exit_code = EXIT_USAGE
    else:
        # tombstoned-original / context-reconstruction-failed /
        # missing-derived-facts — structured outcome, not an error.
        return Envelope(command="replay", ok=True, data=data), EXIT_OK

    return (
        Envelope(
            command="replay",
            ok=False,
            data=data,
            errors=(
                EnvelopeError(
                    code=f"replay-{reason}",
                    message=outcome.detail or reason,
                ),
            ),
        ),
        exit_code,
    )


def replay_cmd(run_id: str, *, reruns: int = 1, timeout: float = 600.0) -> None:
    """Replay a prior run and classify its reproducibility.

    Reconstructs the original run's context from stored evidence, re-executes
    it ``--reruns`` times through the SAME governed native engine path
    (``run/execute_with_engine_context``), and classifies the result as
    ``reproducible`` / ``inconsistent`` / ``unable_to_replay`` (REQ-REP-003).

    ``<run_id>`` is the ORIGINAL run's id; a stale/fake id surfaces a
    structured ``not-found`` error (exit 2), mirroring ``inspect``. The
    replay-execution runs are persisted as first-class Memory Entries (they
    appear in ``memory list``); the Replay Result is cached at
    ``<store>/replay/results/run_<id>/replay_result.json``.

    ``--reruns`` defaults to 1 (cheap single replay). Investigating flakiness
    typically wants ``--reruns 5``. ``unable_to_replay`` is a VALID
    classification (exit 0), not an error.
    """
    store = _require_store("replay")
    original_ref = _resolve_run_reference(store, "replay", run_id)
    try:
        outcome = asyncio.run(
            replay_run(store, original_ref, reruns=reruns, timeout=timeout)
        )
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("replay", str(exc)), EXIT_STORAGE)
    envelope, exit_code = _build_replay_envelope(original_ref, outcome)
    _emit_and_exit(envelope, exit_code)
