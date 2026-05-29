from __future__ import annotations

import pytest


# Commands that remain as stubs at Phase 4 close. Phase 1: init / run / status /
# memory list / show / delete are real. Phase 2: coverage show / diff and
# inspect are real. Phase 3 (this slice): compare, regression compare,
# regression latest are real. Phase 4: localization <run_id> and
# localization latest are real. Only `replay` and `test` remain as stubs.
@pytest.mark.parametrize(
    "argv,expected_command",
    [
        (["replay"], "replay"),
    ],
)
def test_subcommand_stub_emits_not_implemented(run_cli, argv: list[str], expected_command: str) -> None:
    result = run_cli([*argv, "--output", "json"])
    assert result.returncode == 2, f"stderr={result.stderr!r}"
    envelope = result.envelope()
    assert envelope["command"] == expected_command
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "not-implemented"


def test_test_subcommand_help_exits_zero(run_cli) -> None:
    result = run_cli(["test", "--help"])
    assert result.returncode == 0, result.stderr


def test_test_subcommand_no_args_is_not_implemented(run_cli) -> None:
    result = run_cli(["test", "--output", "json"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "test"
    assert envelope["errors"][0]["code"] == "not-implemented"
