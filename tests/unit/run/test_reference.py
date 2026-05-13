"""Unit tests for `novetest.run.reference`."""

from __future__ import annotations

from novetest.models import RunRecord, RunReference
from novetest.run.reference import assign_run_reference
from novetest.utils.ulid import new_ulid, timestamp_ms_from_ulid


def _placeholder_record() -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id="", created_at=0),
        target_expression="tests/",
        target_type="directory",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1,
        completed_at=2,
    )


def test_assigns_run_id_prefix_and_created_at_from_ulid() -> None:
    fixed = new_ulid(timestamp_ms=1_725_000_000_000)
    record = assign_run_reference(_placeholder_record(), run_id=fixed)
    assert record.run_reference.run_id == f"run_{fixed}"
    assert record.run_reference.created_at == timestamp_ms_from_ulid(fixed)


def test_default_ulid_starts_with_run_prefix() -> None:
    record = assign_run_reference(_placeholder_record())
    assert record.run_reference.run_id.startswith("run_")
    assert len(record.run_reference.run_id) == len("run_") + 26


def test_assignment_does_not_mutate_other_fields() -> None:
    original = _placeholder_record()
    after = assign_run_reference(original, run_id=new_ulid(timestamp_ms=0))
    assert after.target_expression == original.target_expression
    assert after.engine_name == original.engine_name
    assert after.test_results == original.test_results
