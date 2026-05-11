"""Unit tests for `novetest.models.test_result`."""

from __future__ import annotations

import pytest

from novetest.models.test_result import SCHEMA_VERSION, TestResult


def test_round_trip_full_fields() -> None:
    original = TestResult(
        node_id="tests/test_foo.py::test_bar",
        outcome="failed",
        duration_ms=42,
        failure_reference="native/pytest-report.json#failures/0",
    )
    assert TestResult.from_dict(original.to_dict()) == original


def test_round_trip_optional_fields_null() -> None:
    original = TestResult(node_id="tests/test_foo.py::test_skip", outcome="skipped")
    assert TestResult.from_dict(original.to_dict()) == original


def test_to_dict_includes_schema_version() -> None:
    tr = TestResult(node_id="t", outcome="passed")
    assert tr.to_dict()["schema_version"] == SCHEMA_VERSION


def test_from_dict_missing_required_key_raises() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        TestResult.from_dict({"schema_version": 1, "node_id": "t"})


def test_from_dict_rejects_future_schema_version() -> None:
    payload = {"schema_version": 99, "node_id": "t", "outcome": "passed"}
    with pytest.raises(ValueError, match="Unsupported"):
        TestResult.from_dict(payload)


def test_instances_are_frozen() -> None:
    tr = TestResult(node_id="t", outcome="passed")
    with pytest.raises(AttributeError):
        tr.outcome = "failed"  # type: ignore[misc]
