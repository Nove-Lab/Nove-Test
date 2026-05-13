"""Python-API integration tests for the Phase 1 orchestration workflows.

These exercise `initialize_project_workspace` → `run_target_in_store` →
`list_run_history` / `retrieve_run_evidence` / `delete_run_evidence` end
to end against the real fixture projects. CLI-level (subprocess) coverage
lives in `test_cli_lifecycle.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.memory import (
    delete_run_evidence,
    list_run_history,
    locate_project_store,
    retrieve_run_evidence,
)
from novetest.orchestration.workflows import (
    build_status_view,
    initialize_project_workspace,
    run_target_in_store,
)
from novetest.run import EngineNotReadyError


async def test_init_creates_store_skeleton_and_reports_readiness(
    basic_workspace: Path,
) -> None:
    result = await initialize_project_workspace(basic_workspace)
    assert result.store.path == basic_workspace / ".novetest"
    assert result.store.store_state == "ready"
    # Engine sub-directories are pre-created so peer engines don't race on mkdir.
    for subdir in (
        "memory/runs",
        "memory/tombstones",
        "run",
        "coverage",
        "regression",
        "localization",
        "replay",
        "orchestration",
        "blobs",
    ):
        assert (result.store.path / subdir).is_dir(), subdir
    assert result.engine_readiness.state == "ready"
    assert result.engine_readiness.engine_context is not None
    assert result.engine_readiness.engine_context.engine_name == "pytest"


async def test_init_against_empty_workspace_is_engine_missing(
    empty_workspace: Path,
) -> None:
    result = await initialize_project_workspace(empty_workspace)
    # Store is created regardless — readiness is informational.
    assert result.store.path == empty_workspace / ".novetest"
    assert result.store.store_state == "ready"
    assert result.engine_readiness.state == "engine-missing"


async def test_init_is_idempotent(basic_workspace: Path) -> None:
    first = await initialize_project_workspace(basic_workspace)
    second = await initialize_project_workspace(basic_workspace)
    assert first.store == second.store


async def test_init_preserves_existing_run_evidence(basic_workspace: Path) -> None:
    """Re-running init must not destroy pre-existing records (REQ-MEM-006)."""

    init = await initialize_project_workspace(basic_workspace)
    outcome = await run_target_in_store("", init.store, timeout=60.0)
    run_id = outcome.memory_entry.run_record.run_reference.run_id

    # Re-init exactly as a returning user would.
    await initialize_project_workspace(basic_workspace)

    history = list_run_history(init.store)
    assert len(history) == 1
    assert history[0].run_record.run_reference.run_id == run_id


async def test_run_target_persists_record_and_native_artifacts(
    basic_workspace: Path,
) -> None:
    init = await initialize_project_workspace(basic_workspace)
    outcome = await run_target_in_store("", init.store, timeout=60.0)

    record = outcome.memory_entry.run_record
    assert record.status == "passed"
    assert record.summary_counts.get("passed") == 3

    # `artifact_paths` should be Project-Store-relative on the persisted record.
    for relative in record.artifact_paths.values():
        assert not Path(relative).is_absolute(), relative
        assert (init.store.path / relative).is_file(), relative

    # `record.json` is laid down under the date-bucketed run directory.
    run_id = record.run_reference.run_id
    record_file = next(
        (init.store.path / "memory" / "runs").rglob(f"run_{run_id}/record.json"),
        None,
    )
    assert record_file is not None
    assert record_file.is_file()


async def test_run_failing_workspace_records_failure(failing_workspace: Path) -> None:
    init = await initialize_project_workspace(failing_workspace)
    outcome = await run_target_in_store("", init.store, timeout=60.0)
    record = outcome.memory_entry.run_record
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_reference is not None


async def test_run_short_circuits_for_empty_workspace(empty_workspace: Path) -> None:
    init = await initialize_project_workspace(empty_workspace)
    with pytest.raises(EngineNotReadyError) as exc_info:
        await run_target_in_store("", init.store, timeout=10.0)
    assert exc_info.value.readiness.state == "engine-missing"
    # The artifact directory is never created because run/execute raises
    # before the adapter can touch the filesystem.
    artifacts_root = init.store.path / "run" / "artifacts"
    if artifacts_root.exists():
        assert not any(artifacts_root.iterdir())


async def test_memory_list_returns_persisted_entry(basic_workspace: Path) -> None:
    init = await initialize_project_workspace(basic_workspace)
    outcome = await run_target_in_store("", init.store, timeout=60.0)
    history = list_run_history(init.store)
    assert len(history) == 1
    assert (
        history[0].run_record.run_reference.run_id
        == outcome.memory_entry.run_record.run_reference.run_id
    )


async def test_memory_show_then_delete_tombstones(basic_workspace: Path) -> None:
    init = await initialize_project_workspace(basic_workspace)
    outcome = await run_target_in_store("", init.store, timeout=60.0)
    ref = outcome.memory_entry.run_record.run_reference

    shown = retrieve_run_evidence(init.store, ref)
    assert shown.tombstoned_at is None
    assert shown.run_record.status == "passed"

    deleted = delete_run_evidence(init.store, ref)
    assert deleted.tombstoned_at is not None
    assert deleted.run_record.status == "tombstoned"

    # The Run Reference is still resolvable after tombstoning (Evidence Citation
    # invariant from foundations.md §4).
    resurfaced = retrieve_run_evidence(init.store, ref)
    assert resurfaced.tombstoned_at is not None


async def test_status_view_reflects_latest_run(basic_workspace: Path) -> None:
    init = await initialize_project_workspace(basic_workspace)
    empty_view = build_status_view(init.store)
    assert empty_view.run_history_size == 0
    assert empty_view.latest_entry is None

    await run_target_in_store("", init.store, timeout=60.0)
    view = build_status_view(init.store)
    assert view.run_history_size == 1
    assert view.latest_entry is not None
    assert view.coverage_available is False  # Phase 1: no derived facts
    assert view.replay_available is False


async def test_locate_finds_store_from_subdirectory(basic_workspace: Path) -> None:
    await initialize_project_workspace(basic_workspace)
    nested = basic_workspace / "tests"
    located = locate_project_store(nested)
    assert located is not None
    assert located.path == basic_workspace / ".novetest"


async def test_locate_returns_none_when_no_ancestor_store(tmp_path: Path) -> None:
    workspace = tmp_path / "outside"
    workspace.mkdir()
    assert locate_project_store(workspace, env={}) is None
