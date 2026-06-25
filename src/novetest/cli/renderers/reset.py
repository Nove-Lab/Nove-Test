"""Text renderer for ``novetest reset`` (command token ``"reset"``)."""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import GLYPH_OK, format_engine_readiness

# Ordered (slot key, singular label, plural label) for the "removed" summary.
# The order pins the decision doc's ``items_removed`` key order; only ``runs``
# and ``tombstones`` inflect, the rest are mass-noun category labels. Zero-
# valued categories are suppressed to keep the line short.
_REMOVED_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("runs", "run", "runs"),
    ("tombstones", "tombstone", "tombstones"),
    ("coverage_facts", "coverage", "coverage"),
    ("regression_pairs", "regression", "regression"),
    ("localization_findings", "localization", "localization"),
    ("replay_results", "replay", "replay"),
)


def render_reset(envelope: Envelope) -> str:
    """Three-line reset summary: header, removed counts, engine readiness.

    ::

        ✓ Reset .novetest/ at /path/.novetest
          removed: 12 runs · 1 tombstone · 12 coverage · 7 regression · 8 localization · 2 replay
          engine readiness: ready — python/pytest 8.0.0

    Zero-valued ``items_removed`` categories are suppressed; an all-zero
    wipe (e.g. a freshly initialized store) renders ``removed: nothing``.
    The engine-readiness line reuses the same projection as ``init``.
    """

    data = envelope.data
    store_path = data.get("store_path", "?")
    items = data.get("items_removed", {})
    readiness = data.get("engine_readiness", {})

    parts = []
    for key, singular, plural in _REMOVED_CATEGORIES:
        count = items.get(key, 0)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    removed = " · ".join(parts) if parts else "nothing"

    lines = [
        f"{GLYPH_OK} Reset .novetest/ at {store_path}",
        f"  removed: {removed}",
        f"  {format_engine_readiness(readiness)}",
    ]
    for issue in readiness.get("issues", []):
        lines.append(f"  issue: {issue}")
    return "\n".join(lines)
