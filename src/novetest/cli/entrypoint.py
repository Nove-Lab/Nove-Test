"""Top-level argv plumbing for the ``novetest`` entrypoint (W3/S47, ORC-01).

The pre-Cyclopts argv preprocessing group extracted verbatim from
``cli/app.py``: the ``--output`` flag extraction, the ``-v`` / ``-h``
top-level intent scan, the Phase-6 default-verb alias injection, and the
version / help envelope emitters. ``cli/app.py::main`` composes these before
dispatching into the Cyclopts ``app`` — keeping this group here confines the
argv-shaping concern to one leaf module (no import of the registration
surface, so no ``app`` <-> ``entrypoint`` cycle).

Pure motion: byte-for-byte identical behavior to the pre-S47 ``cli/app.py``.
"""

from __future__ import annotations

from novetest.cli.output import (
    Envelope,
    OutputMode,
    emit_envelope,
)
from novetest.orchestration.onboarding.command_surface import describe_command_surface
from novetest.orchestration.onboarding.identity import report_cli_identity


_SUBCOMMAND_TOKENS: frozenset[str] = frozenset(
    {
        "test",
        "run",
        "memory",
        "coverage",
        "regression",
        "localization",
        "replay",
        "inspect",
        "compare",
        "status",
        "licenses",
        "init",
        "reset",
    }
)


def _extract_output_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull --output / --output=<v> out of argv; return (value, argv_without_flag)."""
    value: str | None = None
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--output":
            if i + 1 < len(argv):
                value = argv[i + 1]
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("--output="):
            value = tok.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(tok)
        i += 1
    return value, cleaned


def _scan_top_level_intent(argv: list[str]) -> str | None:
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in _SUBCOMMAND_TOKENS:
            return None
        if tok in ("-v", "--version"):
            return "version"
        if tok in ("-h", "--help"):
            return "help"
        if tok == "--output":
            i += 2
            continue
        if tok.startswith("--output="):
            i += 1
            continue
        i += 1
    return None


def _inject_default_verb_alias(argv: list[str]) -> list[str]:
    """Inject ``"test"`` before the first positional when it is not a verb.

    Implements the Phase 6 brief §6 default-verb alias:
    ``novetest <target>`` ≡ ``novetest test <target>`` whenever
    ``<target>`` is not in ``_SUBCOMMAND_TOKENS`` (the reserved verb set)
    and not a flag.

    Disambiguation rule: if the first positional token IS a reserved
    verb, ALWAYS route to that verb's handler even when a directory of
    the same name exists in the workspace. The reserved set wins
    unconditionally (so a workspace with a directory literally named
    ``inspect/`` cannot shadow ``novetest inspect <run_id>``).

    This is called from ``main()`` AFTER ``_extract_output_flag``
    (so ``--output`` and its value are already stripped) AND AFTER the
    top-level intent scan (so ``-v`` / ``-h`` keep their precedence).
    Bare ``novetest`` (empty argv after stripping) is handled separately
    in ``main()`` — that surface emits the help envelope directly per
    REQ-ORCH-006.

    Pure function — no side effects. Returns the (possibly-augmented)
    argv list; the original list is not mutated.
    """

    if not argv:
        return argv
    # Find the first positional (non-flag) token.
    for tok in argv:
        if tok.startswith("-"):
            continue
        # First positional. If it is a reserved verb, leave argv alone.
        if tok in _SUBCOMMAND_TOKENS:
            return argv
        # Else, inject "test" as the verb. Prepending preserves any
        # leading flags Cyclopts may consume at the top level.
        return ["test", *argv]
    # All tokens were flags — let Cyclopts handle (or reject) them.
    return argv


def _emit_version(mode: OutputMode) -> None:
    identity = report_cli_identity()
    emit_envelope(Envelope(command="version", ok=True, data=identity.to_dict()), mode)


def _emit_help(mode: OutputMode) -> None:
    surface = describe_command_surface()
    emit_envelope(Envelope(command="help", ok=True, data=surface.to_dict()), mode)
