"""Unit tests for the xunit (.NET / Coverlet) branch of `derive_coverage_facts`.

Covers the ``coverage_xml`` artifact key + Cobertura XML dispatch (same
key as junit but different parser; engine_name = "xunit" picks the
Cobertura branch). Uses an in-process ``ProjectStore`` with a
fabricated RunRecord and on-disk Cobertura XML payload (no dotnet
toolchain required). The integration counterpart at
``tests/integration/coverage/test_dotnet_cobertura_derive.py`` spawns a
real ``dotnet test --coverage`` against the fixture.

§2.4 binding: files whose resolved on-disk path does not exist are
silently dropped. If ALL files drop, the derive returns
``CoverageUnavailable(missing-native-payload)`` with a
``cobertura-sources-not-found`` discriminator. Both paths are exercised
below.

§2.6 binding: orchestration changes were NOT required — the existing
``coverage_outcome`` discrimination in ``orchestration/workflows/inspect.py``
already returns ``"fact-set"`` when ``derive_coverage_facts`` returns a
``CoverageFactSet``. The dispatch addition here is purely
engine_name-driven; pre-existing pytest / jest / cargo / junit paths
unchanged (covered by sibling tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.derive import derive_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.memory.project_store import (
    ProjectStore,
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


# Cobertura XML body referencing a class whose ``filename`` will exist
# on disk under tmp_path. Used as the happy-path fixture; tests rewrite
# ``{SOURCE_DIR}`` and write the matching source file before invoking
# derive so the §2.4 existence check passes.
_COBERTURA_HAPPY_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1" branch-rate="1" lines-covered="2" lines-valid="2"
          timestamp="0" version="6.0.2" complexity="0">
  <sources>
    <source>{SOURCE_DIR}</source>
  </sources>
  <packages>
    <package name="MathLib" line-rate="1" branch-rate="1" complexity="0">
      <classes>
        <class name="MathLib.MathOps" filename="MathLib/MathOps.cs"
               line-rate="1" branch-rate="1" complexity="0">
          <lines>
            <line number="14" hits="1" branch="false"/>
            <line number="15" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""

# Cobertura XML whose declared source path will NOT exist on disk —
# exercises the §2.4 "all-files-unresolvable" path.
_COBERTURA_NONEXISTENT_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0" branch-rate="0">
  <sources>
    <source>/non/existent/path</source>
  </sources>
  <packages>
    <package name="Ghost" line-rate="0" branch-rate="0" complexity="0">
      <classes>
        <class name="Ghost.Class" filename="Ghost/Ghost.cs" line-rate="0" branch-rate="0">
          <lines>
            <line number="1" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""

# Cobertura XML with no <class> elements — valid but empty report.
# Should NOT trigger sources-not-found per derive's "if raw_files and
# not surviving" guard.
_COBERTURA_NO_CLASSES = """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1" branch-rate="1">
  <sources/>
  <packages/>
