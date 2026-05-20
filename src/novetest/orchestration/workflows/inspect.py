"""``novetest inspect <run_id>`` workflow — aggregated single-run view.

Composes the already-persisted evidence for ONE stored run into a single
view: the Run Record summary plus a per-engine fact section. This slice
populates the Coverage section for real (sourced from the persisted
``coverage_facts.json``); the Regression / Localization / Replay sections
are present-but-``unavailable`` markers, mirroring ``StatusView``'s
``sub_reports`` convention. Phase 3/4/5 slices flip each marker and add the
matching detail block without changing this container shape.

``inspect`` executes nothing — it is a pure read over Memory + Coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.coverage import CoverageUnavailable, get_coverage_facts
from novetest.memory import (
    ProjectStore,
    RunEvidenceNotFoundError,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models import MemoryEntry
from novetest.models.coverage_fact_set import CoverageFactSet


@dataclass(slots=True, frozen=True)
class InspectView:
    """Aggregated single-run view surfaced by ``novetest inspect``.

    ``coverage_outcome`` is the same discriminated block ``coverage show``
    emits (``decisions/2026-05-16-coverage-outcome-envelope-shape.md``):
    either a ``CoverageFactSet`` (kind ``fact-set``) or a
    ``CoverageUnavailable`` (kind ``unavailable``). The Regression /
    Localization / Replay engines are not yet wired, so ``to_dict`` reports
    them as ``unavailable`` sub-reports — the same string-marker convention
    ``StatusView`` uses.
    """

    entry: MemoryEntry
    coverage_outcome: CoverageFactSet | CoverageUnavailable

    def to_dict(self) -> dict[str, object]:
        record = self.entry.run_record
        coverage_present = isinstance(self.coverage_outcome, CoverageFactSet)
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
            "sub_reports": {
                "coverage": "available" if coverage_present else "unavailable",
                "regression": "unavailable",
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
    return InspectView(entry=entry, coverage_outcome=get_coverage_facts(store, ref))


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
