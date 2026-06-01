"""``synthesize_recommendation`` — the pure synthesis entrypoint.

Pipeline (design doc §5):

1. Run every category matcher in priority order.
2. Apply ``compound_resolution`` — drops constituents of any
   ``regression_with_localization`` compound.
3. Apply ``apply_mutual_exclusion`` — drops ``all_green`` whenever any
   other category fired.
4. Build a ``Recommendation`` per surviving hit (citations attached).
5. Sort by ``(priority asc, category asc, primary_slot asc)``.
6. Return the byte-deterministic list.

The function is pure: same ``FactBundle`` in → byte-identical
``list[Recommendation]`` out (modulo whatever is already embedded in the
bundle; the function itself adds no time- or randomness-dependent
inputs).
"""

from __future__ import annotations

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
    list is stable per the brief §1 sort key.
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


def _stable_sort_key(rec: Recommendation) -> tuple[int, str, str, str]:
    """Brief §1 — ``(priority asc, category asc, primary_slot asc)``.

    ``primary_slot`` is the category-specific stable sort key per the
    brief §1 table (e.g. ``"src/calc.py:32"`` for an investigate_location
    on calc.py line 32). It is preserved on the ``Recommendation``
    dataclass at build time so the final sort is byte-deterministic AND
    matches the brief's intent (rank-1 lex-min file wins; sha1 hash
    ordering would break that invariant).

    ``recommendation_id`` is the 4th tiebreaker so two recommendations
    at the same ``(priority, category, primary_slot)`` (which the design
    treats as impossible by construction) still produce a stable order.
    """

    return (rec.priority, rec.category, rec.primary_slot, rec.recommendation_id)


__all__ = [
    "RECOMMENDATION_SCHEMA_VERSION",
    "synthesize_recommendation",
]
