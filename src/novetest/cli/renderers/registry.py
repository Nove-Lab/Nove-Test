"""Verb → renderer dispatch + the public ``render_text`` entry point.

Single source of truth for which command token maps to which renderer
function. ``render_text`` is the only symbol ``cli/output.py`` imports (via
a deferred import inside ``emit_envelope`` — see that function's note on
the dependency direction).

Dispatch model:

1. An envelope carrying ``errors`` (every ``ok == False`` path sets at
   least one) renders the generic error block, regardless of command — so
   stub ``not-implemented``, ``uninitialized``, ``not-found``, adapter, and
   engine-readiness errors all get a consistent human surface.
2. Otherwise dispatch by ``envelope.command``; an unknown command falls
   back to ``render_fallback`` (the safety net for any future verb whose
   renderer has not been wired yet).
3. Non-empty ``warnings`` append a trailing ``warnings:`` block in both
   cases.
"""

from __future__ import annotations

from typing import Callable

from novetest.cli.output import Envelope, EnvelopeError, EnvelopeWarning
from novetest.cli.renderers._format import GLYPH_FAIL, GLYPH_WARN
from novetest.cli.renderers.compare import render_compare
from novetest.cli.renderers.coverage import (
    render_coverage_diff,
    render_coverage_show,
)
from novetest.cli.renderers.init import render_init
from novetest.cli.renderers.inspect import render_inspect
from novetest.cli.renderers.localization import (
    render_localization,
    render_localization_latest,
)
from novetest.cli.renderers.memory import (
    render_memory_delete,
    render_memory_list,
    render_memory_show,
)
from novetest.cli.renderers.onboarding import render_help, render_version
from novetest.cli.renderers.regression import (
    render_regression_compare,
    render_regression_latest,
)
from novetest.cli.renderers.replay import render_replay
from novetest.cli.renderers.run import render_run
from novetest.cli.renderers.status import render_status
from novetest.cli.renderers.test import render_test

_RENDERERS: dict[str, Callable[[Envelope], str]] = {
    "version": render_version,
    "help": render_help,
    "init": render_init,
    "test": render_test,
    "run": render_run,
    "status": render_status,
    "inspect": render_inspect,
    "compare": render_compare,
    "replay": render_replay,
    "memory.list": render_memory_list,
    "memory.show": render_memory_show,
    "memory.delete": render_memory_delete,
    "coverage.show": render_coverage_show,
    "coverage.diff": render_coverage_diff,
    "regression.compare": render_regression_compare,
    "regression.latest": render_regression_latest,
    "localization": render_localization,
    "localization.latest": render_localization_latest,
}


def render_fallback(envelope: Envelope) -> str:
    """Safety net for an unknown command token (no wired renderer)."""

    return (
        f"{envelope.command}: no human renderer "
        f"(use --output json for full detail)"
    )


def render_error(envelope: Envelope) -> str:
    """Generic error block for any ``ok == False`` envelope.

    ::

        ✗ <command>
          <code>: <message>
          <install_hint when present>
    """

    lines = [f"{GLYPH_FAIL} {envelope.command}"]
    for error in envelope.errors:
        lines.append(f"  {error.code}: {error.message}")
        lines.extend(_error_detail_lines(error))
    return "\n".join(lines)


def _error_detail_lines(error: EnvelopeError) -> list[str]:
    hint = error.details.get("install_hint")
    return [f"  {hint}"] if hint else []


def render_warnings(warnings: tuple[EnvelopeWarning, ...]) -> str:
    """Trailing ``warnings:`` block (one ⚠ line per warning)."""

    lines = ["warnings:"]
    for warning in warnings:
        lines.append(f"  {GLYPH_WARN} {warning.code}: {warning.message}")
    return "\n".join(lines)


def render_text(envelope: Envelope) -> str:
    """Render an envelope to human-readable text (public entry point)."""

    if envelope.errors:
        body = render_error(envelope)
    else:
        renderer = _RENDERERS.get(envelope.command, render_fallback)
        body = renderer(envelope)
    if envelope.warnings:
        body += "\n" + render_warnings(envelope.warnings)
    return body
