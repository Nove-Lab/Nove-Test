"""Engine readiness assessment for a Project Workspace.

Workflow per `design/interace-contract/run.md` §1 + `design/workflows/run.md`:
1. `engine_selector.detect_engine_candidates` scans workspace markers and
   returns the inferred (ecosystem, engine) candidates in canonical
   priority order — the single marker/priority table in `engine_selector`
   is the only ordering authority (decision
   `2026-07-03-engine-selection-policy.md` §"Kills the two-priority-lists
   latent bug by design").
2. `assess_engine_readiness` probes the FIRST candidate — by construction
   the same engine `select_native_engine` would dispatch.
   `probe_engine` probes ONE explicitly named engine instead (the store
   pin, a transient ``--engine`` override, or init's per-candidate
   readiness pass). Per-engine, the probe does a deeper check:
   - pytest: pytest config present + pytest + pytest-json-report importable
     from the resolved interpreter.
   - jest: ``node`` on PATH + jest declared in ``package.json``
     ``dependencies`` / ``devDependencies`` or installed under
     ``node_modules/.bin/jest``.
   - go-test: ``go`` on PATH + ``go version`` succeeds + ``go.mod`` in
     the workspace (the marker detection already confirmed this; we
     re-check defensively to close a TOCTOU window).
   - cargo-test: ``cargo`` on PATH + ``cargo nextest --version`` succeeds
     + ``cargo --version`` succeeds + ``Cargo.toml`` in the workspace.
     The nextest gate is **load-bearing**: per
     `decisions/2026-05-29-cargo-adapter-nextest-primary.md`, there is
     no plain-text ``cargo test`` fallback, so absence of
     ``cargo-nextest`` is surfaced as ``engine-misconfigured`` with an
     install hint.

All surfaces are pure inspection. **Nothing is ever installed.**
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from novetest.run.adapters.dotnet_adapter import _detect_test_project
from novetest.run.adapters.junit_adapter import (
    _detect_build_tool,
    _detects_junit4_in_manifest,
    _detects_jupiter_in_manifest,
    _detects_testng_in_manifest,
)
from novetest.run.engine_selector import (
    detect_engine_candidates,
    list_supported_engine_pairs,
)
from novetest.run.errors import EngineNotSupportedError
from novetest.run.types import (
    EngineCandidate,
    EngineReadinessResult,
    NativeEngineContext,
)
from novetest.utils.asyncio_subprocess import run_subprocess


async def assess_engine_readiness(project_workspace: Path) -> EngineReadinessResult:
    """Decide whether ``project_workspace`` is ready for a Native Engine run.

    Returns one of three states:
    - ``ready``: a supported engine adapter applies and its tooling resolves.
    - ``engine-missing``: no supported engine adapter applies (or the only
      adapter that applies has no actual engine configuration in the
      workspace — e.g. a Python project without a pytest setup).
    - ``engine-misconfigured``: a supported engine applies but its required
      tooling is unavailable (e.g. pytest not importable from the resolved
      interpreter, ``pytest-json-report`` plugin missing).

    Polyglot disambiguation: the first candidate in canonical table order
    wins — derived from, not parallel to, `select_native_engine`'s
    selection, so readiness and dispatch cannot disagree.
    """

    candidates = detect_engine_candidates(project_workspace)
    if not candidates:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=(),
            issues=("no supported (ecosystem, native engine) pair detected in workspace",),
        )
    return await _probe_candidate(project_workspace, candidates[0])


async def probe_engine(
    project_workspace: Path, ecosystem: str, engine_name: str
) -> EngineReadinessResult:
    """Readiness of ONE specific engine for ``project_workspace``.

    Serves the anchored-pin flows (decision
    `2026-07-03-engine-selection-policy.md`): `novetest init` probes each
    detected candidate to compute D1's ambiguity over READY candidates,
    and pinned / ``--engine``-overridden executions gate on exactly the
    named engine instead of scan-until-first-success. Marker evidence for
    the pair is re-resolved here (may legitimately be empty — the
    per-engine probes carry their own TOCTOU re-checks).

    Raises `EngineNotSupportedError` for pairs outside the supported
    matrix — the CLI validates ``--engine`` upstream (D7 ``invalid-flag``),
    so reaching the raise is a programming error, not a user-input path.
    """

    if (ecosystem, engine_name) not in list_supported_engine_pairs():
        raise EngineNotSupportedError(
            f"({ecosystem!r}, {engine_name!r}) is not a supported "
            "(ecosystem, engine) pair"
        )
    candidates = detect_engine_candidates(project_workspace)
    candidate = next(
        (
            c
            for c in candidates
            if c.ecosystem == ecosystem and c.engine_name == engine_name
        ),
        EngineCandidate(ecosystem=ecosystem, engine_name=engine_name, evidence=()),
    )
    return await _probe_candidate(project_workspace, candidate)


async def _probe_candidate(
    project_workspace: Path, candidate: EngineCandidate
) -> EngineReadinessResult:
    """Dispatch ``candidate`` to its per-engine readiness probe."""

    probe = _READINESS_PROBES.get((candidate.ecosystem, candidate.engine_name))
    if probe is None:
        # The supported table grew without a matching readiness probe
        # being wired up. Surface as misconfigured so the CLI can name
        # the ecosystem without pretending it is ready. The divergence
        # guard in tests/unit/run/test_engine_selector.py keeps this
        # branch unreachable for shipping engines.
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem=candidate.ecosystem, engine_name=candidate.engine_name
            ),
            evidence=candidate.evidence,
            issues=(f"adapter for {candidate.engine_name!r} not implemented yet",),
        )
    return await probe(project_workspace, candidate)


async def _assess_pytest_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    if not _pytest_configured(project_workspace):
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=candidate.evidence,
            issues=(
                "Python workspace detected but no pytest configuration "
                "(pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found",
            ),
        )

    issues: list[str] = []
    pytest_version = await _probe_pytest_version(project_workspace)
    if pytest_version is None:
        issues.append(
            "pytest is not importable from the resolved interpreter; "
            "install with: pip install pytest"
        )
    if not await _probe_pytest_jsonreport(project_workspace):
        issues.append(
            "pytest-json-report plugin is not importable; "
            "install with: pip install pytest-json-report"
        )

    context = NativeEngineContext(
        ecosystem="python",
        engine_name="pytest",
        engine_version=pytest_version,
    )
    if issues:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=context,
            evidence=candidate.evidence,
            issues=tuple(issues),
        )
    return EngineReadinessResult(
        state="ready",
        engine_context=context,
        evidence=candidate.evidence,
        issues=(),
    )


def _pytest_configured(workspace: Path) -> bool:
    """Cheaper-than-import probe for "this workspace uses pytest"."""

    if (workspace / "pytest.ini").exists():
        return True
    if (workspace / "conftest.py").exists():
        return True
    if (workspace / "tests").is_dir():
        return True
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
        except OSError:
            return False
        if "[tool.pytest.ini_options]" in content:
            return True
    setup_cfg = workspace / "setup.cfg"
    if setup_cfg.exists():
        try:
            content = setup_cfg.read_text(encoding="utf-8")
        except OSError:
            return False
        if "[tool:pytest]" in content:
            return True
    return False


async def _probe_pytest_version(workspace: Path) -> str | None:
    result = await run_subprocess(
        [sys.executable, "-c", "import pytest; print(pytest.__version__)"],
        cwd=workspace,
        timeout=15.0,
    )
    if result.returncode != 0:
        return None
    version = result.stdout.decode("utf-8", errors="replace").strip()
    return version or None


async def _probe_pytest_jsonreport(workspace: Path) -> bool:
    result = await run_subprocess(
        [sys.executable, "-c", "import pytest_jsonreport"],
        cwd=workspace,
        timeout=15.0,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# jest readiness (Phase 2.5)
# ---------------------------------------------------------------------------


async def _assess_jest_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    """Decide jest's readiness state for a JS/TS workspace.

    Sequence:
    1. ``node`` (and ``npx``) on PATH? If absent → ``engine-missing``
       (engine cannot run at all; engine_context dropped so the caller does
       not name jest in the guidance — there is no jest yet).
    2. Jest declared in ``package.json`` deps OR installed under
       ``node_modules/.bin/jest``? If absent → ``engine-misconfigured``
       with engine_context populated (we know it's jest the user wants).
    3. Best-effort version read from
       ``node_modules/jest/package.json`` — informational; never fails the
       state.
    """

    if shutil.which("node") is None or shutil.which("npx") is None:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=candidate.evidence,
            issues=(
                "Node.js (`node`/`npx`) not found on PATH; install Node.js "
                ">=18 and ensure both `node` and `npx` are on PATH",
            ),
        )

    jest_declared = _jest_declared_in_package_json(project_workspace)
    jest_installed = (
        project_workspace / "node_modules" / ".bin" / "jest"
    ).exists() or (
        project_workspace / "node_modules" / ".bin" / "jest.cmd"
    ).exists()

    if not jest_declared and not jest_installed:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="javascript-typescript", engine_name="jest"
            ),
            evidence=candidate.evidence,
            issues=(
                "jest not found in package.json `dependencies`/`devDependencies` "
                "and not installed under `node_modules/.bin/jest`; install with: "
                "npm install --save-dev jest",
            ),
        )
    if not jest_installed:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="javascript-typescript", engine_name="jest"
            ),
            evidence=candidate.evidence,
            issues=(
                "jest is declared in package.json but not installed; run: "
                "npm install",
            ),
        )

    engine_version = _read_jest_version_from_workspace(project_workspace)
    return EngineReadinessResult(
        state="ready",
        engine_context=NativeEngineContext(
            ecosystem="javascript-typescript",
            engine_name="jest",
            engine_version=engine_version,
        ),
        evidence=candidate.evidence,
        issues=(),
    )


def _jest_declared_in_package_json(workspace: Path) -> bool:
    """Cheap text-then-parse probe for "jest in {dev,}Dependencies"."""

    package_json = workspace / "package.json"
    if not package_json.is_file():
        return False
    try:
        content = package_json.read_text(encoding="utf-8")
    except OSError:
        return False
    # Fast-path: if the literal "jest" substring is absent, save the JSON parse.
    if "jest" not in content:
        return False
    try:
        meta = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(meta, dict):
        return False
    for section_key in ("dependencies", "devDependencies"):
        section = meta.get(section_key)
        if isinstance(section, dict) and "jest" in section:
            return True
    return False


def _read_jest_version_from_workspace(workspace: Path) -> str | None:
    """Read ``node_modules/jest/package.json``'s ``version`` field, or None."""

    candidate = workspace / "node_modules" / "jest" / "package.json"
    if not candidate.is_file():
        return None
    try:
        meta = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = meta.get("version") if isinstance(meta, dict) else None
    return str(version) if isinstance(version, str) else None


# ---------------------------------------------------------------------------
# go-test readiness (Phase 3 adapter backlog #1)
# ---------------------------------------------------------------------------


async def _assess_gotest_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    """Decide ``go test``'s readiness state for a Go module workspace.

    Sequence:
    1. ``go`` on PATH? If absent → ``engine-missing``.
    2. ``go.mod`` still present? Already confirmed by candidate detection
       but re-checked to close a TOCTOU window.
    3. ``go version`` succeeds? If non-zero exit → ``engine-misconfigured``
       (broken installation — rare but observable when GOROOT is wrong).
    4. Best-effort version extraction from ``go version``'s output — same
       parser as the adapter's ``_read_go_version``; informational only.
    """

    if shutil.which("go") is None:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=candidate.evidence,
            issues=(
                "`go` not found on PATH; install Go 1.21+ from "
                "https://go.dev/dl/",
            ),
        )

    # Defensive go.mod re-check. `detect_engine_candidates` already saw it
    # but the workspace state can shift between that scan and now.
    if not (project_workspace / "go.mod").is_file():
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="go", engine_name="go-test"
            ),
            evidence=candidate.evidence,
            issues=(
                "Go workspace marker `go.mod` is no longer present at the "
                "workspace root",
            ),
        )

    version_probe = await run_subprocess(
        ["go", "version"], cwd=project_workspace, timeout=10.0
    )
    if version_probe.returncode != 0:
        stderr_text = version_probe.stderr.decode("utf-8", errors="replace").strip()
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="go", engine_name="go-test"
            ),
            evidence=candidate.evidence,
            issues=(
                f"`go version` exited {version_probe.returncode}; check the "
                f"Go installation (GOROOT/GOPATH). stderr: {stderr_text[-200:]}",
            ),
        )

    engine_version = _parse_go_version(
        version_probe.stdout.decode("utf-8", errors="replace")
    )
    return EngineReadinessResult(
        state="ready",
        engine_context=NativeEngineContext(
            ecosystem="go", engine_name="go-test", engine_version=engine_version
        ),
        evidence=candidate.evidence,
        issues=(),
    )


