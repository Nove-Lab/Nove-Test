"""Unit tests for ``synthesizer.py`` — end-to-end pipeline + determinism.

The synthesizer is a pure function over ``FactBundle``; this file
asserts:

- Each fixture's expected category set (mini smoke per brief §7).
- Compound resolution + mutual exclusion fire correctly at the synth
  pipeline level (not just at the matcher level — that's
  ``test_categories.py``).
- Determinism contract: same bundle in → byte-identical
  ``list[Recommendation]`` across 3 consecutive synth calls. The check
  is byte-exact on the JSON-serialized form (the brief's NFR-ORCH-002
  evidence pin).
"""

from __future__ import annotations

import json

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
    CATEGORY_ALL_GREEN,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    FactBundle,
    StageEligibility,
    synthesize_recommendation,
)


def _bundle(*, with_regression: bool, with_localization: bool, fail: bool,
            target_id: str = "01TARGETRUN0000000000000A",
            target_at: int = 1100,
            baseline_id: str = "01PRIORRUN000000000000000A") -> FactBundle:
    baseline = RunReference(run_id=baseline_id, created_at=900)
    target = RunReference(run_id=target_id, created_at=target_at)
    test_results: tuple[TestResult, ...] = (
        TestResult(node_id="tests/test_calc.py::test_divide",
                   outcome="failed" if fail else "passed"),
    )
    record = RunRecord(
        run_reference=target, target_expression="tests/", target_type="dir",
        engine_name="pytest", ecosystem="python",
        status="failed" if fail else "passed",
        started_at=target_at, completed_at=target_at + 1,
        summary_counts={"passed": 0 if fail else 1, "failed": 1 if fail else 0,
                        "skipped": 0, "total": 1},
        test_results=test_results,
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
            rank=1, tied_with=(), code_location=loc,
            score_raw=1.0, score_normalized=1.0,
            formula="ochiai",
            alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
            related_failed_tests=("tests/test_calc.py::test_divide",),
            evidence_citations=(ec,),
        )
        finding = LocalizationFinding(
            run_reference=target, engine_name="pytest", ecosystem="python",
            mode="sbfl_per_test", confidence="high", formula="ochiai",
            alternate_scores_available=("op2", "dstar2", "tarantula"),
            top_n=10, entries=(entry,), derived_at=target_at + 2,
        )

    regression = None
    if with_regression:
        regression = RegressionFactSet(
            baseline_run_reference=baseline, target_run_reference=target,
            baseline_engine_name="pytest", target_engine_name="pytest",
            baseline_engine_version="8.2.0", target_engine_version="8.2.0",
            derived_at=target_at + 1,
            summary=RegressionSummary(
                regressed=1, fixed=0, still_failing=0, still_passing=0,
                still_skipped=0, newly_skipped=0, newly_active=0,
                added=0, removed=0, total_baseline_tests=1, total_target_tests=1,
            ),
            test_transitions=(
                TestTransition(
                    node_id="tests/test_calc.py::test_divide", category="regressed",
                    baseline_outcome="passed", target_outcome="failed",
                    baseline_failure_reference=None, target_failure_reference="x",
                    baseline_duration_ms=10, target_duration_ms=11,
                ),
            ),
            output_diff=None, coverage_change=None,
        )

    elig = StageEligibility(
        coverage="unavailable",
        regression="available" if with_regression else "unavailable",
        localization="sbfl_per_test" if with_localization else "unavailable",
        replay="not_run",
        per_stage_reasons={
            "coverage": "missing-derived-facts",
            "regression": None if with_regression else "no-comparable-baseline",
            "localization": None if with_localization else "no-coverage",
            "replay": "replay_not_run",
        },
    )
    return FactBundle(
        run_reference=target, run_record=record,
        stage_eligibility=elig,
        coverage_facts=None,  # always unavailable in these unit fixtures
        regression_facts=regression,
        localization_findings=finding,
        replay_results=(),
    )


