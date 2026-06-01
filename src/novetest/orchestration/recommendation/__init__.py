"""Recommendation synthesis — closed taxonomy v1.

Public exports mirror ``design/interace-contract/orchestration.md`` §2's
two recommendation interfaces:

- ``synthesize_recommendation`` — main entry; pure function over ``FactBundle``.
- ``cite_recommendation_evidence`` — per-hit citation builder (also used
  internally by ``synthesize_recommendation``; re-exported for the
  NFR-ORCH-002 round-trip test + future Phase 7 MCP surface).

Plus the discriminator types callers need:

- ``Recommendation`` — wire-shape dataclass.
- ``FactBundle`` / ``StageEligibility`` / ``ReplayResult`` — pure-input shape.
- ``RECOMMENDATION_SCHEMA_VERSION`` — wire-shape version emitted on the
  envelope as ``data.recommendation_schema_version``.

Implementation lives across five modules per the brief §3 layout:

- ``categories.py``  — closed taxonomy + trigger predicates + compound/exclusion.
- ``templates.py``   — slot-driven summary text + ``Recommendation`` dataclass.
- ``citations.py``   — polymorphic-by-``kind`` citation projections.
- ``synthesizer.py`` — the pure pipeline ties categories + templates + citations.
- ``fact_bundle.py`` — ``FactBundle`` + ``StageEligibility`` + Replay placeholder.

Synthesis is rule-based + deterministic — no LLM in the synthesis path
(design doc §1). Same ``FactBundle`` → byte-identical
``list[Recommendation]``.
"""

from novetest.orchestration.recommendation.categories import (
    CATEGORIES,
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    PRIORITIES,
)
from novetest.orchestration.recommendation.citations import (
    cite_recommendation_evidence,
)
from novetest.orchestration.recommendation.fact_bundle import (
    FactBundle,
    ReplayResult,
    StageEligibility,
    build_fact_bundle,
)
from novetest.orchestration.recommendation.synthesizer import (
    RECOMMENDATION_SCHEMA_VERSION,
    synthesize_recommendation,
)
from novetest.orchestration.recommendation.templates import (
    Recommendation,
    build_recommendation,
    render_summary,
)


__all__ = [
    "CATEGORIES",
    "CATEGORY_ALL_GREEN",
    "CATEGORY_COVERAGE_GAP",
    "CATEGORY_FLAKY_SUSPECTED",
    "CATEGORY_INVESTIGATE_LOCATION",
    "CATEGORY_INVESTIGATE_REGRESSION",
    "CATEGORY_REGRESSION_WITH_LOCALIZATION",
    "CATEGORY_UNAVAILABLE_ANALYSIS",
    "FactBundle",
    "PRIORITIES",
    "RECOMMENDATION_SCHEMA_VERSION",
    "Recommendation",
    "ReplayResult",
    "StageEligibility",
    "build_fact_bundle",
    "build_recommendation",
    "cite_recommendation_evidence",
    "render_summary",
    "synthesize_recommendation",
]
