"""End-to-end integration tests for D5 engine-scoped baseline resolution.

Pinned decision: ``agent-comms/decisions/2026-07-03-engine-selection-policy.md``
D5 — baseline/candidate selection for cross-run analyses filters by the
target run's ``engine_name``; mixed-engine histories on one target are
legitimate (D3 transient ``--engine`` override) and must resolve to the
nearest same-engine prior instead of reporting unavailable.

Every test seeds the canonical mixed series [pytest, cargo-test, pytest]
into a REAL Project Store via ``store_run_evidence`` (no mocking), then
exercises the full composition each consumer actually runs:

- ``derive_latest_regression`` — the ``regression latest`` path;
- ``build_inspect_view``      — the ``inspect <run_id>`` Regression section;
- ``build_status_view``       — the ``status`` regression availability flag.

Pre-D5, all three paths hand-picked the adjacent (cargo-test) neighbor and
reported unavailable (``REASON_ENGINE_MISMATCH`` via ``compare_runs``, or a
never-written pair cache); these tests pin the post-D5 behavior end to end.
"""

from __future__ import annotations

from pathlib import Path

from novetest.memory.project_store import (
    ProjectStore,
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.orchestration.workflows.inspect import build_inspect_view
from novetest.orchestration.workflows.status import build_status_view
from novetest.regression import derive_latest_regression


_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000

_PY_OLD_ID = "01PYOLD00000000000000000001"
_CARGO_ID = "01CARGO00000000000000000002"
_PY_NEW_ID = "01PYNEW00000000000000000003"


def _record(
    *,
    run_id: str,
    created_at: int,
    engine_name: str = "pytest",
    ecosystem: str = "python",
    test_results: tuple[TestResult, ...],
) -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=created_at),
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        engine_version=None,
        ecosystem=ecosystem,
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1_000,
        test_results=test_results,
    )


def _seed_mixed_engine_store(tmp_path: Path) -> ProjectStore:
    """Seed [pytest(fail), cargo-test, pytest(pass)] on one target.

    The pytest pair carries a real fail→pass transition on the same
    ``node_id`` so a correctly-resolved comparison yields ``fixed == 1`` —
    distinguishable from any accidental pairing.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    store_run_evidence(
        store,
        _record(
            run_id=_PY_OLD_ID,
            created_at=_TS_OLD,
            test_results=(
                TestResult(
                    node_id="tests/x.py::test_a", outcome="failed", duration_ms=9
                ),
            ),
        ),
    )
    store_run_evidence(
        store,
        _record(
            run_id=_CARGO_ID,
            created_at=_TS_MID,
            engine_name="cargo-test",
            ecosystem="rust",
            test_results=(
                TestResult(
                    node_id="tests::rust_case", outcome="passed", duration_ms=3
                ),
            ),
        ),
    )
    store_run_evidence(
        store,
        _record(
            run_id=_PY_NEW_ID,
            created_at=_TS_NEW,
            test_results=(
                TestResult(
                    node_id="tests/x.py::test_a", outcome="passed", duration_ms=8
                ),
            ),
        ),
    )
    return get_project_store_state(store.path)


def test_derive_latest_resolves_same_engine_pair_in_mixed_store(
    tmp_path: Path,
) -> None:
    """``regression latest`` composition: the newest pytest run compares
    against the older pytest run — the cargo-test run in between is
    skipped, and real facts land (``fixed == 1``)."""
    store = _seed_mixed_engine_store(tmp_path)
    result = derive_latest_regression(store)
    assert isinstance(result, RegressionFactSet)
    assert result.baseline_run_reference.run_id == _PY_OLD_ID
    assert result.target_run_reference.run_id == _PY_NEW_ID
    assert result.baseline_engine_name == "pytest"
    assert result.target_engine_name == "pytest"
    assert result.summary.fixed == 1


def test_inspect_view_composes_engine_scoped_baseline(tmp_path: Path) -> None:
    """``inspect <newest pytest run>``: the Regression section is a
    fact-set against the same-engine prior — NOT the pre-D5
    ``engine-mismatch`` unavailable against the adjacent cargo-test run."""
    store = _seed_mixed_engine_store(tmp_path)
    view = build_inspect_view(store, _PY_NEW_ID)
    assert view is not None
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["baseline_run_reference"]["run_id"] == _PY_OLD_ID
    assert outcome["target_run_reference"]["run_id"] == _PY_NEW_ID
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"


def test_status_view_probes_engine_scoped_pair_cache(tmp_path: Path) -> None:
    """``status``: unavailable before any compare (cache-only contract),
    available after the engine-scoped pair is derived. Pre-D5 the flag
    could never flip in a mixed store — status probed the (cargo-test,
    pytest) pair whose cache ``compare_runs`` refuses to ever write."""
    store = _seed_mixed_engine_store(tmp_path)

    before = build_status_view(store)
    assert before.regression_available is False

    derived = derive_latest_regression(store)  # writes the pair cache
    assert isinstance(derived, RegressionFactSet)

    after = build_status_view(store)
    assert after.regression_available is True
    sub_reports = after.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"
