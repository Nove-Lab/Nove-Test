"""Unit tests for `novetest.coverage.parser`."""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage.parser import CoverageJsonParseError, parse_coverage_json
from novetest.models.run_reference import RunReference


def _ref() -> RunReference:
    return RunReference(run_id="01PARSE", created_at=1_700_000_000_000)


def test_parses_top_level_summary(sample_coverage_payload: dict[str, Any]) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
        derived_at=1_700_000_001_000,
    )
    assert fact_set.summary.num_statements == 10
    assert fact_set.summary.covered_statements == 8
    assert fact_set.summary.missing_statements == 2
    assert fact_set.summary.num_branches == 3
    assert fact_set.summary.covered_branches == 2
    assert fact_set.summary.missing_branches == 1
    assert fact_set.summary.percent_covered == pytest.approx(80.0)


def test_files_are_sorted_by_path(sample_coverage_payload: dict[str, Any]) -> None:
    """Sorted file order keeps `coverage_facts.json` byte-deterministic."""
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    paths = [f.file_path for f in fact_set.files]
    assert paths == sorted(paths)
    assert paths == ["src/pkg/calc.py", "src/pkg/util.py"]


def test_executed_and_missing_lines_round_trip(
    sample_coverage_payload: dict[str, Any],
) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    calc = next(f for f in fact_set.files if f.file_path == "src/pkg/calc.py")
    assert calc.executed_lines == (1, 2, 3, 5, 6, 8)
    assert calc.missing_lines == (10, 11)


def test_missing_branches_extracted(sample_coverage_payload: dict[str, Any]) -> None:
    """The deliberately-uncovered branch from the sample shows up here."""
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    calc = next(f for f in fact_set.files if f.file_path == "src/pkg/calc.py")
    assert calc.missing_branches == ((3, 10),)
    assert calc.executed_branches == ((3, 5), (5, 6))


def test_show_contexts_yields_per_test_granularity(
    sample_coverage_payload: dict[str, Any],
) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    assert fact_set.mapping_granularity == "per-test"


def test_contexts_strip_phase_suffix_and_drop_empty_attribution(
    sample_coverage_payload: dict[str, Any],
) -> None:
    """Coverage.py contexts come as ``"<nodeid>|<phase>"`` or ``""``.

    Stripping the phase collapses setup/run/teardown into one attribution
    per test; dropping the empty string removes module-import scope that
    cannot be attributed.
    """
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    calc = next(f for f in fact_set.files if f.file_path == "src/pkg/calc.py")
    # Line 1 in the sample has only "" context => no attribution => not in map.
    assert 1 not in calc.line_contexts
    # Line 2 has "" + "...|setup" + "...|run" => collapses to single nodeid.
    assert calc.line_contexts[2] == ("tests/test_calc.py::test_add",)
    # Line 3 has two distinct nodeids hitting the same line.
    assert calc.line_contexts[3] == (
        "tests/test_calc.py::test_add",
        "tests/test_calc.py::test_sub",
    )


def test_contexts_are_sorted_for_determinism(
    sample_coverage_payload: dict[str, Any],
) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    for file_coverage in fact_set.files:
        for nodeids in file_coverage.line_contexts.values():
            assert list(nodeids) == sorted(nodeids)


def test_metadata_includes_coverage_py_version_and_show_contexts(
    sample_coverage_payload: dict[str, Any],
) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    assert fact_set.metadata["coverage_py_version"] == "7.6.0"
    assert fact_set.metadata["show_contexts"] is True
    assert fact_set.metadata["branch_coverage"] is True


def test_show_contexts_false_yields_aggregate_for_pytest() -> None:
    payload: dict[str, Any] = {
        "meta": {"version": "7.6.0", "show_contexts": False},
        "files": {},
        "totals": {
            "covered_lines": 0,
            "num_statements": 0,
            "percent_covered": 0.0,
            "missing_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
            "missing_branches": 0,
        },
    }
    fact_set = parse_coverage_json(
        payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    assert fact_set.mapping_granularity == "aggregate"


def test_other_engine_defaults_to_aggregate(
    sample_coverage_payload: dict[str, Any],
) -> None:
    fact_set = parse_coverage_json(
        sample_coverage_payload,
        run_reference=_ref(),
        engine_name="jest",  # not Phase 2-foundation, but field must populate
        ecosystem="javascript",
    )
    assert fact_set.mapping_granularity == "aggregate"


def test_missing_top_level_files_raises() -> None:
    payload: dict[str, Any] = {"meta": {}, "totals": {}}
    with pytest.raises(CoverageJsonParseError, match="'files'"):
        parse_coverage_json(
            payload,
            run_reference=_ref(),
            engine_name="pytest",
            ecosystem="python",
        )


def test_missing_top_level_totals_raises() -> None:
    payload: dict[str, Any] = {"meta": {}, "files": {}}
    with pytest.raises(CoverageJsonParseError, match="'totals'"):
        parse_coverage_json(
            payload,
            run_reference=_ref(),
            engine_name="pytest",
            ecosystem="python",
        )


def test_summary_missing_required_key_raises() -> None:
    payload: dict[str, Any] = {
        "meta": {},
        "files": {},
        "totals": {"num_statements": 1},  # missing covered_lines, etc.
    }
    with pytest.raises(CoverageJsonParseError, match="summary block missing"):
        parse_coverage_json(
            payload,
            run_reference=_ref(),
            engine_name="pytest",
            ecosystem="python",
        )


def test_file_entry_missing_summary_raises() -> None:
    payload: dict[str, Any] = {
        "meta": {},
        "files": {
            "src/x.py": {
                "executed_lines": [],
                "missing_lines": [],
                "excluded_lines": [],
            }
        },
        "totals": {
            "covered_lines": 0,
            "num_statements": 0,
            "percent_covered": 0.0,
            "missing_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
            "missing_branches": 0,
        },
    }
    with pytest.raises(CoverageJsonParseError, match="missing required 'summary'"):
        parse_coverage_json(
            payload,
            run_reference=_ref(),
            engine_name="pytest",
            ecosystem="python",
        )


def test_branch_arc_shape_validation() -> None:
    payload: dict[str, Any] = {
        "meta": {},
        "files": {
            "src/x.py": {
                "executed_lines": [],
                "missing_lines": [],
                "excluded_lines": [],
                "missing_branches": [[1, 2, 3]],  # wrong shape
                "executed_branches": [],
                "summary": {
                    "covered_lines": 0,
                    "num_statements": 0,
                    "percent_covered": 0.0,
                    "missing_lines": 0,
                    "num_branches": 0,
                    "covered_branches": 0,
                    "missing_branches": 0,
                },
            }
        },
        "totals": {
            "covered_lines": 0,
            "num_statements": 0,
            "percent_covered": 0.0,
            "missing_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
            "missing_branches": 0,
        },
    }
    with pytest.raises(CoverageJsonParseError, match="2-element"):
        parse_coverage_json(
            payload,
            run_reference=_ref(),
            engine_name="pytest",
            ecosystem="python",
        )


def test_no_meta_block_treated_as_aggregate() -> None:
    """coverage.py JSONs without ``meta`` (older versions) should not crash."""
    payload: dict[str, Any] = {
        "files": {},
        "totals": {
            "covered_lines": 0,
            "num_statements": 0,
            "percent_covered": 0.0,
            "missing_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
            "missing_branches": 0,
        },
    }
    fact_set = parse_coverage_json(
        payload,
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
    )
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.metadata["show_contexts"] is False
