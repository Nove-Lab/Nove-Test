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


def test_dotnet_workspace_raises_until_adapter_lands(tmp_path: Path) -> None:
    """junit / go-test / cargo-test / xunit have no adapters yet — they must
    still raise `EngineNotSupportedError`. xunit is chosen as the
    representative because .NET uses a glob-based detection path that
    exercises a different branch of `_ecosystem_for_workspace`.
    """

    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    with pytest.raises(EngineNotSupportedError):
        select_native_engine(target)
