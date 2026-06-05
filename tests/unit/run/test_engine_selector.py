"""Unit tests for `novetest.run.engine_selector`."""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.run.engine_selector import (
    list_supported_engine_pairs,
    select_native_engine,
)
from novetest.run.errors import EngineNotSupportedError
from novetest.run.types import TestTarget


def test_supported_pairs_cover_six_ecosystems() -> None:
    pairs = list_supported_engine_pairs()
    assert ("python", "pytest") in pairs
    assert ("javascript-typescript", "jest") in pairs
    assert ("java", "junit") in pairs
    assert ("go", "go-test") in pairs
    assert ("rust", "cargo-test") in pairs
    assert ("dotnet", "xunit") in pairs
    assert len(pairs) == 6


def test_python_workspace_selects_pytest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "python"
    assert context.engine_name == "pytest"


def test_unknown_workspace_raises(tmp_path: Path) -> None:
    target = TestTarget("", "workspace", tmp_path)
    with pytest.raises(EngineNotSupportedError):
        select_native_engine(target)


def test_js_workspace_selects_jest(tmp_path: Path) -> None:
    """Phase 2.5: jest is now an implemented adapter, so `package.json`
    workspaces resolve to the jest engine context rather than raising.
    """

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "javascript-typescript"
    assert context.engine_name == "jest"


def test_dotnet_workspace_selects_xunit(tmp_path: Path) -> None:
    """Phase 2.5 sixth-and-last slice: xunit is now an implemented adapter,
    so ``*.csproj`` workspaces resolve to the xunit engine context rather
    than raising. The glob-based detection branch (vs marker-file detection
    used by python/javascript/java/go/rust) is exercised here so the
    selector's two detection paths both have regression coverage.
    """

    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "dotnet"
    assert context.engine_name == "xunit"


def test_go_workspace_selects_gotest(tmp_path: Path) -> None:
    """Phase 3: go-test is now an implemented adapter, so `go.mod`
    workspaces resolve to the go-test engine context rather than raising.
    """

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "go"
    assert context.engine_name == "go-test"


def test_rust_workspace_selects_cargo_test(tmp_path: Path) -> None:
    """Phase 3 (adapter backlog #2): cargo-test is now an implemented
    adapter, so `Cargo.toml` workspaces resolve to the cargo-test engine
    context rather than raising.
    """

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "rust"
    assert context.engine_name == "cargo-test"
