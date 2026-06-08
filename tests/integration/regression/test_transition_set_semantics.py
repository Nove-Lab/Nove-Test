"""Integration tests pinning Regression's transition-detection set semantics.

These tests pin the behavior validated in the 2026-06-08 Q&A slice
(``agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md``):

- Manual Test on 2026-06-01 observed a ``kind: fact-set`` outcome with
  ``summary.regressed == 0 AND summary.fixed == 0`` despite one run
  failing and another passing. The Regression team's verdict — verified
  against decision §3 (closed 9-category taxonomy), decision §C.7
  (consumer filter guidance), and ``compare.py:_build_transitions`` —
  was **INTENT, not bug**.

The binding rule, now pinned in
``design/interace-contract/regression.md`` "Transition Detection
Semantics":

- ``fixed`` / ``regressed`` / ``still_*`` / ``newly_*`` require the
  ``node_id`` to exist on BOTH sides.
- Target-only ``node_id`` → ``added`` (regardless of target outcome).
- Baseline-only ``node_id`` → ``removed`` (regardless of baseline
  outcome).

These integration tests exercise the full ``compare_runs`` engine seam
(Memory + Coverage + Persistence) against the documented contract,
complementing the unit-level ``test_category_*`` cases in
``tests/unit/regression/test_compare.py``.
"""

from __future__ import annotations

from pathlib import Path

from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression import compare_runs


_REF_BASELINE = RunReference(
    run_id="01HBASELINE0000000000000001", created_at=1_700_000_000_000
)
_REF_TARGET = RunReference(
    run_id="01HTARGET00000000000000002", created_at=1_700_000_001_000
)


def _tr(node_id: str, outcome: str, *, duration_ms: int = 10) -> TestResult:
    return TestResult(
        node_id=node_id, outcome=outcome, duration_ms=duration_ms
    )


