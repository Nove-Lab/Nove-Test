"""``_derive_aggregate`` mode — unit tests.

The ``sbfl_aggregate`` mode is Path B of the strategy doc §2 mode
selection: aggregate (or coarser-than-per-test) coverage + failed tests
→ file-level SBFL ranking with FLUCCS-style regression-aware
reweighting when a comparable baseline exists.

Algorithm summary:
- Per file: ``ef`` = failing tests whose failure trace mentions the
  file; ``ep`` ≈ total_passing if file is in aggregate coverage else 0;
  ``nf = total_failing - ef``; ``np = total_passing - ep``.
- Apply all 4 SBFL formulas via the existing helpers.
- If regression "changed_files" is non-empty, multiplicatively boost
  scores by ``(1 + 0.5)``.
- Sort + filter score-zero + normalize + dense-rank + truncate to top_n.

Output: a ``LocalizationFinding`` with:
- ``mode == "sbfl_aggregate"`` and ``confidence == "medium"``.
- ``alternate_scores_available`` = all 3 non-selected formulas (NO
  envelope deviation — same shape as sbfl_per_test).
- File-level entries (``CodeLocation.kind == "file"``).
- ``metadata["regression_reweighted"]`` bool flag.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.derive import _derive_aggregate
from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


def _summary(num: int = 1) -> CoverageSummary:
    return CoverageSummary(
        num_statements=num,
        covered_statements=num,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


def _file_cov(
    *, file_path: str, lines: tuple[int, ...] = (1, 2)
) -> FileCoverage:
    """Aggregate-mode FileCoverage (no line_contexts)."""
    return FileCoverage(
        file_path=file_path,
        executed_lines=lines,
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_summary(len(lines) or 1),
        line_contexts={},
    )


def _make_setup(
    tmp_path: Path,
    *,
    test_results: tuple[TestResult, ...],
    covered_files: tuple[str, ...],
    engine_name: str = "pytest",
) -> tuple[object, RunRecord, CoverageFactSet]:
    """Materialize a Project Store with one Run + aggregate coverage.

    Returns ``(store, record, coverage)``. Uses synthetic IDs so
    fixtures are deterministic across runs.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    ref = RunReference(run_id="01HAGG00000000000000000001", created_at=1_700_000_000_000)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        engine_version=None,
        ecosystem="python" if engine_name == "pytest" else "rust",
        status="failed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=test_results,
    )
    store_run_evidence(store, record)
    files = tuple(_file_cov(file_path=fp) for fp in covered_files)
    coverage = CoverageFactSet(
        run_reference=ref,
        engine_name=engine_name,
        ecosystem="python" if engine_name == "pytest" else "rust",
        mapping_granularity="aggregate",
        summary=_summary(2 * len(files)),
        files=files,
        derived_at=ref.created_at + 500,
    )
    write_coverage_facts(store, coverage)
    handle = get_project_store_state(workspace / ".novetest")
    return handle, record, coverage


def _make_regression_facts(*, changed_files: tuple[str, ...]) -> RegressionFactSet:
    coverage_change = {
        "schema_version": 1,
        "baseline_run_reference": {
            "run_id": "01HBASE000000000000000001",
            "created_at": 1_699_000_000_000,
            "schema_version": 1,
        },
        "target_run_reference": {
            "run_id": "01HAGG00000000000000000001",
            "created_at": 1_700_000_000_000,
            "schema_version": 1,
        },
        "baseline_granularity": "aggregate",
        "target_granularity": "aggregate",
        "summary_before": _summary(0).to_dict(),
        "summary_after": _summary(0).to_dict(),
        "files_added": list(changed_files),
        "files_removed": [],
        "file_deltas": [],
    }
    return RegressionFactSet(
        baseline_run_reference=RunReference(
            run_id="01HBASE000000000000000001", created_at=1_699_000_000_000
        ),
        target_run_reference=RunReference(
            run_id="01HAGG00000000000000000001", created_at=1_700_000_000_000
        ),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version=None,
        target_engine_version=None,
        derived_at=1_700_000_001_000,
        summary=RegressionSummary(
            regressed=0, fixed=0, still_failing=0, still_passing=0,
            still_skipped=0, newly_skipped=0, newly_active=0,
            added=0, removed=0,
            total_baseline_tests=0, total_target_tests=0,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=coverage_change,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_ranks_failure_traced_file_top(tmp_path: Path) -> None:
    """Aggregate coverage + 1 failing test mentioning src/foo.py → top-1."""
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:5: AssertionError",
            ),
            TestResult(
                node_id="tests/t.py::t_ok",
                outcome="passed",
                duration_ms=1,
            ),
        ),
        covered_files=("src/foo.py", "src/bar.py", "src/baz.py"),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert finding.mode == "sbfl_aggregate"
    assert finding.confidence == "medium"
    assert finding.formula == "ochiai"
    assert set(finding.alternate_scores_available) == {"op2", "dstar2", "tarantula"}
    # Only files appearing in failure traces have ef > 0; bar.py and
    # baz.py have ef=0 → Ochiai = 0 → filtered out.
    assert len(finding.entries) == 1
    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "file"
    assert top.code_location.file == "src/foo.py"
    assert top.code_location.symbol is None
    # Ochiai = ef / sqrt((ef+nf) * (ef+ep))
    #        = 1 / sqrt((1+0) * (1+1)) = 1 / sqrt(2)
    assert top.score_raw == pytest.approx(1.0 / (2 ** 0.5))


