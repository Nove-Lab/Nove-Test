"""Shared result types for Coverage engine operations.

REQ-COV-004 calls out unavailability as an explicit outcome rather than an
exception, because native engines vary in coverage support. The four
Coverage interfaces therefore return either their normal success payload
(`CoverageFactSet` / `CoverageDelta` / `CoverageAvailability`) or a
``CoverageUnavailable`` value that records *why* the operation cannot
produce facts. Callers use ``isinstance`` to discriminate.

We keep this in a dedicated module so it can be re-exported alongside the
operation modules without circular-import gymnastics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from novetest.models.run_reference import RunReference


# ---------------------------------------------------------------------------
# Reason codes — string constants so callers can match safely. Keep this set
# small; expand only when a new path through the engine genuinely needs to
# be distinguishable to consumers.
# ---------------------------------------------------------------------------
REASON_RUN_NOT_FOUND: Final[str] = "run-not-found"
REASON_MISSING_NATIVE_PAYLOAD: Final[str] = "missing-native-payload"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"
REASON_NATIVE_PAYLOAD_CORRUPT: Final[str] = "native-payload-corrupt"
REASON_INCOMPARABLE_GRANULARITY: Final[str] = "incomparable-granularity"
# D5 guard (decision 2026-07-03-engine-selection-policy §D5, Finding A of
# the D5 cross-run audit): ``compare_coverage_facts`` refuses cross-engine
# pairs the same way Regression's ``compare_runs`` does. Same wire string
# as Regression's ``REASON_ENGINE_MISMATCH`` ("engine-mismatch") so agents
# can match one constant across both engines' unavailable envelopes.
REASON_ENGINE_MISMATCH: Final[str] = "engine-mismatch"

KNOWN_REASONS: frozenset[str] = frozenset(
    {
        REASON_RUN_NOT_FOUND,
        REASON_MISSING_NATIVE_PAYLOAD,
        REASON_MISSING_DERIVED_FACTS,
        REASON_NATIVE_PAYLOAD_CORRUPT,
        REASON_INCOMPARABLE_GRANULARITY,
        REASON_ENGINE_MISMATCH,
    }
)


@dataclass(slots=True, frozen=True)
class CoverageUnavailable:
    """Explicit unavailable outcome for a Coverage operation.

    Returned (not raised) by ``derive_coverage_facts`` /
    ``get_coverage_facts`` / ``compare_coverage_facts`` when the requested
    facts cannot be produced from the available evidence. ``run_reference``
    is None only when the underlying Run Reference itself could not be
    resolved (``run-not-found``).
    """

    reason: str
    detail: str | None = None
    run_reference: RunReference | None = None
