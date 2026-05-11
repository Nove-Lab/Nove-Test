from __future__ import annotations

import sys
from typing import Any, Callable

from cyclopts import App

from novetest import __version__
from novetest.cli.output import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    OutputMode,
    apply_no_color,
    emit_envelope,
    not_implemented_envelope,
    resolve_output_mode,
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
        "init",
    }
)

app = App(
    name="novetest",
    version=__version__,
    help="Nove Test - AI-first testing orchestration.",
)

_active_mode: OutputMode = OutputMode.JSON


def _make_stub(command_path: str) -> Callable[..., None]:
    def _stub(*args: Any, **kwargs: Any) -> None:
        emit_envelope(not_implemented_envelope(command_path), _active_mode)
        sys.exit(EXIT_USAGE)

    _stub.__name__ = command_path.replace(".", "_")
    _stub.__doc__ = f"Stub for {command_path}; not yet implemented."
    return _stub


def _register_flat(name: str) -> None:
    stub = _make_stub(name)
    app.command(stub, name=name)


def _register_group(group: str, verbs: tuple[str, ...]) -> None:
    sub = App(name=group, help=f"{group} commands (stub - not yet implemented).")
    app.command(sub)
    for verb in verbs:
        stub = _make_stub(f"{group}.{verb}")
        sub.command(stub, name=verb)


def _register_stubs() -> None:
    for name in ("test", "run", "inspect", "compare", "status", "init", "replay", "localization"):
        _register_flat(name)
    _register_group("memory", ("list", "show", "delete"))
    _register_group("coverage", ("show", "diff"))
    _register_group("regression", ("compare", "latest"))


_register_stubs()


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


def _emit_version(mode: OutputMode) -> None:
    identity = report_cli_identity()
    emit_envelope(Envelope(command="version", ok=True, data=identity.to_dict()), mode)


def _emit_help(mode: OutputMode) -> None:
    surface = describe_command_surface()
    emit_envelope(Envelope(command="help", ok=True, data=surface.to_dict()), mode)


def main(argv: list[str] | None = None) -> None:
    global _active_mode
    raw = list(sys.argv[1:] if argv is None else argv)
    explicit, args = _extract_output_flag(raw)
    mode = resolve_output_mode(explicit)
    apply_no_color(mode)
    _active_mode = mode

    intent = _scan_top_level_intent(args)
    if intent == "version":
        _emit_version(mode)
        sys.exit(EXIT_OK)
    if intent == "help":
        _emit_help(mode)
        sys.exit(EXIT_OK)

    try:
        app(args)
    except SystemExit:
        raise
    except Exception as exc:
        emit_envelope(
            Envelope(
                command="cli",
                ok=False,
                errors=(EnvelopeError(code="cli-error", message=str(exc)),),
            ),
            mode,
        )
        sys.exit(EXIT_GENERIC)
