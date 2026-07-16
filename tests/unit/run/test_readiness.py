"""Unit tests for `novetest.run.readiness`.

Marker-detection tests moved to ``test_engine_selector.py`` when the
2026-07-03 pin-driven-dispatch slice consolidated detection into
`engine_selector`. This module covers `probe_engine` — pin-targeted
readiness of one named engine, the surviving public readiness surface
after W2/S12 removed the zero-caller first-candidate auto-scan.
Each per-engine probe (ready / engine-missing / engine-misconfigured) is
exercised through `probe_engine`, which drives the same `_probe_candidate`
internals the removed auto-scan did. The "no supported engine in the
workspace" case is covered via `detect_engine_candidates` returning an
empty candidate set — the signal orchestration's `novetest init` maps to
`no-engine-detected`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.run import readiness as readiness_module
from novetest.run.engine_selector import detect_engine_candidates
from novetest.run.errors import EngineNotSupportedError
from novetest.run.readiness import probe_engine


async def test_pytest_basic_is_ready(basic_workspace: Path) -> None:
    readiness = await probe_engine(basic_workspace, "python", "pytest")
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "pytest"
    assert readiness.engine_context.ecosystem == "python"


async def test_empty_no_engine_workspace_probes_missing(
    empty_workspace: Path,
) -> None:
    """The empty-no-engine fixture carries a bare ``pyproject.toml`` — a
    generic python marker that makes pytest the sole DETECTED candidate,
    but with no pytest actually configured/importable the pytest probe
    reports ``engine-missing`` (context None). This is the exact scenario
    the removed first-candidate auto-scan covered by probing candidate[0];
    it is preserved here by probing the detected pair directly."""

    assert [
        (c.ecosystem, c.engine_name) for c in detect_engine_candidates(empty_workspace)
    ] == [("python", "pytest")]

    readiness = await probe_engine(empty_workspace, "python", "pytest")
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None


async def test_truly_unknown_workspace_has_no_candidates(tmp_path: Path) -> None:
    """A bare directory with no markers at all → empty candidate set (the
    signal orchestration's `novetest init` maps to `no-engine-detected`)."""

    assert detect_engine_candidates(tmp_path) == ()


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

    readiness = await probe_engine(tmp_path, "javascript-typescript", "jest")
    assert readiness.state == "engine-missing"
    assert readiness.engine_context is None
    assert any("Node.js" in issue for issue in readiness.issues)


async def test_jest_workspace_with_node_but_no_jest_dep_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Node available, package.json present but jest not declared → misconfigured."""

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    _patch_node_on_path(monkeypatch, available=True)

    readiness = await probe_engine(tmp_path, "javascript-typescript", "jest")
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

    readiness = await probe_engine(tmp_path, "javascript-typescript", "jest")
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

    readiness = await probe_engine(tmp_path, "javascript-typescript", "jest")
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

    readiness = await probe_engine(tmp_path, "go", "go-test")
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

    readiness = await probe_engine(tmp_path, "go", "go-test")
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

    readiness = await probe_engine(tmp_path, "go", "go-test")
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

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
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

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
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

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
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

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert any("cargo --version" in issue for issue in readiness.issues)


# ---------------------------------------------------------------------------
# TOCTOU exec-failure degradation (RUN-26, W2/S15)
#
# `shutil.which` can pass and the binary then vanish / lose its exec bit
# before the probe's spawn — `run_subprocess` raises FileNotFoundError.
# Every probe must degrade to a readiness RESULT (the dotnet probe's
# pre-existing posture), never crash `probe_engine` with an uncaught
# exception.
# ---------------------------------------------------------------------------


def _patch_run_subprocess_raises(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    """Make every `readiness.run_subprocess` call raise ``exc`` (the
    TOCTOU shape: which() passed, exec failed)."""

    async def raising_run_subprocess(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> object:
        raise exc

    monkeypatch.setattr(
        readiness_module, "run_subprocess", raising_run_subprocess
    )


async def test_pytest_probe_exec_failure_degrades_to_misconfigured(
    basic_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both pytest probes raising FileNotFoundError → the version probe
    degrades to None and the plugin probe to False, so the workspace lands
    ``engine-misconfigured`` with both install-hint issues — no exception."""

    _patch_run_subprocess_raises(
        monkeypatch, FileNotFoundError(2, "No such file or directory")
    )

    readiness = await probe_engine(basic_workspace, "python", "pytest")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "pytest"
    assert any("pytest" in issue for issue in readiness.issues)


async def test_go_probe_exec_failure_degrades_to_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`go` resolvable on PATH but the `go version` spawn raises
    FileNotFoundError (TOCTOU) → ``engine-misconfigured``, not a crash."""

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    _patch_go_on_path(monkeypatch, available=True)
    _patch_run_subprocess_raises(
        monkeypatch, FileNotFoundError(2, "No such file or directory: 'go'")
    )

    readiness = await probe_engine(tmp_path, "go", "go-test")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "go-test"
    assert any("could not be executed" in issue for issue in readiness.issues)


async def test_cargo_nextest_probe_exec_failure_degrades_to_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cargo` resolvable but the `cargo nextest --version` spawn raises
    (TOCTOU / PermissionError shape) → ``engine-misconfigured``."""

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=True)
    _patch_run_subprocess_raises(
        monkeypatch, PermissionError(13, "Permission denied: 'cargo'")
    )

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert any("could not be executed" in issue for issue in readiness.issues)


