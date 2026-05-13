"""CLI subprocess integration tests for the Phase 1 lifecycle.

`init → run → memory list → memory show → memory delete → status` exercised
through the real ``novetest`` console script against fixture projects. The
shape assertions here back up the Phase 1 DoD bullets in
``design/implementation-plan/delivery-phasing.md`` that say "novetest <X>
--output json returns ...".
"""

from __future__ import annotations

from pathlib import Path


def test_init_run_list_show_delete_lifecycle(
    basic_workspace: Path, run_cli_in
) -> None:
    init_result = run_cli_in(basic_workspace, ["init"])
    assert init_result.returncode == 0, init_result.stderr
    init_envelope = init_result.envelope()
    assert init_envelope["command"] == "init"
    assert init_envelope["ok"] is True
    init_data = init_envelope["data"]
    assert isinstance(init_data, dict)
    readiness = init_data["engine_readiness"]
    assert isinstance(readiness, dict)
    assert readiness["state"] == "ready"
    assert readiness["engine"] == "pytest"

    # `run` against a passing fixture → exit 0, status passed.
    run_result = run_cli_in(basic_workspace, ["run"])
    assert run_result.returncode == 0, run_result.stderr
    run_envelope = run_result.envelope()
    run_data = run_envelope["data"]
    assert isinstance(run_data, dict)
    memory_entry = run_data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    assert run_record["status"] == "passed"
    assert run_record["summary_counts"]["passed"] == 3
    run_reference = run_record["run_reference"]
    assert isinstance(run_reference, dict)
    run_id = run_reference["run_id"]
    assert isinstance(run_id, str)
    assert len(run_id) == 26

    list_result = run_cli_in(basic_workspace, ["memory", "list"])
    assert list_result.returncode == 0, list_result.stderr
    list_envelope = list_result.envelope()
    list_data = list_envelope["data"]
    assert isinstance(list_data, dict)
    assert list_data["count"] == 1
    entries = list_data["entries"]
    assert isinstance(entries, list)
    assert isinstance(entries[0], dict)
    listed_record = entries[0]["run_record"]
    assert isinstance(listed_record, dict)
    listed_reference = listed_record["run_reference"]
    assert isinstance(listed_reference, dict)
    assert listed_reference["run_id"] == run_id

    show_result = run_cli_in(basic_workspace, ["memory", "show", run_id])
    assert show_result.returncode == 0, show_result.stderr
    show_entry = show_result.envelope()["data"]
    assert isinstance(show_entry, dict)
    show_memory_entry = show_entry["memory_entry"]
    assert isinstance(show_memory_entry, dict)
    assert show_memory_entry["tombstoned_at"] is None

    delete_result = run_cli_in(basic_workspace, ["memory", "delete", run_id])
    assert delete_result.returncode == 0, delete_result.stderr
    delete_entry = delete_result.envelope()["data"]
    assert isinstance(delete_entry, dict)
    delete_memory_entry = delete_entry["memory_entry"]
    assert isinstance(delete_memory_entry, dict)
    assert delete_memory_entry["tombstoned_at"] is not None
    delete_record = delete_memory_entry["run_record"]
    assert isinstance(delete_record, dict)
    assert delete_record["status"] == "tombstoned"

    # After delete, `memory show` still resolves the run (tombstoned).
    show_again = run_cli_in(basic_workspace, ["memory", "show", run_id])
    assert show_again.returncode == 0
    second_entry = show_again.envelope()["data"]
    assert isinstance(second_entry, dict)
    second_memory_entry = second_entry["memory_entry"]
    assert isinstance(second_memory_entry, dict)
    assert second_memory_entry["tombstoned_at"] is not None


def test_run_with_failing_fixture_returns_exit_code_three(
    failing_workspace: Path, run_cli_in
) -> None:
    run_cli_in(failing_workspace, ["init"])
    result = run_cli_in(failing_workspace, ["run"])
    # exit 3 = the user's tests failed (NOT a Nove Test failure).
    assert result.returncode == 3, result.stderr
    envelope = result.envelope()
    data = envelope["data"]
    assert isinstance(data, dict)
    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    assert run_record["status"] == "failed"


def test_run_against_empty_workspace_is_engine_missing(
    empty_workspace: Path, run_cli_in
) -> None:
    init_envelope = run_cli_in(empty_workspace, ["init"]).envelope()
    init_data = init_envelope["data"]
    assert isinstance(init_data, dict)
    init_readiness = init_data["engine_readiness"]
    assert isinstance(init_readiness, dict)
    assert init_readiness["state"] == "engine-missing"

    result = run_cli_in(empty_workspace, ["run"])
    # exit 4 = engine missing/misconfigured (NFR-RUN-004).
    assert result.returncode == 4, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    errors = envelope["errors"]
    assert isinstance(errors, list) and errors
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"].startswith("engine-")


def test_operating_command_in_uninitialized_dir_returns_structured_envelope(
    tmp_path: Path, run_cli_in
) -> None:
    # No `init` run → no Project Store anywhere in the ancestor chain.
    workspace = tmp_path / "no-store"
    workspace.mkdir()
    result = run_cli_in(workspace, ["memory", "list"])
    # exit 2 = usage error per foundations.md §2.
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    errors = envelope["errors"]
    assert isinstance(errors, list) and errors
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"] == "uninitialized"


def test_status_in_initialized_empty_store_returns_zero_history(
    basic_workspace: Path, run_cli_in
) -> None:
    run_cli_in(basic_workspace, ["init"])
    result = run_cli_in(basic_workspace, ["status"])
    assert result.returncode == 0, result.stderr
    data = result.envelope()["data"]
    assert isinstance(data, dict)
    assert data["run_history_size"] == 0
    assert data["latest_run_reference"] is None
    sub_reports = data["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["coverage"] == "unavailable"
    assert sub_reports["regression"] == "unavailable"
    assert sub_reports["localization"] == "unavailable"
    assert sub_reports["replay"] == "unavailable"
