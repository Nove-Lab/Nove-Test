"""Unit tests for ``novetest.regression.compare`` — the meat of the slice.

Coverage:
- One test per ``TRANSITION_CATEGORIES`` value (9 categories).
- Bucketing edge cases (``xpassed`` → pass-like, ``xfailed`` → skip-like).
- Unknown outcome: defensive bucketing + ``"unknown-outcome:..."`` warning.
- Tombstones (baseline / target / both) → ``REASON_RUN_TOMBSTONED``.
- Engine name mismatch (pytest vs jest) → ``REASON_ENGINE_MISMATCH``.
- Engine version drift (same name) → succeeds with
  ``"engine-version-drift"`` warning.
- Target expression mismatch → ``REASON_TARGET_MISMATCH``.
- Run not found → ``REASON_RUN_NOT_FOUND``.
- Determinism: transitions sorted by ``node_id``; two calls produce
  byte-identical ``to_dict()``.
- Cache hit: ``derive_regression_facts`` not re-invoked.
- Stale-coverage detection: re-derive on next call.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import delete_run_evidence
from novetest.models.memory_entry import MemoryEntry
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    TestTransition,
)
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression import compare as compare_module
from novetest.regression.compare import compare_runs, derive_regression_facts
from novetest.regression.persistence import (
    regression_facts_path,
    write_regression_facts,
)
from novetest.regression.results import (
    REASON_ENGINE_MISMATCH,
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_NOT_FOUND,
    REASON_RUN_TOMBSTONED,
    REASON_TARGET_MISMATCH,
    RegressionUnavailable,
)


_REF_BASELINE = RunReference(run_id="01HBASELINE", created_at=1_700_000_000_000)
_REF_TARGET = RunReference(run_id="01HTARGET01", created_at=1_700_000_001_000)


def _tr(node_id: str, outcome: str) -> TestResult:
    return TestResult(node_id=node_id, outcome=outcome, duration_ms=10)


def _find_transition(
    fact_set: RegressionFactSet, node_id: str
) -> TestTransition:
    for t in fact_set.test_transitions:
        if t.node_id == node_id:
            return t
    raise AssertionError(f"no transition for node_id={node_id!r}")


def _seed_pair(
    store_path: Path,
    seed_run_record: Callable[..., MemoryEntry],
    baseline_outcomes: dict[str, str],
    target_outcomes: dict[str, str],
    **record_overrides: Any,
) -> None:
    baseline_results = tuple(
        _tr(nid, outcome) for nid, outcome in baseline_outcomes.items()
    )
    target_results = tuple(
        _tr(nid, outcome) for nid, outcome in target_outcomes.items()
    )
    baseline_kwargs: dict[str, Any] = {}
    target_kwargs: dict[str, Any] = {}
    for key, value in record_overrides.items():
        if key.startswith("baseline_"):
            baseline_kwargs[key[len("baseline_"):]] = value
        elif key.startswith("target_"):
            target_kwargs[key[len("target_"):]] = value
        else:
            baseline_kwargs[key] = value
            target_kwargs[key] = value
    seed_run_record(
        store_path,
        run_reference=_REF_BASELINE,
        test_results=baseline_results,
        **baseline_kwargs,
    )
    seed_run_record(
        store_path,
        run_reference=_REF_TARGET,
        test_results=target_results,
        **target_kwargs,
    )


# --- one test per TRANSITION_CATEGORIES value (9 categories) -----------------


def test_category_regressed(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "failed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    t = _find_transition(result, "tests/x.py::test_a")
    assert t.category == "regressed"
    assert result.summary.regressed == 1


def test_category_fixed(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "failed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert _find_transition(result, "tests/x.py::test_a").category == "fixed"
    assert result.summary.fixed == 1


def test_category_still_failing(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "errored"},
        {"tests/x.py::test_a": "failed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "still_failing"
    )
    assert result.summary.still_failing == 1


def test_category_still_passing(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "still_passing"
    )
    assert result.summary.still_passing == 1


def test_category_still_skipped(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "skipped"},
        {"tests/x.py::test_a": "skipped"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "still_skipped"
    )
    assert result.summary.still_skipped == 1


def test_category_newly_skipped(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "skipped"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "newly_skipped"
    )
    assert result.summary.newly_skipped == 1


def test_category_newly_active(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "skipped"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "newly_active"
    )
    assert result.summary.newly_active == 1


def test_category_added(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {},
        {"tests/x.py::test_new": "passed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    t = _find_transition(result, "tests/x.py::test_new")
    assert t.category == "added"
    assert t.baseline_outcome is None
    assert t.target_outcome == "passed"
    assert result.summary.added == 1
    # Convenience aggregate: target carries the new test; baseline didn't.
    assert result.summary.total_baseline_tests == 0
    assert result.summary.total_target_tests == 1


def test_category_removed(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_gone": "passed"},
        {},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    t = _find_transition(result, "tests/x.py::test_gone")
    assert t.category == "removed"
    assert t.baseline_outcome == "passed"
    assert t.target_outcome is None
    assert result.summary.removed == 1
    assert result.summary.total_baseline_tests == 1
    assert result.summary.total_target_tests == 0


# --- bucketing edge cases ---------------------------------------------------


def test_xpassed_counts_as_pass_like(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """``xpassed`` is in the pass-like bucket per decision §3 — pass→fail is regressed."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "xpassed"},
        {"tests/x.py::test_a": "failed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert _find_transition(result, "tests/x.py::test_a").category == "regressed"


def test_xfailed_counts_as_skip_like(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """``xfailed`` is in the skip-like bucket per decision §3 — passed→xfailed is newly_skipped."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "xfailed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert (
        _find_transition(result, "tests/x.py::test_a").category == "newly_skipped"
    )


def test_unknown_outcome_emits_warning_and_buckets_defensively(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Outcomes outside the closed 6-set fall into the closest bucket AND
    surface a ``"unknown-outcome:<engine>:<raw>"`` warning (decision §5.2)."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "weird-status"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert "unknown-outcome:pytest:weird-status" in result.warnings
    # ``weird-status`` does not contain "pass" / "skip", so it buckets to fail
    # by default — passed→fail is regressed.
    assert _find_transition(result, "tests/x.py::test_a").category == "regressed"


def test_unknown_outcome_deduplicated_across_tests(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """The same unrecognized outcome on many tests emits the warning ONCE."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {
            "tests/x.py::test_a": "passed",
            "tests/x.py::test_b": "passed",
        },
        {
            "tests/x.py::test_a": "weird",
            "tests/x.py::test_b": "weird",
        },
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    occurrences = [w for w in result.warnings if w.startswith("unknown-outcome:")]
    assert occurrences == ["unknown-outcome:pytest:weird"]


# --- tombstones --------------------------------------------------------------


def test_baseline_tombstoned_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, _REF_BASELINE)

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_TOMBSTONED
    assert result.detail == "baseline"


