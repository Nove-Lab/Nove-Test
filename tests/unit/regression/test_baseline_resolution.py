"""Unit tests for the baseline-resolution helpers.

Covers ``resolve_latest_baseline``, ``derive_latest_regression``, and
``check_regression_availability`` against a real Project Store seeded via
the same public ``store_run_evidence`` + ``delete_run_evidence`` seams the
``find_runs_for_target`` tests use. No mocking of Memory.

- ``resolve_latest_baseline`` → 7 cases (empty, single, exact-two, reverse
  insertion order, three-runs, tombstoned-middle, mixed-targets).
- ``derive_latest_regression`` → 5 cases (empty, single, all-tombstoned,
  latest-tombstoned-with-live-prior, happy-path).
- ``check_regression_availability`` → 5 cases (unknown, no siblings, one
  sibling, all-siblings-tombstoned, tombstoned-input-with-live-sibling).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import delete_run_evidence
from novetest.models.memory_entry import MemoryEntry
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.compare import (
    derive_latest_regression,
    resolve_latest_baseline,
)
from novetest.regression.results import (
    REASON_NO_COMPARABLE_BASELINE,
    RegressionUnavailable,
)
from novetest.regression.retrieval import check_regression_availability
from novetest.models.regression_fact_set import RegressionFactSet


# Three hand-picked timestamps; chronological order is OLD < MID < NEW so
# tests can write any insertion order and still assert the same result.
_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000


def _ref(run_id: str, created_at: int) -> RunReference:
    return RunReference(run_id=run_id, created_at=created_at)


# --- resolve_latest_baseline -------------------------------------------------


def test_resolve_empty_store_returns_no_comparable_baseline(
    initialized_store: Path,
) -> None:
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/"


def test_resolve_single_match_returns_no_comparable_baseline(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """One run on the target is not a pair — there is no baseline to compare against."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01ALONE", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/"