def _parse_go_version(go_version_output: str) -> str | None:
    """Extract the bare version (e.g. ``"1.23.4"``) from ``go version``.

    Expected output shape (stable since Go 1.0):
    ``go version go1.23.4 linux/amd64``. Returns ``None`` on any
    unparseable shape — version is informational metadata, never
    load-bearing.
    """

    parts = go_version_output.strip().split()
    if len(parts) >= 3 and parts[2].startswith("go"):
        version = parts[2][2:]
        return version if version else None
    return None


# ---------------------------------------------------------------------------
# cargo-test readiness (Phase 3 adapter backlog #2)
# ---------------------------------------------------------------------------


async def _assess_cargo_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    """Decide ``cargo nextest``'s readiness state for a Cargo workspace.

    Sequence (per `decisions/2026-05-29-cargo-adapter-nextest-primary.md`):
    1. ``cargo`` on PATH? If absent → ``engine-missing``.
    2. ``Cargo.toml`` still present? Already confirmed by candidate
       detection but re-checked to close a TOCTOU window.
    3. ``cargo nextest --version`` succeeds? **Required.** Per the Q3
       decision there is no plain-text ``cargo test`` fallback; nextest
       absence is surfaced as ``engine-misconfigured`` with a clear
       install hint.
    4. ``cargo --version`` succeeds? If non-zero → ``engine-misconfigured``
       (broken Rust installation). Otherwise → ``ready`` with parsed
       engine_version.
    """

    if shutil.which("cargo") is None:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=candidate.evidence,
            issues=(
                "`cargo` not found on PATH; install Rust toolchain from "
                "https://rustup.rs",
            ),
        )

    # Defensive re-check: marker detection already saw Cargo.toml, but
    # the workspace state can drift between that scan and now.
    if not (project_workspace / "Cargo.toml").is_file():
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="rust", engine_name="cargo-test"
            ),
            evidence=candidate.evidence,
            issues=(
                "Rust workspace marker `Cargo.toml` is no longer present at "
                "the workspace root",
            ),
        )

    # nextest is REQUIRED — no plain-text fallback (Q3 decision §3).
    nextest_probe = await run_subprocess(
        ["cargo", "nextest", "--version"],
        cwd=project_workspace,
        timeout=15.0,
    )
    if nextest_probe.returncode != 0:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="rust", engine_name="cargo-test"
            ),
            evidence=candidate.evidence,
            issues=(
                "`cargo nextest` is not installed (required by the cargo-test "
                "adapter — there is no plain-text fallback per the Q3 "
                "decision). Install with: cargo install cargo-nextest "
                "--locked (or use cargo binstall)",
            ),
        )

    version_probe = await run_subprocess(
        ["cargo", "--version"],
        cwd=project_workspace,
        timeout=10.0,
    )
    if version_probe.returncode != 0:
        stderr_text = version_probe.stderr.decode("utf-8", errors="replace").strip()
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="rust", engine_name="cargo-test"
            ),
            evidence=candidate.evidence,
            issues=(
                f"`cargo --version` exited {version_probe.returncode}; check "
                f"the Rust installation (rustup). stderr: {stderr_text[-200:]}",
            ),
        )

    engine_version = _parse_cargo_version(
        version_probe.stdout.decode("utf-8", errors="replace")
    )
    return EngineReadinessResult(
        state="ready",
        engine_context=NativeEngineContext(
            ecosystem="rust",
            engine_name="cargo-test",
            engine_version=engine_version,
        ),
        evidence=candidate.evidence,
        issues=(),
    )


