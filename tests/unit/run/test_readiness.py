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


# ---------------------------------------------------------------------------
# go-test readiness (Phase 3 adapter backlog #1)
#
# These tests stub `shutil.which` AND `run_subprocess` so the outcome is
# deterministic regardless of whether the host has Go installed. The
# `_assess_gotest_readiness` probe shells out to `go version` for its
# `ready` path; stubbing that returns the exact bytes the parser expects.
# ---------------------------------------------------------------------------


def _patch_go_on_path(
    monkeypatch: pytest.MonkeyPatch, *, available: bool
) -> None:
    def fake_which(binary: str) -> str | None:
        if available and binary == "go":
            return "/fake/bin/go"
        return None

    monkeypatch.setattr(readiness_module.shutil, "which", fake_which)


def _patch_go_version_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout_bytes: bytes = b"go version go1.23.4 linux/amd64\n",
    stderr_bytes: bytes = b"",
) -> None:
    """Stub `readiness.run_subprocess` so the `go version` probe is
    deterministic on hosts without Go."""

    from novetest.utils.asyncio_subprocess import SubprocessResult

    async def fake_run_subprocess(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        return SubprocessResult(
            returncode=returncode,
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            timed_out=False,
        )

    monkeypatch.setattr(readiness_module, "run_subprocess", fake_run_subprocess)


async def test_go_workspace_without_go_on_path_is_engine_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    _patch_go_on_path(monkeypatch, available=False)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None
    assert any("https://go.dev/dl/" in issue for issue in readiness.issues)


async def test_go_workspace_with_go_on_path_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`go.mod` present + `go` on PATH + `go version` succeeds → ready."""

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    _patch_go_on_path(monkeypatch, available=True)
    _patch_go_version_subprocess(monkeypatch)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "go-test"
    assert readiness.engine_context.ecosystem == "go"
    assert readiness.engine_context.engine_version == "1.23.4"


async def test_go_workspace_with_failing_go_version_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`go` on PATH but `go version` exits non-zero (broken GOROOT, etc.)
    → ``engine-misconfigured`` with engine_context populated so the CLI
    can name the engine in guidance.
    """

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    _patch_go_on_path(monkeypatch, available=True)
    _patch_go_version_subprocess(
        monkeypatch,
        returncode=1,
        stdout_bytes=b"",
        stderr_bytes=b"go: cannot find GOROOT\n",
    )

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "go-test"
    assert any("go version" in issue.lower() for issue in readiness.issues)


# ---------------------------------------------------------------------------
# cargo-test readiness (Phase 3 adapter backlog #2)
#
# Stubs `shutil.which` AND `run_subprocess` so the outcome is deterministic
# regardless of whether the host has Rust + nextest installed. Per the Q3
# decision the nextest gate is load-bearing — verified by the
# "engine-misconfigured" cases below.
# ---------------------------------------------------------------------------


def _patch_cargo_on_path(
    monkeypatch: pytest.MonkeyPatch, *, available: bool
) -> None:
    def fake_which(binary: str) -> str | None:
        if available and binary == "cargo":
            return "/fake/bin/cargo"
        return None

    monkeypatch.setattr(readiness_module.shutil, "which", fake_which)


def _patch_cargo_subprocesses(
    monkeypatch: pytest.MonkeyPatch,
    *,
    nextest_returncode: int = 0,
    nextest_stdout: bytes = b"cargo-nextest 0.9.70\n",
    nextest_stderr: bytes = b"",
    cargo_returncode: int = 0,
    cargo_stdout: bytes = b"cargo 1.74.0 (ecb9851af 2023-10-18)\n",
    cargo_stderr: bytes = b"",
) -> None:
    """Stub `readiness.run_subprocess` so cargo + nextest probes are
    deterministic on hosts without Rust.

    The stub distinguishes ``cargo nextest --version`` from
    ``cargo --version`` by argv length / second token.
    """

    from novetest.utils.asyncio_subprocess import SubprocessResult

    async def fake_run_subprocess(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 3 and argv[1] == "nextest":
            return SubprocessResult(
                returncode=nextest_returncode,
                stdout=nextest_stdout,
                stderr=nextest_stderr,
                timed_out=False,
            )
        return SubprocessResult(
            returncode=cargo_returncode,
            stdout=cargo_stdout,
            stderr=cargo_stderr,
            timed_out=False,
        )

    monkeypatch.setattr(readiness_module, "run_subprocess", fake_run_subprocess)


async def test_cargo_workspace_without_cargo_on_path_is_engine_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `cargo` on PATH → engine-missing with rustup install hint."""

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=False)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None
    assert any("https://rustup.rs" in issue for issue in readiness.issues)


async def test_cargo_workspace_without_nextest_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cargo` present but `cargo nextest --version` fails → misconfigured.

    Per the Q3 decision, nextest absence is surfaced loudly — there is
    no plain-text `cargo test` fallback. The install hint MUST mention
    `cargo install cargo-nextest --locked`.
    """

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=True)
    _patch_cargo_subprocesses(
        monkeypatch,
        nextest_returncode=101,
        nextest_stdout=b"",
        nextest_stderr=b"error: no such command: `nextest`\n",
    )

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert any(
        "cargo install cargo-nextest" in issue for issue in readiness.issues
    )


async def test_cargo_workspace_with_cargo_and_nextest_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Cargo.toml` + `cargo` + nextest probe succeeds → ready + version parsed."""

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=True)
    _patch_cargo_subprocesses(monkeypatch)

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert readiness.engine_context.ecosystem == "rust"
    assert readiness.engine_context.engine_version == "1.74.0"


async def test_cargo_workspace_with_failing_cargo_version_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cargo` on PATH and nextest probe OK but `cargo --version` fails →
    engine-misconfigured with engine_context populated.

    Mirrors the gotest "broken installation" branch — surfaces a clear
    rustup-side diagnosis rather than a generic readiness error.
    """

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=True)
    _patch_cargo_subprocesses(
        monkeypatch,
        cargo_returncode=1,
        cargo_stdout=b"",
        cargo_stderr=b"cargo: cannot find rustc\n",
    )

    readiness = await assess_engine_readiness(tmp_path)
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert any("cargo --version" in issue for issue in readiness.issues)
