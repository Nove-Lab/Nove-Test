"""``novetest init`` workflow — anchored engine pin (D1 + D4).

Implements decision ``agent-comms/decisions/2026-07-03-engine-selection-policy.md``:
``init`` is the ONLY place engine detection decides anything. The outcome is a
three-way union the CLI pattern-matches on:

- ``InitializationResult`` — a Project Store exists/was created and carries an
  engine pin (``store.pinned_engine`` is set). ``engine_readiness`` reports the
  pinned engine's probe; readiness stays informational — a missing or
  misconfigured engine never rolls back the store (NFR-RUN-004).
- ``InitNoEngineDetected`` — no marker at the init directory. NOTHING was
  created for a fresh workspace; the D4 bounded downward discovery ran (the
  only downward scan in the product) and its candidate report is attached.
  ``scan_refused`` is True when init was invoked at a filesystem root or
  ``$HOME`` (D4 bound 3: refuse without traversal).
- ``InitEngineAmbiguous`` — no single engine choice (see
  ``anchor_resolution.choose_workspace_engine`` for the exact rule). NOTHING
  was created for a fresh workspace; the caller must re-run with
  ``--engine <name>``.

``engine`` (a pre-validated ``(ecosystem, engine_name)`` pair from the CLI's
``--engine`` flag) skips detection entirely: explicit wins, in all cases.
Re-running ``init --engine <other>`` on an existing store re-pins IN PLACE —
same store, pin updated, run history retained; a second ``.novetest/`` is
never created for a second engine.

Edge case: an *existing* store whose workspace yields no engine choice (a
legacy pin-less store on a markerless/ambiguous anchor) returns the matching
failure value but leaves the store untouched — init never destroys state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from novetest.memory import (
    STORE_DIRNAME,
    STORE_METADATA_FILENAME,
    ProjectStore,
    create_project_store,
)
from novetest.memory.project_store import PinnedEngine, set_pinned_engine
from novetest.orchestration.anchor_resolution import (
    AmbiguousEngines,
    choose_workspace_engine,
)
from novetest.orchestration.workflows.discovery import (
    DiscoveredCandidate,
    discover_candidates_below,
)
from novetest.run import EngineCandidate, EngineReadinessResult, probe_engine


@dataclass(slots=True, frozen=True)
class InitializationResult:
    """Combined onboarding outcome handed back to the CLI / agent caller.

    ``store.pinned_engine`` is always set on this success shape (the store
    handle is re-read after pinning, so it reflects disk state).
    """

    store: ProjectStore
    engine_readiness: EngineReadinessResult


@dataclass(slots=True, frozen=True)
class InitNoEngineDetected:
    """D1 "no marker" outcome: nothing created, D4 discovery report attached."""

    candidates: tuple[DiscoveredCandidate, ...]
    scan_refused: bool


@dataclass(slots=True, frozen=True)
class InitEngineAmbiguous:
    """D1 ambiguous outcome: nothing created, explicit ``--engine`` required."""

    candidates: tuple[EngineCandidate, ...]


async def initialize_project_workspace(
    workspace_path: Path,
    *,
    engine: tuple[str, str] | None = None,
) -> InitializationResult | InitNoEngineDetected | InitEngineAmbiguous:
    """Anchor an engine pin at ``workspace_path`` (D1), creating the store when needed.

    ``engine`` is the CLI-validated ``(ecosystem, engine_name)`` pair from
    ``--engine``; when supplied, detection and ambiguity handling are skipped
    and that engine is pinned (re-pin in place on an existing store).

    Sequencing is load-bearing: for a fresh workspace the engine choice is
    made BEFORE ``create_project_store``, so the no-marker and ambiguous
    outcomes create nothing. An existing store (idempotent re-init) keeps its
    pin when it has one; a legacy pin-less store gets the same choice rule
    applied and is backfilled in place.
    """

    if engine is not None:
        ecosystem, engine_name = engine
        store = create_project_store(workspace_path)
        return InitializationResult(
            store=_pin(store, ecosystem, engine_name),
            engine_readiness=await probe_engine(
                workspace_path, ecosystem, engine_name
            ),
        )

    existing = _existing_store_metadata(workspace_path)
    if existing is not None and existing.pinned_engine is not None:
        # Idempotent re-init: the pin governs; no detection re-runs (D2's
        # "a store implies a pin" invariant).
        pin = existing.pinned_engine
        return InitializationResult(
            store=existing,
            engine_readiness=await probe_engine(
                workspace_path, pin.ecosystem, pin.engine_name
            ),
        )

    choice = await choose_workspace_engine(workspace_path)
    if choice is None:
        discovered = discover_candidates_below(workspace_path)
        return InitNoEngineDetected(
            candidates=discovered if discovered is not None else (),
            scan_refused=discovered is None,
        )
    if isinstance(choice, AmbiguousEngines):
        return InitEngineAmbiguous(candidates=choice.candidates)

    store = create_project_store(workspace_path)
    return InitializationResult(
        store=_pin(store, choice.ecosystem, choice.engine_name),
        engine_readiness=choice.readiness,
    )


def _existing_store_metadata(workspace_path: Path) -> ProjectStore | None:
    """Return the store handle when ``<workspace>/.novetest/store.json`` exists.

    Deliberately checks ``workspace_path`` itself — never a walk-up. ``init``
    anchors where the user stands (D1); verb-time anchor resolution is
    ``anchor_resolution.resolve_workspace``'s job (D2).
    """

    metadata = workspace_path / STORE_DIRNAME / STORE_METADATA_FILENAME
    if not metadata.exists():
        return None
    return create_project_store(workspace_path)  # idempotent read of the handle


def _pin(store: ProjectStore, ecosystem: str, engine_name: str) -> ProjectStore:
    """Persist the pin and return a handle reflecting it (choice → disk)."""

    set_pinned_engine(store, ecosystem, engine_name)
    return replace(
        store,
        pinned_engine=PinnedEngine(ecosystem=ecosystem, engine_name=engine_name),
    )
