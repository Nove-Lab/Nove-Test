"""Unit tests for `novetest.coverage.availability`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from novetest.coverage import (
    CoverageAvailability,
    check_coverage_availability,
    derive_coverage_facts,
)
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import (
    get_memory_entry_availability,
    store_run_evidence,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


def test_unknown_run_returns_unavailable(
    initialized_store: Path, sample_run_reference: RunReference,
) -> None:
    store = get_project_store_state(initialized_store)
    result = check_coverage_availability(store, sample_run_reference)
    assert isinstance(result, CoverageAvailability)
    assert result.available is False
    assert result.run_exists is False
    assert result.facts_persisted is False
    assert result.native_payload_present is False
    assert result.reason == "run-not-found"


def test_run_without_coverage_artifact_is_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    store = get_project_store_state(initialized_store)
    store_run_evidence(
        store, make_run_record(run_reference=sample_run_reference)
    )

    result = check_coverage_availability(store, sample_run_reference)
    assert result.run_exists is True
    assert result.available is False
    assert result.facts_persisted is False
    assert result.native_payload_present is False
    assert result.reason == "no-coverage-evidence"


def test_native_payload_present_makes_run_derivable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    sample_coverage_payload: dict[str, Any],
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    """A run with the native coverage.json on disk is available for derive,
    even before `derive_coverage_facts` has been called."""
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)

    result = check_coverage_availability(store, sample_run_reference)
    assert result.available is True
    assert result.native_payload_present is True
    assert result.facts_persisted is False
    assert result.reason is None


def test_derived_facts_makes_run_available(
    initialized_store: Path,
    sample_run_reference: RunReference,
    sample_coverage_payload: dict[str, Any],
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)
    derive_coverage_facts(store, sample_run_reference)

    result = check_coverage_availability(store, sample_run_reference)
    assert result.available is True
    assert result.facts_persisted is True


def test_availability_agrees_with_memorys_has_coverage_facts_flag(
    initialized_store: Path,
    sample_run_reference: RunReference,
    sample_coverage_payload: dict[str, Any],
    make_run_record: Callable[..., RunRecord],
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    """Charter rule: ``check_coverage_availability`` must agree with Memory's
    ``has_coverage_facts`` flag without importing Memory's private helpers.

    We check the two answers in lockstep across the three meaningful states:
    no native + no derived  |  native + no derived  |  native + derived.
    """
    store = get_project_store_state(initialized_store)

    # State 1: no native payload, no derived facts.
    store_run_evidence(
        store, make_run_record(run_reference=sample_run_reference)
    )
    availability = check_coverage_availability(store, sample_run_reference)
    flags = get_memory_entry_availability(store, sample_run_reference)
    assert availability.facts_persisted == flags["has_coverage_facts"] is False

    # State 2: write native payload (still no derived).
    sample_ref_2 = RunReference(
        run_id="01HSECOND0000000000000000F", created_at=1_700_000_000_001,
    )
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_ref_2,
        coverage_json_payload=sample_coverage_payload,
    )
    availability_2 = check_coverage_availability(store, sample_ref_2)
    flags_2 = get_memory_entry_availability(store, sample_ref_2)
    assert (
        availability_2.facts_persisted
        == flags_2["has_coverage_facts"]
        is False
    )
    assert availability_2.native_payload_present is True

    # State 3: derive runs, persists facts. Both surfaces flip to True.
    derive_coverage_facts(store, sample_ref_2)
    availability_3 = check_coverage_availability(store, sample_ref_2)
    flags_3 = get_memory_entry_availability(store, sample_ref_2)
    assert (
        availability_3.facts_persisted
        == flags_3["has_coverage_facts"]
        is True
    )


def test_check_does_not_raise_on_uninitialized_workflow(
    initialized_store: Path,
) -> None:
    """check_coverage_availability is "pure filesystem probing" — it must
    never raise. Pass an obviously-bogus run id and expect a clean snapshot."""
    store = get_project_store_state(initialized_store)
    bogus = RunReference(run_id="DOES_NOT_EXIST", created_at=1)
    result = check_coverage_availability(store, bogus)
    assert isinstance(result, CoverageAvailability)
    assert result.available is False
    assert result.run_exists is False
