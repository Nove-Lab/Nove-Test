"""Implementation of ``derive_coverage_facts``.

Workflow (from ``design/workflows/coverage.md``):

    derive_coverage_facts(run_reference) -> memory/retrieve_run_evidence

We resolve the Memory Entry for the run, look up the native coverage
payload (artifact key depends on engine: ``coverage_json`` for
pytest / jest, ``coverage_lcov`` for cargo-test,
``coverage_xml`` for junit (JaCoCo) and xunit (Coverlet Cobertura)),
parse it through the engine-appropriate parser, persist the resulting
``CoverageFactSet`` so subsequent ``get_coverage_facts`` calls hit
cache, and return the fact set.

go-test is NOT a ``coverage_json`` consumer: its adapter registers a
cover profile under ``coverage_profile``, but that key is unconsumed —
coverage derivation for go-test is unimplemented, so go-test runs fall
into the default branch, find no ``coverage_json`` entry, and return
the honest ``missing-native-payload`` unavailable outcome (ANA-16).

Missing or unregistered native payload is an **explicit unavailable
outcome** (REQ-COV-004), not an exception. Corrupt payloads (JSON,
LCOV, or XML) are propagated as
``CoverageUnavailable(reason="native-payload-corrupt")`` to keep the
operation total at the engine boundary.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from novetest.coverage import _summary
from novetest.coverage.cobertura_parser import parse_cobertura_xml
from novetest.coverage.istanbul_parser import parse_istanbul_json
from novetest.coverage.jacoco_parser import parse_jacoco_xml
from novetest.coverage.lcov_parser import parse_lcov
from novetest.coverage.parser import CoverageJsonParseError, parse_coverage_json
from novetest.coverage.persistence import write_coverage_facts
from novetest.coverage.results import (
    REASON_MISSING_NATIVE_PAYLOAD,
    REASON_NATIVE_PAYLOAD_CORRUPT,
    REASON_RUN_NOT_FOUND,
    CoverageUnavailable,
)
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RunEvidenceNotFoundError, retrieve_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    FileCoverage,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


# The pinned artifact-key Run Team registers for the coverage.py JSON
# payload. Coverage's contract with Run is that this key, if present,
# points to a Project-Store-relative path to the coverage.py JSON file.
COVERAGE_JSON_ARTIFACT_KEY = "coverage_json"

# Cargo's adapter registers LCOV text at a distinct artifact key — the
# cargo path uses ``cargo llvm-cov nextest --lcov`` which produces a
# completely different format from coverage.py / Istanbul JSON. The
# cargo branch in ``derive_coverage_facts`` dispatches on
# ``engine_name == "cargo-test"`` and resolves THIS key, not
# ``coverage_json``. See
# ``src/novetest/run/adapters/cargo_adapter.py:311`` for the registration.
COVERAGE_LCOV_ARTIFACT_KEY = "coverage_lcov"

# JUnit's adapter registers JaCoCo XML under ``coverage_xml``. The
# dotnet (xunit) adapter ALSO registers under ``coverage_xml`` — same
# key, different XML schema (Coverlet Cobertura instead of JaCoCo).
# Both branches read the same artifact_paths entry; the engine_name
# dispatch picks the right parser. pytest/jest also write Cobertura/XML
# alongside JSON but we always prefer the JSON path for those engines
# (their derive falls into the default JSON branch, not either of the
# XML branches). Multi-module Maven workspaces register the FIRST
# module's XML on the RunRecord and the junit derive branch re-globs
# siblings via the ``metadata["multi_module"] == "true"`` flag.
COVERAGE_JACOCO_XML_ARTIFACT_KEY = "coverage_xml"
COVERAGE_COBERTURA_XML_ARTIFACT_KEY = "coverage_xml"

# Engine names the adapters set on their ``NativeResult`` /
# ``RunRecord.engine_name``. The literal values are contractual — Run
# team pins them in each adapter; the dispatch here matches against
# them. See ``run/adapters/{cargo,junit,dotnet}_adapter.py`` for the
# canonical pins.
_CARGO_ENGINE_NAME = "cargo-test"
_JUNIT_ENGINE_NAME = "junit"
_XUNIT_ENGINE_NAME = "xunit"


def derive_coverage_facts(
    store: ProjectStore, run_reference: RunReference
) -> CoverageFactSet | CoverageUnavailable:
    """Derive structured ``CoverageFactSet`` for ``run_reference``.

    Side effect: writes ``<store>/coverage/facts/run_<id>/coverage_facts.json``
    on success so subsequent ``get_coverage_facts`` calls (and Memory's
    ``has_coverage_facts`` flag) reflect the new state.

    Returns ``CoverageUnavailable`` rather than raising for the expected
    "this run has no coverage payload" / "the JSON file is gone" /
    "the JSON file is corrupt" conditions. Programmer errors (e.g. the
    payload references a path outside the store) still raise.
    """
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError as exc:
        return CoverageUnavailable(
            reason=REASON_RUN_NOT_FOUND,
            detail=str(exc),
            run_reference=run_reference,
        )

    record = entry.run_record

    # Cargo-test uses LCOV at a distinct artifact key and a non-JSON
    # text format — different read path, different parser, different
    # error vocabulary. Branch early so the rest of this function keeps
    # the simple "JSON payload at coverage_json key" mental model.
    if record.engine_name == _CARGO_ENGINE_NAME:
        return _derive_cargo_lcov(store, record)
    # JUnit uses JaCoCo XML at a third distinct key. Multi-module Maven
    # workspaces re-glob siblings under the workspace root from inside
    # the branch.
    if record.engine_name == _JUNIT_ENGINE_NAME:
        return _derive_junit_jacoco(store, record)
    # xunit (.NET) uses Coverlet Cobertura XML at the same ``coverage_xml``
    # key as JUnit but a completely different XML schema. The engine_name
    # dispatch picks the right parser; the artifact key collision is
    # intentional (matches the v1 .NET adapter's pattern precedent).
    if record.engine_name == _XUNIT_ENGINE_NAME:
        return _derive_xunit_cobertura(store, record)

    # SYNC NOTE (ANA-16): there is deliberately NO go-test branch — the
    # gotest adapter registers a cover profile under ``coverage_profile``
    # but no parser consumes it, so go-test falls through to the default
    # ``coverage_json`` lookup below and returns missing-native-payload
    # (honestly unavailable). A future go coverage slice must update
    # THREE sites together: this dispatch (add the branch + a
    # ``coverage_profile`` key constant), ``_COVERAGE_ARTIFACT_KEYS`` in
    # ``availability.py``, and the adapter's key registration
    # (``run/adapters/gotest_adapter.py``).
    rel_path = record.artifact_paths.get(COVERAGE_JSON_ARTIFACT_KEY)
    if not rel_path:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"RunRecord.artifact_paths has no {COVERAGE_JSON_ARTIFACT_KEY!r} "
                "entry; this run was executed without coverage collection"
            ),
            run_reference=record.run_reference,
        )

    coverage_json_path = store.path / rel_path
    if not coverage_json_path.is_file():
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"Native coverage payload not found on disk at {coverage_json_path}"
            ),
            run_reference=record.run_reference,
        )

    try:
        raw_text = coverage_json_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=f"Could not read/parse {coverage_json_path}: {exc}",
            run_reference=record.run_reference,
        )

    if not isinstance(payload, dict):
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=(
                f"coverage.py JSON at {coverage_json_path} is not a top-level "
                "object"
            ),
            run_reference=record.run_reference,
        )

    # Engine dispatch: jest emits Istanbul `coverage-final.json`, a
    # different shape from coverage.py's JSON. Both parsers raise
    # `CoverageJsonParseError` on a shape mismatch so the unavailable
    # outcome below stays uniform.
    try:
        if record.engine_name == "jest":
            fact_set = parse_istanbul_json(
                payload,
                run_reference=record.run_reference,
                engine_name=record.engine_name,
                ecosystem=record.ecosystem,
                workspace_root=store.path.parent,
            )
        else:
            fact_set = parse_coverage_json(
                payload,
                run_reference=record.run_reference,
                engine_name=record.engine_name,
                ecosystem=record.ecosystem,
            )
    except CoverageJsonParseError as exc:
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=str(exc),
            run_reference=record.run_reference,
        )

    write_coverage_facts(store, fact_set)
    return fact_set


def _derive_cargo_lcov(
    store: ProjectStore, record: RunRecord,
) -> CoverageFactSet | CoverageUnavailable:
    """Cargo-test branch: parse the LCOV artifact and persist facts.

    Same total-at-the-boundary contract as the JSON path:
    ``CoverageUnavailable(missing-native-payload)`` for absent / unreg-
    istered artifact, ``CoverageUnavailable(native-payload-corrupt)``
    for malformed LCOV. Other failure modes (e.g. invariant violation
    inside the model layer) propagate as exceptions.
    """
    rel_path = record.artifact_paths.get(COVERAGE_LCOV_ARTIFACT_KEY)
    if not rel_path:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"RunRecord.artifact_paths has no {COVERAGE_LCOV_ARTIFACT_KEY!r} "
                "entry; this cargo-test run was executed without coverage collection"
            ),
            run_reference=record.run_reference,
        )

    lcov_path = store.path / rel_path
    if not lcov_path.is_file():
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=f"Native LCOV payload not found on disk at {lcov_path}",
            run_reference=record.run_reference,
        )

    try:
        fact_set = parse_lcov(
            lcov_path,
            run_reference=record.run_reference,
            engine_name=record.engine_name,
            ecosystem=record.ecosystem,
            # The .novetest/ directory's PARENT is the workspace root —
            # the same convention `derive_coverage_facts` uses to convert
            # Istanbul's absolute paths in the jest branch.
            workspace_root=store.path.parent,
        )
    except CoverageJsonParseError as exc:
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=str(exc),
            run_reference=record.run_reference,
        )

    write_coverage_facts(store, fact_set)
    return fact_set


def _derive_junit_jacoco(
    store: ProjectStore, record: RunRecord,
) -> CoverageFactSet | CoverageUnavailable:
    """Junit branch: parse the JaCoCo XML artifact(s) and persist facts.

    Single-module Maven / Gradle: parse the one XML pointed to by
    ``artifact_paths["coverage_xml"]``.

    Multi-module Maven (``metadata["multi_module"] == "true"``): re-glob
    ``<workspace_root>/*/target/site/jacoco/jacoco.xml`` so every
    module's XML contributes a per-module-prefixed FileCoverage entry
    to the shared CoverageFactSet. The per-module prefix matches the
    module directory name relative to the workspace root, mirroring
    brief §6 D2 ratification.

    Same total-at-the-boundary contract as the LCOV / JSON paths:
    ``CoverageUnavailable(missing-native-payload)`` for absent /
    unregistered artifact, ``CoverageUnavailable(native-payload-corrupt)``
    for malformed XML.
    """

    rel_path = record.artifact_paths.get(COVERAGE_JACOCO_XML_ARTIFACT_KEY)
    if not rel_path:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"RunRecord.artifact_paths has no "
                f"{COVERAGE_JACOCO_XML_ARTIFACT_KEY!r} entry; this junit "
                "run was executed without coverage collection, or the "
                "user's project did not declare a JaCoCo plugin"
            ),
            run_reference=record.run_reference,
        )

    primary_xml = store.path / rel_path
    if not primary_xml.is_file():
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=f"Native JaCoCo XML payload not found on disk at {primary_xml}",
            run_reference=record.run_reference,
        )

    workspace_root = store.path.parent
    xml_paths: list[Path] = [primary_xml]
    module_prefix_for: dict[str, str] = {}

    multi_module_flag = record.metadata.get("multi_module")
    if multi_module_flag == "true":
        # Re-glob siblings. The workspace_root contains module subdirs;
        # each holds target/site/jacoco/jacoco.xml. The primary_xml
        # itself is one of these — re-discover all so the per-module
        # prefix mapping is uniform.
        xml_paths = []
        for module_xml in sorted(
            workspace_root.glob("*/target/site/jacoco/jacoco.xml")
        ):
            xml_paths.append(module_xml)
            # target/site/jacoco/jacoco.xml → 4 levels up is the module dir
            module_dir = module_xml.parents[3]
            module_prefix_for[str(module_xml)] = module_dir.name
        if not xml_paths:
            # Multi-module flag set but no XMLs found — TOCTOU?
            return CoverageUnavailable(
                reason=REASON_MISSING_NATIVE_PAYLOAD,
                detail=(
                    f"multi_module=true on RunRecord but no per-module "
                    f"jacoco.xml found under {workspace_root}/*/target/"
                    f"site/jacoco/"
                ),
                run_reference=record.run_reference,
            )

    try:
        fact_set = parse_jacoco_xml(
            xml_paths,
            run_reference=record.run_reference,
            engine_name=record.engine_name,
            ecosystem=record.ecosystem,
            workspace_root=workspace_root,
            module_prefix_for=module_prefix_for or None,
        )
    except CoverageJsonParseError as exc:
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=str(exc),
            run_reference=record.run_reference,
        )

    write_coverage_facts(store, fact_set)
    return fact_set


