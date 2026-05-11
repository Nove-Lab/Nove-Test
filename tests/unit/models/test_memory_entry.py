"""Unit tests for `novetest.models.memory_entry`."""

from __future__ import annotations

import pytest

from novetest.models.memory_entry import SCHEMA_VERSION, MemoryEntry
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


def _sample_record() -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id="01HXYZ", created_at=1_700_000_000_000),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1_700_000_000_000,
    )


def _sample_entry(**overrides: object) -> MemoryEntry:
    defaults: dict[str, object] = {
        "entry_id": "01HXYZ",
        "run_record": _sample_record(),
        "stored_at": 1_700_000_000_750,
        "has_coverage_facts": True,
        "has_regression_facts": False,
        "has_localization_findings": False,
        "has_replay_result": False,
        "tombstoned_at": None,
    }
    defaults.update(overrides)
    return MemoryEntry(**defaults)  # type: ignore[arg-type]


def test_round_trip_preserves_equality() -> None:
    original = _sample_entry()
    restored = MemoryEntry.from_dict(original.to_dict())
    assert restored == original


def test_round_trip_with_tombstone() -> None:
    original = _sample_entry(tombstoned_at=1_700_000_009_999)
    restored = MemoryEntry.from_dict(original.to_dict())
    assert restored == original
    assert restored.tombstoned_at == 1_700_000_009_999


def test_default_availability_flags_are_false() -> None:
    entry = MemoryEntry(
        entry_id="01HXYZ",
        run_record=_sample_record(),
        stored_at=1,
    )
    assert entry.has_coverage_facts is False
    assert entry.has_regression_facts is False
    assert entry.has_localization_findings is False
    assert entry.has_replay_result is False
    assert entry.tombstoned_at is None


def test_to_dict_includes_schema_version_at_all_levels() -> None:
    payload = _sample_entry().to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["run_record"]["schema_version"] == SCHEMA_VERSION
    assert payload["run_record"]["run_reference"]["schema_version"] == SCHEMA_VERSION


def test_from_dict_missing_required_key_raises() -> None:
    payload = _sample_entry().to_dict()
    del payload["stored_at"]
    with pytest.raises(ValueError, match="missing required keys"):
        MemoryEntry.from_dict(payload)


def test_from_dict_rejects_future_schema_version() -> None:
    payload = _sample_entry().to_dict()
    payload["schema_version"] = 7
    with pytest.raises(ValueError, match="Unsupported"):
        MemoryEntry.from_dict(payload)


def test_from_dict_propagates_nested_run_record_schema_mismatch() -> None:
    payload = _sample_entry().to_dict()
    payload["run_record"]["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        MemoryEntry.from_dict(payload)


def test_instances_are_frozen() -> None:
    entry = _sample_entry()
    with pytest.raises(AttributeError):
        entry.tombstoned_at = 12345  # type: ignore[misc]
