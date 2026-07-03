"""Unit tests for the `build_inspect_view` workflow + `InspectView.to_dict`.

Focused on the aggregation wiring — run lookup, the Coverage section
sourcing, the not-found signal, and the wire shape of the aggregated
view. The Memory / Coverage seams (`list_run_history`,
`retrieve_run_evidence`, `get_coverage_facts`) are monkeypatched at the
`inspect` module so the unit tests never touch the filesystem.
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS
from novetest.localization import LocalizationUnavailable
from novetest.localization.results import REASON_MISSING_DERIVED_FACTS as LOC_REASON_MISSING
from novetest.memory import RunEvidenceNotFoundError
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.coverage_fact_set import CoverageFactSet, CoverageSummary
from novetest.orchestration.workflows import inspect as inspect_module
from novetest.orchestration.workflows.inspect import InspectView, build_inspect_view


# ---------------------------------------------------------------------------
# Helpers — synthetic stand-ins so the unit tests never touch a Project Store.
# ---------------------------------------------------------------------------


_RUN_ID = "01TESTTESTTESTTESTTESTTEST"


def _make_entry(
    run_id: str = _RUN_ID, *, tombstoned_at: int | None = None
) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=1)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="directory",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1,
        completed_at=2,
        summary_counts={"passed": 3, "failed": 0, "total": 3},
    )
    return MemoryEntry(
        entry_id=run_id,
        run_record=record,
        stored_at=3,
        has_coverage_facts=False,
        tombstoned_at=tombstoned_at,
    )


def _make_fact_set(run_id: str = _RUN_ID) -> CoverageFactSet:
    ref = RunReference(run_id=run_id, created_at=1)
    summary = CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=80.0,
    )
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=summary,
        files=(),
        derived_at=4,
    )


def _patch_memory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    history: list[MemoryEntry],
    retrieved: MemoryEntry | RunEvidenceNotFoundError | None = None,
) -> None:
    """Stub `list_run_history`, `retrieve_run_evidence`, and
    `resolve_baseline_for_run` at the inspect seam.

    The baseline selector is stubbed to ``None`` ("no comparable
    baseline"), which keeps the Regression section on its unavailable
    short-circuit — this fixture's tests focus on the Coverage section and
    the container shape. Regression-section composition is pinned in
    ``test_inspect_regression.py`` at the same selector seam.
    ``compare_runs`` is also stubbed to a "must not be called" guard so a
    misconfigured test fails loudly instead of silently scanning a non-
    existent filesystem.
    """

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store: history)

    def fake_retrieve(_store: Any, _ref: RunReference) -> MemoryEntry:
        if isinstance(retrieved, RunEvidenceNotFoundError):
            raise retrieved
        assert retrieved is not None, "retrieve_run_evidence stub not configured"
        return retrieved

    monkeypatch.setattr(inspect_module, "retrieve_run_evidence", fake_retrieve)

    monkeypatch.setattr(
        inspect_module,
        "resolve_baseline_for_run",
        lambda _store, _entry: None,
    )

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError(
            "compare_runs called from inspect; use test_inspect_regression.py's "
            "selector seam to drive the Regression-section path explicitly"
        )

    monkeypatch.setattr(inspect_module, "compare_runs", must_not_be_called)

    # Localization section — default to unavailable (missing_derived_facts) so
    # existing Coverage-section tests stay focused and don't hit the filesystem.
    monkeypatch.setattr(
        inspect_module,
        "get_localization_findings",
        lambda _store, ref: LocalizationUnavailable(
            run_reference=ref,
            reason=LOC_REASON_MISSING,
            detail="findings not yet derived",
        ),
    )

    # Replay section — default to unavailable so existing Coverage-section
    # tests stay focused and don't hit the filesystem.
    from novetest.replay import (
        REASON_MISSING_DERIVED_FACTS as REPLAY_REASON_MISSING,
        ReplayUnavailable,
    )

    monkeypatch.setattr(
        inspect_module,
        "get_replay_result",
        lambda _store, ref: ReplayUnavailable(
            run_reference=ref,
            reason=REPLAY_REASON_MISSING,
            detail="no replay attempt has been made for this run",
        ),
    )


# ---------------------------------------------------------------------------
# build_inspect_view — lookup + not-found
# ---------------------------------------------------------------------------


def test_unknown_run_id_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Memory Entry matches the run_id → `None` (CLI maps to not-found)."""

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store: [])

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("get_coverage_facts called for an unknown run_id")

    monkeypatch.setattr(inspect_module, "get_coverage_facts", must_not_be_called)

    assert build_inspect_view(object(), "fake-id") is None  # type: ignore[arg-type]


