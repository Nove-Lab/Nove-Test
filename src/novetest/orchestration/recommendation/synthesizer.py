"""``synthesize_recommendation`` — the pure synthesis entrypoint.

Pipeline (design doc §5):

1. Run every category matcher in priority order.
2. Apply ``compound_resolution`` — drops constituents of any
   ``regression_with_localization`` compound.
3. Apply ``apply_mutual_exclusion`` — drops ``all_green`` whenever any
   other category fired.
4. Build a ``Recommendation`` per surviving hit (citations attached).
5. Sort by ``(priority asc, category asc, rank asc, score_normalized
   desc, primary_slot asc, recommendation_id asc)``.
6. Return the byte-deterministic list.

The function is pure: same ``FactBundle`` in → byte-identical
``list[Recommendation]`` out (modulo whatever is already embedded in the
bundle; the function itself adds no time- or randomness-dependent
inputs).
"""

from __future__ import annotations

import sys
from typing import Final

from novetest.orchestration.recommendation.categories import (
    MATCHERS_BY_PRIORITY,
    CategoryHit,
    apply_mutual_exclusion,
    compound_resolution,
)
from novetest.orchestration.recommendation.citations import (
    cite_recommendation_evidence,
)
from novetest.orchestration.recommendation.fact_bundle import FactBundle
from novetest.orchestration.recommendation.templates import (
    Recommendation,
    build_recommendation,
)


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


# The wire-shape version emitted on the envelope as
# ``data.recommendation_schema_version``. Bumping requires a follow-up
# PM decision per the brief §"Adding a new category".
RECOMMENDATION_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def synthesize_recommendation(bundle: FactBundle) -> list[Recommendation]:
    """Pure rule-based recommendation synthesis.

    Same ``FactBundle`` → byte-identical ``list[Recommendation]``
    (determinism contract, design doc §4). No I/O, no randomness, no LLM.

    Citation order within each recommendation is stable
    (see ``citations._sort_citations``); recommendation order across the
    list is stable per ``_stable_sort_key`` — and, within one
    ``(priority, category)`` group, follows the analysis's own confidence
    ordering (rank asc, score_normalized desc).
    """

    hits: list[CategoryHit] = []
    for _priority, _name, matcher in MATCHERS_BY_PRIORITY:
        hits.extend(matcher(bundle))

    hits = compound_resolution(hits)
    hits = apply_mutual_exclusion(hits)

    run_id = bundle.run_reference.run_id
    recommendations: list[Recommendation] = [
        build_recommendation(
            hit=hit,
            run_id=run_id,
            citations=cite_recommendation_evidence(hit, bundle),
        )
        for hit in hits
    ]
    recommendations.sort(key=_stable_sort_key)
    return recommendations


# Sentinels for categories whose slots carry no confidence ordering
# (everything except ``investigate_location`` and
# ``regression_with_localization``). Both sort LAST in their dimension, so
# a rank-less group falls straight through to ``primary_slot`` and keeps
# byte-identical ordering to the pre-rank key.
_NO_RANK: Final[int] = sys.maxsize
_NO_SCORE: Final[float] = -1.0  # score_normalized is [0.0, 1.0]


def _rank_of(rec: Recommendation) -> int:
    """``slots["rank"]`` as a sort dimension, or the explicit sentinel."""

    value = rec.slots.get("rank")
    if isinstance(value, bool) or not isinstance(value, int):
        return _NO_RANK
    return value


def _score_of(rec: Recommendation) -> float:
    """``slots["score_normalized"]`` as a sort dimension, or the sentinel.

    NaN is rejected into the sentinel: it compares False against
    everything, which would make the key non-total and break the
    determinism contract.
    """

    value = rec.slots.get("score_normalized")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _NO_SCORE
    number = float(value)
    if number != number:  # NaN
        return _NO_SCORE
    return number


def _stable_sort_key(rec: Recommendation) -> tuple[int, str, int, float, str, str]:
    """``(priority, category, rank, -score_normalized, primary_slot, id)``.

    Cross-``priority`` and cross-``category`` ordering is unchanged — the
    taxonomy's priority order is still the outermost dimension. What the
    two inner dimensions fix is the order WITHIN one
    ``(priority, category)`` group: it now follows the analysis's own
    confidence ordering (ascending ``slots["rank"]``, then descending
    ``slots["score_normalized"]``) instead of the lexicographic file path
    that ``primary_slot`` happens to start with.

    That old behavior was a latent defect: ``primary_slot`` for
    ``investigate_location`` is ``"{file}:{anchor}"``, so a rank-3 suspect
    in ``a.py`` sorted ahead of the rank-1 suspect in ``z.py`` and a
    consumer reading ``recommendations[0]`` was routed to the weakest
    entry in the list (wave-1 persona P1, 2026-07-28).

    ``primary_slot`` keeps its current value and meaning; it is now the
    3rd-level tiebreaker rather than the 1st. ``recommendation_id`` stays
    the final tiebreaker so two recommendations agreeing on every earlier
    dimension (which the design treats as impossible by construction)
    still produce a stable order.

    Every dimension is total: ints, a NaN-free float, and two strings.
    The score is negated because Python sorts ascending and a HIGHER
    normalized score is a STRONGER suspect.

    This layer deliberately does NOT filter or re-weight what the
    analysis produced (e.g. failing-test-file locations) — the candidate
    set is the localization engine's contract; duplicating that rule here
    is how the two layers drift.
    """

    return (
        rec.priority,
        rec.category,
        _rank_of(rec),
        -_score_of(rec),
        rec.primary_slot,
        rec.recommendation_id,
    )


__all__ = [
    "RECOMMENDATION_SCHEMA_VERSION",
    "synthesize_recommendation",
]
