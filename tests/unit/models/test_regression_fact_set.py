"""Unit tests for ``novetest.models.regression_fact_set``.

Each dataclass needs a ``to_dict`` ↔ ``from_dict`` round-trip, a
``schema_version`` mismatch test (where applicable), and coverage of the
read-side tolerance rules pinned in decision §8.
"""

from __future__ import annotations

import pytest

from novetest.models.regression_fact_set import (
    SCHEMA_VERSION,
    TRANSITION_CATEGORIES,
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
    TestTransition,
)
from novetest.models.run_reference import RunReference


def _summary() -> RegressionSummary:
    return RegressionSummary(
        regressed=1,
        fixed=2,
        still_failing=3,
        still_passing=4,
        still_skipped=5,
        newly_skipped=6,
        newly_active=7,
        added=8,
        removed=9,
        total_baseline_tests=22,
        total_target_tests=21,
    )


def _output_diff() -> OutputDiffRecord:
    return OutputDiffRecord(
        baseline_stdout_sha256="aaa",
        target_stdout_sha256="bbb",
        baseline_stderr_sha256=None,
        target_stderr_sha256=None,
        stdout_identical=False,
        stderr_identical=True,
        baseline_stdout_path="run/artifacts/run_B/native/stdout.log",
        target_stdout_path="run/artifacts/run_T/native/stdout.log",
        baseline_stderr_path=None,
        target_stderr_path=None,
    )


def _transition(category: str = "regressed") -> TestTransition:
    return TestTransition(
        node_id="tests/test_x.py::test_a",
        category=category,
        baseline_outcome="passed",
        target_outcome="failed",
        baseline_failure_reference=None,
        target_failure_reference="blobs/sha256/abc",
        baseline_duration_ms=12,
        target_duration_ms=9,
    )


def _fact_set() -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=RunReference(run_id="01HBASE", created_at=1),
        target_run_reference=RunReference(run_id="01HTRGT", created_at=2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=1_700_000_000_000,
        summary=_summary(),
        test_transitions=(_transition(),),
        output_diff=_output_diff(),
        coverage_change={"schema_version": 1, "files_added": ["x.py"]},
        warnings=("engine-version-drift",),
    )


# --- TestTransition ---------------------------------------------------------


def test_test_transition_round_trip() -> None:
    t = _transition()
    assert TestTransition.from_dict(t.to_dict()) == t


def test_test_transition_round_trip_with_nulls() -> None:
    """An ``added`` transition has no baseline side; a ``removed`` has no target side."""
    added = TestTransition(
        node_id="tests/test_y.py::test_new",
        category="added",
        baseline_outcome=None,
        target_outcome="passed",
        baseline_failure_reference=None,
        target_failure_reference=None,
        baseline_duration_ms=None,
        target_duration_ms=15,
    )
    assert TestTransition.from_dict(added.to_dict()) == added


def test_test_transition_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="category"):
        TestTransition(
            node_id="x",
            category="renamed",  # not in TRANSITION_CATEGORIES
            baseline_outcome="passed",
            target_outcome="passed",
            baseline_failure_reference=None,
            target_failure_reference=None,
            baseline_duration_ms=None,
            target_duration_ms=None,
        )


def test_test_transition_schema_version_mismatch_raises() -> None:
    payload = _transition().to_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="schema_version"):
        TestTransition.from_dict(payload)


def test_transition_categories_is_closed_nine_set() -> None:
    """Decision §3 pins the closed taxonomy at exactly nine values."""
    assert len(TRANSITION_CATEGORIES) == 9
    expected = {
        "regressed",
        "fixed",
        "still_failing",
        "still_passing",
        "still_skipped",
        "newly_skipped",
        "newly_active",
        "added",
        "removed",
    }
    assert set(TRANSITION_CATEGORIES) == expected


# --- RegressionSummary ------------------------------------------------------


def test_regression_summary_round_trip() -> None:
    s = _summary()
    assert RegressionSummary.from_dict(s.to_dict()) == s


def test_regression_summary_missing_key_raises() -> None:
    payload = _summary().to_dict()
    del payload["added"]
    with pytest.raises(ValueError, match="missing required keys"):
        RegressionSummary.from_dict(payload)


# --- OutputDiffRecord -------------------------------------------------------


def test_output_diff_record_round_trip() -> None:
    od = _output_diff()
    assert OutputDiffRecord.from_dict(od.to_dict()) == od


def test_output_diff_record_read_tolerance_for_optional_fields() -> None:
    """All SHA/path fields default to ``None`` when omitted on the wire
    (decision §8 — read-side compatibility seam)."""
    minimal = {"stdout_identical": False, "stderr_identical": False}
    record = OutputDiffRecord.from_dict(minimal)
    assert record.baseline_stdout_sha256 is None
    assert record.target_stdout_sha256 is None
    assert record.baseline_stderr_sha256 is None
    assert record.target_stderr_sha256 is None
    assert record.baseline_stdout_path is None
    assert record.target_stdout_path is None
    assert record.baseline_stderr_path is None
    assert record.target_stderr_path is None


# --- RegressionFactSet ------------------------------------------------------


def test_regression_fact_set_round_trip() -> None:
    fs = _fact_set()
    assert RegressionFactSet.from_dict(fs.to_dict()) == fs


def test_regression_fact_set_round_trip_with_none_optional_blocks() -> None:
    fs = RegressionFactSet(
        baseline_run_reference=RunReference(run_id="01HBASE", created_at=1),
        target_run_reference=RunReference(run_id="01HTRGT", created_at=2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version=None,
        target_engine_version=None,
        derived_at=1_700_000_000_000,
        summary=_summary(),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )
    assert RegressionFactSet.from_dict(fs.to_dict()) == fs


def test_regression_fact_set_schema_version_mismatch_raises() -> None:
    payload = _fact_set().to_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="schema_version"):
        RegressionFactSet.from_dict(payload)


def test_regression_fact_set_read_tolerance_omits_optionals() -> None:
    """``warnings`` / ``metadata`` / ``output_diff`` / ``coverage_change``
    are optional on read per decision §8."""
    full = _fact_set().to_dict()
    # Strip every optional that §8 declares read-tolerant.
    for k in ("warnings", "metadata", "output_diff", "coverage_change",
              "baseline_engine_version", "target_engine_version"):
        full.pop(k, None)
    restored = RegressionFactSet.from_dict(full)
    assert restored.warnings == ()
    assert restored.metadata == {}
    assert restored.output_diff is None
    assert restored.coverage_change is None
    assert restored.baseline_engine_version is None
    assert restored.target_engine_version is None


def test_regression_fact_set_missing_required_key_raises() -> None:
    """A required top-level field is NOT in the read-tolerance list."""
    payload = _fact_set().to_dict()
    del payload["baseline_engine_name"]
    with pytest.raises(ValueError, match="missing required keys"):
        RegressionFactSet.from_dict(payload)


def test_regression_fact_set_carries_coverage_change_verbatim() -> None:
    """``coverage_change`` is stored as an opaque dict; we don't dissect it."""
    fs = _fact_set()
    restored = RegressionFactSet.from_dict(fs.to_dict())
    assert restored.coverage_change == {
        "schema_version": 1,
        "files_added": ["x.py"],
    }
