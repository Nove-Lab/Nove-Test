"""Implementations of ``get_localization_findings`` and ``check_localization_availability``.

Mirrors ``src/novetest/regression/retrieval.py`` in shape:

- ``get_localization_findings``     — pure cache read (no derivation).
- ``check_localization_availability`` — cheap precondition probe; bool result.

The latest-resolution composition helpers
(``resolve_latest_analyzable_run`` + ``derive_latest_localization``) live
in ``novetest.localization.derive`` so they sit next to
``derive_localization_findings`` — mirrors Regression's pattern of
keeping ``resolve_latest_baseline`` + ``derive_latest_regression`` next
to ``compare_runs`` in ``compare.py``.
"""

from __future__ import annotations

from novetest.coverage.retrieval import get_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.localization.persistence import read_localization_findings_raw
from novetest.localization.results import (
    REASON_MISSING_DERIVED_FACTS,
    LocalizationUnavailable,
)
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RunEvidenceNotFoundError, retrieve_run_evidence
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_reference import RunReference


# Outcome bucket for "failed-like" — mirrors derive.py. Localization cares
# only about the failed/non-failed distinction, so the 3-bucket
# pass/fail/skip vocabulary used by Regression is overkill here.
_FAILED_OUTCOMES: frozenset[str] = frozenset({"failed", "errored"})


def get_localization_findings(
    store: ProjectStore,
    run_reference: RunReference,
) -> LocalizationFinding | LocalizationUnavailable:
    """Return previously-derived Localization Findings for ``run_reference``.

    Returns:
    - ``LocalizationFinding`` when ``localization_findings.json`` exists.
    - ``LocalizationUnavailable(reason="missing_derived_facts",
      detail="findings not yet derived")`` when the cache file is
      absent. The caller should invoke ``derive_localization_findings``
      to trigger derivation. (Per the decision §X split, this is the
      recoverable cache-empty case — distinct from
      ``run_not_analyzable``, which is reserved for structurally non-
      derivable runs such as tombstoned records.)
    """
    raw = read_localization_findings_raw(store, run_reference.run_id)
    if raw is None:
        return LocalizationUnavailable(
            run_reference=run_reference,
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="findings not yet derived",
        )
    return LocalizationFinding.from_dict(raw)


def check_localization_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Cheap precondition probe for Orchestration eligibility evaluation.

    Returns ``True`` iff ALL three preconditions for the per-test SBFL
    path are satisfied:

    1. ``retrieve_run_evidence`` succeeds AND the entry is not tombstoned.
    2. The Run Record has at least one failed test result.
    3. Coverage Facts exist for the run AND
       ``mapping_granularity == "per-test"``.

    Does NOT derive. The Localization engine's ``derive_localization_findings``
    is the only function that actually computes scores; this helper is
    the cheap "is the derivation even worth attempting" gate.

    Returns ``False`` on any precondition failure — missing-tolerant by
    design (mirrors ``check_regression_availability`` / Coverage's
    availability helpers).
    """
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError:
        return False
    if entry.tombstoned_at is not None:
        return False
    has_failed = any(
        tr.outcome in _FAILED_OUTCOMES for tr in entry.run_record.test_results
    )
    if not has_failed:
        return False
    coverage = get_coverage_facts(store, entry.run_record.run_reference)
    if isinstance(coverage, CoverageUnavailable):
        return False
    return coverage.mapping_granularity == "per-test"