def test_resolve_exactly_two_runs_returns_older_then_newer(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Decision §2 — return order is (baseline, target) = (older, newer)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLDER", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEWER", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01OLDER"
    assert target_ref.run_id == "01NEWER"


def test_resolve_inserts_in_reverse_order_still_orders_by_created_at(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Memory's newest-first guarantee is load-bearing — we must NOT rely on
    insertion order. Insert NEW first, OLD second; baseline must still be OLD."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEWER", _TS_NEW),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLDER", _TS_OLD),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01OLDER"
    assert target_ref.run_id == "01NEWER"


def test_resolve_three_runs_picks_two_most_recent(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Three runs: oldest is dropped; (baseline, target) = (2nd-latest, latest)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01MID", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01MID"
    assert target_ref.run_id == "01NEW"


def test_resolve_excludes_tombstoned_middle_run(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Decision §C.1 + Memory default — tombstoned candidates are excluded.
    With the middle run tombstoned, (baseline, target) = (oldest live, latest)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    mid_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01MID", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, mid_entry.run_record.run_reference)

    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    # Latest live = 01NEW (target); 2nd-latest live = 01OLD (baseline).
    assert baseline_ref.run_id == "01OLD"
    assert target_ref.run_id == "01NEW"


def test_resolve_mixed_targets_only_considers_matching_expression(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Mixed target_expressions: only the matching expression contributes pairs.
    Two runs on "tests/" + one on "tests/other.py" → resolve picks the "tests/" pair."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01HIT1", _TS_OLD),
        target_expression="tests/",
    )
    # Newest by created_at but on a different target — must NOT be picked.
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OTHER", _TS_NEW),
        target_expression="tests/other.py",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01HIT2", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01HIT1"
    assert target_ref.run_id == "01HIT2"


# --- derive_latest_regression ------------------------------------------------


def test_derive_latest_empty_store_returns_no_runs_detail(
    initialized_store: Path,
) -> None:
    store = get_project_store_state(initialized_store)
    result = derive_latest_regression(store)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "no-runs"


def test_derive_latest_single_run_propagates_resolve_detail(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """With one run, ``resolve_latest_baseline`` returns
    ``RegressionUnavailable(detail=target_expression)``. Decision contract:
    propagate as-is — do NOT overwrite ``detail`` to ``"no-runs"`` (which
    would lose the more useful target hint)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01ALONE", _TS_MID),
        target_expression="tests/foo/",
    )
    store = get_project_store_state(initialized_store)
    result = derive_latest_regression(store)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/foo/"  # not "no-runs"


def test_derive_latest_all_tombstoned_returns_no_runs_detail(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """All-tombstoned store has no live "active target" anchor → no-runs."""
    a = seed_run_record(
        initialized_store,
        run_reference=_ref("01A", _TS_OLD),
        target_expression="tests/",
    )
    b = seed_run_record(
        initialized_store,
        run_reference=_ref("01B", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, a.run_record.run_reference)
    delete_run_evidence(store, b.run_record.run_reference)

    result = derive_latest_regression(store)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "no-runs"


def test_derive_latest_skips_tombstoned_latest_and_uses_live_earlier_target(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """The active target is taken from the latest **non-tombstoned** run.
    A tombstoned latest must not anchor the comparison: two earlier live runs
    on the same target should produce a happy-path RegressionFactSet."""
    # Two live runs on "tests/" plus a tombstoned-latest run on a different
    # target. Active target falls back to the latest live run's target.
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
        test_results=(TestResult(node_id="tests/x.py::a", outcome="passed", duration_ms=5),),
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01MID", _TS_MID),
        target_expression="tests/",
        test_results=(TestResult(node_id="tests/x.py::a", outcome="failed", duration_ms=6),),
    )
    latest = seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/different.py",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, latest.run_record.run_reference)

    result = derive_latest_regression(store)
    assert isinstance(result, RegressionFactSet)
    # The two live runs on "tests/" are the pair; the test_a transition is
    # the pass→fail regression we seeded.
    assert result.baseline_run_reference.run_id == "01OLD"
    assert result.target_run_reference.run_id == "01MID"
    assert result.summary.regressed == 1


def test_derive_latest_happy_path_returns_fact_set(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Two live runs sharing a target → a RegressionFactSet falls out."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
        test_results=(
            TestResult(node_id="tests/x.py::a", outcome="passed", duration_ms=5),
        ),
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
        test_results=(
            TestResult(node_id="tests/x.py::a", outcome="passed", duration_ms=4),
        ),
    )
    store = get_project_store_state(initialized_store)
    result = derive_latest_regression(store)
    assert isinstance(result, RegressionFactSet)
    assert result.baseline_run_reference.run_id == "01OLD"
    assert result.target_run_reference.run_id == "01NEW"
    # One still_passing transition on test_a — proves compose actually fired.
    assert len(result.test_transitions) == 1
    assert result.test_transitions[0].category == "still_passing"


# --- check_regression_availability -------------------------------------------


def test_check_unknown_run_reference_returns_false(
    initialized_store: Path,
) -> None:
    """Missing-tolerant: unknown run_reference is not an error."""
    store = get_project_store_state(initialized_store)
    result = check_regression_availability(
        store, _ref("01UNKNOWN", _TS_MID)
    )
    assert result is False


def test_check_no_siblings_on_same_target_returns_false(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """A single run on its target has no comparable prior."""
    entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01ALONE", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = check_regression_availability(
        store, entry.run_record.run_reference
    )
    assert result is False


def test_check_one_comparable_sibling_returns_true(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """One live sibling on the same target → availability True."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    new_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = check_regression_availability(
        store, new_entry.run_record.run_reference
    )
    assert result is True


def test_check_all_siblings_tombstoned_returns_false(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Siblings excluded by Memory's default (tombstoned) → no comparable prior."""
    old_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    new_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, old_entry.run_record.run_reference)

    result = check_regression_availability(
        store, new_entry.run_record.run_reference
    )
    assert result is False


def test_check_tombstoned_input_with_live_sibling_returns_true(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Tombstone of the input is irrelevant — we measure whether a comparable
    prior exists. A tombstoned input + live sibling on the same target → True."""
    old_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    new_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, new_entry.run_record.run_reference)

    # The input run is now tombstoned but is still resolvable via
    # retrieve_run_evidence (tombstoned records remain readable). The live
    # sibling 01OLD on the same target makes the availability True.
    result = check_regression_availability(
        store, new_entry.run_record.run_reference
    )
    assert result is True
    # Sanity: the live sibling is in fact present.
    assert old_entry.run_record.run_reference.run_id == "01OLD"