def test_passing_only_run_with_aggregate_coverage_yields_no_entries(
    tmp_path: Path,
) -> None:
    """No failing tests in failed_test_ids → no candidate files → empty entries.

    (Note: the dispatcher in ``derive_localization_findings`` rejects
    zero-failed-tests with REASON_NO_FAILED_TESTS before reaching this
    function; but the function itself should also be safe when called
    directly with empty failed_test_ids.)
    """
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_ok",
                outcome="passed",
                duration_ms=1,
            ),
        ),
        covered_files=("src/foo.py",),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset(),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert finding.entries == ()


# ---------------------------------------------------------------------------
# Regression-aware reweighting
# ---------------------------------------------------------------------------


def test_regression_reweighting_lifts_changed_file_score(tmp_path: Path) -> None:
    """Two failure-traced files: only changed.py is in regression set;
    its score gets the ``×1.5`` boost."""
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_a",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/changed.py:3: e",
            ),
            TestResult(
                node_id="tests/t.py::t_b",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/unchanged.py:7: e",
            ),
        ),
        covered_files=("src/changed.py", "src/unchanged.py"),
    )
    rf = _make_regression_facts(changed_files=("src/changed.py",))
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t_a", "tests/t.py::t_b"}),
        regression_facts=rf,
        top_n=10,
        formula="ochiai",
    )
    assert finding.metadata.get("regression_reweighted") is True
    assert finding.metadata.get("changed_files_count") == 1

    by_file = {e.code_location.file: e for e in finding.entries}
    assert "src/changed.py" in by_file
    assert "src/unchanged.py" in by_file

    # Both files have identical (ef, ep, nf, np), so unboosted Ochiai is
    # equal. The 1.5x boost flips ranking so changed.py is rank 1.
    assert by_file["src/changed.py"].rank == 1
    assert by_file["src/unchanged.py"].rank == 2
    # The boosted file's raw score is exactly 1.5x the unboosted one.
    assert by_file["src/changed.py"].score_raw == pytest.approx(
        by_file["src/unchanged.py"].score_raw * 1.5
    )


def test_no_regression_facts_path_falls_back_to_failure_only_ochiai(
    tmp_path: Path,
) -> None:
    """Without regression_facts, mode is still ``sbfl_aggregate`` but the
    floor (failure-only Ochiai) applies — ``regression_reweighted=False``
    in metadata."""
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:3: e",
            ),
        ),
        covered_files=("src/foo.py",),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert finding.metadata.get("regression_reweighted") is False
    assert finding.metadata.get("changed_files_count") == 0
    assert finding.mode == "sbfl_aggregate"
    assert finding.confidence == "medium"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_small_n_one_failing_one_passing(tmp_path: Path) -> None:
    """Small-N edge case — single failing test + single passing test."""
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_pass",
                outcome="passed",
                duration_ms=1,
            ),
            TestResult(
                node_id="tests/t.py::t_fail",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:1: e",
            ),
        ),
        covered_files=("src/foo.py",),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t_fail"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert len(finding.entries) == 1
    assert finding.entries[0].code_location.file == "src/foo.py"


