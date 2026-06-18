"""Text renderer for ``novetest replay`` (command token ``"replay"``)."""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._outcomes import replay_outcome_line


def render_replay(envelope: Envelope) -> str:
    """Classification glyph + rerun count + original run id.

    ::

        ✓ reproducible · 3/3 · run_id=01HX...
        ✗ inconsistent · 2/5 failed · run_id=01HX...
    """

    data = envelope.data
    original = data.get("original_run_reference", {}).get("run_id", "?")
    line = replay_outcome_line(data.get("replay_outcome", {}))
    return f"{line} · run_id={original}"
