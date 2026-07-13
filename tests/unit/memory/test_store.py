"""Unit tests for `novetest.memory.store`."""

from __future__ import annotations

import itertools
import json
import os
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from novetest.memory import store as store_module
from novetest.memory.project_store import (
    STORE_METADATA_FILENAME,
    ProjectStore,
    ProjectStoreCorruptError,
    ProjectStoreNotFoundError,
    create_project_store,
)
from novetest.memory.store import (
    RECORD_FILENAME,
    RUN_DIR_PREFIX,
    RunEvidenceAlreadyExistsError,
    RunEvidenceNotFoundError,
    SkippedRecord,
    delete_run_evidence,
    find_runs_for_target,
    get_memory_entry_availability,
    list_run_history,
    retrieve_run_evidence,
    store_run_evidence,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# 2024-01-02T00:00:00Z and 2026-05-13T10:30:00Z, hand-picked for stable date paths.
TS_2024_01_02 = 1_704_153_600_000
TS_2026_05_13 = 1_778_668_200_000


def _record(
    *,
    run_id: str = "01HXYZ",
    created_at: int = TS_2024_01_02,
    target_expression: str = "tests/test_foo.py",
    status: str = "passed",
) -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=created_at),
        target_expression=target_expression,
        target_type="file",
        engine_name="pytest",
        engine_version="8.2.1",
        ecosystem="python",
        status=status,
        started_at=created_at,
        completed_at=created_at + 250,
        summary_counts={"passed": 1, "failed": 0},
        test_results=(
            TestResult(node_id=f"{target_expression}::test_a", outcome="passed", duration_ms=4),
        ),
        artifact_paths={
            "pytest_json": f"run/artifacts/run_{run_id}/native/pytest-report.json"
        },
        metadata={"cwd": "/tmp/proj"},
    )


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return create_project_store(tmp_path)


def test_store_writes_record_under_ulid_date_path(store: ProjectStore) -> None:
    record = _record(run_id="01HXYZ", created_at=TS_2024_01_02)
    entry = store_run_evidence(store, record)

    expected_dir = (
        store.path / "memory" / "runs" / "2024" / "01" / "02" / f"{RUN_DIR_PREFIX}01HXYZ"
    )
    assert (expected_dir / RECORD_FILENAME).is_file()
    assert entry.entry_id == "01HXYZ"
    assert entry.run_record == record
    assert entry.tombstoned_at is None
    # Availability flags for derived facts are all False until peer engines write.
    assert entry.has_coverage_facts is False
    assert entry.has_regression_facts is False
    assert entry.has_localization_findings is False
    assert entry.has_replay_result is False


def test_store_round_trips_through_disk(store: ProjectStore) -> None:
    record = _record()
    entry = store_run_evidence(store, record)
    persisted_path = (
        store.path / "memory" / "runs" / "2024" / "01" / "02" / f"{RUN_DIR_PREFIX}01HXYZ"
        / RECORD_FILENAME
    )
    raw = json.loads(persisted_path.read_text(encoding="utf-8"))
    # The persisted document is the caller's record plus Memory's MEM-04
    # `stored_at` stamp — no other key is added, dropped, or rewritten.
    assert raw == {**record.to_dict(), "stored_at": entry.stored_at}