# Glob pattern for per-test mode (currently empirically inert per
# decision 2026-06-03 §3 amendment, but a future Coverlet release that
# fixes the XPlat data collector pipe would emit files matching this
# glob under the ``coverage_xml`` artifact directory). Includes the
# aggregate filename too so an adapter that registers the parent
# directory regardless of mode still finds the file. See
# ``run/adapters/dotnet_adapter.py::_glob_coverage_xml`` for the
# Run-side counterpart.
_COBERTURA_GLOB = "*.cobertura.xml"


def _derive_xunit_cobertura(
    store: ProjectStore, record: RunRecord,
) -> CoverageFactSet | CoverageUnavailable:
    """Xunit (.NET) branch: parse the Coverlet Cobertura XML artifact(s).

    The dotnet adapter registers ``artifact_paths["coverage_xml"]`` to
    EITHER a single ``coverage.cobertura.xml`` file (aggregate-effective
    default per decision 2026-06-03 §3 amendment) OR a parent directory
    containing ``coverage.<slug>.cobertura.xml`` per-test files (the
    forward-compat path for a future Coverlet release that fixes the
    empirically-inert XPlat ``<PerTestCoverage>`` element). This helper
    handles both shapes.

    Per task brief §2.4, source files that no longer exist on disk are
    silently dropped — the Cobertura XML is still valuable evidence
    even when the user moved the source tree post-run, but coverage
    facts that point at non-existent files would just confuse
    downstream verbs. If ZERO files resolve to on-disk paths, this
    returns ``CoverageUnavailable(missing-native-payload)`` with a
    ``cobertura-sources-not-found`` discriminator in the detail string.

    Per task brief §2.5, ``mapping_granularity`` is hard-coded
    ``aggregate`` by the parser (per decision 2026-06-03 §3 amended:
    Coverlet XPlat path is aggregate-effective-default; per-test is
    deferred to a future Coverlet release or a separate
    ``coverlet.msbuild`` opt-in slice).

    Same total-at-the-boundary contract as the JSON / LCOV / JaCoCo
    paths: ``CoverageUnavailable(missing-native-payload)`` for absent /
    unregistered artifact, ``CoverageUnavailable(native-payload-corrupt)``
    for malformed XML. Other failure modes (e.g. invariant violation
    inside the model layer) propagate as exceptions.
    """

    rel_path = record.artifact_paths.get(COVERAGE_COBERTURA_XML_ARTIFACT_KEY)
    if not rel_path:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"RunRecord.artifact_paths has no "
                f"{COVERAGE_COBERTURA_XML_ARTIFACT_KEY!r} entry; this xunit "
                "run was executed without coverage collection, or "
                "coverlet.collector was absent / below the 6.0.2 floor "
                "(see decisions/2026-06-03-coverlet-pertestcoverage-key.md)"
            ),
            run_reference=record.run_reference,
        )

    coverage_path = store.path / rel_path
    xml_paths: list[Path]
    if coverage_path.is_file():
        xml_paths = [coverage_path]
    elif coverage_path.is_dir():
        # Per-test mode (forward-compat) OR aggregate-mode adapter
        # registered the parent directory for any reason. Glob the
        # Cobertura XMLs inside.
        xml_paths = sorted(coverage_path.glob(_COBERTURA_GLOB))
        if not xml_paths:
            return CoverageUnavailable(
                reason=REASON_MISSING_NATIVE_PAYLOAD,
                detail=(
                    f"coverage_xml registered as directory {coverage_path} "
                    f"but contains no {_COBERTURA_GLOB!r} files; Coverlet "
                    f"output may be missing or under a different glob"
                ),
                run_reference=record.run_reference,
            )
    else:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"Native Cobertura XML payload not found on disk at "
                f"{coverage_path}"
            ),
            run_reference=record.run_reference,
        )

    workspace_root = store.path.parent
    try:
        raw_fact_set = parse_cobertura_xml(
            xml_paths,
            run_reference=record.run_reference,
            engine_name=record.engine_name,
            ecosystem=record.ecosystem,
            workspace_root=workspace_root,
        )
    except CoverageJsonParseError as exc:
        return CoverageUnavailable(
            reason=REASON_NATIVE_PAYLOAD_CORRUPT,
            detail=str(exc),
            run_reference=record.run_reference,
        )

    # §2.4: drop FileCoverage entries whose resolved path doesn't exist
    # on disk. Empty raw_fact_set.files (XML had no classes at all) is
    # NOT a sources-not-found condition — it's a valid empty report.
    surviving_files: tuple[FileCoverage, ...] = tuple(
        fc
        for fc in raw_fact_set.files
        if (workspace_root / fc.file_path).is_file()
    )

    if raw_fact_set.files and not surviving_files:
        # XML had classes but NONE resolved to on-disk files — the
        # source tree appears to have moved post-run.
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail=(
                f"Cobertura XML at {coverage_path} described "
                f"{len(raw_fact_set.files)} source files but NONE exist "
                f"on disk under workspace {workspace_root} — has the "
                f"project tree moved post-run? "
                f"(cobertura-sources-not-found)"
            ),
            run_reference=record.run_reference,
        )

    if len(surviving_files) != len(raw_fact_set.files):
        # Partial survival — rebuild with filtered files + recomputed
        # summary (shared sum-of-parts roll-up, W2/S33) so downstream
        # consumers see a consistent fact set without re-parsing the XML.
        fact_set = replace(
            raw_fact_set,
            files=surviving_files,
            summary=_summary.aggregate_summary(surviving_files),
        )
    else:
        fact_set = raw_fact_set

    write_coverage_facts(store, fact_set)
    return fact_set