class TestSynthesizerEndToEnd:
    def test_compound_emitted_alone_when_overlap(self) -> None:
        bundle = _bundle(with_regression=True, with_localization=True, fail=True)
        recs = synthesize_recommendation(bundle)
        cats = [r.category for r in recs]
        # Compound swallows investigate_location + investigate_regression
        # for the same (file, test_id) pair. Coverage is unavailable +
        # tests failed → unavailable_analysis fires alongside the
        # compound (partial-availability path).
        assert CATEGORY_REGRESSION_WITH_LOCALIZATION in cats
        assert CATEGORY_INVESTIGATE_LOCATION not in cats
        assert CATEGORY_INVESTIGATE_REGRESSION not in cats
        assert CATEGORY_UNAVAILABLE_ANALYSIS in cats

    def test_investigate_location_alone_when_no_regression(self) -> None:
        bundle = _bundle(with_regression=False, with_localization=True, fail=True)
        recs = synthesize_recommendation(bundle)
        cats = [r.category for r in recs]
        assert CATEGORY_INVESTIGATE_LOCATION in cats
        assert CATEGORY_REGRESSION_WITH_LOCALIZATION not in cats
        # Tests failed, coverage + regression unavailable → unavailable_analysis fires.
        assert CATEGORY_UNAVAILABLE_ANALYSIS in cats

    def test_all_green_when_passing(self) -> None:
        bundle = _bundle(with_regression=False, with_localization=False, fail=False)
        recs = synthesize_recommendation(bundle)
        cats = [r.category for r in recs]
        # When no fail + no regression + no localization findings,
        # all_green fires and nothing else can.
        assert cats == [CATEGORY_ALL_GREEN]

    def test_unavailable_analysis_alone_when_failing_with_zero_facts(self) -> None:
        bundle = _bundle(with_regression=False, with_localization=False, fail=True)
        recs = synthesize_recommendation(bundle)
        cats = [r.category for r in recs]
        # Tests failed, zero facts → only unavailable_analysis (the
        # investigation-categories all require ≥1 fact-set).
        assert cats == [CATEGORY_UNAVAILABLE_ANALYSIS]

    def test_recommendations_sorted_by_priority(self) -> None:
        bundle = _bundle(with_regression=True, with_localization=True, fail=True)
        recs = synthesize_recommendation(bundle)
        priorities = [r.priority for r in recs]
        assert priorities == sorted(priorities), priorities


def _entry(*, rank: int, file: str, score: float, symbol: str) -> LocalizationEntry:
    """One localization entry at an explicit (rank, file, score)."""
    loc = CodeLocation(
        kind="symbol", file=file, symbol=symbol,
        line_range=(10, 20), primary_line=12, evidence_lines=(12,),
    )
    ec = EvidenceCitation(
        kind="test_result",
        run_reference=RunReference(run_id="01TARGETRUN0000000000000A", created_at=1100),
        selector={"test_id": "tests/test_totals.py::test_invoice", "outcome": "failed"},
    )
    return LocalizationEntry(
        rank=rank, tied_with=(), code_location=loc,
        score_raw=score, score_normalized=score,
        formula="ochiai",
        alternate_scores={"op2": score, "dstar2": score, "tarantula": score},
        related_failed_tests=("tests/test_totals.py::test_invoice",),
        evidence_citations=(ec,),
    )


def _ranked_bundle(entries: tuple[LocalizationEntry, ...]) -> FactBundle:
    """A failing-run bundle whose ONLY facts are the given localization entries.

    Regression + coverage are absent, so ``investigate_location`` is the
    only multi-hit category and the assertions isolate intra-group order.
    """
    target = RunReference(run_id="01TARGETRUN0000000000000A", created_at=1100)
    record = RunRecord(
        run_reference=target, target_expression="tests/", target_type="dir",
        engine_name="pytest", ecosystem="python", status="failed",
        started_at=1100, completed_at=1101,
        summary_counts={"passed": 0, "failed": 1, "skipped": 0, "total": 1},
        test_results=(
            TestResult(node_id="tests/test_totals.py::test_invoice", outcome="failed"),
        ),
    )
    finding = LocalizationFinding(
        run_reference=target, engine_name="pytest", ecosystem="python",
        mode="sbfl_per_test", confidence="high", formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10, entries=entries, derived_at=1102,
    )
    elig = StageEligibility(
        coverage="unavailable", regression="unavailable",
        localization="sbfl_per_test", replay="not_run",
        per_stage_reasons={
            "coverage": "missing-derived-facts",
            "regression": "no-comparable-baseline",
            "localization": None,
            "replay": "replay_not_run",
        },
    )
    return FactBundle(
        run_reference=target, run_record=record, stage_eligibility=elig,
        coverage_facts=None, regression_facts=None,
        localization_findings=finding, replay_results=(),
    )


