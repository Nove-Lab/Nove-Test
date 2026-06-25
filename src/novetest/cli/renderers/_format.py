"""Shared, domain-agnostic formatting primitives for the text renderers.

Hand-rolled (no ``rich`` / ``colorama`` / new runtime dep) and **no ANSI
color** — color is deferred post-MVP per the renderer task brief
§"Out of scope". The status glyphs (``✓`` / ``✗`` / ``—`` / ``⚠``) are
plain Unicode literals that render on every modern terminal (Windows
Terminal, PowerShell, every *nix terminal); legacy ``cmd.exe`` may show a
box but the surrounding textual code (``passed``, ``3/3``, etc.) still
conveys the meaning.

Everything here is a pure function — no I/O, no globals, deterministic for
the same input. The verb renderers compose these primitives; the
kind-discriminated engine-outcome blocks live in ``_outcomes.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

# Status glyphs — Unicode literals, no ANSI escapes.
GLYPH_OK = "✓"  # ✓
GLYPH_FAIL = "✗"  # ✗
GLYPH_UNAVAILABLE = "—"  # —
GLYPH_WARN = "⚠"  # ⚠
GLYPH_ACTION = "!"
GLYPH_UNKNOWN = "?"


_PASS_STATUSES = frozenset({"passed", "pass", "ok"})
_FAIL_STATUSES = frozenset({"failed", "fail", "errored", "error"})


def run_status_glyph(status: str) -> str:
    """Map a normalized Run Record status to a glyph.

    ``passed`` → ✓, ``failed`` / ``errored`` → ✗, anything else → —.
    """

    lowered = status.lower()
    if lowered in _PASS_STATUSES:
        return GLYPH_OK
    if lowered in _FAIL_STATUSES:
        return GLYPH_FAIL
    return GLYPH_UNAVAILABLE


def availability_glyph(state: str) -> str:
    """Map a sub-report availability flag to a glyph (``available`` → ✓)."""

    return GLYPH_OK if state == "available" else GLYPH_UNAVAILABLE


def format_timestamp(value: Any) -> str:
    """Render an epoch-milliseconds integer as an ISO-8601 UTC string.

    Deterministic: the same millisecond value always renders the same
    string. Non-integer input (defensive — the wire shape pins these as
    ``int``) is passed through via ``str`` so a renderer never raises on a
    malformed envelope.
    """

    if not isinstance(value, int):
        return str(value)
    moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


def percent(value: Any) -> str:
    """Render a float percentage to one decimal place (``86.7%``)."""

    if isinstance(value, (int, float)):
        return f"{float(value):.1f}%"
    return str(value)


def target_label(target_expression: str) -> str:
    """Human label for a Run Record target expression.

    An empty expression is the whole-workspace target; render it as the
    explicit ``<workspace>`` token rather than a confusing blank.
    """

    return target_expression if target_expression else "<workspace>"


def format_engine_readiness(readiness: Mapping[str, Any]) -> str:
    """Shared ``engine readiness: <state> — <engine>`` projection line.

    Both ``render_init`` and ``render_reset`` print the identical engine
    readiness line — this is the single source of that projection. Returns
    the line content WITHOUT leading indentation (the caller owns layout).
    A missing/false engine renders ``no engine detected``; a present engine
    renders ``<ecosystem>/<engine>`` with an optional `` <version>`` suffix.
    """

    state = readiness.get("state", "?")
    engine = readiness.get("engine")
    ecosystem = readiness.get("ecosystem")
    engine_version = readiness.get("engine_version")
    if engine:
        engine_part = f"{ecosystem}/{engine}"
        if engine_version:
            engine_part += f" {engine_version}"
    else:
        engine_part = "no engine detected"
    return f"engine readiness: {state} — {engine_part}"


def indent_block(text: str, prefix: str = "  ") -> str:
    """Prefix every line of a (possibly multi-line) string with ``prefix``."""

    return "\n".join(prefix + line for line in text.split("\n"))


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a left-aligned, space-padded column table.

    Columns are sized to the widest cell (header or body). Cells are joined
    by two spaces; trailing whitespace is stripped per line so the output
    is stable for snapshot pinning. An empty ``rows`` list renders the
    header alone.
    """

    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(cells: list[str]) -> str:
        padded = [cells[i].ljust(widths[i]) for i in range(len(cells))]
        return "  ".join(padded).rstrip()

    lines = [render_row(headers)]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)