def test_store_refuses_to_overwrite(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    with pytest.raises(RunEvidenceAlreadyExistsError):
        store_run_evidence(store, record)


def test_retrieve_returns_stored_entry(store: ProjectStore) -> None:
    record = _record(run_id="01ABC", created_at=TS_2026_05_13)
    stored = store_run_evidence(store, record)
    fetched = retrieve_run_evidence(store, record.run_reference)
    assert fetched.entry_id == stored.entry_id
    assert fetched.run_record == record
    assert fetched.tombstoned_at is None


def test_retrieve_unknown_run_raises(store: ProjectStore) -> None:
    ghost = RunReference(run_id="01NOPE", created_at=TS_2024_01_02)
    with pytest.raises(RunEvidenceNotFoundError):
        retrieve_run_evidence(store, ghost)


def test_list_history_is_newest_first(store: ProjectStore) -> None:
    early = _record(run_id="01EARLY", created_at=TS_2024_01_02)
    late = _record(run_id="01LATE", created_at=TS_2026_05_13)
    store_run_evidence(store, early)
    store_run_evidence(store, late)

    entries = list_run_history(store)
    assert [e.entry_id for e in entries] == ["01LATE", "01EARLY"]


def test_list_history_empty_on_fresh_store(store: ProjectStore) -> None:
    assert list_run_history(store) == []


def test_list_history_includes_tombstoned(store: ProjectStore) -> None:
    live = _record(run_id="01LIVE", created_at=TS_2024_01_02)
    gone = _record(run_id="01GONE", created_at=TS_2026_05_13)
    store_run_evidence(store, live)
    store_run_evidence(store, gone)
    delete_run_evidence(store, gone.run_reference)

    entries = list_run_history(store)
    assert {e.entry_id for e in entries} == {"01LIVE", "01GONE"}
    tombstoned = next(e for e in entries if e.entry_id == "01GONE")
    assert tombstoned.tombstoned_at is not None
    assert tombstoned.run_record.status == "tombstoned"


def test_delete_moves_dir_to_tombstones(store: ProjectStore) -> None:
    record = _record(run_id="01ABC", created_at=TS_2024_01_02)
    store_run_evidence(store, record)

    live_dir = (
        store.path / "memory" / "runs" / "2024" / "01" / "02" / f"{RUN_DIR_PREFIX}01ABC"
    )
    assert live_dir.is_dir()

    delete_run_evidence(store, record.run_reference)

    assert not live_dir.exists()
    tomb = store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01ABC"
    assert (tomb / RECORD_FILENAME).is_file()


def test_delete_marks_record_tombstoned(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    entry = delete_run_evidence(store, record.run_reference)

    assert entry.tombstoned_at is not None
    assert entry.run_record.status == "tombstoned"
    assert entry.run_record.metadata["tombstoned_at"] == entry.tombstoned_at


def test_delete_then_retrieve_still_resolves(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    delete_run_evidence(store, record.run_reference)

    refetched = retrieve_run_evidence(store, record.run_reference)
    assert refetched.entry_id == record.run_reference.run_id
    assert refetched.tombstoned_at is not None
    assert refetched.run_record.status == "tombstoned"


def test_delete_is_idempotent(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    first = delete_run_evidence(store, record.run_reference)
    second = delete_run_evidence(store, record.run_reference)

    assert first.tombstoned_at == second.tombstoned_at
    assert first.run_record == second.run_record


def test_delete_unknown_run_raises(store: ProjectStore) -> None:
    ghost = RunReference(run_id="01NOPE", created_at=TS_2024_01_02)
    with pytest.raises(RunEvidenceNotFoundError):
        delete_run_evidence(store, ghost)


# --- MEM-02: tombstone atomicity (mutate-then-single-rename) ------------------
#
# `delete_run_evidence` materializes the fully-tombstoned `record.json` at the
# LIVE location first, then moves the directory with ONE atomic `Path.rename`.
# These tests crash the process at the rename boundary and pin the write order,
# proving no crash can strand a permanently invariant-violating tombstone
# (`status` original + `tombstoned_at=None` at the tombstone location, which the
# re-delete no-op used to make permanent). The `move_then_crash` / order-pin
# tests fail against the old rename-then-write module (A/B honesty check).


def test_delete_crash_at_rename_is_not_a_permanent_partial_state(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash the instant the tombstone move completes must not strand an
    invariant-violating tombstone.

    Reproduces the MEM-02 window: the directory move to ``tombstones/`` has
    completed but the process dies before returning. Under mutate-then-single-
    rename the moved record is ALREADY fully tombstoned, so a re-issued delete
    (a no-op on the now-tombstoned run) reports a valid entry — ``status ==
    "tombstoned"`` AND non-null ``tombstoned_at``. Under the OLD rename-then-
    write order the moved record still carried the original status with
    ``tombstoned_at=None`` and the re-delete no-op made that permanent, so this
    test FAILS there (A/B proof).
    """
    record = _record(run_id="01CRASH", created_at=TS_2024_01_02)
    store_run_evidence(store, record)

    real_rename = Path.rename

    def move_then_crash(self: Path, target: Path) -> Path:
        real_rename(self, target)
        raise OSError("simulated crash immediately after the tombstone move")

    monkeypatch.setattr(Path, "rename", move_then_crash)
    with pytest.raises(OSError):
        delete_run_evidence(store, record.run_reference)

    # The move happened; the record now lives in the tombstone location. A
    # re-issued delete must expose a valid tombstone, not a phantom one.
    monkeypatch.setattr(Path, "rename", real_rename)
    healed = delete_run_evidence(store, record.run_reference)
    assert healed.run_record.status == "tombstoned"
    assert healed.tombstoned_at is not None
    assert healed.run_record.metadata["tombstoned_at"] == healed.tombstoned_at

    refetched = retrieve_run_evidence(store, record.run_reference)
    assert refetched.tombstoned_at is not None
    assert refetched.run_record.status == "tombstoned"


def test_delete_crash_before_move_leaves_live_and_self_heals(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the record is stamped but the move never runs, the run stays LIVE and
    a re-issued delete completes cleanly.

    ``Path.rename`` is forced to raise WITHOUT moving anything, so the
    tombstoned ``record.json`` sits at the live location. ``_resolve`` keys
    ``tombstoned`` off *location*, so the run still resolves LIVE (no phantom
    tombstone with a null timestamp), and a re-issued delete does not
    short-circuit — it re-stamps and completes the move, restoring the invariant.
    """
    record = _record(run_id="01LIVEHEAL", created_at=TS_2024_01_02)
    store_run_evidence(store, record)

    def refuse_move(self: Path, target: Path) -> Path:
        raise OSError("simulated crash before the tombstone move")

    monkeypatch.setattr(Path, "rename", refuse_move)
    with pytest.raises(OSError):
        delete_run_evidence(store, record.run_reference)

    live_dir = (
        store.path / "memory" / "runs" / "2024" / "01" / "02"
        / f"{RUN_DIR_PREFIX}01LIVEHEAL"
    )
    tomb_dir = store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01LIVEHEAL"
    assert live_dir.is_dir()
    assert not tomb_dir.exists()
    # The atomic write left no stray temp file behind.
    assert not (live_dir / (RECORD_FILENAME + ".tmp")).exists()
    # Location says live → no invariant-violating tombstone is exposed.
    availability = get_memory_entry_availability(store, record.run_reference)
    assert availability["tombstoned"] is False
    assert retrieve_run_evidence(store, record.run_reference).tombstoned_at is None

    # Self-heal: restore the move and re-issue delete.
    monkeypatch.undo()
    healed = delete_run_evidence(store, record.run_reference)
    assert healed.run_record.status == "tombstoned"
    assert healed.tombstoned_at is not None
    assert not live_dir.exists()
    assert (tomb_dir / RECORD_FILENAME).is_file()


def test_delete_writes_tombstoned_record_before_the_move(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin the write-then-rename order: at the instant the move runs, the source
    ``record.json`` is ALREADY tombstoned.

    A spy wraps ``Path.rename`` and, before performing the real move, reads the
    ``record.json`` at the source (live) directory. Under mutate-then-single-
    rename that content is already ``tombstoned`` with a stamped
    ``tombstoned_at``; under the OLD order it would still be the original status
    (the write happened after the move), so this FAILS there.
    """
    record = _record(run_id="01ORDER", created_at=TS_2024_01_02)
    store_run_evidence(store, record)

    seen: dict[str, object] = {}
    real_rename = Path.rename

    def spy_rename(self: Path, target: Path) -> Path:
        raw = json.loads((self / RECORD_FILENAME).read_text(encoding="utf-8"))
        seen["status"] = raw["status"]
        seen["tombstoned_at"] = raw["metadata"].get("tombstoned_at")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", spy_rename)
    entry = delete_run_evidence(store, record.run_reference)

    assert seen["status"] == "tombstoned"
    assert seen["tombstoned_at"] == entry.tombstoned_at
    # And the delete still completed normally into the tombstone location.
    assert entry.run_record.status == "tombstoned"
    assert entry.tombstoned_at is not None


def test_availability_all_false_after_store(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    avail = get_memory_entry_availability(store, record.run_reference)
    assert avail == {
        "has_coverage_facts": False,
        "has_regression_facts": False,
        "has_localization_findings": False,
        "has_replay_result": False,
        "tombstoned": False,
    }


def test_availability_flips_on_disk_presence(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)

    # Simulate peer engines writing their derived-fact files.
    rid = record.run_reference.run_id
    coverage = store.path / "coverage" / "facts" / f"{RUN_DIR_PREFIX}{rid}"
    coverage.mkdir(parents=True)
    (coverage / "coverage_facts.json").write_text("{}", encoding="utf-8")

    localization = store.path / "localization" / "findings" / f"{RUN_DIR_PREFIX}{rid}"
    localization.mkdir(parents=True)
    (localization / "localization_findings.json").write_text("{}", encoding="utf-8")

    replay = store.path / "replay" / "results" / f"{RUN_DIR_PREFIX}{rid}"
    replay.mkdir(parents=True)
    (replay / "replay_result.json").write_text("{}", encoding="utf-8")

    pair = store.path / "regression" / "pairs" / f"{RUN_DIR_PREFIX}{rid}__run_baseline"
    pair.mkdir(parents=True)
    (pair / "regression_facts.json").write_text("{}", encoding="utf-8")

    avail = get_memory_entry_availability(store, record.run_reference)
    assert avail == {
        "has_coverage_facts": True,
        "has_regression_facts": True,
        "has_localization_findings": True,
        "has_replay_result": True,
        "tombstoned": False,
    }


def test_availability_reports_tombstoned_after_delete(store: ProjectStore) -> None:
    record = _record()
    store_run_evidence(store, record)
    delete_run_evidence(store, record.run_reference)
    avail = get_memory_entry_availability(store, record.run_reference)
    assert avail["tombstoned"] is True


def test_availability_unknown_run_raises(store: ProjectStore) -> None:
    ghost = RunReference(run_id="01NOPE", created_at=TS_2024_01_02)
    with pytest.raises(RunEvidenceNotFoundError):
        get_memory_entry_availability(store, ghost)


# --- find_runs_for_target ----------------------------------------------------


def test_find_runs_for_target_empty_store_returns_empty_list(
    store: ProjectStore,
) -> None:
    result = find_runs_for_target(store, "tests/test_foo.py")
    assert result == []


def test_find_runs_for_target_no_match_returns_empty_list(
    store: ProjectStore,
) -> None:
    store_run_evidence(store, _record(run_id="01A", target_expression="tests/test_a.py"))
    store_run_evidence(store, _record(run_id="01B", target_expression="tests/test_b.py"))
    assert find_runs_for_target(store, "tests/test_missing.py") == []


def test_find_runs_for_target_single_match(store: ProjectStore) -> None:
    target = "tests/test_only.py"
    store_run_evidence(store, _record(run_id="01ONLY", target_expression=target))

    result = find_runs_for_target(store, target)

    assert len(result) == 1
    assert result[0].entry_id == "01ONLY"
    assert result[0].run_record.target_expression == target


def test_find_runs_for_target_returns_newest_first(store: ProjectStore) -> None:
    target = "tests/test_shared.py"
    # Insert in non-chronological order to prove the sort is by created_at,
    # not insertion order.
    store_run_evidence(
        store,
        _record(run_id="01MID", created_at=TS_2024_01_02 + 1_000, target_expression=target),
    )
    store_run_evidence(
        store,
        _record(run_id="01OLD", created_at=TS_2024_01_02, target_expression=target),
    )
    store_run_evidence(
        store,
        _record(run_id="01NEW", created_at=TS_2026_05_13, target_expression=target),
    )

    result = find_runs_for_target(store, target)

    assert [e.entry_id for e in result] == ["01NEW", "01MID", "01OLD"]


def test_find_runs_for_target_filters_out_non_matching(store: ProjectStore) -> None:
    target = "tests/test_shared.py"
    store_run_evidence(store, _record(run_id="01HIT1", target_expression=target))
    store_run_evidence(store, _record(run_id="01MISS", target_expression="tests/other.py"))
    store_run_evidence(
        store,
        _record(run_id="01HIT2", created_at=TS_2026_05_13, target_expression=target),
    )

    result = find_runs_for_target(store, target)

    assert {e.entry_id for e in result} == {"01HIT1", "01HIT2"}
    assert all(e.run_record.target_expression == target for e in result)


def test_find_runs_for_target_excludes_tombstoned_by_default(
    store: ProjectStore,
) -> None:
    target = "tests/test_shared.py"
    live = _record(run_id="01LIVE", target_expression=target)
    gone = _record(run_id="01GONE", created_at=TS_2026_05_13, target_expression=target)
    store_run_evidence(store, live)
    store_run_evidence(store, gone)
    delete_run_evidence(store, gone.run_reference)

    result = find_runs_for_target(store, target)

    assert [e.entry_id for e in result] == ["01LIVE"]


def test_find_runs_for_target_includes_tombstoned_when_opted_in(
    store: ProjectStore,
) -> None:
    target = "tests/test_shared.py"
    live = _record(run_id="01LIVE", target_expression=target)
    gone = _record(run_id="01GONE", created_at=TS_2026_05_13, target_expression=target)
    store_run_evidence(store, live)
    store_run_evidence(store, gone)
    delete_run_evidence(store, gone.run_reference)

    result = find_runs_for_target(store, target, include_tombstoned=True)

    assert [e.entry_id for e in result] == ["01GONE", "01LIVE"]
    tombstoned = next(e for e in result if e.entry_id == "01GONE")
    assert tombstoned.tombstoned_at is not None
    assert tombstoned.run_record.status == "tombstoned"


def test_find_runs_for_target_returns_both_when_target_types_differ(
    store: ProjectStore,
) -> None:
    """Filter is on ``target_expression`` alone: differing ``target_type`` does
    not partition results. Regression's comparability check, not Memory, is
    responsible for narrowing down by target_type.
    """
    from dataclasses import replace

    target = "tests/shared"
    file_record = _record(run_id="01FILE", target_expression=target)
    pkg_record = replace(
        _record(run_id="01PKG", created_at=TS_2026_05_13, target_expression=target),
        target_type="package",
    )
    store_run_evidence(store, file_record)
    store_run_evidence(store, pkg_record)

    result = find_runs_for_target(store, target)

    assert {e.entry_id for e in result} == {"01FILE", "01PKG"}
    target_types = {e.run_record.target_type for e in result}
    assert target_types == {"file", "package"}


# --- ordering determinism (XCT-07 / S36) --------------------------------------
#
# Pinned cross-team convention (S36; verbatim in the memory and regression
# briefs): total order on runs = lexicographic on the composite key
# ``(created_at, run_id)``; newest-first = descending on both components;
# ``run_id`` is a ULID string and plain string comparison is the tie component.
#
# The permutation tests monkeypatch ``_iter_all_records`` to feed the REAL
# resolved records in EVERY possible pre-sort order, so they cannot silently
# depend on filesystem enumeration order — pre-fix, Python's stable sort
# preserved rglob order among same-millisecond siblings, which is
# host-dependent (XCT-07).


def _resolved_records(store: ProjectStore) -> list[store_module._ResolvedRecord]:
    """Materialize the store's real resolved records once, for permutation."""
    return list(store_module._iter_all_records(store))


def _iteration_feeding(
    records: Sequence[store_module._ResolvedRecord],
) -> Callable[..., Iterator[store_module._ResolvedRecord]]:
    """An ``_iter_all_records`` stand-in yielding ``records`` in the given order."""

    def fake(
        _store: ProjectStore, *, skipped: list[SkippedRecord] | None = None
    ) -> Iterator[store_module._ResolvedRecord]:
        return iter(records)

    return fake


def test_list_history_same_ms_ties_break_on_run_id_for_every_iteration_order(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three same-millisecond siblings order run_id-descending no matter what
    order the scan yields them in; the older run sorts last even though its
    run_id string is the largest (created_at stays the primary component).
    """
    for run_id in ("01TIEB", "01TIEA", "01TIEC"):
        store_run_evidence(store, _record(run_id=run_id, created_at=TS_2026_05_13))
    store_run_evidence(store, _record(run_id="01ZOLD", created_at=TS_2024_01_02))
    records = _resolved_records(store)
    assert len(records) == 4

    for permutation in itertools.permutations(records):
        monkeypatch.setattr(
            store_module, "_iter_all_records", _iteration_feeding(permutation)
        )
        entries = list_run_history(store)
        assert [e.entry_id for e in entries] == [
            "01TIEC",
            "01TIEB",
            "01TIEA",
            "01ZOLD",
        ], (
            "order broke for pre-sort permutation "
            f"{[r.record.run_reference.run_id for r in permutation]}"
        )


def test_find_runs_same_ms_ties_break_on_run_id_for_every_iteration_order(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`find_runs_for_target` applies the identical composite key after its
    target filter: same-ms matches order run_id-descending for every pre-sort
    permutation, the same-ms non-matching sibling stays excluded, and the
    older match sorts last despite the largest run_id string.
    """
    target = "tests/test_shared.py"
    for run_id in ("01TIEB", "01TIEA", "01TIEC"):
        store_run_evidence(
            store,
            _record(run_id=run_id, created_at=TS_2026_05_13, target_expression=target),
        )
    store_run_evidence(
        store,
        _record(
            run_id="01MISS",
            created_at=TS_2026_05_13,
            target_expression="tests/other.py",
        ),
    )
    store_run_evidence(
        store,
        _record(run_id="01ZOLD", created_at=TS_2024_01_02, target_expression=target),
    )
    records = _resolved_records(store)
    assert len(records) == 5

    for permutation in itertools.permutations(records):
        monkeypatch.setattr(
            store_module, "_iter_all_records", _iteration_feeding(permutation)
        )
        entries = find_runs_for_target(store, target)
        assert [e.entry_id for e in entries] == [
            "01TIEC",
            "01TIEB",
            "01TIEA",
            "01ZOLD",
        ], (
            "order broke for pre-sort permutation "
            f"{[r.record.run_reference.run_id for r in permutation]}"
        )


def test_list_history_same_ms_on_disk_is_run_id_descending(
    store: ProjectStore,
) -> None:
    """End-to-end pin through the real rglob scan: insertion order is
    scrambled, and the composite key — not FS or insertion order — decides
    the same-millisecond tie.
    """
    for run_id in ("01SIBB", "01SIBC", "01SIBA"):
        store_run_evidence(store, _record(run_id=run_id, created_at=TS_2026_05_13))

    entries = list_run_history(store)

    assert [e.entry_id for e in entries] == ["01SIBC", "01SIBB", "01SIBA"]


def test_find_runs_same_ms_on_disk_is_run_id_descending(
    store: ProjectStore,
) -> None:
    target = "tests/test_shared.py"
    for run_id in ("01SIBB", "01SIBC", "01SIBA"):
        store_run_evidence(
            store,
            _record(run_id=run_id, created_at=TS_2026_05_13, target_expression=target),
        )

    entries = find_runs_for_target(store, target)

    assert [e.entry_id for e in entries] == ["01SIBC", "01SIBB", "01SIBA"]


# --- has_regression_facts ----------------------------------------------------
#
# The `_availability_flags` probe scans `<store>/regression/pairs/` for any
# directory whose name contains `run_<run_id>` (either baseline or target
# position) AND holds a `regression_facts.json`. Decision
# `2026-05-26-regression-facts-json-layout.md` §1 pins the layout; §C.5 names
# this probe as Memory's responsibility (engine team owns file shape, Memory
# owns the existence probe). These tests cover the cold/empty/missing-file
# guards plus baseline/target/multi-pair/tombstoned flips so the contract is
# nailed down at the Memory boundary before any CLI verb consumes it.


def _write_stub_regression_facts(pair_dir: Path) -> None:
    """Write a minimal pair file. The probe checks existence only, never parses."""
    pair_dir.mkdir(parents=True)
    (pair_dir / "regression_facts.json").write_text(
        '{"schema_version": 1}', encoding="utf-8"
    )


def test_has_regression_facts_cold_store_returns_false(store: ProjectStore) -> None:
    """No `<store>/regression/pairs/` dir exists at all → flag stays False, no exception."""
    record = _record(run_id="01COLD")
    store_run_evidence(store, record)

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is False
    # Sanity: the probed `pairs/` subdir was never created (project store init
    # materializes `regression/` empty, but `regression/pairs/` only appears
    # once Regression writes its first pair).
    assert not (store.path / "regression" / "pairs").exists()


def test_has_regression_facts_empty_pairs_dir_returns_false(
    store: ProjectStore,
) -> None:
    """`<store>/regression/pairs/` exists but is empty → flag is False."""
    record = _record(run_id="01EMPTY")
    store_run_evidence(store, record)
    (store.path / "regression" / "pairs").mkdir(parents=True)

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is False


def test_has_regression_facts_when_run_is_baseline(store: ProjectStore) -> None:
    """Run appears in the baseline (left) position of a pair → flag flips True."""
    record = _record(run_id="01BASE")
    store_run_evidence(store, record)
    pair_dir = (
        store.path / "regression" / "pairs" / f"{RUN_DIR_PREFIX}01BASE__run_01TGT"
    )
    _write_stub_regression_facts(pair_dir)

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is True


def test_has_regression_facts_when_run_is_target(store: ProjectStore) -> None:
    """Run appears in the target (right) position of a pair → flag flips True.

    Confirms the probe is positionally agnostic — `compare_runs(a, b)` and
    `compare_runs(b, a)` are distinct files (decision §1), but Memory's
    availability flag does not care which side the run sat on.
    """
    record = _record(run_id="01TGT")
    store_run_evidence(store, record)
    pair_dir = (
        store.path / "regression" / "pairs" / f"run_01BASE__{RUN_DIR_PREFIX}01TGT"
    )
    _write_stub_regression_facts(pair_dir)

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is True


def test_has_regression_facts_run_in_multiple_pairs_is_idempotent(
    store: ProjectStore,
) -> None:
    """Run participates in several pairs (both as baseline and as target) → still True."""
    record = _record(run_id="01HUB")
    store_run_evidence(store, record)
    pairs_root = store.path / "regression" / "pairs"
    _write_stub_regression_facts(pairs_root / f"{RUN_DIR_PREFIX}01HUB__run_01OTHER1")
    _write_stub_regression_facts(pairs_root / f"run_01OTHER2__{RUN_DIR_PREFIX}01HUB")
    _write_stub_regression_facts(pairs_root / f"{RUN_DIR_PREFIX}01HUB__run_01OTHER3")

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is True


def test_has_regression_facts_pair_dir_without_json_returns_false(
    store: ProjectStore,
) -> None:
    """Pair dir exists but `regression_facts.json` is missing → flag is False.

    Deliberate "file is the truth, directory is the index" guard: a crashed
    mid-write or hand-deleted facts file MUST NOT light up the availability
    flag. Memory reflects the canonical artifact, not the scaffold around it.
    """
    record = _record(run_id="01SCAFFOLD")
    store_run_evidence(store, record)
    pair_dir = (
        store.path / "regression" / "pairs" / f"{RUN_DIR_PREFIX}01SCAFFOLD__run_01X"
    )
    pair_dir.mkdir(parents=True)
    # Intentionally NO regression_facts.json.

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is False


def test_has_regression_facts_run_not_in_any_pair_returns_false(
    store: ProjectStore,
) -> None:
    """Pairs exist on disk for OTHER runs but none mention this run → flag is False."""
    record = _record(run_id="01SOLO")
    store_run_evidence(store, record)
    pairs_root = store.path / "regression" / "pairs"
    _write_stub_regression_facts(pairs_root / "run_01A__run_01B")
    _write_stub_regression_facts(pairs_root / "run_01C__run_01D")

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is False


def test_has_regression_facts_for_tombstoned_run_with_matching_pair(
    store: ProjectStore,
) -> None:
    """Tombstoned run with a stale pair file on disk → flag is True.

    Per decision §C.1, tombstoned runs may retain pair files for audit; the
    Regression engine handles the fail-hard at `compare_runs` time. Memory's
    job is to reflect what's on disk — availability ≠ usability.
    """
    record = _record(run_id="01GHOST")
    store_run_evidence(store, record)
    pair_dir = (
        store.path / "regression" / "pairs" / f"{RUN_DIR_PREFIX}01GHOST__run_01PEER"
    )
    _write_stub_regression_facts(pair_dir)
    delete_run_evidence(store, record.run_reference)

    avail = get_memory_entry_availability(store, record.run_reference)

    assert avail["has_regression_facts"] is True
    assert avail["tombstoned"] is True


# --- MEM-01: run+reset race — no silent run loss -------------------------------
#
# `wipe_project_store` atomically renames `.novetest/` away. If that happens
# after this process resolved its store handle, `store_run_evidence`'s
# `mkdir(parents=True)` used to resurrect a store.json-less skeleton at the old
# path; `find_nearest_store` skips such a `.novetest/` forever, so the run was
# silently orphaned. The fix re-verifies `store.json` immediately before the
# mkdir and raises the domain uninitialized error instead. A/B: drop the
# pre-mkdir check and both tests below fail (no raise; skeleton resurrected).


def _live_record_path(store: ProjectStore, run_id: str) -> Path:
    """Path of a TS_2024_01_02-dated run's record.json (date path 2024/01/02)."""
    return (
        store.path / "memory" / "runs" / "2024" / "01" / "02"
        / f"{RUN_DIR_PREFIX}{run_id}" / RECORD_FILENAME
    )


def test_store_raises_uninitialized_when_store_wiped_concurrently(
    store: ProjectStore, tmp_path: Path
) -> None:
    # Simulate the wipe's atomic detach landing between handle resolution and
    # the store write: the whole `.novetest/` moves to a staging sibling.
    store.path.rename(tmp_path / ".novetest.deleting.01RACEULID")

    with pytest.raises(ProjectStoreNotFoundError):
        store_run_evidence(store, _record())

    # Load-bearing: no orphan skeleton was resurrected at the old path.
    assert not store.path.exists()


def test_store_raises_uninitialized_when_metadata_vanished(
    store: ProjectStore,
) -> None:
    # Partial shape: the directory survives but `store.json` is gone. Such a
    # `.novetest/` is not a store (find_nearest_store walks past it), so
    # writing into it would orphan the run just the same.
    (store.path / STORE_METADATA_FILENAME).unlink()

    with pytest.raises(ProjectStoreNotFoundError):
        store_run_evidence(store, _record())

    assert not _live_record_path(store, "01HXYZ").exists()


# --- MEM-04: stored_at is persisted, not mtime-derived -------------------------
#
# `store_run_evidence` stamps `stored_at` (epoch ms) INTO `record.json`; every
# read path prefers that persisted value and only falls back to the file mtime
# for legacy (pre-MEM-04) records. Tombstoning preserves the ORIGINAL stamp —
# `tombstoned_at` stays the separate deletion timestamp. The stamp never leaks
# into the nested `run_record` wire projection (MemoryEntry.stored_at is the
# established envelope slot).


def test_stored_at_persisted_and_preferred_over_mtime(store: ProjectStore) -> None:
    record = _record()
    entry = store_run_evidence(store, record)
    record_path = _live_record_path(store, "01HXYZ")

    raw = json.loads(record_path.read_text(encoding="utf-8"))
    assert raw["stored_at"] == entry.stored_at
    assert isinstance(raw["stored_at"], int)

    # Shift the file mtime far away (backup restore / git checkout / cloud
    # sync all do this in the wild). The reported stored_at must not move.
    os.utime(record_path, ns=(TS_2026_05_13 * 10**6, TS_2026_05_13 * 10**6))

    assert retrieve_run_evidence(store, record.run_reference).stored_at == entry.stored_at
    assert list_run_history(store)[0].stored_at == entry.stored_at
    assert (
        find_runs_for_target(store, record.target_expression)[0].stored_at
        == entry.stored_at
    )


def test_legacy_record_without_stored_at_falls_back_to_mtime(
    store: ProjectStore,
) -> None:
    # Hand-write a pre-MEM-04 record.json. `to_dict()` omits the key when the
    # field is None, so this is byte-exactly the legacy shape.
    record = _record()
    assert "stored_at" not in record.to_dict()
    record_path = _live_record_path(store, "01HXYZ")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    os.utime(record_path, ns=(TS_2026_05_13 * 10**6, TS_2026_05_13 * 10**6))

    fetched = retrieve_run_evidence(store, record.run_reference)
    assert fetched.stored_at == TS_2026_05_13


def test_tombstone_preserves_original_stored_at(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Whole-second stamps keep the float round-trip through time.time() exact.
    stamp_store = TS_2024_01_02 + 5_000
    stamp_delete = TS_2024_01_02 + 777_000
    record = _record()

    monkeypatch.setattr("novetest.memory.store.time.time", lambda: stamp_store / 1000)
    entry = store_run_evidence(store, record)
    assert entry.stored_at == stamp_store

    monkeypatch.setattr("novetest.memory.store.time.time", lambda: stamp_delete / 1000)
    deleted = delete_run_evidence(store, record.run_reference)

    # stored_at did NOT shift to deletion time; tombstoned_at is separate.
    assert deleted.stored_at == stamp_store
    assert deleted.tombstoned_at == stamp_delete

    tombstone_record = store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01HXYZ" / RECORD_FILENAME
    raw = json.loads(tombstone_record.read_text(encoding="utf-8"))
    assert raw["stored_at"] == stamp_store

    refetched = retrieve_run_evidence(store, record.run_reference)
    assert refetched.stored_at == stamp_store
    assert refetched.tombstoned_at == stamp_delete

    # The re-delete no-op reports the same preserved stamp.
    again = delete_run_evidence(store, record.run_reference)
    assert again.stored_at == stamp_store


def test_legacy_tombstone_stamps_pre_delete_mtime_not_deletion_time(
    store: ProjectStore,
) -> None:
    # A LEGACY record being tombstoned: the rewrite stamps the pre-rewrite
    # mtime (the best available approximation of the original store instant)
    # so deletion does not shift stored_at even for old records.
    record = _record()
    record_path = _live_record_path(store, "01HXYZ")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    os.utime(record_path, ns=(TS_2026_05_13 * 10**6, TS_2026_05_13 * 10**6))

    deleted = delete_run_evidence(store, record.run_reference)

    assert deleted.stored_at == TS_2026_05_13
    tombstone_record = store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01HXYZ" / RECORD_FILENAME
    raw = json.loads(tombstone_record.read_text(encoding="utf-8"))
    assert raw["stored_at"] == TS_2026_05_13
    assert retrieve_run_evidence(store, record.run_reference).stored_at == TS_2026_05_13


def test_stored_at_stays_off_the_run_record_wire_projection(
    store: ProjectStore,
) -> None:
    # Envelope byte-compat pin: `MemoryEntry.to_dict()["run_record"]` must not
    # grow a `stored_at` key — the stamp surfaces ONLY at the MemoryEntry level.
    record = _record()
    stored = store_run_evidence(store, record)

    entries = [
        stored,
        retrieve_run_evidence(store, record.run_reference),
        *list_run_history(store),
        *find_runs_for_target(store, record.target_expression),
    ]
    for entry in entries:
        assert entry.run_record.stored_at is None
        payload = entry.to_dict()
        assert "stored_at" not in payload["run_record"]
        assert payload["stored_at"] == stored.stored_at


# --- MEM-05: per-record isolation in history scans ------------------------------
#
# One torn/corrupt/future-schema `record.json` must not kill the scan
# interfaces (`list_run_history` / `find_runs_for_target`) that memory list,
# regression baseline resolution, and localization latest-derivation all walk.
# Failed records are SKIPPED and surfaced through the optional `skipped`
# collector (path included). Targeted reads stay LOUD. A/B: revert the
# isolation in `_iter_all_records` and every scan test below dies on the
# planted record again.


def _plant_torn_record(store: ProjectStore, run_id: str, created_at: int) -> Path:
    """Store a healthy run, then tear its record.json (torn-write shape)."""
    store_run_evidence(store, _record(run_id=run_id, created_at=created_at))
    matches = [
        p
        for p in (store.path / "memory" / "runs").rglob(RECORD_FILENAME)
        if p.parent.name == f"{RUN_DIR_PREFIX}{run_id}"
    ]
    assert len(matches) == 1
    matches[0].write_text('{"schema_version": 1, "run_refe', encoding="utf-8")
    return matches[0]


def test_list_run_history_skips_torn_record_and_reports_its_path(
    store: ProjectStore,
) -> None:
    store_run_evidence(store, _record(run_id="01OK", created_at=TS_2024_01_02))
    torn_path = _plant_torn_record(store, "01TORN", TS_2026_05_13)

    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)

    assert [e.entry_id for e in entries] == ["01OK"]
    assert len(skipped) == 1
    assert skipped[0].path == torn_path
    assert skipped[0].error  # non-empty parse failure message


def test_list_run_history_skips_future_schema_record(store: ProjectStore) -> None:
    store_run_evidence(store, _record(run_id="01OK", created_at=TS_2024_01_02))
    future = _record(run_id="01FUTURE", created_at=TS_2026_05_13)
    store_run_evidence(store, future)
    future_path = (
        store.path / "memory" / "runs" / "2026" / "05" / "13"
        / f"{RUN_DIR_PREFIX}01FUTURE" / RECORD_FILENAME
    )
    raw = json.loads(future_path.read_text(encoding="utf-8"))
    raw["schema_version"] = 2
    future_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)

    assert [e.entry_id for e in entries] == ["01OK"]
    assert [s.path for s in skipped] == [future_path]
    assert "schema_version" in skipped[0].error


def test_scan_survives_corrupt_record_without_a_collector(
    store: ProjectStore,
) -> None:
    # The non-CLI consumers (status/inspect/regression/localization) call the
    # scan interfaces WITHOUT a collector: isolation alone must hold.
    store_run_evidence(store, _record(run_id="01OK", created_at=TS_2024_01_02))
    _plant_torn_record(store, "01TORN", TS_2026_05_13)

    assert [e.entry_id for e in list_run_history(store)] == ["01OK"]


def test_find_runs_for_target_skips_corrupt_record(store: ProjectStore) -> None:
    target = "tests/test_shared.py"
    store_run_evidence(
        store, _record(run_id="01OK", created_at=TS_2024_01_02, target_expression=target)
    )
    torn_path = _plant_torn_record(store, "01TORN", TS_2026_05_13)

    skipped: list[SkippedRecord] = []
    result = find_runs_for_target(store, target, skipped=skipped)

    assert [e.entry_id for e in result] == ["01OK"]
    assert [s.path for s in skipped] == [torn_path]


def test_corrupt_tombstoned_record_is_skipped_too(store: ProjectStore) -> None:
    store_run_evidence(store, _record(run_id="01OK", created_at=TS_2024_01_02))
    gone = _record(run_id="01GONE", created_at=TS_2026_05_13)
    store_run_evidence(store, gone)
    delete_run_evidence(store, gone.run_reference)
    tombstone_record = (
        store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01GONE" / RECORD_FILENAME
    )
    tombstone_record.write_text("not json at all", encoding="utf-8")

    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)

    assert [e.entry_id for e in entries] == ["01OK"]
    assert [s.path for s in skipped] == [tombstone_record]
    # S42: tombstone dirs are `run_<id>`-named too — the skip carries the id.
    assert skipped[0].run_id == "01GONE"


# --- S42 / XCT-03: typed corruption error on loud paths + run_id on skips -------
#
# `_read_record` wraps parse/shape failures in `ProjectStoreCorruptError`
# (path-bearing message) so every residual loud path carries the typed
# storage error the CLI maps to `store-corrupt` / exit 5. Scan skips gain
# the `run_id` field so addressed lookup misses can recognize a corrupt
# record (Q1 Option A). A/B: revert the `_read_record` wrap and the typed
# tests below observe raw ValueErrors again.


def test_targeted_read_of_corrupt_run_raises_typed_storage_error(
    store: ProjectStore,
) -> None:
    # `retrieve_run_evidence` names ONE run — a parse failure must propagate,
    # and since S42 it propagates TYPED with the corrupt file's path in the
    # message (the exit-5 `store-corrupt` contract's raise side).
    torn = _record(run_id="01TORN", created_at=TS_2026_05_13)
    torn_path = _plant_torn_record(store, "01TORN", TS_2026_05_13)

    with pytest.raises(ProjectStoreCorruptError) as exc_info:
        retrieve_run_evidence(store, torn.run_reference)
    assert str(torn_path) in str(exc_info.value)


def test_targeted_read_of_future_schema_run_raises_typed_storage_error(
    store: ProjectStore,
) -> None:
    future = _record(run_id="01FUTURE", created_at=TS_2026_05_13)
    store_run_evidence(store, future)
    future_path = (
        store.path / "memory" / "runs" / "2026" / "05" / "13"
        / f"{RUN_DIR_PREFIX}01FUTURE" / RECORD_FILENAME
    )
    raw = json.loads(future_path.read_text(encoding="utf-8"))
    raw["schema_version"] = 2
    future_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProjectStoreCorruptError, match="Unsupported") as exc_info:
        retrieve_run_evidence(store, future.run_reference)
    assert str(future_path) in str(exc_info.value)


def test_targeted_read_of_corrupt_tombstoned_run_raises_typed_storage_error(
    store: ProjectStore,
) -> None:
    gone = _record(run_id="01GONE", created_at=TS_2026_05_13)
    store_run_evidence(store, gone)
    delete_run_evidence(store, gone.run_reference)
    tombstone_record = (
        store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}01GONE" / RECORD_FILENAME
    )
    tombstone_record.write_text("not json at all", encoding="utf-8")

    with pytest.raises(ProjectStoreCorruptError) as exc_info:
        retrieve_run_evidence(store, gone.run_reference)
    assert str(tombstone_record) in str(exc_info.value)


def test_delete_of_corrupt_run_raises_typed_storage_error(
    store: ProjectStore,
) -> None:
    # Tombstoning re-writes the PARSED record — a corrupt record cannot be
    # tombstoned. The typed raise is what makes the CLI's exit-5 outcome
    # (rather than a fake success or a cli-error) possible.
    torn = _record(run_id="01TORN", created_at=TS_2026_05_13)
    torn_path = _plant_torn_record(store, "01TORN", TS_2026_05_13)

    with pytest.raises(ProjectStoreCorruptError) as exc_info:
        delete_run_evidence(store, torn.run_reference)
    assert str(torn_path) in str(exc_info.value)
    # Nothing was mutated: the (corrupt) record is still at its live location.
    assert torn_path.is_file()


def test_read_record_does_not_wrap_oserror(store: ProjectStore) -> None:
    # Vanished-file semantics unchanged (S42 pins the wrap to parse/shape
    # failures only): a missing file is an OSError, never `store-corrupt`.
    with pytest.raises(FileNotFoundError):
        store_module._read_record(store.path / "memory" / "nope" / RECORD_FILENAME)


def test_skipped_record_carries_run_id_from_directory_name(
    store: ProjectStore,
) -> None:
    torn_path = _plant_torn_record(store, "01TORN", TS_2026_05_13)

    skipped: list[SkippedRecord] = []
    list_run_history(store, skipped=skipped)

    assert [s.run_id for s in skipped] == ["01TORN"]
    assert skipped[0].path == torn_path
    # The typed wrap keeps the skip's error message path-bearing.
    assert str(torn_path) in skipped[0].error


def test_skipped_record_run_id_is_none_for_unparseable_directory(
    store: ProjectStore,
) -> None:
    weird_dir = store.path / "memory" / "runs" / "2026" / "05" / "13" / "weird"
    weird_dir.mkdir(parents=True)
    (weird_dir / RECORD_FILENAME).write_text("not json", encoding="utf-8")

    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)

    assert entries == []
    assert [s.run_id for s in skipped] == [None]


# --- S43 rider: non-UTF-8 record.json is corruption like any other ------------
#
# S42's corruption inventory row 12: `_read_record` read the file OUTSIDE its
# typed wrap, so a record.json holding non-UTF-8 bytes escaped as a raw
# `UnicodeDecodeError` (a ValueError subclass) instead of the path-bearing
# `ProjectStoreCorruptError`. The S43 rider moves the read inside the wrap.
# A/B: revert that (read before the try) and both tests below fail.


def _plant_non_utf8_record(store: ProjectStore, run_id: str) -> Path:
    """Store a healthy run at TS_2026_05_13, then overwrite it with bad bytes."""
    store_run_evidence(store, _record(run_id=run_id, created_at=TS_2026_05_13))
    record_path = (
        store.path / "memory" / "runs" / "2026" / "05" / "13"
        / f"{RUN_DIR_PREFIX}{run_id}" / RECORD_FILENAME
    )
    # 0xFF is never a valid UTF-8 start byte → UnicodeDecodeError at read_text.
    record_path.write_bytes(b'\xff\xfe{"schema_version": 1}')
    return record_path


def test_targeted_read_of_non_utf8_record_raises_typed_storage_error(
    store: ProjectStore,
) -> None:
    bad = _record(run_id="01BYTES", created_at=TS_2026_05_13)
    record_path = _plant_non_utf8_record(store, "01BYTES")

    with pytest.raises(ProjectStoreCorruptError) as exc_info:
        retrieve_run_evidence(store, bad.run_reference)
    assert str(record_path) in str(exc_info.value)


def test_scan_skip_of_non_utf8_record_carries_path_and_run_id(
    store: ProjectStore,
) -> None:
    # The scan side already skipped this class (raw ValueError catch); the
    # rider upgrades the skip's error message to the path-bearing typed form
    # — the same doctrine every other corruption class has had since S42
    # (memory.md MEM-05: the projected warning message names the file).
    store_run_evidence(store, _record(run_id="01OK", created_at=TS_2024_01_02))
    record_path = _plant_non_utf8_record(store, "01BYTES")

    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)

    assert [e.entry_id for e in entries] == ["01OK"]
    assert [s.run_id for s in skipped] == ["01BYTES"]
    assert str(record_path) in skipped[0].error
