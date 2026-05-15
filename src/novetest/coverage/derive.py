"""Implementation of ``derive_coverage_facts``.

Workflow (from ``design/workflows/coverage.md``):

    derive_coverage_facts(run_reference) -> memory/retrieve_run_evidence

We resolve the Memory Entry for the run, look up the native coverage
payload registered under ``RunRecord.artifact_paths["coverage_json"]``,
parse it, persist the resulting ``CoverageFactSet`` so subsequent
``get_coverage_facts`` calls hit cache, and return the fact set.

Missing or unregistered native payload is an **explicit unavailable
outcome** (REQ-COV-004), not an exception. Corrupt JSON is propagated as
``CoverageUnavailable(reason="native-payload-corrupt")`` to keep the
operation total at the engine boundary.
"""

from __future__ import annotations

import json

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
from novetest.models.run_reference import RunReference


# The pinned artifact-key Run Team registers for the coverage.py JSON
# payload. Coverage's contract with Run is that this key, if present,
# points to a Project-Store-relative path to the coverage.py JSON file.
COVERAGE_JSON_ARTIFACT_KEY = "coverage_json"


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

    try:
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
