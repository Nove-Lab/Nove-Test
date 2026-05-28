"""Shared result types for Localization engine operations.

Mirrors ``src/novetest/coverage/results.py`` / ``regression/results.py``:
unavailable outcomes are discriminator-pattern values (``isinstance``
against ``LocalizationUnavailable``) rather than exceptions, so the
engine boundary stays total and callers compose without try/except.

The four ``REASON_*`` constants and the Unavailable shape are the
working-draft contract for this Phase-4-entry slice; PM freezes them in
a follow-up ``decisions/`` entry after Manual Test fields them.

When does each reason fire (per-test path, this slice):

- ``no_failed_tests``      — Run Record has 0 failed test results.
- ``no_coverage``          — Run Record has failed tests but Coverage
                              Facts are unavailable, OR available with
                              ``mapping_granularity != "per-test"``. In
                              a follow-up slice the latter triggers the
                              ``sbfl_aggregate`` mode; today it surfaces
                              as Unavailable with an explanatory detail.
- ``no_run_evidence``      — ``retrieve_run_evidence`` raises (no live
                              and no tombstoned record for the ref).
- ``run_not_analyzable``   — the Run Record is tombstoned. Strict policy:
                              the AI consumer "will spend tokens
                              reasoning over noise" otherwise (strategy
                              doc §5 + Regression precedent).
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
REASON_NO_FAILED_TESTS: Final[str] = "no_failed_tests"
REASON_NO_COVERAGE: Final[str] = "no_coverage"
REASON_NO_RUN_EVIDENCE: Final[str] = "no_run_evidence"
REASON_RUN_NOT_ANALYZABLE: Final[str] = "run_not_analyzable"

KNOWN_REASONS: frozenset[str] = frozenset(
    {
        REASON_NO_FAILED_TESTS,
        REASON_NO_COVERAGE,
        REASON_NO_RUN_EVIDENCE,
        REASON_RUN_NOT_ANALYZABLE,
    }
)


@dataclass(slots=True, frozen=True)
class LocalizationUnavailable:
    """Explicit unavailable outcome for a Localization operation.

    Returned (not raised) by ``derive_localization_findings`` /
    ``get_localization_findings`` when ranked findings cannot be produced
    from the available evidence. ``run_reference`` is populated when known;
    it is ``None`` only when the underlying Run Reference itself could not
    be resolved.
    """

    run_reference: RunReference | None
    reason: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.reason not in KNOWN_REASONS:
            raise ValueError(
                f"Invalid LocalizationUnavailable.reason={self.reason!r}; "
                f"expected one of {sorted(KNOWN_REASONS)!r}"
            )
