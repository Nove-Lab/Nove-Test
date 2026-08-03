"""Cyclopts command registration + the ``novetest`` process entrypoint.

Since the W3/S47 decomposition (ORC-01) this module is the thin transport
spine: it builds the Cyclopts ``app`` (+ the memory / coverage / regression /
localization sub-apps), registers each verb body from ``cli/handlers/*``, and
owns ``main`` (argv preprocessing lives in ``cli/entrypoint.py``; the shared
seams in ``cli/_shared.py``). No verb logic or envelope construction lives here
anymore — those moved verbatim into the per-verb handlers, so the wire contract
(envelopes, exit codes, per-command ``--help``, registration surface) is
byte-identical to the pre-S47 monolith.

Back-compat re-exports: the symbols other modules and tests import by name from
``novetest.cli.app`` (the seams, argv helpers, projectors, verb functions, and
the standalone builders) are re-bound below so ``from novetest.cli.app import
X`` and ``novetest.cli.app.X`` keep resolving. ``novetest.cli.app:main`` stays
the ``[project.scripts]`` / ``__main__`` entrypoint.
"""

from __future__ import annotations

import sys

from cyclopts import App
from cyclopts.exceptions import CycloptsError

from novetest import __version__

# --- Shared seams (re-exported for back-compat: tests import several by name) -
from novetest.cli._shared import (
    _adapter_to_envelope_warnings,
    _emit_and_exit,
    _engine_candidates_payload,
    _engine_not_ready_code,
    _lookup_miss_exit,
    _map_execution_exception,
    _readiness_payload,
    _require_store,
    _resolve_run_reference,
    _store_corrupt_envelope,
    _uninitialized,
    _validate_engine_flag,
    set_active_mode,
)

# --- Argv preprocessing group (re-exported: test_argv_helpers / _default_verb) -
from novetest.cli.entrypoint import (
    _emit_help,
    _emit_version,
    _extract_output_flag,
    _inject_default_verb_alias,
    _scan_top_level_intent,
)

# --- Verb handlers ---------------------------------------------------------
from novetest.cli.handlers.compare import compare_cmd
from novetest.cli.handlers.coverage import coverage_diff, coverage_show
from novetest.cli.handlers.inspect import inspect_cmd
from novetest.cli.handlers.licenses import licenses_cmd
from novetest.cli.handlers.localization import (
    _build_localization_cache_rederived_warning,
    _build_localization_formula_noop_warning,
    _build_localization_stale_build_rederived_warning,
    _localization_audit_warning,
    localization_latest,
    localization_run,
)
from novetest.cli.handlers.memory import memory_delete, memory_list, memory_show
from novetest.cli.handlers.onboarding import init, reset_cmd
from novetest.cli.handlers.regression import regression_compare, regression_latest
from novetest.cli.handlers.replay import _build_replay_envelope, replay_cmd
from novetest.cli.handlers.run import run_cmd
from novetest.cli.handlers.status import status
from novetest.cli.handlers.test import build_test_envelope, test_cmd
from novetest.cli.output import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    InvalidOutputModeError,
    OutputMode,
    apply_no_color,
    emit_envelope,
    fallback_output_mode,
    invalid_output_mode_envelope,
    resolve_output_mode,
)
from novetest.cli.usage import (
    classify_builtin_surface,
    help_envelope,
    usage_error_envelope,
)

# --- Engine outcome projectors (re-exported: test_projection asserts identity) -
from novetest.orchestration.projection import (
    coverage_delta_payload,
    coverage_outcome_payload,
    localization_outcome_payload,
    regression_outcome_payload,
    replay_outcome_payload,
)


# ---------------------------------------------------------------------------
# Cyclopts app + sub-app registration
# ---------------------------------------------------------------------------


app = App(
    name="novetest",
    version=__version__,
    help="Nove Test - AI-first testing orchestration.",
)

# Top-level onboarding + operating verbs.
app.command(init)
app.command(reset_cmd, name="reset")
app.command(run_cmd, name="run")
app.command(status)
app.command(licenses_cmd, name="licenses")
app.command(compare_cmd, name="compare")
app.command(inspect_cmd, name="inspect")
app.command(test_cmd, name="test")
app.command(replay_cmd, name="replay")

# Memory subcommand group.
memory_app = App(
    name="memory", help="Memory commands: list / show / delete run evidence."
)
app.command(memory_app)
memory_app.command(memory_list, name="list")
memory_app.command(memory_show, name="show")
memory_app.command(memory_delete, name="delete")

# Coverage subcommand group.
coverage_app = App(
    name="coverage",
    help="Coverage commands: show / diff Coverage Facts for stored runs.",
)
app.command(coverage_app)
coverage_app.command(coverage_show, name="show")
coverage_app.command(coverage_diff, name="diff")

# Regression subcommand group.
regression_app = App(
    name="regression",
    help="Regression commands: compare two runs / resolve the latest pair.",
)
app.command(regression_app)
regression_app.command(regression_compare, name="compare")
regression_app.command(regression_latest, name="latest")

# Localization subcommand group (runnable default + `latest`).
localization_app = App(
    name="localization",
    help="Localization commands: rank suspicious code locations (SBFL) for a run.",
)
app.command(localization_app)
localization_app.default(localization_run)
localization_app.command(localization_latest, name="latest")


