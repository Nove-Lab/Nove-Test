"""Text renderer for the ``novetest licenses`` verb.

Renders the third-party attribution list as a scannable block grouped by
source (runtime / vendored / install-time bootstrap), one aligned line per
component (``<package> (<version>)`` left-padded, then the SPDX license). When
the envelope carries ``data.notices_text`` — i.e. ``--full`` was supplied —
the verbatim ``NOTICES.md`` body is appended after a divider.

No ANSI color (post-MVP per the text-renderer cycle); alignment is plain
``str.ljust``, column width computed from the widest component name so the
output is deterministic for the pinned const.
"""

from __future__ import annotations

from typing import Any

from novetest.cli.output import Envelope

# Human labels for the three ``source`` groups, rendered in this fixed order.
_SOURCE_GROUPS: tuple[tuple[str, str], ...] = (
    ("runtime", "runtime dependencies"),
    ("vendored", "vendored binary"),
    ("install-time-bootstrap", "install-time bootstrap"),
)

_ATTRIBUTION_PATH = "*.dist-info/licenses/NOTICES.md"
_FULL_DIVIDER = "--- VERBATIM NOTICES.md ---"


def _name_version(entry: dict[str, Any]) -> str:
    return f"{entry.get('package', '?')} ({entry.get('version', '?')})"


def render_licenses(envelope: Envelope) -> str:
    """Render the ``licenses`` envelope to human-readable text."""

    data = envelope.data
    licenses: list[dict[str, Any]] = list(data.get("licenses", []))

    lines = [f"licenses ({len(licenses)} third-party components)", ""]

    name_width = max((len(_name_version(e)) for e in licenses), default=0)
    for source, label in _SOURCE_GROUPS:
        members = [e for e in licenses if e.get("source") == source]
        if not members:
            continue
        lines.append(f"  {label}")
        for entry in members:
            namever = _name_version(entry).ljust(name_width)
            lines.append(f"    {namever}  {entry.get('license', '')}".rstrip())
        lines.append("")

    lines.append("  full verbatim license texts: novetest licenses --full")
    lines.append(f"  attribution file (in wheel): {_ATTRIBUTION_PATH}")

    notices_text = data.get("notices_text")
    if notices_text is not None:
        lines.append("")
        lines.append(f"  {_FULL_DIVIDER}")
        lines.append("")
        lines.append(str(notices_text))

    return "\n".join(lines)
