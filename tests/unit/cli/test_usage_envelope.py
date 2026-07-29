"""Unit tests for ``cli/usage.py`` — the structured usage / help projection.

Pure functions over ``(app, tokens)``; no subprocess. The wire-level
pins (real bytes, real exit codes) live in
``tests/integration/cli/test_usage_error_envelope.py``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from cyclopts import App
from cyclopts.exceptions import CycloptsError

from novetest.cli.app import app, main
from novetest.cli.usage import (
    HELP_SCHEMA_VERSION,
    USAGE_ERROR_FALLBACK_CODE,
    classify_builtin_surface,
    help_envelope,
    usage_error_code,
    usage_error_envelope,
)


def _parse_failure(tokens: list[str]) -> CycloptsError:
    """The REAL Cyclopts exception for ``tokens`` (not a hand-built stub)."""
    with pytest.raises(CycloptsError) as excinfo:
        app.parse_args(tokens, print_error=False, exit_on_error=False)
    return excinfo.value


class TestUsageErrorCode:
    @pytest.mark.parametrize(
        ("tokens", "expected"),
        [
            (["coverage", "show", "--run", "x"], "unknown-option"),
            (["coverage", "show"], "missing-argument"),
            (["inspect"], "missing-argument"),
            (["memory", "bogus"], "unknown-command"),
        ],
    )
    def test_known_failures_map_to_closed_tokens(
        self, tokens: list[str], expected: str
    ) -> None:
        assert usage_error_code(_parse_failure(tokens)) == expected

    def test_unlisted_cyclopts_error_falls_back(self) -> None:
        assert usage_error_code(CycloptsError(msg="x")) == USAGE_ERROR_FALLBACK_CODE


class TestUsageErrorEnvelope:
    def test_envelope_shape(self) -> None:
        tokens = ["coverage", "show"]
        envelope = usage_error_envelope(app, tokens, _parse_failure(tokens))
        payload = envelope.to_dict()
        assert payload["schema"] == "novetest/v1"
        assert payload["ok"] is False
        # Dotted sub-verb naming, matching the handlers' own convention
        # (``coverage.show`` / ``regression.compare``).
        assert payload["command"] == "coverage.show"
        assert payload["data"] == {}
        assert payload["warnings"] == []
        assert len(payload["errors"]) == 1
        error = payload["errors"][0]
        assert error["code"] == "missing-argument"
        assert error["message"]
        assert error["details"] == {"command_path": ["coverage", "show"]}

    def test_unresolvable_command_falls_back_to_cli(self) -> None:
        # ``--nope`` resolves to no command chain at all.
        tokens = ["--nope"]
        with pytest.raises(CycloptsError) as excinfo:
            app.parse_args(tokens, print_error=False, exit_on_error=False)
        envelope = usage_error_envelope(app, tokens, excinfo.value)
        assert envelope.command == "cli"
        assert envelope.errors[0].details == {"command_path": []}

    def test_message_is_cyclopts_own_sentence(self) -> None:
        tokens = ["coverage", "show", "--run", "x"]
        exc = _parse_failure(tokens)
        envelope = usage_error_envelope(app, tokens, exc)
        assert envelope.errors[0].message == str(exc)

    def test_is_deterministic(self) -> None:
        tokens = ["coverage", "show"]
        first = usage_error_envelope(app, tokens, _parse_failure(tokens)).to_dict()
        second = usage_error_envelope(app, tokens, _parse_failure(tokens)).to_dict()
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestHelpEnvelope:
    def test_leaf_command_help(self) -> None:
        envelope = help_envelope(app, ["coverage", "show", "--help"])
        payload = envelope.to_dict()
        assert payload["command"] == "help"
        assert payload["ok"] is True
        data = payload["data"]
        assert data["schemaVersion"] == HELP_SCHEMA_VERSION
        # The help FLAG must not leak into the resolved command path.
        assert data["commandPath"] == ["coverage", "show"]
        assert data["usage"] == "novetest coverage show [OPTIONS]"
        assert data["subcommands"] == []
        assert data["parameters"] == [
            {
                "name": "--run-id",
                "aliases": [],
                "required": True,
                "type": "str",
                "summary": "",
            }
        ]

    def test_command_group_help_lists_subcommands(self) -> None:
        data = help_envelope(app, ["memory", "-h"]).data
        assert data["commandPath"] == ["memory"]
        assert data["parameters"] == []
        assert [s["name"] for s in data["subcommands"]] == ["delete", "list", "show"]
        assert data["usage"] == "novetest memory COMMAND"

    def test_aliases_and_types_are_projected(self) -> None:
        data = help_envelope(app, ["run", "--help"]).data
        by_name: dict[str, Any] = {p["name"]: p for p in data["parameters"]}
        assert by_name["--coverage"]["aliases"] == ["-c", "--no-coverage"]
        assert by_name["--coverage"]["type"] == "bool"
        assert by_name["--coverage"]["required"] is False

    def test_summary_is_the_first_line_of_the_description(self) -> None:
        data = help_envelope(app, ["run", "--help"]).data
        assert data["description"].startswith(data["summary"])
        assert "\n" not in data["summary"]

    def test_is_deterministic(self) -> None:
        first = help_envelope(app, ["run", "--help"]).to_dict()
        second = help_envelope(app, ["run", "--help"]).to_dict()
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestClassifyBuiltinSurface:
    def test_help_flag_resolves_to_help(self) -> None:
        resolved, _bound, _ignored = app.parse_args(
            ["run", "--help"], print_error=False, exit_on_error=False
        )
        assert classify_builtin_surface(resolved) == "help"

    def test_version_flag_resolves_to_version(self) -> None:
        resolved, _bound, _ignored = app.parse_args(
            ["run", "--version"], print_error=False, exit_on_error=False
        )
        assert classify_builtin_surface(resolved) == "version"

    def test_regular_verb_is_not_a_builtin(self) -> None:
        resolved, _bound, _ignored = app.parse_args(
            ["status"], print_error=False, exit_on_error=False
        )
        assert classify_builtin_surface(resolved) is None

    def test_plain_callable_is_not_a_builtin(self) -> None:
        assert classify_builtin_surface(lambda: None) is None

    def test_help_print_of_any_app_is_recognized(self) -> None:
        # The check is on the underlying function, so it holds for a
        # sub-app's bound method too.
        other = App(name="other")
        assert classify_builtin_surface(other.help_print) == "help"


class TestPreParseNeverChangesNonUsageOutcomes:
    """The structured pre-parse is additive: it may only answer usage/help.

    Anything else it stumbles on must fall through to the normal dispatch
    so the pre-existing ``cli-error`` envelope still reaches the agent.
    """

    def test_non_cyclopts_parse_failure_still_yields_cli_error_envelope(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(App, "parse_args", boom)
        monkeypatch.setenv("NOVETEST_OUTPUT", "json")
        with pytest.raises(SystemExit) as excinfo:
            main(["status"])
        assert excinfo.value.code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "novetest/v1"
        assert payload["ok"] is False
        assert payload["command"] == "cli"
        assert payload["errors"][0]["code"] == "cli-error"
        assert "kaboom" in payload["errors"][0]["message"]
