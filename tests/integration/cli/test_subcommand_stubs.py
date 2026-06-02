from __future__ import annotations


# After the Phase 5 entry slice (``replay`` promoted to a real verb), NO
# top-level subcommand remains a stub. Phase 1: init / run / status / memory
# list / show / delete. Phase 2: coverage show / diff and inspect. Phase 3:
# compare, regression compare, regression latest. Phase 4: localization
# <run_id> and localization latest. Phase 6 entry: ``test``. Phase 5 entry
# (this slice): ``replay``. The previous parametrized "emits not-implemented"
# stub test is therefore removed — there is nothing left to assert as a stub.


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
