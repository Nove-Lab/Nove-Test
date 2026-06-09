"""Unit tests for `novetest.coverage.istanbul_parser`.

Exercises the Istanbul `coverage-final.json` -> `CoverageFactSet` parser
against a pinned inline sample (no Node needed). The sample mirrors jest's
`json` coverage reporter output: a map keyed by absolute file path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.coverage.istanbul_parser import parse_istanbul_json
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.run_reference import RunReference


_WORKSPACE = Path("/ws/project")


def _ref() -> RunReference:
    return RunReference(run_id="01ISTANBUL", created_at=1_700_000_000_000)


def _sample_istanbul() -> dict[str, Any]:
    """Two-file Istanbul payload.

    ``src/calc.js``  — 3 statements, statement 2 (line 5) uncovered.
    ``src/util.js``  — 1 statement, fully covered.
    """
    return {
        "/ws/project/src/calc.js": {
            "path": "/ws/project/src/calc.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 24},
                },
                "1": {
                    "start": {"line": 2, "column": 2},
                    "end": {"line": 2, "column": 15},
                },
                "2": {
                    "start": {"line": 5, "column": 2},
                    "end": {"line": 5, "column": 18},
                },
            },
            "fnMap": {},
            "branchMap": {
                "0": {
                    "type": "if",
                    "locations": [
                        {
                            "start": {"line": 4, "column": 2},
                            "end": {"line": 6, "column": 3},
                        },
                        {
                            "start": {"line": 7, "column": 9},
                            "end": {"line": 9, "column": 3},
                        },
                    ],
                }
            },
            "s": {"0": 3, "1": 3, "2": 0},
            "f": {},
            "b": {"0": [3, 0]},
        },
        "/ws/project/src/util.js": {
            "path": "/ws/project/src/util.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 12},
                },
            },
            "fnMap": {},
            "branchMap": {},
            "s": {"0": 1},
            "f": {},
            "b": {},
        },
    }


def _parse(payload: dict[str, Any]):
    return parse_istanbul_json(
        payload,
        run_reference=_ref(),
        engine_name="jest",
        ecosystem="javascript-typescript",
        workspace_root=_WORKSPACE,
        derived_at=1_700_000_001_000,
    )


def test_parses_two_files_with_workspace_relative_paths() -> None:
    fact_set = _parse(_sample_istanbul())
    paths = [f.file_path for f in fact_set.files]
    # Absolute Istanbul paths are relativized against the workspace root.
    assert paths == ["src/calc.js", "src/util.js"]


def test_files_are_sorted_by_path() -> None:
    """Sorted file order keeps `coverage_facts.json` byte-deterministic."""
    fact_set = _parse(_sample_istanbul())
    paths = [f.file_path for f in fact_set.files]
    assert paths == sorted(paths)


def test_executed_and_missing_lines_from_statement_hits() -> None:
    fact_set = _parse(_sample_istanbul())
    calc = next(f for f in fact_set.files if f.file_path == "src/calc.js")
    # Statements 0/1 hit (lines 1, 2); statement 2 (line 5) uncovered.
    assert calc.executed_lines == (1, 2)
    assert calc.missing_lines == (5,)


def test_per_file_statement_summary() -> None:
    fact_set = _parse(_sample_istanbul())
    calc = next(f for f in fact_set.files if f.file_path == "src/calc.js")
    assert calc.summary.num_statements == 3
    assert calc.summary.covered_statements == 2
    assert calc.summary.missing_statements == 1
    assert calc.summary.percent_covered == pytest.approx(66.67)

    util = next(f for f in fact_set.files if f.file_path == "src/util.js")
    assert util.summary.num_statements == 1
    assert util.summary.covered_statements == 1
    assert util.summary.missing_statements == 0
    assert util.summary.percent_covered == pytest.approx(100.0)


def test_aggregate_summary_sums_statement_counters() -> None:
    fact_set = _parse(_sample_istanbul())
    summary = fact_set.summary
    assert summary.num_statements == 4
    assert summary.covered_statements == 3
    assert summary.missing_statements == 1
    # 3 / 4 -> 75.0
    assert summary.percent_covered == pytest.approx(75.0)


def test_mapping_granularity_is_aggregate_with_empty_line_contexts() -> None:
    """jest's default --coverage merges per-run; no per-test attribution."""
    fact_set = _parse(_sample_istanbul())
    assert fact_set.mapping_granularity == "aggregate"
    for file_coverage in fact_set.files:
        assert file_coverage.line_contexts == {}


def test_branches_are_reported_as_zero() -> None:
    """Istanbul branches do not map to coverage.py arcs — documented as zero.

    See `istanbul_parser` module docstring: emitting fabricated arcs would
    feed misleading Code Locations to Localization (Phase 4).
    """
    fact_set = _parse(_sample_istanbul())
    assert fact_set.summary.num_branches == 0
    assert fact_set.summary.covered_branches == 0
    assert fact_set.summary.missing_branches == 0
    for file_coverage in fact_set.files:
        assert file_coverage.executed_branches == ()
        assert file_coverage.missing_branches == ()


