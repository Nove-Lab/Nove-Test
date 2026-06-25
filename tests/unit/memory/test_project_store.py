"""Unit tests for `novetest.memory.project_store`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.memory.project_store import (
    ENV_NOVETEST_HOME,
    STORE_DIRNAME,
    STORE_METADATA_FILENAME,
    ProjectStore,
    ProjectStoreCorruptError,
    ProjectStoreNotFoundError,
    WipeReport,
    create_project_store,
    get_project_store_state,
    locate_project_store,
    wipe_project_store,
)


EXPECTED_SUBDIRS: tuple[str, ...] = (
    "blobs",
    "memory/runs",
    "memory/tombstones",
    "run",
    "coverage",
    "regression",
    "localization",
    "replay",
    "orchestration",
)


def test_create_writes_full_skeleton(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)

    assert store.path == tmp_path / STORE_DIRNAME
    assert store.store_state == "ready"
    assert store.schema_version == 1
    assert (store.path / STORE_METADATA_FILENAME).is_file()
    for rel in EXPECTED_SUBDIRS:
        assert (store.path / rel).is_dir(), rel


def test_create_metadata_round_trips(tmp_path: Path) -> None:
    handle = create_project_store(tmp_path)
    raw = json.loads((handle.path / STORE_METADATA_FILENAME).read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": 1,
        "initialized_at": handle.initialized_at,
        "store_state": "ready",
    }


def test_create_is_idempotent_preserves_run_records(tmp_path: Path) -> None:
    first = create_project_store(tmp_path)
    # Drop a sentinel under memory/runs/ that init must NOT remove.
    sentinel = first.path / "memory" / "runs" / "2026" / "05" / "13" / "run_TEST"
    sentinel.mkdir(parents=True)
    (sentinel / "record.json").write_text('{"sentinel": true}\n', encoding="utf-8")
    original_initialized_at = first.initialized_at

    second = create_project_store(tmp_path)

    assert second == first
    assert second.initialized_at == original_initialized_at  # not overwritten
    assert (sentinel / "record.json").read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_create_completes_partial_skeleton(tmp_path: Path) -> None:
    # Half-initialized: .novetest/ exists but no store.json — recoverable.
    (tmp_path / STORE_DIRNAME).mkdir()
    handle = create_project_store(tmp_path)
    assert (handle.path / STORE_METADATA_FILENAME).is_file()
    for rel in EXPECTED_SUBDIRS:
        assert (handle.path / rel).is_dir(), rel


def test_create_rejects_missing_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError):
        create_project_store(missing)


def test_locate_finds_in_current_dir(tmp_path: Path) -> None:
    create_project_store(tmp_path)
    handle = locate_project_store(tmp_path, env={})
    assert handle is not None
    assert handle.path == tmp_path / STORE_DIRNAME


def test_locate_walks_upward(tmp_path: Path) -> None:
    create_project_store(tmp_path)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    handle = locate_project_store(deep, env={})
    assert handle is not None
    assert handle.path == tmp_path / STORE_DIRNAME


def test_locate_stops_at_first_match(tmp_path: Path) -> None:
    # Outer store + inner store; the walk should stop at the inner one.
    outer = create_project_store(tmp_path)
    inner_workspace = tmp_path / "nested"
    inner_workspace.mkdir()
    inner = create_project_store(inner_workspace)
    handle = locate_project_store(inner_workspace, env={})
    assert handle is not None
    assert handle.path == inner.path
    assert handle.path != outer.path


def test_locate_returns_none_when_uninitialized(tmp_path: Path) -> None:
    assert locate_project_store(tmp_path, env={}) is None


def test_locate_honors_novetest_home_env(tmp_path: Path) -> None:
    pinned_workspace = tmp_path / "pinned"
    pinned_workspace.mkdir()
    pinned = create_project_store(pinned_workspace)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    handle = locate_project_store(elsewhere, env={ENV_NOVETEST_HOME: str(pinned.path)})
    assert handle is not None
    assert handle.path == pinned.path


def test_locate_with_invalid_novetest_home_returns_none(tmp_path: Path) -> None:
    bogus = tmp_path / "does-not-exist"
    assert locate_project_store(tmp_path, env={ENV_NOVETEST_HOME: str(bogus)}) is None


def test_get_state_reads_metadata(tmp_path: Path) -> None:
    created = create_project_store(tmp_path)
    state = get_project_store_state(created.path)
    assert state == created


def test_get_state_on_corrupt_json_raises(tmp_path: Path) -> None:
    handle = create_project_store(tmp_path)
    (handle.path / STORE_METADATA_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(ProjectStoreCorruptError):
        get_project_store_state(handle.path)


def test_get_state_on_missing_metadata_raises(tmp_path: Path) -> None:
    (tmp_path / STORE_DIRNAME).mkdir()
    with pytest.raises(ProjectStoreCorruptError):
        get_project_store_state(tmp_path / STORE_DIRNAME)


def test_handle_is_frozen(tmp_path: Path) -> None:
    handle = create_project_store(tmp_path)
    with pytest.raises(AttributeError):
        handle.store_state = "different"  # type: ignore[misc]


def test_handle_to_dict_shape(tmp_path: Path) -> None:
    handle = create_project_store(tmp_path)
    payload = handle.to_dict()
    assert payload == {
        "schema_version": 1,
        "store_path": str(handle.path),
        "initialized_at": handle.initialized_at,
        "store_state": "ready",
    }


# --- wipe_project_store ------------------------------------------------------
#
# Coverage for the destructive primitive specified by
# `agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md`
# and `agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md`.
# The atomicity sequence (count → rename → rmtree) is load-bearing; tests pin
# each branch of it.


def _seed_artifact(path: Path, body: str = "{}\n") -> None:
    """Materialize a terminal artifact file (and parents) for counting tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_wipe_happy_path_returns_report_and_deletes_tree(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    # One fake run + one fake coverage fact (the task brief's minimum population).
    _seed_artifact(
        store.path / "memory" / "runs" / "2026" / "06" / "24" / "run_TEST" / "record.json"
    )
    _seed_artifact(
        store.path / "coverage" / "facts" / "run_TEST" / "coverage_facts.json"
    )

    report = wipe_project_store(store.path)

    assert isinstance(report, WipeReport)
    assert report.store_path == store.path
    assert report.previous_initialized_at == store.initialized_at
    assert report.items_removed == {
        "runs": 1,
        "tombstones": 0,
        "coverage_facts": 1,
        "regression_pairs": 0,
        "localization_findings": 0,
        "replay_results": 0,
    }
    # Live store path is gone; the staging dir (rmtree's target) is gone too.
    assert not store.path.exists()
    staging_orphans = list(tmp_path.glob(".novetest.deleting.*"))
    assert staging_orphans == []


def test_wipe_refuses_when_store_missing(tmp_path: Path) -> None:
    missing = tmp_path / ".novetest"
    with pytest.raises(ProjectStoreNotFoundError):
        wipe_project_store(missing)


def test_wipe_refuses_when_metadata_missing(tmp_path: Path) -> None:
    # Directory exists but `store.json` does not — a "partial init" shape that
    # `create_project_store` is allowed to complete, but `wipe_project_store`
    # MUST refuse so an unrelated empty `.novetest/` can never be auto-wiped.
    store_path = tmp_path / STORE_DIRNAME
    store_path.mkdir()
    with pytest.raises(ProjectStoreNotFoundError):
        wipe_project_store(store_path)
    # Directory left untouched on refusal.
    assert store_path.is_dir()


def test_wipe_refuses_corrupt_store(tmp_path: Path) -> None:
    # Load-bearing safety property: a corrupt `store.json` MUST NOT trigger
    # auto-wipe. The decision doc pins this — a transient FS issue is the
    # likely cause and the operator must inspect manually.
    store = create_project_store(tmp_path)
    (store.path / STORE_METADATA_FILENAME).write_text("not json", encoding="utf-8")

    with pytest.raises(ProjectStoreCorruptError):
        wipe_project_store(store.path)

    # Live store still present after refusal — atomicity guarantee.
    assert store.path.is_dir()
    assert (store.path / STORE_METADATA_FILENAME).is_file()


def test_wipe_rmtree_failure_leaves_staging_orphan_not_live_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Atomicity property: after the single `rename` succeeds, the live store
    # is detached. If `rmtree` raises, we surface the failure WITHOUT trying
    # to undo the rename — the orphaned staging dir is acceptable, a
    # half-deleted live store would not be.
    store = create_project_store(tmp_path)
    _seed_artifact(
        store.path / "memory" / "runs" / "2026" / "06" / "24" / "run_TEST" / "record.json"
    )

    def boom(path: Path, ignore_errors: bool = False) -> None:  # noqa: ARG001
        raise OSError("simulated rmtree failure")

    monkeypatch.setattr(
        "novetest.memory.project_store.shutil.rmtree", boom
    )

    with pytest.raises(OSError, match="simulated rmtree failure"):
        wipe_project_store(store.path)

    assert not store.path.exists(), "live store path must be detached"
    orphans = list(tmp_path.glob(".novetest.deleting.*"))
    assert len(orphans) == 1, orphans
    # Orphan still holds the data — proves we did not partial-delete it.
    assert (orphans[0] / STORE_METADATA_FILENAME).is_file()
    # No manual cleanup: `project_store.shutil` IS the same module object as
    # any `shutil` imported here, so calling `shutil.rmtree` while the patch
    # is in effect would re-trigger `boom`. The future `vacuum` verb is the
    # intended sweep mechanism for orphans by name pattern (deferred per the
    # decision doc §"Out of scope"); `tmp_path` teardown handles us here.


def test_wipe_then_create_project_store_succeeds(tmp_path: Path) -> None:
    # Round-trip: wiping must leave the workspace in a state where the next
    # `create_project_store(workspace)` cleanly rebuilds the skeleton. This
    # pins the post-MVP `reset` verb's "wipe then re-init" contract — the
    # primitive itself does not re-init; that's the Orchestration workflow's
    # responsibility.
    first = create_project_store(tmp_path)
    first_initialized_at = first.initialized_at

    wipe_project_store(first.path)

    rebuilt = create_project_store(tmp_path)
    assert rebuilt.path == first.path
    assert rebuilt.store_state == "ready"
    assert (rebuilt.path / STORE_METADATA_FILENAME).is_file()
    for rel in EXPECTED_SUBDIRS:
        assert (rebuilt.path / rel).is_dir(), rel
    # New stamp — not the old one (sanity check that we didn't somehow
    # resurrect the previous metadata).
    assert rebuilt.initialized_at >= first_initialized_at
