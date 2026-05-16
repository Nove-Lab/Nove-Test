"""Subprocess E2E tests for `novetest coverage show` / `coverage diff`.

The prior `--coverage` slice introduced the persistence path; this slice
adds the read-back surfaces. Closes Phase 2 DoD #2 ("`novetest coverage
diff` returns structured deltas with stable Code Location identity") at
the user-facing layer, and is the first CLI surface where the
``kind: "unavailable"`` branch becomes reachable end-to-end (Manual Test
flagged this as a coverage gap in the prior cycle).

Strategy: run `novetest run --coverage tests/` twice against the
`pytest-coverage` fixture to produce two persisted Run Records with
`coverage_facts.json` on disk, then exercise `show` and `diff` against
those run_ids via real subprocess invocations.
"""

from __future__ import annotations

from pathlib import Path


def _run_with_coverage(coverage_workspace: Path, run_cli_in) -> str:
    """Execute `novetest run --coverage tests/` and return the new run_id."""

    result = run_cli_in(coverage_workspace, ["run", "--coverage", "tests/"])
    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    data = envelope["data"]
    assert isinstance(data, dict)
    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_id = memory_entry["entry_id"]
    assert isinstance(run_id, str) and len(run_id) == 26
    return run_id


def test_coverage_show_returns_fact_set_for_persisted_run(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    run_id = _run_with_coverage(coverage_workspace, run_cli_in)

    result = run_cli_in(coverage_workspace, ["coverage", "show", run_id])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["command"] == "coverage.show"
    assert envelope["ok"] is True

    data = envelope["data"]
    assert isinstance(data, dict)
    outcome = data["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["mapping_granularity"] == "per-test"
    assert outcome["run_reference"]["run_id"] == run_id

    summary = outcome["summary"]
    assert isinstance(summary, dict)
    assert isinstance(summary["percent_covered"], (int, float))
    assert summary["num_statements"] > 0


def test_coverage_show_emits_unavailable_for_run_without_coverage(
    coverage_workspace: Path, run_cli_in
) -> None:
    """A run that completed WITHOUT `--coverage` has no `coverage_facts.json`
    on disk. `coverage show` for that run_id must surface
    ``kind: "unavailable"`` with reason ``missing-derived-facts`` — the
    first user-typable command path that exercises this branch end-to-end.
    """

    run_cli_in(coverage_workspace, ["init"])
    # Run WITHOUT --coverage so the derive hook never fires.
    result = run_cli_in(coverage_workspace, ["run", "tests/"])
    assert result.returncode == 0, result.stderr
    data = result.envelope()["data"]
    assert isinstance(data, dict)
    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_id = memory_entry["entry_id"]

    show_result = run_cli_in(coverage_workspace, ["coverage", "show", run_id])
    assert show_result.returncode == 0, show_result.stderr
    outcome = show_result.envelope()["data"]["coverage_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == "missing-derived-facts"
    assert outcome["run_reference"]["run_id"] == run_id


def test_coverage_show_returns_not_found_for_fake_run_id(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    result = run_cli_in(coverage_workspace, ["coverage", "show", "fake-id"])
    # exit 2 = usage error per foundations.md §2; mirrors `memory show` behavior.
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["command"] == "coverage.show"
    errors = envelope["errors"]
    assert isinstance(errors, list) and errors
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"] == "not-found"


def test_coverage_diff_returns_delta_between_two_persisted_runs(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    id1 = _run_with_coverage(coverage_workspace, run_cli_in)
    id2 = _run_with_coverage(coverage_workspace, run_cli_in)
    assert id1 != id2

    result = run_cli_in(coverage_workspace, ["coverage", "diff", id1, id2])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["command"] == "coverage.diff"
    assert envelope["ok"] is True

    delta = envelope["data"]["coverage_delta"]
    assert isinstance(delta, dict)
    assert delta["kind"] == "delta"
    assert delta["baseline_run_reference"]["run_id"] == id1
    assert delta["target_run_reference"]["run_id"] == id2
    assert delta["baseline_granularity"] == "per-test"
    assert delta["target_granularity"] == "per-test"
    # Same fixture run twice → both summaries report the same coverage.
    assert (
        delta["summary_before"]["percent_covered"]
        == delta["summary_after"]["percent_covered"]
    )
    # No file changes between identical runs.
    assert delta["files_added"] == []
    assert delta["files_removed"] == []
    # `file_deltas` is compact: files with no actual transition are omitted.
    assert isinstance(delta["file_deltas"], list)


def test_coverage_diff_emits_unavailable_when_one_side_lacks_facts(
    coverage_workspace: Path, run_cli_in
) -> None:
    """One run has facts (--coverage), the other does not. The propagated
    `CoverageUnavailable` from `compare_coverage_facts` surfaces as
    `coverage_delta.kind == "unavailable"`.
    """

    run_cli_in(coverage_workspace, ["init"])
    id_with = _run_with_coverage(coverage_workspace, run_cli_in)
    # The second run is plain (no --coverage), so it has no facts on disk.
    plain_result = run_cli_in(coverage_workspace, ["run", "tests/"])
    assert plain_result.returncode == 0
    plain_data = plain_result.envelope()["data"]
    assert isinstance(plain_data, dict)
    plain_memory_entry = plain_data["memory_entry"]
    assert isinstance(plain_memory_entry, dict)
    id_without = plain_memory_entry["entry_id"]

    result = run_cli_in(coverage_workspace, ["coverage", "diff", id_with, id_without])
    assert result.returncode == 0, result.stderr
    delta = result.envelope()["data"]["coverage_delta"]
    assert isinstance(delta, dict)
    assert delta["kind"] == "unavailable"
    assert delta["reason"] == "missing-derived-facts"
    assert delta["run_reference"]["run_id"] == id_without


def test_coverage_diff_returns_not_found_for_fake_run_id(
    coverage_workspace: Path, run_cli_in
) -> None:
    run_cli_in(coverage_workspace, ["init"])
    id1 = _run_with_coverage(coverage_workspace, run_cli_in)

    result = run_cli_in(coverage_workspace, ["coverage", "diff", id1, "fake-id"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["command"] == "coverage.diff"
    assert envelope["errors"][0]["code"] == "not-found"
