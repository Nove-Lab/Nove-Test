"""``FactBundle`` — the synthesizer's pure input shape.

Bundles the Run Record plus the (optional) downstream fact-sets produced by
the four downstream engines into a single immutable structure. The
synthesizer is a pure function of ``FactBundle`` (no I/O, no globals) — so
this file owns:

- the ``FactBundle`` dataclass (immutable, slots),
- the ``StageEligibility`` dataclass that records per-stage availability,
- the ``build_fact_bundle`` builder that maps each engine's
  ``FactSet | Unavailable`` discriminator value onto the bundle's
  ``FactSet | None`` slot (and the ``--reruns`` replay sub-workflow's
  outcome onto the ``replay_results`` tuple slot).

Determinism contract (synthesis design doc §4): same ``FactBundle`` in,
byte-identical ``list[Recommendation]`` out. Builder helpers below avoid
any time- or randomness-dependent inputs — every output field is sourced
from the engine outcomes the caller passed in.

ReplayResult re-export
----------------------

The canonical ``ReplayResult`` model lives at ``models/replay_result.py`` and
was promoted by the Phase 5 entry slice; this module re-imports it so existing
callers of ``from ...fact_bundle import ReplayResult`` (the recommendation
package ``__init__`` and the synthesizer's ``flaky_suspected`` matcher)
continue to work. The five binding fields (``run_reference`` /
``classification`` / ``reruns_total`` / ``reruns_failed`` / ``test_id``) are
unchanged, so this is a re-export, not a behavior change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from novetest.models import (
    FAIL_LIKE_OUTCOMES,
    LocalizationFinding,
    ReplayResult,
    RunRecord,
)
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.localization_finding import LOCALIZATION_MODES
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_reference import RunReference


__all__ = [
    "FactBundle",
    "ReplayResult",
    "StageEligibility",
    "build_fact_bundle",
    "has_failed_tests",
    "passed_count",
    "record_has_failed_tests",
    "skipped_count",
    "total_count",
]


# ---------------------------------------------------------------------------
# StageEligibility — the per-stage availability summary the envelope emits
# (also a free-standing input the synthesizer reads for ``unavailable_analysis``).
# ---------------------------------------------------------------------------


# Closed vocabulary for the four eligibility slots. The Localization slot
# follows the Localization engine's ``mode`` vocabulary when available; the
# ``unavailable`` / ``not_applicable`` / ``not_run`` values mirror the brief
# §5 envelope shape exactly.
COVERAGE_ELIGIBILITY: Final[frozenset[str]] = frozenset(
    {"available", "unavailable", "not_applicable"}
)
REGRESSION_ELIGIBILITY: Final[frozenset[str]] = frozenset(
    {"available", "unavailable", "not_applicable"}
)
# Localization adopts the engine's three modes verbatim when a finding is
# available, plus ``unavailable`` / ``not_applicable`` for the no-data and
# pre-Phase-4 paths. ``LOCALIZATION_MODES`` is imported from the engine so
# the two stay in lockstep.
LOCALIZATION_ELIGIBILITY: Final[frozenset[str]] = (
    LOCALIZATION_MODES | frozenset({"unavailable", "not_applicable"})
)
REPLAY_ELIGIBILITY: Final[frozenset[str]] = frozenset(
    {"available", "unavailable", "not_applicable", "not_run"}
)


@dataclass(slots=True, frozen=True)
class StageEligibility:
    """Per-stage availability summary surfaced on the ``novetest test`` envelope.

    Each slot is a closed-vocabulary string (see the ``*_ELIGIBILITY``
    frozensets above). Validation fires in ``__post_init__`` so an
    accidental drift in the synthesizer never reaches the envelope.

    For the ``localization`` slot specifically: when a Localization Finding
    is available the value is the finding's ``mode`` (e.g.
    ``"sbfl_per_test"`` / ``"sbfl_aggregate"`` / ``"failure_proximity"``);
    when no finding exists or the engine returned Unavailable, the value
    is ``"unavailable"``.

    ``per_stage_reasons`` carries the engine's own ``unavailable.reason``
    field verbatim — used by the synthesizer's ``unavailable_analysis``
    category as the ``reason_per_stage`` slot value (brief §1 — sub-table
    Slot semantics).
    """

    coverage: str
    regression: str
    localization: str
    replay: str
    per_stage_reasons: dict[str, str | None]

    def __post_init__(self) -> None:
        if self.coverage not in COVERAGE_ELIGIBILITY:
            raise ValueError(
                f"Invalid StageEligibility.coverage={self.coverage!r}; "
                f"expected one of {sorted(COVERAGE_ELIGIBILITY)!r}"
            )
        if self.regression not in REGRESSION_ELIGIBILITY:
            raise ValueError(
                f"Invalid StageEligibility.regression={self.regression!r}; "
                f"expected one of {sorted(REGRESSION_ELIGIBILITY)!r}"
            )
        if self.localization not in LOCALIZATION_ELIGIBILITY:
            raise ValueError(
                f"Invalid StageEligibility.localization={self.localization!r}; "
                f"expected one of {sorted(LOCALIZATION_ELIGIBILITY)!r}"
            )
        if self.replay not in REPLAY_ELIGIBILITY:
            raise ValueError(
                f"Invalid StageEligibility.replay={self.replay!r}; "
                f"expected one of {sorted(REPLAY_ELIGIBILITY)!r}"
            )

    def to_dict(self) -> dict[str, str]:
        """Envelope projection.

        ``per_stage_reasons`` is intentionally NOT emitted here — the
        envelope's ``stage_eligibility`` block is just the four slot
        values. The reason map is consumed by the synthesizer's
        ``unavailable_analysis`` builder; it surfaces as the
        ``reason_per_stage`` recommendation slot, not as a top-level
        envelope field.
        """
        return {
            "coverage": self.coverage,
            "regression": self.regression,
            "localization": self.localization,
            "replay": self.replay,
        }

    def unavailable_stages(self) -> list[str]:
        """Return the ordered list of stages currently in ``unavailable`` state.

        Order is stable (brief §1 — Slot semantics): ``coverage``,
        ``regression``, ``localization``, ``replay`` — filtered to those
        whose value is exactly ``"unavailable"``. Used as the
        ``unavailable_stages`` slot for ``unavailable_analysis``.
        """
        out: list[str] = []
        if self.coverage == "unavailable":
            out.append("coverage")
        if self.regression == "unavailable":
            out.append("regression")
        if self.localization == "unavailable":
            out.append("localization")
        if self.replay == "unavailable":
            out.append("replay")
        return out


# ---------------------------------------------------------------------------
# FactBundle — the synthesizer's pure input.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class FactBundle:
    """Bundle of facts the synthesizer reasons over for a single run.

    ``coverage_facts`` / ``regression_facts`` / ``localization_findings``
    are ``None`` exactly when the corresponding engine returned Unavailable
    (or has not been called). ``replay_results`` is a (possibly empty)
    tuple of Replay Results: empty when Replay was not invoked
    (``--reruns`` absent / no failed tests) or the attempt could not start
    (``ReplayUnavailable``); today the integrated workflow performs at most
    one whole-run Replay Attempt per invocation, so the tuple holds 0 or 1
    elements — the tuple shape is the 2026-06-25 ``--reruns`` brief's pin
    (future per-test replay scoping would yield multiple). The
    ``StageEligibility`` slot is the source of truth for "which stages had
    something to say" — the synthesizer reads from there for
    ``unavailable_analysis`` and from the fact-set slots for the other
    categories.

    ``run_reference`` is duplicated from ``run_record.run_reference`` for
    the convenience of synthesis code that needs the ref without dereferencing
    the record.
    """

    run_reference: RunReference
    run_record: RunRecord
    stage_eligibility: StageEligibility
    coverage_facts: CoverageFactSet | None
    regression_facts: RegressionFactSet | None
    localization_findings: LocalizationFinding | None
    replay_results: tuple[ReplayResult, ...] = ()


# ---------------------------------------------------------------------------
# Builder — maps engine outcomes onto FactBundle slots.
# ---------------------------------------------------------------------------


def build_fact_bundle(
    *,
    run_record: RunRecord,
    stage_eligibility: StageEligibility,
    coverage_facts: CoverageFactSet | None,
    regression_facts: RegressionFactSet | None,
    localization_findings: LocalizationFinding | None,
    replay_results: tuple[ReplayResult, ...] = (),
) -> FactBundle:
    """Compose a ``FactBundle`` from already-resolved engine outcomes.

    The caller (``workflows/test.py``) is responsible for invoking each
    engine and mapping its ``FactSet | Unavailable`` discriminator value
    to ``FactSet | None`` (an ``Unavailable`` outcome becomes ``None``).
    Centralizing that mapping at the caller lets per-engine retries /
    fallbacks live closer to the engine surface; this builder is a pure
    aggregation step that produces an immutable bundle the synthesizer
    can read in any order.

    ``replay_results`` defaults to the empty tuple — the integrated
    workflow only invokes Replay when ``--reruns N > 0`` AND the Run
    Record has failed tests (2026-06-25 decision). A ``ReplayUnavailable``
    attempt outcome also maps to the empty tuple (the eligibility slot,
    not the bundle, carries the unavailability reason).
    """

    return FactBundle(
        run_reference=run_record.run_reference,
        run_record=run_record,
        stage_eligibility=stage_eligibility,
        coverage_facts=coverage_facts,
        regression_facts=regression_facts,
        localization_findings=localization_findings,
        replay_results=replay_results,
    )


def has_failed_tests(bundle: FactBundle) -> bool:
    """Return True iff the Run Record reports at least one failing test.

    Used by ``unavailable_analysis`` (which only fires when we owe the
    user an explanation — i.e. tests failed AND some stage was
    unavailable) and by ``all_green`` (which requires zero failures).

    Thin wrapper over ``record_has_failed_tests`` (which the integrated
    workflow also uses pre-bundle to decide whether the ``--reruns``
    replay sub-workflow triggers) so the two call sites share one
    fail-detection semantic.
    """
    return record_has_failed_tests(bundle.run_record)


def record_has_failed_tests(record: RunRecord) -> bool:
    """Return True iff ``record`` reports at least one failing test.

    The probe uses ``summary_counts.failed`` first when present (the
    common case — pytest, jest, go, cargo all populate this), and falls
    back to scanning ``test_results`` for fail-like outcomes when the
    summary block is missing. The fall-back is defensive: every adapter
    populates ``summary_counts.failed`` today, but the field is
    ``dict[str, int]``-typed at the model layer so a future adapter
    could in principle ship without it.
    """
    counts = record.summary_counts
    if "failed" in counts:
        return counts["failed"] > 0
    return any(_is_fail_outcome(tr.outcome) for tr in record.test_results)


def _is_fail_outcome(outcome: str) -> bool:
    """Return True for the fail-like outcome strings native engines emit.

    The membership set is the ``novetest.models.FAIL_LIKE_OUTCOMES`` SSoT
    (S25 / correction C6): exactly ``{"failed", "errored"}``. The former
    inline literal also accepted singular ``"error"`` — an XCT-05 drift that
    no adapter can reach (the normalizer maps ``error -> errored``).
    """

    return outcome.lower() in FAIL_LIKE_OUTCOMES


def passed_count(bundle: FactBundle) -> int:
    """Return the number of passing tests for the Run Record.

    Mirrors ``has_failed_tests``: reads ``summary_counts['passed']`` when
    present, falls back to a scan over ``test_results`` for ``passed``
    outcomes. Used as the ``passed`` slot value for ``all_green``.
    """
    counts = bundle.run_record.summary_counts
    if "passed" in counts:
        return counts["passed"]
    return sum(1 for tr in bundle.run_record.test_results if tr.outcome.lower() == "passed")


def skipped_count(bundle: FactBundle) -> int:
    """Return the number of skipped tests for the Run Record.

    Used as the ``skipped`` slot value for ``all_green``. Defensive
    fall-back mirrors ``passed_count``.
    """
    counts = bundle.run_record.summary_counts
    if "skipped" in counts:
        return counts["skipped"]
    return sum(1 for tr in bundle.run_record.test_results if tr.outcome.lower() == "skipped")


def total_count(bundle: FactBundle) -> int:
    """Return the total number of tests reported by the Run Record.

    Prefers ``summary_counts['total']`` (the canonical key adapters
    populate); falls back to ``len(test_results)`` when absent.
    """
    counts = bundle.run_record.summary_counts
    if "total" in counts:
        return counts["total"]
    return len(bundle.run_record.test_results)
