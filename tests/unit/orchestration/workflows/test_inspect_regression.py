"""Unit tests for the Regression section of `build_inspect_view`.

Companion to ``test_inspect.py``: that file covers the Coverage section and
the container shape; this file pins the Regression-section composition
(`_resolve_inspect_regression`). Memory + Regression seams are
monkeypatched at the `inspect` module so the tests never touch the
filesystem.
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS
from novetest.localization import LocalizationUnavailable
from novetest.localization.results import REASON_MISSING_DERIVED_FACTS as LOC_REASON_MISSING
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration.workflows import inspect as inspect_module
from novetest.orchestration.workflows.inspect import build_inspect_view
from novetest.regression import (
    REASON_ENGINE_MISMATCH,
    REASON_NO_COMPARABLE_BASELINE,
    REASON_RUN_TOMBSTONED,
    RegressionUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    run_id: str,
    *,
    created_at: int,
    target_expression: str = "tests/",
    tombstoned_at: int | None = None,
    engine_name: str = "pytest",
) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type="dir",
        engine_name=engine_name,
        ecosystem="python",
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1,
        summary_counts={"passed": 1, "total": 1},
    )
    return MemoryEntry(
        entry_id=run_id,
        run_record=record,
        stored_at=created_at + 2,
        has_coverage_facts=False,
        tombstoned_at=tombstoned_at,
    )


def _make_regression_fact_set(baseline_ref: RunReference, target_ref: RunReference) -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=baseline_ref,
        target_run_reference=target_ref,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=100,
        summary=RegressionSummary(
            regressed=0,
            fixed=0,
            still_failing=0,
            still_passing=1,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=1,
            total_target_tests=1,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )


def _patch_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    history: list[MemoryEntry],
    retrieved: MemoryEntry,
    siblings: list[MemoryEntry],
    compare_result: RegressionFactSet | RegressionUnavailable | None,
) -> list[tuple[RunReference, RunReference]]:
    """Wire all four inspect seams. Returns a list captured `compare_runs`
    is called with — empty when `_resolve_inspect_regression` short-
    circuits at the "no prior" branch."""

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store: history)
    monkeypatch.setattr(
        inspect_module, "retrieve_run_evidence", lambda *_a, **_k: retrieved
    )
    monkeypatch.setattr(
        inspect_module,
        "find_runs_for_target",
        lambda _store, _target, *, include_tombstoned=False: siblings,
    )
    # Coverage is the other engine in the inspect surface — keep it
    # unavailable here so the Regression-section tests stay focused.
    monkeypatch.setattr(
        inspect_module,
        "get_coverage_facts",
        lambda _s, ref: CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="coverage out of scope for these regression tests",
            run_reference=ref,
        ),
    )

    seen: list[tuple[RunReference, RunReference]] = []

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> RegressionFactSet | RegressionUnavailable:
        seen.append((baseline, target))
        if compare_result is None:
            raise AssertionError(
                "compare_runs called but no compare_result configured for this test"
            )
        return compare_result

    monkeypatch.setattr(inspect_module, "compare_runs", fake_compare)

    # Localization section — default to unavailable so the Regression-section
    # tests stay focused and don't hit the filesystem.
    monkeypatch.setattr(
        inspect_module,
        "get_localization_findings",
        lambda _store, ref: LocalizationUnavailable(
            run_reference=ref,
            reason=LOC_REASON_MISSING,
            detail="findings not yet derived",
        ),
    )

    return seen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_latest_of_two_runs_resolves_prior_as_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _make_entry("01PRIORPRIORPRIORPRIORPRIO", created_at=1)
    inspected = _make_entry("01INSPECTINSPECTINSPECTINS", created_at=2)
    expected_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, inspected.run_record.run_reference
    )

    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        siblings=[inspected, prior],
        compare_result=expected_fact_set,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    # The composer called compare_runs(prior, inspected) — argument order
    # matches decision §2 (older=baseline, newer=target).
    assert seen == [(prior.run_record.run_reference, inspected.run_record.run_reference)]

    payload = view.to_dict()
    outcome = payload["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["baseline_run_reference"]["run_id"] == prior.run_record.run_reference.run_id
    assert outcome["target_run_reference"]["run_id"] == inspected.run_record.run_reference.run_id
    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"


def test_inspecting_an_old_run_uses_immediate_prior_not_global_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspecting a middle run in a 3-run history: the baseline is the run
    immediately BEFORE it (older), NOT the global latest. This is the
    composition decision documented in `_resolve_inspect_regression`."""

    oldest = _make_entry("01OLDESTOLDESTOLDESTOLDEST", created_at=1)
    middle = _make_entry("01MIDDLEMIDDLEMIDDLEMIDDLE", created_at=2)
    newest = _make_entry("01NEWESTNEWESTNEWESTNEWEST", created_at=3)
    expected_fact_set = _make_regression_fact_set(
        oldest.run_record.run_reference, middle.run_record.run_reference
    )

    seen = _patch_seams(
        monkeypatch,
        history=[newest, middle, oldest],  # newest-first per list_run_history
        retrieved=middle,                    # the inspected run
        siblings=[newest, middle, oldest],   # same target → all three
        compare_result=expected_fact_set,
    )

    view = build_inspect_view(object(), middle.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    # compare_runs was called once with the immediate prior (oldest), NOT
    # with the global latest pair (oldest, newest).
    assert seen == [(oldest.run_record.run_reference, middle.run_record.run_reference)]
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["baseline_run_reference"]["run_id"] == oldest.run_record.run_reference.run_id
    assert outcome["target_run_reference"]["run_id"] == middle.run_record.run_reference.run_id


def test_only_run_on_target_surfaces_no_comparable_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _make_entry("01ONLYRUNONLYRUNONLYRUNONL", created_at=5, target_expression="tests/")

    seen = _patch_seams(
        monkeypatch,
        history=[inspected],
        retrieved=inspected,
        siblings=[inspected],     # only itself
        compare_result=None,      # compare_runs must NOT be called
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    # The composer populates target_run_reference with the inspected run's
    # reference and leaves baseline_run_reference null (no baseline exists).
    assert outcome["target_run_reference"]["run_id"] == inspected.run_record.run_reference.run_id
    assert outcome["baseline_run_reference"] is None
    assert outcome["detail"] == "tests/"
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "unavailable"


def test_tombstoned_inspected_run_propagates_compare_run_tombstoned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tombstoned inspected run with a live prior reaches `compare_runs`,
    which fail-hards with `REASON_RUN_TOMBSTONED` per decision §C.1."""

    prior = _make_entry("01PRIORPRIORPRIORPRIORPRIO", created_at=1)
    inspected = _make_entry(
        "01TOMBSTONETOMBSTONETOMBST", created_at=2, tombstoned_at=999
    )
    inspected_ref = inspected.run_record.run_reference
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        # find_runs_for_target(include_tombstoned=False) — Memory drops the
        # tombstoned inspected run, so the prior is alone in siblings.
        siblings=[prior],
        compare_result=RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail="target",
            baseline_run_reference=prior.run_record.run_reference,
            target_run_reference=inspected_ref,
        ),
    )

    view = build_inspect_view(object(), inspected_ref.run_id)  # type: ignore[arg-type]
    assert view is not None
    # The prior IS strictly older than the inspected, so compare_runs IS
    # called — and the engine fails hard with TOMBSTONED.
    assert seen == [(prior.run_record.run_reference, inspected_ref)]
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_TOMBSTONED


def test_live_inspected_with_only_tombstoned_priors_surfaces_no_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`find_runs_for_target(include_tombstoned=False)` filters tombstoned
    priors upstream. The composer never sees them, so the live inspected
    run reports no comparable baseline."""

    inspected = _make_entry("01LIVEINSPECTLIVEINSPECTIN", created_at=5)
    # Note: `siblings=` is what `find_runs_for_target` returns — with
    # `include_tombstoned=False`, only the live inspected itself appears.
    seen = _patch_seams(
        monkeypatch,
        history=[inspected],  # the tombstoned priors are elided from history too — irrelevant
        retrieved=inspected,
        siblings=[inspected],
        compare_result=None,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE


def test_other_target_siblings_are_excluded_by_find_runs_for_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`find_runs_for_target` filters by `target_expression`; a run on a
    different target never reaches the composer's filter step."""

    other_target = _make_entry(
        "01OTHEROTHEROTHEROTHEROTHE", created_at=1, target_expression="other/"
    )
    inspected = _make_entry(
        "01SAMETARGETSAMETARGETSAME", created_at=2, target_expression="tests/"
    )
    # The siblings list IS what `find_runs_for_target("tests/", ...)` would
    # return — only the inspected itself (other_target's expression mismatches).
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, other_target],
        retrieved=inspected,
        siblings=[inspected],
        compare_result=None,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE


def test_engine_mismatch_between_inspected_and_prior_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`compare_runs` surfaces `REASON_ENGINE_MISMATCH` when the prior was
    pytest and the inspected is jest on the same `target_expression`."""

    prior = _make_entry(
        "01PRIORPYTESTPRIORPYTESTPR", created_at=1, engine_name="pytest"
    )
    inspected = _make_entry(
        "01INSPECTJESTINSPECTJESTIN", created_at=2, engine_name="jest"
    )
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        siblings=[inspected, prior],
        compare_result=RegressionUnavailable(
            reason=REASON_ENGINE_MISMATCH,
            detail="baseline engine_name='pytest' != target engine_name='jest'",
            baseline_run_reference=prior.run_record.run_reference,
            target_run_reference=inspected.run_record.run_reference,
        ),
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    # compare_runs IS called — the engine, not the composer, classifies it.
    assert len(seen) == 1
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_ENGINE_MISMATCH


def test_sub_reports_regression_flips_across_available_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `sub_reports["regression"]` marker must reflect the actual
    outcome — `"available"` only when a `RegressionFactSet` lands."""

    # Case 1: available (fact-set)
    prior = _make_entry("01PRIORAAAAAAAAAAAAAAAAAAA", created_at=1)
    inspected = _make_entry("01TARGETAAAAAAAAAAAAAAAAAA", created_at=2)
    expected_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, inspected.run_record.run_reference
    )
    _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        siblings=[inspected, prior],
        compare_result=expected_fact_set,
    )
    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"

    # Case 2: unavailable (single-run target)
    only = _make_entry("01ONLYBBBBBBBBBBBBBBBBBBBB", created_at=10)
    _patch_seams(
        monkeypatch,
        history=[only],
        retrieved=only,
        siblings=[only],
        compare_result=None,
    )
    view = build_inspect_view(object(), only.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "unavailable"
