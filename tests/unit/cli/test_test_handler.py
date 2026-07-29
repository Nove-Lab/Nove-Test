"""Unit tests for ``cli/handlers/test.py::build_test_envelope``.

Pure-function envelope projection: feed in a synthetic ``TestOutcome``,
verify the brief §5 envelope shape + exit code mapping. No subprocess.

Also carries the WIRE-level pin for recommendation ordering: the order a
consumer actually sees is ``data.recommendations[]`` in the serialized
envelope, so that array — not only the in-process list — is asserted
here.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_USER_TESTS_FAILED,
)
from novetest.models import LocalizationFinding, MemoryEntry, RunRecord
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.orchestration.recommendation import (
    CATEGORY_ALL_GREEN,
    CATEGORY_INVESTIGATE_LOCATION,
    FactBundle,
    PRIORITIES,
    Recommendation,
    StageEligibility,
    synthesize_recommendation,
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
            "localization": "no-failed-tests",
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

    def test_errored_run_returns_exit_user_tests_failed_and_ok_true(self) -> None:
        """An errored suite is a persisted USER result, not a Nove Test
        failure (W1/S8, ORC-04): exit 3, ok=True — same class as failed."""
        outcome = _make_outcome(status="errored")
        envelope, exit_code = build_test_envelope(outcome)
        assert exit_code == EXIT_USER_TESTS_FAILED
        assert envelope.ok is True

    def test_out_of_vocabulary_status_stays_tool_failure(self) -> None:
        """Defensive else-branch only: the closed status vocabulary is
        passed/failed/errored; anything else means an upstream bug and
        surfaces as (ok=False, exit 1)."""
        outcome = _make_outcome(status="bogus-status")
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


# ---------------------------------------------------------------------------
# Wire-level recommendation ordering (wave-1 persona P1, 2026-07-28)
# ---------------------------------------------------------------------------


def _localization_finding_inverse_lex_order() -> LocalizationFinding:
    """Three suspects whose lex file order is the INVERSE of their rank.

    Explicit fixture data — deliberately NOT whatever the localization
    engine currently emits, so this pin is independent of that engine's
    candidate-set rules.
    """
    ref = RunReference(run_id="01TESTRUN0000000000000000A", created_at=1000)
    entries: list[LocalizationEntry] = []
    for rank, file, symbol, score in (
        (1, "src/zeta.py", "zeta_fn", 1.0),
        (2, "src/mid.py", "invoice_total", 0.894),
        (3, "src/alpha.py", "compute_discount", 0.816),
    ):
        entries.append(
            LocalizationEntry(
                rank=rank,
                tied_with=(),
                code_location=CodeLocation(
                    kind="symbol", file=file, symbol=symbol,
                    line_range=(10, 20), primary_line=12, evidence_lines=(12,),
                ),
                score_raw=score,
                score_normalized=score,
                formula="ochiai",
                alternate_scores={"op2": score},
                related_failed_tests=("tests/test_totals.py::test_invoice",),
                evidence_citations=(
                    EvidenceCitation(
                        kind="test_result", run_reference=ref,
                        selector={"test_id": "tests/test_totals.py::test_invoice"},
                    ),
                ),
            )
        )
    return LocalizationFinding(
        run_reference=ref, engine_name="pytest", ecosystem="python",
        mode="sbfl_per_test", confidence="high", formula="ochiai",
        alternate_scores_available=("op2",),
        top_n=10, entries=tuple(entries), derived_at=1003,
    )


class TestWireRecommendationOrdering:
    """``data.recommendations[]`` — the order the AI consumer actually reads.

    Wave-1 persona P1 followed array position (its PostToolUse hook used
    ``recs[0]``) and was routed to the rank-3 suspect. The pin below is
    on the SERIALIZED envelope, not the in-process list.
    """

    def _serialized_recommendations(self) -> list[dict[str, object]]:
        ref = RunReference(run_id="01TESTRUN0000000000000000A", created_at=1000)
        record = RunRecord(
            run_reference=ref, target_expression="tests/", target_type="dir",
            engine_name="pytest", ecosystem="python", status="failed",
            started_at=1000, completed_at=1001,
            summary_counts={"passed": 0, "failed": 1, "total": 1},
            test_results=(
                TestResult(
                    node_id="tests/test_totals.py::test_invoice", outcome="failed"
                ),
            ),
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
        bundle = FactBundle(
            run_reference=ref, run_record=record, stage_eligibility=elig,
            coverage_facts=None, regression_facts=None,
            localization_findings=_localization_finding_inverse_lex_order(),
            replay_results=(),
        )
        outcome = _make_outcome(
            status="failed", recommendations=synthesize_recommendation(bundle)
        )
        envelope, _ = build_test_envelope(outcome)
        # Round-trip through the actual JSON bytes the CLI writes.
        payload = json.loads(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))
        recommendations: list[dict[str, object]] = payload["data"]["recommendations"]
        return recommendations

    def test_first_wire_recommendation_is_the_rank_one_suspect(self) -> None:
        recommendations = self._serialized_recommendations()
        first = recommendations[0]
        assert first["category"] == CATEGORY_INVESTIGATE_LOCATION
        slots = first["slots"]
        assert isinstance(slots, dict)
        assert slots["rank"] == 1
        assert slots["file"] == "src/zeta.py"
        assert slots["score_normalized"] == 1.0

    def test_wire_array_order_tracks_rank_not_file_path(self) -> None:
        recommendations = self._serialized_recommendations()
        locations = [
            r for r in recommendations
            if r["category"] == CATEGORY_INVESTIGATE_LOCATION
        ]
        ranks = [r["slots"]["rank"] for r in locations]  # type: ignore[index]
        files = [r["slots"]["file"] for r in locations]  # type: ignore[index]
        assert ranks == [1, 2, 3]
        # …and the file column is descending-lexicographic, proving the
        # array is NOT ordered by path.
        assert files == ["src/zeta.py", "src/mid.py", "src/alpha.py"]

    def test_every_wire_recommendation_carries_at_least_one_citation(self) -> None:
        # NFR-ORCH-002 stays true through the reordering.
        for rec in self._serialized_recommendations():
            citations = rec["evidence_citations"]
            assert isinstance(citations, list)
            assert len(citations) >= 1
