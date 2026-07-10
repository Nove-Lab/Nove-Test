"""Unit tests for ``templates.py`` — slot-driven summary rendering.

Phase 6 entry slice; brief at
``agent-comms/tasks/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md``.

One test per category template confirms the rendered string contains the
slot values verbatim. Determinism contract: identical ``(category,
slots)`` input → byte-identical output.
"""

from __future__ import annotations

import pytest

from novetest.orchestration.recommendation import (
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    Recommendation,
    render_summary,
)
from novetest.orchestration.recommendation.templates import (
    SUMMARY_TEMPLATES,
    _recommendation_id,
)


class TestSummaryTemplates:
    def test_every_category_has_template(self) -> None:
        expected = {
            CATEGORY_REGRESSION_WITH_LOCALIZATION,
            CATEGORY_INVESTIGATE_LOCATION,
            CATEGORY_INVESTIGATE_REGRESSION,
            CATEGORY_COVERAGE_GAP,
            CATEGORY_FLAKY_SUSPECTED,
            CATEGORY_UNAVAILABLE_ANALYSIS,
            CATEGORY_ALL_GREEN,
        }
        assert set(SUMMARY_TEMPLATES.keys()) == expected

    def test_investigate_location_renders_symbol_and_anchor(self) -> None:
        slots = {
            "symbol": "divide",
            "file": "src/calc.py",
            "primary_line": 32,
            "line_range": [31, 34],
            "rank": 1,
            "score_normalized": 1.0,
            "formula": "ochiai",
            "mode": "sbfl_per_test",
        }
        out = render_summary(CATEGORY_INVESTIGATE_LOCATION, slots)
        assert "`divide`@32" in out
        assert "`src/calc.py`" in out
        assert "rank 1" in out
        assert "ochiai=1.000" in out
        assert "sbfl_per_test" in out

    def test_investigate_location_file_level_falls_back_to_path_anchor(self) -> None:
        slots = {
            "symbol": None,
            "file": "src/calc.py",
            "primary_line": 32,
            "line_range": None,
            "rank": 2,
            "score_normalized": 0.5,
            "formula": "ochiai",
            "mode": "failure_proximity",
        }
        out = render_summary(CATEGORY_INVESTIGATE_LOCATION, slots)
        assert "`src/calc.py`:32" in out
        assert "failure_proximity" in out

    def test_investigate_regression_renders_test_id_and_refs(self) -> None:
        slots = {
            "test_id": "tests/test_a.py::test_x",
            "regression_kind": "newly_failing",
            "run_reference_from": "01PRIOR000000000000000000A",
            "run_reference_to": "01TARGET00000000000000000A",
        }
        out = render_summary(CATEGORY_INVESTIGATE_REGRESSION, slots)
        assert "tests/test_a.py::test_x" in out
        assert "01PRIOR000000000000000000A" in out
        assert "01TARGET00000000000000000A" in out

    def test_regression_with_localization_renders_compound(self) -> None:
        slots = {
            "test_id": "tests/test_a.py::test_x",
            "regression_kind": "newly_failing",
            "symbol": "buggy_func",
            "file": "src/x.py",
            "primary_line": 10,
            "line_range": [9, 11],
            "rank": 1,
            "score_normalized": 1.0,
            "formula": "ochiai",
            "mode": "sbfl_per_test",
            "run_reference_from": "01PRIOR000000000000000000A",
            "run_reference_to": "01TARGET00000000000000000A",
        }
        out = render_summary(CATEGORY_REGRESSION_WITH_LOCALIZATION, slots)
        assert "tests/test_a.py::test_x" in out
        assert "buggy_func" in out
        assert "src/x.py" in out
        assert "rank 1" in out

    def test_coverage_gap_renders_lines(self) -> None:
        slots = {
            "file": "src/x.py",
            "lines": [10, 11, 12],
            "mode": "sbfl_aggregate",
            "related_finding_id": "entry_index_0",
        }
        out = render_summary(CATEGORY_COVERAGE_GAP, slots)
        assert "10, 11, 12" in out
        assert "src/x.py" in out
        assert "sbfl_aggregate" in out
        assert "entry_index_0" in out

    def test_flaky_suspected_renders_rerun_ratio(self) -> None:
        slots = {
            "test_id": "tests/test_b.py::test_flaky",
            "reruns_total": 5,
            "reruns_failed": 2,
            "run_reference": "01RUN0000000000000000000A",
        }
        out = render_summary(CATEGORY_FLAKY_SUSPECTED, slots)
        assert "tests/test_b.py::test_flaky" in out
        assert "2/5" in out

    def test_unavailable_analysis_renders_stage_reasons(self) -> None:
        slots = {
            "unavailable_stages": ["coverage", "localization"],
            "reason_per_stage": {
                "coverage": "missing-derived-facts",
                "localization": "no-coverage",
            },
            "run_reference": "01RUN0000000000000000000A",
        }
        out = render_summary(CATEGORY_UNAVAILABLE_ANALYSIS, slots)
        assert "coverage (missing-derived-facts)" in out
        assert "localization (no-coverage)" in out

    def test_all_green_renders_counts(self) -> None:
        slots = {
            "run_reference": "01RUN0000000000000000000A",
            "total_tests": 7,
            "passed": 6,
            "skipped": 1,
        }
        out = render_summary(CATEGORY_ALL_GREEN, slots)
        assert "passed 6" in out
        assert "skipped 1" in out
        assert "total 7" in out


class TestRenderSummaryRejectsUnknownCategory:
    def test_raises_on_unknown(self) -> None:
        with pytest.raises(ValueError):
            render_summary("not_a_category", {})


class TestRecommendationDataclass:
    def test_to_dict_round_trip_preserves_slots_and_citations(self) -> None:
        rec = Recommendation(
            recommendation_id="rec_X_abc",
            category=CATEGORY_ALL_GREEN,
            priority=7,
            summary="All tests green.",
            slots={"total_tests": 1, "passed": 1, "skipped": 0},
            evidence_citations=[{"kind": "run_reference"}],
        )
        body = rec.to_dict()
        assert body["recommendation_id"] == "rec_X_abc"
        assert body["category"] == CATEGORY_ALL_GREEN
        assert body["slots"]["total_tests"] == 1
        assert body["evidence_citations"][0]["kind"] == "run_reference"

    def test_rejects_unknown_category(self) -> None:
        with pytest.raises(ValueError):
            Recommendation(
                recommendation_id="rec_X_abc",
                category="not_a_category",
                priority=0,
                summary="x",
            )


class TestDeterministicId:
    def test_same_input_yields_same_id(self) -> None:
        a = _recommendation_id(run_id="r1", category="c", primary_slot="s")
        b = _recommendation_id(run_id="r1", category="c", primary_slot="s")
        assert a == b

    def test_id_includes_run_id_and_short_hash(self) -> None:
        rid = _recommendation_id(run_id="rrr", category="c", primary_slot="s")
        assert rid.startswith("rec_rrr_")
        suffix = rid.split("_")[-1]
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)
