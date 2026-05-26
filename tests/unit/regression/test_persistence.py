"""Unit tests for ``novetest.regression.persistence``.

The path layout is **load-bearing** — Memory's ``_availability_flags`` probe
scans ``<store>/regression/pairs/`` for directory names containing
``run_<run_id>``. These tests pin the directory + filename shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory.project_store import get_project_store_state
from novetest.models.regression_fact_set import (
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_reference import RunReference
from novetest.regression.persistence import (
    REGRESSION_FACTS_FILENAME,
    read_regression_facts_raw,
    regression_facts_path,
    regression_pair_dir,
    regression_pair_dirname,
    write_regression_facts,
)


def _summary() -> RegressionSummary:
    return RegressionSummary(
        regressed=0, fixed=0, still_failing=0, still_passing=1,
        still_skipped=0, newly_skipped=0, newly_active=0, added=0,
        removed=0, total_baseline_tests=1, total_target_tests=1,
    )


def _fact_set(
    baseline_id: str = "01HBASE",
    target_id: str = "01HTRGT",
) -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=RunReference(run_id=baseline_id, created_at=1),
        target_run_reference=RunReference(run_id=target_id, created_at=2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=1_700_000_000_000,
        summary=_summary(),
        test_transitions=(),
        output_diff=OutputDiffRecord(
            baseline_stdout_sha256=None,
            target_stdout_sha256=None,
            baseline_stderr_sha256=None,
            target_stderr_sha256=None,
            stdout_identical=True,
            stderr_identical=True,
            baseline_stdout_path=None,
            target_stdout_path=None,
            baseline_stderr_path=None,
            target_stderr_path=None,
        ),
        coverage_change=None,
    )


def test_regression_pair_dirname_is_load_bearing() -> None:
    """The directory naming is the contract Memory's probe scans for —
    keep the literal layout pinned."""
    assert (
        regression_pair_dirname("01HBASE", "01HTRGT")
        == "run_01HBASE__run_01HTRGT"
    )


def test_regression_pair_dirname_is_order_significant() -> None:
    """(A, B) and (B, A) produce different directory names per decision §1."""
    assert regression_pair_dirname("A", "B") != regression_pair_dirname("B", "A")


def test_regression_facts_filename_constant() -> None:
    assert REGRESSION_FACTS_FILENAME == "regression_facts.json"


def test_regression_facts_path_matches_memory_probe_location(
    initialized_store: Path,
) -> None:
    store = get_project_store_state(initialized_store)
    expected = (
        store.path
        / "regression"
        / "pairs"
        / "run_01HBASE__run_01HTRGT"
        / "regression_facts.json"
    )
    assert regression_facts_path(store, "01HBASE", "01HTRGT") == expected


def test_write_then_read_round_trips(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    fs = _fact_set()
    target = write_regression_facts(store, fs)
    assert target.is_file()

    raw = read_regression_facts_raw(
        store, fs.baseline_run_reference.run_id, fs.target_run_reference.run_id
    )
    assert raw is not None
    restored = RegressionFactSet.from_dict(raw)
    assert restored == fs


def test_write_creates_directory_on_demand(initialized_store: Path) -> None:
    """Top-level ``<store>/regression/pairs`` exists at init; per-pair
    dir is materialized lazily."""
    store = get_project_store_state(initialized_store)
    fs = _fact_set(baseline_id="01HNEW1", target_id="01HNEW2")
    pair_dir = regression_pair_dir(store, "01HNEW1", "01HNEW2")
    assert not pair_dir.exists()
    write_regression_facts(store, fs)
    assert pair_dir.is_dir()


def test_write_overwrites_existing(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    first = _fact_set()
    write_regression_facts(store, first)
    # Re-derive: same pair, different derived_at.
    second = RegressionFactSet(
        baseline_run_reference=first.baseline_run_reference,
        target_run_reference=first.target_run_reference,
        baseline_engine_name=first.baseline_engine_name,
        target_engine_name=first.target_engine_name,
        baseline_engine_version=first.baseline_engine_version,
        target_engine_version=first.target_engine_version,
        derived_at=first.derived_at + 1_000,
        summary=first.summary,
        test_transitions=first.test_transitions,
        output_diff=first.output_diff,
        coverage_change=first.coverage_change,
    )
    write_regression_facts(store, second)
    raw = read_regression_facts_raw(
        store, first.baseline_run_reference.run_id,
        first.target_run_reference.run_id,
    )
    assert raw is not None
    assert raw["derived_at"] == second.derived_at


def test_read_returns_none_when_no_facts(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    assert (
        read_regression_facts_raw(store, "01HNONE1", "01HNONE2") is None
    )


def test_written_file_is_valid_json(initialized_store: Path) -> None:
    """Memory's probe checks the regression_facts.json file specifically;
    downstream tooling reads it as JSON. A trailing newline keeps
    line-oriented tools happy."""
    store = get_project_store_state(initialized_store)
    fs = _fact_set()
    path = write_regression_facts(store, fs)
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = json.loads(raw)
    assert parsed["schema_version"] == 1
    assert parsed["baseline_run_reference"]["run_id"] == "01HBASE"
    assert parsed["target_run_reference"]["run_id"] == "01HTRGT"
