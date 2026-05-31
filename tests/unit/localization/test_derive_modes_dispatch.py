"""Mode-selection routing tests for ``derive_localization_findings``.

The dispatch algorithm (strategy doc §2 pseudocode):

    if not failed_tests:
        return Unavailable(REASON_NO_FAILED_TESTS)
    if coverage unavailable:
        return failure_proximity finding (Path C)
    if coverage.mapping_granularity == "per-test":
        return sbfl_per_test finding (Path A)
    # otherwise (aggregate / per-test-file / per-test-class)
    return sbfl_aggregate finding (Path B)

This file exercises the 3-way routing × {with regression, without
regression} matrix at the engine boundary (not at the per-mode helper
boundary — the helpers have their own dedicated test files).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.derive import derive_localization_findings
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
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


def _summary(n: int = 1) -> CoverageSummary:
    return CoverageSummary(
        num_statements=n,
        covered_statements=n,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


def _seed(
    tmp_path: Path,
    *,
    mapping_granularity: str | None,
    per_test: bool = False,
) -> tuple[object, RunReference]:
    """Materialize a Store with one failing run + optional coverage.

    - ``mapping_granularity=None`` → no coverage facts on disk (Path C).
    - ``mapping_granularity="per-test"`` + ``per_test=True`` → Path A.
    - any other value → Path B.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    # The per-test path actually executes the SBFL pipeline including
    # symbol resolution, so we materialize a real source file when going
    # down Path A to keep the resolver happy.
    if per_test:
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        (workspace / "src" / "foo.py").write_text(
            "def buggy(x):\n    return x + 1\n", encoding="utf-8"
        )
    store = create_project_store(workspace)
    ref = RunReference(run_id="01HDISPATCH000000000000001", created_at=1_700_000_000_000)
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
                node_id="tests/t.py::test_passes",
                outcome="passed",
                duration_ms=1,
            ),
            TestResult(
                node_id="tests/t.py::test_fails",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:2: AssertionError",
            ),
        ),
    )
    store_run_evidence(store, record)
    if mapping_granularity is not None:
        if per_test:
            line_contexts = {
                1: ("tests/t.py::test_passes",),
                2: ("tests/t.py::test_fails",),
            }
        else:
            line_contexts = {}
        cov = CoverageFactSet(
            run_reference=ref,
            engine_name="pytest",
            ecosystem="python",
            mapping_granularity=mapping_granularity,
            summary=_summary(2),
            files=(
                FileCoverage(
                    file_path="src/foo.py",
                    executed_lines=(1, 2),
                    missing_lines=(),
                    excluded_lines=(),
                    executed_branches=(),
                    missing_branches=(),
                    summary=_summary(2),
                    line_contexts=line_contexts,
                ),
            ),
            derived_at=ref.created_at + 500,
        )
        write_coverage_facts(store, cov)
    handle = get_project_store_state(workspace / ".novetest")
    return handle, ref


# ---------------------------------------------------------------------------
# Path A — sbfl_per_test
# ---------------------------------------------------------------------------


def test_per_test_coverage_routes_to_sbfl_per_test(tmp_path: Path) -> None:
    store, ref = _seed(tmp_path, mapping_granularity="per-test", per_test=True)
    result = derive_localization_findings(store, ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_per_test"
    assert result.confidence == "high"


# ---------------------------------------------------------------------------
# Path B — sbfl_aggregate (3 sub-variants for granularity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "granularity",
    ["aggregate", "per-test-file", "per-test-class"],
)
def test_non_per_test_granularity_routes_to_sbfl_aggregate(
    tmp_path: Path, granularity: str
) -> None:
    """Any coverage granularity coarser than per-test → Path B."""
    store, ref = _seed(tmp_path, mapping_granularity=granularity)
    result = derive_localization_findings(store, ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_aggregate"
    assert result.confidence == "medium"


# ---------------------------------------------------------------------------
# Path C — failure_proximity
# ---------------------------------------------------------------------------


def test_no_coverage_routes_to_failure_proximity(tmp_path: Path) -> None:
    """No coverage facts at all → Path C (failure_proximity)."""
    store, ref = _seed(tmp_path, mapping_granularity=None)
    result = derive_localization_findings(store, ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "failure_proximity"
    assert result.confidence == "low"
    # Brief §7 deviation.
    assert result.alternate_scores_available == ()


# ---------------------------------------------------------------------------
# Mode-selection cross-talk guard
# ---------------------------------------------------------------------------


def test_path_a_does_not_route_to_path_b_for_per_test_coverage(
    tmp_path: Path,
) -> None:
    """Regression guard: per-test coverage MUST NOT accidentally hit
    Path B's helper."""
    store, ref = _seed(tmp_path, mapping_granularity="per-test", per_test=True)
    result = derive_localization_findings(store, ref)
    assert isinstance(result, LocalizationFinding)
    # Specifically NOT sbfl_aggregate.
    assert result.mode == "sbfl_per_test"
    assert result.mode != "sbfl_aggregate"
    assert result.mode != "failure_proximity"
