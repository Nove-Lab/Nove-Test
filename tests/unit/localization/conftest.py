"""Shared fixtures for ``tests/unit/localization/``.

Each helper below is exposed as a pytest fixture so the test modules
call them via the fixture-injection seam (mirroring
``tests/unit/regression/conftest.py``). Helpers build real
``ProjectStore``s + ``RunRecord``s + ``CoverageFactSet``s through the
public seams (``create_project_store``, ``store_run_evidence``,
``write_coverage_facts``) — no Memory / Coverage mocks; the engine
tests stay honest about the on-disk shape.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from novetest.coverage.persistence import write_coverage_facts
from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.memory.store import delete_run_evidence, store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# Stable Run Reference so cache-path tests are predictable.
DEFAULT_REF = RunReference(
    run_id="01HDERIVE000000000000000XX", created_at=1_700_000_000_000
)


@dataclass(frozen=True)
class SeededRun:
    """Convenience bundle: store + record + facts after seeding."""

    store: ProjectStore
    record: RunRecord
    coverage: CoverageFactSet | None


def _summary(num_statements: int = 1) -> CoverageSummary:
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=num_statements,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


@pytest.fixture()
def default_ref() -> RunReference:
    return DEFAULT_REF


@pytest.fixture()
def make_file() -> Callable[[str, dict[int, tuple[str, ...]]], FileCoverage]:
    """Factory: build a ``FileCoverage`` for ``(file_path, line_contexts)``."""

    def _make(
        file_path: str, contexts: dict[int, tuple[str, ...]]
    ) -> FileCoverage:
        return FileCoverage(
            file_path=file_path,
            executed_lines=tuple(sorted(contexts.keys())),
            missing_lines=(),
            excluded_lines=(),
            executed_branches=(),
            missing_branches=(),
            summary=_summary(len(contexts) or 1),
            line_contexts=contexts,
        )

    return _make


@pytest.fixture()
def make_record() -> Callable[..., RunRecord]:
    """Factory: build a pytest ``RunRecord`` with the supplied test results."""

    def _make(
        *,
        test_results: tuple[TestResult, ...],
        run_reference: RunReference = DEFAULT_REF,
        target_expression: str = "tests/",
        target_type: str = "dir",
        status: str = "failed",
    ) -> RunRecord:
        return RunRecord(
            run_reference=run_reference,
            target_expression=target_expression,
            target_type=target_type,
            engine_name="pytest",
            engine_version="8.2.0",
            ecosystem="python",
            status=status,
            started_at=run_reference.created_at,
            completed_at=run_reference.created_at + 1_000,
            test_results=test_results,
        )

    return _make


@pytest.fixture()
def make_coverage() -> Callable[..., CoverageFactSet]:
    """Factory: build a per-test ``CoverageFactSet`` over a tuple of files."""

    def _make(
        *,
        files: tuple[FileCoverage, ...],
        run_reference: RunReference = DEFAULT_REF,
        mapping_granularity: str = "per-test",
    ) -> CoverageFactSet:
        total_lines = sum(len(f.executed_lines) for f in files) or 1
        return CoverageFactSet(
            run_reference=run_reference,
            engine_name="pytest",
            ecosystem="python",
            mapping_granularity=mapping_granularity,
            summary=_summary(total_lines),
            files=files,
            derived_at=run_reference.created_at + 500,
        )

    return _make


@pytest.fixture()
def seed_store() -> Callable[..., SeededRun]:
    """Factory: materialize a Project Store with one seeded run + optional coverage.

    Returns a ``SeededRun`` bundle. The store path is derived from the
    given ``workspace_dir`` (which becomes the parent of ``.novetest/``).
    """

    def _seed(
        workspace_dir: Path,
        *,
        record: RunRecord,
        coverage: CoverageFactSet | None,
        tombstone: bool = False,
    ) -> SeededRun:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        store = create_project_store(workspace_dir)
        store_run_evidence(store, record)
        if coverage is not None:
            write_coverage_facts(store, coverage)
        if tombstone:
            delete_run_evidence(store, record.run_reference)
        return SeededRun(store=store, record=record, coverage=coverage)

    return _seed


@pytest.fixture()
def write_python_module() -> Callable[[Path, str], None]:
    """Factory: write a Python source file at a given path (creates parents)."""

    def _write(path: Path, source: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    return _write