</coverage>
"""


def _seed_xunit_run(
    store: ProjectStore,
    *,
    run_reference: RunReference,
    cobertura_body: str | None,
    workspace_files: dict[str, str] | None = None,
    coverage_xml_rel: str | None = None,
    register_artifact_key: bool = True,
) -> None:
    """Persist a xunit RunRecord with the given Cobertura XML on disk.

    ``cobertura_body``: the XML text. ``None`` means do NOT write the
    file (test the missing-file path).

    ``workspace_files``: optional dict of {relative_path: content} to
    write under ``store.path.parent`` (the workspace root) so §2.4's
    existence check passes for those files.

    ``coverage_xml_rel``: override the registered artifact_paths value;
    defaults to a canonical
    ``run/artifacts/run_<id>/native/TestResults/.../coverage.cobertura.xml``.

    ``register_artifact_key``: if False, omit the ``coverage_xml`` key
    entirely (exercises the no-artifact-key path).
    """
    workspace = store.path.parent
    if workspace_files:
        for rel, content in workspace_files.items():
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    if coverage_xml_rel is None:
        coverage_xml_rel = (
            f"run/artifacts/run_{run_reference.run_id}/native/"
            f"TestResults/aggregate/coverage.cobertura.xml"
        )
    if cobertura_body is not None:
        target = store.path / coverage_xml_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cobertura_body, encoding="utf-8")

    artifact_paths = (
        {"coverage_xml": coverage_xml_rel} if register_artifact_key else {}
    )

    record = RunRecord(
        run_reference=run_reference,
        target_expression="",
        target_type="workspace",
        engine_name="xunit",
        ecosystem="dotnet",
        engine_version="8.0.421",
        status="failed",
        started_at=1,
        completed_at=2,
        summary_counts={"total": 3, "passed": 2, "failed": 1},
        test_results=(),
        artifact_paths=artifact_paths,
        metadata={
            "native_exit_code": 1,
            "coverlet_version": "6.0.2",
            "dotnet_sdk_version": "8.0.421",
        },
    )
    store_run_evidence(store, record)


@pytest.fixture
def xunit_store(tmp_path: Path) -> tuple[ProjectStore, RunReference]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = get_project_store_state(create_project_store(workspace).path)
    run_ref = RunReference(run_id="dotnetA", created_at=1)
    return store, run_ref


# --- Happy-path dispatch -----------------------------------------------------


def test_derive_xunit_routes_engine_name_through_cobertura_parser(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """A ``xunit`` Run Record's Cobertura XML yields a real CoverageFactSet.

    Confirms ``derive_coverage_facts`` dispatches on ``engine_name`` to
    the Cobertura parser (NOT the JaCoCo parser — pointing a Cobertura
    XML at the JaCoCo parser would surface as ``native-payload-corrupt``
    because the root tag is ``<coverage>``, not ``<report>``).
    """
    store, run_ref = xunit_store
    workspace = store.path.parent
    body = _COBERTURA_HAPPY_TEMPLATE.format(SOURCE_DIR=str(workspace))
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=body,
        # Materialize the source file so §2.4 existence check passes.
        workspace_files={"MathLib/MathOps.cs": "// stub source"},
    )

    result = derive_coverage_facts(store, run_ref)

    assert isinstance(result, CoverageFactSet)
    assert result.engine_name == "xunit"
    assert result.ecosystem == "dotnet"
    # §2.5: hard-coded aggregate per amended Coverlet decision §3.
    assert result.mapping_granularity == "aggregate"
    assert result.metadata.get("coverage_format") == "cobertura-xml"
    assert [f.file_path for f in result.files] == ["MathLib/MathOps.cs"]
    assert result.files[0].executed_lines == (14,)
    assert result.files[0].missing_lines == (15,)


def test_derive_xunit_persists_facts_at_load_bearing_path(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """Memory's ``has_coverage_facts`` flag auto-flips because we write
    to the load-bearing ``coverage_facts.json`` path."""
    from novetest.coverage.persistence import coverage_facts_path

    store, run_ref = xunit_store
    workspace = store.path.parent
    body = _COBERTURA_HAPPY_TEMPLATE.format(SOURCE_DIR=str(workspace))
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=body,
        workspace_files={"MathLib/MathOps.cs": "// stub source"},
    )

    derive_coverage_facts(store, run_ref)

    assert coverage_facts_path(store, run_ref.run_id).is_file()


# --- Unavailable paths -------------------------------------------------------


def test_derive_xunit_run_without_coverage_xml_returns_unavailable(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """A xunit Run Record missing the ``coverage_xml`` artifact key
    surfaces as ``missing-native-payload``. The detail mentions the
    xunit-specific artifact key + Coverlet decision link so operators
    don't grep for the wrong one."""
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=None,
        register_artifact_key=False,
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "missing-native-payload"
    assert "coverage_xml" in (result.detail or "")
    # The detail should not reference cargo/python keys (would mislead
    # an operator debugging a dotnet run).
    assert "coverage_json" not in (result.detail or "")
    assert "coverage_lcov" not in (result.detail or "")