# ---------------------------------------------------------------------------
# junit readiness (Phase 2.5 fifth-ecosystem slice)
# ---------------------------------------------------------------------------


async def _assess_junit_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    """Decide JUnit 5's readiness state for a Java workspace.

    Sequence (per task brief §5 + §10 doctor probe table):
    1. OS gate — Windows is unsupported until the PyApp Windows binary
       pipeline ships (Open Question #16). Surface ``os-unsupported``.
    2. Detect the build tool from manifest files (pom.xml /
       build.gradle{,.kts}). The marker detector already saw at least
       one — re-resolve which one here so we know whether to probe
       ``mvn`` or ``gradle`` next.
    3. JDK on PATH? If absent → ``engine-misconfigured`` /
       ``missing-jdk`` with install hint.
    4. Build tool binary on PATH (or ``./gradlew`` wrapper for Gradle)?
       If absent → ``engine-misconfigured`` / ``missing-build-tool``.
    5. JUnit Jupiter declared in manifest? If absent → ``engine-
       misconfigured`` / ``missing-jupiter`` (with specific JUnit 4 /
       TestNG diagnostics when those are detected as the actual blocker).
    6. JUnit 4 declared alongside Jupiter? → ``engine-misconfigured`` /
       ``junit-4-not-supported`` (D5).
    7. TestNG declared alongside Jupiter? → ``engine-misconfigured`` /
       ``testng-not-supported``.
    8. Best-effort Jupiter version capture; informational metadata on
       the returned context.
    """

    # Step 1: OS gate (per decision §"Windows" in
    # 2026-06-03-junit-console-launcher-vendor.md).
    if sys.platform.startswith("win"):
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "JUnit adapter requires a non-Windows host until the "
                "Windows binary pipeline ships (Open Question #16)",
            ),
        )

    # Step 2: build tool detection.
    build_tool = _detect_build_tool(project_workspace)
    if build_tool is None:
        # Marker detector saw at least one of pom.xml / build.gradle{,.kts}
        # but neither resolves now — TOCTOU. Surface as misconfigured
        # rather than crash the workflow.
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "Java workspace markers were detected but neither pom.xml "
                "nor build.gradle{,.kts} is readable at the workspace root",
            ),
        )

    # Step 3: JDK on PATH.
    if shutil.which("java") is None:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "`java` not found on PATH; install JDK 17+ (see "
                "scripts/dev-host-setup.md §5)",
            ),
        )

    # Step 4: build tool binary on PATH (or gradlew wrapper).
    if build_tool == "maven":
        if shutil.which("mvn") is None:
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="java", engine_name="junit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "`mvn` not found on PATH; install Maven 3.9+ (see "
                    "scripts/dev-host-setup.md §5)",
                ),
            )
    else:  # gradle
        has_wrapper = (project_workspace / "gradlew").is_file()
        if shutil.which("gradle") is None and not has_wrapper:
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="java", engine_name="junit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "`gradle` not found on PATH and no `./gradlew` wrapper "
                    "in workspace; install Gradle 7.6+ (see "
                    "scripts/dev-host-setup.md §5) or commit the wrapper",
                ),
            )

    # Step 5: Jupiter declared.
    if not _detects_jupiter_in_manifest(project_workspace, build_tool):
        # JUnit 4 / TestNG diagnostic specificity: when Jupiter is
        # missing AND the manifest carries JUnit 4 or TestNG, surface
        # the specific framework rather than the generic
        # `missing-jupiter` so the user knows the actual blocker.
        if _detects_junit4_in_manifest(project_workspace, build_tool):
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="java", engine_name="junit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "JUnit 4 detected (artifactId=junit, version=4.x); "
                    "Nove Test supports JUnit 5 (Jupiter) only — migrate "
                    "via the JUnit Vintage Engine or upgrade tests to "
                    "Jupiter",
                ),
            )
        if _detects_testng_in_manifest(project_workspace, build_tool):
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="java", engine_name="junit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "TestNG detected (artifactId=testng); Nove Test "
                    "currently supports JUnit 5 only — TestNG support is "
                    "deferred to a future cycle",
                ),
            )
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "JUnit Jupiter (junit-jupiter) is not declared in the "
                "project's dependencies; add it to the build manifest",
            ),
        )

    # Step 6/7: JUnit 4 / TestNG present alongside Jupiter — surface a
    # specific reject so the user knows the conflict, even though
    # Jupiter would technically run. (D5 + §10 row 6/7.)
    if _detects_junit4_in_manifest(project_workspace, build_tool):
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "JUnit 4 detected alongside Jupiter; Nove Test supports "
                "JUnit 5 only — remove the JUnit 4 dependency (or run "
                "tests under JUnit Vintage Engine explicitly)",
            ),
        )
    if _detects_testng_in_manifest(project_workspace, build_tool):
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="java", engine_name="junit"
            ),
            evidence=candidate.evidence,
            issues=(
                "TestNG detected alongside Jupiter; Nove Test currently "
                "supports JUnit 5 only — remove the TestNG dependency",
            ),
        )

    # Step 8: ready. Best-effort version capture.
    engine_version = _detect_jupiter_version_for_readiness(
        project_workspace, build_tool
    )
    return EngineReadinessResult(
        state="ready",
        engine_context=NativeEngineContext(
            ecosystem="java",
            engine_name="junit",
            engine_version=engine_version,
        ),
        evidence=candidate.evidence,
        issues=(),
    )


