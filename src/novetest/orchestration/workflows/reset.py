"""``novetest reset`` workflow: wipe the active Project Store, then re-init.

Composes Memory's destructive ``wipe_project_store`` primitive with the
existing ``init`` composition, exactly as
``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``
§"Atomicity guarantee" prescribes: locate → refuse-if-absent → wipe →
re-create skeleton → re-probe engine readiness.

Anchored-pin integration (decision ``2026-07-03-engine-selection-policy.md``):

- The re-init happens at the wiped store's **anchor** (``store.path.parent``),
  not at the invocation cwd — resetting from a subdirectory must rebuild the
  same workspace it wiped, never relocate the store (D2).
- The previous store's engine pin is **carried over** to the re-created
  store: the user consented to that engine at ``init`` time and ``reset``
  wipes *evidence*, not intent. Without the carry-over, resetting a
  dual-marker workspace would wipe the store and then fail ambiguous —
  destroying state the user could not recover with a plain ``init``.
- A legacy pin-less store makes the D1 engine choice **before** the wipe:
  a single choice proceeds (wipe → re-init pinned to it); an ambiguous or
  markerless anchor **refuses without wiping** and passes the failure
  outcome to the CLI — reset never destroys state it cannot rebuild.

The wipe primitive is public **at module path only** —
``novetest.memory.project_store`` (Memory deliberately did not re-export it
through ``novetest.memory.__init__``). It is imported **lazily inside the
function** so each call re-reads the current
``novetest.memory.project_store`` attribute (clean per-call monkeypatch
isolation in unit tests). ``WipeReport`` is referenced only for typing,
under ``TYPE_CHECKING``. ``locate_project_store`` stays on the package path
(it is part of Memory's long-standing ``__init__`` surface).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from novetest.orchestration.anchor_resolution import (
    AmbiguousEngines,
    choose_workspace_engine,
)
from novetest.orchestration.workflows.discovery import discover_candidates_below
from novetest.orchestration.workflows.init import (
    InitEngineAmbiguous,
    InitializationResult,
    InitNoEngineDetected,
    initialize_project_workspace,
)

if TYPE_CHECKING:
    from novetest.memory.project_store import WipeReport


@dataclass(slots=True, frozen=True)
class ResetResult:
    """Combined wipe + re-init outcome handed back to the CLI / agent caller.

    ``wipe_report`` carries the pre-wipe ``items_removed`` counts and the
    old store's ``previous_initialized_at``; ``init_result`` carries the
    freshly created store plus its engine-readiness probe (identical to a
    bare ``novetest init``).
    """

    wipe_report: WipeReport
    init_result: InitializationResult


async def reset_project_workspace(
    workspace_path: Path,
) -> ResetResult | InitNoEngineDetected | InitEngineAmbiguous:
    """Wipe the active Project Store, then re-create it via ``init``.

    Raises (before any destructive action) when the workspace has no
    Project Store in its walk-up chain (``ProjectStoreNotFoundError`` →
    CLI ``uninitialized`` / exit 2). A corrupt store surfaces as
    ``ProjectStoreCorruptError`` (raised by ``wipe_project_store`` →
    CLI ``store-corrupt`` / exit 5) — reset deliberately refuses to wipe a
    store it cannot read. Any filesystem failure during the wipe surfaces
    as ``OSError`` (→ CLI ``store-wipe-failed`` / exit 5); the primitive's
    atomic-rename guard means the original store is still recoverable.

    The engine to re-pin is resolved BEFORE any destructive action: the
    previous pin when present, else the D1 choice for a legacy pin-less
    store. When that choice fails (ambiguous / markerless anchor), the
    matching ``InitEngineAmbiguous`` / ``InitNoEngineDetected`` outcome is
    returned **without wiping** — the store is left untouched and the CLI
    names the follow-up (``novetest init --engine <name>``, then retry).
    With the pair fixed up-front, the post-wipe re-init goes through the
    init workflow's explicit-``engine`` path and cannot fail.
    """

    from novetest.memory import locate_project_store
    from novetest.memory.project_store import (
        ProjectStoreNotFoundError,
        wipe_project_store,
    )

    store = locate_project_store(workspace_path)
    if store is None:
        raise ProjectStoreNotFoundError(
            "No Project Store found in this directory or any ancestor; "
            "nothing to reset. Run `novetest init` to create one."
        )
    anchor = store.path.parent
    previous_pin = store.pinned_engine
    if previous_pin is not None:
        engine_pair = (previous_pin.ecosystem, previous_pin.engine_name)
    else:
        # Legacy pin-less store: make the D1 choice BEFORE the wipe so an
        # ambiguous or markerless anchor refuses while everything is intact.
        choice = await choose_workspace_engine(anchor)
        if choice is None:
            discovered = discover_candidates_below(anchor)
            return InitNoEngineDetected(
                candidates=discovered if discovered is not None else (),
                scan_refused=discovered is None,
            )
        if isinstance(choice, AmbiguousEngines):
            return InitEngineAmbiguous(candidates=choice.candidates)
        engine_pair = (choice.ecosystem, choice.engine_name)

    wipe_report = wipe_project_store(store.path)
    init_outcome = await initialize_project_workspace(anchor, engine=engine_pair)
    if not isinstance(init_outcome, InitializationResult):
        # Structurally unreachable (explicit-engine init always succeeds);
        # kept for type soundness rather than an unchecked cast.
        return init_outcome
    return ResetResult(wipe_report=wipe_report, init_result=init_outcome)
