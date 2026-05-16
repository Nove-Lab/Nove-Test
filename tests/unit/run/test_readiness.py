"""Unit tests for `novetest.run.readiness`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.run import readiness as readiness_module
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


async def test_truly_unknown_workspace_is_missing(tmp_path: Path) -> None:
    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None


# ---------------------------------------------------------------------------
# jest readiness (Phase 2.5)
#
# Every jest test monkeypatches ``shutil.which`` in the readiness module so
# the outcome is deterministic regardless of whether the host has Node.js
# installed. The CI matrix has no Node.js today; these tests are designed
# to be cell-agnostic.
# ---------------------------------------------------------------------------


def _patch_node_on_path(
    monkeypatch: pytest.MonkeyPatch, *, available: bool
) -> None:
    """Make `shutil.which("node"|"npx")` return a fake path or None.

    Patches the readiness module's `shutil.which` reference so other
    `shutil.which` callers in the same test process are unaffected.
    """

    def fake_which(binary: str) -> str | None:
        if available and binary in {"node", "npx"}:
            return f"/fake/bin/{binary}"
        return None

    monkeypatch.setattr(readiness_module.shutil, "which", fake_which)


async def test_jest_workspace_without_node_is_engine_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No node/npx on PATH → engine-missing.

    Replaces the old Phase-1-only test that asserted engine-misconfigured
    blindly. With jest's adapter shipping in Phase 2.5, the meaningful
    "missing" outcome is the host lacking Node.js entirely.
    """

    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"jest": "^29.7.0"}}),
        encoding="utf-8",
    )
    _patch_node_on_path(monkeypatch, available=False)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None
    assert any("Node.js" in issue for issue in readiness.issues)


async def test_jest_workspace_with_node_but_no_jest_dep_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Node available, package.json present but jest not declared → misconfigured."""

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    _patch_node_on_path(monkeypatch, available=True)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "jest"
    assert any("npm install --save-dev jest" in issue for issue in readiness.issues)


async def test_jest_workspace_declared_but_not_installed_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """jest in devDependencies but no node_modules/.bin/jest → misconfigured.

    Surfaces the "you forgot to run npm install" diagnosis distinctly from
    "you forgot to declare jest at all".
    """

    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"jest": "^29.7.0"}}),
        encoding="utf-8",
    )
    _patch_node_on_path(monkeypatch, available=True)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "jest"
    assert any("npm install" in issue for issue in readiness.issues)


async def test_jest_workspace_with_node_and_local_bin_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """jest declared + ``node_modules/.bin/jest`` present + node on PATH → ready."""

    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"jest": "^29.7.0"}}),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "jest").write_text("#!/usr/bin/env node\n", encoding="utf-8")
    # Populate the version metadata so the readiness probe captures it.
    jest_pkg_dir = tmp_path / "node_modules" / "jest"
    jest_pkg_dir.mkdir()
    (jest_pkg_dir / "package.json").write_text(
        json.dumps({"name": "jest", "version": "29.7.0"}),
        encoding="utf-8",
    )
    _patch_node_on_path(monkeypatch, available=True)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "jest"
    assert readiness.engine_context.ecosystem == "javascript-typescript"
    assert readiness.engine_context.engine_version == "29.7.0"
