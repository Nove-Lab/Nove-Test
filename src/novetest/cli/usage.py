"""Structured usage / help surfaces for the JSON output modes.

Cyclopts owns argument parsing, and by default it reports parse and
validation failures — and prints ``--help`` — as Rich-formatted human
text, regardless of the resolved output mode. For the AI-agent consumer
that pinned ``NOVETEST_OUTPUT=json`` once at session start (exactly what
the docs teach), that breaks the ``novetest/v1`` promise on the ERROR
path, which is the worst place to break it: a ``| python -m json.tool``
pipe swallows the message entirely and the agent has to re-run blind to
discover what went wrong (wave-1 persona P2, 2026-07-28).

This module projects those Cyclopts surfaces onto the standard envelope:

- ``usage_error_envelope`` — parse / validation failures.
- ``help_envelope``       — ``novetest <subcommand> --help``.
- ``classify_builtin_surface`` — tells ``cli/app.py::main`` which of the
  two (if either) a resolved Cyclopts command is.

Every function here is pure: same ``(app, tokens)`` in → byte-identical
envelope out. ``cli/app.py::main`` decides *when* to call them and owns
the exit codes.

**Exit codes are deliberately unchanged by this module.** Usage errors
keep the exit 1 Cyclopts returned before; ``--help`` keeps exit 0. Only
the emitted body changes. (The orchestration interface contract describes
flag/usage errors as exit 2 — reconciling that is a separate, versioned
contract decision and explicitly out of scope here.)

Text mode is untouched: ``main`` only routes through this module for
``json`` / ``ndjson``, so a human at a TTY keeps the Rich rendering.
"""

from __future__ import annotations

from typing import Any, Callable, Final, Literal

from cyclopts import App
from cyclopts.exceptions import (
    CoercionError,
    CycloptsError,
    MissingArgumentError,
    UnknownCommandError,
    UnknownOptionError,
    UnusedCliTokensError,
    ValidationError,
)

from novetest.cli.output import Envelope, EnvelopeError

# Wire version of the ``data`` block emitted by ``help_envelope``. Kept
# separate from the envelope ``schema`` (``novetest/v1``) and from the
# command-surface version used by the top-level ``novetest --help``.
HELP_SCHEMA_VERSION: Final[int] = 1

# Envelope ``command`` used when no command chain could be resolved
# (e.g. an unknown top-level verb) — mirrors the generic ``cli-error``
# fallback ``main`` already uses.
_UNRESOLVED_COMMAND: Final[str] = "cli"

# Closed error-code vocabulary for the usage class. Ordered: the FIRST
# ``isinstance`` match wins, so a Cyclopts subclass that is not listed
# (e.g. ``ConsumeMultipleError`` under ``MissingArgumentError``) resolves
# to its listed parent instead of falling through to the generic token.
# Anything genuinely unlisted becomes ``usage-error`` — agents can pin on
# that as the class-level token.
_ERROR_CODES: Final[tuple[tuple[type[CycloptsError], str], ...]] = (
    (UnknownOptionError, "unknown-option"),
    (UnknownCommandError, "unknown-command"),
    (MissingArgumentError, "missing-argument"),
    (CoercionError, "invalid-value"),
    (ValidationError, "invalid-value"),
    (UnusedCliTokensError, "unexpected-argument"),
)
USAGE_ERROR_FALLBACK_CODE: Final[str] = "usage-error"


def classify_builtin_surface(
    command: Callable[..., Any],
) -> Literal["help", "version"] | None:
    """Name the Cyclopts built-in a resolved command is, if any.

    Cyclopts resolves ``--help`` / ``-h`` to ``App.help_print`` and
    ``--version`` to ``App.version_print`` (they are registered as
    commands on every app). Both print human text straight to a console,
    so JSON mode has to intercept them before dispatch.
    """

    underlying = getattr(command, "__func__", None)
    if underlying is App.help_print:
        return "help"
    if underlying is App.version_print:
        return "version"
    return None


def usage_error_code(exc: CycloptsError) -> str:
    """Map a Cyclopts parse failure onto the closed error-code vocabulary."""

    for exc_type, code in _ERROR_CODES:
        if isinstance(exc, exc_type):
            return code
    return USAGE_ERROR_FALLBACK_CODE


def usage_error_envelope(
    app: App, tokens: list[str], exc: CycloptsError
) -> Envelope:
    """``ok: false`` envelope for a Cyclopts parse / validation failure.

    ``message`` is Cyclopts' own rendered sentence (the same text the
    Rich box carried), so nothing an operator could read before is lost.
    """

    chain = _command_chain(app, tokens)
    command = ".".join(chain) if chain else _UNRESOLVED_COMMAND
    return Envelope(
        command=command,
        ok=False,
        errors=(
            EnvelopeError(
                code=usage_error_code(exc),
                message=str(exc),
                details={"command_path": list(chain)},
            ),
        ),
    )


