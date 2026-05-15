"""Unit tests for `novetest.models.coverage_fact_set`."""

from __future__ import annotations

import pytest

from novetest.models.coverage_fact_set import (
    SCHEMA_VERSION,
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


def _sample_reference() -> RunReference:
    return RunReference(run_id="01HXYZ", created_at=1_700_000_000_000)


def _sample_summary(**overrides: object) -> CoverageSummary:
    defaults: dict[str, object] = {
        "num_statements": 100,
        "covered_statements": 80,
        "missing_statements": 20,
        "excluded_statements": 0,
        "num_branches": 30,
        "covered_branches": 25,
        "missing_branches": 5,
        "percent_covered": 80.0,
    }
    defaults.update(overrides)
    return CoverageSummary(**defaults)  # type: ignore[arg-type]


def _sample_file(**overrides: object) -> FileCoverage:
    defaults: dict[str, object] = {
        "file_path": "src/pkg/module.py",
        "executed_lines": (1, 2, 3, 5),
        "missing_lines": (4,),
        "excluded_lines": (),
        "executed_branches": ((2, 3), (3, 5)),
        "missing_branches": ((3, 4),),
        "summary": _sample_summary(),
        "line_contexts": {
            1: ("tests/test_module.py::test_a", "tests/test_module.py::test_b"),
            2: ("tests/test_module.py::test_a",),
        },
    }
    defaults.update(overrides)
    return FileCoverage(**defaults)  # type: ignore[arg-type]


def _sample_fact_set(**overrides: object) -> CoverageFactSet:
    defaults: dict[str, object] = {
        "run_reference": _sample_reference(),
        "engine_name": "pytest",
        "ecosystem": "python",
        "mapping_granularity": "per-test",
        "summary": _sample_summary(),
        "files": (_sample_file(),),
        "derived_at": 1_700_000_001_000,
        "metadata": {"coverage_py_version": "7.6.0", "show_contexts": True},
    }
    defaults.update(overrides)
    return CoverageFactSet(**defaults)  # type: ignore[arg-type]


# --- CoverageSummary ---------------------------------------------------------


def test_summary_round_trip() -> None:
    summary = _sample_summary()
    assert CoverageSummary.from_dict(summary.to_dict()) == summary


def test_summary_from_dict_missing_key_raises() -> None:
    payload = _sample_summary().to_dict()
    del payload["num_statements"]
    with pytest.raises(ValueError, match="missing required keys"):
        CoverageSummary.from_dict(payload)


def test_summary_excluded_defaults_to_zero_when_absent() -> None:
    payload = _sample_summary().to_dict()
    del payload["excluded_statements"]
    restored = CoverageSummary.from_dict(payload)
    assert restored.excluded_statements == 0


# --- FileCoverage ------------------------------------------------------------


def test_file_round_trip_with_contexts() -> None:
    file_coverage = _sample_file()
    restored = FileCoverage.from_dict(file_coverage.to_dict())
    assert restored == file_coverage


def test_file_round_trip_without_contexts() -> None:
    file_coverage = _sample_file(line_contexts={})
    restored = FileCoverage.from_dict(file_coverage.to_dict())
    assert restored.line_contexts == {}


def test_file_to_dict_stringifies_line_context_keys() -> None:
    file_coverage = _sample_file()
    payload = file_coverage.to_dict()
    # JSON object keys are strings — to_dict must produce that shape so
    # downstream json.dumps does not coerce dict[int, ...] keys silently.
    assert all(isinstance(k, str) for k in payload["line_contexts"].keys())


def test_file_branch_arc_must_be_two_element_sequence() -> None:
    payload = _sample_file().to_dict()
    payload["missing_branches"] = [[1, 2, 3]]
    with pytest.raises(ValueError, match="2-element sequence"):
        FileCoverage.from_dict(payload)


def test_file_from_dict_missing_required_key_raises() -> None:
    payload = _sample_file().to_dict()
    del payload["summary"]
    with pytest.raises(ValueError, match="missing required keys"):
        FileCoverage.from_dict(payload)


# --- CoverageFactSet ---------------------------------------------------------


def test_fact_set_round_trip() -> None:
    fact_set = _sample_fact_set()
    restored = CoverageFactSet.from_dict(fact_set.to_dict())
    assert restored == fact_set


def test_fact_set_to_dict_includes_schema_version_and_nested_versions() -> None:
    fact_set = _sample_fact_set()
    payload = fact_set.to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["run_reference"]["schema_version"] == SCHEMA_VERSION


def test_fact_set_rejects_unknown_granularity() -> None:
    with pytest.raises(ValueError, match="Invalid mapping_granularity"):
        _sample_fact_set(mapping_granularity="per-line")


@pytest.mark.parametrize(
    "granularity",
    ["per-test", "per-test-class", "per-test-file", "aggregate"],
)
def test_fact_set_accepts_each_documented_granularity(granularity: str) -> None:
    fact_set = _sample_fact_set(mapping_granularity=granularity)
    assert fact_set.mapping_granularity == granularity


def test_fact_set_from_dict_missing_required_key_raises() -> None:
    payload = _sample_fact_set().to_dict()
    del payload["mapping_granularity"]
    with pytest.raises(ValueError, match="missing required keys"):
        CoverageFactSet.from_dict(payload)


def test_fact_set_from_dict_rejects_future_schema_version() -> None:
    payload = _sample_fact_set().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        CoverageFactSet.from_dict(payload)


def test_fact_set_round_trip_with_empty_files_and_metadata() -> None:
    fact_set = CoverageFactSet(
        run_reference=_sample_reference(),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="aggregate",
        summary=_sample_summary(num_statements=0, covered_statements=0,
                                missing_statements=0, num_branches=0,
                                covered_branches=0, missing_branches=0,
                                percent_covered=0.0),
        files=(),
        derived_at=1_700_000_001_000,
    )
    restored = CoverageFactSet.from_dict(fact_set.to_dict())
    assert restored == fact_set


def test_fact_set_instances_are_frozen() -> None:
    fact_set = _sample_fact_set()
    with pytest.raises(AttributeError):
        fact_set.engine_name = "jest"  # type: ignore[misc]
