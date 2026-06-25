"""``novetest reset`` workflow: wipe the active Project Store, then re-init.

Composes Memory's destructive ``wipe_project_store`` primitive with the
existing ``init`` composition, exactly as
``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``
§"Atomicity guarantee" prescribes: locate → refuse-if-absent → wipe →
re-create skeleton → re-probe engine readiness.

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

from novetest.orchestration.workflows.init import (
    InitializationResult,
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


async def reset_project_workspace(workspace_path: Path) -> ResetResult:
    """Wipe the active Project Store, then re-create it via ``init``.

    Raises (before any destructive action) when the workspace has no
    Project Store in its walk-up chain (``ProjectStoreNotFoundError`` →
    CLI ``uninitialized`` / exit 2). A corrupt store surfaces as
    ``ProjectStoreCorruptError`` (raised by ``wipe_project_store`` →
    CLI ``store-corrupt`` / exit 5) — reset deliberately refuses to wipe a
    store it cannot read. Any filesystem failure during the wipe surfaces
    as ``OSError`` (→ CLI ``store-wipe-failed`` / exit 5); the primitive's
    atomic-rename guard means the original store is still recoverable.
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
    wipe_report = wipe_project_store(store.path)
    init_result = await initialize_project_workspace(workspace_path)
    return ResetResult(wipe_report=wipe_report, init_result=init_result)