_JUPITER_INLINE_VERSION_MAVEN_RE = re.compile(
    r"<artifactId>\s*junit-jupiter(?:-[a-z]+)?\s*</artifactId>\s*"
    r"<version>\s*([\d\.]+)\s*</version>",
    re.IGNORECASE | re.DOTALL,
)
_JUPITER_PROPERTY_VERSION_MAVEN_RE = re.compile(
    r"<junit\.jupiter\.version>\s*([\d\.]+)\s*</junit\.jupiter\.version>",
    re.IGNORECASE,
)
_JUPITER_VERSION_GRADLE_PROBE_RE = re.compile(
    r"org\.junit\.jupiter[:.\s]junit-jupiter[^\"']*['\"]\s*[,:]?\s*['\"]?"
    r"([0-9][\d\.]*)",
    re.IGNORECASE,
)


def _detect_jupiter_version_for_readiness(
    workspace: Path, build_tool: str,
) -> str | None:
    """Mirrors the adapter's `_detect_jupiter_version_*` for readiness use.

    Duplicated rather than imported to avoid circular import (readiness
    already imports detection helpers from the adapter; the version
    parse here uses regexes specific to the readiness context).
    """

    if build_tool == "maven":
        content = ""
        path = workspace / "pom.xml"
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                return None
        match = _JUPITER_PROPERTY_VERSION_MAVEN_RE.search(content)
        if match:
            return match.group(1)
        inline = _JUPITER_INLINE_VERSION_MAVEN_RE.search(content)
        return inline.group(1) if inline else None
    if build_tool == "gradle":
        content = ""
        for fname in ("build.gradle", "build.gradle.kts"):
            path = workspace / fname
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                    break
                except OSError:
                    continue
        match = _JUPITER_VERSION_GRADLE_PROBE_RE.search(content)
        return match.group(1) if match else None
    return None


