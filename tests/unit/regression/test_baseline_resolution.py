"""Unit tests for the baseline-resolution helpers.

Covers ``resolve_baseline_for_run``, ``resolve_latest_baseline``,
``derive_latest_regression``, and ``check_regression_availability`` against
a real Project Store seeded via the same public ``store_run_evidence`` +
``delete_run_evidence`` seams the ``find_runs_for_target`` tests use. No
mocking of Memory — with ONE deliberate exception: the XCT-07
order-independence cases monkeypatch ``find_runs_for_target`` in the
``compare`` namespace, because proving order-independence requires
presenting adversarial candidate orderings a real (sorted) store cannot
yield.

- ``resolve_latest_baseline`` → 7 pure-series cases (empty, single,
  exact-two, reverse insertion order, three-runs, tombstoned-middle,
  mixed-targets) — this block is the "pure series behavior unchanged"
  snapshot for the D5 engine-scoping slice — plus 3 mixed-engine cases.
- ``resolve_baseline_for_run`` → 3 direct cases (skip newer + cross-engine,
  only-cross-engine priors, tombstoned same-engine prior).
- ``derive_latest_regression`` → 5 cases (empty, single, all-tombstoned,
  latest-tombstoned-with-live-prior, happy-path) + 1 mixed-engine case.
- ``check_regression_availability`` → 5 cases (unknown, no siblings, one
  sibling, all-siblings-tombstoned, tombstoned-input-with-live-sibling)
  + 2 engine-scoping cases.
- XCT-07 / ANA-25 / ANA-26 (W2/S36) → 9 cases: composite-key
  ``(created_at, run_id)`` tie-break (same-ms siblings orderable, pick =
  closest predecessor, order-independent + repeated-run stable), honest
  ``no-comparable-baseline`` detail (engine hint only when D5 filtering
  actually excluded candidates), and probe/resolver parity.
- W2-S37 rider (S36-close) → 2 cases: empty ``target_expression`` (bare
  ``novetest test``) renders the ``(entire workspace)`` placeholder in the
  ``no-comparable-baseline`` detail, plain and engine-hinted forms.

Engine scoping is D5 of
``agent-comms/decisions/2026-07-03-engine-selection-policy.md``: baseline /
candidate selection for cross-run analyses filters by the target run's
``engine_name``; mixed-engine histories are legitimate (D3 transient
``--engine`` override) and must resolve to the nearest same-engine prior.

Ordering convention (pinned verbatim in the W2/S36 task briefs, shared
with Memory's storage-side sort tiebreak): total order on runs =
lexicographic on the composite key ``(created_at, run_id)``; newest-first
= descending on both components; "strictly older than target" =
``(created_at, run_id) < (target.created_at, target.run_id)``; ``run_id``
is a ULID string and plain string comparison is the tie component.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import permutations
from pathlib import Path

import pytest

from novetest.memory.project_store import ProjectStore, get_project_store_state
from novetest.memory.store import delete_run_evidence
from novetest.models.memory_entry import MemoryEntry
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.compare import (
    derive_latest_regression,
    resolve_baseline_for_run,
    resolve_latest_baseline,
)
from novetest.regression.results import (
    REASON_NO_COMPARABLE_BASELINE,
    RegressionUnavailable,
)
from novetest.regression.retrieval import check_regression_availability
from novetest.models.regression_fact_set import RegressionFactSet


# Four hand-picked timestamps; chronological order is OLD < MID < NEW <
# NEWEST so tests can write any insertion order and still assert the same
# result.
_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000
_TS_NEWEST = 1_700_000_003_000


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


# --- resolve_latest_baseline: D5 engine scoping --------------------------------
#
# Mixed-engine histories on ONE target are legitimate (decision D3 transient
# --engine override). D5's binding rule: the baseline must share the target
# run's engine_name; the target itself stays the newest live run regardless
# of engine.


def test_resolve_mixed_engine_series_picks_same_engine_baseline(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Series [pytest, cargo-test, pytest]: the newest pytest run resolves
    the OLDER pytest run as baseline, skipping the cargo-test run in
    between (pre-D5 this reported unavailable via the guaranteed
    ``REASON_ENGINE_MISMATCH`` neighbor). The task's headline acceptance
    case."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01PYOLD"
    assert target_ref.run_id == "01PYNEW"


def test_resolve_target_selection_is_engine_agnostic(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Series [pytest, pytest, cargo-test]: the TARGET is the newest live
    run regardless of engine (the cargo-test run), and since no cargo-test
    prior exists the result is unavailable — with the engine carried in
    ``detail`` so the operator sees the D5 filter (not run scarcity)
    eliminated the two pytest candidates."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYMID", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_NEW),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/ (engine=cargo-test)"


def test_resolve_single_run_per_engine_returns_engine_detail(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Series [cargo-test, pytest] (one run each): the pytest target has no
    pytest prior → unavailable with the engine-suffixed detail. The plain
    ``detail=target_expression`` form stays reserved for the
    fewer-than-two-runs case (see the pure-series tests above)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_OLD),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/ (engine=pytest)"


# --- resolve_baseline_for_run (the shared D5 selector) -------------------------


def test_baseline_for_run_skips_newer_and_cross_engine_siblings(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Input = the MIDDLE pytest run of [pytest, cargo-test, pytest(input),
    pytest(newer)]: the selector must skip the newer pytest run (not
    strictly older) AND the cargo-test run (cross-engine), landing on the
    oldest pytest run."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    input_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYMID", _TS_NEW),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEWEST", _TS_NEWEST),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_baseline_for_run(store, input_entry)
    assert result is not None
    assert result.run_id == "01PYOLD"


def test_baseline_for_run_returns_none_when_only_cross_engine_priors(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """All strictly-older siblings run a different engine → ``None`` (the
    caller surfaces it as unavailable / False)."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO1", _TS_OLD),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO2", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    input_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    assert resolve_baseline_for_run(store, input_entry) is None


