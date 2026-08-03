"""Unit tests for the 7 trigger predicates + compound + mutual exclusion.

Each test constructs a minimal in-memory ``FactBundle`` and asserts the
matcher fires (or refuses to fire) under the brief §1 trigger conditions.
The ``flaky_suspected`` matcher additionally exercises the ``ReplayResult``
placeholder per the brief §7 "Phase 5 dep" note.

Compound resolution + mutual exclusion are pinned in dedicated tests at
the bottom — the brief §1 "Compound rule" / "Mutual exclusion rules"
clauses are the binding contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

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
    synthesize_recommendation,
)
from novetest.orchestration.recommendation.fact_bundle import has_failed_tests
from novetest.orchestration.recommendation.categories import (
    CATEGORIES,
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    MATCHERS_BY_PRIORITY,
    PRIORITIES,
    CategoryHit,
    apply_mutual_exclusion,
    compound_resolution,
    match_all_green,
    match_coverage_gap,
    match_flaky_suspected,
    match_investigate_location,
    match_investigate_regression,
    match_regression_with_localization,
    match_unavailable_analysis,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@dataclass
class _BundleParts:
    run_reference: RunReference
    run_record: RunRecord
    coverage: CoverageFactSet | None = None
    regression: RegressionFactSet | None = None
    localization: LocalizationFinding | None = None
    replay: ReplayResult | None = None
    eligibility: StageEligibility = field(
        default_factory=lambda: _all_available_eligibility()
    )

    def to_bundle(self) -> FactBundle:
        return FactBundle(
            run_reference=self.run_reference,
            run_record=self.run_record,
            stage_eligibility=self.eligibility,
            coverage_facts=self.coverage,
            regression_facts=self.regression,
            localization_findings=self.localization,
            # Harness convenience: the single optional ``replay`` slot maps
            # onto the tuple-shaped ``replay_results`` field (2026-06-25
            # ``--reruns`` rename); multi-result cases live in
            # ``test_match_flaky_suspected_list.py``.
            replay_results=(self.replay,) if self.replay is not None else (),
        )


def _all_available_eligibility() -> StageEligibility:
    """Default — every stage reports ``available`` / matching mode."""

    return StageEligibility(
        coverage="available",
        regression="available",
        localization="sbfl_per_test",
        replay="not_run",
        per_stage_reasons={
            "coverage": None,
            "regression": None,
            "localization": None,
            "replay": "replay_not_run",
        },
    )


def _all_unavailable_eligibility() -> StageEligibility:
    """Every analyzable stage unavailable; replay stays ``not_run``."""

    return StageEligibility(
        coverage="unavailable",
        regression="unavailable",
        localization="unavailable",
        replay="not_run",
        per_stage_reasons={
            "coverage": "missing-derived-facts",
            "regression": "no-comparable-baseline",
            "localization": "no-coverage",
            "replay": "replay_not_run",
        },
    )


def _make_run_reference(run_id: str = "01TESTRUNREF000000000000A", at: int = 1000) -> RunReference:
    return RunReference(run_id=run_id, created_at=at)


def _make_run_record(
    ref: RunReference,
    *,
    target: str = "tests/",
    passed: int = 1,
    failed: int = 0,
    skipped: int = 0,
    test_results: tuple[TestResult, ...] = (),
    status: str | None = None,
) -> RunRecord:
    inferred_status = status or ("failed" if failed > 0 else "passed")
    return RunRecord(
        run_reference=ref,
        target_expression=target,
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status=inferred_status,
        started_at=ref.created_at,
        completed_at=ref.created_at + 1,
        engine_version="8.2.0",
        summary_counts={
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": passed + failed + skipped,
        },
        test_results=test_results,
    )


def _make_localization(
    ref: RunReference,
    *,
    mode: str = "sbfl_per_test",
    confidence: str = "high",
    entries: tuple[LocalizationEntry, ...] | None = None,
) -> LocalizationFinding:
    if entries is None:
        loc = CodeLocation(
            kind="symbol",
            file="src/calc.py",
            symbol="divide",
            line_range=(31, 34),
            primary_line=32,
            evidence_lines=(32,),
        )
        citation = EvidenceCitation(
            kind="test_result",
            run_reference=ref,
            selector={"test_id": "tests/test_calc.py::test_divide", "outcome": "failed"},
        )
        entries = (
            LocalizationEntry(
                rank=1,
                tied_with=(),
                code_location=loc,
                score_raw=1.0,
                score_normalized=1.0,
                formula="ochiai",
                alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
                related_failed_tests=("tests/test_calc.py::test_divide",),
                evidence_citations=(citation,),
            ),
        )
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode=mode,
        confidence=confidence,
        formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10,
        entries=entries,
        derived_at=ref.created_at + 5,
    )


def _make_regression(
    baseline_ref: RunReference,
    target_ref: RunReference,
    *,
    regressed_tests: tuple[str, ...] = ("tests/test_calc.py::test_divide",),
) -> RegressionFactSet:
    transitions = tuple(
        TestTransition(
            node_id=test_id,
            category="regressed",
            baseline_outcome="passed",
            target_outcome="failed",
            baseline_failure_reference=None,
            target_failure_reference=f"native://failure_ref_{i}",
            baseline_duration_ms=10,
            target_duration_ms=12,
        )
        for i, test_id in enumerate(regressed_tests)
    )
    return RegressionFactSet(
        baseline_run_reference=baseline_ref,
        target_run_reference=target_ref,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=target_ref.created_at + 1,
        summary=RegressionSummary(
            regressed=len(regressed_tests),
            fixed=0,
            still_failing=0,
            still_passing=0,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=len(regressed_tests),
            total_target_tests=len(regressed_tests),
        ),
        test_transitions=transitions,
        output_diff=None,
        coverage_change=None,
    )


def _make_coverage(
    ref: RunReference,
    *,
    file_path: str = "src/calc.py",
    missing_lines: tuple[int, ...] = (32, 33),
) -> CoverageFactSet:
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
    file_cov = FileCoverage(
        file_path=file_path,
        executed_lines=(31, 34),
        missing_lines=missing_lines,
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=summary,
    )
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=summary,
        files=(file_cov,),
        derived_at=ref.created_at + 2,
    )


# ---------------------------------------------------------------------------
# match_investigate_location
# ---------------------------------------------------------------------------


class TestInvestigateLocation:
    def test_fires_on_high_confidence_rank_1(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=_make_localization(ref),
        ).to_bundle()

        hits = match_investigate_location(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_INVESTIGATE_LOCATION
        assert h.priority == PRIORITIES[CATEGORY_INVESTIGATE_LOCATION]
        assert h.payload["file"] == "src/calc.py"
        assert h.payload["symbol"] == "divide"
        assert h.payload["rank"] == 1
        assert h.payload["formula"] == "ochiai"
        assert h.payload["mode"] == "sbfl_per_test"

    def test_skips_low_confidence(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=_make_localization(ref, confidence="low", mode="failure_proximity"),
        ).to_bundle()

        assert match_investigate_location(bundle) == []

    def test_skips_rank_above_3(self) -> None:
        ref = _make_run_reference()
        # Build a 5-entry finding; rank 4 + 5 must be dropped.
        loc1 = CodeLocation(
            kind="file", file="src/a.py", symbol=None, line_range=None,
            primary_line=1, evidence_lines=(),
        )
        cit1 = EvidenceCitation(kind="test_result", run_reference=ref, selector={"test_id": "t1", "outcome": "failed"})
        entries = tuple(
            LocalizationEntry(
                rank=i,
                tied_with=(),
                code_location=CodeLocation(
                    kind="file", file=f"src/{chr(ord('a') + i - 1)}.py",
                    symbol=None, line_range=None,
                    primary_line=i, evidence_lines=(),
                ),
                score_raw=1.0 - 0.1 * i,
                score_normalized=1.0 - 0.1 * i,
                formula="ochiai",
                alternate_scores={},
                related_failed_tests=("t1",),
                evidence_citations=(cit1,),
            )
            for i in range(1, 6)
        )
        finding = _make_localization(ref, entries=entries)
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=finding,
        ).to_bundle()
        hits = match_investigate_location(bundle)
        assert [h.payload["rank"] for h in hits] == [1, 2, 3]

    def test_no_localization_no_hits(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=None,
        ).to_bundle()
        assert match_investigate_location(bundle) == []


# ---------------------------------------------------------------------------
# match_investigate_regression
# ---------------------------------------------------------------------------


class TestInvestigateRegression:
    def test_fires_on_each_regressed_test(self) -> None:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        target_ref = _make_run_reference("01TARGETRUNREF0000000000A", at=1100)
        rf = _make_regression(
            baseline_ref, target_ref, regressed_tests=("a::1", "b::2")
        )
        bundle = _BundleParts(
            run_reference=target_ref,
            run_record=_make_run_record(target_ref, failed=2, passed=0),
            regression=rf,
        ).to_bundle()
        hits = match_investigate_regression(bundle)
        # Sorted alphabetically by node_id.
        assert [h.payload["test_id"] for h in hits] == ["a::1", "b::2"]
        for h in hits:
            assert h.payload["regression_kind"] == "newly_failing"
            assert h.payload["run_reference_from"] == baseline_ref.run_id
            assert h.payload["run_reference_to"] == target_ref.run_id

    def test_does_not_fire_for_non_regressed_transitions(self) -> None:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        target_ref = _make_run_reference("01TARGETRUNREF0000000000A", at=1100)
        rf = RegressionFactSet(
            baseline_run_reference=baseline_ref,
            target_run_reference=target_ref,
            baseline_engine_name="pytest",
            target_engine_name="pytest",
            baseline_engine_version="8.2.0",
            target_engine_version="8.2.0",
            derived_at=1101,
            summary=RegressionSummary(
                regressed=0, fixed=1, still_failing=0, still_passing=1,
                still_skipped=0, newly_skipped=0, newly_active=0,
                added=0, removed=0, total_baseline_tests=2, total_target_tests=2,
            ),
            test_transitions=(
                TestTransition(
                    node_id="fixed_test", category="fixed",
                    baseline_outcome="failed", target_outcome="passed",
                    baseline_failure_reference="x", target_failure_reference=None,
                    baseline_duration_ms=10, target_duration_ms=10,
                ),
            ),
            output_diff=None, coverage_change=None,
        )
        bundle = _BundleParts(
            run_reference=target_ref,
            run_record=_make_run_record(target_ref, passed=2),
            regression=rf,
        ).to_bundle()
        assert match_investigate_regression(bundle) == []


# ---------------------------------------------------------------------------
# match_regression_with_localization (compound)
# ---------------------------------------------------------------------------


class TestRegressionWithLocalization:
    def test_fires_when_test_id_in_related_failed_tests(self) -> None:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        target_ref = _make_run_reference("01TARGETRUNREF0000000000A", at=1100)
        rf = _make_regression(
            baseline_ref, target_ref,
            regressed_tests=("tests/test_calc.py::test_divide",),
        )
        finding = _make_localization(target_ref)
        bundle = _BundleParts(
            run_reference=target_ref,
            run_record=_make_run_record(target_ref, failed=1, passed=0),
            regression=rf,
            localization=finding,
        ).to_bundle()
        hits = match_regression_with_localization(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_REGRESSION_WITH_LOCALIZATION
        assert h.priority == PRIORITIES[CATEGORY_REGRESSION_WITH_LOCALIZATION]
        assert h.payload["test_id"] == "tests/test_calc.py::test_divide"
        assert h.payload["file"] == "src/calc.py"
        assert h.payload["symbol"] == "divide"
        assert h.payload["regression_kind"] == "newly_failing"

    def test_no_fire_when_no_overlap(self) -> None:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        target_ref = _make_run_reference("01TARGETRUNREF0000000000A", at=1100)
        # Regression covers t1 but localization's related_failed_tests is t2.
        rf = _make_regression(baseline_ref, target_ref, regressed_tests=("t1",))
        loc = CodeLocation(
            kind="symbol", file="src/x.py", symbol="bug",
            line_range=(1, 2), primary_line=1, evidence_lines=(1,),
        )
        cit = EvidenceCitation(kind="test_result", run_reference=target_ref, selector={"test_id": "t2", "outcome": "failed"})
        entries = (
            LocalizationEntry(
                rank=1, tied_with=(),
                code_location=loc,
                score_raw=1.0, score_normalized=1.0,
                formula="ochiai", alternate_scores={},
                related_failed_tests=("t2",),
                evidence_citations=(cit,),
            ),
        )
        finding = _make_localization(target_ref, entries=entries)
        bundle = _BundleParts(
            run_reference=target_ref,
            run_record=_make_run_record(target_ref, failed=2, passed=0),
            regression=rf,
            localization=finding,
        ).to_bundle()
        assert match_regression_with_localization(bundle) == []

    def test_no_fire_without_regression(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=_make_localization(ref),
        ).to_bundle()
        assert match_regression_with_localization(bundle) == []


# ---------------------------------------------------------------------------
# match_coverage_gap
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_fires_when_uncovered_line_inside_suspect_range(self) -> None:
        ref = _make_run_reference()
        finding = _make_localization(ref)  # divide at lines 31-34
        coverage = _make_coverage(ref, missing_lines=(32, 33))
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            coverage=coverage,
            localization=finding,
        ).to_bundle()
        hits = match_coverage_gap(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.payload["file"] == "src/calc.py"
        assert h.payload["lines"] == [32, 33]
        assert h.payload["related_finding_id"] == "entry_index_0"
        assert h.payload["mode"] == "sbfl_per_test"

    def test_no_fire_when_uncovered_outside_range(self) -> None:
        ref = _make_run_reference()
        finding = _make_localization(ref)
        # uncovered line 50 is outside the divide range (31-34)
        coverage = _make_coverage(ref, missing_lines=(50,))
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            coverage=coverage,
            localization=finding,
        ).to_bundle()
        assert match_coverage_gap(bundle) == []

    def test_no_fire_without_coverage(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            localization=_make_localization(ref),
            coverage=None,
        ).to_bundle()
        assert match_coverage_gap(bundle) == []


# ---------------------------------------------------------------------------
# match_flaky_suspected — mock ReplayResult (Phase 5 dep)
# ---------------------------------------------------------------------------


class TestFlakySuspected:
    def test_fires_on_inconsistent_classification(self) -> None:
        ref = _make_run_reference()
        replay = ReplayResult(
            run_reference=ref,
            classification="inconsistent",
            reruns_total=5,
            reruns_failed=2,
            test_id="tests/test_a.py::test_flaky",
        )
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            replay=replay,
        ).to_bundle()
        hits = match_flaky_suspected(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_FLAKY_SUSPECTED
        assert h.payload["test_id"] == "tests/test_a.py::test_flaky"
        assert h.payload["reruns_total"] == 5
        assert h.payload["reruns_failed"] == 2

    def test_no_fire_when_reproducible(self) -> None:
        ref = _make_run_reference()
        replay = ReplayResult(
            run_reference=ref,
            classification="reproducible",
            reruns_total=3,
            reruns_failed=3,
        )
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            replay=replay,
        ).to_bundle()
        assert match_flaky_suspected(bundle) == []

    def test_no_fire_without_replay(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            replay=None,
        ).to_bundle()
        assert match_flaky_suspected(bundle) == []


# ---------------------------------------------------------------------------
# match_unavailable_analysis
# ---------------------------------------------------------------------------


class TestUnavailableAnalysis:
    def test_fires_when_stage_unavailable_and_tests_failed(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1, passed=0),
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()
        hits = match_unavailable_analysis(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_UNAVAILABLE_ANALYSIS
        assert h.payload["unavailable_stages"] == ["coverage", "regression", "localization"]
        assert "coverage" in h.payload["reason_per_stage"]
        assert h.payload["reason_per_stage"]["coverage"] == "missing-derived-facts"

    def test_no_fire_when_all_available(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
        ).to_bundle()
        assert match_unavailable_analysis(bundle) == []

    def test_no_fire_when_unavailable_but_no_failures(self) -> None:
        """A run that EXECUTED and had no failures owes no explanation.

        Brief §1 trigger row: ``unavailable_analysis`` requires "≥1 test
        failed" — otherwise the run is just incomplete-but-fine. Since row
        45 that is only half the gate: the run must ALSO have executed as
        a suite (see ``TestCollectionFailureRow45``). Both halves are
        exercised here — this record is ``status: "passed"`` with real
        passing tests, so neither disjunct fires.
        """

        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, passed=1, failed=0),
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()
        assert match_unavailable_analysis(bundle) == []


# ---------------------------------------------------------------------------
# match_all_green
# ---------------------------------------------------------------------------


class TestAllGreen:
    def test_fires_on_zero_failures_no_regression(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, passed=3),
        ).to_bundle()
        hits = match_all_green(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_ALL_GREEN
        assert h.payload["total_tests"] == 3
        assert h.payload["passed"] == 3
        assert h.payload["skipped"] == 0

    def test_no_fire_when_test_failed(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
        ).to_bundle()
        assert match_all_green(bundle) == []

    def test_no_fire_when_regression_present(self) -> None:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        target_ref = _make_run_reference("01TARGETRUNREF0000000000A", at=1100)
        rf = _make_regression(baseline_ref, target_ref)
        bundle = _BundleParts(
            run_reference=target_ref,
            run_record=_make_run_record(target_ref, passed=2),
            regression=rf,
        ).to_bundle()
        # rf reports regressed=1 → all_green refuses to fire.
        assert match_all_green(bundle) == []


# ---------------------------------------------------------------------------
# Row 45 — a suite that never executed must not be reported green
# ---------------------------------------------------------------------------


def _errored_zero_result_record(ref: RunReference) -> RunRecord:
    """The exact Run Record a pytest collection failure persists.

    Measured against ``tests/fixtures/projects/pytest-collection-error``:
    ``status: "errored"``, ``summary_counts == {"total": 0, "collected": 0}``
    (note there is no ``"failed"`` key at all, so ``record_has_failed_tests``
    falls through to scanning ``test_results``) and zero ``test_results``.
    """

    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="errored",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1,
        engine_version="8.2.0",
        summary_counts={"total": 0, "collected": 0},
        test_results=(),
    )


class TestCollectionFailureRow45:
    """A zero-collected, ``errored`` run routes to explanation, not to green.

    Delivery-phasing row 45. The counting predicates cannot separate
    "nothing failed because everything passed" from "nothing failed
    because nothing ran" — only ``run_record.status`` can, and before this
    fix no matcher consulted it.
    """

    def _bundle(self) -> FactBundle:
        ref = _make_run_reference()
        return _BundleParts(
            run_reference=ref,
            run_record=_errored_zero_result_record(ref),
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()

    def test_the_vacuous_precondition_still_holds(self) -> None:
        """Pin WHY the defect existed, so a future refactor cannot hide it.

        ``has_failed_tests`` is False on this bundle — correctly, there are
        no failures. Any gate built on that predicate alone is therefore
        vacuously satisfied. This assertion is the premise the two tests
        below defend against; if it ever flips, they stop testing the
        thing they were written for.
        """

        assert has_failed_tests(self._bundle()) is False

    def test_all_green_refuses(self) -> None:
        assert match_all_green(self._bundle()) == []

    def test_unavailable_analysis_fires_instead(self) -> None:
        hits = match_unavailable_analysis(self._bundle())
        assert len(hits) == 1
        assert hits[0].category == CATEGORY_UNAVAILABLE_ANALYSIS
        assert hits[0].payload["unavailable_stages"] == [
            "coverage",
            "regression",
            "localization",
        ]

    def test_synthesis_emits_exactly_one_non_green_recommendation(self) -> None:
        """End of the pipeline, not just the matcher: what the agent reads."""

        recs = synthesize_recommendation(self._bundle())
        assert [r.category for r in recs] == [CATEGORY_UNAVAILABLE_ANALYSIS]
        assert "green" not in recs[0].summary.lower()
        # NFR-ORCH-002 — a recommendation always carries evidence.
        assert recs[0].evidence_citations

    def test_all_green_survives_when_the_suite_actually_ran_empty(self) -> None:
        """The adjacent case is deliberately NOT swept up by this fix.

        An engine that ran to completion and exited clean with zero tests
        (go / junit / xunit — ``status: "passed"``) keeps its existing
        ``all_green`` + ``zero-tests-collected`` treatment. Same zero
        counts, different status, different answer: this is the assertion
        that proves the fix discriminates on status rather than on
        emptiness.
        """

        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, passed=0, failed=0, skipped=0),
        ).to_bundle()
        assert bundle.run_record.status == "passed"
        hits = match_all_green(bundle)
        assert len(hits) == 1
        assert hits[0].payload["total_tests"] == 0

    def test_unknown_future_status_also_refuses_green(self) -> None:
        """The status gate is an ALLOW-list, so it is safe against growth.

        A status this code has never seen must read as "did not execute",
        never as "clean". A deny-list (``status != "errored"``) would pass
        this and silently re-open row 45 for the next status the Run
        engine adds.
        """

        ref = _make_run_reference()
        record = _make_run_record(ref, passed=0, failed=0, status="interrupted")
        bundle = _BundleParts(
            run_reference=ref,
            run_record=record,
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()
        assert match_all_green(bundle) == []
        assert len(match_unavailable_analysis(bundle)) == 1

    @pytest.mark.parametrize(
        ("status", "passed", "failed", "expect_unavailable"),
        [
            ("passed", 3, 0, False),
            ("failed", 2, 1, True),
            ("errored", 2, 1, True),
        ],
    )
    def test_widened_gate_does_not_misfire_on_executed_runs(
        self, status: str, passed: int, failed: int, expect_unavailable: bool
    ) -> None:
        """Regression matrix for the widened ``unavailable_analysis`` gate.

        Every stage is unavailable in all three rows, so only the second
        half of the gate varies. The pre-row-45 answers must be unchanged:
        a green run stays silent, a failing run still explains itself, and
        an ``errored`` run that DID collect tests is handled by the
        original ``has_failed_tests`` disjunct, not by the new one.
        """

        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(
                ref, passed=passed, failed=failed, status=status
            ),
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()
        fired = len(match_unavailable_analysis(bundle)) == 1
        assert fired is expect_unavailable

    def test_mutual_exclusion_is_not_the_thing_holding_the_line(self) -> None:
        """``apply_mutual_exclusion`` swept for the same vacuous shape.

        Its rule-1 drop is keyed on the PRESENCE of another hit, so it is
        not vacuous — but it is also not a second line of defence: fed an
        ``all_green`` hit alone it passes it straight through. That is why
        the fix had to land in ``match_all_green`` itself rather than
        relying on ``unavailable_analysis`` happening to fire alongside.
        """

        lone_green = CategoryHit(
            category=CATEGORY_ALL_GREEN,
            priority=PRIORITIES[CATEGORY_ALL_GREEN],
            primary_slot="",
            payload={},
        )
        assert apply_mutual_exclusion([lone_green]) == [lone_green]


# ---------------------------------------------------------------------------
# Row 46 — which categories carry a ``rank`` slot (the docs route on this)
# ---------------------------------------------------------------------------


class TestRankBearingCategoriesRow46:
    """Pin the premise the documented routing recipes are built on.

    ``docs/agent/quick-start.md`` and ``docs/agent/after-test.md`` both
    branch on ``slots["rank"]``, and ``after-test.md`` used to read it off
    a ``coverage_gap`` recommendation — which raises ``KeyError: 'rank'``,
    unreachable today only because priority 4 always loses to a priority-2
    ``investigate_location`` when both are present. That is an ordering
    accident, not a guarantee, so the doc was corrected to route
    ``coverage_gap`` separately.

    This test guards the OTHER direction of that drift: if a matcher ever
    gains or loses a ``rank`` slot, the docs' branch assignment silently
    becomes wrong again. Failing here means a doc edit is owed.
    """

    RANK_BEARING = {
        CATEGORY_INVESTIGATE_LOCATION,
        CATEGORY_REGRESSION_WITH_LOCALIZATION,
    }

    def _all_hits(self) -> list[CategoryHit]:
        baseline_ref = _make_run_reference("01PRIORRUNREF00000000000A", at=900)
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref,
            run_record=_make_run_record(ref, failed=1),
            coverage=_make_coverage(ref),
            regression=_make_regression(baseline_ref, ref),
            localization=_make_localization(ref),
            replay=ReplayResult(
                run_reference=ref,
                classification="inconsistent",
                reruns_total=5,
                reruns_failed=2,
                test_id="tests/test_calc.py::test_divide",
            ),
            eligibility=_all_unavailable_eligibility(),
        ).to_bundle()
        hits: list[CategoryHit] = []
        for _priority, _name, matcher in MATCHERS_BY_PRIORITY:
            hits.extend(matcher(bundle))
        return hits

    def test_every_category_is_exercised_by_this_bundle(self) -> None:
        """Guard the guard: an unexercised category proves nothing below."""

        fired = {h.category for h in self._all_hits()}
        # ``all_green`` cannot coexist with failures by construction, so it
        # is asserted separately (it has no ``rank`` slot either).
        assert fired == CATEGORIES - {CATEGORY_ALL_GREEN}

    def test_rank_slot_membership_matches_what_the_docs_route_on(self) -> None:
        for hit in self._all_hits():
            has_rank = "rank" in hit.payload
            assert has_rank is (hit.category in self.RANK_BEARING), (
                f"{hit.category} rank-slot membership changed; "
                "docs/agent/{quick-start,after-test}.md route on this"
            )

    def test_coverage_gap_slot_keys_are_exactly_what_the_docs_read(self) -> None:
        """``after-test.md``'s ``coverage_gap`` branch reads file + lines."""

        hits = [
            h for h in self._all_hits() if h.category == CATEGORY_COVERAGE_GAP
        ]
        assert hits
        assert set(hits[0].payload) == {
            "file",
            "lines",
            "mode",
            "related_finding_id",
        }

    def test_all_green_carries_no_rank_either(self) -> None:
        ref = _make_run_reference()
        bundle = _BundleParts(
            run_reference=ref, run_record=_make_run_record(ref, passed=2)
        ).to_bundle()
        hits = match_all_green(bundle)
        assert hits and "rank" not in hits[0].payload


