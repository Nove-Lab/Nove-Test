"""Unit tests for `novetest.models.run_reference`."""

from __future__ import annotations

import pytest

from novetest.models.run_reference import SCHEMA_VERSION, RunReference


def test_round_trip_preserves_equality() -> None:
    original = RunReference(run_id="01HXYZABCDEF0000000000", created_at=1_700_000_000_000)
    restored = RunReference.from_dict(original.to_dict())
    assert restored == original


def test_to_dict_includes_schema_version() -> None:
    ref = RunReference(run_id="01HXYZ", created_at=1)
    assert ref.to_dict()["schema_version"] == SCHEMA_VERSION


def test_from_dict_missing_required_key_raises() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        RunReference.from_dict({"schema_version": 1, "run_id": "01HXYZ"})


def test_from_dict_rejects_future_schema_version() -> None:
    payload = {"schema_version": 2, "run_id": "01HXYZ", "created_at": 1}
    with pytest.raises(ValueError, match="Unsupported"):
        RunReference.from_dict(payload)


def test_instances_are_frozen() -> None:
    ref = RunReference(run_id="01HXYZ", created_at=1)
    with pytest.raises(AttributeError):
        ref.run_id = "tampered"  # type: ignore[misc]


def test_uses_slots_and_has_no_dict() -> None:
    ref = RunReference(run_id="01HXYZ", created_at=1)
    assert not hasattr(ref, "__dict__")
