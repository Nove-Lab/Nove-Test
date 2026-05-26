"""Shared fixtures for `tests/unit/regression/`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.memory_entry import MemoryEntry
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


@pytest.fixture()
def initialized_store(tmp_path: Path) -> Path:
    """Create an initialized Project Store; return its `.novetest/` path."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return create_project_store(workspace).path


@pytest.fixture()
def make_test_result() -> Callable[..., TestResult]:
    """Factory fixture for ``TestResult`` instances."""

    def _make(
        node_id: str,
        outcome: str = "passed",
        *,
        duration_ms: int | None = 10,
        failure_reference: str | None = None,
    ) -> TestResult:
        return TestResult(
            node_id=node_id,
            outcome=outcome,
            duration_ms=duration_ms,
            failure_reference=failure_reference,
        )

    return _make


@pytest.fixture()
def make_run_record() -> Callable[..., RunRecord]:
    """Factory fixture for ``RunRecord`` instances.

    Keyword arguments:
        run_reference: required
        test_results: optional tuple of ``TestResult`` (default empty)
        target_expression: default "tests/"
        target_type: default "dir"
        engine_name: default "pytest"
        engine_version: default "8.2.0"
        ecosystem: default "python"
        artifact_paths: default {}
    """

    def _make(
        *,
        run_reference: RunReference,
        test_results: tuple[TestResult, ...] = (),
        target_expression: str = "tests/",
        target_type: str = "dir",
        engine_name: str = "pytest",
        engine_version: str | None = "8.2.0",
        ecosystem: str = "python",
        artifact_paths: dict[str, str] | None = None,
        status: str = "passed",
    ) -> RunRecord:
        return RunRecord(
            run_reference=run_reference,
            target_expression=target_expression,
            target_type=target_type,
            engine_name=engine_name,
            engine_version=engine_version,
            ecosystem=ecosystem,
            status=status,
            started_at=run_reference.created_at,
            completed_at=run_reference.created_at + 1_000,
            test_results=test_results,
            artifact_paths=dict(artifact_paths or {}),
        )

    return _make


@pytest.fixture()
def seed_run_record(
    make_run_record: Callable[..., RunRecord],
) -> Callable[..., MemoryEntry]:
    """Factory: persist a RunRecord into the Project Store and return the Memory entry."""

    def _seed(
        store_path: Path,
        *,
        run_reference: RunReference,
        test_results: tuple[TestResult, ...] = (),
        **record_kwargs: object,
    ) -> MemoryEntry:
        store = get_project_store_state(store_path)
        record = make_run_record(
            run_reference=run_reference,
            test_results=test_results,
            **record_kwargs,  # type: ignore[arg-type]
        )
        return store_run_evidence(store, record)

    return _seed
