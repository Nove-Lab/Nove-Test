"""Unit tests for the JUnit branch of `derive_coverage_facts`.

Covers the `coverage_xml` artifact key + JaCoCo XML dispatch, plus the
multi-module re-glob path. Uses an in-process `ProjectStore` with a
fabricated RunRecord and on-disk JaCoCo XML payload (no Maven/Gradle
required).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.derive import derive_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<report name="basic">
    <package name="com/example">
        <sourcefile name="Calculator.java">
            <line nr="3" mi="0" ci="3" mb="0" cb="0"/>
            <line nr="10" mi="3" ci="0" mb="0" cb="0"/>
        </sourcefile>
    </package>
</report>
"""


@pytest.fixture
def workspace_with_store(tmp_path: Path) -> tuple[ProjectStore, Path]:
    """Create a Project Store + a JaCoCo XML payload registered on a
    fresh RunRecord. Returns the store + the run-evidence directory."""

    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    artifact_rel = "run/artifacts/run_test/native/coverage.xml"
    artifact_abs = store.path / artifact_rel
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    artifact_abs.write_text(_JACOCO_XML, encoding="utf-8")

    record = RunRecord(
        run_reference=RunReference(run_id="test", created_at=1),
        target_expression="",
        target_type="workspace",
        engine_name="junit",
        ecosystem="java",
        engine_version="5.10.2",
        status="failed",
        started_at=1,
        completed_at=2,
        summary_counts={"total": 1, "passed": 0, "failed": 1},
        test_results=(),
        artifact_paths={"coverage_xml": artifact_rel},
        metadata={"native_exit_code": 1, "multi_module": "false"},
    )
    store_run_evidence(store, record)
    return store, artifact_abs


def test_derive_junit_jacoco_emits_fact_set(
    workspace_with_store: tuple[ProjectStore, Path],
) -> None:
    store, _ = workspace_with_store
    fact_set = derive_coverage_facts(
        store, RunReference(run_id="test", created_at=1)
    )
    assert isinstance(fact_set, CoverageFactSet)
    assert fact_set.engine_name == "junit"
    assert fact_set.mapping_granularity == "aggregate"
    assert len(fact_set.files) == 1
    fc = fact_set.files[0]
    assert fc.file_path == "src/main/java/com/example/Calculator.java"
    assert fc.executed_lines == (3,)
    assert fc.missing_lines == (10,)


def test_derive_junit_jacoco_missing_artifact(tmp_path: Path) -> None:
    """A RunRecord without a `coverage_xml` artifact key surfaces
    `missing-native-payload`."""

    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    record = RunRecord(
        run_reference=RunReference(run_id="nojacoco", created_at=1),
        target_expression="",
        target_type="workspace",
        engine_name="junit",
        ecosystem="java",
        engine_version="5.10.2",
        status="passed",
        started_at=1,
        completed_at=2,
        summary_counts={"total": 1, "passed": 1},
        test_results=(),
        artifact_paths={},  # no coverage_xml
        metadata={"native_exit_code": 0},
    )
    store_run_evidence(store, record)

    outcome = derive_coverage_facts(
        store, RunReference(run_id="nojacoco", created_at=1)
    )
    assert isinstance(outcome, CoverageUnavailable)
    assert outcome.reason == "missing-native-payload"


def test_derive_junit_jacoco_malformed_xml_surfaces_corrupt(
    tmp_path: Path,
) -> None:
    """A malformed JaCoCo XML payload surfaces
    `native-payload-corrupt`."""

    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    artifact_rel = "run/artifacts/run_bad/native/coverage.xml"
    (store.path / artifact_rel).parent.mkdir(parents=True, exist_ok=True)
    (store.path / artifact_rel).write_text(
        "<not closed", encoding="utf-8"
    )

    record = RunRecord(
        run_reference=RunReference(run_id="bad", created_at=1),
        target_expression="",
        target_type="workspace",
        engine_name="junit",
        ecosystem="java",
        engine_version="5.10.2",
        status="passed",
        started_at=1,
        completed_at=2,
        summary_counts={"total": 1, "passed": 1},
        test_results=(),
        artifact_paths={"coverage_xml": artifact_rel},
        metadata={"native_exit_code": 0},
    )
    store_run_evidence(store, record)

    outcome = derive_coverage_facts(
        store, RunReference(run_id="bad", created_at=1)
    )
    assert isinstance(outcome, CoverageUnavailable)
    assert outcome.reason == "native-payload-corrupt"
