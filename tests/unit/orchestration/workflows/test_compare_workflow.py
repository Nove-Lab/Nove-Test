"""W2/S23 (ORC-06) — ``build_compare_view`` workflow tests.

Covers the regression+coverage synthesis extracted from
``cli/app.py::compare_cmd``: both engines are called exactly once with
the resolved pair, the two blocks compose independently (partial
availability is data, not an error), and ``CompareView.to_dict()``
reproduces the pre-S23 inline envelope ``data`` payload byte-for-byte
(S17-precedent oracle: verbatim replica of the pre-move dict assembly,
including key order).

The CLI-handler wiring (run_id resolution → workflow → envelope) is
covered by ``tests/unit/cli/test_compare.py``; the subprocess e2e by
``tests/integration/orchestration/test_coverage_cli.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.compare import CoverageDelta
from novetest.models import RunReference
from novetest.models.coverage_fact_set import CoverageSummary
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration.projection import (
    coverage_delta_payload,
    regression_outcome_payload,
)
from novetest.orchestration.workflows import compare as wf
from novetest.orchestration.workflows.compare import CompareView, build_compare_view
from novetest.regression import RegressionUnavailable


_BASELINE_ID = "01CMPBASELINECMPBASELINECM"
_TARGET_ID = "01CMPTARGETCMPTARGETCMPTAR"
_STORE = object()  # the workflow only threads the store to the engines


def _baseline_ref() -> RunReference:
    return RunReference(run_id=_BASELINE_ID, created_at=1)


def _target_ref() -> RunReference:
    return RunReference(run_id=_TARGET_ID, created_at=2)


def _summary(percent: float = 80.0) -> CoverageSummary:
    return CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=percent,
    )


def _regression_fact_set() -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=_baseline_ref(),
        target_run_reference=_target_ref(),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=4,
        summary=RegressionSummary(
            regressed=0,
            fixed=1,
            still_failing=0,
            still_passing=12,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=13,
            total_target_tests=13,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )


def _regression_unavailable() -> RegressionUnavailable:
    return RegressionUnavailable(
        reason="run-tombstoned",
        detail="target",
        baseline_run_reference=_baseline_ref(),
        target_run_reference=_target_ref(),
    )


def _coverage_delta() -> CoverageDelta:
    return CoverageDelta(
        baseline_run_reference=_baseline_ref(),
        target_run_reference=_target_ref(),
        baseline_granularity="per-test",
        target_granularity="per-test",
        summary_before=_summary(70.0),
        summary_after=_summary(90.0),
        files_added=(),
        files_removed=(),
        file_deltas=(),
    )


def _coverage_unavailable() -> CoverageUnavailable:
    return CoverageUnavailable(
        reason="missing-derived-facts",
        detail="No coverage_facts.json for target",
        run_reference=_target_ref(),
    )


def _patch_engines(
    monkeypatch: pytest.MonkeyPatch,
    regression: RegressionFactSet | RegressionUnavailable,
    coverage: CoverageDelta | CoverageUnavailable,
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    regression_calls: list[tuple[Any, ...]] = []
    coverage_calls: list[tuple[Any, ...]] = []

    def fake_compare_runs(*args: Any) -> RegressionFactSet | RegressionUnavailable:
        regression_calls.append(args)
        return regression

    def fake_compare_coverage(*args: Any) -> CoverageDelta | CoverageUnavailable:
        coverage_calls.append(args)
        return coverage

    monkeypatch.setattr(wf, "compare_runs", fake_compare_runs)
    monkeypatch.setattr(wf, "compare_coverage_facts", fake_compare_coverage)
    return regression_calls, coverage_calls


def test_build_compare_view_calls_both_engines_once_with_the_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regression_calls, coverage_calls = _patch_engines(
        monkeypatch, _regression_fact_set(), _coverage_delta()
    )
    baseline, target = _baseline_ref(), _target_ref()
    view = build_compare_view(_STORE, baseline, target)  # type: ignore[arg-type]
    assert regression_calls == [(_STORE, baseline, target)]
    assert coverage_calls == [(_STORE, baseline, target)]
    assert isinstance(view, CompareView)


@pytest.mark.parametrize(
    ("regression", "coverage"),
    [
        (_regression_fact_set(), _coverage_delta()),
        (_regression_fact_set(), _coverage_unavailable()),
        (_regression_unavailable(), _coverage_delta()),
        (_regression_unavailable(), _coverage_unavailable()),
    ],
    ids=[
        "both-available",
        "coverage-unavailable",
        "regression-unavailable",
        "both-unavailable",
    ],
)
def test_view_composes_independently_and_matches_premove_payload(
    monkeypatch: pytest.MonkeyPatch,
    regression: RegressionFactSet | RegressionUnavailable,
    coverage: CoverageDelta | CoverageUnavailable,
) -> None:
    """Oracle: ``to_dict()`` equals the verbatim pre-S23 inline assembly.

    Pre-move ``compare_cmd`` built the envelope data as::

        {
            "regression_outcome": _regression_outcome_payload(regression_outcome),
            "coverage_delta": _coverage_delta_payload(coverage_outcome),
        }

    with the two projectors byte-identical to today's shared
    ``orchestration/projection.py`` functions (their own preservation
    oracle lives in ``tests/unit/orchestration/test_projection.py``).
    """
    _patch_engines(monkeypatch, regression, coverage)
    view = build_compare_view(_STORE, _baseline_ref(), _target_ref())  # type: ignore[arg-type]
    payload = view.to_dict()
    replica = {
        "regression_outcome": regression_outcome_payload(regression),
        "coverage_delta": coverage_delta_payload(coverage),
    }
    assert payload == replica
    # Key ORDER is part of the byte-stable wire (json.dumps preserves
    # insertion order) — pin it explicitly.
    assert list(payload.keys()) == ["regression_outcome", "coverage_delta"]


def test_view_never_short_circuits_on_single_engine_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_engines(monkeypatch, _regression_unavailable(), _coverage_unavailable())
    payload = build_compare_view(
        _STORE, _baseline_ref(), _target_ref()  # type: ignore[arg-type]
    ).to_dict()
    assert payload["regression_outcome"]["kind"] == "unavailable"
    assert payload["regression_outcome"]["reason"] == "run-tombstoned"
    assert payload["coverage_delta"]["kind"] == "unavailable"
    assert payload["coverage_delta"]["reason"] == "missing-derived-facts"
