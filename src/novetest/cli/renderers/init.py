"""Text renderer for ``novetest init`` (command token ``"init"``)."""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import GLYPH_OK, format_engine_readiness


def render_init(envelope: Envelope) -> str:
    """Two-line init summary plus any engine-readiness issues.

    ::

        ✓ Initialized .novetest/ at /path/.novetest
          engine readiness: ready — python/pytest 9.0.3

    ``init`` never fails on a missing engine (readiness is informational),
    so the leading glyph is always ✓; engine absence surfaces in the
    readiness line as ``no engine detected``.
    """

    data = envelope.data
    store_path = data.get("store_path", "?")
    readiness = data.get("engine_readiness", {})

    lines = [
        f"{GLYPH_OK} Initialized .novetest/ at {store_path}",
        f"  {format_engine_readiness(readiness)}",
    ]
    for issue in readiness.get("issues", []):
        lines.append(f"  issue: {issue}")
    return "\n".join(lines)
