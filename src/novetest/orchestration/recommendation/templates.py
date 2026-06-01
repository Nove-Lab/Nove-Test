"""One summary template per closed-taxonomy v1 category.

Template rendering is **pure string interpolation** of the
``CategoryHit.payload`` slot dict. No conditional prose, no LLM, no
randomness — same slots in, byte-identical summary string out. This
keeps the determinism contract (synthesis design doc §4) auditable at
template granularity.

Recommendation envelope shape (brief §3 / design doc §3):

.. code-block:: json

    {
      "recommendation_id": "rec_<run_id>_<sha1[:8]>",
      "category": "<category>",
      "priority": <int>,
      "summary": "<rendered template>",
      "slots": { ... },
      "evidence_citations": [ ... ]
    }

This file owns:

- ``Recommendation`` — the immutable wire-shape dataclass.
- ``SUMMARY_TEMPLATES`` — one template string per category.
- ``render_summary`` — pure renderer over (category, slots).
- ``build_recommendation`` — composer that ties slots + summary +
  citations + deterministic id into a ``Recommendation``.

The ``recommendation_id`` is derived from
``sha1(category|primary_slot)[:8]`` per the design doc §4 — bundled with
the run_id it is globally unique across runs and stable across re-derives
of the same fact bundle.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Final

from novetest.orchestration.recommendation.categories import (
    CATEGORIES,
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    CategoryHit,
)


# ---------------------------------------------------------------------------
# Recommendation wire-shape dataclass
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Recommendation:
    """One emitted recommendation (envelope wire shape).

    All fields are JSON-serializable primitives or lists/dicts thereof
    (brief §1 — "Slot semantics: All slot values are JSON-serializable
    primitives or lists thereof"). ``priority`` is the integer from
    ``categories.PRIORITIES`` (lower = more important).

    ``primary_slot`` is the category-specific stable sort key (brief §1
    "Stable ordering rule"). It is preserved on the dataclass so the
    final sort can apply ``(priority, category, primary_slot)`` without
    re-deriving — keeping the sort deterministic AND coherent with the
    brief's table. Internal: NOT surfaced via ``to_dict`` to keep the
    wire shape minimal (the brief §3 example envelope does not list
    ``primary_slot`` among the recommendation keys).
    """

    recommendation_id: str
    category: str
    priority: int
    summary: str
    primary_slot: str = ""
    slots: dict[str, Any] = field(default_factory=dict)
    evidence_citations: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"Invalid Recommendation.category={self.category!r}; "
                f"expected one of {sorted(CATEGORIES)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        # ``dict(...)`` defensive-copies so the caller cannot mutate the
        # dataclass's slot dict through the returned envelope.
        # ``primary_slot`` is internal — NOT included on the wire.
        return {
            "recommendation_id": self.recommendation_id,
            "category": self.category,
            "priority": self.priority,
            "summary": self.summary,
            "slots": dict(self.slots),
            "evidence_citations": [dict(c) for c in self.evidence_citations],
        }


# ---------------------------------------------------------------------------
# Summary templates — closed set, one per category
# ---------------------------------------------------------------------------


# Brief §1 froze the slot keys per category. The summary strings below are
# the pinned templates — wording change requires a ``schema_version`` bump.
SUMMARY_TEMPLATES: Final[dict[str, str]] = {
    CATEGORY_REGRESSION_WITH_LOCALIZATION: (
        "Test `{test_id}` newly failing in this run; "
        "suspected location {symbol_or_file_anchor} in `{file}` "
        "(rank {rank}, {formula}={score_normalized:.3f}, {mode})."
    ),
    CATEGORY_INVESTIGATE_LOCATION: (
        "Investigate {symbol_or_file_anchor} in `{file}` "
        "(rank {rank}, {formula}={score_normalized:.3f}, {mode})."
    ),
    CATEGORY_INVESTIGATE_REGRESSION: (
        "Test `{test_id}` newly failing this run "
        "(baseline `{run_reference_from}` → `{run_reference_to}`)."
    ),
    CATEGORY_COVERAGE_GAP: (
        "Uncovered code in `{file}` at line(s) {lines_str} "
        "overlaps a {mode} suspect ({related_finding_id})."
    ),
    CATEGORY_FLAKY_SUSPECTED: (
        "Test `{test_id}` flaky: {reruns_failed}/{reruns_total} reruns failed."
    ),
    CATEGORY_UNAVAILABLE_ANALYSIS: (
        "Failing tests but downstream analysis incomplete: "
        "{unavailable_stages_str}."
    ),
    CATEGORY_ALL_GREEN: (
        "All tests green; no action recommended "
        "(passed {passed}, skipped {skipped}, total {total_tests})."
    ),
}


def render_summary(category: str, slots: dict[str, Any]) -> str:
    """Render the category's pinned template against ``slots``.

    Slot keys consumed by each template are exactly the ones the matcher
    populated on ``CategoryHit.payload`` (per brief §1's slot-keys table);
    a few synthetic-key derivations live below (``symbol_or_file_anchor``,
    ``lines_str``, ``unavailable_stages_str``) so the rendered prose can
    stay one-line and stable.

    Returns the rendered string. Same ``(category, slots)`` in →
    byte-identical string out.
    """

    if category not in SUMMARY_TEMPLATES:
        raise ValueError(f"No summary template for category={category!r}")
    template = SUMMARY_TEMPLATES[category]
    rendering = dict(slots)
    rendering.setdefault("symbol_or_file_anchor", _symbol_or_file_anchor(slots))
    rendering.setdefault("lines_str", _lines_str(slots))
    rendering.setdefault(
        "unavailable_stages_str", _unavailable_stages_str(slots)
    )
    return template.format(**rendering)


# ---------------------------------------------------------------------------
# Recommendation builder — ties everything together
# ---------------------------------------------------------------------------


def build_recommendation(
    *,
    hit: CategoryHit,
    run_id: str,
    citations: list[dict[str, Any]],
) -> Recommendation:
    """Build the final ``Recommendation`` for one ``CategoryHit``.

    ``recommendation_id`` is deterministic per design doc §4 — formed
    from ``sha1(f"{category}|{primary_slot}")[:8]`` and prefixed with
    ``rec_<run_id>_``. The hash ensures the id is identifiable + stable;
    the ``run_id`` prefix scopes uniqueness to a run so two runs producing
    the same category+slot don't collide.

    Citations come from ``citations.py::cite_recommendation_evidence`` —
    this function does not invent them. ``slots`` is a verbatim copy of
    the hit's payload (the brief §1 slot-keys table makes the matcher
    payload the canonical wire shape; no further projection needed).
    """

    rec_id = _recommendation_id(
        run_id=run_id, category=hit.category, primary_slot=hit.primary_slot
    )
    summary = render_summary(hit.category, hit.payload)
    return Recommendation(
        recommendation_id=rec_id,
        category=hit.category,
        priority=hit.priority,
        summary=summary,
        primary_slot=hit.primary_slot,
        slots=dict(hit.payload),
        evidence_citations=list(citations),
    )


def _recommendation_id(*, run_id: str, category: str, primary_slot: str) -> str:
    """Deterministic 8-char-hash-suffixed id. See design doc §4."""

    digest = hashlib.sha1(
        f"{category}|{primary_slot}".encode("utf-8")
    ).hexdigest()
    return f"rec_{run_id}_{digest[:8]}"


def _symbol_or_file_anchor(slots: dict[str, Any]) -> str:
    """Render the ``{symbol}@{primary_line}`` or ``{file}:{primary_line}`` anchor.

    Symbol-level findings get ``symbol@primary_line`` (the
    most-informative-line-in-the-symbol convention from
    ``CodeLocation.primary_line``); file-level findings fall back to
    ``{file}:{primary_line}``.
    """

    symbol = slots.get("symbol")
    primary_line = slots.get("primary_line")
    if symbol:
        return f"`{symbol}`@{primary_line}"
    file_val = slots.get("file") or ""
    return f"`{file_val}`:{primary_line}"


def _lines_str(slots: dict[str, Any]) -> str:
    """Render a deterministic ``"1, 2, 5"``-style line list."""

    lines = slots.get("lines") or []
    return ", ".join(str(line) for line in lines)


def _unavailable_stages_str(slots: dict[str, Any]) -> str:
    """Render the brief §1 closed list of unavailable stages with reasons.

    Format: ``"coverage (no_coverage_data), localization (run_not_analyzable)"``
    — stable order matches ``StageEligibility.unavailable_stages()`` which
    already returns them in the brief §1 order.
    """

    stages = slots.get("unavailable_stages") or []
    reasons = slots.get("reason_per_stage") or {}
    pieces = []
    for stage in stages:
        reason = reasons.get(stage)
        if reason:
            pieces.append(f"{stage} ({reason})")
        else:
            pieces.append(stage)
    return ", ".join(pieces)


__all__ = [
    "Recommendation",
    "SUMMARY_TEMPLATES",
    "build_recommendation",
    "render_summary",
]
