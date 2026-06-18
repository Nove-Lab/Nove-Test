"""Human-readable TEXT renderers for the ``novetest`` CLI.

Public surface is the single function ``render_text(envelope) -> str``,
consumed only by ``cli/output.py::emit_envelope`` for ``OutputMode.TEXT``.
The ``OutputMode.JSON`` / ``OutputMode.NDJSON`` wire shapes are untouched
by this package — AI agents pin against those; humans get this text.
"""

from novetest.cli.renderers.registry import render_text

__all__ = ["render_text"]
