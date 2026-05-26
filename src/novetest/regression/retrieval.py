"""Implementations of ``get_regression_facts`` and ``check_regression_availability``.

Workflow (from ``design/workflows/regression.md``):

    get_regression_facts(run_reference_1, run_reference_2)  -> -
    check_regression_availability(run_reference)            -> memory/find_runs_for_target

``get_regression_facts`` is a pure cache read: the canonical pair directory
either exists with a parseable payload, or it doesn't. We do NOT resolve
Memory entries here — the caller (`compare_runs`) does that and surfaces
``REASON_RUN_NOT_FOUND`` / ``REASON_RUN_TOMBSTONED`` for its own reasons
(tombstoning is fail-hard regardless of cache existence, per decision §C.1).

Coverage-schema-stale detection (decision §C.6) lives here: if the on-disk
payload embeds a ``coverage_change`` block whose ``schema_version`` falls
below the current ``CoverageDelta`` schema, we return
``RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS,
detail="coverage-schema-stale")``. The caller re-derives.

``check_regression_availability`` returns a plain ``bool`` (not a
discriminator) — the only failure mode is "no comparable prior", which is
exactly what ``False`` means. Used by Orchestration eligibility evaluation
(Phase 6) and Localization (Phase 4).
"""

from __future__ import annotations

from typing import Any

from novetest.coverage.compare import SCHEMA_VERSION as COVERAGE_DELTA_SCHEMA_VERSION
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import (
    RunEvidenceNotFoundError,
    find_runs_for_target,
    retrieve_run_evidence,
)
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_reference import RunReference
from novetest.regression.persistence import read_regression_facts_raw
from novetest.regression.results import (
    REASON_MISSING_DERIVED_FACTS,
    RegressionUnavailable,
)


_COVERAGE_SCHEMA_STALE_DETAIL = "coverage-schema-stale"


def get_regression_facts(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> RegressionFactSet | RegressionUnavailable:
    """Return the previously-derived ``RegressionFactSet`` for a pair.

    Argument order is load-bearing — ``(baseline, target)`` per decision
    §2; reversing the args resolves to a different on-disk directory and
    is a logically distinct operation.

    Returns:
    - ``RegressionFactSet`` when the canonical pair directory exists with a
      valid payload AND the embedded coverage payload (if any) is current.
    - ``RegressionUnavailable(reason="missing-derived-facts")`` when the
      pair directory does not exist.
    - ``RegressionUnavailable(reason="missing-derived-facts",
      detail="coverage-schema-stale")`` when the cached payload embeds a
      Coverage delta whose schema is older than ``CoverageDelta``'s
      current schema (decision §C.6).
    """
    raw = read_regression_facts_raw(
        store,
        baseline_run_reference.run_id,
        target_run_reference.run_id,
    )
    if raw is None:
        return RegressionUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail=(
                "No regression_facts.json found for this pair; call "
                "derive_regression_facts first"
            ),
            baseline_run_reference=baseline_run_reference,
            target_run_reference=target_run_reference,
        )

    coverage_change = raw.get("coverage_change")
    if _coverage_change_is_stale(coverage_change):
        return RegressionUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail=_COVERAGE_SCHEMA_STALE_DETAIL,
            baseline_run_reference=baseline_run_reference,
            target_run_reference=target_run_reference,
        )

    return RegressionFactSet.from_dict(raw)


def check_regression_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Return True iff a comparable prior (non-tombstoned) run exists.

    "Comparable" here = "shares the same resolved ``target_expression``" —
    the same partition rule ``find_runs_for_target`` uses. Engine /
    target-type compatibility checks are deliberately deferred to
    ``compare_runs``; this helper only answers the eligibility question
    ("is there *any* prior the caller could compare against?").

    Behaviour:
    - Unknown ``run_reference`` (no live or tombstoned record) → ``False``.
      Missing-tolerant by design: eligibility evaluation treats absence as
      "not available", never as an error.
    - Tombstoned input ``run_reference`` → still computes availability against
      its historical ``target_expression``. A tombstone of the input does
      not erase the question; we measure whether a comparable prior exists,
      not whether the input itself is live.
    - The input run is filtered out of the candidate set by ``run_id``, so
      a target with only one run (the input) yields ``False``.
    """
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError:
        return False
    siblings = find_runs_for_target(
        store,
        entry.run_record.target_expression,
        include_tombstoned=False,
    )
    comparable = [
        e for e in siblings
        if e.run_record.run_reference.run_id != run_reference.run_id
    ]
    return len(comparable) >= 1


def _coverage_change_is_stale(coverage_change: Any) -> bool:
    """True iff the embedded coverage block carries an older schema_version.

    A ``None`` (or absent) ``coverage_change`` is NOT stale — it just means
    neither run had Coverage Facts at derive time, which is a valid steady
    state. We only flag genuinely-older embedded payloads.
    """
    if not isinstance(coverage_change, dict):
        return False
    embedded_version = coverage_change.get("schema_version")
    if not isinstance(embedded_version, int):
        # Missing / non-int schema_version on the embedded payload is a
        # malformed write rather than a stale read; let
        # ``CoverageDelta.from_dict`` (called by downstream consumers)
        # surface the ValueError. ``get_regression_facts`` v1 is not
        # responsible for repairing malformed embedded payloads.
        return False
    return embedded_version < COVERAGE_DELTA_SCHEMA_VERSION
