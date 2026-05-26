"""Unit tests for ``novetest.regression.retrieval``.

``get_regression_facts`` is a pure cache reader: missing pair directory →
``REASON_MISSING_DERIVED_FACTS``; existing payload with stale embedded
Coverage delta → same reason, ``detail="coverage-schema-stale"`` (decision
§C.6). Memory is NOT consulted at this layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory.project_store import get_project_store_state
from novetest.models.regression_fact_set import (
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_reference import RunReference
from novetest.regression.persistence import (
    regression_facts_path,
    write_regression_facts,
)
from novetest.regression.results import (
    REASON_MISSING_DERIVED_FACTS,
    RegressionUnavailable,
)
from novetest.regression.retrieval import get_regression_facts


_BASELINE_REF = RunReference(run_id="01HBASE", created_at=1)
_TARGET_REF = RunReference(run_id="01HTRGT", created_at=2)


def _summary() -> RegressionSummary:
    return RegressionSummary(
        regressed=0, fixed=0, still_failing=0, still_passing=0,
        still_skipped=0, newly_skipped=0, newly_active=0, added=0,
        removed=0, total_baseline_tests=0, total_target_tests=0,
    )


def _fact_set(*, coverage_change: dict[str, object] | None = None) -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=_BASELINE_REF,
        target_run_reference=_TARGET_REF,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version=None,
        target_engine_version=None,
        derived_at=1_700_000_000_000,
        summary=_summary(),
        test_transitions=(),
        output_diff=OutputDiffRecord(
            baseline_stdout_sha256=None,
            target_stdout_sha256=None,
            baseline_stderr_sha256=None,
            target_stderr_sha256=None,
            stdout_identical=True,
            stderr_identical=True,
            baseline_stdout_path=None,
            target_stdout_path=None,
            baseline_stderr_path=None,
            target_stderr_path=None,
        ),
        coverage_change=coverage_change,
    )


def test_get_returns_missing_when_no_pair_dir(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    result = get_regression_facts(store, _BASELINE_REF, _TARGET_REF)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
    assert result.baseline_run_reference == _BASELINE_REF
    assert result.target_run_reference == _TARGET_REF


def test_get_returns_cached_facts_when_present(initialized_store: Path) -> None:
    store = get_project_store_state(initialized_store)
    fs = _fact_set()
    write_regression_facts(store, fs)
    result = get_regression_facts(store, _BASELINE_REF, _TARGET_REF)
    assert isinstance(result, RegressionFactSet)
    assert result == fs


def test_get_flags_coverage_schema_stale(initialized_store: Path) -> None:
    """Decision §C.6 — an embedded ``coverage_change.schema_version`` below
    current returns ``missing-derived-facts`` with ``coverage-schema-stale``
    detail so the caller can re-derive."""
    store = get_project_store_state(initialized_store)
    path = regression_facts_path(
        store, _BASELINE_REF.run_id, _TARGET_REF.run_id
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    fs = _fact_set()
    payload = fs.to_dict()
    # Hand-craft a stale embedded coverage_change. Schema_version 0 is
    # below the current CoverageDelta schema (1) by definition.
    payload["coverage_change"] = {"schema_version": 0, "files_added": []}
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = get_regression_facts(store, _BASELINE_REF, _TARGET_REF)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
    assert result.detail == "coverage-schema-stale"


def test_get_passes_through_null_coverage_change(initialized_store: Path) -> None:
    """``coverage_change is None`` is NOT stale — it just means neither
    side had Coverage Facts at derive time."""
    store = get_project_store_state(initialized_store)
    write_regression_facts(store, _fact_set(coverage_change=None))
    result = get_regression_facts(store, _BASELINE_REF, _TARGET_REF)
    assert isinstance(result, RegressionFactSet)
    assert result.coverage_change is None


def test_get_argument_order_is_load_bearing(initialized_store: Path) -> None:
    """``(rA, rB)`` and ``(rB, rA)`` resolve to different pair directories —
    a cached forward pair does NOT satisfy a reverse lookup."""
    store = get_project_store_state(initialized_store)
    write_regression_facts(store, _fact_set())

    reversed_result = get_regression_facts(store, _TARGET_REF, _BASELINE_REF)
    assert isinstance(reversed_result, RegressionUnavailable)
    assert reversed_result.reason == REASON_MISSING_DERIVED_FACTS
