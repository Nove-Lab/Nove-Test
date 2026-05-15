"""Unit tests for `novetest.coverage.persistence`."""

from __future__ import annotations

import json
from pathlib import Path

from novetest.coverage.persistence import (
    COVERAGE_FACTS_FILENAME,
    coverage_facts_dir,
    coverage_facts_path,
    read_coverage_facts,
    write_coverage_facts,
)
from novetest.memory.project_store import get_project_store_state
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


def _make_fact_set(run_id: str = "01HFOO") -> CoverageFactSet:
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
    file_coverage = FileCoverage(
        file_path="src/pkg/a.py",
        executed_lines=(1, 2),
        missing_lines=(3,),
        excluded_lines=(),
        executed_branches=((1, 2),),
        missing_branches=((1, 3),),
        summary=summary,
        line_contexts={1: ("tests/test_a.py::test_one",)},
    )
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=1_700_000_000_000),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=summary,
        files=(file_coverage,),
        derived_at=1_700_000_001_000,
    )


def test_coverage_facts_path_is_load_bearing(initialized_store: Path) -> None:
    """Path MUST match Memory's `_availability_flags` probe location.

    Memory checks ``<store>/coverage/facts/run_<id>/coverage_facts.json``;
    this asserts our helper produces exactly that path.
    """
    store = get_project_store_state(initialized_store)
    expected = (
        store.path
        / "coverage"
        / "facts"
        / "run_01HFOO"
        / "coverage_facts.json"
    )
    assert coverage_facts_path(store, "01HFOO") == expected


def test_coverage_facts_filename_constant() -> None:
    """The filename is part of the contract — keep the constant honest."""
    assert COVERAGE_FACTS_FILENAME == "coverage_facts.json"


def test_write_then_read_round_trips(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    fact_set = _make_fact_set()
    target = write_coverage_facts(store, fact_set)
    assert target.is_file()
    restored = read_coverage_facts(store, fact_set.run_reference.run_id)
    assert restored == fact_set


def test_write_creates_directory_on_demand(initialized_store: Path) -> None:
    """Pre-existing `<store>/coverage/facts/` is created by init; per-run
    dir is materialized lazily on first write."""
    store = get_project_store_state(initialized_store)
    fact_set = _make_fact_set(run_id="01HNEW")
    run_dir = coverage_facts_dir(store, "01HNEW")
    assert not run_dir.exists()
    write_coverage_facts(store, fact_set)
    assert run_dir.is_dir()


def test_write_overwrites_existing_facts(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    first = _make_fact_set()
    write_coverage_facts(store, first)
    # Re-derive with a different derived_at — second write must replace.
    second = CoverageFactSet(
        run_reference=first.run_reference,
        engine_name=first.engine_name,
        ecosystem=first.ecosystem,
        mapping_granularity=first.mapping_granularity,
        summary=first.summary,
        files=first.files,
        derived_at=first.derived_at + 1000,
    )
    write_coverage_facts(store, second)
    restored = read_coverage_facts(store, first.run_reference.run_id)
    assert restored is not None
    assert restored.derived_at == second.derived_at


def test_read_returns_none_when_no_facts_yet(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    assert read_coverage_facts(store, "01HNONE") is None


def test_written_file_is_valid_json(initialized_store: Path) -> None:
    """Memory's flag probes for the file; downstream tooling reads it as JSON.
    A trailing newline keeps line-oriented tools happy."""
    store = get_project_store_state(initialized_store)
    fact_set = _make_fact_set()
    path = write_coverage_facts(store, fact_set)
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = json.loads(raw)
    assert parsed["schema_version"] == 1
    assert parsed["run_reference"]["run_id"] == fact_set.run_reference.run_id
