"""Text renderers for the onboarding surfaces: ``--version`` and ``--help``.

Both are argv-pre-Cyclopts surfaces emitted directly from ``main()`` (see
``cli/app.py::_emit_version`` / ``_emit_help``), so their ``command``
tokens are ``"version"`` and ``"help"``.
"""

from __future__ import annotations

from novetest.cli.output import Envelope


def render_version(envelope: Envelope) -> str:
    """One-line CLI identity: ``novetest 0.1.1 (Python 3.11.9, linux-x86_64)``."""

    data = envelope.data
    version = data.get("installedVersion", "?")
    python_version = data.get("pythonVersion", "?")
    platform = data.get("platform", "?")
    return f"novetest {version} (Python {python_version}, {platform})"


def render_help(envelope: Envelope) -> str:
    """Verb listing grouped by section (Onboarding / Operating).

    Each verb is one aligned line: ``<name>  <summary>``. The name column
    is sized to the widest verb name across both sections so the summaries
    line up.
    """

    data = envelope.data
    onboarding = data.get("onboarding", [])
    operating = data.get("operating", [])
    width = max(
        (len(spec.get("name", "")) for spec in [*onboarding, *operating]),
        default=0,
    )

    lines = ["novetest — AI-first testing orchestration", ""]
    for title, specs in (("Onboarding", onboarding), ("Operating", operating)):
        if not specs:
            continue
        lines.append(f"{title}:")
        for spec in specs:
            name = spec.get("name", "")
            summary = spec.get("summary", "")
            lines.append(f"  {name.ljust(width)}  {summary}")
        lines.append("")
    return "\n".join(lines).rstrip()
