"""``novetest run`` workflow: execute target in workspace + persist to Memory.

Wires `run/execute` to `memory/store_run_evidence` exactly as
`design/workflows/run.md` §1 prescribes. Pre-generates the ULID so Run's
adapter writes Native artifacts directly under
``<store>/run/artifacts/run_<ulid>/native/``; this lets us hand Memory a
RunRecord with already-Project-Store-relative ``artifact_paths`` and skip
a post-run file move.

When ``collect_coverage=True`` is requested, after a successful persist
the workflow calls ``coverage/derive_coverage_facts`` so the
``coverage_facts.json`` lands on disk at the contract-frozen path and
Memory's ``has_coverage_facts`` flag auto-flips on subsequent reads. The
derive call returns either a ``CoverageFactSet`` (success) or a
``CoverageUnavailable`` value (REQ-COV-004) — both are forwarded on the
``RunOutcome`` for the CLI handler to format into the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from novetest.coverage import CoverageUnavailable, derive_coverage_facts
from novetest.memory import ProjectStore, retrieve_run_evidence, store_run_evidence
from novetest.models import MemoryEntry
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.run import execute, resolve_test_target
from novetest.utils.ulid import generate_ulid


@dataclass(slots=True, frozen=True)
class RunOutcome:
    """Result of the run-and-persist workflow.

    ``coverage_outcome`` is ``None`` when ``collect_coverage`` was not
    requested. Otherwise it carries either a ``CoverageFactSet`` (success)
    or a ``CoverageUnavailable`` (the run completed but Coverage could not
    derive facts — e.g. the native payload was missing or corrupt). The
    CLI handler discriminates with ``isinstance`` to emit the envelope's
    ``coverage_outcome`` block.
    """

    memory_entry: MemoryEntry
    artifact_dir: Path
    coverage_outcome: CoverageFactSet | CoverageUnavailable | None = None


async def run_target_in_store(
    target_expression: str,
    store: ProjectStore,
    *,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> RunOutcome:
    """Resolve target → execute → persist (→ optionally derive coverage facts).

    The workspace path is the parent of ``store.path`` (i.e. the directory
    that contains ``.novetest/``). ``target_expression`` is the user-facing
    string from the CLI; resolution into file/directory/nodeid happens here.

    When ``collect_coverage=True``, the adapter is invoked with coverage
    instrumentation and the workflow follows up with
    ``coverage/derive_coverage_facts`` after persisting the Run Record so
    the resulting ``coverage_facts.json`` lands at
    ``<store>/coverage/facts/run_<id>/coverage_facts.json``. The
    ``RunOutcome.memory_entry`` is then refreshed via
    ``retrieve_run_evidence`` so the returned ``has_coverage_facts`` flag
    reflects the new on-disk state.
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
        collect_coverage=collect_coverage,
    )

    relative_paths = {
        name: str(Path(p).relative_to(store.path))
        for name, p in record.artifact_paths.items()
    }
    persisted_record = replace(record, artifact_paths=relative_paths)
    entry = store_run_evidence(store, persisted_record)

    coverage_outcome: CoverageFactSet | CoverageUnavailable | None = None
    if collect_coverage:
        coverage_outcome = derive_coverage_facts(store, persisted_record.run_reference)
        # Re-read the Memory Entry so ``has_coverage_facts`` reflects the
        # filesystem state after the (possibly successful) derive call.
        entry = retrieve_run_evidence(store, persisted_record.run_reference)

    return RunOutcome(
        memory_entry=entry,
        artifact_dir=artifact_dir,
        coverage_outcome=coverage_outcome,
    )
