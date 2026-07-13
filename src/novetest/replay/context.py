"""``reconstruct_replay_context`` — rebuild the replay execution context.

Resolves, from stored Run evidence, everything the governed Run path needs
to re-execute a prior run under reconstructed conditions (REQ-REP-001):

- the original ``RunRecord`` (for later consistency classification),
- the ``TestTarget`` (re-resolved from the record's ``target_expression``
  against the live workspace), and
- the ``NativeEngineContext`` (recorded engine name / ecosystem / version),

so ``replay_run`` can hand them to ``run/execute_with_engine_context`` and
keep the SAME native engine path the original run used (REQ-REP-002).

This is a **pure, synchronous** resolution step (per the interface
contract): it reads Memory and classifies the target, but does NOT probe
engine readiness (an async concern handled by ``replay_run``) and does NOT
verify that the target files still exist on disk (a runtime concern — a
vanished test file surfaces as an ``errored`` replay run, which the
classifier maps to ``unable_to_replay``, rather than as a reconstruction
failure here).
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.memory import (
    ProjectStore,
    RunEvidenceNotFoundError,
    retrieve_run_evidence,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.replay.errors import (
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    REASON_TOMBSTONED_ORIGINAL,
    ReplayUnavailable,
)
from novetest.run import NativeEngineContext, TestTarget, resolve_test_target


@dataclass(slots=True, frozen=True)
class ReplayContext:
    """Everything ``replay_run`` needs to re-execute a prior run.

    ``original_record`` is the run being replayed (the comparison baseline
    for ``classify_replay_consistency``). ``test_target`` and
    ``engine_context`` are handed verbatim to
    ``run/execute_with_engine_context``.
    """

    original_record: RunRecord
    test_target: TestTarget
    engine_context: NativeEngineContext


def reconstruct_replay_context(
    store: ProjectStore,
    original_ref: RunReference,
) -> ReplayContext | ReplayUnavailable:
    """Rebuild the replay context for ``original_ref`` from stored evidence.

    Returns a ``ReplayContext`` on success, or a ``ReplayUnavailable`` when:

    - the original run has no stored evidence (``original-not-found``),
    - the original run was tombstoned (``tombstoned-original`` — a deleted
      run is intentionally non-replayable), or
    - the workspace path no longer exists (``target-missing``).

    Engine readiness is NOT checked here (``replay_run`` does that
    asynchronously); a non-existent *target file* within a live workspace is
    also not rejected here — it surfaces downstream as an errored replay run.
    """
    try:
        entry = retrieve_run_evidence(store, original_ref)
    except RunEvidenceNotFoundError:
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_ORIGINAL_NOT_FOUND,
            detail=f"no run evidence for run_id={original_ref.run_id!r}",
        )

    if entry.tombstoned_at is not None:
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_TOMBSTONED_ORIGINAL,
            detail="original run was tombstoned; it cannot be replayed",
        )

    record = entry.run_record
    workspace_path = store.path.parent
    if not workspace_path.is_dir():
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_TARGET_MISSING,
            detail=f"workspace path {workspace_path} no longer exists",
        )

    test_target = resolve_test_target(record.target_expression, workspace_path)
    engine_context = NativeEngineContext(
        ecosystem=record.ecosystem,
        engine_name=record.engine_name,
        engine_version=record.engine_version,
    )
    return ReplayContext(
        original_record=record,
        test_target=test_target,
        engine_context=engine_context,
    )