def _parse_cargo_version(cargo_version_output: str) -> str | None:
    """Extract the bare version (e.g. ``"1.74.0"``) from ``cargo --version``.

    Expected output shape (stable since cargo 1.0): ``cargo 1.74.0
    (ecb9851af 2023-10-18)``. Returns ``None`` on any unparseable shape
    — version is informational metadata, never load-bearing.
    """

    parts = cargo_version_output.strip().split()
    if len(parts) >= 2 and parts[0] == "cargo":
        version = parts[1]
        return version if version else None
    return None


# ---------------------------------------------------------------------------
# xunit / .NET readiness (Phase 2.5 sixth-and-last-ecosystem slice)
# ---------------------------------------------------------------------------


_XUNIT_PACKAGEREF_PROBE_RE: re.Pattern[str] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']xunit[\"'](?![.])",
    re.IGNORECASE,
)
_XUNIT_V3_PACKAGEREF_PROBE_RE: re.Pattern[str] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']xunit[\"'][^>]*"
    r"Version\s*=\s*[\"']3\.",
    re.IGNORECASE,
)
_MSTEST_PACKAGEREF_PROBE_RE: re.Pattern[str] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']MSTest\.TestFramework[\"']",
    re.IGNORECASE,
)
_NUNIT_PACKAGEREF_PROBE_RE: re.Pattern[str] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']NUnit[\"']",
    re.IGNORECASE,
)


