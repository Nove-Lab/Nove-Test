"""End-to-end ``novetest reset --confirm`` round-trip via real subprocesses.

Lifecycle: seed a Project Store with one Run Record → ``novetest reset
--confirm`` → ``novetest status``. Asserts the wipe removed the run
(``items_removed.runs >= 1``), the store is re-initialized
(``store_state == "ready"``), and ``status`` reports an empty history.

The store is seeded directly via the Memory + engine persistence helpers
(no native test engine needed on the runner), mirroring
``test_status_inspect_consistency_e2e.py``. The destructive
``wipe_project_store`` primitive (Memory, landed at ``cfffa70``) is
exercised for real here — this is the binding round-trip the unit tests
mock out.
"""

from __future__ import annotations


def _seed_one_run(workspace) -> None:
    """Materialize a Project Store under ``workspace`` with a single run.

    The store carries an engine pin the way any post-anchored-pin ``init``
    leaves it (decision 2026-07-03-engine-selection-policy D1): ``reset``
    carries the pin across the wipe, so the seeded shape must carry one —
    the pin-less legacy shape is the D6 migration case, covered by the
    anchored-pin e2e suite instead.
    """
    from novetest.memory.project_store import (
        create_project_store,
        set_pinned_engine,
    )
    from novetest.memory.store import store_run_evidence
    from novetest.models.run_record import RunRecord
    from novetest.models.run_reference import RunReference
    from novetest.models.test_result import TestResult

    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")
    ref = RunReference(
        run_id="01D6RESET000000000000000A", created_at=1_700_000_000_000
    )
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status="passed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(
                node_id="tests/x.py::test_ok", outcome="passed", duration_ms=5
            ),
        ),
    )
    store_run_evidence(store, record)


def test_reset_round_trip_wipes_runs_and_reinitializes(isolated_cwd, run_cli) -> None:
    _seed_one_run(isolated_cwd)

    # Sanity: the seeded run is visible before the reset.
    pre = run_cli(["memory", "list", "--output", "json"])
    assert pre.returncode == 0, pre.stderr
    assert pre.envelope()["data"]["count"] == 1

    # ----- novetest reset --confirm -----
    reset = run_cli(["reset", "--confirm", "--output", "json"])
    assert reset.returncode == 0, reset.stderr
    env = reset.envelope()
    assert env["schema"] == "novetest/v1"
    assert env["command"] == "reset"
    assert env["ok"] is True
    data = env["data"]
    assert data["store_state"] == "ready"
    assert data["items_removed"]["runs"] >= 1
    assert "previous_initialized_at" in data
    assert "initialized_at" in data

    # ----- novetest status: store is empty after the wipe + re-init -----
    status = run_cli(["status", "--output", "json"])
    assert status.returncode == 0, status.stderr
    assert status.envelope()["data"]["run_history_size"] == 0


def test_reset_without_confirm_is_a_usage_error(isolated_cwd, run_cli) -> None:
    """``reset`` without ``--confirm`` refuses (exit 2) and does NOT wipe."""
    _seed_one_run(isolated_cwd)

    result = run_cli(["reset", "--output", "json"])
    assert result.returncode == 2
    env = result.envelope()
    assert env["ok"] is False
    assert env["errors"][0]["code"] == "confirm-required"

    # The store is untouched — the seeded run is still listed.
    after = run_cli(["memory", "list", "--output", "json"])
    assert after.envelope()["data"]["count"] == 1
