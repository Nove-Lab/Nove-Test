"""Unit tests for the S42 / XCT-03 ``store-corrupt`` (exit 5) CLI mapping.

Two wire deltas are pinned here (Gate-1 Q1 Option A, task
``orchestration-team-2026-07-13-w2-s42-store-corruption-exit5``):

1. **Addressed-corrupt escalation** — a run_id-addressed lookup that misses
   because the isolated scan skipped the requested record as corrupt
   escalates from the dishonest ``not-found`` / exit 2 to ``store-corrupt``
   / exit 5 (``_lookup_miss_exit``). Genuinely-absent ids keep ``not-found``.
2. **Residual loud paths** — a ``ProjectStoreCorruptError`` surfacing
   through a verb body (TOCTOU: the record turned corrupt between the scan
   and a targeted read) maps to ``store-corrupt`` / exit 5 at the verb's
   transport seam instead of falling through to ``main()``'s generic
   ``cli-error`` / exit 1.

The two ``main()``-routed TOCTOU tests use a REAL store + the real
``retrieve_run_evidence`` / ``delete_run_evidence`` chain — they are the
A/B sentinels for the Memory-side ``_read_record`` wrap: revert the wrap
and they observe the pre-S42 ``cli-error`` / exit 1 again. Engine seams in
the remaining tests are monkeypatched at ``cli.app`` (the module that calls
them), per the module convention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.memory import SkippedRecord
from novetest.memory.project_store import (
    ProjectStoreCorruptError,
    create_project_store,
)
from novetest.memory.store import RECORD_FILENAME, RUN_DIR_PREFIX, store_run_evidence
from novetest.models import MemoryEntry, RunRecord, RunReference


_RUN_ID = "01CORRUPTRUN"
_ABSENT_ID = "01NOSUCHRUN"
_FAKE_PATH = Path("/store/memory/runs/2026/07/13/run_01CORRUPTRUN/record.json")


def _make_record(run_id: str = _RUN_ID, created_at: int = 1_700_000_000_000) -> RunRecord:
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=created_at),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1_000,
        summary_counts={"passed": 1, "total": 1},
    )


def _make_memory_entry(run_id: str = _RUN_ID) -> MemoryEntry:
    record = _make_record(run_id)
    return MemoryEntry(entry_id=run_id, run_record=record, stored_at=3)


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


def _stub_history_with_corrupt_skip(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str = _RUN_ID,
    path: Path = _FAKE_PATH,
) -> None:
    """History scan that returns nothing but reports one corrupt skip."""
    error = f"Corrupt run record at {path}: Expecting value: line 1 column 1"

    def fake_history(_store: Any, skipped: Any = None) -> list[MemoryEntry]:
        if skipped is not None:
            skipped.append(SkippedRecord(path=path, error=error, run_id=run_id))
        return []

    monkeypatch.setattr(app_module, "list_run_history", fake_history)


def _raise_corrupt(*_a: Any, **_k: Any) -> Any:
    raise ProjectStoreCorruptError(f"Corrupt run record at {_FAKE_PATH}: boom")


async def _raise_corrupt_async(*_a: Any, **_k: Any) -> Any:
    raise ProjectStoreCorruptError(f"Corrupt run record at {_FAKE_PATH}: boom")


# ---------------------------------------------------------------------------
# Q1-A: addressed-corrupt lookup escalation (exit 2 not-found → exit 5)
# ---------------------------------------------------------------------------


def test_resolve_run_reference_escalates_corrupt_match_to_store_corrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    _stub_history_with_corrupt_skip(monkeypatch)

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("get_coverage_facts called for a corrupt-skipped run")

    monkeypatch.setattr(app_module, "get_coverage_facts", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show(_RUN_ID)
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "coverage.show"
    assert payload["errors"][0]["code"] == "store-corrupt"
    # Path doctrine: the operator locates the corrupt file from the message.
    assert str(_FAKE_PATH) in payload["errors"][0]["message"]
    # Non-memory verbs stay warning-free (S41 transport choice unchanged).
    assert payload["warnings"] == []


def test_resolve_run_reference_keeps_not_found_for_absent_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """The escalation fires ONLY on an id match — a genuinely-absent id keeps
    the unchanged ``not-found`` / exit 2 even while corrupt skips exist."""
    _stub_history_with_corrupt_skip(monkeypatch)
    monkeypatch.setattr(app_module, "get_coverage_facts", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show(_ABSENT_ID)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "not-found"


def test_memory_show_corrupt_addressed_lookup_exits_5_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    _stub_history_with_corrupt_skip(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        app_module.memory_show(_RUN_ID)
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["command"] == "memory.show"
    assert payload["errors"][0]["code"] == "store-corrupt"
    assert str(_FAKE_PATH) in payload["errors"][0]["message"]
    # Memory verbs keep the S41 warning channel alongside the escalation.
    assert [w["code"] for w in payload["warnings"]] == ["corrupt-run-record-skipped"]
    assert payload["warnings"][0]["details"]["path"] == str(_FAKE_PATH)


def test_memory_delete_corrupt_addressed_lookup_exits_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    _stub_history_with_corrupt_skip(monkeypatch)

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("delete_run_evidence called for a corrupt-skipped run")

    monkeypatch.setattr(app_module, "delete_run_evidence", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.memory_delete(_RUN_ID)
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["command"] == "memory.delete"
    assert payload["errors"][0]["code"] == "store-corrupt"
    assert str(_FAKE_PATH) in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# Residual loud paths (TOCTOU): real read chain, main()-routed
# ---------------------------------------------------------------------------


def _seed_then_corrupt(workspace: Path) -> tuple[MemoryEntry, Path]:
    """A real store whose ONE record is corrupted after being scanned."""
    store = create_project_store(workspace)
    entry = store_run_evidence(store, _make_record())
    matches = [
        p
        for p in (store.path / "memory" / "runs").rglob(RECORD_FILENAME)
        if p.parent.name == f"{RUN_DIR_PREFIX}{_RUN_ID}"
    ]
    assert len(matches) == 1
    matches[0].write_text('{"schema_version": 1, "run_refe', encoding="utf-8")
    return entry, matches[0]


def test_memory_show_toctou_corrupt_targeted_read_maps_store_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scan hit, then the REAL targeted read finds the record corrupt: the
    typed error maps to exit 5 at the verb seam. A/B sentinel for the
    Memory-side ``_read_record`` wrap — reverting it makes this observe the
    pre-S42 ``cli-error`` / exit 1 from ``main()``'s generic handler."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    entry, record_path = _seed_then_corrupt(workspace)
    # Freeze the scan at its pre-corruption result (the TOCTOU shape).
    monkeypatch.setattr(
        app_module, "list_run_history", lambda _store, skipped=None: [entry]
    )
    monkeypatch.chdir(workspace)

    with pytest.raises(SystemExit) as exc_info:
        app_module.main(["memory", "show", _RUN_ID, "--output", "json"])
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["command"] == "memory.show"
    assert payload["errors"][0]["code"] == "store-corrupt"
    assert str(record_path) in payload["errors"][0]["message"]


def test_memory_delete_toctou_corrupt_targeted_read_maps_store_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    entry, record_path = _seed_then_corrupt(workspace)
    monkeypatch.setattr(
        app_module, "list_run_history", lambda _store, skipped=None: [entry]
    )
    monkeypatch.chdir(workspace)

    with pytest.raises(SystemExit) as exc_info:
        app_module.main(["memory", "delete", _RUN_ID, "--output", "json"])
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["command"] == "memory.delete"
    assert payload["errors"][0]["code"] == "store-corrupt"
    assert str(record_path) in payload["errors"][0]["message"]
    # Nothing tombstoned: the corrupt record is still at its live location.
    assert record_path.is_file()


# ---------------------------------------------------------------------------
# Residual loud paths: per-verb catch seams (engine/workflow call raises)
# ---------------------------------------------------------------------------


def _assert_store_corrupt(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == command
    assert payload["errors"][0]["code"] == "store-corrupt"
    assert str(_FAKE_PATH) in payload["errors"][0]["message"]


def test_coverage_show_maps_engine_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(
        app_module, "list_run_history", lambda _s, skipped=None: [_make_memory_entry()]
    )
    monkeypatch.setattr(app_module, "get_coverage_facts", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show(_RUN_ID)
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "coverage.show")


def test_regression_latest_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(app_module, "derive_latest_regression", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_latest()
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "regression.latest")


def test_compare_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    baseline_id = "01BASELINE"
    monkeypatch.setattr(
        app_module,
        "list_run_history",
        lambda _s, skipped=None: [
            _make_memory_entry(baseline_id),
            _make_memory_entry(_RUN_ID),
        ],
    )
    monkeypatch.setattr(app_module, "build_compare_view", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.compare_cmd(baseline_id, _RUN_ID)
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "compare")


def test_localization_latest_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(
        app_module, "derive_latest_localization_with_flag_policy", _raise_corrupt
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "localization.latest")


def test_status_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    # `status` composes cache-only readers that still do targeted reads
    # (`get_coverage_facts` -> `retrieve_run_evidence`) — the TOCTOU loud
    # path is reachable from a pure-read verb too.
    monkeypatch.setattr(app_module, "build_status_view", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.status()
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "status")


def test_inspect_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(app_module, "build_inspect_view", _raise_corrupt)

    with pytest.raises(SystemExit) as exc_info:
        app_module.inspect_cmd(_RUN_ID)
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "inspect")


def test_replay_maps_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(
        app_module, "list_run_history", lambda _s, skipped=None: [_make_memory_entry()]
    )
    monkeypatch.setattr(app_module, "replay_run", _raise_corrupt_async)

    with pytest.raises(SystemExit) as exc_info:
        app_module.replay_cmd(_RUN_ID)
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "replay")


def test_run_cmd_maps_workflow_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(app_module, "run_target_in_store", _raise_corrupt_async)

    with pytest.raises(SystemExit) as exc_info:
        app_module.run_cmd("tests/")
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "run")


def test_test_cmd_maps_workflow_store_corruption_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    monkeypatch.setattr(app_module, "test_target_in_store", _raise_corrupt_async)

    with pytest.raises(SystemExit) as exc_info:
        app_module.test_cmd("tests/")
    assert exc_info.value.code == 5
    _assert_store_corrupt(capsys, "test")