async def test_cargo_version_probe_exec_failure_degrades_to_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The nextest probe succeeds but the follow-up `cargo --version`
    spawn raises (the binary vanished BETWEEN the two probes) →
    ``engine-misconfigured`` — covers the second cargo guard site."""

    from novetest.utils.asyncio_subprocess import SubprocessResult

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    _patch_cargo_on_path(monkeypatch, available=True)

    async def nextest_ok_then_raise(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 3 and argv[1] == "nextest":
            return SubprocessResult(
                returncode=0,
                stdout=b"cargo-nextest 0.9.70\n",
                stderr=b"",
                timed_out=False,
            )
        raise FileNotFoundError(2, "No such file or directory: 'cargo'")

    monkeypatch.setattr(readiness_module, "run_subprocess", nextest_ok_then_raise)

    readiness = await probe_engine(tmp_path, "rust", "cargo-test")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "cargo-test"
    assert any("cargo --version" in issue for issue in readiness.issues)


# ---------------------------------------------------------------------------
# Detection ↔ probe coherence (2026-07-03 pin-driven-dispatch slice)
#
# Detection order is the sole ordering SSoT (`engine_selector._ENGINE_MARKER_TABLE`),
# and pinned execution probes exactly the named pair via `probe_engine`, so
# readiness and dispatch structurally cannot disagree on a polyglot workspace
# (question 2026-07-02 §4.1). Pre-W2/S12 a first-candidate auto-scan probed the
# first candidate; that scan is gone, but the ordering guarantee it leaned on
# survives in `detect_engine_candidates`.
# ---------------------------------------------------------------------------


async def test_detection_and_probe_agree_on_pom_plus_gomod_workspace(
    tmp_path: Path,
) -> None:
    """The §4.1 mismatch workspace: detection ranks java/junit first (the
    pair a pin created from detection would dispatch), and probing THAT
    pair classifies it — never a go-test probe result.

    Pre-fix, readiness's hand-ordered chain probed go (rank 3) while the
    selector dispatched java — a `pom.xml`+`go.mod` workspace could have
    Go readiness-verified but JUnit dispatched. Now detection is the sole
    ordering SSoT and pinned execution probes exactly the named pair via
    `probe_engine`, so the two structurally cannot disagree. The bare
    pom.xml has no Jupiter (and the host may lack a JDK, Maven, or be
    Windows-OS-gated), so probing java/junit lands ``engine-misconfigured``
    with the junit context.
    """

    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")

    first = detect_engine_candidates(tmp_path)[0]
    assert (first.ecosystem, first.engine_name) == ("java", "junit")

    readiness = await probe_engine(tmp_path, "java", "junit")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    probed = (
        readiness.engine_context.ecosystem,
        readiness.engine_context.engine_name,
    )
    assert probed == (first.ecosystem, first.engine_name) == ("java", "junit")


# ---------------------------------------------------------------------------
# probe_engine — pin-targeted readiness (2026-07-03 pin-driven-dispatch)
#
# Serves the anchored-pin flows: init probing each candidate for the D1
# ready-candidate ambiguity gate, and pinned/overridden executions gating
# on exactly the named engine instead of scan-until-first-success.
# ---------------------------------------------------------------------------


async def test_probe_engine_tooling_only_package_json_is_candidate_but_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tooling-only ``package.json`` (no jest anywhere) marker-matches
    but does NOT probe ready — the distinction decision D1's ambiguity is
    defined over. `novetest init` must not count this workspace's jest
    candidate toward `engine-ambiguous`.
    """

    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"prettier": "^3.0.0"}}),
        encoding="utf-8",
    )
    _patch_node_on_path(monkeypatch, available=True)

    candidates = detect_engine_candidates(tmp_path)
    assert [(c.ecosystem, c.engine_name) for c in candidates] == [
        ("javascript-typescript", "jest")
    ]

    readiness = await probe_engine(tmp_path, "javascript-typescript", "jest")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "jest"


async def test_probe_engine_targets_named_engine_not_first_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`probe_engine` replaces scan-until-first-success for pinned flows:
    on a python+go workspace, probing the go pin must run the go probe —
    python (the higher-priority candidate a first-candidate auto-scan would
    take) is not consulted at all.
    """

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    _patch_go_on_path(monkeypatch, available=True)
    _patch_go_version_subprocess(monkeypatch)

    readiness = await probe_engine(tmp_path, "go", "go-test")
    assert readiness.state == "ready"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "go-test"
    assert readiness.engine_context.engine_version == "1.23.4"
    assert readiness.evidence == ("go.mod",)


async def test_probe_engine_vanished_marker_is_misconfigured_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pinned engine whose workspace marker is gone (stale pin, moved
    manifest) surfaces the probe's own TOCTOU diagnosis — evidence is
    empty but the probe still runs and classifies.
    """

    _patch_go_on_path(monkeypatch, available=True)

    readiness = await probe_engine(tmp_path, "go", "go-test")
    assert readiness.state == "engine-misconfigured"
    assert readiness.engine_context is not None
    assert readiness.engine_context.engine_name == "go-test"
    assert readiness.evidence == ()
    assert any("go.mod" in issue for issue in readiness.issues)


async def test_probe_engine_unsupported_pair_raises(tmp_path: Path) -> None:
    """Pairs outside the six-engine matrix raise — the CLI validates
    ``--engine`` upstream (D7 ``invalid-flag``), so this is the
    programming-error surface, not a readiness state.
    """

    with pytest.raises(EngineNotSupportedError):
        await probe_engine(tmp_path, "php", "phpunit")