def help_envelope(app: App, tokens: list[str]) -> Envelope:
    """``ok: true`` envelope describing one command's invocation surface.

    Emitted for ``novetest <subcommand> --help`` in JSON modes. The
    top-level ``novetest --help`` is answered earlier by
    ``cli/entrypoint.py::_emit_help`` from the hand-maintained command
    surface; both carry ``command == "help"`` so an agent can switch on
    one field.
    """

    chain, target = _resolve_target(app, tokens)
    parameters = _parameters(target)
    subcommands = _subcommands(target)
    data: dict[str, Any] = {
        "schemaVersion": HELP_SCHEMA_VERSION,
        "commandPath": list(chain),
        "usage": _usage(chain, parameters, subcommands),
        "summary": _first_line(_help_text(target)),
        "description": _help_text(target),
        "parameters": parameters,
        "subcommands": subcommands,
    }
    return Envelope(command="help", ok=True, data=data)


# ---------------------------------------------------------------------------
# Internal helpers — Cyclopts introspection
# ---------------------------------------------------------------------------


def _command_chain(app: App, tokens: list[str]) -> tuple[str, ...]:
    """The resolved command tokens, or ``()`` when nothing resolves.

    Defensive: ``parse_commands`` walks the registration tree and cannot
    raise for our surface, but a usage-error envelope must never fail to
    be produced because introspection stumbled.
    """

    try:
        chain, _apps, _unused = app.parse_commands(tokens)
    except Exception:  # pragma: no cover - defensive
        return ()
    return tuple(chain)


def _resolve_target(app: App, tokens: list[str]) -> tuple[tuple[str, ...], App]:
    """``(command chain, the App the chain resolves to)``.

    The help / version flags are registered as real Cyclopts *commands*,
    so ``parse_commands(["run", "--help"])`` resolves to the ``--help``
    pseudo-app. Strip them first — we want the app the user asked ABOUT.
    """

    reserved = set(app.help_flags) | set(app.version_flags)
    described = [token for token in tokens if token not in reserved]
    try:
        chain, apps, _unused = app.parse_commands(described)
    except Exception:  # pragma: no cover - defensive
        return ((), app)
    target = apps[-1] if apps else app
    return (tuple(chain), target)


def _parameters(target: App) -> list[dict[str, Any]]:
    """Project the target command's parameters onto a stable wire shape.

    Order follows the command function's signature — deterministic. A
    pure command *group* (``novetest coverage``) has no default command
    and therefore no parameters of its own.
    """

    if target.default_command is None:
        return []
    try:
        collection = target.assemble_argument_collection(parse_docstring=True)
    except Exception:  # pragma: no cover - defensive
        return []
    parameters: list[dict[str, Any]] = []
    for argument in collection:
        if not argument.show:
            continue
        names = [str(name) for name in argument.names]
        if not names:
            continue
        parameters.append(
            {
                "name": names[0],
                "aliases": names[1:],
                "required": bool(argument.required),
                "type": _type_name(getattr(argument, "hint", None)),
                "summary": (argument.parameter.help or "").strip(),
            }
        )
    return parameters


def _subcommands(target: App) -> list[dict[str, str]]:
    """Registered sub-verbs, minus the help / version pseudo-commands."""

    reserved = set(target.help_flags) | set(target.version_flags)
    subcommands: list[dict[str, str]] = []
    for name in sorted(key for key in target if key not in reserved):
        sub = target[name]
        subcommands.append(
            {"name": name, "summary": _first_line(_help_text(sub))}
        )
    return subcommands


def _usage(
    chain: tuple[str, ...],
    parameters: list[dict[str, Any]],
    subcommands: list[dict[str, str]],
) -> str:
    """A literal, deterministic usage line built from what actually exists."""

    parts = ["novetest", *chain]
    if subcommands:
        parts.append("COMMAND")
    if parameters:
        parts.append("[OPTIONS]")
    return " ".join(parts)


def _help_text(target: object) -> str:
    value = getattr(target, "help", "")
    return value.strip() if isinstance(value, str) else ""


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _type_name(hint: object) -> str:
    if hint is None:
        return ""
    name = getattr(hint, "__name__", None)
    return name if isinstance(name, str) else str(hint)


__all__ = [
    "HELP_SCHEMA_VERSION",
    "USAGE_ERROR_FALLBACK_CODE",
    "classify_builtin_surface",
    "help_envelope",
    "usage_error_code",
    "usage_error_envelope",
]
