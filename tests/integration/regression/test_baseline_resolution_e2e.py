"""End-to-end integration tests for the baseline-resolution helpers.

Build real ``RunRecord``s via the real ``store_run_evidence`` seam, call
``derive_latest_regression`` end-to-end, and validate:

- A ``RegressionFactSet`` lands on disk at the pinned pair path with the
  expected summary (`regressed=1`); re-calling preserves ``derived_at``
  (cache hit, not re-derivation).
- A tombstoned latest run is skipped; ``derive_latest_regression`` picks
  the two next-most-recent live runs sharing the active target.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import delete_run_evidence, store_run_evidence
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression import derive_latest_regression
from novetest.regression.persistence import regression_facts_path


_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000


def _record(
    *,
    run_id: str,
    created_at: int,
    target_expression: str,
    test_results: tuple[TestResult, ...],
) -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=created_at),
        target_expression=target_expression,
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1_000,
        test_results=test_results,
    )


def test_derive_latest_writes_facts_at_pinned_path_and_caches(
    tmp_path: Path,
) -> None:
    """Three runs sharing a target — derive_latest_regression picks the two
    most recent and persists the regression facts at the canonical path."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    # Three live runs on the same target; the latest introduces a real
    # regression on test_a (pass → fail).
    store_run_evidence(
        store,
        _record(
            run_id="01OLDRUN0000000000000000001",
            created_at=_TS_OLD,
            target_expression="tests/",
            test_results=(
                TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=10),
            ),
        ),
    )
    store_run_evidence(
        store,
        _record(
            run_id="01MIDRUN0000000000000000002",
            created_at=_TS_MID,
            target_expression="tests/",
            test_results=(
                TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=9),
            ),
        ),
    )
    store_run_evidence(
        store,
        _record(
            run_id="01NEWRUN0000000000000000003",
            created_at=_TS_NEW,
            target_expression="tests/",
            test_results=(
                TestResult(node_id="tests/x.py::test_a", outcome="failed", duration_ms=11),
            ),
        ),
    )

    # First call — derives + writes.
    handle = get_project_store_state(store.path)
    first = derive_latest_regression(handle)
    assert isinstance(first, RegressionFactSet)
    assert first.baseline_run_reference.run_id == "01MIDRUN0000000000000000002"
    assert first.target_run_reference.run_id == "01NEWRUN0000000000000000003"
    assert first.summary.regressed == 1

    pair_path = regression_facts_path(
        handle,
        first.baseline_run_reference.run_id,
        first.target_run_reference.run_id,
    )
    assert pair_path.is_file()
    # Decision §1 pair-key convention: literal "__" between the two
    # ``run_<id>`` segments. The path-itself test in compare_e2e.py asserts
    # the same shape on a different code path; here we just sanity-check the
    # operator-facing artifact landed where Memory expects to find it.
    assert "__" in pair_path.parent.name
    payload = json.loads(pair_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    initial_derived_at = first.derived_at

    # Second call — cache hit; ``derived_at`` is preserved (the write-side
    # would have produced a fresh epoch_ms).
    second = derive_latest_regression(handle)
    assert isinstance(second, RegressionFactSet)
    assert second.derived_at == initial_derived_at


def test_derive_latest_skips_tombstoned_latest_in_real_store(
    tmp_path: Path,
) -> None:
    """A tombstoned latest run must not anchor the active target. The two
    next-most-recent live runs (on a different target) produce the pair."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    store_run_evidence(
        store,
        _record(
            run_id="01OLDRUN0000000000000000010",
            created_at=_TS_OLD,
            target_expression="tests/core/",
            test_results=(
                TestResult(node_id="tests/core/x.py::test_a", outcome="passed", duration_ms=10),
            ),
        ),
    )
    store_run_evidence(
        store,
        _record(
            run_id="01MIDRUN0000000000000000020",
            created_at=_TS_MID,
            target_expression="tests/core/",
            test_results=(
                TestResult(node_id="tests/core/x.py::test_a", outcome="failed", duration_ms=12),
            ),
        ),
    )
    latest = _record(
        run_id="01NEWRUN0000000000000000030",
        created_at=_TS_NEW,
        target_expression="tests/scratch/",
        test_results=(
            TestResult(node_id="tests/scratch/y.py::test_z", outcome="passed", duration_ms=4),
        ),
    )
    store_run_evidence(store, latest)
    delete_run_evidence(store, latest.run_reference)

    handle = get_project_store_state(store.path)
    result = derive_latest_regression(handle)
    assert isinstance(result, RegressionFactSet)
    # Active target falls back to the latest live run's target ("tests/core/")
    # which has two runs → the pair resolves cleanly.
    assert result.baseline_run_reference.run_id == "01OLDRUN0000000000000000010"
    assert result.target_run_reference.run_id == "01MIDRUN0000000000000000020"
    assert result.summary.regressed == 1
