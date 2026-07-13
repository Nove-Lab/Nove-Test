"""Unit tests for the JUnit branch of `derive_coverage_facts`.

Covers the `coverage_xml` artifact key + JaCoCo XML dispatch, plus the
multi-module re-glob path. Uses an in-process `ProjectStore` with a
fabricated RunRecord and on-disk JaCoCo XML payload (no Maven/Gradle
required).

ANA-05 (Gate-1 Q3-A) binding: JaCoCo `file_path`s are COMPOSED under
the standard Maven/Gradle ``src/main/java`` layout (the v1 contract),
so derive drops entries whose composed path does not exist on disk —
mirroring the Cobertura branch's §2.4 filter. If the XML had files but
NONE survive, derive returns
``CoverageUnavailable(missing-native-payload)`` with a
``jacoco-sources-not-found`` discriminator. All three shapes (no-op on
standard layout / partial survival / all-dropped) are exercised below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.derive import derive_coverage_facts
from novetest.coverage.jacoco_parser import parse_jacoco_xml
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

# Two sourcefiles — Calculator.java gets materialized on disk by the
# ANA-05 partial-survival test; Ghost.java never does.
_JACOCO_XML_TWO_FILES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<report name="mixed">
    <package name="com/example">
        <sourcefile name="Calculator.java">
            <line nr="3" mi="0" ci="3" mb="0" cb="0"/>
            <line nr="10" mi="3" ci="0" mb="0" cb="0"/>
        </sourcefile>
        <sourcefile name="Ghost.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
            <line nr="2" mi="0" ci="1" mb="0" cb="0"/>
        </sourcefile>
    </package>
</report>
"""

# Workspace-relative path the parser composes for Calculator.java.
_CALCULATOR_REL = "src/main/java/com/example/Calculator.java"


@pytest.fixture
def workspace_with_store(tmp_path: Path) -> tuple[ProjectStore, Path]:
    """Create a Project Store + a JaCoCo XML payload registered on a
    fresh RunRecord, with the composed source path materialized on disk
    (standard Maven/Gradle layout) so the ANA-05 existence filter is a
    no-op. Returns the store + the XML artifact path."""

    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    artifact_rel = "run/artifacts/run_test/native/coverage.xml"
    artifact_abs = store.path / artifact_rel
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    artifact_abs.write_text(_JACOCO_XML, encoding="utf-8")

    source_abs = workspace / _CALCULATOR_REL
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    source_abs.write_text("// stub source", encoding="utf-8")

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


# --- ANA-05: disk-existence filter on composed paths -------------------------


def _seed_junit_run(
    tmp_path: Path,
    *,
    run_id: str,
    jacoco_xml: str,
    workspace_files: tuple[str, ...] = (),
) -> ProjectStore:
    """Store + junit RunRecord with ``jacoco_xml`` registered under
    ``coverage_xml``. ``workspace_files`` are workspace-relative paths
    materialized on disk so the ANA-05 existence check passes for them.
    """

    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    artifact_rel = f"run/artifacts/run_{run_id}/native/coverage.xml"
    artifact_abs = store.path / artifact_rel
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    artifact_abs.write_text(jacoco_xml, encoding="utf-8")

    for rel in workspace_files:
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// stub source", encoding="utf-8")

    record = RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=1),
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
    return store


def test_derive_junit_jacoco_standard_layout_unaffected_by_filter(
    workspace_with_store: tuple[ProjectStore, Path],
) -> None:
    """ANA-05 negative space: when every composed path exists on disk
    (standard Maven/Gradle layout), the existence filter is a no-op —
    derived facts are identical to the raw parser output field-for-field
    (modulo the ``derived_at`` timestamp, pinned here by reuse)."""

    store, artifact_abs = workspace_with_store
    run_ref = RunReference(run_id="test", created_at=1)

    derived = derive_coverage_facts(store, run_ref)
    assert isinstance(derived, CoverageFactSet)

    raw = parse_jacoco_xml(
        [artifact_abs],
        run_reference=run_ref,
        engine_name="junit",
        ecosystem="java",
        workspace_root=store.path.parent,
        derived_at=derived.derived_at,
    )
    assert derived == raw


def test_derive_junit_jacoco_partial_survival_drops_only_missing_files(
    tmp_path: Path,
) -> None:
    """ANA-05: when some composed paths exist and some don't, only the
    existing files survive; the summary is recomputed from the
    survivors (NOT the raw XML's 4-statement roll-up)."""

    store = _seed_junit_run(
        tmp_path,
        run_id="mixed",
        jacoco_xml=_JACOCO_XML_TWO_FILES,
        # Only Calculator.java materialized; Ghost.java stays missing.
        workspace_files=(_CALCULATOR_REL,),
    )

    result = derive_coverage_facts(
        store, RunReference(run_id="mixed", created_at=1)
    )
    assert isinstance(result, CoverageFactSet)
    assert [f.file_path for f in result.files] == [_CALCULATOR_REL]
    # Recomputed from the surviving file only: 2 statements, 1 covered
    # (the raw XML described 4 statements, 3 covered across both files).
    assert result.summary.num_statements == 2
    assert result.summary.covered_statements == 1


def test_derive_junit_jacoco_all_sources_missing_returns_sources_not_found(
    tmp_path: Path,
) -> None:
    """ANA-05: when NO composed path exists on disk (non-standard
    source layout, or the tree moved post-run), derive returns
    ``CoverageUnavailable(missing-native-payload)`` with the
    ``jacoco-sources-not-found`` detail discriminator (symmetrical with
    the Cobertura branch's ``cobertura-sources-not-found``)."""

    store = _seed_junit_run(
        tmp_path,
        run_id="ghost",
        jacoco_xml=_JACOCO_XML,
        workspace_files=(),  # nothing materialized on disk
    )

    result = derive_coverage_facts(
        store, RunReference(run_id="ghost", created_at=1)
    )
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "missing-native-payload"
    assert "jacoco-sources-not-found" in (result.detail or "")
