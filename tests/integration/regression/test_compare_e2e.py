"""End-to-end integration tests for ``compare_runs``.

Build two real ``RunRecord``s via the real ``store_run_evidence`` seam,
call ``compare_runs(store, baseline, target)``, and validate:

- The persisted ``regression_facts.json`` lands at the pinned path.
- The on-disk JSON shape matches decision §4 (key-level pattern match).
- Cross-engine integration with Coverage: when both runs have
  ``CoverageFactSet`` written via the real ``write_coverage_facts`` seam,
  ``coverage_change`` is populated with a ``CoverageDelta.to_dict()``
  payload; when neither side has Coverage Facts, ``coverage_change`` is None.
- Cache hit: re-calling ``compare_runs`` does NOT rewrite the file
  (``st_mtime_ns`` unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.coverage.persistence import write_coverage_facts
from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression import compare_runs
from novetest.regression.persistence import regression_facts_path


_REF_BASELINE = RunReference(
    run_id="01HBASELINE0000000000000001", created_at=1_700_000_000_000
)
_REF_TARGET = RunReference(
    run_id="01HTARGET00000000000000002", created_at=1_700_000_001_000
)


def _summary(pct: float = 80.0) -> CoverageSummary:
    return CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=pct,
    )


def _file(path: str, executed: tuple[int, ...]) -> FileCoverage:
    return FileCoverage(
        file_path=path,
        executed_lines=executed,
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_summary(),
    )


def _build_two_runs(workspace: Path) -> tuple[Path, RunRecord, RunRecord]:
    """Materialize a Project Store with two runs sharing the same target.

    Baseline: 2 passes + 1 fail (``tests/x.py::test_a`` passes).
    Target  : 2 passes + 1 fail + 1 new (``tests/x.py::test_a`` now fails;
              ``tests/x.py::test_new`` appears).
    """
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    baseline = RunRecord(
        run_reference=_REF_BASELINE,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="failed",
        started_at=_REF_BASELINE.created_at,
        completed_at=_REF_BASELINE.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=12),
            TestResult(node_id="tests/x.py::test_b", outcome="passed", duration_ms=7),
            TestResult(node_id="tests/x.py::test_c", outcome="failed", duration_ms=9),
        ),
    )
    target = RunRecord(
        run_reference=_REF_TARGET,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="failed",
        started_at=_REF_TARGET.created_at,
        completed_at=_REF_TARGET.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_a", outcome="failed", duration_ms=14),
            TestResult(node_id="tests/x.py::test_b", outcome="passed", duration_ms=6),
            TestResult(node_id="tests/x.py::test_c", outcome="failed", duration_ms=10),
            TestResult(node_id="tests/x.py::test_new", outcome="passed", duration_ms=5),
        ),
    )
    store_run_evidence(store, baseline)
    store_run_evidence(store, target)
    return store.path, baseline, target


def test_compare_runs_produces_expected_facts(tmp_path: Path) -> None:
    store_path, _baseline, _target = _build_two_runs(tmp_path / "ws")
    # Re-resolve handle (mirrors how a CLI verb would consume it).
    from novetest.memory.project_store import get_project_store_state
    store = get_project_store_state(store_path)

    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)

    # 1 regression (test_a: pass→fail), 1 still-passing (test_b),
    # 1 still-failing (test_c), 1 added (test_new).
    assert fact_set.summary.regressed == 1
    assert fact_set.summary.still_passing == 1
    assert fact_set.summary.still_failing == 1
    assert fact_set.summary.added == 1
    assert fact_set.summary.removed == 0
    assert fact_set.summary.total_baseline_tests == 3
    assert fact_set.summary.total_target_tests == 4

    by_id = {t.node_id: t for t in fact_set.test_transitions}
    assert by_id["tests/x.py::test_a"].category == "regressed"
    assert by_id["tests/x.py::test_b"].category == "still_passing"
    assert by_id["tests/x.py::test_c"].category == "still_failing"
    assert by_id["tests/x.py::test_new"].category == "added"
    assert by_id["tests/x.py::test_new"].baseline_outcome is None
    assert by_id["tests/x.py::test_new"].target_outcome == "passed"


def test_compare_runs_writes_facts_at_pinned_path(tmp_path: Path) -> None:
    """The persisted file path is the contract — Memory's probe relies on it."""
    store_path, _b, _t = _build_two_runs(tmp_path / "ws")
    from novetest.memory.project_store import get_project_store_state
    store = get_project_store_state(store_path)
    compare_runs(store, _REF_BASELINE, _REF_TARGET)

    expected_path = regression_facts_path(
        store, _REF_BASELINE.run_id, _REF_TARGET.run_id
    )
    assert expected_path.is_file()
    # Decision §4 — validate the on-disk JSON shape at key level.
    parsed = json.loads(expected_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == 1
    assert parsed["baseline_run_reference"]["run_id"] == _REF_BASELINE.run_id
    assert parsed["target_run_reference"]["run_id"] == _REF_TARGET.run_id
    assert parsed["baseline_engine_name"] == "pytest"
    assert parsed["target_engine_name"] == "pytest"
    assert "summary" in parsed
    assert "test_transitions" in parsed
    assert "output_diff" in parsed
    assert "coverage_change" in parsed
    assert "warnings" in parsed
    assert "metadata" in parsed
    # 9 summary categories + 2 totals = 11 keys (decision §3).
    assert len(parsed["summary"]) == 11


def test_compare_runs_embeds_coverage_when_both_sides_have_facts(
    tmp_path: Path,
) -> None:
    store_path, _b, _t = _build_two_runs(tmp_path / "ws")
    from novetest.memory.project_store import get_project_store_state
    store = get_project_store_state(store_path)

    baseline_fact_set = CoverageFactSet(
        run_reference=_REF_BASELINE,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_summary(),
        files=(_file("src/calc.py", executed=(1, 2, 3)),),
        derived_at=_REF_BASELINE.created_at + 500,
    )
    target_fact_set = CoverageFactSet(
        run_reference=_REF_TARGET,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_summary(pct=90.0),
        files=(_file("src/calc.py", executed=(1, 2, 3, 4)),),
        derived_at=_REF_TARGET.created_at + 500,
    )
    write_coverage_facts(store, baseline_fact_set)
    write_coverage_facts(store, target_fact_set)

    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)
    assert fact_set.coverage_change is not None
    # The embedded payload is ``CoverageDelta.to_dict()`` — validate via the
    # round-trip seam to confirm it's a real, parseable CoverageDelta blob.
    from novetest.coverage.compare import CoverageDelta
    delta = CoverageDelta.from_dict(dict(fact_set.coverage_change))
    assert delta.baseline_run_reference == _REF_BASELINE
    assert delta.target_run_reference == _REF_TARGET
    # The per-file transition is the line 4 newly-covered in target.
    assert len(delta.file_deltas) == 1
    assert delta.file_deltas[0].newly_covered_lines == (4,)


def test_compare_runs_coverage_change_none_when_neither_side_has_facts(
    tmp_path: Path,
) -> None:
    store_path, _b, _t = _build_two_runs(tmp_path / "ws")
    from novetest.memory.project_store import get_project_store_state
    store = get_project_store_state(store_path)

    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)
    assert fact_set.coverage_change is None


def test_compare_runs_cache_hit_does_not_rewrite_file(tmp_path: Path) -> None:
    """A second ``compare_runs`` call must read the cached file rather than
    re-writing it — ``st_mtime_ns`` should be identical across the two calls."""
    store_path, _b, _t = _build_two_runs(tmp_path / "ws")
    from novetest.memory.project_store import get_project_store_state
    store = get_project_store_state(store_path)

    first = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(first, RegressionFactSet)
    cache_path = regression_facts_path(
        store, _REF_BASELINE.run_id, _REF_TARGET.run_id
    )
    initial_mtime = cache_path.stat().st_mtime_ns

    second = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(second, RegressionFactSet)
    assert cache_path.stat().st_mtime_ns == initial_mtime
