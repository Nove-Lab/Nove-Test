"""Unit tests for `novetest.memory.store`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.memory.store import (
    RECORD_FILENAME,
    RUN_DIR_PREFIX,
    RunEvidenceAlreadyExistsError,
    RunEvidenceNotFoundError,
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
    store_run_evidence(store, record)
    persisted_path = (
        store.path / "memory" / "runs" / "2024" / "01" / "02" / f"{RUN_DIR_PREFIX}01HXYZ"
        / RECORD_FILENAME
    )
    raw = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert raw == record.to_dict()


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