class TestRankOrdering:
    """The array order must track the analysis's own confidence ordering.

    Reproduces the wave-1 persona P1 shape (2026-07-28): three suspects
    whose LEXICOGRAPHIC file order is the exact INVERSE of their rank
    order. Under the pre-fix key — ``(priority, category, primary_slot)``,
    where ``primary_slot`` starts with the file path — the weakest suspect
    landed at ``recommendations[0]`` and a position-following consumer was
    routed to it.
    """

    # ledgerly-shaped: alphabetical file order is rank 3 → 2 → 1.
    P1_ENTRIES = (
        _entry(rank=1, file="src/zeta.py", score=1.0, symbol="zeta_fn"),
        _entry(rank=2, file="src/mid.py", score=0.894, symbol="invoice_total"),
        _entry(rank=3, file="src/alpha.py", score=0.816, symbol="compute_discount"),
    )

    def test_rank_one_is_first_even_when_its_file_sorts_last(self) -> None:
        recs = synthesize_recommendation(_ranked_bundle(self.P1_ENTRIES))
        locations = [r for r in recs if r.category == CATEGORY_INVESTIGATE_LOCATION]
        assert [r.slots["rank"] for r in locations] == [1, 2, 3]
        assert [r.slots["file"] for r in locations] == [
            "src/zeta.py", "src/mid.py", "src/alpha.py",
        ]
        # The headline invariant: the FIRST recommendation overall is the
        # rank-1 suspect, not the lex-min file.
        assert recs[0].category == CATEGORY_INVESTIGATE_LOCATION
        assert recs[0].slots["rank"] == 1
        assert recs[0].slots["file"] == "src/zeta.py"

    def test_fixture_lex_order_really_is_the_inverse_of_rank_order(self) -> None:
        # Guards the test itself: if a future edit makes the file names
        # sort in rank order, the test above stops proving anything.
        by_rank = sorted(self.P1_ENTRIES, key=lambda e: e.rank)
        files_in_rank_order = [e.code_location.file for e in by_rank]
        assert files_in_rank_order == sorted(files_in_rank_order, reverse=True)

    def test_equal_rank_breaks_on_descending_score(self) -> None:
        entries = (
            _entry(rank=1, file="src/aaa.py", score=0.5, symbol="weak"),
            _entry(rank=1, file="src/zzz.py", score=0.9, symbol="strong"),
        )
        recs = synthesize_recommendation(_ranked_bundle(entries))
        locations = [r for r in recs if r.category == CATEGORY_INVESTIGATE_LOCATION]
        assert [r.slots["score_normalized"] for r in locations] == [0.9, 0.5]

    def test_equal_rank_and_score_keeps_lexicographic_primary_slot(self) -> None:
        entries = (
            _entry(rank=1, file="src/zzz.py", score=0.9, symbol="z"),
            _entry(rank=1, file="src/aaa.py", score=0.9, symbol="a"),
        )
        recs = synthesize_recommendation(_ranked_bundle(entries))
        locations = [r for r in recs if r.category == CATEGORY_INVESTIGATE_LOCATION]
        assert [r.slots["file"] for r in locations] == ["src/aaa.py", "src/zzz.py"]

    def test_cross_category_order_still_follows_priority(self) -> None:
        # unavailable_analysis (priority 6) fires alongside the locations
        # (priority 2); the rank dimension must not reorder across groups.
        recs = synthesize_recommendation(_ranked_bundle(self.P1_ENTRIES))
        priorities = [r.priority for r in recs]
        assert priorities == sorted(priorities), priorities
        assert CATEGORY_UNAVAILABLE_ANALYSIS in [r.category for r in recs]
        # …and the rank-less category still sorts after every ranked one.
        assert recs[-1].category == CATEGORY_UNAVAILABLE_ANALYSIS

    def test_ranked_ordering_is_deterministic_across_calls(self) -> None:
        bundle = _ranked_bundle(self.P1_ENTRIES)
        dumps = [
            json.dumps([r.to_dict() for r in synthesize_recommendation(bundle)],
                       sort_keys=True)
            for _ in range(3)
        ]
        assert dumps[0] == dumps[1] == dumps[2]


class TestDeterminism:
    """Brief §1 — same FactBundle → byte-identical recommendation list."""

    def test_three_consecutive_synth_calls_are_byte_identical(self) -> None:
        bundle = _bundle(with_regression=True, with_localization=True, fail=True)
        first = synthesize_recommendation(bundle)
        second = synthesize_recommendation(bundle)
        third = synthesize_recommendation(bundle)
        # Convert to JSON for byte-exact comparison.
        first_json = json.dumps([r.to_dict() for r in first], sort_keys=True)
        second_json = json.dumps([r.to_dict() for r in second], sort_keys=True)
        third_json = json.dumps([r.to_dict() for r in third], sort_keys=True)
        assert first_json == second_json == third_json

    def test_determinism_across_all_three_categories(self) -> None:
        # All-green smoke.
        b1 = _bundle(with_regression=False, with_localization=False, fail=False)
        r1a = synthesize_recommendation(b1)
        r1b = synthesize_recommendation(b1)
        assert [r.to_dict() for r in r1a] == [r.to_dict() for r in r1b]

        # Investigate_location smoke.
        b2 = _bundle(with_regression=False, with_localization=True, fail=True)
        r2a = synthesize_recommendation(b2)
        r2b = synthesize_recommendation(b2)
        assert [r.to_dict() for r in r2a] == [r.to_dict() for r in r2b]