def test_entry_vanishing_between_list_and_retrieve_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: a race where the entry is listed but gone on retrieve."""

    _patch_memory(
        monkeypatch,
        history=[_make_entry()],
        retrieved=RunEvidenceNotFoundError("gone"),
    )
    monkeypatch.setattr(
        inspect_module, "get_coverage_facts", lambda *_a, **_k: _make_fact_set()
    )
    assert build_inspect_view(object(), _RUN_ID) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# build_inspect_view + InspectView.to_dict — Coverage section
# ---------------------------------------------------------------------------


def test_view_with_coverage_facts_projects_fact_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry()
    _patch_memory(monkeypatch, history=[entry], retrieved=entry)

    seen_ref: list[RunReference] = []

    def fake_get(_store: Any, ref: RunReference) -> CoverageFactSet:
        seen_ref.append(ref)
        return _make_fact_set()

    monkeypatch.setattr(inspect_module, "get_coverage_facts", fake_get)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert isinstance(view, InspectView)
    assert seen_ref and seen_ref[0].run_id == _RUN_ID

    payload = view.to_dict()
    run_reference = payload["run_reference"]
    assert isinstance(run_reference, dict)
    assert run_reference["run_id"] == _RUN_ID
    assert run_reference["created_at"] == 1

    outcome = payload["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["mapping_granularity"] == "per-test"
    assert outcome["summary"]["percent_covered"] == 80.0
    assert outcome["run_reference"]["run_id"] == _RUN_ID

    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["coverage"] == "available"


def test_view_without_coverage_facts_projects_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run executed without `--coverage` → `kind: "unavailable"`."""

    entry = _make_entry()
    _patch_memory(monkeypatch, history=[entry], retrieved=entry)

    def fake_get(_store: Any, ref: RunReference) -> CoverageUnavailable:
        return CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="No coverage_facts.json found for this run",
            run_reference=ref,
        )

    monkeypatch.setattr(inspect_module, "get_coverage_facts", fake_get)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert isinstance(view, InspectView)
    payload = view.to_dict()

    outcome = payload["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_MISSING_DERIVED_FACTS
    assert outcome["run_reference"]["run_id"] == _RUN_ID

    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["coverage"] == "unavailable"


# ---------------------------------------------------------------------------
# InspectView.to_dict — container shape
# ---------------------------------------------------------------------------


def test_run_summary_carries_record_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _make_entry()
    _patch_memory(monkeypatch, history=[entry], retrieved=entry)
    monkeypatch.setattr(
        inspect_module, "get_coverage_facts", lambda *_a, **_k: _make_fact_set()
    )

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    summary = view.to_dict()["run_summary"]
    assert isinstance(summary, dict)
    assert summary["status"] == "passed"
    assert summary["target_expression"] == "tests/"
    assert summary["target_type"] == "directory"
    assert summary["engine_name"] == "pytest"
    assert summary["ecosystem"] == "python"
    assert summary["summary_counts"] == {"passed": 3, "failed": 0, "total": 3}
    assert summary["tombstoned"] is False


def test_pending_engines_are_unavailable_sub_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression / Localization / Replay are present-but-unavailable until
    their engines land — same string-marker convention as `status`."""

    entry = _make_entry()
    _patch_memory(monkeypatch, history=[entry], retrieved=entry)
    monkeypatch.setattr(
        inspect_module, "get_coverage_facts", lambda *_a, **_k: _make_fact_set()
    )

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "unavailable"
    assert sub_reports["localization"] == "unavailable"
    assert sub_reports["replay"] == "unavailable"


def test_tombstoned_run_remains_inspectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tombstoned Memory Entry is still inspectable (mirror `memory show`)."""

    entry = _make_entry(tombstoned_at=999)
    _patch_memory(monkeypatch, history=[entry], retrieved=entry)
    monkeypatch.setattr(
        inspect_module, "get_coverage_facts", lambda *_a, **_k: _make_fact_set()
    )

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert isinstance(view, InspectView)
    summary = view.to_dict()["run_summary"]
    assert isinstance(summary, dict)
    assert summary["tombstoned"] is True
