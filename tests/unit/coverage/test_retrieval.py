"""Unit tests for `novetest.coverage.retrieval`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from novetest.coverage import derive_coverage_facts, get_coverage_facts
from novetest.coverage.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_NOT_FOUND,
    CoverageUnavailable,
)
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


def test_get_returns_previously_derived_facts(
    initialized_store: Path,
    sample_coverage_payload: dict[str, Any],
    sample_run_reference: RunReference,
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)
    derived = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(derived, CoverageFactSet)

    cached = get_coverage_facts(store, sample_run_reference)
    assert isinstance(cached, CoverageFactSet)
    assert cached == derived


def test_get_without_derived_facts_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """Run exists, but derive has not been called yet."""
    store = get_project_store_state(initialized_store)
    store_run_evidence(
        store, make_run_record(run_reference=sample_run_reference)
    )

    result = get_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
    assert result.run_reference == sample_run_reference


def test_get_missing_run_returns_run_not_found(
    initialized_store: Path,
    sample_run_reference: RunReference,
) -> None:
    """Stale references get a clean signal instead of a Memory exception."""
    store = get_project_store_state(initialized_store)
    result = get_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND


def test_get_does_not_auto_derive(
    initialized_store: Path,
    sample_coverage_payload: dict[str, Any],
    sample_run_reference: RunReference,
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    """`get` is cache-read only; the External `coverage show` workflow
    stitches get-then-derive together in Orchestration. If `get` ever
    auto-derived, the contract would collapse."""
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)
    result = get_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
