"""Unit tests for ``citations.py`` — per-kind projections + stable sort.

Each per-category dispatch path is exercised against a minimal bundle and
the produced citation list is asserted for (a) ≥1 citation (REQ-ORCH-005)
and (b) selector content sufficient for the round-trip retrieval interface.

Citation order is pinned: ``(kind index, lex selector)``. The order pin
is load-bearing for the determinism contract (synth design doc §3).
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.models import LocalizationFinding, RunRecord
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
    TestTransition,
)
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.orchestration.recommendation import (
    FactBundle,
    ReplayResult,
    StageEligibility,
    cite_recommendation_evidence,
)
from novetest.orchestration.recommendation.categories import (
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    PRIORITIES,
    CategoryHit,
)
from novetest.orchestration.recommendation.citations import (
    CITATION_KIND_ORDER,
    KIND_COVERAGE_FACT,
    KIND_LOCALIZATION_FINDING,
    KIND_REGRESSION_FACT,
    KIND_REPLAY_RESULT,
    KIND_RUN_REFERENCE,
    KIND_TEST_RESULT,
)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


@dataclass
class _Fixture:
    ref_baseline: RunReference
    ref_target: RunReference
    bundle: FactBundle


def _build_full_fixture(*, with_regression: bool = True, with_localization: bool = True,
                        with_coverage: bool = True, with_replay: bool = False) -> _Fixture:
    baseline = RunReference(run_id="01PRIORRUN000000000000000A", created_at=900)
    target = RunReference(run_id="01TARGETRUN0000000000000A", created_at=1100)
    record = RunRecord(
        run_reference=target,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=1100,
        completed_at=1101,
        summary_counts={"passed": 1, "failed": 1, "total": 2},
        test_results=(
            TestResult(node_id="tests/test_calc.py::test_divide", outcome="failed"),
        ),
    )

    finding = None
    if with_localization:
        loc = CodeLocation(
            kind="symbol", file="src/calc.py", symbol="divide",
            line_range=(31, 34), primary_line=32, evidence_lines=(32,),
        )
        ec = EvidenceCitation(
            kind="test_result", run_reference=target,
            selector={"test_id": "tests/test_calc.py::test_divide", "outcome": "failed"},
        )
        entry = LocalizationEntry(
            rank=1, tied_with=(),
            code_location=loc, score_raw=1.0, score_normalized=1.0,
            formula="ochiai",
            alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
            related_failed_tests=("tests/test_calc.py::test_divide",),
            evidence_citations=(ec,),
        )
        finding = LocalizationFinding(
            run_reference=target,
            engine_name="pytest", ecosystem="python",
            mode="sbfl_per_test", confidence="high", formula="ochiai",
            alternate_scores_available=("op2", "dstar2", "tarantula"),
            top_n=10, entries=(entry,), derived_at=1102,
        )

    regression = None
    if with_regression:
        regression = RegressionFactSet(
            baseline_run_reference=baseline,
            target_run_reference=target,
            baseline_engine_name="pytest", target_engine_name="pytest",
            baseline_engine_version="8.2.0", target_engine_version="8.2.0",
            derived_at=1103,
            summary=RegressionSummary(
                regressed=1, fixed=0, still_failing=0, still_passing=1,
                still_skipped=0, newly_skipped=0, newly_active=0,
                added=0, removed=0, total_baseline_tests=2, total_target_tests=2,
            ),
            test_transitions=(
                TestTransition(
                    node_id="tests/test_calc.py::test_divide",
                    category="regressed",
                    baseline_outcome="passed", target_outcome="failed",
                    baseline_failure_reference=None, target_failure_reference="x",
                    baseline_duration_ms=10, target_duration_ms=11,
                ),
            ),
            output_diff=None, coverage_change=None,
        )

    coverage = None
    if with_coverage:
        summary = CoverageSummary(
            num_statements=10, covered_statements=8, missing_statements=2,
            excluded_statements=0, num_branches=2, covered_branches=1,
            missing_branches=1, percent_covered=80.0,
        )
        coverage = CoverageFactSet(
            run_reference=target,
            engine_name="pytest", ecosystem="python",
            mapping_granularity="per-test",
            summary=summary,
            files=(
                FileCoverage(
                    file_path="src/calc.py",
                    executed_lines=(31, 34), missing_lines=(32, 33),
                    excluded_lines=(), executed_branches=(), missing_branches=(),
                    summary=summary,
                ),
            ),
            derived_at=1104,
        )

    replay = (
        ReplayResult(
            run_reference=target,
            classification="inconsistent",
            reruns_total=5,
            reruns_failed=2,
            test_id="tests/test_calc.py::test_divide",
        )
        if with_replay
        else None
    )

    bundle = FactBundle(
        run_reference=target,
        run_record=record,
        stage_eligibility=StageEligibility(
            coverage="available" if with_coverage else "unavailable",
            regression="available" if with_regression else "unavailable",
            localization="sbfl_per_test" if with_localization else "unavailable",
            replay="not_run",
            per_stage_reasons={
                "coverage": None if with_coverage else "missing-derived-facts",
                "regression": None if with_regression else "no-comparable-baseline",
                "localization": None if with_localization else "no_coverage",
                "replay": "replay_not_run",
            },
        ),
        coverage_facts=coverage,
        regression_facts=regression,
        localization_findings=finding,
        replay_result=replay,
    )
    return _Fixture(ref_baseline=baseline, ref_target=target, bundle=bundle)


# ---------------------------------------------------------------------------
# Per-category citation projections
# ---------------------------------------------------------------------------


class TestCitations:
    def test_investigate_location_has_localization_and_test_result(self) -> None:
        fx = _build_full_fixture(with_regression=False)
        hit = CategoryHit(
            category=CATEGORY_INVESTIGATE_LOCATION,
            priority=PRIORITIES[CATEGORY_INVESTIGATE_LOCATION],
            primary_slot="src/calc.py:31",
            payload={
                "symbol": "divide", "file": "src/calc.py",
                "primary_line": 32, "line_range": [31, 34],
                "rank": 1, "score_normalized": 1.0,
                "formula": "ochiai", "mode": "sbfl_per_test",
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        kinds = [c["kind"] for c in cites]
        assert KIND_LOCALIZATION_FINDING in kinds
        assert KIND_TEST_RESULT in kinds
        # Stable order: coverage_fact, localization_finding, regression_fact, ...
        # (only localization_finding + test_result present here).
        assert kinds == sorted(kinds, key=lambda k: CITATION_KIND_ORDER.index(k))

    def test_investigate_regression_has_regression_and_test_result(self) -> None:
        fx = _build_full_fixture(with_localization=False, with_coverage=False)
        hit = CategoryHit(
            category=CATEGORY_INVESTIGATE_REGRESSION,
            priority=PRIORITIES[CATEGORY_INVESTIGATE_REGRESSION],
            primary_slot="tests/test_calc.py::test_divide",
            payload={
                "test_id": "tests/test_calc.py::test_divide",
                "regression_kind": "newly_failing",
                "run_reference_from": fx.ref_baseline.run_id,
                "run_reference_to": fx.ref_target.run_id,
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        kinds = [c["kind"] for c in cites]
        assert KIND_REGRESSION_FACT in kinds
        assert KIND_TEST_RESULT in kinds
        # Regression citation carries both refs for direct round-trip.
        reg = next(c for c in cites if c["kind"] == KIND_REGRESSION_FACT)
        assert reg["run_reference_from"]["run_id"] == fx.ref_baseline.run_id
        assert reg["run_reference_to"]["run_id"] == fx.ref_target.run_id

    def test_compound_has_all_three(self) -> None:
        fx = _build_full_fixture()
        hit = CategoryHit(
            category=CATEGORY_REGRESSION_WITH_LOCALIZATION,
            priority=PRIORITIES[CATEGORY_REGRESSION_WITH_LOCALIZATION],
            primary_slot="src/calc.py:31:tests/test_calc.py::test_divide",
            payload={
                "test_id": "tests/test_calc.py::test_divide",
                "regression_kind": "newly_failing",
                "symbol": "divide", "file": "src/calc.py",
                "primary_line": 32, "line_range": [31, 34],
                "rank": 1, "score_normalized": 1.0,
                "formula": "ochiai", "mode": "sbfl_per_test",
                "run_reference_from": fx.ref_baseline.run_id,
                "run_reference_to": fx.ref_target.run_id,
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        kinds = {c["kind"] for c in cites}
        assert KIND_LOCALIZATION_FINDING in kinds
        assert KIND_REGRESSION_FACT in kinds
        assert KIND_TEST_RESULT in kinds
        assert len(cites) >= 3

    def test_coverage_gap_has_coverage_and_localization(self) -> None:
        fx = _build_full_fixture()
        hit = CategoryHit(
            category=CATEGORY_COVERAGE_GAP,
            priority=PRIORITIES[CATEGORY_COVERAGE_GAP],
            primary_slot="src/calc.py:32",
            payload={
                "file": "src/calc.py",
                "lines": [32, 33],
                "mode": "sbfl_per_test",
                "related_finding_id": "entry_index_0",
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        kinds = [c["kind"] for c in cites]
        assert KIND_COVERAGE_FACT in kinds
        assert KIND_LOCALIZATION_FINDING in kinds
        cov = next(c for c in cites if c["kind"] == KIND_COVERAGE_FACT)
        assert cov["selector"]["file"] == "src/calc.py"
        assert cov["selector"]["lines"] == [32, 33]

    def test_flaky_suspected_has_replay_and_test_result(self) -> None:
        fx = _build_full_fixture(with_replay=True)
        hit = CategoryHit(
            category=CATEGORY_FLAKY_SUSPECTED,
            priority=PRIORITIES[CATEGORY_FLAKY_SUSPECTED],
            primary_slot="tests/test_calc.py::test_divide",
            payload={
                "test_id": "tests/test_calc.py::test_divide",
                "reruns_total": 5,
                "reruns_failed": 2,
                "run_reference": fx.ref_target.run_id,
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        kinds = [c["kind"] for c in cites]
        assert KIND_REPLAY_RESULT in kinds
        assert KIND_TEST_RESULT in kinds

    def test_unavailable_analysis_emits_bare_run_reference(self) -> None:
        fx = _build_full_fixture(with_regression=False, with_localization=False, with_coverage=False)
        hit = CategoryHit(
            category=CATEGORY_UNAVAILABLE_ANALYSIS,
            priority=PRIORITIES[CATEGORY_UNAVAILABLE_ANALYSIS],
            primary_slot="",
            payload={
                "unavailable_stages": ["coverage", "regression", "localization"],
                "reason_per_stage": {
                    "coverage": "missing-derived-facts",
                    "regression": "no-comparable-baseline",
                    "localization": "no_coverage",
                },
                "run_reference": fx.ref_target.run_id,
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        assert len(cites) == 1
        assert cites[0]["kind"] == KIND_RUN_REFERENCE
        assert cites[0]["run_reference"]["run_id"] == fx.ref_target.run_id

    def test_all_green_emits_bare_run_reference(self) -> None:
        fx = _build_full_fixture(with_regression=False, with_localization=False, with_coverage=False)
        hit = CategoryHit(
            category=CATEGORY_ALL_GREEN,
            priority=PRIORITIES[CATEGORY_ALL_GREEN],
            primary_slot="",
            payload={
                "run_reference": fx.ref_target.run_id,
                "total_tests": 1, "passed": 1, "skipped": 0,
            },
        )
        cites = cite_recommendation_evidence(hit, fx.bundle)
        assert len(cites) == 1
        assert cites[0]["kind"] == KIND_RUN_REFERENCE
