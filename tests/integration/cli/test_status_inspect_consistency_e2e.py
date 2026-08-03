"""Subprocess E2E test cross-checking ``status`` ↔ ``inspect`` ↔ direct-verb
agreement on engine-fact availability — the Defect-6 contract.

Reproduces Manual Test 2026-06-01's Scenario H (cargo aggregate run)
with the OS-portable pytest equivalent: a Project Store is seeded
directly via the Memory + engine persistence helpers (no need for a
cargo toolchain on the test runner) with one prior + one latest run on
the same target, with coverage facts + localization findings + a
cached regression pair file all persisted on disk. Then three real
``novetest`` subprocess invocations are issued and cross-checked:

1. ``novetest status`` → ``sub_reports.coverage`` /
   ``sub_reports.localization`` / ``sub_reports.regression`` ALL
   "available"; ``sub_reports.replay`` == "unavailable".
2. ``novetest inspect <latest_run_id>`` → ``coverage_outcome.kind`` /
   ``localization_outcome.kind`` / ``regression_outcome.kind`` ALL
   "fact-set"; ``sub_reports`` agrees with #1.
3. ``novetest localization <latest_run_id>`` →
   ``localization_outcome.kind == "fact-set"`` (direct-verb agreement).

The sub-observation pin: ``inspect.coverage_outcome.summary.percent_covered``
is the canonical path (frozen by
``decisions/2026-05-16-coverage-outcome-envelope-shape.md``); there is
NO top-level ``percent_covered`` key on ``coverage_outcome``. Pre-fix,
``dict.get("percent_covered")`` against the top level returned ``None``
because the field doesn't exist — Manual Test surfaced this as a
"vestigial field" suspicion. The disposition is "explained as
intended": the wire shape nests it under ``summary``. This test pins
both halves: the canonical nested path returns the expected value AND
the top-level key is genuinely absent (regression-pin against later
introduction as a wrong-path read).

Granularity choice: the pytest path emits per-test-granular coverage,
which exercises the same retrieval call (``get_coverage_facts``) the
cargo aggregate path uses; granularity-independence is pinned at the
unit-test level (see
``test_status.py::test_defect6_aggregate_granularity_coverage_facts_marks_coverage_available``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.persistence import write_localization_findings
from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.persistence import write_regression_facts


_PRIOR_REF = RunReference(
    run_id="01D6PRIOR000000000000000A", created_at=1_700_000_000_000
)
_LATEST_REF = RunReference(
    run_id="01D6LATEST00000000000000A", created_at=1_700_000_001_000
)


def _seed_store_with_all_facts(workspace: Path) -> Path:
    """Materialize a Project Store with two runs + coverage + localization
    + regression all persisted on disk.

    Returns the workspace dir (parent of ``.novetest``) the CLI should
    ``cd`` into. The persisted shapes pass each engine's ``from_dict``
    round-trip so the CLI's cache reads succeed against real on-disk
    bytes — no test-only mocks.
    """

    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)

    # Two passing runs on the same target so the regression pair is well-
    # defined (most-recent strictly-older sibling on ``tests/`` → prior).
    # The CLI's ``status`` workflow's pair-selection mirrors this.
    prior = RunRecord(
        run_reference=_PRIOR_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="failed",
        started_at=_PRIOR_REF.created_at,
        completed_at=_PRIOR_REF.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_buggy", outcome="failed", duration_ms=10),
        ),
    )
    latest = RunRecord(
        run_reference=_LATEST_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="failed",
        started_at=_LATEST_REF.created_at,
        completed_at=_LATEST_REF.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_buggy", outcome="failed", duration_ms=11),
        ),
    )
    store_run_evidence(store, prior)
    store_run_evidence(store, latest)

    # Coverage facts for the latest run — per-test granularity + a known
    # ``percent_covered`` so the sub-observation pin can assert against a
    # specific value (85.71, mirroring Manual Test's reproduction).
    summary = CoverageSummary(
        num_statements=14,
        covered_statements=12,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=2,
        missing_branches=0,
        percent_covered=85.71,
    )
    file_coverage = FileCoverage(
        file_path="src/calc.py",
        executed_lines=(1, 2, 3),
        missing_lines=(4,),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=summary,
    )
    coverage_fact_set = CoverageFactSet(
        run_reference=_LATEST_REF,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=summary,
        files=(file_coverage,),
        derived_at=_LATEST_REF.created_at + 1_500,
    )
    write_coverage_facts(store, coverage_fact_set)

    # Localization findings for the latest run — top-1 is ``calc.buggy``
    # with Ochiai 1.0 (the per-test SBFL shape; granularity-matching
    # convention pinned by the engine).
    loc = CodeLocation(
        kind="symbol",
        file="src/calc.py",
        symbol="buggy",
        line_range=(4, 5),
        primary_line=5,
        evidence_lines=(5,),
    )
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=_LATEST_REF,
        selector={"test_id": "tests/x.py::test_buggy", "outcome": "failed"},
    )
    localization_entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=loc,
        score_raw=1.0,
        score_normalized=1.0,
        formula="ochiai",
        alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
        related_failed_tests=("tests/x.py::test_buggy",),
        evidence_citations=(citation,),
    )
    finding = LocalizationFinding(
        run_reference=_LATEST_REF,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10,
        entries=(localization_entry,),
        derived_at=_LATEST_REF.created_at + 2_000,
        # Load-bearing since the row-43 stale-build detector (2026-08-03):
        # every SBFL-mode finding THIS build persists carries the four
        # ``test_file_*`` keys (``localization/derive.py::
        # _exclusion_metadata``), so a seed without them is not a
        # current-build artifact — it is a pre-``088091e`` one, and the
        # ``localization`` verb would (correctly) invalidate it and
        # re-derive instead of serving it. This seed exists to exercise
        # the Defect-6 availability agreement, so it must look like what
        # this build writes.
        metadata={
            "changed_files_count": None,
            "regression_reweighted": None,
            "test_file_locations_excluded": 0,
            "test_file_exclusion_reverted": False,
            "test_file_exclusion_basis": "exact",
            "test_file_locations_suppressed": [],
        },
    )
    write_localization_findings(store, finding)

    # Regression facts for the (prior, latest) pair — minimal shape since
    # both runs had the same single failing test (still_failing=1).
    regression_fact_set = RegressionFactSet(
        baseline_run_reference=_PRIOR_REF,
        target_run_reference=_LATEST_REF,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=_LATEST_REF.created_at + 2_500,
        summary=RegressionSummary(
            regressed=0,
            fixed=0,
            still_failing=1,
            still_passing=0,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=1,
            total_target_tests=1,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )
    write_regression_facts(store, regression_fact_set)

    return store.path.parent  # workspace dir the CLI should `cd` into


def _run_cli(workspace: Path, args: list[str]) -> tuple[int, dict[str, object], str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload: dict[str, object] = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, payload, result.stderr


# ---------------------------------------------------------------------------
# E2E: status ↔ inspect ↔ direct localization verb agree on availability.
# Reproduces Manual Test 2026-06-01 Scenario H against an OS-portable
# pytest-shaped seed. Defect-6 regression pin.
# ---------------------------------------------------------------------------


def test_status_inspect_localization_agree_on_availability(tmp_path: Path) -> None:
    """Status ↔ inspect ↔ direct verb all agree that every cached engine's
    facts are available for the latest run.

    Pre-fix: ``status.sub_reports.coverage`` / ``.localization`` /
    ``.regression`` all reported ``"unavailable"`` despite the on-disk
    facts being present and ``inspect`` reading them correctly. Post-fix
    all three sources of truth agree.
    """

    workspace = _seed_store_with_all_facts(tmp_path / "ws")

    # ----- novetest status -----
    code, status_env, stderr = _run_cli(workspace, ["status"])
    assert code == 0, f"status exit {code}, stderr={stderr!r}"
    assert status_env["ok"] is True
    assert status_env["command"] == "status"
    status_data = status_env["data"]
    assert isinstance(status_data, dict)
    latest_ref = status_data["latest_run_reference"]
    assert isinstance(latest_ref, dict)
    assert latest_ref["run_id"] == _LATEST_REF.run_id
    sub_reports = status_data["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports == {
        "coverage": "available",
        "regression": "available",
        "localization": "available",
        "replay": "unavailable",
    }, f"Defect-6 contract violation: status.sub_reports = {sub_reports!r}"
    assert status_data["run_history_size"] == 2

    # ----- novetest inspect <latest> -----
    code, inspect_env, stderr = _run_cli(
        workspace, ["inspect", _LATEST_REF.run_id]
    )
    assert code == 0, f"inspect exit {code}, stderr={stderr!r}"
    assert inspect_env["ok"] is True
    assert inspect_env["command"] == "inspect"
    inspect_data = inspect_env["data"]
    assert isinstance(inspect_data, dict)

    coverage_outcome = inspect_data["coverage_outcome"]
    assert isinstance(coverage_outcome, dict)
    assert coverage_outcome["kind"] == "fact-set"

    localization_outcome = inspect_data["localization_outcome"]
    assert isinstance(localization_outcome, dict)
    assert localization_outcome["kind"] == "fact-set"

    regression_outcome = inspect_data["regression_outcome"]
    assert isinstance(regression_outcome, dict)
    assert regression_outcome["kind"] == "fact-set"

    inspect_sub_reports = inspect_data["sub_reports"]
    assert isinstance(inspect_sub_reports, dict)
    # Cross-source-of-truth: inspect agrees with status (Defect-6 contract).
    assert inspect_sub_reports == sub_reports

    # ----- novetest localization <latest> (direct verb) -----
    code, loc_env, stderr = _run_cli(
        workspace, ["localization", _LATEST_REF.run_id]
    )
    assert code == 0, f"localization exit {code}, stderr={stderr!r}"
    assert loc_env["ok"] is True
    assert loc_env["command"] == "localization"
    loc_data = loc_env["data"]
    assert isinstance(loc_data, dict)
    direct_outcome = loc_data["localization_outcome"]
    assert isinstance(direct_outcome, dict)
    assert direct_outcome["kind"] == "fact-set"
    # Direct verb agrees with both status and inspect.
    assert direct_outcome["run_reference"]["run_id"] == _LATEST_REF.run_id


# ---------------------------------------------------------------------------
# Sub-observation pin: percent_covered lives at coverage_outcome.summary.*,
# NOT at coverage_outcome.* top-level. Manual Test 2026-06-01 suspected a
# vestigial top-level field; disposition is "explained as intended" —
# the wire shape nests it under summary per the 2026-05-16 envelope
# decision. This test pins both halves to defend against a future patch
# accidentally introducing a wrong-path read.
# ---------------------------------------------------------------------------


def test_inspect_coverage_percent_covered_lives_under_summary_only(
    tmp_path: Path,
) -> None:
    """``coverage_outcome.summary.percent_covered`` is canonical;
    ``coverage_outcome.percent_covered`` does NOT exist."""

    workspace = _seed_store_with_all_facts(tmp_path / "ws_sub_obs")
    code, envelope, stderr = _run_cli(
        workspace, ["inspect", _LATEST_REF.run_id]
    )
    assert code == 0, f"inspect exit {code}, stderr={stderr!r}"
    data = envelope["data"]
    assert isinstance(data, dict)
    coverage_outcome = data["coverage_outcome"]
    assert isinstance(coverage_outcome, dict)

    # Canonical path returns the seeded value.
    summary = coverage_outcome["summary"]
    assert isinstance(summary, dict)
    assert summary["percent_covered"] == 85.71

    # Top-level field is genuinely absent — regression pin against later
    # introduction as a wrong-path read.
    assert "percent_covered" not in coverage_outcome, (
        "Defect-6 sub-observation regression: coverage_outcome top-level "
        "must NOT carry a `percent_covered` field — it lives under "
        "`.summary.percent_covered` per the 2026-05-16 envelope decision."
    )
