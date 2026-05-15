"""Unit tests for `novetest.coverage.compare`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from novetest.coverage import compare_coverage_facts
from novetest.coverage.compare import (
    CoverageDelta,
    FileCoverageDelta,
)
from novetest.coverage.persistence import write_coverage_facts
from novetest.coverage.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_NOT_FOUND,
    CoverageUnavailable,
)
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


def _make_summary(
    num_statements: int = 10,
    covered_statements: int = 8,
    missing_statements: int = 2,
    num_branches: int = 2,
    covered_branches: int = 1,
    missing_branches: int = 1,
    percent_covered: float = 80.0,
) -> CoverageSummary:
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=missing_statements,
        excluded_statements=0,
        num_branches=num_branches,
        covered_branches=covered_branches,
        missing_branches=missing_branches,
        percent_covered=percent_covered,
    )


def _make_file(
    path: str,
    executed: tuple[int, ...] = (1, 2, 3),
    missing: tuple[int, ...] = (4,),
    executed_branches: tuple[tuple[int, int], ...] = ((1, 2),),
    missing_branches: tuple[tuple[int, int], ...] = ((1, 4),),
) -> FileCoverage:
    return FileCoverage(
        file_path=path,
        executed_lines=executed,
        missing_lines=missing,
        excluded_lines=(),
        executed_branches=executed_branches,
        missing_branches=missing_branches,
        summary=_make_summary(),
    )


def _make_fact_set(
    run_id: str,
    files: tuple[FileCoverage, ...],
    summary: CoverageSummary | None = None,
    granularity: str = "per-test",
) -> CoverageFactSet:
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=1_700_000_000_000),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity=granularity,
        summary=summary or _make_summary(),
        files=files,
        derived_at=1_700_000_001_000,
    )


# --- delta entity ------------------------------------------------------------


def test_file_delta_round_trip() -> None:
    delta = FileCoverageDelta(
        file_path="src/x.py",
        newly_covered_lines=(5, 6),
        newly_uncovered_lines=(3,),
        newly_covered_branches=((5, 6),),
        newly_uncovered_branches=((3, 4),),
        summary_before=_make_summary(),
        summary_after=_make_summary(covered_statements=9, missing_statements=1,
                                     percent_covered=90.0),
    )
    assert FileCoverageDelta.from_dict(delta.to_dict()) == delta


def test_coverage_delta_round_trip() -> None:
    delta = CoverageDelta(
        baseline_run_reference=RunReference(run_id="A", created_at=1),
        target_run_reference=RunReference(run_id="B", created_at=2),
        baseline_granularity="per-test",
        target_granularity="per-test",
        summary_before=_make_summary(),
        summary_after=_make_summary(percent_covered=90.0),
        files_added=("src/new.py",),
        files_removed=("src/old.py",),
        file_deltas=(
            FileCoverageDelta(
                file_path="src/x.py",
                newly_covered_lines=(5,),
                newly_uncovered_lines=(),
                newly_covered_branches=(),
                newly_uncovered_branches=(),
                summary_before=_make_summary(),
                summary_after=_make_summary(),
            ),
        ),
    )
    assert CoverageDelta.from_dict(delta.to_dict()) == delta


# --- compare_coverage_facts behaviour ---------------------------------------


def test_compare_identifies_newly_covered_and_uncovered_lines(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    baseline = _make_fact_set(
        "01HBASE",
        files=(_make_file("src/x.py", executed=(1, 2), missing=(3, 4)),),
    )
    target = _make_fact_set(
        "01HTRGT",
        files=(_make_file("src/x.py", executed=(1, 3), missing=(2, 4)),),
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert len(result.file_deltas) == 1
    delta = result.file_deltas[0]
    assert delta.file_path == "src/x.py"
    assert delta.newly_covered_lines == (3,)
    assert delta.newly_uncovered_lines == (2,)


def test_compare_identifies_newly_covered_branches(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    baseline = _make_fact_set(
        "01HBASE",
        files=(
            _make_file(
                "src/x.py",
                executed_branches=((1, 2),),
                missing_branches=((1, 3),),
            ),
        ),
    )
    target = _make_fact_set(
        "01HTRGT",
        files=(
            _make_file(
                "src/x.py",
                executed_branches=((1, 2), (1, 3)),
                missing_branches=(),
            ),
        ),
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.file_deltas[0].newly_covered_branches == ((1, 3),)
    assert result.file_deltas[0].newly_uncovered_branches == ()


def test_compare_identifies_added_and_removed_files(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    baseline = _make_fact_set(
        "01HBASE",
        files=(_make_file("src/old.py"), _make_file("src/keep.py")),
    )
    target = _make_fact_set(
        "01HTRGT",
        files=(_make_file("src/keep.py"), _make_file("src/new.py")),
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.files_added == ("src/new.py",)
    assert result.files_removed == ("src/old.py",)


def test_compare_omits_files_with_no_transition(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    """Identical files (same executed lines/branches) produce no delta entry,
    keeping the on-the-wire payload compact."""
    same = _make_file("src/keep.py")
    baseline = _make_fact_set("01HBASE", files=(same,))
    # Same lines + branches in target — no transition.
    target = _make_fact_set("01HTRGT", files=(same,))
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.file_deltas == ()


def test_compare_carries_both_granularities(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    baseline = _make_fact_set("01HBASE", files=(_make_file("src/x.py"),),
                              granularity="per-test")
    target = _make_fact_set("01HTRGT", files=(_make_file("src/x.py"),),
                            granularity="aggregate")
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.baseline_granularity == "per-test"
    assert result.target_granularity == "aggregate"


def test_compare_baseline_unavailable_propagates(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    target = _make_fact_set("01HTRGT", files=(_make_file("src/x.py"),))
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)
    baseline_ref = RunReference(run_id="01HMISS", created_at=1_700_000_000_000)

    result = compare_coverage_facts(
        store, baseline_ref, target.run_reference
    )
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND


def test_compare_target_unavailable_propagates(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
    make_run_record: Callable[..., RunRecord],
) -> None:
    baseline = _make_fact_set("01HBASE", files=(_make_file("src/x.py"),))
    seed_fact_set(initialized_store, baseline)
    store = get_project_store_state(initialized_store)
    # Seed the run record for target but no derived facts.
    target_ref = RunReference(run_id="01HBARE", created_at=1_700_000_000_000)
    store_run_evidence(store, make_run_record(run_reference=target_ref))

    result = compare_coverage_facts(
        store, baseline.run_reference, target_ref
    )
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS


def test_compare_carries_summary_before_and_after(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    baseline_summary = _make_summary(
        num_statements=10, covered_statements=5, missing_statements=5,
        percent_covered=50.0,
    )
    target_summary = _make_summary(
        num_statements=10, covered_statements=9, missing_statements=1,
        percent_covered=90.0,
    )
    baseline = _make_fact_set(
        "01HBASE", files=(_make_file("src/x.py"),), summary=baseline_summary,
    )
    target = _make_fact_set(
        "01HTRGT", files=(_make_file("src/x.py"),), summary=target_summary,
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.summary_before.percent_covered == 50.0
    assert result.summary_after.percent_covered == 90.0
