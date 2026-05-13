"""Unit tests for `novetest.run.reference`."""

from __future__ import annotations

from novetest.models import RunRecord, RunReference
from novetest.run.reference import assign_run_reference
from novetest.utils.ulid import ULID_LENGTH, extract_timestamp_ms, generate_ulid


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


def test_assigns_raw_ulid_run_id_and_created_at() -> None:
    fixed = generate_ulid(timestamp_ms=1_725_000_000_000)
    record = assign_run_reference(_placeholder_record(), run_id=fixed)
    assert record.run_reference.run_id == fixed
    assert record.run_reference.created_at == extract_timestamp_ms(fixed)


def test_default_ulid_is_canonical_length() -> None:
    record = assign_run_reference(_placeholder_record())
    assert len(record.run_reference.run_id) == ULID_LENGTH
    # Raw ULID — no ``run_`` prefix; Memory adds that when laying down the path.
    assert not record.run_reference.run_id.startswith("run_")


def test_assignment_does_not_mutate_other_fields() -> None:
    original = _placeholder_record()
    after = assign_run_reference(original, run_id=generate_ulid(timestamp_ms=0))
    assert after.target_expression == original.target_expression
    assert after.engine_name == original.engine_name
    assert after.test_results == original.test_results