def test_baseline_for_run_skips_tombstoned_same_engine_prior(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """A tombstoned same-engine prior is excluded (Memory's
    ``include_tombstoned=False`` convention); the next-older live
    same-engine run wins."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
    )
    mid_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYMID", _TS_MID),
        target_expression="tests/",
    )
    input_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, mid_entry.run_record.run_reference)

    result = resolve_baseline_for_run(store, input_entry)
    assert result is not None
    assert result.run_id == "01PYOLD"


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


def test_derive_latest_mixed_engine_series_produces_facts(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """D5 acceptance case end-to-end: series [pytest(fail), cargo-test,
    pytest(pass)] on one target — ``derive_latest_regression`` resolves the
    same-engine pair AND produces a fact set (the pair clears
    ``compare_runs``' engine guard by construction). Pre-D5 this returned
    ``REASON_NO_COMPARABLE_BASELINE``-adjacent noise: the resolver picked
    the cargo-test neighbor and ``compare_runs`` refused it."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
        test_results=(
            TestResult(node_id="tests/x.py::a", outcome="failed", duration_ms=7),
        ),
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
        test_results=(
            TestResult(node_id="tests::rust_case", outcome="passed", duration_ms=3),
        ),
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
        test_results=(
            TestResult(node_id="tests/x.py::a", outcome="passed", duration_ms=6),
        ),
    )
    store = get_project_store_state(initialized_store)
    result = derive_latest_regression(store)
    assert isinstance(result, RegressionFactSet)
    assert result.baseline_run_reference.run_id == "01PYOLD"
    assert result.target_run_reference.run_id == "01PYNEW"
    assert result.baseline_engine_name == "pytest"
    assert result.target_engine_name == "pytest"
    assert result.summary.fixed == 1


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


def test_check_only_cross_engine_sibling_returns_false(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """D5: a sibling produced by a different engine is NOT a comparable
    prior — counting it would report "available" for a comparison
    ``compare_runs`` is guaranteed to refuse."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_OLD),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    new_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = check_regression_availability(
        store, new_entry.run_record.run_reference
    )
    assert result is False


def test_check_same_engine_sibling_among_cross_engine_noise_returns_true(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """D5: one same-engine sibling among cross-engine noise flips
    availability True — mirrors the [pytest, cargo-test, pytest] resolver
    case."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01PYOLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01CARGO", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    new_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01PYNEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = check_regression_availability(
        store, new_entry.run_record.run_reference
    )
    assert result is True


# --- XCT-07 / ANA-25 / ANA-26: composite-key tie-break, honest detail, parity --
#
# Same-millisecond sibling runs are real (tight rerun loops — replay's
# engine mints ULIDs back-to-back). The selector's order is the composite
# key ``(created_at, run_id)``; the pick is the maximum key strictly below
# the target's (the closest predecessor), computed by an order-independent
# max-scan. Where a test needs a SPECIFIC candidate ordering (adversarial
# shuffles, or a pinned newest-first head for ``resolve_latest_baseline``
# among ties), it monkeypatches ``find_runs_for_target`` in the ``compare``
# namespace instead of relying on filesystem enumeration order.


def _fake_find_runs_factory(
    presented: list[MemoryEntry],
) -> Callable[..., list[MemoryEntry]]:
    """Build a ``find_runs_for_target`` stand-in replaying ``presented``.

    Mutate ``presented`` in place between calls to change the ordering the
    selector sees. Signature mirrors the real seam (extra keywords accepted
    and ignored).
    """

    def _fake(
        _store: ProjectStore,
        _target_expression: str,
        *,
        include_tombstoned: bool = False,
        skipped: object = None,
    ) -> list[MemoryEntry]:
        return list(presented)

    return _fake


def test_baseline_for_run_same_ms_smaller_run_id_is_comparable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """ANA-25 A/B honesty proof (predicate half): a sibling sharing the
    target's ``created_at`` with a smaller ``run_id`` IS strictly older and
    becomes the baseline. Pre-fix, the ``created_at >=`` skip made same-ms
    siblings never comparable — reverting the predicate fails this test.
    No ordering monkeypatch needed: the max-scan is order-independent."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    target_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_baseline_for_run(store, target_entry)
    assert result is not None
    assert result.run_id == "01TIEA"


def test_baseline_for_run_same_ms_larger_run_id_is_not_comparable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """The tie-break is a strict total order, not "any same-ms sibling":
    probing the SMALLER-``run_id`` side of the tie finds nothing strictly
    older, so no baseline resolves."""
    target_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    assert resolve_baseline_for_run(store, target_entry) is None


def test_baseline_for_run_tie_pick_is_order_independent(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tie-break determinism (the brief's headline case): same
    ``created_at``, differing ``run_id``s, every candidate ordering (all 24
    permutations), twice over → the identical pick each time: the closest
    predecessor by composite key. Candidates for target ``(MID, 01TIEZ)``
    are ``(OLD, 01AOLD)`` < ``(MID, 01TIEA)`` < ``(MID, 01TIEB)`` — the
    pick is ``01TIEB``, never the older-ms run and never input-order
    dependent."""
    older = seed_run_record(
        initialized_store,
        run_reference=_ref("01AOLD", _TS_OLD),
        target_expression="tests/",
    )
    tie_a = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    tie_b = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    target_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEZ", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)

    presented: list[MemoryEntry] = []
    monkeypatch.setattr(
        "novetest.regression.compare.find_runs_for_target",
        _fake_find_runs_factory(presented),
    )
    entries = [older, tie_a, tie_b, target_entry]
    for _ in range(2):  # repeated-run stability
        for perm in permutations(entries):
            presented[:] = perm
            result = resolve_baseline_for_run(store, target_entry)
            assert result is not None
            assert result.run_id == "01TIEB"


def test_resolve_latest_two_same_ms_runs_now_compare(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ANA-25 A/B honesty proof (resolver half): two live same-ms siblings
    on one target now yield a valid ``(baseline, target)`` pair. Pre-fix
    this exact shape refused with ``no-comparable-baseline`` AND blamed the
    engine filter in ``detail``. The head is pinned newest-first by
    composite key via the monkeypatched source — the storage-side ordering
    tiebreak ships in the parallel S36 memory slice, so this test must not
    depend on filesystem enumeration order."""
    tie_a = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    tie_b = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    monkeypatch.setattr(
        "novetest.regression.compare.find_runs_for_target",
        _fake_find_runs_factory([tie_b, tie_a]),  # newest-first
    )
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, tuple)
    baseline_ref, target_ref = result
    assert baseline_ref.run_id == "01TIEA"
    assert target_ref.run_id == "01TIEB"


def test_resolve_latest_same_ms_tie_on_real_store_is_deterministic(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Real-store determinism, no ordering monkeypatch: series [tie, tie,
    newer] — the head is unambiguous (unique newest ms) and the same-ms
    pair sits among the candidates. Whatever order the store enumerates
    the tie, the baseline is the composite-key maximum below the target
    (``01TIEB``), stable across repeated resolution."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEWER", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    for _ in range(2):
        result = resolve_latest_baseline(store, "tests/")
        assert isinstance(result, tuple)
        baseline_ref, target_ref = result
        assert baseline_ref.run_id == "01TIEB"
        assert target_ref.run_id == "01NEWER"


def test_resolve_latest_no_strictly_older_sibling_detail_has_no_engine_hint(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ANA-25 detail honesty (negative case): the head entry has a live
    sibling but none strictly older (same-ms with a LARGER ``run_id`` —
    reachable only while the presented ordering drifts from the
    composite-key convention) → plain ``detail=target_expression``.
    Pre-fix this path emitted the misleading ``(engine=...)`` suffix even
    though D5 filtering never excluded anything — there was nothing to
    filter."""
    tie_a = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    tie_b = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    monkeypatch.setattr(
        "novetest.regression.compare.find_runs_for_target",
        _fake_find_runs_factory([tie_a, tie_b]),  # head = smaller run_id
    )
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/"
    assert "(engine=" not in (result.detail or "")


def test_resolve_latest_same_ms_cross_engine_prior_keeps_engine_detail(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ANA-25 detail honesty (positive case): a strictly-older sibling
    exists (same-ms, smaller ``run_id``) but is cross-engine — the D5
    filter genuinely eliminated it, so the ``(engine=...)`` hint stays."""
    cargo = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    target = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    monkeypatch.setattr(
        "novetest.regression.compare.find_runs_for_target",
        _fake_find_runs_factory([target, cargo]),  # newest-first
    )
    result = resolve_latest_baseline(store, "tests/")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "tests/ (engine=pytest)"


def test_check_oldest_run_with_newer_sibling_returns_false(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """ANA-26 A/B divergence proof: the OLDEST run of a series has no
    strictly-older sibling, so the probe must say ``False`` — in lockstep
    with the resolver. The pre-fix any-sibling probe answered ``True``
    here while derivation was guaranteed to refuse with
    ``no-comparable-baseline`` (the false-positive ANA-26 documents);
    reverting the delegation fails this test."""
    old_entry = seed_run_record(
        initialized_store,
        run_reference=_ref("01OLD", _TS_OLD),
        target_expression="tests/",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01NEW", _TS_NEW),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    probe = check_regression_availability(
        store, old_entry.run_record.run_reference
    )
    assert probe is False
    # Parity: the probe's verdict IS the resolver's verdict.
    assert resolve_baseline_for_run(store, old_entry) is None


def test_check_same_ms_tie_parity_matches_resolver_both_directions(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Probe ⟺ resolver on the tie itself: the larger-``run_id`` side of a
    same-ms pair has a baseline (``True``), the smaller side does not
    (``False``) — and each probe answer equals
    ``resolve_baseline_for_run(...) is not None`` for the same entry."""
    tie_a = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEA", _TS_MID),
        target_expression="tests/",
    )
    tie_b = seed_run_record(
        initialized_store,
        run_reference=_ref("01TIEB", _TS_MID),
        target_expression="tests/",
    )
    store = get_project_store_state(initialized_store)
    for entry, expected in ((tie_b, True), (tie_a, False)):
        probe = check_regression_availability(
            store, entry.run_record.run_reference
        )
        assert probe is expected
        assert probe is (resolve_baseline_for_run(store, entry) is not None)


# --- W2-S37 rider (S36-close): empty target expression placeholder detail ----


def test_resolve_latest_empty_target_renders_placeholder_detail(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """A bare ``novetest test`` records ``target_expression=""``; the
    ``no-comparable-baseline`` refusal must render the pinned
    ``(entire workspace)`` placeholder, not an unreadable ``detail: ""``."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01BARE", _TS_MID),
        target_expression="",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "(entire workspace)"


def test_resolve_latest_empty_target_placeholder_keeps_engine_hint(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """The placeholder composes with the ANA-25 D5 engine hint: an empty
    expression whose only strictly-older sibling is cross-engine renders
    ``(entire workspace) (engine=<name>)`` — never a leading bare space."""
    seed_run_record(
        initialized_store,
        run_reference=_ref("01BAREA", _TS_OLD),
        target_expression="",
        engine_name="cargo-test",
        ecosystem="rust",
    )
    seed_run_record(
        initialized_store,
        run_reference=_ref("01BAREB", _TS_MID),
        target_expression="",
    )
    store = get_project_store_state(initialized_store)
    result = resolve_latest_baseline(store, "")
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_NO_COMPARABLE_BASELINE
    assert result.detail == "(entire workspace) (engine=pytest)"
