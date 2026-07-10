"""``get_localization_findings`` + ``check_localization_availability`` unit tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from novetest.localization.persistence import write_localization_findings
from novetest.localization.results import (
    REASON_MISSING_DERIVED_FACTS,
    LocalizationUnavailable,
)
from novetest.localization.retrieval import (
    check_localization_availability,
    get_localization_findings,
)
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.models.coverage_fact_set import CoverageFactSet, FileCoverage
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


def _finding(ref: RunReference) -> LocalizationFinding:
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("dstar2", "op2", "tarantula"),
        top_n=10,
        entries=(),
        derived_at=ref.created_at + 500,
    )


# --- get_localization_findings ----------------------------------------------


def test_get_cache_present_returns_finding(
    tmp_path: Path, default_ref: RunReference
) -> None:
    store = create_project_store(tmp_path)
    write_localization_findings(store, _finding(default_ref))
    result = get_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.run_reference == default_ref


def test_get_cache_absent_returns_unavailable(
    tmp_path: Path, default_ref: RunReference
) -> None:
    """Per decision §X split: cache-empty → ``missing-derived-facts``
    (recoverable: caller should derive). ``run-not-analyzable`` is
    reserved for structurally non-derivable runs (e.g. tombstoned)."""
    store = create_project_store(tmp_path)
    result = get_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
    assert result.detail == "findings not yet derived"
    # ``run_reference`` is populated on the cache-empty path so the caller
    # can identify which run needs deriving.
    assert result.run_reference == default_ref


# --- check_localization_availability ----------------------------------------


def test_availability_unknown_run_returns_false(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    unknown = RunReference(
        run_id="01HUNKNOWN0000000000000000", created_at=1_700_000_000_000
    )
    assert check_localization_availability(store, unknown) is False


def test_availability_no_failed_tests_returns_false(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="passed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ("tests/a.py::t",)}),),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    assert check_localization_availability(store, default_ref) is False


def test_availability_no_coverage_returns_true_post_defect4(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Defect 4 (2026-06-01) relaxed the gate so coverage-less runs are
    analyzable via the ``failure_proximity`` mode dispatcher path.

    Pre-2026-06-01 this returned ``False`` (the gate rejected anything
    without per-test coverage). Per ``history/2026-06-01-localization-
    phase4-modes-and-cargo-defect-cascade.md`` §"Defect 4" the gate now
    matches the 3-mode dispatch in ``derive_localization_findings``:
    a non-tombstoned entry with at least one failed test is analyzable
    regardless of coverage shape."""
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    seed_store(workspace, record=record, coverage=None)
    store = get_project_store_state(workspace / ".novetest")
    assert check_localization_availability(store, default_ref) is True


def test_availability_aggregate_coverage_returns_true_post_defect4(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Defect 4 (2026-06-01) relaxed the gate so aggregate-granularity
    runs are analyzable via the ``sbfl_aggregate`` mode dispatcher path.

    Pre-2026-06-01 this returned ``False`` (the gate accepted only
    ``mapping_granularity == "per-test"``), which made
    ``novetest localization latest`` return ``run-not-analyzable`` for
    cargo / go / jest runs. Per ``history/2026-06-01-localization-
    phase4-modes-and-cargo-defect-cascade.md`` §"Defect 4" the gate
    now matches the dispatcher's contract."""
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ("tests/a.py::t",)}),),
        mapping_granularity="aggregate",
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    assert check_localization_availability(store, default_ref) is True


def test_availability_tombstoned_returns_false(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ("tests/a.py::t",)}),),
    )
    seed_store(workspace, record=record, coverage=coverage, tombstone=True)
    store = get_project_store_state(workspace / ".novetest")
    assert check_localization_availability(store, default_ref) is False


def test_availability_all_preconditions_satisfied_returns_true(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ("tests/a.py::t",)}),),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    assert check_localization_availability(store, default_ref) is True
