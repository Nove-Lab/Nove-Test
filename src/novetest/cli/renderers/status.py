"""Text renderer for ``novetest status`` (command token ``"status"``)."""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import availability_glyph

# Fixed render order for the four sub-reports (deterministic, independent of
# dict iteration order).
_SUB_REPORTS = ("coverage", "regression", "localization", "replay")


def render_status(envelope: Envelope) -> str:
    """Latest-run header + per-sub-report availability list.

    ::

        latest run · 01HX... · history: 2 runs

          ✓ coverage       available
          — regression     unavailable
          ...
    """

    data = envelope.data
    latest = data.get("latest_run_reference")
    history_size = data.get("run_history_size", 0)
    run_word = "run" if history_size == 1 else "runs"

    if latest is None:
        return f"no runs yet · history: {history_size} {run_word}"

    run_id = latest.get("run_id", "?")
    sub_reports = data.get("sub_reports", {})
    lines = [f"latest run · {run_id} · history: {history_size} {run_word}", ""]
    for name in _SUB_REPORTS:
        state = sub_reports.get(name, "unavailable")
        lines.append(f"  {availability_glyph(state)} {name.ljust(13)} {state}")
    return "\n".join(lines)