def test_derive_xunit_missing_xml_file_returns_unavailable(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """RunRecord registers ``coverage_xml`` but the file was removed.

    Same total-at-the-boundary contract as the JSON / LCOV / JaCoCo
    path analogs.
    """
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        # cobertura_body=None means do NOT write the file, but the
        # artifact key IS registered.
        cobertura_body=None,
        register_artifact_key=True,
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "missing-native-payload"


def test_derive_xunit_malformed_xml_returns_corrupt(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """A malformed Cobertura body surfaces as ``native-payload-corrupt``."""
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        # Truncated XML — opens <coverage> without closing it.
        cobertura_body="<?xml version='1.0'?><coverage><packages>",
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "native-payload-corrupt"


def test_derive_xunit_wrong_root_tag_returns_corrupt(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """Pointing a JaCoCo XML (root=<report>) at the xunit dispatch
    surfaces as corrupt — protects against artifact-key collision
    bugs where someone wires JaCoCo XML into a xunit RunRecord."""
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=(
            '<?xml version="1.0"?><report name="not-cobertura"/>'
        ),
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "native-payload-corrupt"


def test_derive_xunit_all_sources_unresolvable_returns_sources_not_found(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """§2.4: when every class resolves to a non-existent file, derive
    returns ``CoverageUnavailable(missing-native-payload)`` with a
    ``cobertura-sources-not-found`` discriminator so operators can
    distinguish "no coverage data" from "user moved the source tree"."""
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=_COBERTURA_NONEXISTENT_TEMPLATE,
        # NO workspace_files — Ghost/Ghost.cs does not exist.
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "missing-native-payload"
    assert "cobertura-sources-not-found" in (result.detail or "")


def test_derive_xunit_empty_packages_returns_empty_fact_set(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """A Cobertura XML with no <class> elements yields a valid empty
    FactSet, NOT a sources-not-found error (zero classes is different
    from "had classes but they all dropped")."""
    store, run_ref = xunit_store
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=_COBERTURA_NO_CLASSES,
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageFactSet)
    assert result.files == ()
    assert result.summary.num_statements == 0
    assert result.mapping_granularity == "aggregate"


def test_derive_xunit_partial_survival_drops_only_missing_files(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """When some Cobertura classes resolve and some don't, the surviving
    set is what gets persisted; summary is recomputed accordingly."""
    store, run_ref = xunit_store
    workspace = store.path.parent
    # Two classes — A exists on disk, B doesn't.
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.5" branch-rate="0">
  <sources>
    <source>{workspace}</source>
  </sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.RealFile" filename="App/RealFile.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
            <line number="2" hits="0" branch="false"/>
          </lines>
        </class>
        <class name="App.MovedFile" filename="App/MovedFile.cs" line-rate="0" branch-rate="0">
          <lines>
            <line number="1" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""
    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=body,
        # Only RealFile materialized on disk.
        workspace_files={"App/RealFile.cs": "// real"},
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageFactSet)
    # MovedFile dropped per §2.4; RealFile survives.
    assert [f.file_path for f in result.files] == ["App/RealFile.cs"]
    # Summary recomputed from the surviving file (NOT the original 3
    # statements that the raw XML described).
    assert result.summary.num_statements == 2
    assert result.summary.covered_statements == 1


def test_derive_xunit_directory_artifact_globs_xml_children(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """Forward-compat: when the adapter registers ``coverage_xml`` as a
    DIRECTORY (the per-test mode the dotnet adapter takes when the
    inert-today ``<PerTestCoverage>`` element starts working), derive
    globs ``*.cobertura.xml`` files inside it."""
    store, run_ref = xunit_store
    workspace = store.path.parent
    body = _COBERTURA_HAPPY_TEMPLATE.format(SOURCE_DIR=str(workspace))

    # Build a directory full of cobertura XMLs and register the
    # directory itself as the coverage_xml artifact.
    dir_rel = (
        f"run/artifacts/run_{run_ref.run_id}/native/TestResults/per-test"
    )
    dir_abs = store.path / dir_rel
    dir_abs.mkdir(parents=True, exist_ok=True)
    (dir_abs / "coverage.test1.cobertura.xml").write_text(body, encoding="utf-8")
    (dir_abs / "coverage.test2.cobertura.xml").write_text(body, encoding="utf-8")
    # Distractor file that should be ignored by the glob.
    (dir_abs / "coverage.json").write_text("{}", encoding="utf-8")

    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=None,  # don't auto-write a single XML
        coverage_xml_rel=dir_rel,
        workspace_files={"MathLib/MathOps.cs": "// stub source"},
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageFactSet)
    # Both XMLs reference MathOps.cs; final state collapses to one
    # FileCoverage entry (last-write-wins per parser docstring).
    assert [f.file_path for f in result.files] == ["MathLib/MathOps.cs"]


def test_derive_xunit_empty_directory_artifact_returns_unavailable(
    xunit_store: tuple[ProjectStore, RunReference],
) -> None:
    """A registered directory with NO Cobertura XMLs inside surfaces
    as ``missing-native-payload``."""
    store, run_ref = xunit_store
    dir_rel = (
        f"run/artifacts/run_{run_ref.run_id}/native/TestResults/empty-dir"
    )
    (store.path / dir_rel).mkdir(parents=True, exist_ok=True)

    _seed_xunit_run(
        store,
        run_reference=run_ref,
        cobertura_body=None,
        coverage_xml_rel=dir_rel,
    )

    result = derive_coverage_facts(store, run_ref)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == "missing-native-payload"
    assert "*.cobertura.xml" in (result.detail or "") or "cobertura" in (
        result.detail or ""
    )