def test_excluded_lines_are_empty() -> None:
    """Istanbul `coverage-final.json` carries no exclusion data."""
    fact_set = _parse(_sample_istanbul())
    for file_coverage in fact_set.files:
        assert file_coverage.excluded_lines == ()


def test_engine_and_ecosystem_are_preserved() -> None:
    fact_set = _parse(_sample_istanbul())
    assert fact_set.engine_name == "jest"
    assert fact_set.ecosystem == "javascript-typescript"
    assert fact_set.derived_at == 1_700_000_001_000


def test_multiple_statements_on_one_line_collapse_to_executed() -> None:
    """A line counts as executed when ANY statement on it was hit."""
    payload = {
        "/ws/project/src/a.js": {
            "path": "/ws/project/src/a.js",
            "statementMap": {
                "0": {
                    "start": {"line": 3, "column": 0},
                    "end": {"line": 3, "column": 10},
                },
                "1": {
                    "start": {"line": 3, "column": 12},
                    "end": {"line": 3, "column": 20},
                },
            },
            "s": {"0": 1, "1": 0},
        }
    }
    fact_set = _parse(payload)
    file_coverage = fact_set.files[0]
    # Line 3 has one hit and one miss statement -> line is executed.
    assert file_coverage.executed_lines == (3,)
    assert file_coverage.missing_lines == ()
    # ...but statement counters still see one covered, one missing.
    assert file_coverage.summary.num_statements == 2
    assert file_coverage.summary.covered_statements == 1


def test_empty_payload_yields_empty_fact_set() -> None:
    """A zero-file Istanbul report is valid, not corrupt."""
    fact_set = _parse({})
    assert fact_set.files == ()
    assert fact_set.summary.num_statements == 0
    assert fact_set.summary.percent_covered == pytest.approx(100.0)


def test_path_outside_workspace_falls_back_to_relative_path() -> None:
    """Absolute paths must never be persisted (decision 2026-05-15 #6)."""
    payload = {
        "/elsewhere/vendor/lib.js": {
            "path": "/elsewhere/vendor/lib.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 5},
                },
            },
            "s": {"0": 1},
        }
    }
    fact_set = _parse(payload)
    file_path = fact_set.files[0].file_path
    assert not Path(file_path).is_absolute()
    assert file_path.startswith("../")


def test_cross_drive_value_error_falls_back_to_drive_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows cross-drive simulation: when ``os.path.relpath`` itself
    raises ``ValueError`` (``GITHUB_WORKSPACE`` on D: vs path on C:),
    the parser falls through to the shared helper's drive-stripped
    POSIX form. Reproduces the 2026-06-09 Windows CI fault class on a
    Linux host so future regressions are caught BEFORE escaping to
    Windows-only CI."""
    import os as _os

    def _raising_relpath(path: object, start: object = _os.curdir) -> str:  # noqa: ARG001
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(_os.path, "relpath", _raising_relpath)

    payload = {
        "/elsewhere/vendor/lib.js": {
            "path": "/elsewhere/vendor/lib.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 5},
                },
            },
            "s": {"0": 1},
        }
    }
    fact_set = _parse(payload)
    file_path = fact_set.files[0].file_path
    # Universal contract: never absolute even in the simulated
    # cross-drive ValueError branch.
    assert not Path(file_path).is_absolute()
    # POSIX-flavored (no backslashes).
    assert "\\" not in file_path
    # Drive-stripped: leading "/" gone, structure preserved.
    assert file_path == "elsewhere/vendor/lib.js"


def test_non_object_file_entry_raises() -> None:
    with pytest.raises(CoverageJsonParseError, match="not an object"):
        _parse({"/ws/project/src/a.js": [1, 2, 3]})


def test_entry_missing_statement_map_raises() -> None:
    payload = {"/ws/project/src/a.js": {"s": {}, "fnMap": {}}}
    with pytest.raises(CoverageJsonParseError, match="statementMap"):
        _parse(payload)


def test_entry_missing_statement_hits_raises() -> None:
    payload = {"/ws/project/src/a.js": {"statementMap": {}, "fnMap": {}}}
    with pytest.raises(CoverageJsonParseError, match="statement hits"):
        _parse(payload)


def test_statement_map_entry_missing_start_line_raises() -> None:
    payload = {
        "/ws/project/src/a.js": {
            "statementMap": {"0": {"end": {"line": 1, "column": 5}}},
            "s": {"0": 1},
        }
    }
    with pytest.raises(CoverageJsonParseError, match="start.line"):
        _parse(payload)


def test_non_integer_hit_count_raises() -> None:
    payload = {
        "/ws/project/src/a.js": {
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 5},
                },
            },
            "s": {"0": "lots"},
        }
    }
    with pytest.raises(CoverageJsonParseError, match="not an .*integer"):
        _parse(payload)


def test_round_trips_through_frozen_on_disk_schema() -> None:
    """The fact set must survive `to_dict` -> `from_dict` (frozen schema)."""
    from novetest.models.coverage_fact_set import CoverageFactSet

    fact_set = _parse(_sample_istanbul())
    restored = CoverageFactSet.from_dict(fact_set.to_dict())
    assert restored == fact_set
