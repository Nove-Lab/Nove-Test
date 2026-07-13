"""Marker detection for the supported (ecosystem, engine) pairs.

This module owns THE single source of truth for engine detection: the
ordered marker/priority table `_ENGINE_MARKER_TABLE`. Everything that
needs to know "what markers identify each ecosystem, and who wins on a
polyglot workspace" derives from that one constant —
`detect_engine_candidates`, and through it the disambiguation inside
`readiness.assess_engine_readiness`. The supported PAIR matrix itself
lives one layer down in `models.engine_matrix.SUPPORTED_ENGINE_PAIRS`
(XCT-13 / S43); `list_supported_engine_pairs` returns that domain
constant since S11 collapsed the run-side derived copy, and divergence
guards (`tests/unit/run/test_engine_selector.py`,
`tests/unit/models/test_engine_matrix.py`) pin the marker table's
(ecosystem, engine) projection exactly equal to it. Run-time dispatch
is pin-driven and lives in `engine.py`'s `_ADAPTER_ENTRY_POINTS` dict —
detection here decides only what a pin CAN name. There is deliberately
no second ordered list anywhere in `run/`; the historic
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

from novetest.models import SUPPORTED_ENGINE_PAIRS
from novetest.run.types import EngineCandidate

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

def list_supported_engine_pairs() -> tuple[tuple[str, str], ...]:
    """Return the (ecosystem, engine_name) pairs Nove Test claims to support.

    Returns the ``models.SUPPORTED_ENGINE_PAIRS`` domain constant — the
    SSoT since XCT-13/S43 promoted the matrix out of this module; S11
    collapsed the run-side derived copy onto it. `_ENGINE_MARKER_TABLE`
    above stays the DETECTION source (markers + priority); its
    (ecosystem, engine) projection is pinned exactly equal to the models
    constant by the divergence guards, so the two data sources cannot
    drift apart silently.
    """

    return SUPPORTED_ENGINE_PAIRS


def detect_engine_candidates(project_workspace: Path) -> tuple[EngineCandidate, ...]:
    """Infer candidate (ecosystem, engine) pairs from workspace markers.

    Marker-based only: scans ONE directory (plus the dotnet row's
    one-level csproj glob), no recursion, no subprocess. Candidates come
    back in canonical priority order — the first entry is the canonical
    winner (the pair that, once pinned, `engine.py`'s
    `_ADAPTER_ENTRY_POINTS` dispatch runs). The caller decides how to
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
