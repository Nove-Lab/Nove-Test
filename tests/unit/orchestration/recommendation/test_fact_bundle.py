"""Unit tests for ``fact_bundle.py``.

Phase 6 entry slice. Pins the StageEligibility validation surface, the
ReplayResult placeholder, and the ``build_fact_bundle`` aggregation
builder.
"""

from __future__ import annotations

import pytest

from novetest.models import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.orchestration.recommendation import (
    FactBundle,
    ReplayResult,
    StageEligibility,
    build_fact_bundle,
)
from novetest.orchestration.recommendation.fact_bundle import (
    has_failed_tests,
    passed_count,
    skipped_count,
    total_count,
)


def _make_run_record(
    *,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    test_results: tuple[TestResult, ...] = (),
) -> RunRecord:
    ref = RunReference(run_id="01RUN00000000000000000000A", created_at=100)
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed" if failed > 0 else "passed",
        started_at=100,
        completed_at=101,
        summary_counts={"passed": passed, "failed": failed, "skipped": skipped, "total": passed + failed + skipped},
        test_results=test_results,
    )


class TestStageEligibility:
    def test_valid_slots_pass(self) -> None:
        elig = StageEligibility(
            coverage="available",
            regression="available",
            localization="sbfl_per_test",
            replay="not_run",
            per_stage_reasons={},
        )
        body = elig.to_dict()
        assert body == {
            "coverage": "available",
            "regression": "available",
            "localization": "sbfl_per_test",
            "replay": "not_run",
        }

    def test_localization_accepts_three_modes(self) -> None:
        for mode in ("sbfl_per_test", "sbfl_aggregate", "failure_proximity"):
            StageEligibility(
                coverage="not_applicable",
                regression="not_applicable",
                localization=mode,
                replay="not_applicable",
                per_stage_reasons={},
            )

    def test_invalid_coverage_value_raises(self) -> None:
        with pytest.raises(ValueError):
            StageEligibility(
                coverage="???",
                regression="available",
                localization="unavailable",
                replay="not_run",
                per_stage_reasons={},
            )

    def test_unavailable_stages_returns_stable_order(self) -> None:
        elig = StageEligibility(
            coverage="unavailable",
            regression="available",
            localization="unavailable",
            replay="not_run",
            per_stage_reasons={
                "coverage": "missing-derived-facts",
                "regression": None,
                "localization": "no_coverage",
                "replay": "replay_not_run",
            },
        )
        # Brief §1 — stable order: coverage, regression, localization, replay.
        assert elig.unavailable_stages() == ["coverage", "localization"]

    def test_unavailable_stages_includes_replay_when_explicitly_unavailable(self) -> None:
        elig = StageEligibility(
            coverage="available",
            regression="available",
            localization="sbfl_per_test",
            replay="unavailable",
            per_stage_reasons={"replay": "could-not-replay"},
        )
        assert elig.unavailable_stages() == ["replay"]


class TestReplayResult:
    def test_valid_classifications(self) -> None:
        ref = RunReference(run_id="01R000000000000000000000A", created_at=1)
        for c in ("reproducible", "inconsistent", "unable_to_replay"):
            ReplayResult(
                run_reference=ref,
                classification=c,
                reruns_total=1,
                reruns_failed=0,
            )

    def test_invalid_classification_raises(self) -> None:
        ref = RunReference(run_id="01R000000000000000000000A", created_at=1)
        with pytest.raises(ValueError):
            ReplayResult(
                run_reference=ref,
                classification="not-a-classification",
                reruns_total=1,
                reruns_failed=0,
            )


class TestBuildFactBundle:
    def test_all_fields_propagate(self) -> None:
        record = _make_run_record(passed=1)
        elig = StageEligibility(
            coverage="available",
            regression="not_applicable",
            localization="unavailable",
            replay="not_run",
            per_stage_reasons={},
        )
        bundle = build_fact_bundle(
            run_record=record,
            stage_eligibility=elig,
            coverage_facts=None,
            regression_facts=None,
            localization_findings=None,
        )
        assert isinstance(bundle, FactBundle)
        assert bundle.run_record is record
        assert bundle.run_reference == record.run_reference
        assert bundle.stage_eligibility is elig
        assert bundle.coverage_facts is None
        assert bundle.regression_facts is None
        assert bundle.localization_findings is None
        assert bundle.replay_result is None


class TestSummaryHelpers:
    def test_has_failed_tests_uses_summary_counts(self) -> None:
        record = _make_run_record(failed=2, passed=3)
        bundle = build_fact_bundle(
            run_record=record,
            stage_eligibility=StageEligibility(
                coverage="not_applicable", regression="not_applicable",
                localization="unavailable", replay="not_run",
                per_stage_reasons={},
            ),
            coverage_facts=None, regression_facts=None, localization_findings=None,
        )
        assert has_failed_tests(bundle) is True
        assert passed_count(bundle) == 3
        assert skipped_count(bundle) == 0
        assert total_count(bundle) == 5

    def test_has_failed_tests_falls_back_to_test_results_when_summary_absent(self) -> None:
        ref = RunReference(run_id="01R000000000000000000000A", created_at=1)
        record = RunRecord(
            run_reference=ref,
            target_expression="tests/",
            target_type="dir",
            engine_name="pytest",
            ecosystem="python",
            status="failed",
            started_at=1,
            test_results=(
                TestResult(node_id="t1", outcome="failed"),
                TestResult(node_id="t2", outcome="passed"),
            ),
            summary_counts={},
        )
        bundle = build_fact_bundle(
            run_record=record,
            stage_eligibility=StageEligibility(
                coverage="not_applicable", regression="not_applicable",
                localization="unavailable", replay="not_run",
                per_stage_reasons={},
            ),
            coverage_facts=None, regression_facts=None, localization_findings=None,
        )
        assert has_failed_tests(bundle) is True
        assert passed_count(bundle) == 1
        assert total_count(bundle) == 2
