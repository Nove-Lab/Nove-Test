"""Subprocess E2E tests for `novetest inspect <run_id>`.

Closes Phase 2 DoD #3 ("`inspect` returns the Coverage section
populated") at the user-facing layer. The aggregated view inspects ONE
already-stored run: it executes nothing.

Strategy: `novetest run [--coverage] tests/` against the `pytest-coverage`
fixture to produce a persisted Run Record, then exercise `inspect`
against that run_id via real subprocess invocations.
"""

from __future__ import annotations

from pathlib import Path


def _run_id_of(envelope: dict, key: str = "entry_id") -> str:
    data = envelope["data"]
    assert isinstance(data, dict)
    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_id = memory_entry[key]
    assert isinstance(run_id, str) and len(run_id) == 26
    return run_id


def test_inspect_populates_coverage_section_for_coverage_run(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    run_result = run_cli_in(coverage_workspace, ["run", "--coverage", "tests/"])
    assert run_result.returncode == 0, run_result.stderr
    run_id = _run_id_of(run_result.envelope())

    result = run_cli_in(coverage_workspace, ["inspect", run_id])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["command"] == "inspect"
    assert envelope["ok"] is True

    data = envelope["data"]
    assert isinstance(data, dict)
    assert data["run_reference"]["run_id"] == run_id

    summary = data["run_summary"]
    assert isinstance(summary, dict)
    assert summary["status"] == "passed"
    assert summary["engine_name"] == "pytest"
    assert summary["ecosystem"] == "python"
    assert summary["tombstoned"] is False
    assert isinstance(summary["summary_counts"], dict)

    outcome = data["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["mapping_granularity"] == "per-test"
    assert outcome["run_reference"]["run_id"] == run_id
    assert outcome["summary"]["num_statements"] > 0

    sub_reports = data["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["coverage"] == "available"
    assert sub_reports["regression"] == "unavailable"
    assert sub_reports["localization"] == "unavailable"
    assert sub_reports["replay"] == "unavailable"


def test_inspect_coverage_section_unavailable_for_plain_run(
    coverage_workspace: Path, run_cli_in
) -> None:
    """A run executed WITHOUT `--coverage` has no `coverage_facts.json`.
    `inspect` for that run_id reports the Coverage section as
    ``kind: "unavailable"`` with reason ``missing-derived-facts``.
    """

    run_cli_in(coverage_workspace, ["init"])
    run_result = run_cli_in(coverage_workspace, ["run", "tests/"])
    assert run_result.returncode == 0, run_result.stderr
    run_id = _run_id_of(run_result.envelope())

    result = run_cli_in(coverage_workspace, ["inspect", run_id])
    assert result.returncode == 0, result.stderr

    data = result.envelope()["data"]
    assert isinstance(data, dict)
    outcome = data["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == "missing-derived-facts"
    assert outcome["run_reference"]["run_id"] == run_id
    assert data["sub_reports"]["coverage"] == "unavailable"


def test_inspect_returns_not_found_for_fake_run_id(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    result = run_cli_in(coverage_workspace, ["inspect", "fake-id"])
    # exit 2 = usage error per foundations.md §2; mirrors `memory show`.
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["command"] == "inspect"
    errors = envelope["errors"]
    assert isinstance(errors, list) and errors
    assert errors[0]["code"] == "not-found"


def test_inspect_in_uninitialized_tree_reports_uninitialized(
    coverage_workspace: Path, run_cli_in
) -> None:
    """No ancestor `.novetest/` → structured `uninitialized` envelope,
    exit 2, no traceback (mirror `memory show`)."""

    # `coverage_workspace` is materialized but NOT `init`-ed here.
    result = run_cli_in(coverage_workspace, ["inspect", "01ANYRUNIDANYRUNIDANYRUNID"])
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["command"] == "inspect"
    assert envelope["errors"][0]["code"] == "uninitialized"


def test_inspect_remains_available_for_tombstoned_run(
    coverage_workspace: Path, run_cli_in
) -> None:
    """A tombstoned run is still inspectable — the Run Reference stays
    resolvable for Evidence Citation (mirror `memory show`)."""

    run_cli_in(coverage_workspace, ["init"])
    run_result = run_cli_in(coverage_workspace, ["run", "--coverage", "tests/"])
    assert run_result.returncode == 0, run_result.stderr
    run_id = _run_id_of(run_result.envelope())

    delete_result = run_cli_in(coverage_workspace, ["memory", "delete", run_id])
    assert delete_result.returncode == 0, delete_result.stderr

    result = run_cli_in(coverage_workspace, ["inspect", run_id])
    assert result.returncode == 0, result.stderr
    data = result.envelope()["data"]
    assert isinstance(data, dict)
    assert data["run_reference"]["run_id"] == run_id
    assert data["run_summary"]["tombstoned"] is True
    # Coverage facts derived before the tombstone remain readable.
    assert data["coverage_outcome"]["kind"] == "fact-set"
