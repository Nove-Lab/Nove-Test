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
    REASON_ENGINE_MISMATCH,
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
    engine_name: str = "pytest",
    ecosystem: str = "python",
) -> CoverageFactSet:
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=1_700_000_000_000),
        engine_name=engine_name,
        ecosystem=ecosystem,
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


def test_compare_refuses_cross_engine_pair(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    """Mixed-engine pair → ``CoverageUnavailable(REASON_ENGINE_MISMATCH)``.

    D5 guard (decision 2026-07-03-engine-selection-policy §D5, Finding A
    of the D5 cross-run audit): a pytest fact set diffed against a
    cargo-test fact set must be refused, not silently reduced to file-set
    noise. Mirrors Regression's ``compare_runs`` guard: same wire string
    ("engine-mismatch"), same detail shape carrying BOTH engine names.
    """
    baseline = _make_fact_set(
        "01HBASE",
        files=(_make_file("src/x.py"),),
        engine_name="pytest",
        ecosystem="python",
    )
    target = _make_fact_set(
        "01HTRGT",
        files=(_make_file("src/lib.rs"),),
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_ENGINE_MISMATCH
    # Detail carries both names so consumers don't need a second lookup.
    assert result.detail is not None
    assert "pytest" in result.detail
    assert "cargo-test" in result.detail
    # Pair-level reason names the baseline side (2026-05-16 envelope
    # decision binding constraint #4 tie-break, extended by the 2026-07-03
    # amendment).
    assert result.run_reference == baseline.run_reference


def test_compare_engine_mismatch_reason_is_symmetric(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    """Swapping the sides still refuses the pair; the named run_reference
    follows the (new) baseline side, and the detail order follows the
    argument order."""
    pytest_side = _make_fact_set(
        "01HPYT",
        files=(_make_file("src/x.py"),),
        engine_name="pytest",
        ecosystem="python",
    )
    cargo_side = _make_fact_set(
        "01HCRG",
        files=(_make_file("src/lib.rs"),),
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_fact_set(initialized_store, pytest_side)
    seed_fact_set(initialized_store, cargo_side)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, cargo_side.run_reference, pytest_side.run_reference
    )
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_ENGINE_MISMATCH
    assert result.detail is not None
    assert result.detail.index("cargo-test") < result.detail.index("pytest")
    assert result.run_reference == cargo_side.run_reference


def test_compare_same_engine_non_pytest_pair_still_produces_delta(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    """The guard keys on INEQUALITY, not on any privileged engine name —
    a cargo-test vs cargo-test pair passes through to the normal delta
    path unchanged.

    Note on the Regression-side embed (task item 4): this new reason is
    unreachable through ``regression/compare.py::_maybe_coverage_change``
    — ``compare_runs`` refuses cross-engine pairs with its OWN
    ``REASON_ENGINE_MISMATCH`` guard (regression/compare.py:178-183)
    BEFORE the coverage embed runs, and even if it were reachable the
    embed folds ANY ``CoverageUnavailable`` into ``coverage_change =
    None``. No Regression-side behavior change in this slice.
    """
    baseline = _make_fact_set(
        "01HBASE",
        files=(_make_file("src/lib.rs", executed=(1, 2), missing=(3,)),),
        engine_name="cargo-test",
        ecosystem="rust",
    )
    target = _make_fact_set(
        "01HTRGT",
        files=(_make_file("src/lib.rs", executed=(1, 2, 3), missing=()),),
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_fact_set(initialized_store, baseline)
    seed_fact_set(initialized_store, target)
    store = get_project_store_state(initialized_store)

    result = compare_coverage_facts(
        store, baseline.run_reference, target.run_reference
    )
    assert isinstance(result, CoverageDelta)
    assert result.file_deltas[0].newly_covered_lines == (3,)


def test_compare_engine_guard_fires_after_availability_checks(
    initialized_store: Path,
    seed_fact_set: Callable[..., None],
) -> None:
    """Ordering pin: a missing side still surfaces its OWN unavailability
    reason (run-not-found / missing-derived-facts), NOT engine-mismatch —
    the guard only fires once both fact sets resolved. Keeps the
    2026-05-16 decision's constraint #4 semantics intact for the
    single-side-missing case."""
    baseline = _make_fact_set(
        "01HBASE",
        files=(_make_file("src/x.py"),),
        engine_name="pytest",
    )
    seed_fact_set(initialized_store, baseline)
    store = get_project_store_state(initialized_store)
    missing_ref = RunReference(run_id="01HMISS", created_at=1_700_000_000_000)

    result = compare_coverage_facts(store, baseline.run_reference, missing_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND


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