def test_per_test_file_granularity_routed_to_aggregate(tmp_path: Path) -> None:
    """Granularity ``"per-test-file"`` (jest/dotnet partial attribution)
    is also handled by the aggregate path per strategy doc §2 (the
    Path B precondition is ``mapping_granularity in {"aggregate",
    "per-test-class", "per-test-file"}``).

    Verified here at the helper level by passing a ``per-test-file``
    granularity coverage in. The dispatch test in
    ``test_derive_modes_dispatch.py`` covers the top-level routing.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    ref = RunReference(run_id="01HAGGPTF000000000000000001", created_at=1_700_000_000_000)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version=None,
        ecosystem="python",
        status="failed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(
                node_id="tests/t.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:3: e",
            ),
        ),
    )
    store_run_evidence(store, record)
    coverage = CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test-file",
        summary=_summary(1),
        files=(_file_cov(file_path="src/foo.py"),),
        derived_at=ref.created_at + 500,
    )
    write_coverage_facts(store, coverage)
    handle = get_project_store_state(workspace / ".novetest")

    finding = _derive_aggregate(
        store=handle,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    # Same algorithm, same output mode.
    assert finding.mode == "sbfl_aggregate"
    assert len(finding.entries) == 1


# ---------------------------------------------------------------------------
# Defect 3 regression pins (2026-05-31) — coverage-scope filter
# ---------------------------------------------------------------------------


def test_defect3_stdlib_path_in_failure_trace_is_dropped_by_coverage_filter(
    tmp_path: Path,
) -> None:
    """Defect 3 regression pin: a failure-trace path that's NOT in coverage
    (e.g. Rust stdlib like ``/rustc/.../library/core/src/panicking.rs``)
    MUST be dropped from the candidate set by the algorithm-level filter.

    Without the filter, the parser-extracted stdlib path would tie with
    the real bug file at e_f=1 (or take the top spot lexicographically).
    With the filter, only files in the project's ``coverage.files`` are
    considered candidates; stdlib files (which aren't instrumented for
    coverage) are naturally excluded.

    This is the defense-in-depth half of CEO Option D (the other half is
    the parser-side catch-all regex removal, tested separately in
    ``test_failure_log_parser.py::test_cargo_bare_rs_path_does_NOT_match_after_defect3_fix``).
    """
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                # Simulate a failure trace that mentions BOTH the bug file
                # AND a "stdlib-like" path (something not in covered_files).
                # The two anchored cargo regexes (panicked at / failed at)
                # also extract this synthetic input on the cargo engine,
                # but the same principle applies for pytest-style inputs:
                # the algorithm filter MUST drop the un-covered path.
                failure_reference=(
                    "src/buggy.py:5: AssertionError\n"
                    "stack: /rustc/abc123/library/core/src/panicking.rs:80: panic_fmt"
                ),
            ),
        ),
        # Coverage ONLY includes the workspace file, not the stdlib path.
        covered_files=("src/buggy.py",),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    # The stdlib-like path MUST NOT appear in entries.
    file_paths = [e.code_location.file for e in finding.entries]
    assert not any("panicking.rs" in p for p in file_paths), (
        f"Defect 3 regression: stdlib path leaked into ranking: {file_paths!r}"
    )
    assert not any("/rustc/" in p for p in file_paths), (
        f"Defect 3 regression: /rustc/ path leaked into ranking: {file_paths!r}"
    )
    # Only the covered workspace file is a candidate.
    assert file_paths == ["src/buggy.py"]
    # Sanity: the surviving file ranks #1 with positive Ochiai score.
    assert finding.entries[0].rank == 1
    assert finding.entries[0].score_raw > 0


def test_defect3_failure_trace_only_files_are_filtered_out(tmp_path: Path) -> None:
    """A workspace file mentioned in a failure trace but NOT in coverage
    is dropped by the filter. Per the question doc's Risk analysis:

      "if a bug is in a workspace file that wasn't covered by any test
      (zero coverage), this filter would drop it too."

    This test pins that tradeoff explicitly. The fixture: one failing
    test points at `src/never_covered.py`, but coverage only includes
    `src/sometimes_covered.py` (a different file with no failure mention).
    Result: NO entries — both files have score=0 after the algorithm.

    (`src/never_covered.py` is filtered before scoring; `src/sometimes_covered.py`
    has ef=0 and is filtered by the Step 5 score-zero gate.)
    """
    store, record, coverage = _make_setup(
        tmp_path,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/never_covered.py:1: AssertionError",
            ),
            TestResult(
                node_id="tests/t.py::t_ok",
                outcome="passed",
                duration_ms=1,
            ),
        ),
        # Coverage includes a DIFFERENT file from the one in the failure trace.
        covered_files=("src/sometimes_covered.py",),
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    # Trade-off documented in derive.py: never_covered.py is dropped because
    # it's not in coverage; sometimes_covered.py has ef=0 (no failure mention)
    # so Ochiai=0 and it's dropped by the Step 5 score-zero gate.
    # Result: no entries. Mode still surfaces (so the consumer sees the
    # ranking attempt outcome).
    assert finding.entries == ()
    assert finding.mode == "sbfl_aggregate"
    # The parse_warnings should still mention the failing test was processed
    # (failure log was parseable; the file just wasn't in coverage scope).
    # No parse_warning expected here — parsing succeeded; the filter is
    # downstream. (parse_warnings only fire when the parser returns empty.)
    parse_warnings = finding.metadata.get("parse_warnings", [])
    assert parse_warnings == [], (
        f"Expected no parse_warnings (file was parseable, just not in coverage); "
        f"got {parse_warnings!r}"
    )