async def _assess_xunit_readiness(
    project_workspace: Path,
    candidate: EngineCandidate,
) -> EngineReadinessResult:
    """Decide xunit's readiness state for a .NET workspace.

    Sequence (per task brief §3.1 + decision 2026-06-03):
    1. ``dotnet`` on PATH? If absent → ``engine-missing`` (engine cannot
       run at all; engine_context dropped so the caller does not name
       xunit in the guidance — there is no xunit reachable yet).
    2. ``*.csproj`` present (one-level walk to support the canonical
       library + test project split)? Already confirmed by candidate
       detection; re-checked to close a TOCTOU window.
    3. xUnit ``<PackageReference Include="xunit">`` in the picked test
       csproj? If MSTest or NUnit detected instead → ``engine-
       misconfigured`` with framework-specific guidance. If none of the
       three → generic ``missing-xunit``.
    4. Best-effort SDK version capture from ``dotnet --version`` —
       informational metadata; never fails the state.

    Coverlet floor is NOT a readiness gate (the adapter itself emits
    a runtime warning + falls back to aggregate when Coverlet is below
    floor — see `dotnet_adapter.run_xunit`). Coverlet is only required
    when `collect_coverage=True`; bare ``novetest run`` works without it.
    """

    if shutil.which("dotnet") is None:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=candidate.evidence,
            issues=(
                "`dotnet` not found on PATH; install .NET SDK 8.0+ "
                "(see scripts/dev-host-setup.md §6)",
            ),
        )

    # Test-project selection is single-sourced from the adapter's
    # ``_detect_test_project`` (RUN-14, W1/S2): readiness must probe the
    # exact csproj ``run_xunit`` will hand to ``dotnet test``, so the
    # token set, sort, and pick rule live in ONE place. A local
    # re-implementation here diverged once ("test" only vs the adapter's
    # tests/test/specs/spec) and let readiness answer ``ready`` for a
    # csproj the adapter never runs — or block a runnable workspace.
    chosen_csproj, _all_csprojs, _all_slns = _detect_test_project(
        project_workspace
    )
    if chosen_csproj is None:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="dotnet", engine_name="xunit"
            ),
            evidence=candidate.evidence,
            issues=(
                ".NET workspace markers detected but no *.csproj found at "
                "the workspace root or one level deep; expected the "
                "canonical library + test project split (e.g. "
                "MyLib/MyLib.csproj + MyLib.Tests/MyLib.Tests.csproj)",
            ),
        )

    try:
        csproj_content = chosen_csproj.read_text(encoding="utf-8")
    except OSError:
        csproj_content = ""

    if _XUNIT_V3_PACKAGEREF_PROBE_RE.search(csproj_content) is not None:
        # v3 is a "readiness=ready, but coverage will be deferred" state.
        # The adapter's run-time warning surfaces the deferral; readiness
        # itself stays green so the user CAN run tests.
        engine_version = await _probe_dotnet_sdk_version(project_workspace)
        return EngineReadinessResult(
            state="ready",
            engine_context=NativeEngineContext(
                ecosystem="dotnet",
                engine_name="xunit",
                engine_version=engine_version,
            ),
            evidence=candidate.evidence,
            issues=(),
        )

    if _XUNIT_PACKAGEREF_PROBE_RE.search(csproj_content) is None:
        # No xunit. Diagnose whether it's MSTest / NUnit / nothing.
        if _MSTEST_PACKAGEREF_PROBE_RE.search(csproj_content) is not None:
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="dotnet", engine_name="xunit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "MSTest detected (PackageReference MSTest.TestFramework); "
                    "Nove Test currently supports xUnit v2 only — MSTest "
                    "support is deferred to a future cycle per "
                    "decisions/2026-06-03-coverlet-pertestcoverage-key.md "
                    "§\"Why no separate MstestAdapter / NunitAdapter\"",
                ),
            )
        if _NUNIT_PACKAGEREF_PROBE_RE.search(csproj_content) is not None:
            return EngineReadinessResult(
                state="engine-misconfigured",
                engine_context=NativeEngineContext(
                    ecosystem="dotnet", engine_name="xunit"
                ),
                evidence=candidate.evidence,
                issues=(
                    "NUnit detected (PackageReference NUnit); Nove Test "
                    "currently supports xUnit v2 only — NUnit support is "
                    "deferred to a future cycle per "
                    "decisions/2026-06-03-coverlet-pertestcoverage-key.md "
                    "§\"Why no separate MstestAdapter / NunitAdapter\"",
                ),
            )
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem="dotnet", engine_name="xunit"
            ),
            evidence=candidate.evidence,
            issues=(
                "xUnit is not declared in "
                f"{chosen_csproj.name}; add "
                "<PackageReference Include=\"xunit\" Version=\"2.6.0\" /> "
                "(or later 2.x) and <PackageReference Include="
                "\"xunit.runner.visualstudio\" /> to the test project",
            ),
        )

    engine_version = await _probe_dotnet_sdk_version(project_workspace)
    return EngineReadinessResult(
        state="ready",
        engine_context=NativeEngineContext(
            ecosystem="dotnet",
            engine_name="xunit",
            engine_version=engine_version,
        ),
        evidence=candidate.evidence,
        issues=(),
    )