def test_target_tombstoned_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, _REF_TARGET)

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_TOMBSTONED
    assert result.detail == "target"


def test_both_tombstoned_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    delete_run_evidence(store, _REF_BASELINE)
    delete_run_evidence(store, _REF_TARGET)

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_TOMBSTONED
    assert result.detail == "both"


def test_tombstone_check_overrides_cached_facts(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Decision §C.1: tombstoning AFTER the cache was created must still
    return ``REASON_RUN_TOMBSTONED``, not surface stale cached facts."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    # First call populates the cache.
    initial = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(initial, RegressionFactSet)
    assert regression_facts_path(
        store, _REF_BASELINE.run_id, _REF_TARGET.run_id
    ).is_file()

    delete_run_evidence(store, _REF_BASELINE)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_TOMBSTONED


# --- engine name / version + target mismatches -------------------------------


def test_engine_name_mismatch_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
        baseline_engine_name="pytest",
        target_engine_name="jest",
        baseline_ecosystem="python",
        target_ecosystem="node",
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_ENGINE_MISMATCH


def test_engine_version_drift_warning(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
        baseline_engine_version="8.1.0",
        target_engine_version="8.2.0",
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert "engine-version-drift" in result.warnings
    assert result.baseline_engine_version == "8.1.0"
    assert result.target_engine_version == "8.2.0"


def test_target_expression_mismatch_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
        baseline_target_expression="tests/foo/",
        target_target_expression="tests/bar/",
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_TARGET_MISMATCH


def test_target_type_drift_emits_warning_not_failure(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Same target_expression with differing target_type: warning, not failure."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
        baseline_target_type="dir",
        target_target_type="file",
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert "target-type-drift" in result.warnings


# --- run-not-found / general errors -----------------------------------------


def test_baseline_not_found_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Only the target is seeded; baseline ref doesn't resolve."""
    seed_run_record(
        initialized_store,
        run_reference=_REF_TARGET,
        test_results=(_tr("tests/x.py::test_a", "passed"),),
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND
    assert result.detail is not None
    assert result.detail.startswith("baseline:")
    # Both refs are surfaced for the caller's audit trail.
    assert result.baseline_run_reference == _REF_BASELINE
    assert result.target_run_reference == _REF_TARGET


def test_target_not_found_returns_unavailable(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    seed_run_record(
        initialized_store,
        run_reference=_REF_BASELINE,
        test_results=(_tr("tests/x.py::test_a", "passed"),),
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND
    assert result.detail is not None
    assert result.detail.startswith("target:")


# --- determinism / caching --------------------------------------------------


def test_transitions_sorted_by_node_id_ascending(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Decision §5 constraint #3 — load-bearing for NFR-REG-001."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {
            "tests/z.py::test_a": "passed",
            "tests/a.py::test_z": "passed",
            "tests/m.py::test_m": "failed",
        },
        {
            "tests/z.py::test_a": "passed",
            "tests/a.py::test_z": "failed",
            "tests/m.py::test_m": "passed",
        },
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    node_ids = [t.node_id for t in result.test_transitions]
    assert node_ids == sorted(node_ids)


def test_compare_runs_is_byte_deterministic(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Two successive calls must produce byte-identical ``to_dict()`` output.

    ``derived_at`` is the only embedded timestamp that could vary; the
    second call is a cache hit so it returns the original derived_at."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed", "tests/x.py::test_b": "failed"},
        {"tests/x.py::test_a": "failed", "tests/x.py::test_b": "passed"},
    )
    store = get_project_store_state(initialized_store)
    first = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    second = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(first, RegressionFactSet)
    assert isinstance(second, RegressionFactSet)
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


def test_second_call_hits_cache_does_not_re_derive(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)

    first = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(first, RegressionFactSet)

    # Sentinel: any subsequent derive call must explode loudly.
    calls = {"count": 0}

    real_derive = compare_module.derive_regression_facts

    def sentinel(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        return real_derive(*args, **kwargs)

    monkeypatch.setattr(compare_module, "derive_regression_facts", sentinel)
    second = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(second, RegressionFactSet)
    assert calls["count"] == 0


def test_stale_coverage_in_cache_triggers_re_derive(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    """Decision §C.6: a cached payload with embedded coverage_change at a
    lower schema_version returns ``missing-derived-facts`` from
    ``get_regression_facts``; ``compare_runs`` re-derives in response."""
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    # Pre-populate the cache with a hand-crafted stale payload.
    cache_path = regression_facts_path(
        store, _REF_BASELINE.run_id, _REF_TARGET.run_id
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "baseline_run_reference": _REF_BASELINE.to_dict(),
                "target_run_reference": _REF_TARGET.to_dict(),
                "baseline_engine_name": "pytest",
                "target_engine_name": "pytest",
                "baseline_engine_version": "8.2.0",
                "target_engine_version": "8.2.0",
                "derived_at": 0,
                "summary": {
                    "regressed": 0, "fixed": 0, "still_failing": 0,
                    "still_passing": 0, "still_skipped": 0, "newly_skipped": 0,
                    "newly_active": 0, "added": 0, "removed": 0,
                    "total_baseline_tests": 0, "total_target_tests": 0,
                },
                "test_transitions": [],
                "output_diff": None,
                "coverage_change": {"schema_version": 0, "files_added": []},
                "warnings": [],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    # Re-derive recomputed real summary + dropped the stale embed
    # (neither side has Coverage Facts → coverage_change is None).
    assert result.coverage_change is None
    assert result.summary.still_passing == 1


# --- output diff fingerprints -----------------------------------------------


def test_output_diff_sha256_from_artifact_bytes(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    store = get_project_store_state(initialized_store)
    # Materialize per-run stdout files; register them in artifact_paths.
    baseline_rel = (
        f"run/artifacts/run_{_REF_BASELINE.run_id}/native/stdout.log"
    )
    target_rel = f"run/artifacts/run_{_REF_TARGET.run_id}/native/stdout.log"
    (store.path / baseline_rel).parent.mkdir(parents=True, exist_ok=True)
    (store.path / target_rel).parent.mkdir(parents=True, exist_ok=True)
    baseline_bytes = b"baseline stdout body\n"
    target_bytes = b"target stdout body\n"
    (store.path / baseline_rel).write_bytes(baseline_bytes)
    (store.path / target_rel).write_bytes(target_bytes)

    seed_run_record(
        initialized_store,
        run_reference=_REF_BASELINE,
        test_results=(_tr("tests/x.py::test_a", "passed"),),
        artifact_paths={"stdout": baseline_rel},
    )
    seed_run_record(
        initialized_store,
        run_reference=_REF_TARGET,
        test_results=(_tr("tests/x.py::test_a", "passed"),),
        artifact_paths={"stdout": target_rel},
    )

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert result.output_diff is not None
    od = result.output_diff
    assert od.baseline_stdout_sha256 == hashlib.sha256(baseline_bytes).hexdigest()
    assert od.target_stdout_sha256 == hashlib.sha256(target_bytes).hexdigest()
    assert od.stdout_identical is False
    assert od.stderr_identical is False  # neither side present
    # Paths are Project-Store-relative, not absolute (decision §4 constraint #5).
    assert od.baseline_stdout_path == baseline_rel
    assert od.target_stdout_path == target_rel
    assert od.baseline_stderr_path is None
    assert od.target_stderr_path is None


def test_output_diff_none_when_neither_side_has_artifacts(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "passed"},
    )
    store = get_project_store_state(initialized_store)
    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert result.output_diff is None


def test_output_diff_identical_when_same_bytes(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    store = get_project_store_state(initialized_store)
    body = b"same bytes everywhere\n"
    baseline_rel = (
        f"run/artifacts/run_{_REF_BASELINE.run_id}/native/stdout.log"
    )
    target_rel = f"run/artifacts/run_{_REF_TARGET.run_id}/native/stdout.log"
    (store.path / baseline_rel).parent.mkdir(parents=True, exist_ok=True)
    (store.path / target_rel).parent.mkdir(parents=True, exist_ok=True)
    (store.path / baseline_rel).write_bytes(body)
    (store.path / target_rel).write_bytes(body)

    seed_run_record(
        initialized_store,
        run_reference=_REF_BASELINE,
        test_results=(),
        artifact_paths={"stdout": baseline_rel},
    )
    seed_run_record(
        initialized_store,
        run_reference=_REF_TARGET,
        test_results=(),
        artifact_paths={"stdout": target_rel},
    )

    result = compare_runs(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert result.output_diff is not None
    assert result.output_diff.stdout_identical is True


# --- direct derive entry point -----------------------------------------------


def test_derive_regression_facts_writes_to_disk(
    initialized_store: Path,
    seed_run_record: Callable[..., MemoryEntry],
) -> None:
    _seed_pair(
        initialized_store,
        seed_run_record,
        {"tests/x.py::test_a": "passed"},
        {"tests/x.py::test_a": "failed"},
    )
    store = get_project_store_state(initialized_store)
    result = derive_regression_facts(store, _REF_BASELINE, _REF_TARGET)
    assert isinstance(result, RegressionFactSet)
    assert regression_facts_path(
        store, _REF_BASELINE.run_id, _REF_TARGET.run_id
    ).is_file()
