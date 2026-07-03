"""Unit tests for `novetest.memory.project_store`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.memory.project_store import (
    ENV_NOVETEST_HOME,
    STORE_DIRNAME,
    STORE_METADATA_FILENAME,
    PinnedEngine,
    ProjectStore,
    ProjectStoreCorruptError,
    ProjectStoreNotFoundError,
    WipeReport,
    create_project_store,
    find_nearest_store,
    get_pinned_engine,
    get_project_store_state,
    locate_project_store,
    set_pinned_engine,
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
        "pinned_engine": None,
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


# --- engine pin (anchored-pin decision D1/D6) --------------------------------
#
# Coverage for the optional `pinned_engine` store.json field and its get/set
# accessors, specified by `agent-comms/decisions/2026-07-03-engine-selection-
# policy.md` and `agent-comms/tasks/memory-team-2026-07-03-engine-pin-store-
# primitives.md`. Load-bearing properties: legacy stores load as None with NO
# rewrite; malformation is corruption (never silent None); pair validation is
# write-time only.


def _metadata_bytes(store_path: Path) -> bytes:
    return (store_path / STORE_METADATA_FILENAME).read_bytes()


def test_pin_round_trip(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    set_pinned_engine(store, "python", "pytest")

    assert get_pinned_engine(store) == PinnedEngine(
        ecosystem="python", engine_name="pytest"
    )
    # Persisted shape is the decision-doc pinned object, nested in store.json.
    raw = json.loads(_metadata_bytes(store.path))
    assert raw["pinned_engine"] == {"ecosystem": "python", "engine_name": "pytest"}
    # The other metadata fields survived the rewrite.
    assert raw["schema_version"] == 1
    assert raw["initialized_at"] == store.initialized_at
    assert raw["store_state"] == "ready"


def test_repin_overwrites_in_place_and_preserves_run_history(tmp_path: Path) -> None:
    # Decision D1: re-running `init --engine <other>` re-pins IN PLACE — same
    # store, pin updated, run history retained. Mixed-engine histories are
    # legitimate (e.g. Rust + PyO3 roots).
    store = create_project_store(tmp_path)
    sentinel = store.path / "memory" / "runs" / "2026" / "07" / "03" / "run_TEST"
    sentinel.mkdir(parents=True)
    (sentinel / "record.json").write_text('{"sentinel": true}\n', encoding="utf-8")

    set_pinned_engine(store, "python", "pytest")
    set_pinned_engine(store, "rust", "cargo-test")

    assert get_pinned_engine(store) == PinnedEngine(
        ecosystem="rust", engine_name="cargo-test"
    )
    assert (sentinel / "record.json").read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_fresh_store_has_no_pin_key_and_loads_none(tmp_path: Path) -> None:
    # `create_project_store` never pins — pinning is the init workflow's
    # explicit act (D1), via the setter. The key is absent, not null.
    store = create_project_store(tmp_path)
    raw = json.loads(_metadata_bytes(store.path))
    assert "pinned_engine" not in raw
    assert get_pinned_engine(store) is None
    assert store.pinned_engine is None


def test_legacy_store_loads_none_without_rewrite(tmp_path: Path) -> None:
    # A pre-pin store.json (exactly the three historical keys) must load with
    # pinned_engine=None and stay BYTE-IDENTICAL across every read path —
    # backfill is Orchestration's D6 flow, never a side effect of loading.
    store_path = tmp_path / STORE_DIRNAME
    store_path.mkdir()
    legacy_payload = {
        "schema_version": 1,
        "initialized_at": 1750000000000,
        "store_state": "ready",
    }
    (store_path / STORE_METADATA_FILENAME).write_text(
        json.dumps(legacy_payload, indent=2) + "\n", encoding="utf-8"
    )
    before = _metadata_bytes(store_path)

    handle = get_project_store_state(store_path)
    assert handle.pinned_engine is None
    assert get_pinned_engine(handle) is None
    located = locate_project_store(tmp_path, env={})
    assert located is not None and located.pinned_engine is None
    recreated = create_project_store(tmp_path)  # idempotent path
    assert recreated.pinned_engine is None

    assert _metadata_bytes(store_path) == before


def test_set_pinned_engine_rejects_unsupported_pair(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    before = _metadata_bytes(store.path)

    # Mismatched but individually valid halves.
    with pytest.raises(ValueError, match="Unsupported"):
        set_pinned_engine(store, "python", "jest")
    # Entirely unknown pair.
    with pytest.raises(ValueError, match="Unsupported"):
        set_pinned_engine(store, "fortran", "ftest")

    # Refusal happens before any disk mutation.
    assert _metadata_bytes(store.path) == before


def test_set_pinned_engine_accepts_all_six_supported_pairs(tmp_path: Path) -> None:
    # The setter validates against Run's canonical list (single source of
    # truth); this pins that all six REQ-RUN-006 pairs pass.
    from novetest.run.engine_selector import list_supported_engine_pairs

    store = create_project_store(tmp_path)
    for ecosystem, engine_name in list_supported_engine_pairs():
        set_pinned_engine(store, ecosystem, engine_name)
        assert get_pinned_engine(store) == PinnedEngine(
            ecosystem=ecosystem, engine_name=engine_name
        )


def test_get_pinned_engine_is_disk_authoritative_over_stale_handle(
    tmp_path: Path,
) -> None:
    # The handle is frozen; a handle loaded before a set must still observe
    # the new pin through the accessor (reads go to disk, not the field).
    stale = create_project_store(tmp_path)
    set_pinned_engine(stale, "go", "go-test")
    assert stale.pinned_engine is None  # frozen snapshot, unchanged
    assert get_pinned_engine(stale) == PinnedEngine(
        ecosystem="go", engine_name="go-test"
    )


def test_malformed_pin_is_corrupt_not_none(tmp_path: Path) -> None:
    # Silent-None on malformation would trigger a silent D6 re-detect that
    # overwrites user intent — so malformation is corruption, loudly.
    store = create_project_store(tmp_path)
    metadata_path = store.path / STORE_METADATA_FILENAME
    base = json.loads(metadata_path.read_text(encoding="utf-8"))

    for bad_pin in ("pytest", ["python", "pytest"], {"ecosystem": "python"}):
        payload = {**base, "pinned_engine": bad_pin}
        metadata_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with pytest.raises(ProjectStoreCorruptError, match="pinned_engine"):
            get_project_store_state(store.path)
        with pytest.raises(ProjectStoreCorruptError, match="pinned_engine"):
            get_pinned_engine(store)


def test_wellformed_unknown_pin_loads_tolerantly(tmp_path: Path) -> None:
    # Forward tolerance: a store pinned by a NEWER novetest to a 7th engine
    # must not read as corrupt here — pair validation is write-time only;
    # dispatch is where an unknown engine fails, with a better error.
    store = create_project_store(tmp_path)
    metadata_path = store.path / STORE_METADATA_FILENAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["pinned_engine"] = {"ecosystem": "zig", "engine_name": "zig-test"}
    metadata_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert get_pinned_engine(store) == PinnedEngine(
        ecosystem="zig", engine_name="zig-test"
    )


def test_set_pinned_engine_on_corrupt_store_raises(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    (store.path / STORE_METADATA_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(ProjectStoreCorruptError):
        set_pinned_engine(store, "python", "pytest")


def test_pinned_handle_to_dict_includes_pin(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    set_pinned_engine(store, "javascript-typescript", "jest")
    reloaded = get_project_store_state(store.path)
    assert reloaded.to_dict()["pinned_engine"] == {
        "ecosystem": "javascript-typescript",
        "engine_name": "jest",
    }


# --- find_nearest_store (decision D2 walk-up) --------------------------------
#
# The pure upward-walk primitive underneath verb-level anchor resolution.
# `locate_project_store` delegates its walk here, so the locate tests above
# double as divergence guards; these pin the Path-returning surface itself.


def test_find_nearest_store_found_at_start(tmp_path: Path) -> None:
    create_project_store(tmp_path)
    assert find_nearest_store(tmp_path) == tmp_path.resolve()


def test_find_nearest_store_found_at_depth(tmp_path: Path) -> None:
    create_project_store(tmp_path)
    deep = tmp_path / "src" / "pkg" / "sub"
    deep.mkdir(parents=True)
    assert find_nearest_store(deep) == tmp_path.resolve()


def test_find_nearest_store_not_found_returns_none(tmp_path: Path) -> None:
    # No store anywhere on the walk from tmp_path to / (same hermeticity
    # assumption as test_locate_returns_none_when_uninitialized above).
    assert find_nearest_store(tmp_path) is None


def test_find_nearest_store_nearest_wins(tmp_path: Path) -> None:
    # D2 / Open Q #17 resolution: nested stores → nearest wins, no
    # multi-store semantics.
    create_project_store(tmp_path)
    inner_workspace = tmp_path / "nested"
    inner_workspace.mkdir()
    create_project_store(inner_workspace)
    start = inner_workspace / "src"
    start.mkdir()
    assert find_nearest_store(start) == inner_workspace.resolve()


def test_find_nearest_store_walks_past_metadata_less_novetest_dir(
    tmp_path: Path,
) -> None:
    # A `.novetest/` without store.json (partial-init crash shape) is not a
    # store — same predicate `locate_project_store` has always used.
    create_project_store(tmp_path)
    inner_workspace = tmp_path / "nested"
    (inner_workspace / STORE_DIRNAME).mkdir(parents=True)
    assert find_nearest_store(inner_workspace) == tmp_path.resolve()


def test_find_nearest_store_finds_corrupt_store_and_load_raises(
    tmp_path: Path,
) -> None:
    # Consistent with existing conventions: discovery matches on store.json
    # PRESENCE (no parsing), so a corrupt store is found — and then errors
    # loudly at load instead of being silently shadowed by an ancestor store.
    create_project_store(tmp_path)  # valid ancestor that must NOT win
    inner_workspace = tmp_path / "nested"
    inner_store = inner_workspace / STORE_DIRNAME
    inner_store.mkdir(parents=True)
    (inner_store / STORE_METADATA_FILENAME).write_text("not json", encoding="utf-8")

    anchor = find_nearest_store(inner_workspace)
    assert anchor == inner_workspace.resolve()
    with pytest.raises(ProjectStoreCorruptError):
        get_project_store_state(anchor / STORE_DIRNAME)


def test_find_nearest_store_from_file_start_walks_from_parent(tmp_path: Path) -> None:
    create_project_store(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    module = src / "module.py"
    module.write_text("x = 1\n", encoding="utf-8")
    assert find_nearest_store(module) == tmp_path.resolve()
