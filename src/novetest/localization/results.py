"""Shared result types for Localization engine operations.

Mirrors ``src/novetest/coverage/results.py`` / ``regression/results.py``:
unavailable outcomes are discriminator-pattern values (``isinstance``
against ``LocalizationUnavailable``) rather than exceptions, so the
engine boundary stays total and callers compose without try/except.

The five ``REASON_*`` constants and the Unavailable shape are pinned by
``agent-comms/decisions/2026-05-28-localization-finding-shape.md`` §6 +
§X (the §X split lands in this slice; a v2 of that decision will codify
the resulting 5-element ``KNOWN_REASONS``).

When does each reason fire:

- ``no-failed-tests``        — Run Record has 0 failed test results.
- ``no-coverage``            — Run Record has failed tests but Coverage
                                Facts are unavailable, OR available with
                                ``mapping_granularity != "per-test"``. In
                                a follow-up slice the latter triggers the
                                ``sbfl_aggregate`` mode; today it surfaces
                                as Unavailable with an explanatory detail.
- ``no-run-evidence``        — ``retrieve_run_evidence`` raises (no live
                                and no tombstoned record for the ref).
- ``missing-derived-facts``  — Cache empty: ``get_localization_findings``
                                was called before
                                ``derive_localization_findings`` produced
                                facts for this run. Recoverable — the
                                caller should ``derive``.
- ``run-not-analyzable``     — Run is structurally non-derivable: the
                                Run Record is tombstoned, or its evidence
                                is corrupted past use. NOT recoverable —
                                this is the strict policy (the AI consumer
                                "will spend tokens reasoning over noise"
                                otherwise — strategy doc §5 + Regression
                                precedent). Distinct from
                                ``missing-derived-facts`` per the §X split.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from novetest.models.run_reference import RunReference


# ---------------------------------------------------------------------------
# Reason codes — string constants so callers can match safely. Keep this set
# small; expand only when a new path through the engine genuinely needs to
# be distinguishable to consumers.
#
# Kebab-case, matching the coverage / regression / replay reason vocabulary
# (W2/S29, ANA-09 — pre-wire-freeze alignment). ``missing-derived-facts`` is
# deliberately the LITERAL same token those three engines use for the same
# concept, so one matcher works across every engine's unavailable outcome in
# a single ``inspect`` payload.
# ---------------------------------------------------------------------------
REASON_NO_FAILED_TESTS: Final[str] = "no-failed-tests"
REASON_NO_COVERAGE: Final[str] = "no-coverage"
REASON_NO_RUN_EVIDENCE: Final[str] = "no-run-evidence"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"
REASON_RUN_NOT_ANALYZABLE: Final[str] = "run-not-analyzable"

KNOWN_REASONS: frozenset[str] = frozenset(
    {
        REASON_NO_FAILED_TESTS,
        REASON_NO_COVERAGE,
        REASON_NO_RUN_EVIDENCE,
        REASON_MISSING_DERIVED_FACTS,
        REASON_RUN_NOT_ANALYZABLE,
    }
)


@dataclass(slots=True, frozen=True)
class LocalizationUnavailable:
    """Explicit unavailable outcome for a Localization operation.

    Returned (not raised) by ``derive_localization_findings`` /
    ``get_localization_findings`` / ``resolve_latest_analyzable_run`` /
    ``derive_latest_localization`` when ranked findings cannot be produced
    from the available evidence. ``run_reference`` is populated when known;
    it is ``None`` only when the underlying Run Reference itself could not
    be resolved (e.g. the latest-resolution helpers when the store has no
    suitable run to point at).
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a 3-key dict for envelope projection.

        All three keys are ALWAYS present — ``run_reference`` and
        ``detail`` are emitted as ``null`` when ``None`` rather than
        omitted, so consumers can rely on key presence and only branch
        on value nullability. Mirrors
        ``RegressionUnavailable.to_dict()`` (per the freeze §6 known
        gap).
        """
        return {
            "run_reference": (
                None if self.run_reference is None else self.run_reference.to_dict()
            ),
            "reason": self.reason,
            "detail": self.detail,
        }
