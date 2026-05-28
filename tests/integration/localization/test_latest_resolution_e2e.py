"""End-to-end integration tests for the latest-resolution helpers.

Builds three real Run Records via the real ``store_run_evidence`` +
``write_coverage_facts`` seams (no mocking), then exercises:

- ``resolve_latest_analyzable_run`` skips a passing-only run, skips a
  failing-without-coverage run, and returns the failing-with-coverage
  run.
- ``derive_latest_localization`` end-to-end through the same store —
  the canonical ``localization_findings.json`` lands at the
  load-bearing path and the Memory flag flips on a refreshed
  ``retrieve_run_evidence`` call.
"""

from __future__ import annotations

from pathlib import Path

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization import (
    derive_latest_localization,
    resolve_latest_analyzable_run,
)
from novetest.localization.persistence import localization_findings_path
from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import retrieve_run_evidence, store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# Three timestamps so insertion order is independent of chronological order.
_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000


def _record(
    *,
    run_id: str,
    created_at: int,
    test_results: tuple[TestResult, ...],
    status: str,
) -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=created_at),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status=status,
        started_at=created_at,
        completed_at=created_at + 1_000,
        test_results=test_results,
    )


def _summary(num: int) -> CoverageSummary:
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


def _per_test_coverage(
    *,
    run_reference: RunReference,
    files: tuple[FileCoverage, ...],
) -> CoverageFactSet:
    total = sum(len(f.executed_lines) for f in files) or 1
    return CoverageFactSet(
        run_reference=run_reference,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_summary(total),
        files=files,
        derived_at=run_reference.created_at + 500,
    )


def _calc_file(line_contexts: dict[int, tuple[str, ...]]) -> FileCoverage:
    return FileCoverage(
        file_path="src/calc.py",
        executed_lines=tuple(sorted(line_contexts.keys())),
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_summary(len(line_contexts) or 1),
        line_contexts=line_contexts,
    )


_BUGGY_SOURCE = (
    "def safe(x):\n"          # line 1
    "    return x + 1\n"      # line 2
    "\n"
    "def buggy(x):\n"         # line 4
    "    return x * 0\n"      # line 5 — the bug
    "\n"
    "def neutral(x):\n"       # line 7
    "    return x\n"          # line 8
)


def test_resolve_latest_picks_failing_with_coverage_over_failing_without(
    tmp_path: Path,
) -> None:
    """Three runs in the store, newest-first:

    1. PASSING_ONLY (newest)            — no failed tests, has coverage   → skip
    2. FAILING_NO_COVERAGE (middle)     — has failed tests, no coverage   → skip
    3. FAILING_WITH_COVERAGE (oldest)   — has failed tests + coverage     → RETURNED

    Memory orders newest-first, so the resolver probes them in this order
    and must walk past the first two before returning the third.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    # Materialize the source the resolver's downstream consumer will need.
    (workspace / "src").mkdir()
    (workspace / "src" / "calc.py").write_text(_BUGGY_SOURCE, encoding="utf-8")
    store = create_project_store(workspace)

    # Oldest: failing test + per-test coverage attribution → analyzable.
    failing_with_cov_ref = RunReference(
        run_id="01OLDFAILCOV0000000000000001", created_at=_TS_OLD
    )
    store_run_evidence(
        store,
        _record(
            run_id=failing_with_cov_ref.run_id,
            created_at=failing_with_cov_ref.created_at,
            test_results=(
                TestResult(
                    node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1
                ),
                TestResult(
                    node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1
                ),
            ),
            status="failed",
        ),
    )
    write_coverage_facts(
        store,
        _per_test_coverage(
            run_reference=failing_with_cov_ref,
            files=(
                _calc_file(
                    {
                        1: ("tests/test_calc.py::test_safe",),
                        2: ("tests/test_calc.py::test_safe",),
                        4: ("tests/test_calc.py::test_buggy",),
                        5: ("tests/test_calc.py::test_buggy",),
                    }
                ),
            ),
        ),
    )

    # Middle: failing test, no coverage → check fails (no_coverage path).
    failing_no_cov_ref = RunReference(
        run_id="01MIDFAILNOCOV00000000000002", created_at=_TS_MID
    )
    store_run_evidence(
        store,
        _record(
            run_id=failing_no_cov_ref.run_id,
            created_at=failing_no_cov_ref.created_at,
            test_results=(
                TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
            ),
            status="failed",
        ),
    )

    # Newest: passing only + coverage → check fails (no_failed_tests path).
    passing_only_ref = RunReference(
        run_id="01NEWPASSONLY0000000000000003", created_at=_TS_NEW
    )
    store_run_evidence(
        store,
        _record(
            run_id=passing_only_ref.run_id,
            created_at=passing_only_ref.created_at,
            test_results=(
                TestResult(
                    node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1
                ),
            ),
            status="passed",
        ),
    )
    write_coverage_facts(
        store,
        _per_test_coverage(
            run_reference=passing_only_ref,
            files=(
                _calc_file(
                    {
                        1: ("tests/test_calc.py::test_safe",),
                        2: ("tests/test_calc.py::test_safe",),
                    }
                ),
            ),
        ),
    )

    handle = get_project_store_state(workspace / ".novetest")
    result = resolve_latest_analyzable_run(handle)
    assert isinstance(result, RunReference)
    assert result.run_id == failing_with_cov_ref.run_id


def test_derive_latest_writes_findings_to_canonical_path_and_flips_memory_flag(
    tmp_path: Path,
) -> None:
    """End-to-end: derive_latest_localization writes the canonical
    ``localization_findings.json`` and Memory's flag flips on refresh.

    Single analyzable run keeps the test focused on the composition seam;
    the multi-run resolver path is exercised by the test above.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "calc.py").write_text(_BUGGY_SOURCE, encoding="utf-8")
    store = create_project_store(workspace)

    analyzable_ref = RunReference(
        run_id="01HE2EANALY00000000000000001", created_at=_TS_NEW
    )
    store_run_evidence(
        store,
        _record(
            run_id=analyzable_ref.run_id,
            created_at=analyzable_ref.created_at,
            test_results=(
                TestResult(
                    node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1
                ),
                TestResult(
                    node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1
                ),
            ),
            status="failed",
        ),
    )
    write_coverage_facts(
        store,
        _per_test_coverage(
            run_reference=analyzable_ref,
            files=(
                _calc_file(
                    {
                        1: ("tests/test_calc.py::test_safe",),
                        2: ("tests/test_calc.py::test_safe",),
                        4: ("tests/test_calc.py::test_buggy",),
                        5: ("tests/test_calc.py::test_buggy",),
                    }
                ),
            ),
        ),
    )

    handle = get_project_store_state(workspace / ".novetest")
    finding = derive_latest_localization(handle)
    assert isinstance(finding, LocalizationFinding)
    assert finding.run_reference == analyzable_ref
    assert finding.mode == "sbfl_per_test"

    findings_path = localization_findings_path(handle, analyzable_ref.run_id)
    assert findings_path.is_file()

    refreshed = retrieve_run_evidence(handle, analyzable_ref)
    assert refreshed.has_localization_findings is True
