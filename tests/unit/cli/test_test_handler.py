"""Unit tests for ``cli/handlers/test.py::build_test_envelope``.

Pure-function envelope projection: feed in a synthetic ``TestOutcome``,
verify the brief §5 envelope shape + exit code mapping. No subprocess.
"""

from __future__ import annotations

from pathlib import Path

from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_USER_TESTS_FAILED,
)
from novetest.models import MemoryEntry, RunRecord
from novetest.models.run_reference import RunReference
from novetest.orchestration.recommendation import (
    CATEGORY_ALL_GREEN,
    FactBundle,
    PRIORITIES,
    Recommendation,
    StageEligibility,
)
from novetest.orchestration.workflows.test import TestOutcome


def _make_outcome(*, status: str, recommendations: list[Recommendation] | None = None) -> TestOutcome:
    ref = RunReference(run_id="01TESTRUN0000000000000000A", created_at=1000)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=1000,
        completed_at=1001,
        summary_counts={"passed": 1, "failed": 0, "total": 1},
    )
    entry = MemoryEntry(
        entry_id=ref.run_id,
        run_record=record,
        stored_at=1002,
        has_coverage_facts=False,
    )
    elig = StageEligibility(
        coverage="not_applicable",
        regression="not_applicable",
        localization="unavailable",
        replay="not_run",
        per_stage_reasons={
            "coverage": None,
            "regression": None,
            "localization": "no_failed_tests",
            "replay": "replay_not_run",
        },
    )
    bundle = FactBundle(
        run_reference=ref,
        run_record=record,
        stage_eligibility=elig,
        coverage_facts=None,
        regression_facts=None,
        localization_findings=None,
        replay_results=(),
    )
    return TestOutcome(
        memory_entry=entry,
        artifact_dir=Path("/tmp/x"),
        stage_eligibility=elig,
        fact_bundle=bundle,
        recommendations=recommendations or [],
        run_record_status=status,
    )


class TestBuildTestEnvelope:
    def test_passing_run_returns_exit_ok_and_ok_true(self) -> None:
        rec = Recommendation(
            recommendation_id="rec_X_abc",
            category=CATEGORY_ALL_GREEN,
            priority=PRIORITIES[CATEGORY_ALL_GREEN],
            summary="All tests green.",
            slots={"total_tests": 1, "passed": 1, "skipped": 0},
            evidence_citations=[{"kind": "run_reference", "run_reference": {}, "selector": {}}],
        )
        outcome = _make_outcome(status="passed", recommendations=[rec])
        envelope, exit_code = build_test_envelope(outcome)
        assert exit_code == EXIT_OK
        assert envelope.ok is True
        assert envelope.command == "test"
        body = envelope.to_dict()["data"]
        assert body["recommendation_schema_version"] == 1
        assert body["run_reference"]["run_id"] == "01TESTRUN0000000000000000A"
        assert body["stage_eligibility"] == {
            "coverage": "not_applicable",
            "regression": "not_applicable",
            "localization": "unavailable",
            "replay": "not_run",
        }
        assert body["recommendations"][0]["category"] == CATEGORY_ALL_GREEN

    def test_failing_run_returns_exit_user_tests_failed_but_ok_true(self) -> None:
        outcome = _make_outcome(status="failed")
        envelope, exit_code = build_test_envelope(outcome)
        assert exit_code == EXIT_USER_TESTS_FAILED
        # Transport succeeded; user tests failed is data, not a transport error.
        assert envelope.ok is True

    def test_errored_run_returns_exit_generic_and_ok_false(self) -> None:
        outcome = _make_outcome(status="errored")
        envelope, exit_code = build_test_envelope(outcome)
        assert exit_code == EXIT_GENERIC
        assert envelope.ok is False

    def test_envelope_data_keys_match_brief_v5(self) -> None:
        outcome = _make_outcome(status="passed")
        envelope, _ = build_test_envelope(outcome)
        data = envelope.to_dict()["data"]
        # Brief §5 envelope data keys.
        assert set(data.keys()) == {
            "run_reference",
            "stage_eligibility",
            "recommendation_schema_version",
            "recommendations",
        }
