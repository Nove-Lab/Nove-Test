"""Supported (ecosystem, engine) pairs and selection from a Test Target.

Phase 1 shipped pytest; Phase 2.5 added jest. The remaining four pairs
(junit / go-test / cargo-test / xunit) appear in
`list_supported_engine_pairs` so detection and CLI surfaces can name them
even though `select_native_engine` raises for any selection without an
implemented adapter.
"""

from __future__ import annotations

from novetest.run.errors import EngineNotSupportedError
from novetest.run.types import NativeEngineContext, TestTarget

# Order matches REQ-RUN-006 in the requirements specification.
_SUPPORTED_PAIRS: tuple[tuple[str, str], ...] = (
    ("python", "pytest"),
    ("javascript-typescript", "jest"),
    ("java", "junit"),
    ("go", "go-test"),
    ("rust", "cargo-test"),
    ("dotnet", "xunit"),
)

# Workspace markers that identify the ecosystem of a Test Target. Multiple
# markers per ecosystem are OK; the first match wins.
_ECOSYSTEM_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini")),
    ("javascript-typescript", ("package.json",)),
    ("java", ("pom.xml", "build.gradle", "build.gradle.kts")),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
)


def list_supported_engine_pairs() -> tuple[tuple[str, str], ...]:
    """Return the (ecosystem, engine_name) pairs Nove Test claims to support."""

    return _SUPPORTED_PAIRS


def _ecosystem_for_workspace(workspace_path: object) -> str | None:
    """Return the ecosystem of ``workspace_path`` or ``None`` if not inferable."""

    from pathlib import Path

    if not isinstance(workspace_path, Path):
        return None
    for ecosystem, markers in _ECOSYSTEM_MARKERS:
        if any((workspace_path / m).exists() for m in markers):
            return ecosystem
    # .NET uses glob markers; check separately.
    if any(workspace_path.glob("*.csproj")) or any(workspace_path.glob("*.sln")):
        return "dotnet"
    return None


_IMPLEMENTED_ECOSYSTEM_TO_ENGINE: dict[str, str] = {
    "python": "pytest",
    "javascript-typescript": "jest",
}


def select_native_engine(test_target: TestTarget) -> NativeEngineContext:
    """Pick the Native Engine for a resolved Test Target.

    Returns a `NativeEngineContext` for any ecosystem with a shipping
    adapter (python+pytest, javascript-typescript+jest). Any other
    detected-but-not-yet-implemented ecosystem (java / go / rust / dotnet)
    raises `EngineNotSupportedError`. Workspaces that match no supported
    ecosystem also raise — the caller is expected to gate on
    `assess_engine_readiness` first.
    """

    ecosystem = _ecosystem_for_workspace(test_target.workspace_path)
    if ecosystem is None:
        raise EngineNotSupportedError(
            f"no supported ecosystem detected for workspace {test_target.workspace_path!s}"
        )
    engine_name = _IMPLEMENTED_ECOSYSTEM_TO_ENGINE.get(ecosystem)
    if engine_name is None:
        raise EngineNotSupportedError(
            f"adapter for ecosystem {ecosystem!r} not implemented yet"
        )
    return NativeEngineContext(ecosystem=ecosystem, engine_name=engine_name)
