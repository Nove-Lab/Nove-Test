"""``get_replay_result`` and ``check_replay_availability``.

Mirrors ``localization/retrieval.py`` in shape:

- ``get_replay_result``        — pure cache read (no execution, no derivation).
- ``check_replay_availability`` — cheap precondition probe; bool result.

``get_replay_result`` is consumed by ``orchestration/novetest inspect`` and
``novetest status`` (both cache-only, side-effect-free). ``check_replay_availability``
is the eligibility predicate consumed by Orchestration: it answers "can a
Replay Attempt be reconstructed for this run?" — NOT "has one already run?".
"""

from __future__ import annotations

from novetest.memory.project_store import ProjectStore
from novetest.models.replay_result import ReplayResult
from novetest.models.run_reference import RunReference
from novetest.replay.context import ReplayContext, reconstruct_replay_context
from novetest.replay.errors import (
    REASON_MISSING_DERIVED_FACTS,
    ReplayUnavailable,
)
from novetest.replay.persistence import read_replay_result_raw


def get_replay_result(
    store: ProjectStore,
    original_ref: RunReference,
) -> ReplayResult | ReplayUnavailable:
    """Return the previously-derived Replay Result for ``original_ref``.

    Returns:
    - ``ReplayResult`` when ``replay_result.json`` exists for the run.
    - ``ReplayUnavailable(reason="missing-derived-facts")`` when no Replay
      Attempt has been made (the cache file is absent). The caller should
      invoke ``replay_run`` to produce one.

    Cache-only: never executes a replay. Mirrors ``get_localization_findings``
    / ``get_coverage_facts``.
    """
    raw = read_replay_result_raw(store, original_ref)
    if raw is None:
        return ReplayUnavailable(
            run_reference=original_ref,
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="no replay attempt has been made for this run",
        )
    return ReplayResult.from_dict(raw)


def check_replay_availability(
    store: ProjectStore,
    original_ref: RunReference,
) -> bool:
    """Return True iff a Replay Attempt can be reconstructed for the run.

    Cheap probe for Orchestration eligibility evaluation: it reuses
    ``reconstruct_replay_context`` and reports whether the context resolves
    (original run present, not tombstoned, workspace path live). Does NOT
    probe engine readiness (async) and does NOT execute anything.

    Missing-tolerant by design (mirrors ``check_localization_availability``):
    any reconstruction failure returns ``False``.
    """
    return isinstance(
        reconstruct_replay_context(store, original_ref), ReplayContext
    )
