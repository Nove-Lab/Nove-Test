"""Implementation of ``derive_coverage_facts``.

Workflow (from ``design/workflows/coverage.md``):

    derive_coverage_facts(run_reference) -> memory/retrieve_run_evidence

We resolve the Memory Entry for the run, look up the native coverage
payload (artifact key depends on engine: ``coverage_json`` for
pytest / jest / go-test, ``coverage_lcov`` for cargo-test), parse it
through the engine-appropriate parser, persist the resulting
``CoverageFactSet`` so subsequent ``get_coverage_facts`` calls hit
cache, and return the fact set.

Missing or unregistered native payload is an **explicit unavailable
outcome** (REQ-COV-004), not an exception. Corrupt payloads (JSON or
LCOV) are propagated as
``CoverageUnavailable(reason="native-payload-corrupt")`` to keep the
operation total at the engine boundary.
"""

from __future__ import annotations

import json

from novetest.coverage.istanbul_parser import parse_istanbul_json
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
from novetest.models.coverage_fact_set import CoverageFactSet
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

# Engine name the cargo adapter sets on its ``NativeResult`` /
# ``RunRecord.engine_name``. The literal value is contractual — Run
# team pins it in ``cargo_adapter.py``; the dispatch here matches
# against it.
_CARGO_ENGINE_NAME = "cargo-test"


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