def _seed_store(
    workspace: Path,
    baseline_results: tuple[TestResult, ...],
    target_results: tuple[TestResult, ...],
    *,
    baseline_status: str = "passed",
    target_status: str = "passed",
) -> Path:
    """Materialize two Run Records sharing ``target_expression="tests/"``.

    Returns the absolute Project Store path so callers can re-resolve a
    handle the way a CLI verb would.
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
        status=baseline_status,
        started_at=_REF_BASELINE.created_at,
        completed_at=_REF_BASELINE.created_at + 1_000,
        test_results=baseline_results,
    )
    target = RunRecord(
        run_reference=_REF_TARGET,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status=target_status,
        started_at=_REF_TARGET.created_at,
        completed_at=_REF_TARGET.created_at + 1_000,
        test_results=target_results,
    )
    store_run_evidence(store, baseline)
    store_run_evidence(store, target)
    return store.path


# --- same-set transitions populate `fixed` / `regressed` --------------------


def test_same_node_id_fail_to_pass_populates_fixed(tmp_path: Path) -> None:
    """Same ``node_id`` on both sides + fail-like → pass-like = ``fixed``.

    Counterpoint to ``test_disjoint_test_sets_yield_empty_fixed_and_regressed``
    below: when the test set overlaps, ``fixed`` populates as expected.
    Pinned at the integration boundary (through ``store_run_evidence`` +
    on-disk persistence) so a future refactor of either Memory or
    Persistence still produces the right answer.
    """
    store_path = _seed_store(
        tmp_path / "ws",
        baseline_results=(_tr("tests/x.py::test_a", "failed", duration_ms=14),),
        target_results=(_tr("tests/x.py::test_a", "passed", duration_ms=9),),
        baseline_status="failed",
    )
    store = get_project_store_state(store_path)
    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)

    assert fact_set.summary.fixed == 1
    assert fact_set.summary.regressed == 0
    assert fact_set.summary.added == 0
    assert fact_set.summary.removed == 0
    assert fact_set.summary.total_baseline_tests == 1
    assert fact_set.summary.total_target_tests == 1

    assert len(fact_set.test_transitions) == 1
    transition = fact_set.test_transitions[0]
    assert transition.node_id == "tests/x.py::test_a"
    assert transition.category == "fixed"
    # Both outcomes preserved as raw native strings.
    assert transition.baseline_outcome == "failed"
    assert transition.target_outcome == "passed"


def test_same_node_id_pass_to_fail_populates_regressed(tmp_path: Path) -> None:
    """Symmetric to the fail→pass case: same-set pass→fail = ``regressed``.

    The two same-set transitions (``regressed``, ``fixed``) are symmetric
    by design; pinning both at the integration boundary guards against a
    one-sided regression in either direction.
    """
    store_path = _seed_store(
        tmp_path / "ws",
        baseline_results=(_tr("tests/x.py::test_a", "passed"),),
        target_results=(_tr("tests/x.py::test_a", "failed"),),
        target_status="failed",
    )
    store = get_project_store_state(store_path)
    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)

    assert fact_set.summary.regressed == 1
    assert fact_set.summary.fixed == 0
    assert fact_set.summary.added == 0
    assert fact_set.summary.removed == 0

    transition = fact_set.test_transitions[0]
    assert transition.category == "regressed"
    assert transition.baseline_outcome == "passed"
    assert transition.target_outcome == "failed"


# --- disjoint sets — the D6 F+ reproducer ----------------------------------


def test_disjoint_test_sets_yield_empty_fixed_and_regressed(
    tmp_path: Path,
) -> None:
    """D6 Scenario F+ reproducer (carry-forward from 2026-06-01 Manual Test).

    Two Run Records over the same ``target_expression``, one failing and
    one passing, but the ``test_results`` ``node_id`` sets are completely
    disjoint. Per the interface contract's Transition Detection
    Semantics:

    - ``summary.regressed`` and ``summary.fixed`` are both ``0`` (neither
      requires the same ``node_id`` on both sides; neither overlaps here).
    - ``summary.added`` reflects the target-only test, regardless of its
      outcome.
    - ``summary.removed`` reflects the baseline-only test, regardless of
      its outcome.

    A consumer reading ``regressed == 0 AND fixed == 0`` MUST NOT
    conclude "nothing changed" — they MUST also read ``added`` and
    ``removed`` per the consumer-guidance section of the contract.
    """
    store_path = _seed_store(
        tmp_path / "ws",
        baseline_results=(_tr("tests/x.py::test_only_in_baseline", "failed"),),
        target_results=(_tr("tests/x.py::test_only_in_target", "passed"),),
        baseline_status="failed",
    )
    store = get_project_store_state(store_path)
    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)

    # The headline finding — neither shared-set bucket populated.
    assert fact_set.summary.fixed == 0
    assert fact_set.summary.regressed == 0
    assert fact_set.summary.still_failing == 0
    assert fact_set.summary.still_passing == 0
    # The signal lives entirely in added + removed.
    assert fact_set.summary.added == 1
    assert fact_set.summary.removed == 1
    # Convenience aggregates count in-both + side-only.
    assert fact_set.summary.total_baseline_tests == 1
    assert fact_set.summary.total_target_tests == 1

    by_id = {t.node_id: t for t in fact_set.test_transitions}
    assert set(by_id.keys()) == {
        "tests/x.py::test_only_in_baseline",
        "tests/x.py::test_only_in_target",
    }

    removed = by_id["tests/x.py::test_only_in_baseline"]
    assert removed.category == "removed"
    assert removed.baseline_outcome == "failed"
    assert removed.target_outcome is None

    added = by_id["tests/x.py::test_only_in_target"]
    assert added.category == "added"
    assert added.baseline_outcome is None
    assert added.target_outcome == "passed"


# --- mixed sets ------------------------------------------------------------


def test_mixed_sets_classify_each_node_id_independently(tmp_path: Path) -> None:
    """One shared transition + one target-only + one baseline-only.

    Exercises the union-walk over node_ids: each node_id is classified
    independently of the others. The shared ``test_shared`` goes through
    the bucket classifier and lands as ``fixed``; the target-only
    ``test_new_failure`` goes through the "target-only" branch and lands
    as ``added`` (with a fail-like target_outcome — the consumer
    "newly-introduced failure" filter case from decision §C.7); the
    baseline-only ``test_gone`` lands as ``removed``.
    """
    store_path = _seed_store(
        tmp_path / "ws",
        baseline_results=(
            _tr("tests/x.py::test_gone", "passed"),
            _tr("tests/x.py::test_shared", "failed"),
        ),
        target_results=(
            _tr("tests/x.py::test_new_failure", "failed"),
            _tr("tests/x.py::test_shared", "passed"),
        ),
        baseline_status="failed",
        target_status="failed",
    )
    store = get_project_store_state(store_path)
    fact_set = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(fact_set, RegressionFactSet)

    assert fact_set.summary.fixed == 1
    assert fact_set.summary.regressed == 0
    assert fact_set.summary.added == 1
    assert fact_set.summary.removed == 1
    # total_baseline_tests = in-both (1) + removed (1) = 2; symmetric for target.
    assert fact_set.summary.total_baseline_tests == 2
    assert fact_set.summary.total_target_tests == 2

    by_id = {t.node_id: t for t in fact_set.test_transitions}
    assert by_id["tests/x.py::test_shared"].category == "fixed"
    assert by_id["tests/x.py::test_new_failure"].category == "added"
    # This is the "newly-introduced failure" surface — consumers wanting
    # the full suspect-universe filter per decision §C.7 union this case
    # with ``regressed`` + ``still_failing``.
    assert by_id["tests/x.py::test_new_failure"].target_outcome == "failed"
    assert by_id["tests/x.py::test_gone"].category == "removed"
    assert by_id["tests/x.py::test_gone"].baseline_outcome == "passed"
