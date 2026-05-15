"""Shared fixtures for `tests/unit/coverage/`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from novetest.coverage.persistence import write_coverage_facts
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_coverage_payload() -> dict[str, Any]:
    """Coverage.py 7.x JSON payload with show_contexts=True.

    Two files: ``src/pkg/calc.py`` (partial coverage, one branch
    deliberately uncovered) and ``src/pkg/util.py`` (100%).
    """
    raw = (FIXTURES_DIR / "sample_coverage.json").read_text(encoding="utf-8")
    return json.loads(raw)


@pytest.fixture()
def sample_run_reference() -> RunReference:
    return RunReference(
        run_id="01HCOV0000000000000000FACT",
        created_at=1_700_000_000_000,
    )


@pytest.fixture()
def initialized_store(tmp_path: Path) -> Path:
    """Create an initialized Project Store; return its `.novetest/` path.

    Tests use ``get_project_store_state(path)`` to obtain the live handle.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return create_project_store(workspace).path


@pytest.fixture()
def make_run_record() -> Callable[..., RunRecord]:
    """Factory fixture for minimal `RunRecord` instances.

    Keyword arguments:
        run_reference: required
        artifact_paths: optional, defaults to {}
        engine_name: defaults to "pytest"
        ecosystem: defaults to "python"
    """

    def _make(
        *,
        run_reference: RunReference,
        artifact_paths: dict[str, str] | None = None,
        engine_name: str = "pytest",
        ecosystem: str = "python",
    ) -> RunRecord:
        return RunRecord(
            run_reference=run_reference,
            target_expression="tests/",
            target_type="dir",
            engine_name=engine_name,
            ecosystem=ecosystem,
            status="passed",
            started_at=run_reference.created_at,
            artifact_paths=dict(artifact_paths or {}),
        )

    return _make


@pytest.fixture()
def seed_run_with_coverage(
    make_run_record: Callable[..., RunRecord],
) -> Callable[..., RunRecord]:
    """Factory: persist a RunRecord AND drop coverage.json into native/.

    The persisted RunRecord registers ``artifact_paths["coverage_json"]``
    pointing at the file we just wrote — exactly what Run Team's pytest
    coverage-emission slice will produce.

    Returns the persisted RunRecord.
    """

    def _seed(
        store_path: Path,
        *,
        run_reference: RunReference,
        coverage_json_payload: dict[str, Any],
    ) -> RunRecord:
        store = get_project_store_state(store_path)
        rel = (
            f"run/artifacts/run_{run_reference.run_id}/native/coverage.json"
        )
        native_dir = store.path / Path(rel).parent
        native_dir.mkdir(parents=True, exist_ok=True)
        (store.path / rel).write_text(
            json.dumps(coverage_json_payload), encoding="utf-8"
        )
        record = make_run_record(
            run_reference=run_reference,
            artifact_paths={"coverage_json": rel},
        )
        store_run_evidence(store, record)
        return record

    return _seed


@pytest.fixture()
def seed_fact_set(
    make_run_record: Callable[..., RunRecord],
) -> Callable[..., None]:
    """Factory: persist a RunRecord AND a CoverageFactSet for that run.

    Used by tests that need to set up two-or-more runs with already-derived
    facts (e.g. ``compare_coverage_facts``) without going through the
    coverage.py JSON path.
    """

    def _seed(store_path: Path, fact_set: CoverageFactSet) -> None:
        store = get_project_store_state(store_path)
        store_run_evidence(
            store,
            make_run_record(run_reference=fact_set.run_reference),
        )
        write_coverage_facts(store, fact_set)

    return _seed
