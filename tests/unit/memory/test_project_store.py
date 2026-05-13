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
    create_project_store,
    get_project_store_state,
    locate_project_store,
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
