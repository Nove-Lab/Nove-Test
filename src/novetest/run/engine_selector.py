"""Supported (ecosystem, engine) pairs, marker detection, and selection.

This module owns THE single source of truth for engine detection: the
ordered marker/priority table `_ENGINE_MARKER_TABLE`. Everything that
needs to know "which ecosystems exist, what markers identify them, and
who wins on a polyglot workspace" derives from that one constant —
`list_supported_engine_pairs`, `detect_engine_candidates`,
`select_native_engine`, and (via `detect_engine_candidates`) the
disambiguation inside `readiness.assess_engine_readiness`. There is
deliberately no second ordered list anywhere in `run/`; the historic
selector-vs-readiness rank mismatch (java 3rd vs junit 5th — the §4.1
latent bug of the 2026-07-02 engine-selection-policy question) is dead
by construction. See `decisions/2026-07-03-engine-selection-policy.md`
§"Kills the two-priority-lists latent bug by design".

Phase 1 shipped pytest; Phase 2.5 added jest; Phase 3 (adapter backlog
slice #1) added go-test; Phase 3 (adapter backlog slice #2) added
cargo-test; Phase 2.5 fifth-ecosystem slice added junit; Phase 2.5
sixth-and-final slice added xunit (.NET). All six pairs in
`list_supported_engine_pairs` are fully implemented adapters.
"""

from __future__ import annotations

from pathlib import Path

from novetest.run.errors import EngineNotSupportedError
from novetest.run.types import EngineCandidate, NativeEngineContext, TestTarget

# THE canonical ordered marker/priority table. Row order matches
# REQ-RUN-006 in the requirements specification and decides which engine
# wins when a workspace matches multiple ecosystems (earlier row wins).
#
# Markers containing ``*`` are glob patterns evaluated relative to the
# workspace root; plain names are literal existence checks. The dotnet
# row needs globs because .NET has no fixed-name root manifest: the
# canonical pattern places csprojs in subdirectories
# (``MyLib/MyLib.csproj`` + ``MyLib.Tests/MyLib.Tests.csproj``), hence
# the one-level ``*/*.csproj`` walk; ``*.sln`` lives at workspace root
# by convention so it only globs depth 0.
_ENGINE_MARKER_TABLE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("python", "pytest", ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini")),
    ("javascript-typescript", "jest", ("package.json",)),
    ("java", "junit", ("pom.xml", "build.gradle", "build.gradle.kts")),
    ("go", "go-test", ("go.mod",)),
    ("rust", "cargo-test", ("Cargo.toml",)),
    ("dotnet", "xunit", ("*.sln", "*.csproj", "*/*.csproj")),
)

_SUPPORTED_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (ecosystem, engine_name) for ecosystem, engine_name, _ in _ENGINE_MARKER_TABLE
)


def list_supported_engine_pairs() -> tuple[tuple[str, str], ...]:
    """Return the (ecosystem, engine_name) pairs Nove Test claims to support."""

    return _SUPPORTED_PAIRS


def detect_engine_candidates(project_workspace: Path) -> tuple[EngineCandidate, ...]:
    """Infer candidate (ecosystem, engine) pairs from workspace markers.

    Marker-based only: scans ONE directory (plus the dotnet row's
    one-level csproj glob), no recursion, no subprocess. Candidates come
    back in canonical priority order — first entry is what
    `select_native_engine` would dispatch. The caller decides how to
    disambiguate: `novetest init` treats ≥2 READY candidates as
    `engine-ambiguous` (decision 2026-07-03-engine-selection-policy D1,
    with per-candidate readiness via `readiness.probe_engine`), while
    `assess_engine_readiness` probes the first candidate.
    """

    candidates: list[EngineCandidate] = []
    for ecosystem, engine_name, markers in _ENGINE_MARKER_TABLE:
        evidence = _marker_evidence(project_workspace, markers)
        if evidence:
            candidates.append(
                EngineCandidate(
                    ecosystem=ecosystem,
                    engine_name=engine_name,
                    evidence=evidence,
                )
            )
    return tuple(candidates)


def _marker_evidence(root: Path, markers: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve which of ``markers`` exist under ``root``.

    Literal markers are reported in declaration order under their
    declared name; glob markers are reported as sorted, de-duplicated
    root-relative paths in POSIX form on every platform (identifiable
    downstream when multiple matches at different depths share a
    basename). POSIX separators are load-bearing: evidence strings flow
    into readiness/init envelopes consumed by AI agents, so the same
    workspace must serialize identically on Windows and POSIX hosts
    (2026-07-03 fast-follow; ``str(PurePath)`` yields ``\\`` on Windows).
    """

    literal_hits: list[str] = []
    glob_hits: set[str] = set()
    for marker in markers:
        if "*" in marker:
            for match in root.glob(marker):
                glob_hits.add(match.relative_to(root).as_posix())
        elif (root / marker).exists():
            literal_hits.append(marker)
    return tuple(literal_hits) + tuple(sorted(glob_hits))


def select_native_engine(test_target: TestTarget) -> NativeEngineContext:
    """Pick the Native Engine for a resolved Test Target.

    The first candidate in canonical table order wins — by construction
    the same engine `assess_engine_readiness` probes. Workspaces that
    match no supported ecosystem raise — the caller is expected to gate
    on `assess_engine_readiness` first.

    Under the anchored-pin model this auto-detect selection only serves
    the legacy `execute(engine=None)` path; pinned flows hand `execute`
    the resolved pair directly and never reach this function.
    """

    candidates = detect_engine_candidates(test_target.workspace_path)
    if not candidates:
        raise EngineNotSupportedError(
            f"no supported ecosystem detected for workspace {test_target.workspace_path!s}"
        )
    chosen = candidates[0]
    return NativeEngineContext(
        ecosystem=chosen.ecosystem, engine_name=chosen.engine_name
    )
