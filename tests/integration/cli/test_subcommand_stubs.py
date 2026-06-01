from __future__ import annotations

import pytest


# Commands that remain as stubs after the Phase 6 entry slice. Phase 1:
# init / run / status / memory list / show / delete are real. Phase 2:
# coverage show / diff and inspect are real. Phase 3: compare, regression
# compare, regression latest are real. Phase 4: localization <run_id> and
# localization latest are real. Phase 6 entry (this slice): ``test`` is
# real. Only ``replay`` remains as a stub (Phase 5 dep).
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
    """``novetest test --help`` returns Cyclopts' verb help (exit 0).

    The integrated workflow is implemented by Phase 6 entry — its
    real-store behavior is covered by
    ``tests/integration/orchestration/test_test_workflow.py``; the
    default-verb alias activation is covered by
    ``tests/integration/cli/test_default_verb_alias.py``.
    """

    result = run_cli(["test", "--help"])
    assert result.returncode == 0, result.stderr