async def _probe_dotnet_sdk_version(workspace: Path) -> str | None:
    """Best-effort SDK version read via ``dotnet --version``.

    Returns ``"8.0.421"`` shape strings. None silently on any subprocess
    failure (informational metadata only; never load-bearing for the
    readiness state's correctness).
    """

    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return None
    try:
        result = await run_subprocess(
            [dotnet, "--version"],
            cwd=workspace,
            timeout=10.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    return text or None


# ---------------------------------------------------------------------------
# Probe registry
# ---------------------------------------------------------------------------

# Per-engine readiness probes, keyed by the supported (ecosystem,
# engine_name) pairs. Deliberately UNORDERED (a dict, not a list):
# disambiguation order lives solely in `engine_selector._ENGINE_MARKER_TABLE`
# — `assess_engine_readiness` takes the first detected candidate and this
# registry only answers "which probe implements that pair". The divergence
# guard in `tests/unit/run/test_engine_selector.py` pins registry keys ==
# `list_supported_engine_pairs()`.
_READINESS_PROBES: dict[
    tuple[str, str],
    Callable[[Path, EngineCandidate], Awaitable[EngineReadinessResult]],
] = {
    ("python", "pytest"): _assess_pytest_readiness,
    ("javascript-typescript", "jest"): _assess_jest_readiness,
    ("java", "junit"): _assess_junit_readiness,
    ("go", "go-test"): _assess_gotest_readiness,
    ("rust", "cargo-test"): _assess_cargo_readiness,
    ("dotnet", "xunit"): _assess_xunit_readiness,
}
