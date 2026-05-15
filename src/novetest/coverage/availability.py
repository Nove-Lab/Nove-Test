"""Implementation of ``check_coverage_availability``.

Workflow (from ``design/workflows/coverage.md``):

    check_coverage_availability(run_reference) -> -   (no further interface call)

Pure filesystem/record probing. Two probes:

1. **Derived facts present?** Probe
   ``<store>/coverage/facts/run_<id>/coverage_facts.json``. This MUST agree
   with Memory's ``MemoryEntry.has_coverage_facts`` flag — we replicate the
   path check rather than importing Memory's private helper, per the
   charter rule ("must agree without importing Memory's private helpers").

2. **Derivable from native payload?** Probe whether the Run Record
   advertises a ``coverage_json`` artifact AND that file exists on disk.

A run is *available* when either probe succeeds. Orchestration's stage
eligibility uses this signal to decide whether to call ``derive`` /
``get`` or to surface an "unavailable" sub-report.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.coverage.persistence import coverage_facts_path
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RunEvidenceNotFoundError, retrieve_run_evidence
from novetest.models.run_reference import RunReference


# Mirror the pinned artifact key from derive.py so the two stay in sync if
# Run Team ever renames it (the rename would land in a single decision).
_COVERAGE_JSON_ARTIFACT_KEY = "coverage_json"


@dataclass(slots=True, frozen=True)
class CoverageAvailability:
    """Filesystem-derived availability snapshot for a Run's Coverage facts.

    ``available`` is the headline signal — true iff Coverage Facts can
    either be retrieved (``facts_persisted``) or derived right now from a
    native payload that's still on disk (``native_payload_present``).

    ``reason`` is populated only when ``available`` is false, so callers
    can pass it straight to a structured envelope without conditional
    boilerplate.
    """

    available: bool
    facts_persisted: bool
    native_payload_present: bool
    run_exists: bool
    reason: str | None = None


# Reason strings used when available=False. Kept private; consumers should
# branch on the booleans, not strings.
_REASON_RUN_NOT_FOUND = "run-not-found"
_REASON_NO_COVERAGE_EVIDENCE = "no-coverage-evidence"


def check_coverage_availability(
    store: ProjectStore, run_reference: RunReference
) -> CoverageAvailability:
    """Return whether Coverage Facts can be derived or retrieved for ``run_reference``.

    Does not raise for an unknown Run Reference — that produces an
    ``available=False, run_exists=False`` snapshot. Orchestration's
    stage-eligibility evaluator treats that as a clean "unavailable"
    sub-report rather than an internal error.
    """
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError:
        return CoverageAvailability(
            available=False,
            facts_persisted=False,
            native_payload_present=False,
            run_exists=False,
            reason=_REASON_RUN_NOT_FOUND,
        )

    run_id = entry.run_record.run_reference.run_id
    facts_persisted = coverage_facts_path(store, run_id).is_file()

    native_payload_present = False
    rel_path = entry.run_record.artifact_paths.get(_COVERAGE_JSON_ARTIFACT_KEY)
    if rel_path:
        native_payload_present = (store.path / rel_path).is_file()

    available = facts_persisted or native_payload_present
    return CoverageAvailability(
        available=available,
        facts_persisted=facts_persisted,
        native_payload_present=native_payload_present,
        run_exists=True,
        reason=None if available else _REASON_NO_COVERAGE_EVIDENCE,
    )
