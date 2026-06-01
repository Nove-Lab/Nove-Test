"""Unit tests for the Phase 6 default-verb alias hook.

Brief §6: ``novetest <target>`` resolves to ``novetest test <target>``
when ``<target>`` is not in the reserved verb set
(``_SUBCOMMAND_TOKENS``). Bare ``novetest`` MUST NOT trigger any test
execution — that path is handled in ``main()`` (empty-args check) and
not exercised here.

The disambiguation rule (brief §6) — "if the first positional token is
in the reserved set, ALWAYS route to the verb handler" — is the
critical contract this hook enforces: a workspace with a directory
named ``inspect/`` cannot shadow ``novetest inspect <run_id>``.

Pure-function tests; no subprocess. Integration tests in
``tests/integration/cli/test_default_verb_alias.py`` cover the
subprocess-level activation surface.
"""

from __future__ import annotations

import pytest

from novetest.cli.app import _inject_default_verb_alias


class TestInjectDefaultVerbAlias:
    def test_empty_argv_leaves_unchanged(self) -> None:
        """Bare ``novetest`` — the empty case is handled in ``main()``."""

        assert _inject_default_verb_alias([]) == []

    def test_reserved_verb_left_alone(self) -> None:
        """``novetest run tests/`` keeps its explicit verb."""

        for verb in ("init", "test", "run", "memory", "inspect", "compare",
                     "status", "coverage", "regression", "localization", "replay"):
            argv = [verb, "tests/"]
            assert _inject_default_verb_alias(argv) == argv, verb

    def test_target_path_gets_alias(self) -> None:
        """``novetest tests/test_x.py`` → ``novetest test tests/test_x.py``."""

        result = _inject_default_verb_alias(["tests/test_x.py"])
        assert result == ["test", "tests/test_x.py"]

    def test_target_directory_gets_alias(self) -> None:
        result = _inject_default_verb_alias(["tests/"])
        assert result == ["test", "tests/"]

    def test_target_with_pytest_nodeid_gets_alias(self) -> None:
        result = _inject_default_verb_alias(["tests/test_x.py::test_y"])
        assert result == ["test", "tests/test_x.py::test_y"]

    def test_target_quoted_like_string_gets_alias(self) -> None:
        result = _inject_default_verb_alias(["my_module"])
        assert result == ["test", "my_module"]

    def test_target_with_glob_gets_alias(self) -> None:
        result = _inject_default_verb_alias(["tests/*.py"])
        assert result == ["test", "tests/*.py"]

    def test_disambiguation_directory_named_after_verb(self) -> None:
        """A workspace directory named ``inspect/`` cannot shadow the verb.

        Brief §6: the reserved set wins unconditionally. This is the
        load-bearing disambiguation invariant.
        """

        result = _inject_default_verb_alias(["inspect", "run_id_value"])
        # Routes to inspect, NOT to ``test inspect run_id_value``.
        assert result == ["inspect", "run_id_value"]

    def test_all_flags_no_alias(self) -> None:
        """If every token is a flag, no positional → no alias injection."""

        result = _inject_default_verb_alias(["--verbose"])
        assert result == ["--verbose"]

    def test_leading_flag_then_target_gets_alias(self) -> None:
        """Leading flags are preserved; first positional triggers alias.

        Cyclopts may consume top-level flags before the verb. The hook
        injects ``test`` BEFORE the first positional, preserving any
        leading flags Cyclopts will see at the top level.
        """

        result = _inject_default_verb_alias(["--verbose", "tests/"])
        assert result == ["test", "--verbose", "tests/"]

    def test_pure_function_does_not_mutate_input(self) -> None:
        """Defensive — the hook is pure; the caller's list survives intact."""

        original = ["tests/"]
        snapshot = list(original)
        _inject_default_verb_alias(original)
        assert original == snapshot
