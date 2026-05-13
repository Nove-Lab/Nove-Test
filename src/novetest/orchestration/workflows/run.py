"""``novetest run`` workflow: execute target in workspace + persist to Memory.

Wires `run/execute` to `memory/store_run_evidence` exactly as
`design/workflows/run.md` §1 prescribes. Pre-generates the ULID so Run's
adapter writes Native artifacts directly under
``<store>/run/artifacts/run_<ulid>/native/``; this lets us hand Memory a
RunRecord with already-Project-Store-relative ``artifact_paths`` and skip
a post-run file move.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from novetest.memory import ProjectStore, store_run_evidence
from novetest.models import MemoryEntry
from novetest.run import execute, resolve_test_target
from novetest.utils.ulid import generate_ulid


@dataclass(slots=True, frozen=True)
class RunOutcome:
    """Result of the run-and-persist workflow."""

    memory_entry: MemoryEntry
    artifact_dir: Path


async def run_target_in_store(
    target_expression: str,
    store: ProjectStore,
    *,
    timeout: float | None = 600.0,
) -> RunOutcome:
    """Resolve target → execute → persist.

    The workspace path is the parent of ``store.path`` (i.e. the directory
    that contains ``.novetest/``). ``target_expression`` is the user-facing
    string from the CLI; resolution into file/directory/nodeid happens here.
    """

    workspace_path = store.path.parent
    target = resolve_test_target(target_expression, workspace_path)
    run_id = generate_ulid()
    artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"

    record = await execute(
        target,
        artifact_dir=artifact_dir,
        run_id=run_id,
        timeout=timeout,
    )

    relative_paths = {
        name: str(Path(p).relative_to(store.path))
        for name, p in record.artifact_paths.items()
    }
    persisted_record = replace(record, artifact_paths=relative_paths)
    entry = store_run_evidence(store, persisted_record)
    return RunOutcome(memory_entry=entry, artifact_dir=artifact_dir)
