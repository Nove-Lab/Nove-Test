"""Text renderer for the integrated ``novetest test`` verb (token ``"test"``).

The most user-facing surface: a recommendation summary line followed by one
block per recommendation (glyph + category tag + the synthesizer's own
human ``summary`` sentence + the first Evidence Citation). The recommendation
``summary`` is already a fully-formed sentence (the synthesizer renders it
from the closed-taxonomy templates), so the renderer's job is to frame it,
not rewrite it.
"""

from __future__ import annotations

from typing import Any

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import GLYPH_ACTION, GLYPH_OK, GLYPH_UNAVAILABLE

# Glyph per closed-taxonomy v1 category (categories.py). ``all_green`` is a
# clean bill of health (✓); ``unavailable_analysis`` is an informational
# "we owe you an explanation" surface (—); the five investigation
# categories are actionable (!).
_CATEGORY_GLYPHS = {
    "all_green": GLYPH_OK,
    "unavailable_analysis": GLYPH_UNAVAILABLE,
}


def _category_glyph(category: str) -> str:
    return _CATEGORY_GLYPHS.get(category, GLYPH_ACTION)


def _citation_line(citation: dict[str, Any]) -> str:
    """Render the first Evidence Citation to a compact provenance line.

    Each Recommendation carries ≥1 citation (NFR-ORCH-002); the kinds are
    the closed set produced by ``recommendation/citations.py``.
    """

    kind = citation.get("kind", "?")
    selector = citation.get("selector", {})
    if kind == "run_reference":
        run_id = citation.get("run_reference", {}).get("run_id", "?")
        return f"run_reference {run_id}"
    if kind == "localization_finding":
        return (
            f"localization_finding {selector.get('file', '?')}"
            f":{selector.get('primary_line', '?')} (rank {selector.get('rank', '?')})"
        )
    if kind == "coverage_fact":
        return f"coverage_fact {selector.get('file', '?')}"
    if kind == "regression_fact":
        return f"regression_fact {selector.get('test_id', '?')}"
    if kind == "test_result":
        test_id = citation.get("test_id", selector.get("test_id", "?"))
        return f"test_result {test_id} ({citation.get('outcome', '?')})"
    if kind == "replay_result":
        return f"replay_result {selector.get('classification', '?')}"
    return str(kind)


def render_test(envelope: Envelope) -> str:
    """Recommendation summary line + one block per recommendation."""

    data = envelope.data
    recommendations = data.get("recommendations", [])
    run_id = data.get("run_reference", {}).get("run_id", "?")

    count = len(recommendations)
    category_count = len({rec.get("category") for rec in recommendations})
    rec_word = "recommendation" if count == 1 else "recommendations"
    cat_word = "category" if category_count == 1 else "categories"
    summary = (
        f"{count} {rec_word} · {category_count} {cat_word} · run_id={run_id}"
    )
    if not recommendations:
        return summary

    lines = [summary, ""]
    for rec in recommendations:
        category = rec.get("category", "?")
        glyph = _category_glyph(category)
        lines.append(f"  {glyph} [{category}] {rec.get('summary', '')}")
        citations = rec.get("evidence_citations", [])
        if citations:
            lines.append(f"      ↳ {_citation_line(citations[0])}")
    return "\n".join(lines)
