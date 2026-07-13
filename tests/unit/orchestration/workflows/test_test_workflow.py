"""Unit tests for ``orchestration/workflows/test.py``.

The integrated workflow chains many engines together, so the full
``test_target_in_store`` end-to-end behavior lives in the integration
suite (``tests/integration/orchestration/test_test_workflow.py``).
This file covers two unit-scope concerns:

- ``_build_stage_eligibility`` — pure projection from per-engine outcomes
  onto a ``StageEligibility`` value (every branch).
- ``build_test_outcome_from_run_id`` — cache-only re-derivation against
  a synthetic store; pins the determinism that Phase-6 inspect needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS as COV_REASON_MISSING
from novetest.localization import LocalizationFinding, LocalizationUnavailable
from novetest.localization.results import (
    REASON_NO_COVERAGE as LOC_REASON_NO_COVERAGE,
)
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_reference import RunReference
from novetest.orchestration.recommendation import StageEligibility
from novetest.orchestration.workflows import test as test_module
from novetest.orchestration.workflows.test import _build_stage_eligibility
from novetest.regression import RegressionUnavailable
from novetest.regression.results import (
    REASON_NO_COMPARABLE_BASELINE as REG_REASON_NO_COMPARABLE_BASELINE,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_ref() -> RunReference:
    return RunReference(run_id="01TARGETRUN0000000000000A", created_at=1100)


def _coverage_facts() -> CoverageFactSet:
    ref = _make_ref()
    summary = CoverageSummary(
        num_statements=10, covered_statements=8, missing_statements=2,
        excluded_statements=0, num_branches=2, covered_branches=1,
        missing_branches=1, percent_covered=80.0,
    )
    return CoverageFactSet(
        run_reference=ref, engine_name="pytest", ecosystem="python",
        mapping_granularity="per-test",
        summary=summary, files=(), derived_at=1101,
    )


def _regression_facts() -> RegressionFactSet:
    baseline = RunReference(run_id="01PRIORRUN000000000000000A", created_at=900)
    ref = _make_ref()
    return RegressionFactSet(
        baseline_run_reference=baseline, target_run_reference=ref,
        baseline_engine_name="pytest", target_engine_name="pytest",
        baseline_engine_version="8.2.0", target_engine_version="8.2.0",
        derived_at=1102,
        summary=RegressionSummary(
            regressed=0, fixed=0, still_failing=0, still_passing=1,
            still_skipped=0, newly_skipped=0, newly_active=0,
            added=0, removed=0, total_baseline_tests=1, total_target_tests=1,
        ),
        test_transitions=(), output_diff=None, coverage_change=None,
    )


def _localization_finding() -> LocalizationFinding:
    ref = _make_ref()
    loc = CodeLocation(
        kind="symbol", file="src/calc.py", symbol="divide",
        line_range=(31, 34), primary_line=32, evidence_lines=(32,),
    )
    ec = EvidenceCitation(
        kind="test_result", run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_divide", "outcome": "failed"},
    )
    entry = LocalizationEntry(
        rank=1, tied_with=(), code_location=loc,
        score_raw=1.0, score_normalized=1.0,
        formula="ochiai", alternate_scores={},
        related_failed_tests=("tests/test_calc.py::test_divide",),
        evidence_citations=(ec,),
    )
    return LocalizationFinding(
        run_reference=ref, engine_name="pytest", ecosystem="python",
        mode="sbfl_aggregate", confidence="medium", formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10, entries=(entry,), derived_at=1103,
    )


# ---------------------------------------------------------------------------
# _build_stage_eligibility
# ---------------------------------------------------------------------------


class TestBuildStageEligibility:
    def test_all_available(self) -> None:
        elig = _build_stage_eligibility(
            coverage_outcome=_coverage_facts(),
            regression_outcome=_regression_facts(),
            localization_outcome=_localization_finding(),
        )
        assert isinstance(elig, StageEligibility)
        assert elig.coverage == "available"
        assert elig.regression == "available"
        # Localization slot takes the engine's mode.
        assert elig.localization == "sbfl_aggregate"
        assert elig.replay == "not_run"

    def test_all_unavailable(self) -> None:
        ref = _make_ref()
        elig = _build_stage_eligibility(
            coverage_outcome=CoverageUnavailable(
                reason=COV_REASON_MISSING,
                detail="x",
                run_reference=ref,
            ),
            regression_outcome=RegressionUnavailable(
                reason=REG_REASON_NO_COMPARABLE_BASELINE,
                detail="tests/",
                baseline_run_reference=None,
                target_run_reference=ref,
            ),
            localization_outcome=LocalizationUnavailable(
                run_reference=ref,
                reason=LOC_REASON_NO_COVERAGE,
                detail="No coverage data",
            ),
        )
        assert elig.coverage == "unavailable"
        assert elig.regression == "unavailable"
        assert elig.localization == "unavailable"
        # Reason preservation.
        assert elig.per_stage_reasons["coverage"] == COV_REASON_MISSING
        assert elig.per_stage_reasons["regression"] == REG_REASON_NO_COMPARABLE_BASELINE
        assert elig.per_stage_reasons["localization"] == LOC_REASON_NO_COVERAGE
        # Replay always "not_run" in Phase 6 entry.
        assert elig.replay == "not_run"

    def test_mixed_states(self) -> None:
        ref = _make_ref()
        elig = _build_stage_eligibility(
            coverage_outcome=_coverage_facts(),
            regression_outcome=RegressionUnavailable(
                reason=REG_REASON_NO_COMPARABLE_BASELINE,
                detail="tests/",
                baseline_run_reference=None,
                target_run_reference=ref,
            ),
            localization_outcome=_localization_finding(),
        )
        assert elig.coverage == "available"
        assert elig.regression == "unavailable"
        assert elig.localization == "sbfl_aggregate"
        assert elig.unavailable_stages() == ["regression"]

    def test_localization_modes_match_engine(self) -> None:
        for mode in ("sbfl_per_test", "sbfl_aggregate", "failure_proximity"):
            finding = _localization_finding()
            # Re-fab with the right mode (dataclasses are frozen, so use replace).
            from dataclasses import replace as _replace
            confidence = "high" if mode == "sbfl_per_test" else ("medium" if mode == "sbfl_aggregate" else "low")
            mode_finding = _replace(finding, mode=mode, confidence=confidence)
            elig = _build_stage_eligibility(
                coverage_outcome=_coverage_facts(),
                regression_outcome=_regression_facts(),
                localization_outcome=mode_finding,
            )
            assert elig.localization == mode, mode


# ---------------------------------------------------------------------------
# build_test_outcome_from_run_id — no-comparable-baseline refusal detail
# ---------------------------------------------------------------------------


def _seed_single_run(workspace: Path, target_expression: str) -> str:
    """Materialize a real Project Store with ONE run; return its run_id.

    A single run on a target means the real ``resolve_baseline_for_run``
    selector answers ``None`` — the re-derive path's own
    no-comparable-baseline refusal site fires (the object under test)."""
    from novetest.memory import create_project_store, store_run_evidence
    from novetest.models.run_record import RunRecord
    from novetest.models.test_result import TestResult

    store = create_project_store(workspace)
    ref = RunReference(run_id="01W2S27DETA0000000000000AA", created_at=1_700_000_000_000)
    record = RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="passed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_ok", outcome="passed", duration_ms=5),
        ),
    )
    store_run_evidence(store, record)
    return ref.run_id


@pytest.mark.parametrize(
    ("target_expression", "expected_detail"),
    [
        pytest.param("", "(entire workspace)", id="bare-invocation-placeholder"),
        pytest.param("tests/", "tests/", id="non-empty-expression-unchanged"),
    ],
)
def test_rederive_no_baseline_refusal_detail_renders_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_expression: str,
    expected_detail: str,
) -> None:
    """W2/S27 (Gate-1 Q5b): a bare ``novetest test`` records an EMPTY
    ``target_expression``; the re-derive path's no-comparable-baseline
    refusal must render the pinned ``(entire workspace)`` placeholder
    instead of ``detail: ""`` (mirrors regression's S36-close pin).
    Non-empty expressions pass through verbatim.

    The refusal object never surfaces its ``detail`` past
    ``_build_stage_eligibility`` (which keeps only ``reason``), so the pin
    captures it there via a recording pass-through — everything else runs
    against a real single-run Project Store (real selector → ``None``)."""

    from novetest.memory import locate_project_store

    run_id = _seed_single_run(tmp_path, target_expression)
    store = locate_project_store(tmp_path)
    assert store is not None

    captured: dict[str, Any] = {}
    real_builder = test_module._build_stage_eligibility

    def recording_builder(**kwargs: Any) -> StageEligibility:
        captured.update(kwargs)
        return real_builder(**kwargs)

    monkeypatch.setattr(test_module, "_build_stage_eligibility", recording_builder)

    outcome = test_module.build_test_outcome_from_run_id(store, run_id)

    assert outcome is not None
    refusal = captured["regression_outcome"]
    assert isinstance(refusal, RegressionUnavailable)
    assert refusal.reason == REG_REASON_NO_COMPARABLE_BASELINE
    assert refusal.detail == expected_detail
