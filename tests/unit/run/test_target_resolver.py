"""Unit tests for `novetest.run.target_resolver`."""

from __future__ import annotations

from pathlib import Path

from novetest.run.target_resolver import resolve_test_target


def test_empty_expression_yields_workspace(tmp_path: Path) -> None:
    target = resolve_test_target("", tmp_path)
    assert target.target_type == "workspace"
    assert target.target_expression == ""
    assert target.workspace_path == tmp_path


def test_whitespace_only_yields_workspace(tmp_path: Path) -> None:
    target = resolve_test_target("   ", tmp_path)
    assert target.target_type == "workspace"


def test_double_colon_yields_nodeid(tmp_path: Path) -> None:
    target = resolve_test_target("tests/test_x.py::test_y", tmp_path)
    assert target.target_type == "nodeid"
    assert target.target_expression == "tests/test_x.py::test_y"


def test_existing_directory_yields_directory(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    target = resolve_test_target("tests", tmp_path)
    assert target.target_type == "directory"


def test_non_directory_yields_file(tmp_path: Path) -> None:
    target = resolve_test_target("tests/test_x.py", tmp_path)
    assert target.target_type == "file"
