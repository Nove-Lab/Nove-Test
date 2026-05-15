"""Implementation of ``get_coverage_facts``.

Workflow (from ``design/workflows/coverage.md``):

    get_coverage_facts(run_reference) -> memory/retrieve_run_evidence

We resolve the Memory Entry to confirm the run exists at all (so callers
get a clean ``run-not-found`` signal for stale references), then read the
previously-derived ``coverage_facts.json`` for the run. We never call
``derive_coverage_facts`` from here — the contract for ``get`` is
"cached / previously derived"; the External ``novetest coverage show``
workflow stitches ``get`` then ``derive`` together in Orchestration.
"""

from __future__ import annotations

from novetest.coverage.persistence import read_coverage_facts
from novetest.coverage.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_NOT_FOUND,
    CoverageUnavailable,
)
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RunEvidenceNotFoundError, retrieve_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_reference import RunReference


def get_coverage_facts(
    store: ProjectStore, run_reference: RunReference
) -> CoverageFactSet | CoverageUnavailable:
    """Return the previously-derived ``CoverageFactSet`` for ``run_reference``.

    Returns:
    - ``CoverageFactSet`` when ``coverage_facts.json`` exists on disk.
    - ``CoverageUnavailable(reason="run-not-found")`` when the Run
      Reference doesn't resolve to any Memory Entry (live or tombstoned).
    - ``CoverageUnavailable(reason="missing-derived-facts")`` when the run
      exists but no facts have been derived yet.
    """
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError as exc:
        return CoverageUnavailable(
            reason=REASON_RUN_NOT_FOUND,
            detail=str(exc),
            run_reference=run_reference,
        )

    fact_set = read_coverage_facts(store, entry.run_record.run_reference.run_id)
    if fact_set is None:
        return CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail=(
                "No coverage_facts.json found for this run; call "
                "derive_coverage_facts first"
            ),
            run_reference=entry.run_record.run_reference,
        )
    return fact_set
