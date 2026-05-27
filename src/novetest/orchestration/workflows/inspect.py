"""``novetest inspect <run_id>`` workflow — aggregated single-run view.

Composes the already-persisted evidence for ONE stored run into a single
view: the Run Record summary plus per-engine fact sections. This file
populates the Coverage section (cache-read via ``get_coverage_facts``) AND
the Regression section (composed at the orchestration layer using
``find_runs_for_target`` + ``compare_runs`` — see
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
from novetest.memory import (
    ProjectStore,
    RunEvidenceNotFoundError,
    find_runs_for_target,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models import MemoryEntry
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.regression import (
    REASON_NO_COMPARABLE_BASELINE,
    RegressionFactSet,
    RegressionUnavailable,
    compare_runs,
)


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

    Localization / Replay engines are not yet wired, so ``to_dict`` reports
    them as ``unavailable`` sub-reports — the same string-marker convention
    ``StatusView`` uses.
    """

    entry: MemoryEntry
    coverage_outcome: CoverageFactSet | CoverageUnavailable
    regression_outcome: RegressionFactSet | RegressionUnavailable

    def to_dict(self) -> dict[str, object]:
        record = self.entry.run_record
        coverage_present = isinstance(self.coverage_outcome, CoverageFactSet)
        regression_present = isinstance(self.regression_outcome, RegressionFactSet)
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
            "coverage_outcome": _coverage_outcome_section(self.coverage_outcome),
            "regression_outcome": _regression_outcome_section(self.regression_outcome),
            "sub_reports": {
                "coverage": "available" if coverage_present else "unavailable",
                "regression": "available" if regression_present else "unavailable",
                "localization": "unavailable",
                "replay": "unavailable",
            },
        }


def build_inspect_view(store: ProjectStore, run_id: str) -> InspectView | None:
    """Aggregate the stored evidence for ``run_id`` into an ``InspectView``.

    Returns ``None`` when no Memory Entry (live or tombstoned) matches
    ``run_id`` — the CLI handler maps that to a structured ``not-found``
    envelope. Tombstoned runs remain inspectable, mirroring ``memory show``.

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

    history = list_run_history(store)
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
    )


def _resolve_inspect_regression(
    store: ProjectStore,
    inspected: MemoryEntry,
) -> RegressionFactSet | RegressionUnavailable:
    """Resolve the baseline-for-this-specific-run and call ``compare_runs``.

    The Regression engine's ``resolve_latest_baseline`` returns the GLOBAL
    latest two runs on a target — wrong fit for ``inspect <some_old_run>``,
    which wants "the most recent live run that is strictly OLDER than this
    one on the same target". Composed here at the orchestration layer using
    Memory's ``find_runs_for_target`` + Regression's ``compare_runs`` —
    no new engine surface introduced (decision: keep engine surface frozen,
    the composition is a small orchestration concern).

    Tombstone handling: ``find_runs_for_target(..., include_tombstoned=False)``
    drops tombstoned siblings on the read side, so a live ``inspected`` run
    with only tombstoned priors surfaces ``REASON_NO_COMPARABLE_BASELINE``.
    A tombstoned ``inspected`` run with live priors reaches ``compare_runs``,
    which fails-hard with ``REASON_RUN_TOMBSTONED`` per decision §C.1 — no
    special-case needed here.
    """

    inspected_ref = inspected.run_record.run_reference
    siblings = find_runs_for_target(
        store,
        inspected.run_record.target_expression,
        include_tombstoned=False,
    )
    prior = [
        s
        for s in siblings
        if s.run_record.run_reference.created_at < inspected_ref.created_at
    ]
    if not prior:
        return RegressionUnavailable(
            reason=REASON_NO_COMPARABLE_BASELINE,
            detail=inspected.run_record.target_expression,
            baseline_run_reference=None,
            target_run_reference=inspected_ref,
        )
    prior.sort(key=lambda e: e.run_record.run_reference.created_at, reverse=True)
    baseline_ref = prior[0].run_record.run_reference
    return compare_runs(store, baseline_ref, inspected_ref)


def _coverage_outcome_section(
    outcome: CoverageFactSet | CoverageUnavailable,
) -> dict[str, object]:
    """Project a Coverage outcome onto the frozen ``coverage_outcome`` shape.

    Identical wire shape to ``cli/app.py::_coverage_outcome_payload`` — the
    two cannot share a single function without an orchestration↔cli import
    cycle, and the shape is frozen by
    ``decisions/2026-05-16-coverage-outcome-envelope-shape.md`` so the
    duplication carries no drift risk.
    """

    if isinstance(outcome, CoverageFactSet):
        return {
            "kind": "fact-set",
            "run_reference": outcome.run_reference.to_dict(),
            "mapping_granularity": outcome.mapping_granularity,
            "summary": outcome.summary.to_dict(),
        }
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _regression_outcome_section(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, object]:
    """Project a Regression outcome onto the working-draft ``regression_outcome`` shape.

    Identical wire shape to ``cli/app.py::_regression_outcome_payload`` —
    the same orchestration↔cli import-cycle reason the Coverage analog
    duplicates its projection. Shape is the working draft per
    ``decisions/2026-05-26-regression-facts-json-layout.md`` §C.2; PM
    freezes it via a follow-up decision after Manual Test fields it. Once
    frozen, drift risk is bounded.
    """

    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }
