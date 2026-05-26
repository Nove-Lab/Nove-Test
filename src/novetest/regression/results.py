"""Shared result types for Regression engine operations.

Mirrors ``src/novetest/coverage/results.py`` 1:1 in shape: regression-
specific outcomes are also discriminator-pattern values (``isinstance``
against ``RegressionUnavailable``) rather than exceptions, so the engine
boundary stays total and callers compose cleanly without try/except
gymnastics.

Reason codes and the Unavailable shape are pinned by
``agent-comms/decisions/2026-05-26-regression-facts-json-layout.md`` §7.
Adding a new ``REASON_*`` constant requires a follow-up decision update.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from novetest.models.run_reference import RunReference


# ---------------------------------------------------------------------------
# Reason codes — string constants so callers can match safely. Keep this set
# small; expand only when a new path through the engine genuinely needs to
# be distinguishable to consumers. The six values here are the closed set
# pinned by decision §7.
# ---------------------------------------------------------------------------
REASON_RUN_NOT_FOUND: Final[str] = "run-not-found"
REASON_RUN_TOMBSTONED: Final[str] = "run-tombstoned"
REASON_NO_COMPARABLE_BASELINE: Final[str] = "no-comparable-baseline"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"
REASON_ENGINE_MISMATCH: Final[str] = "engine-mismatch"
REASON_TARGET_MISMATCH: Final[str] = "target-mismatch"

KNOWN_REASONS: frozenset[str] = frozenset(
    {
        REASON_RUN_NOT_FOUND,
        REASON_RUN_TOMBSTONED,
        REASON_NO_COMPARABLE_BASELINE,
        REASON_MISSING_DERIVED_FACTS,
        REASON_ENGINE_MISMATCH,
        REASON_TARGET_MISMATCH,
    }
)


@dataclass(slots=True, frozen=True)
class RegressionUnavailable:
    """Explicit unavailable outcome for a Regression operation.

    Returned (not raised) by ``compare_runs`` / ``derive_regression_facts``
    / ``get_regression_facts`` when the requested facts cannot be
    produced. ``baseline_run_reference`` / ``target_run_reference`` are
    populated when known; both may be ``None`` if a Run Reference itself
    could not be resolved.

    ``detail`` carries operator-readable specifics (e.g. ``"baseline"`` /
    ``"target"`` / ``"both"`` for tombstone cases per decision §C.1, or
    ``"coverage-schema-stale"`` for the coverage-coupling stale-read path
    per decision §C.6).
    """

    reason: str
    detail: str | None = None
    baseline_run_reference: RunReference | None = None
    target_run_reference: RunReference | None = None
