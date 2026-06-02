"""Persistence helpers — atomic write + raw read + Memory probe coupling.

Mirrors ``tests/unit/localization/test_persistence.py`` in structure and
intent.  All tests use a real ``tmp_path``-backed Project Store; no mocking.

The path layout is load-bearing: Memory's ``_availability_flags`` probe
checks for exactly::

    <store>/replay/results/run_<original_run_id>/replay_result.json

Any deviation silently breaks the ``has_replay_result`` flag.  This module
pins that path via ``test_replay_result_path_layout_is_load_bearing``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.replay.persistence import (
    read_replay_result_raw,
    replay_result_dir,
    replay_result_path,
    write_replay_result,
)


# ---------------------------------------------------------------------------
# Stable reference so cache-path tests are predictable
# ---------------------------------------------------------------------------

_REF = RunReference(run_id="01HPERSIST00000000000000RR", created_at=1_700_000_000_000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(run_reference: RunReference = _REF) -> ReplayResult:
    """Build a minimal valid ``ReplayResult`` for ``run_reference``."""
    return ReplayResult(
        run_reference=run_reference,
        classification="reproducible",
        reruns_total=3,
        reruns_failed=0,
        test_id=None,
        replayed_run_reference=RunReference(
            run_id="01HPERSIST00000000000REPL", created_at=1_700_000_001_000
        ),
        per_rerun_outcomes=("passed", "passed", "passed"),
        consistency_summary={
            "original_passed": 1,
            "original_failed": 0,
            "replay_passed": 3,
            "replay_failed": 0,
            "replay_errored": 0,
        },
        attempted_at=1_748_000_000_000,
        reason=None,
    )


# ---------------------------------------------------------------------------
# Path layout — load-bearing Memory probe coupling
# ---------------------------------------------------------------------------


def test_replay_result_path_layout_is_load_bearing(tmp_path: Path) -> None:
    """The exact path that Memory's ``_availability_flags`` probe must match.

    Memory checks:
    ``<store>/replay/results/run_<run_id>/replay_result.json``
    """
    store = create_project_store(tmp_path)
    expected = (
        store.path
        / "replay"
        / "results"
        / f"run_{_REF.run_id}"
        / "replay_result.json"
    )
    assert replay_result_path(store, _REF) == expected


def test_replay_result_dir_matches_path_parent(tmp_path: Path) -> None:
    """``replay_result_dir`` must equal the parent of ``replay_result_path``."""
    store = create_project_store(tmp_path)
    assert replay_result_dir(store, _REF) == replay_result_path(store, _REF).parent


# ---------------------------------------------------------------------------
# Round-trip: write → read_raw → from_dict
# ---------------------------------------------------------------------------


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    """``write_replay_result`` + ``read_replay_result_raw`` + ``from_dict`` round-trips."""
    store = create_project_store(tmp_path)
    result = _result()

    write_path = write_replay_result(store, _REF, result)

    assert write_path == replay_result_path(store, _REF)

    raw = read_replay_result_raw(store, _REF)
    assert raw is not None

    restored = ReplayResult.from_dict(raw)
    assert restored == result


def test_round_trip_inconsistent_with_test_id(tmp_path: Path) -> None:
    """Round-trip preserves non-None ``test_id`` and ``reason=None``."""
    store = create_project_store(tmp_path)
    ref = RunReference(run_id="01HPERS00000000000000RR2", created_at=1_700_000_000_001)
    result = ReplayResult(
        run_reference=ref,
        classification="inconsistent",
        reruns_total=5,
        reruns_failed=2,
        test_id="tests/test_flaky.py::test_flaky",
        per_rerun_outcomes=("passed", "failed", "passed", "passed", "failed"),
        consistency_summary={"original_passed": 1, "replay_passed": 3, "replay_failed": 2},
        attempted_at=1_748_800_000_000,
        reason=None,
    )

    write_replay_result(store, ref, result)
    raw = read_replay_result_raw(store, ref)
    assert raw is not None
    restored = ReplayResult.from_dict(raw)
    assert restored == result
    assert restored.test_id == "tests/test_flaky.py::test_flaky"


def test_round_trip_unable_to_replay_with_reason(tmp_path: Path) -> None:
    """Round-trip preserves ``unable_to_replay`` classification and ``reason``."""
    store = create_project_store(tmp_path)
    ref = RunReference(run_id="01HPERS00000000000000RR3", created_at=1_700_000_000_002)
    result = ReplayResult(
        run_reference=ref,
        classification="unable_to_replay",
        reruns_total=0,
        reruns_failed=0,
        test_id=None,
        replayed_run_reference=None,
        per_rerun_outcomes=(),
        consistency_summary={"original_passed": 1},
        attempted_at=0,
        reason="no-replayed-runs",
    )

    write_replay_result(store, ref, result)
    raw = read_replay_result_raw(store, ref)
    assert raw is not None
    restored = ReplayResult.from_dict(raw)
    assert restored == result
    assert restored.reason == "no-replayed-runs"


# ---------------------------------------------------------------------------
# read_replay_result_raw returns None for missing file
# ---------------------------------------------------------------------------


def test_read_missing_returns_none(tmp_path: Path) -> None:
    """``read_replay_result_raw`` returns ``None`` when no file exists."""
    store = create_project_store(tmp_path)
    unknown_ref = RunReference(run_id="01HUNKNOWN0000000000000YY", created_at=1_700_000_000_000)
    assert read_replay_result_raw(store, unknown_ref) is None


# ---------------------------------------------------------------------------
# write creates parent directory on demand
# ---------------------------------------------------------------------------


def test_write_creates_parent_directory_on_demand(tmp_path: Path) -> None:
    """``write_replay_result`` must create the run subdirectory if absent."""
    store = create_project_store(tmp_path)
    target_dir = replay_result_dir(store, _REF)
    assert not target_dir.exists()
    write_replay_result(store, _REF, _result())
    assert target_dir.is_dir()


# ---------------------------------------------------------------------------
# Atomic overwrite: write twice → second wins, no .tmp leftover
# ---------------------------------------------------------------------------


def test_overwrite_existing_file_with_fresh_result(tmp_path: Path) -> None:
    """Re-writing replaces the payload — refreshed Replay Attempt works."""
    store = create_project_store(tmp_path)
    write_replay_result(store, _REF, _result())

    ref2 = RunReference(run_id="01HPERSIST00000000000REPL", created_at=1_700_000_001_000)
    updated = ReplayResult(
        run_reference=_REF,
        classification="inconsistent",
        reruns_total=1,
        reruns_failed=1,
        attempted_at=9_999,
    )
    write_replay_result(store, _REF, updated)

    raw = read_replay_result_raw(store, _REF)
    assert raw is not None
    assert raw["classification"] == "inconsistent"
    assert raw["attempted_at"] == 9_999


def test_write_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    """After a successful write, no ``.tmp`` files linger in the result directory."""
    store = create_project_store(tmp_path)
    write_replay_result(store, _REF, _result())

    target_dir = replay_result_dir(store, _REF)
    contents = list(target_dir.iterdir())
    # Only the canonical file should exist.
    assert contents == [target_dir / "replay_result.json"]


# ---------------------------------------------------------------------------
# Memory flag: has_replay_result flips after write
# ---------------------------------------------------------------------------


def test_memory_flag_has_replay_result_flips_after_write(tmp_path: Path) -> None:
    """Memory's ``has_replay_result`` flag flips after the canonical write.

    This is the load-bearing coupling between the persistence path and
    Memory's ``_availability_flags`` probe.
    """
    store = create_project_store(tmp_path)
    record = RunRecord(
        run_reference=_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=_REF.created_at,
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="passed", duration_ms=1),
        ),
    )
    entry = store_run_evidence(store, record)
    assert entry.has_replay_result is False

    write_replay_result(store, _REF, _result())

    from novetest.memory.store import retrieve_run_evidence

    refreshed = retrieve_run_evidence(store, _REF)
    assert refreshed.has_replay_result is True


# ---------------------------------------------------------------------------
# Malformed JSON raises ValueError
# ---------------------------------------------------------------------------


def test_read_non_object_json_raises(tmp_path: Path) -> None:
    """A ``replay_result.json`` whose root is not a JSON object raises ``ValueError``."""
    store = create_project_store(tmp_path)
    target_dir = replay_result_dir(store, _REF)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "replay_result.json").write_text(
        json.dumps(["not", "an", "object"]) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not a JSON object"):
        read_replay_result_raw(store, _REF)
