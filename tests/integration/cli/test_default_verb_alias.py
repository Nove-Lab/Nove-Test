"""Subprocess E2E tests for the Phase 6 default-verb alias activation.

Brief §6 binding contracts:

- ``novetest <target>`` ≡ ``novetest test <target>`` when ``<target>``
  is not in the reserved verb set.
- Bare ``novetest`` (no args) → help envelope, exit 0, NO test execution.
- Reserved verbs (``run``, ``inspect``, ``status``, ``memory``, ...)
  ALWAYS win disambiguation even when a directory of the same name
  exists in the workspace.
- ``novetest run <target>`` (the explicit raw-evidence path) stays
  callable unchanged.

These pin the subprocess-level activation; pure-function tests for the
alias hook live in ``tests/unit/cli/test_default_verb_alias.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _materialize_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


def test_bare_novetest_emits_help_envelope_does_not_execute_tests(run_cli) -> None:
    """REQ-ORCH-006: bare ``novetest`` MUST emit help and exit 0.

    Even though ``novetest <target>`` ≡ ``novetest test <target>``, a
    bare ``novetest`` (no positional) MUST NOT silently invoke the
    integrated workflow with an empty target.
    """

    result = run_cli([])
    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "help"
    assert envelope["ok"] is True


def test_reserved_verb_is_routed_even_with_no_target(run_cli) -> None:
    """``novetest status`` routes to the status handler (uninitialized envelope).

    The disambiguation rule guarantees the reserved verb is always
    honored; in this isolated-cwd fixture the store is uninitialized,
    so the envelope reports ``code: "uninitialized"`` with exit 2.
    """

    result = run_cli(["status", "--output", "json"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "status"
    assert envelope["errors"][0]["code"] == "uninitialized"


def test_explicit_test_verb_in_uninitialized_dir_reports_uninitialized(run_cli) -> None:
    """``novetest test tests/`` in an uninitialized dir surfaces the uninit envelope.

    Confirms the integrated workflow handler IS wired (no longer a stub)
    and that its store-resolution path uses the standard helper.
    """

    result = run_cli(["test", "tests/", "--output", "json"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "test"
    assert envelope["errors"][0]["code"] == "uninitialized"


def test_default_verb_alias_routes_target_to_test(run_cli) -> None:
    """``novetest tests/`` aliases to ``novetest test tests/``.

    The handler invoked must be the ``test`` handler — confirmed by
    ``envelope.command == "test"``. The uninit envelope shape in the
    isolated cwd is the structural pin; the workflow execution is
    covered by ``tests/integration/orchestration/test_test_workflow.py``.
    """

    result = run_cli(["tests/", "--output", "json"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "test", (
        f"Expected alias to route to 'test' handler; envelope={envelope!r}"
    )
    assert envelope["errors"][0]["code"] == "uninitialized"


def test_explicit_run_verb_is_not_aliased(run_cli) -> None:
    """``novetest run <target>`` stays explicit; alias never fires."""

    result = run_cli(["run", "tests/", "--output", "json"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "run"


def test_alias_with_output_flag_before_target(run_cli) -> None:
    """``novetest --output json tests/`` aliases correctly.

    The ``_extract_output_flag`` extractor strips the flag before the
    alias hook runs; the alias then sees ``["tests/"]`` and prepends
    ``"test"``.
    """

    result = run_cli(["--output", "json", "tests/"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "test"
