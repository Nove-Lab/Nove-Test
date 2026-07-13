"""``novetest inspect <run_id>`` workflow — aggregated single-run view.

Composes the already-persisted evidence for ONE stored run into a single
view: the Run Record summary plus per-engine fact sections. This file
populates the Coverage section (cache-read via ``get_coverage_facts``) AND
the Regression section (composed at the orchestration layer using
Regression's ``resolve_baseline_for_run`` + ``compare_runs`` — see
``_resolve_inspect_regression`` for the composition rationale).
Localization / Replay remain present-but-``unavailable`` markers, mirroring
``StatusView``'s ``sub_reports`` convention; Phase 4/5 slices flip each
marker and add the matching detail block without changing this container
shape.

``inspect`` executes nothing — it is a pure read over Memory + Coverage +
Regression caches.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.coverage import CoverageUnavailable, get_coverage_facts
from novetest.localization import (
    LocalizationFinding,
    LocalizationUnavailable,
    get_localization_findings,
)
from novetest.memory import (
    ProjectStore,
    RunEvidenceNotFoundError,
    SkippedRecord,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models import MemoryEntry, ReplayResult
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.orchestration.projection import (
    coverage_outcome_payload,
    localization_outcome_payload,
    regression_outcome_payload,
    replay_outcome_payload,
)
from novetest.regression import (
    REASON_NO_COMPARABLE_BASELINE,
    RegressionFactSet,
    RegressionUnavailable,
    compare_runs,
    resolve_baseline_for_run,
)
from novetest.replay import ReplayUnavailable, get_replay_result


@dataclass(slots=True, frozen=True)
class InspectView:
    """Aggregated single-run view surfaced by ``novetest inspect``.

    ``coverage_outcome`` is the same discriminated block ``coverage show``
    emits (``decisions/2026-05-16-coverage-outcome-envelope-shape.md``):
    either a ``CoverageFactSet`` (kind ``fact-set``) or a
    ``CoverageUnavailable`` (kind ``unavailable``).

    ``regression_outcome`` is the working-draft block ``regression compare``
    emits (shape TBD-frozen per
    ``decisions/2026-05-26-regression-facts-json-layout.md`` §C.2): either
    a ``RegressionFactSet`` (kind ``fact-set``) or a
    ``RegressionUnavailable`` (kind ``unavailable``).

    Localization (Phase 4) and Replay (Phase 5) are now wired: ``to_dict``
    reports each sub-report ``available`` when its evidence resolved on disk,
    ``unavailable`` otherwise.
    """

    entry: MemoryEntry
    coverage_outcome: CoverageFactSet | CoverageUnavailable
    regression_outcome: RegressionFactSet | RegressionUnavailable
    localization_outcome: LocalizationFinding | LocalizationUnavailable
    replay_outcome: ReplayResult | ReplayUnavailable

    def to_dict(self) -> dict[str, object]:
        record = self.entry.run_record
        coverage_present = isinstance(self.coverage_outcome, CoverageFactSet)
        regression_present = isinstance(self.regression_outcome, RegressionFactSet)
        localization_present = isinstance(self.localization_outcome, LocalizationFinding)
        replay_present = isinstance(self.replay_outcome, ReplayResult)
        return {
            "run_reference": record.run_reference.to_dict(),
            "run_summary": {
                "status": record.status,
                "target_expression": record.target_expression,
                "target_type": record.target_type,
                "engine_name": record.engine_name,
                "ecosystem": record.ecosystem,
                "summary_counts": dict(record.summary_counts),
                "tombstoned": self.entry.tombstoned_at is not None,
            },
            "coverage_outcome": coverage_outcome_payload(self.coverage_outcome),
            "regression_outcome": regression_outcome_payload(self.regression_outcome),
            "localization_outcome": localization_outcome_payload(
                self.localization_outcome
            ),
            "replay_outcome": replay_outcome_payload(self.replay_outcome),
            "sub_reports": {
                "coverage": "available" if coverage_present else "unavailable",
                "regression": "available" if regression_present else "unavailable",
                "localization": "available" if localization_present else "unavailable",
                "replay": "available" if replay_present else "unavailable",
            },
        }


def build_inspect_view(
    store: ProjectStore,
    run_id: str,
    *,
    skipped: list[SkippedRecord] | None = None,
) -> InspectView | None:
    """Aggregate the stored evidence for ``run_id`` into an ``InspectView``.

    Returns ``None`` when no Memory Entry (live or tombstoned) matches
    ``run_id`` — the CLI handler maps that to a structured ``not-found``
    envelope. Tombstoned runs remain inspectable, mirroring ``memory show``.

    ``skipped`` is threaded to the history scan's MEM-05 collector so the
    CLI can distinguish a genuine miss from a corrupt-on-disk record whose
    ``run_id`` matches the requested id (Gate-1 Q1-A escalation to
    ``store-corrupt`` — ``inspect`` joins the S42 addressed-verb set).

    The Coverage section is sourced cache-read-only via
    ``get_coverage_facts`` — ``inspect`` never derives. A run executed
    without ``novetest run --coverage`` therefore yields a
    ``CoverageUnavailable`` (reason ``missing-derived-facts``).

    The Regression section is composed at this orchestration layer (see
    ``_resolve_inspect_regression``) so a stored old run inspects against
    the run IMMEDIATELY before it on the same target — NOT against the
    global latest pair. ``compare_runs`` itself is cache-aware: subsequent
    inspects of the same run hit the persisted ``regression_facts.json``
    without re-deriving.
    """

    history = list_run_history(store, skipped=skipped)
    target = next(
        (e for e in history if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target is None:
        return None
    ref = target.run_record.run_reference
    try:
        entry = retrieve_run_evidence(store, ref)
    except RunEvidenceNotFoundError:
        return None
    return InspectView(
        entry=entry,
        coverage_outcome=get_coverage_facts(store, ref),
        regression_outcome=_resolve_inspect_regression(store, entry),
        localization_outcome=_resolve_inspect_localization(store, entry),
        replay_outcome=get_replay_result(store, ref),
    )


def _resolve_inspect_regression(
    store: ProjectStore,
    inspected: MemoryEntry,
) -> RegressionFactSet | RegressionUnavailable:
    """Resolve the baseline-for-this-specific-run and call ``compare_runs``.

    The Regression engine's ``resolve_latest_baseline`` returns the GLOBAL
    latest two runs on a target — wrong fit for ``inspect <some_old_run>``,
    which wants "the most recent live run that is strictly OLDER than this
    one on the same target and the same engine". That selection is
    Regression's shared ``resolve_baseline_for_run`` selector — engine-
    scoped per D5 of ``decisions/2026-07-03-engine-selection-policy.md`` —
    composed here with ``compare_runs`` at the orchestration layer.

    Engine scoping (D5): a same-target prior produced by a DIFFERENT engine
    (legitimate mixed history under a transient ``--engine`` override) is
    never selected, so this path surfaces
    ``REASON_NO_COMPARABLE_BASELINE`` — not ``REASON_ENGINE_MISMATCH`` —
    when only cross-engine priors exist. The mismatch guard remains
    reachable via explicitly user-picked pairs (``regression compare``).

    Tombstone handling: the selector excludes tombstoned siblings
    (Memory's ``include_tombstoned=False`` convention), so a live
    ``inspected`` run with only tombstoned priors surfaces
    ``REASON_NO_COMPARABLE_BASELINE``. A tombstoned ``inspected`` run with
    live priors reaches ``compare_runs``, which fails-hard with
    ``REASON_RUN_TOMBSTONED`` per decision §C.1 — no special-case needed
    here.
    """

    inspected_ref = inspected.run_record.run_reference
    baseline_ref = resolve_baseline_for_run(store, inspected)
    if baseline_ref is None:
        return RegressionUnavailable(
            reason=REASON_NO_COMPARABLE_BASELINE,
            # A bare ``novetest test`` records an EMPTY target expression —
            # render the pinned placeholder instead of ``detail: ""``
            # (mirrors regression's S36-close pin; free-text only).
            detail=inspected.run_record.target_expression
            or "(entire workspace)",
            baseline_run_reference=None,
            target_run_reference=inspected_ref,
        )
    return compare_runs(store, baseline_ref, inspected_ref)


def _resolve_inspect_localization(
    store: ProjectStore,
    inspected: MemoryEntry,
) -> LocalizationFinding | LocalizationUnavailable:
    """Cache-only read of the Localization findings for the inspected run.

    Unlike Regression (which has no per-run cache, so ``inspect`` must
    compose ``resolve_baseline_for_run`` + ``compare_runs``), Localization HAS a
    per-run cache at
    ``<store>/localization/findings/run_<id>/localization_findings.json``.
    So ``inspect`` reads it cache-only via ``get_localization_findings`` — it
    NEVER derives (no subprocess, no SBFL math), mirroring the Coverage
    section's ``get_coverage_facts`` behavior. A run that is analyzable but
    has not had ``novetest localization`` run against it therefore surfaces
    ``LocalizationUnavailable(reason="missing-derived-facts")`` — the engine
    fills ``run_reference`` + the ``"findings not yet derived"`` detail when
    the input ref resolves but the cache is empty. (The ``no-failed-tests`` /
    ``no-coverage`` reasons only fire from ``derive_localization_findings``,
    never from this cache-only path.)
    """

    return get_localization_findings(store, inspected.run_record.run_reference)
