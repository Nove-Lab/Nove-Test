"""Subprocess E2E tests for the Phase 3 CLI surface.

Verbs covered:

- ``novetest regression compare <baseline> <target>``
- ``novetest regression latest``
- ``novetest compare <baseline> <target>``

Strategy: invoke ``novetest`` as a real subprocess against a tmp Project
Store seeded with two real ``RunRecord``s via the public Memory seam
(``store_run_evidence``), then exercise the three verbs and inspect the
emitted envelopes. The persisted ``regression_facts.json`` is exercised
through the engine's own cache path — no test-only mocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


_BASELINE_REF = RunReference(
    run_id="01CLIBASELINE000000000000A", created_at=1_700_000_000_000
)
_TARGET_REF = RunReference(
    run_id="01CLITARGET00000000000000B", created_at=1_700_000_001_000
)


def _build_two_runs(workspace: Path) -> Path:
    """Materialize a Project Store with two runs sharing the same target."""

    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    baseline = RunRecord(
        run_reference=_BASELINE_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="failed",
        started_at=_BASELINE_REF.created_at,
        completed_at=_BASELINE_REF.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=10),
            TestResult(node_id="tests/x.py::test_b", outcome="failed", duration_ms=12),
        ),
    )
    target = RunRecord(
        run_reference=_TARGET_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="passed",
        started_at=_TARGET_REF.created_at,
        completed_at=_TARGET_REF.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=9),
            TestResult(node_id="tests/x.py::test_b", outcome="passed", duration_ms=11),
        ),
    )
    store_run_evidence(store, baseline)
    store_run_evidence(store, target)
    return store.path.parent  # the workspace dir CLI should `cd` into


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
# Tests
# ---------------------------------------------------------------------------


def test_regression_compare_e2e_emits_fact_set(tmp_path: Path) -> None:
    workspace = _build_two_runs(tmp_path / "ws")
    code, envelope, stderr = _run_cli(
        workspace, ["regression", "compare", _BASELINE_REF.run_id, _TARGET_REF.run_id]
    )
    assert code == 0, stderr
    assert envelope["command"] == "regression.compare"
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    outcome = data["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    summary = outcome["summary"]
    assert isinstance(summary, dict)
    # Baseline had 1 fail + 1 pass; target has 2 passes → 1 fixed, 1 still_passing.
    assert summary["fixed"] == 1
    assert summary["still_passing"] == 1
    assert summary["regressed"] == 0
    # Envelope projection strips the persisted schema_version.
    assert "schema_version" not in outcome


def test_regression_latest_e2e_emits_fact_set(tmp_path: Path) -> None:
    workspace = _build_two_runs(tmp_path / "ws")
    code, envelope, stderr = _run_cli(workspace, ["regression", "latest"])
    assert code == 0, stderr
    assert envelope["command"] == "regression.latest"
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    outcome = data["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    # `derive_latest_regression` picks the latest two on the active target —
    # the baseline-newer pair we just persisted.
    assert outcome["baseline_run_reference"]["run_id"] == _BASELINE_REF.run_id
    assert outcome["target_run_reference"]["run_id"] == _TARGET_REF.run_id


def test_compare_e2e_emits_both_blocks(tmp_path: Path) -> None:
    workspace = _build_two_runs(tmp_path / "ws")
    code, envelope, stderr = _run_cli(
        workspace, ["compare", _BASELINE_REF.run_id, _TARGET_REF.run_id]
    )
    assert code == 0, stderr
    assert envelope["command"] == "compare"
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    # Both top-level data keys present.
    assert set(data.keys()) == {"regression_outcome", "coverage_delta"}
    regression = data["regression_outcome"]
    assert isinstance(regression, dict)
    assert regression["kind"] == "fact-set"
    # Neither run was executed with `--coverage`, so coverage_delta surfaces
    # the propagated unavailable from `compare_coverage_facts`.
    coverage = data["coverage_delta"]
    assert isinstance(coverage, dict)
    assert coverage["kind"] == "unavailable"
    assert coverage["reason"] == "missing-derived-facts"