# ---------------------------------------------------------------------------
# compound_resolution
# ---------------------------------------------------------------------------


class TestCompoundResolution:
    def _hit(self, category: str, primary_slot: str, **payload: Any) -> CategoryHit:
        return CategoryHit(
            category=category, priority=PRIORITIES[category],
            primary_slot=primary_slot, payload=payload,
        )

    def test_compound_swallows_matching_constituents(self) -> None:
        hits = [
            self._hit(
                CATEGORY_REGRESSION_WITH_LOCALIZATION, "src/calc.py:32:t1",
                file="src/calc.py", primary_line=32, test_id="t1",
            ),
            self._hit(
                CATEGORY_INVESTIGATE_LOCATION, "src/calc.py:32",
                file="src/calc.py", primary_line=32,
            ),
            self._hit(
                CATEGORY_INVESTIGATE_REGRESSION, "t1",
                test_id="t1",
            ),
        ]
        out = compound_resolution(hits)
        assert [h.category for h in out] == [CATEGORY_REGRESSION_WITH_LOCALIZATION]

    def test_compound_does_not_swallow_unrelated_constituents(self) -> None:
        hits = [
            self._hit(
                CATEGORY_REGRESSION_WITH_LOCALIZATION, "src/calc.py:32:t1",
                file="src/calc.py", primary_line=32, test_id="t1",
            ),
            self._hit(
                CATEGORY_INVESTIGATE_LOCATION, "src/other.py:5",
                file="src/other.py", primary_line=5,
            ),
            self._hit(
                CATEGORY_INVESTIGATE_REGRESSION, "t99",
                test_id="t99",
            ),
        ]
        out = compound_resolution(hits)
        cats = [h.category for h in out]
        assert CATEGORY_REGRESSION_WITH_LOCALIZATION in cats
        assert CATEGORY_INVESTIGATE_LOCATION in cats
        assert CATEGORY_INVESTIGATE_REGRESSION in cats

    def test_compound_does_not_swallow_same_file_different_line(self) -> None:
        """ORC-12: a same-file, different-symbol/line ``investigate_location``
        survives — the swallow key is ``(file, primary_line)``, not bare file.

        Scenario: ``src/calc.py`` hosts two functions. Function A (line 32)
        is caught by a regression+localization compound; function B (line 90)
        has its own independent ``investigate_location`` (a different
        defect). The compound must swallow ONLY its own constituent at
        ``(src/calc.py, 32)`` and leave B's hit at ``(src/calc.py, 90)``
        intact. Before the fix, file-level swallowing deleted B silently.
        """

        hits = [
            self._hit(
                CATEGORY_REGRESSION_WITH_LOCALIZATION, "src/calc.py:32:t1",
                file="src/calc.py", primary_line=32, test_id="t1",
            ),
            # Genuine constituent — same (file, primary_line) as the compound.
            self._hit(
                CATEGORY_INVESTIGATE_LOCATION, "src/calc.py:32",
                file="src/calc.py", primary_line=32,
            ),
            # Unrelated same-file hit at a DIFFERENT line — must survive.
            self._hit(
                CATEGORY_INVESTIGATE_LOCATION, "src/calc.py:90",
                file="src/calc.py", primary_line=90,
            ),
        ]
        out = compound_resolution(hits)
        survivors = [
            (h.category, h.payload.get("primary_line")) for h in out
        ]
        assert (CATEGORY_REGRESSION_WITH_LOCALIZATION, 32) in survivors
        # The unrelated same-file location at line 90 is NOT swallowed.
        assert (CATEGORY_INVESTIGATE_LOCATION, 90) in survivors
        # The genuine constituent at line 32 IS swallowed.
        assert (CATEGORY_INVESTIGATE_LOCATION, 32) not in survivors

    def test_no_compound_no_change(self) -> None:
        hits = [
            self._hit(
                CATEGORY_INVESTIGATE_LOCATION, "src/foo.py:1",
                file="src/foo.py", primary_line=1,
            ),
            self._hit(CATEGORY_INVESTIGATE_REGRESSION, "tX", test_id="tX"),
        ]
        out = compound_resolution(hits)
        assert out == hits


# ---------------------------------------------------------------------------
# apply_mutual_exclusion
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    def _hit(self, category: str) -> CategoryHit:
        return CategoryHit(
            category=category, priority=PRIORITIES[category],
            primary_slot="", payload={},
        )

    def test_all_green_dropped_when_other_category_fires(self) -> None:
        hits = [
            self._hit(CATEGORY_ALL_GREEN),
            self._hit(CATEGORY_INVESTIGATE_LOCATION),
        ]
        out = apply_mutual_exclusion(hits)
        assert [h.category for h in out] == [CATEGORY_INVESTIGATE_LOCATION]

    def test_all_green_alone_survives(self) -> None:
        hits = [self._hit(CATEGORY_ALL_GREEN)]
        out = apply_mutual_exclusion(hits)
        assert [h.category for h in out] == [CATEGORY_ALL_GREEN]
