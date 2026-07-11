"""Single-source engine-outcome projectors for the v1 envelope (W2/S23, ORC-08).

The four per-engine outcome projectors and the coverage-delta payload
builder were previously double-defined — once in ``cli/app.py`` (verb
envelopes) and once in ``orchestration/workflows/inspect.py`` (the
aggregated ``inspect`` view) — with only a docstring promise of
"identical wire shape" holding them together. This module is the ONE
definition both call paths import; the doubles are deleted and a
divergence guard (``tests/unit/orchestration/test_projection.py``) pins
that neither module re-grows a local copy.

Layer placement: orchestration-neutral — this module imports engine
result types only (never ``novetest.cli``), so both ``cli/app.py`` and
the orchestration workflows can import it without a cycle. The CLI
remains the only place exit codes are decided; these functions shape
``data`` blocks exclusively.

Wire stability: every function here emits the exact byte shape the two
pre-S23 copies emitted. ``schema_version`` is stripped from persisted
bodies on the wire — envelope versioning lives at the top-level
``schema`` field, not inside individual data blocks.
"""

from __future__ import annotations

from typing import Any

from novetest.coverage import CoverageUnavailable
from novetest.coverage.compare import CoverageDelta
from novetest.localization import LocalizationFinding, LocalizationUnavailable
from novetest.models import ReplayResult
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.regression import RegressionFactSet, RegressionUnavailable
from novetest.replay import ReplayUnavailable


def coverage_outcome_payload(
    outcome: CoverageFactSet | CoverageUnavailable,
) -> dict[str, Any]:
    """Project a Coverage derive outcome onto the envelope wire shape.

    Two ``kind`` values discriminate at parse time: ``fact-set`` carries
    the granularity + summary, ``unavailable`` carries the reason +
    detail. The ``run_reference`` block is present in both (``None`` only
    when the Run Reference itself could not be resolved). Shape frozen by
    ``decisions/2026-05-16-coverage-outcome-envelope-shape.md``.
    """
    if isinstance(outcome, CoverageFactSet):
        return {
            "kind": "fact-set",
            "run_reference": outcome.run_reference.to_dict(),
            "mapping_granularity": outcome.mapping_granularity,
            "summary": outcome.summary.to_dict(),
        }
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def coverage_delta_payload(
    outcome: CoverageDelta | CoverageUnavailable,
) -> dict[str, Any]:
    """Project a Coverage compare outcome onto the envelope wire shape.

    Two ``kind`` values discriminate at parse time: ``delta`` carries the
    full delta payload (baseline + target references, both summaries, file
    adds/removes, per-file deltas), ``unavailable`` carries the propagated
    reason + detail from whichever side lacked derived facts. Emitted by
    BOTH ``coverage diff`` and the composed ``compare`` view — the pre-S23
    double-exposure is now this one function.
    """
    if isinstance(outcome, CoverageDelta):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "delta", **body}
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def regression_outcome_payload(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, Any]:
    """Project a Regression outcome onto the envelope wire shape.

    Working draft — PM freezes the shape via a follow-up decision per
    ``decisions/2026-05-26-regression-facts-json-layout.md`` §C.2; until
    then consumers pattern-match on ``kind`` only. ``fact-set`` carries
    the full persisted body (verbatim ``RegressionFactSet.to_dict()`` with
    ``schema_version`` stripped); ``unavailable`` carries both
    ``baseline_run_reference`` and ``target_run_reference`` as
    independently nullable fields so the consumer can tell which side was
    missing (richer than Coverage's single-``run_reference`` shape).
    """
    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def localization_outcome_payload(
    outcome: LocalizationFinding | LocalizationUnavailable,
) -> dict[str, Any]:
    """Project a Localization outcome onto the envelope wire shape.

    ``fact-set`` carries the verbatim ``LocalizationFinding.to_dict()``
    with the top-level ``schema_version`` stripped (the finding shape
    itself is frozen by ``decisions/2026-05-28-localization-finding-shape-v2.md``);
    ``unavailable`` carries the 3-key ``LocalizationUnavailable.to_dict()``
    (``run_reference`` / ``reason`` / ``detail``, all always present;
    ``run_reference`` is ``null`` for the latest-resolution empty /
    non-analyzable cases). The nested ``LocalizationEntry`` /
    ``CodeLocation`` / ``EvidenceCitation`` shapes round-trip verbatim.
    """
    if isinstance(outcome, LocalizationFinding):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


def replay_outcome_payload(
    outcome: ReplayResult | ReplayUnavailable,
) -> dict[str, Any]:
    """Project a Replay outcome onto the frozen ``replay_outcome`` block.

    A ``ReplayResult`` surfaces as ``kind: "replay-result"`` with the full
    classification block; the original ``run_reference`` is dropped from
    the inner block because every emitting surface already carries it at
    the top level (``data.original_run_reference`` on the ``replay`` verb,
    ``run_reference`` on the inspect view). A ``ReplayUnavailable``
    surfaces as the 3-key ``kind: "unavailable"`` block.
    """
    if isinstance(outcome, ReplayResult):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        body.pop("run_reference", None)
        return {"kind": "replay-result", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


__all__ = [
    "coverage_delta_payload",
    "coverage_outcome_payload",
    "localization_outcome_payload",
    "regression_outcome_payload",
    "replay_outcome_payload",
]
