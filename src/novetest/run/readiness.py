"""Engine readiness assessment for a Project Workspace.

Workflow per `design/interace-contract/run.md` §1 + `design/workflows/run.md`:
1. `detect_engine_candidates` scans workspace markers and returns the
   inferred (ecosystem, engine) candidates.
2. `assess_engine_readiness` reconciles those candidates with the supported
   pairs from `list_supported_engine_pairs`, then per-engine does a deeper
   check:
   - pytest: pytest config present + pytest + pytest-json-report importable
     from the resolved interpreter.
   - jest: ``node`` on PATH + jest declared in ``package.json``
     ``dependencies`` / ``devDependencies`` or installed under
     ``node_modules/.bin/jest``.

Both surfaces are pure inspection. **Nothing is ever installed.**
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from novetest.run.engine_selector import list_supported_engine_pairs
from novetest.run.types import (
    EngineCandidate,
    EngineReadinessResult,
    NativeEngineContext,
)
from novetest.utils.asyncio_subprocess import run_subprocess


_PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini")
_JS_MARKERS = ("package.json",)
_JAVA_MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts")
_GO_MARKERS = ("go.mod",)
_RUST_MARKERS = ("Cargo.toml",)


def detect_engine_candidates(project_workspace: Path) -> tuple[EngineCandidate, ...]:
    """Infer candidate (ecosystem, engine) pairs from workspace markers.

    Marker-based only; no filesystem walks, no subprocess. Multiple
    candidates may be returned for polyglot workspaces — the caller decides
    how to disambiguate.
    """

    candidates: list[EngineCandidate] = []

    python_evidence = _existing_markers(project_workspace, _PYTHON_MARKERS)
    if python_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="python",
                engine_name="pytest",
                evidence=python_evidence,
            )
        )

    js_evidence = _existing_markers(project_workspace, _JS_MARKERS)
    if js_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="javascript-typescript",
                engine_name="jest",
                evidence=js_evidence,
            )
        )

    java_evidence = _existing_markers(project_workspace, _JAVA_MARKERS)
    if java_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="java",
                engine_name="junit",
                evidence=java_evidence,
            )
        )

    go_evidence = _existing_markers(project_workspace, _GO_MARKERS)
    if go_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="go",
                engine_name="go-test",
                evidence=go_evidence,
            )
        )

    rust_evidence = _existing_markers(project_workspace, _RUST_MARKERS)
    if rust_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="rust",
                engine_name="cargo-test",
                evidence=rust_evidence,
            )
        )

    dotnet_evidence = _glob_markers(project_workspace, ("*.csproj", "*.sln"))
    if dotnet_evidence:
        candidates.append(
            EngineCandidate(
                ecosystem="dotnet",
                engine_name="xunit",
                evidence=dotnet_evidence,
            )
        )

    return tuple(candidates)


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
    """

    candidates = detect_engine_candidates(project_workspace)
    supported = {pair for pair in list_supported_engine_pairs()}

    relevant = [c for c in candidates if (c.ecosystem, c.engine_name) in supported]
    if not relevant:
        return EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=tuple(sorted({m for c in candidates for m in c.evidence})),
            issues=("no supported (ecosystem, native engine) pair detected in workspace",),
        )

    # Prefer the python+pytest candidate when both python and js workspaces
    # are present (a hybrid repo) — Phase 1 / 2 invariant. If only jest is
    # present, route to the jest probe.
    pytest_candidate = next(
        (c for c in relevant if c.ecosystem == "python" and c.engine_name == "pytest"),
        None,
    )
    if pytest_candidate is not None:
        return await _assess_pytest_readiness(project_workspace, pytest_candidate)

    jest_candidate = next(
        (
            c
            for c in relevant
            if c.ecosystem == "javascript-typescript" and c.engine_name == "jest"
        ),
        None,
    )
    if jest_candidate is not None:
        return await _assess_jest_readiness(project_workspace, jest_candidate)

    # A supported candidate was detected, but no adapter implementation
    # exists yet (java / go / rust / dotnet) — surface as misconfigured so
    # the CLI can name the ecosystem without pretending it is ready.
    chosen = relevant[0]
    return EngineReadinessResult(
        state="engine-misconfigured",
        engine_context=NativeEngineContext(
            ecosystem=chosen.ecosystem, engine_name=chosen.engine_name
        ),
        evidence=chosen.evidence,
        issues=(f"adapter for {chosen.engine_name!r} not implemented yet",),
    )


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


def _existing_markers(root: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if (root / name).exists())


def _glob_markers(root: Path, patterns: tuple[str, ...]) -> tuple[str, ...]:
    hits: list[str] = []
    for pattern in patterns:
        for match in root.glob(pattern):
            hits.append(match.name)
    return tuple(sorted(set(hits)))


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
