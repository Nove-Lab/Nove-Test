"""``novetest status`` workflow — Project Store summary view.

Returns the latest Run Reference and Run History readiness, plus
per-sub-report availability flags. The four sub-report flags (coverage,
regression, localization, replay) are computed by **cache-only reads** of
each engine's previously-derived facts: ``status`` MUST NOT trigger a
derivation as a side effect (the verb is the "what is cached?" gate,
not a derive-on-read action).

The availability path mirrors ``inspect.py``'s ``_resolve_inspect_*``
helpers — same retrieval functions, same discriminator-based decision —
so ``status.sub_reports.X == "available"`` and
``inspect.X_outcome.kind == "fact-set"`` MUST agree for any given run.
Pre-Defect-6 this file left every flag hard-defaulted to ``False`` from
the Phase 1 stub, which made ``status`` lie about availability for
coverage / localization / regression even when the on-disk facts were
present AND ``inspect`` correctly reported them as ``fact-set``. The
post-Defect-6 contract: three sources of truth (``status``, ``inspect``,
on-disk file) agree by construction because they all read the same
underlying cache (see
``agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md``
for the empirical reproduction).

Replay (Phase 5 entry) is now a cache-only probe like the other three:
``replay_available`` flips ``True`` when
``<store>/replay/results/run_<latest_id>/replay_result.json`` exists and
parses (``get_replay_result`` returns a ``ReplayResult``). ``status`` reports
"a Replay Attempt has already produced a result for the latest run" — NOT "a
replay could be attempted" (that eligibility question is
``check_replay_availability``). Like the others, this read NEVER executes a
replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.coverage import get_coverage_facts
from novetest.localization import LocalizationFinding, get_localization_findings
from novetest.memory import (
    ProjectStore,
    list_run_history,
)
from novetest.memory.project_store import PinnedEngine
from novetest.models import MemoryEntry, ReplayResult
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.regression import (
    RegressionFactSet,
    get_regression_facts,
    resolve_baseline_for_run,
)
from novetest.replay import get_replay_result


@dataclass(slots=True, frozen=True)
class StatusView:
    """Status entity surfaced by ``novetest status``.

    ``pinned_engine`` surfaces the store's anchored engine pin (decision
    ``2026-07-03-engine-selection-policy.md``; additive envelope field).
    ``None`` only for a legacy pin-less store on a markerless anchor —
    every store touched by ``init`` or the D6 migration carries a pin.
    """

    latest_entry: MemoryEntry | None
    run_history_size: int
    coverage_available: bool = False
    regression_available: bool = False
    localization_available: bool = False
    replay_available: bool = False
    pinned_engine: PinnedEngine | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "latest_run_reference": (
                self.latest_entry.run_record.run_reference.to_dict()
                if self.latest_entry is not None
                else None
            ),
            "run_history_size": self.run_history_size,
            "pinned_engine": (
                self.pinned_engine.to_dict()
                if self.pinned_engine is not None
                else None
            ),
            "sub_reports": {
                "coverage": "available" if self.coverage_available else "unavailable",
                "regression": "available" if self.regression_available else "unavailable",
                "localization": (
                    "available" if self.localization_available else "unavailable"
                ),
                "replay": "available" if self.replay_available else "unavailable",
            },
        }


def build_status_view(store: ProjectStore) -> StatusView:
    """Aggregate the current Memory state into a Status view.

    The four ``*_available`` flags are computed by cache-only retrieval
    against the newest **live** Memory Entry — the same run that surfaces
    as ``latest_run_reference`` on the envelope. ``list_run_history``
    returns newest-first across BOTH live and tombstoned runs, so the head
    is the first entry that is NOT a tombstone (a deleted run must never
    surface as the current head — see ``_is_tombstoned``). When no live run
    remains — a fresh store with no runs, OR a store whose runs have all
    been tombstoned — every flag stays ``False`` and
    ``latest_run_reference`` is ``null``, while ``run_history_size`` keeps
    its full count (tombstones included), unchanged.

    Each flag is a pure ``isinstance(result, FactSet)`` check against the
    relevant engine's ``get_*`` cache-read helper:

    - Coverage: ``get_coverage_facts(store, latest_ref)`` →
      ``CoverageFactSet`` means
      ``<store>/coverage/facts/run_<latest_id>/coverage_facts.json``
      exists and parses cleanly. Granularity-independent: per-test,
      per-test-class, per-test-file, AND aggregate all surface as
      ``available`` (the Defect-6 reproduction was a cargo aggregate run
      whose facts were on disk but reported as ``unavailable``).
    - Localization: ``get_localization_findings(store, latest_ref)`` →
      ``LocalizationFinding`` means
      ``<store>/localization/findings/run_<latest_id>/localization_findings.json``
      exists. Mode-independent: per-test SBFL, aggregate SBFL, and
      failure-proximity all surface as ``available``.
    - Regression: see ``_latest_regression_available`` — needs a prior
      comparable sibling AND a cached pair file.
    - Replay: ``get_replay_result(store, latest_ref)`` → ``ReplayResult``
      means
      ``<store>/replay/results/run_<latest_id>/replay_result.json`` exists
      (a Replay Attempt has been made). Classification-independent:
      ``reproducible`` / ``inconsistent`` / ``unable_to_replay`` all surface
      as ``available`` (the result exists either way).

    The cache-only contract is load-bearing: ``status`` must be cheap and
    side-effect-free. We deliberately do NOT call ``compare_runs`` here
    (which would derive on cache miss) — the regression flag is computed
    via ``get_regression_facts`` so a pair that has never been compared
    surfaces as ``unavailable`` even when both runs exist.
    """

    history = list_run_history(store)
    run_history_size = len(history)
    latest = next((entry for entry in history if not _is_tombstoned(entry)), None)
    if latest is None:
        # No live head: either a fresh store (empty history) or every run
        # has been tombstoned. ``run_history_size`` still reports the full
        # count (tombstones included) — only the head selection changes.
        return StatusView(
            latest_entry=None,
            run_history_size=run_history_size,
            pinned_engine=store.pinned_engine,
        )

    latest_ref = latest.run_record.run_reference
    coverage_available = isinstance(
        get_coverage_facts(store, latest_ref), CoverageFactSet
    )
    localization_available = isinstance(
        get_localization_findings(store, latest_ref), LocalizationFinding
    )
    regression_available = _latest_regression_available(store, latest)
    replay_available = isinstance(
        get_replay_result(store, latest_ref), ReplayResult
    )
    return StatusView(
        latest_entry=latest,
        run_history_size=run_history_size,
        coverage_available=coverage_available,
        regression_available=regression_available,
        localization_available=localization_available,
        replay_available=replay_available,
        pinned_engine=store.pinned_engine,
    )


def _is_tombstoned(entry: MemoryEntry) -> bool:
    """Return True iff ``entry`` is a soft-deleted (tombstoned) run.

    Discriminant: the Memory tombstone primitive stamps
    ``run_record.status == "tombstoned"`` on delete (equivalently
    ``entry.tombstoned_at is not None`` for a healthy tombstone; the
    status token is the more robust of the two — it also holds if a
    delete is interrupted after the record mutate but before the
    directory rename). ``status`` filters tombstones OUT of head
    selection so a deleted run is never reported as the current head
    (ORC-16).

    Recorded non-goal: legacy partial-state tombstones (MEM-02 — the
    record kept its original status and ``tombstoned_at`` was never
    stamped) are indistinguishable from a live run at this layer and are
    out of scope here. Their creation path is removed by the parallel S9
    Memory slice; no Memory-side API is added for status.
    """

    return entry.run_record.status == "tombstoned"


def _latest_regression_available(
    store: ProjectStore, latest_entry: MemoryEntry
) -> bool:
    """Return True iff a cached ``regression_facts.json`` exists for the
    natural ``(prior_sibling, latest_entry)`` pair on the same target.

    Pair selection is Regression's shared ``resolve_baseline_for_run``
    selector — the most-recent strictly-older live sibling on the same
    ``target_expression`` AND the same ``engine_name`` (D5 of
    ``decisions/2026-07-03-engine-selection-policy.md``) — the exact
    selector ``inspect.py::_resolve_inspect_regression`` composes, so the
    two verbs agree by construction. The difference is the final read:
    ``inspect`` calls ``compare_runs`` (which derives on cache miss);
    ``status`` calls ``get_regression_facts`` (cache-only) because
    ``status`` MUST NOT derive as a side effect.

    A run with no comparable prior (fresh store, single run on the target,
    or only cross-engine priors) returns ``False`` — the natural "no
    comparable baseline" answer. Two comparable runs without a prior
    ``regression compare`` / ``compare`` invocation also return ``False``
    because the pair file has never been written.
    """

    baseline_ref = resolve_baseline_for_run(store, latest_entry)
    if baseline_ref is None:
        return False
    latest_ref = latest_entry.run_record.run_reference
    return isinstance(
        get_regression_facts(store, baseline_ref, latest_ref), RegressionFactSet
    )
