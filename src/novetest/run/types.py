"""Shared in-process types for the Run engine.

These are NOT persisted entities; they are call/return data classes used
between Run's internal modules. Persisted entities live under
`novetest.models` and round-trip via JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass(slots=True, frozen=True)
class TestTarget:
    """Normalized target of a run.

    The product of `run/resolve_test_target`. ``target_type`` is one of
    ``workspace`` | ``directory`` | ``file`` | ``nodeid``.
    """

    # Stop pytest from auto-collecting this `Test*`-prefixed dataclass as a
    # test class when it appears in a test module's import surface.
    __test__: ClassVar[bool] = False

    target_expression: str
    target_type: str
    workspace_path: Path


@dataclass(slots=True, frozen=True)
class NativeEngineContext:
    """Identifies the engine that will execute (or executed) a run.

    Inlined onto `RunRecord` for persistence; here it serves the internal
    handoff between the readiness probe (`probe_engine`) and `execute`'s
    adapter dispatch. ``ecosystem`` and ``engine_name`` come from
    `list_supported_engine_pairs`; ``engine_version`` is filled in after
    the adapter has probed the local install.
    """

    ecosystem: str
    engine_name: str
    engine_version: str | None = None


@dataclass(slots=True, frozen=True)
class EngineCandidate:
    """Pre-readiness inference: this ecosystem/engine pair *might* apply.

    Produced by `detect_engine_candidates` purely from filesystem markers.
    Whether the candidate is actually usable is decided by
    `assess_engine_readiness`.
    """

    ecosystem: str
    engine_name: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class EngineReadinessResult:
    """Output of `assess_engine_readiness`.

    ``state`` is one of ``ready`` | ``engine-missing`` | ``engine-misconfigured``.
    ``engine_context`` is populated when a supported adapter was detected
    (even if misconfigured, so the caller can name the engine in guidance).
    ``evidence`` enumerates the workspace markers backing the classification.
    ``issues`` carries human-readable diagnosis lines for the misconfigured
    case (empty otherwise).
    """

    state: str
    engine_context: NativeEngineContext | None
    evidence: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class AdapterWarning:
    """Notice-grade signal an adapter raises during a run.

    Structurally compatible with ``cli.output.EnvelopeWarning`` (same
    three fields ``code`` / ``message`` / ``details``) so the
    orchestration↔CLI projection at envelope-construction time is a
    field-by-field copy. Kept in ``run/`` rather than re-exporting
    ``EnvelopeWarning`` from ``cli/output.py`` so the adapter layer
    does NOT take a dependency on the CLI layer (the existing dependency
    direction is ``cli → orchestration → run``; an
    ``adapter → cli`` import would invert it).

    Per `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
    §"Option C follow-up slice scope" criterion #3 the converged shape
    is ``code: str`` (machine-friendly slug) + ``message: str``
    (human-readable hint) + ``details: dict[str, Any]`` (optional
    structured context). The reserved adapter-warning *kinds* live in
    each adapter's module constants (e.g. ``WARNING_COVERLET_ABSENT``)
    to stay close to their emit sites; the catalog is documented in
    the same decision file.
    """

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class NativeResult:
    """Raw adapter output handed to `normalize_native_result`.

    ``payload`` is the parsed engine-native structure (for pytest, the
    `pytest-json-report` JSON object). ``artifact_paths`` are absolute paths
    on disk that the orchestration layer will later copy/move into the
    Project Store under `.novetest/run/artifacts/run_<ulid>/`.

    ``metadata`` is the typed slot adapters use to stash per-engine
    auxiliary strings that MUST surface on the persisted `RunRecord`
    (e.g. secondary-runner versions like ``nextest_version`` distinct
    from the primary ``engine_version``, or engine-specific
    configuration flags an AI consumer might want to inspect). The
    normalizer overlays this dict onto its own metadata at
    `normalize_native_result` time; see that function's docstring for
    the reserved-key contract. Per
    `decisions/2026-05-30-native-result-metadata-slot.md` (option (b),
    payload-stash convention retired): keys/values are strictly
    ``str`` so the contract layer is type-checkable and IDE-visible.
    Transient per-engine state that does NOT need to surface on
    ``RunRecord`` stays in ``payload``.

    ``warnings`` carries adapter-emitted notice-grade signals that the
    orchestration layer lifts onto the JSON envelope's top-level
    ``warnings`` field (per
    `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`).
    NOT persisted onto ``RunRecord`` — warnings are transient envelope
    decorations, not facts. The forensic per-warning payload (the
    ``payload["warnings"]`` list each adapter still writes) is kept for
    one release cycle as the v1 bridge per the same decision; both
    channels are populated in steady state.

    ``workspace_root`` is the workspace the engine executed in
    (``TestTarget.workspace_path``, resolved). Transient normalization
    input, NOT persisted: the jest normalizer uses it to rewrite the
    absolute suite-file prefix of its synthesized node_ids to
    workspace-relative POSIX form (RUN-13 / W2-S11). Adapters whose
    native test identities are already workspace-stable (pytest, go,
    junit, cargo, xunit) leave it ``None``.
    """

    engine_name: str
    payload: dict[str, object]
    artifact_paths: dict[str, Path]
    returncode: int
    started_at_ms: int
    completed_at_ms: int
    engine_version: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: tuple[AdapterWarning, ...] = ()
    workspace_root: Path | None = None