# ---------------------------------------------------------------------------
# Process entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    explicit, args = _extract_output_flag(raw)
    try:
        mode = resolve_output_mode(explicit)
    except InvalidOutputModeError as exc:
        # Row 48: the mode that failed to resolve is the very thing that
        # would normally decide how to render this error, so fall back to
        # the no-value default (JSON off a tty, TEXT on one). This is the
        # ONLY pre-dispatch failure — it precedes verb parsing, the help /
        # version intents and the alias injection — so it gets its own
        # emit rather than routing through the machinery below, none of
        # which has run yet. EXIT_USAGE (2), the same bucket
        # ``_validate_engine_flag``'s ``invalid-flag`` uses: a bad value
        # for a known option is a usage problem, not a tool failure.
        mode = fallback_output_mode()
        apply_no_color(mode)
        emit_envelope(invalid_output_mode_envelope(exc), mode)
        sys.exit(EXIT_USAGE)
    apply_no_color(mode)
    set_active_mode(mode)

    intent = _scan_top_level_intent(args)
    if intent == "version":
        _emit_version(mode)
        sys.exit(EXIT_OK)
    if intent == "help":
        _emit_help(mode)
        sys.exit(EXIT_OK)

    # Bare ``novetest`` (no positional / no verb / no recognized flag) —
    # per Phase 6 brief §6 + REQ-ORCH-006, emit the help envelope and
    # exit 0. This MUST come before the alias injection: bare-novetest
    # must NOT silently become ``novetest test`` (which would try to
    # invoke the integrated workflow with an empty target).
    if not args:
        _emit_help(mode)
        sys.exit(EXIT_OK)

    # Default-verb alias: ``novetest <target>`` → ``novetest test <target>``
    # when ``<target>`` is not in the reserved verb set. Pure-function
    # transformation; the alias hook itself is testable in isolation
    # (see ``tests/unit/cli/test_default_verb_alias.py``).
    args = _inject_default_verb_alias(args)

    # Structured modes: keep the ``novetest/v1`` promise on the usage and
    # help surfaces too. Cyclopts otherwise answers both with Rich human
    # text no matter the output mode, which breaks an agent's JSON pipe
    # exactly where it hurts most — the error path (delivery-phasing row
    # 30 / wave-1 persona P2). Resolving the parse here does NOT dispatch:
    # the command still runs through the untouched ``app(args)`` call
    # below, so execution behaviour and exit codes are byte-identical.
    if mode in (OutputMode.JSON, OutputMode.NDJSON):
        builtin: str | None
        try:
            resolved, _bound, _ignored = app.parse_args(
                args, print_error=False, exit_on_error=False
            )
        except CycloptsError as exc:
            # Cyclopts exits 1 on these today; only the body changes.
            emit_envelope(usage_error_envelope(app, args, exc), mode)
            sys.exit(EXIT_GENERIC)
        except Exception:
            # NOT a usage error. Fall through to the normal dispatch so
            # the pre-parse can never change the outcome: ``app(args)``
            # re-raises it and the generic handler below emits the same
            # ``cli-error`` envelope it always did.
            builtin = None
        else:
            builtin = classify_builtin_surface(resolved)
        if builtin == "help":
            emit_envelope(help_envelope(app, args), mode)
            sys.exit(EXIT_OK)
        if builtin == "version":
            _emit_version(mode)
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


# Explicit re-export surface: the verb functions (needed for registration) plus
# the seams / builders / argv helpers / projectors that other modules and tests
# import by name, so ``from novetest.cli.app import X`` / ``novetest.cli.app.X``
# keep resolving after the S47 move. ``__all__`` also marks the re-exported
# imports for mypy's ``no_implicit_reexport`` check.
__all__ = [
    "app",
    "main",
    "memory_app",
    "coverage_app",
    "regression_app",
    "localization_app",
    # verbs
    "init",
    "reset_cmd",
    "run_cmd",
    "status",
    "licenses_cmd",
    "memory_list",
    "memory_show",
    "memory_delete",
    "coverage_show",
    "coverage_diff",
    "regression_compare",
    "regression_latest",
    "compare_cmd",
    "localization_run",
    "localization_latest",
    "inspect_cmd",
    "test_cmd",
    "replay_cmd",
    # seams / builders / helpers (re-exported)
    "_adapter_to_envelope_warnings",
    "_emit_and_exit",
    "_engine_candidates_payload",
    "_engine_not_ready_code",
    "_lookup_miss_exit",
    "_map_execution_exception",
    "_readiness_payload",
    "_require_store",
    "_resolve_run_reference",
    "_store_corrupt_envelope",
    "_uninitialized",
    "_validate_engine_flag",
    "set_active_mode",
    "_emit_help",
    "_emit_version",
    "_extract_output_flag",
    "_inject_default_verb_alias",
    "_scan_top_level_intent",
    "_build_replay_envelope",
    "build_test_envelope",
    "_build_localization_cache_rederived_warning",
    "_build_localization_formula_noop_warning",
    "_build_localization_stale_build_rederived_warning",
    "_localization_audit_warning",
    "coverage_delta_payload",
    "coverage_outcome_payload",
    "localization_outcome_payload",
    "regression_outcome_payload",
    "replay_outcome_payload",
]
