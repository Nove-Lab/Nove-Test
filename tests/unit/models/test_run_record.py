"""Unit tests for `novetest.models.run_record`."""

from __future__ import annotations

import pytest

from novetest.models.run_record import SCHEMA_VERSION, RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


def _sample_reference() -> RunReference:
    return RunReference(run_id="01HXYZ", created_at=1_700_000_000_000)


def _sample_record(**overrides: object) -> RunRecord:
    defaults: dict[str, object] = {
        "run_reference": _sample_reference(),
        "target_expression": "tests/test_foo.py",
        "target_type": "file",
        "engine_name": "pytest",
        "engine_version": "8.2.1",
        "ecosystem": "python",
        "status": "failed",
        "started_at": 1_700_000_000_000,
        "completed_at": 1_700_000_000_500,
        "summary_counts": {"passed": 1, "failed": 1},
        "test_results": (
            TestResult(node_id="tests/test_foo.py::test_a", outcome="passed", duration_ms=4),
            TestResult(node_id="tests/test_foo.py::test_b", outcome="failed", duration_ms=8),
        ),
        "artifact_paths": {
            "junit_xml": "run/artifacts/01HXYZ/native/junit.xml",
            "pytest_json": "run/artifacts/01HXYZ/native/pytest-report.json",
        },
        "metadata": {"cwd": "/tmp/proj", "python": "3.12.4"},
    }
    defaults.update(overrides)
    return RunRecord(**defaults)  # type: ignore[arg-type]


def test_round_trip_preserves_equality() -> None:
    original = _sample_record()
    restored = RunRecord.from_dict(original.to_dict())
    assert restored == original


def test_round_trip_with_defaults() -> None:
    minimal = RunRecord(
        run_reference=_sample_reference(),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1_700_000_000_000,
    )
    assert RunRecord.from_dict(minimal.to_dict()) == minimal


def test_to_dict_includes_schema_version_and_nested_reference() -> None:
    record = _sample_record()
    payload = record.to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["run_reference"]["schema_version"] == SCHEMA_VERSION
    assert payload["test_results"][0]["schema_version"] == SCHEMA_VERSION


def test_from_dict_missing_required_key_raises() -> None:
    payload = _sample_record().to_dict()
    del payload["target_expression"]
    with pytest.raises(ValueError, match="missing required keys"):
        RunRecord.from_dict(payload)


def test_from_dict_rejects_future_schema_version() -> None:
    payload = _sample_record().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        RunRecord.from_dict(payload)


def test_from_dict_propagates_nested_schema_mismatch() -> None:
    payload = _sample_record().to_dict()
    payload["run_reference"]["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        RunRecord.from_dict(payload)


def test_instances_are_frozen() -> None:
    record = _sample_record()
    with pytest.raises(AttributeError):
        record.status = "passed"  # type: ignore[misc]


# --- MEM-04: additive-optional `stored_at` ------------------------------------
#
# The Memory engine's persistence stamp. Contract (task
# memory-team-2026-07-10-w2-s41): epoch-ms int, OPTIONAL under the frozen
# schema_version == 1, key omitted (not null) when unset so pre-change records
# round-trip byte-identically, absence tolerated forever.


def test_stored_at_defaults_to_none_and_stays_off_to_dict() -> None:
    record = _sample_record()
    assert record.stored_at is None
    assert "stored_at" not in record.to_dict()


def test_stored_at_round_trips_when_set() -> None:
    record = _sample_record(stored_at=1_700_000_000_900)
    payload = record.to_dict()
    assert payload["stored_at"] == 1_700_000_000_900
    restored = RunRecord.from_dict(payload)
    assert restored == record
    assert restored.stored_at == 1_700_000_000_900


def test_from_dict_tolerates_legacy_payload_without_stored_at() -> None:
    # A pre-MEM-04 record.json has no `stored_at` key; it must load forever
    # (readers fall back to file mtime at the store layer).
    payload = _sample_record().to_dict()
    assert "stored_at" not in payload
    restored = RunRecord.from_dict(payload)
    assert restored.stored_at is None


def test_stored_at_does_not_bump_schema_version() -> None:
    assert SCHEMA_VERSION == 1
    assert _sample_record(stored_at=1).to_dict()["schema_version"] == 1
