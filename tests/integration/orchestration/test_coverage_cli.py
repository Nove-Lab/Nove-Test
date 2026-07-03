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

from novetest.coverage.persistence import write_coverage_facts
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


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


def _seed_cargo_fact_set(coverage_workspace: Path) -> str:
    """Seed a cargo-test RunRecord + persisted CoverageFactSet in-process.

    The D5 engine-mismatch CLI case needs a second engine's facts in the
    same store. Running a real cargo toolchain here would make the test
    host-dependent; seeding through the same persistence surface the
    derive path uses (`store_run_evidence` + `write_coverage_facts`) is
    deterministic and exercises the identical read path
    (`compare_coverage_facts` → `get_coverage_facts`) in the subprocess.
    """
    store = get_project_store_state(coverage_workspace / ".novetest")
    ref = RunReference(
        run_id="01HCARGO00000000000000FACT", created_at=1_700_000_000_000
    )
    summary = CoverageSummary(
        num_statements=3,
        covered_statements=2,
        missing_statements=1,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=66.67,
    )
    fact_set = CoverageFactSet(
        run_reference=ref,
        engine_name="cargo-test",
        ecosystem="rust",
        mapping_granularity="aggregate",
        summary=summary,
        files=(
            FileCoverage(
                file_path="src/lib.rs",
                executed_lines=(1, 2),
                missing_lines=(3,),
                excluded_lines=(),
                executed_branches=(),
                missing_branches=(),
                summary=summary,
            ),
        ),
        derived_at=1_700_000_001_000,
    )
    store_run_evidence(
        store,
        RunRecord(
            run_reference=ref,
            target_expression="tests/",
            target_type="dir",
            engine_name="cargo-test",
            ecosystem="rust",
            status="passed",
            started_at=ref.created_at,
            artifact_paths={},
        ),
    )
    write_coverage_facts(store, fact_set)
    return ref.run_id


def test_coverage_diff_refuses_cross_engine_pair(
    coverage_workspace: Path, run_cli_in
) -> None:
    """`novetest coverage diff <pytest_run> <cargo_run>` → the D5 guard.

    Task 2026-07-03 coverage-compare-engine-guard acceptance criterion:
    the CLI surfaces `coverage_delta.kind == "unavailable"` with the new
    `engine-mismatch` reason — NO `CoverageDelta` is emitted for a
    cross-engine pair. The reason renders through the existing generic
    unavailable projection (`_coverage_delta_payload`) with zero CLI
    changes; this test pins that end-to-end.
    """
    run_cli_in(coverage_workspace, ["init"])
    pytest_run_id = _run_with_coverage(coverage_workspace, run_cli_in)
    cargo_run_id = _seed_cargo_fact_set(coverage_workspace)

    result = run_cli_in(
        coverage_workspace, ["coverage", "diff", pytest_run_id, cargo_run_id]
    )
    # Unavailable is NOT a CLI error (2026-05-16 decision constraint #3):
    # exit 0, ok: true — the verb succeeded; the refusal is the result.
    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "coverage.diff"
    assert envelope["ok"] is True

    delta = envelope["data"]["coverage_delta"]
    assert isinstance(delta, dict)
    assert delta["kind"] == "unavailable"
    assert delta["reason"] == "engine-mismatch"
    # Detail carries both engine names.
    assert "pytest" in delta["detail"]
    assert "cargo-test" in delta["detail"]
    # Pair-level reason names the baseline side (2026-07-03 amendment to
    # the 2026-05-16 envelope decision).
    assert delta["run_reference"]["run_id"] == pytest_run_id
    # No delta fields leak into the unavailable kind (constraint #1).
    assert "file_deltas" not in delta
    assert "files_added" not in delta
