"""Wire tests: usage / help surfaces stay inside the ``novetest/v1`` envelope.

Delivery-phasing board row 30 (FC-3) — with ``NOVETEST_OUTPUT=json``
pinned once at session start (what the docs teach), these surfaces used to
answer with Rich box-drawn human text, so a scripted consumer's
``| python -m json.tool`` pipe died with
``JSONDecodeError: Expecting value: line 1 column 1`` and the agent had to
re-run blind to learn what went wrong (wave-1 persona P2, 2026-07-28).

One test per surface named in the board row, asserted on the REAL
subprocess bytes:

- ``novetest run --help``
- ``novetest coverage show --run <id>``   (unknown option)
- ``novetest coverage show``              (missing required flag)
- ``novetest inspect``                    (missing required flag)

Exit codes are pinned to what each surface returned BEFORE this change —
only the body moved into the envelope.
"""

from __future__ import annotations

import json
from typing import Any

JSON_ENV = {"NOVETEST_OUTPUT": "json"}

# Glyphs that only appear in Cyclopts' Rich rendering. Their absence is
# the negative half of the contract.
_RICH_MARKERS = ("╭", "╰", "│", "\x1b[")


def _envelope(stdout: str) -> dict[str, Any]:
    """Parse stdout the way an agent's ``json.tool`` pipe would."""
    payload = json.loads(stdout)
    assert isinstance(payload, dict)
    assert payload["schema"] == "novetest/v1"
    return payload


def _assert_no_rich_text(text: str) -> None:
    for marker in _RICH_MARKERS:
        assert marker not in text, f"Rich rendering leaked: {marker!r} in {text[:200]!r}"


class TestUsageErrorsAreEnvelopes:
    def test_unknown_option_emits_ok_false_envelope(self, run_cli: Any) -> None:
        result = run_cli(
            ["coverage", "show", "--run", "01ABC"], env_overrides=JSON_ENV
        )
        # Exit code unchanged (Cyclopts returned 1 for this before).
        assert result.returncode == 1
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["command"] == "coverage.show"
        assert payload["data"] == {}
        errors = payload["errors"]
        assert len(errors) == 1
        assert errors[0]["code"] == "unknown-option"
        assert "--run" in errors[0]["message"]
        assert errors[0]["details"]["command_path"] == ["coverage", "show"]
        _assert_no_rich_text(result.stdout)

    def test_missing_required_flag_on_coverage_show(self, run_cli: Any) -> None:
        result = run_cli(["coverage", "show"], env_overrides=JSON_ENV)
        assert result.returncode == 1
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["command"] == "coverage.show"
        assert payload["errors"][0]["code"] == "missing-argument"
        assert "--run-id" in payload["errors"][0]["message"]
        _assert_no_rich_text(result.stdout)

    def test_missing_required_flag_on_inspect(self, run_cli: Any) -> None:
        result = run_cli(["inspect"], env_overrides=JSON_ENV)
        assert result.returncode == 1
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["command"] == "inspect"
        assert payload["errors"][0]["code"] == "missing-argument"
        assert "--run-id" in payload["errors"][0]["message"]
        _assert_no_rich_text(result.stdout)

    def test_unknown_subcommand_emits_envelope(self, run_cli: Any) -> None:
        result = run_cli(["memory", "bogus"], env_overrides=JSON_ENV)
        assert result.returncode == 1
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["errors"][0]["code"] == "unknown-command"

    def test_ndjson_mode_emits_one_json_line(self, run_cli: Any) -> None:
        result = run_cli(
            ["coverage", "show"], env_overrides={"NOVETEST_OUTPUT": "ndjson"}
        )
        assert result.returncode == 1
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["schema"] == "novetest/v1"
        assert payload["errors"][0]["code"] == "missing-argument"


class TestSubcommandHelpIsAnEnvelope:
    def test_run_help_emits_help_envelope(self, run_cli: Any) -> None:
        result = run_cli(["run", "--help"], env_overrides=JSON_ENV)
        # Exit code unchanged: help has always exited 0.
        assert result.returncode == 0
        payload = _envelope(result.stdout)
        assert payload["ok"] is True
        assert payload["command"] == "help"
        assert payload["errors"] == []
        data = payload["data"]
        assert data["schemaVersion"] == 1
        assert data["commandPath"] == ["run"]
        assert data["usage"].startswith("novetest run")
        assert data["summary"]
        parameter_names = {p["name"] for p in data["parameters"]}
        assert "--coverage" in parameter_names
        assert "--engine" in parameter_names
        _assert_no_rich_text(result.stdout)

    def test_help_marks_required_parameters(self, run_cli: Any) -> None:
        # The required-flag information P2 could only discover by
        # triggering the error is now on the help surface itself.
        result = run_cli(["coverage", "show", "--help"], env_overrides=JSON_ENV)
        assert result.returncode == 0
        data = _envelope(result.stdout)["data"]
        required = {p["name"] for p in data["parameters"] if p["required"]}
        assert required == {"--run-id"}

    def test_group_help_lists_subcommands(self, run_cli: Any) -> None:
        result = run_cli(["coverage", "--help"], env_overrides=JSON_ENV)
        assert result.returncode == 0
        data = _envelope(result.stdout)["data"]
        assert data["commandPath"] == ["coverage"]
        assert {s["name"] for s in data["subcommands"]} == {"show", "diff"}

    def test_subcommand_version_flag_emits_identity_envelope(
        self, run_cli: Any
    ) -> None:
        # ``--version`` is the sibling Cyclopts built-in and printed raw
        # human text on the same code path.
        result = run_cli(["run", "--version"], env_overrides=JSON_ENV)
        assert result.returncode == 0
        payload = _envelope(result.stdout)
        assert payload["command"] == "version"
        assert payload["data"]["installedVersion"]


class TestTextModeUnchanged:
    """The human surface keeps Cyclopts' Rich rendering, verbatim."""

    def test_usage_error_still_renders_human_text(self, run_cli: Any) -> None:
        result = run_cli(
            ["coverage", "show"], env_overrides={"NOVETEST_OUTPUT": "text"}
        )
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "--run-id" in combined
        # Not an envelope: the human path never emitted one here.
        assert "novetest/v1" not in combined

    def test_help_still_renders_human_text(self, run_cli: Any) -> None:
        result = run_cli(["run", "--help"], env_overrides={"NOVETEST_OUTPUT": "text"})
        assert result.returncode == 0
        assert "novetest/v1" not in result.stdout
        assert "Usage" in result.stdout


class TestNormalDispatchUnaffected:
    """The structured pre-parse must not double-run or swallow a verb."""

    def test_valid_verb_still_executes_once(self, run_cli: Any) -> None:
        # ``status`` in an uninitialized workspace is a known envelope:
        # one emission, the pre-existing uninitialized error contract.
        result = run_cli(["status"], env_overrides=JSON_ENV)
        payload = _envelope(result.stdout)
        assert payload["command"] == "status"
        assert payload["errors"][0]["code"] == "uninitialized"
        assert result.returncode == 2
        # Exactly one envelope on stdout (a double dispatch would emit two).
        assert result.stdout.count('"schema"') == 1
