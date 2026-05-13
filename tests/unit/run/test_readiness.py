"""Unit tests for `novetest.run.readiness`."""

from __future__ import annotations

from pathlib import Path

from novetest.run.readiness import (
    assess_engine_readiness,
    detect_engine_candidates,
)


def test_detect_python_candidate_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("python", "pytest") in pairs


def test_detect_js_candidate_from_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("javascript-typescript", "jest") in pairs


def test_detect_dotnet_via_csproj_glob(tmp_path: Path) -> None:
    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("dotnet", "xunit") in pairs


def test_detect_multiple_candidates_for_polyglot(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    pairs = {(c.ecosystem, c.engine_name) for c in detect_engine_candidates(tmp_path)}
    assert {"python", "javascript-typescript", "go"}.issubset({eco for eco, _ in pairs})


def test_detect_empty_workspace_returns_empty(tmp_path: Path) -> None:
    assert detect_engine_candidates(tmp_path) == ()


async def test_pytest_basic_is_ready(basic_workspace: Path) -> None:
    readiness = await assess_engine_readiness(basic_workspace)
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "pytest"
    assert readiness.engine_context.ecosystem == "python"


async def test_empty_no_engine_is_missing(empty_workspace: Path) -> None:
    readiness = await assess_engine_readiness(empty_workspace)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None


async def test_jest_only_workspace_is_misconfigured_in_phase1(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "jest"


async def test_truly_unknown_workspace_is_missing(tmp_path: Path) -> None:
    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None
