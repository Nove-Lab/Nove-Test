"""End-to-end: ``novetest test --reruns N`` activates ``flaky_suspected``.

Decision ``2026-06-25-test-reruns-flag-and-replay-integration`` exit
condition: the category "demonstrably fires from a failed-test invocation"
through the single user command. Uses the ``flaky-python`` fixture (counter
parity: even invocation → pass, odd → fail) with the counter pre-seeded to
``1`` so the ORIGINAL run fails (odd) and the first replay rerun passes
(even) — a divergence the Replay classifier labels ``inconsistent``.

Invocation ledger for ``--reruns 2`` (each native run increments the
on-disk counter):

====================  ==========  =======
execution             invocation  outcome
====================  ==========  =======
original ``test``     1 (odd)     failed
replay rerun #1       2 (even)    passed   ← diverges from the original
replay rerun #2       3 (odd)     failed
====================  ==========  =======

→ ``reruns_total=2``, ``reruns_failed=1``, focal ``test_id`` set,
classification ``inconsistent`` → one ``flaky_suspected`` recommendation.

Placement note: the brief pins ``tests/integration/`` root; this file lives
under ``tests/integration/cli/`` per the Orchestration charter (CLI
lifecycle tests invoke ``novetest`` as a real subprocess via the shared
``run_cli`` fixture) — same carried-forward PM review item as the reset
cycle's e2e.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from syrupy.assertion import SnapshotAssertion


_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"
_COUNTER_FILENAME = ".flaky_invocations"
_FLAKY_TEST_ID = "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"


def _materialize_flaky_workspace(workspace: Path, *, seed: str) -> None:
    """Copy the ``flaky-python`` fixture INTO ``workspace`` and seed the
    invocation counter (``"1"`` → the next run is odd → fails)."""
    shutil.copytree(
        _FIXTURE_ROOT / "flaky-python",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
        dirs_exist_ok=True,
    )
    (workspace / _COUNTER_FILENAME).write_text(seed, encoding="utf-8")


def _distill_recommendation(rec: dict[str, Any]) -> dict[str, Any]:
    """Project a recommendation onto its run-independent shape.

    ULID-bearing fields (``recommendation_id``, ``run_reference`` values)
    change per run; category / priority / slots-minus-refs / citation
    kinds+selectors are byte-stable and snapshot-pinned.
    """
    slots = {k: v for k, v in rec["slots"].items() if k != "run_reference"}
    citations = [
        {"kind": c["kind"], "selector": c.get("selector", {})}
        for c in rec["evidence_citations"]
    ]
    return {
        "category": rec["category"],
        "priority": rec["priority"],
        "summary": re.sub(r"01[0-9A-HJKMNP-TV-Z]{24}", "<run_id>", rec["summary"]),
        "slots": slots,
        "citations": citations,
    }


def test_reruns_flag_produces_flaky_suspected_end_to_end(
    isolated_cwd: Path, run_cli: Any, snapshot: SnapshotAssertion
) -> None:
    _materialize_flaky_workspace(isolated_cwd, seed="1")

    init = run_cli(["init"])
    assert init.returncode == 0, init.stdout + init.stderr

    result = run_cli(["test", "--reruns", "2"])
    # Original run failed (odd invocation) → EXIT_USER_TESTS_FAILED, ok true
    # (transport succeeded; replay outcomes never affect the exit code).
    assert result.returncode == 3, result.stdout + result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is True
    data = envelope["data"]

    # Decision §"Envelope": the ONLY stage-eligibility difference vs the
    # default path is replay transitioning "not_run" → "available".
    assert data["stage_eligibility"]["replay"] == "available"

    flaky = [
        r
        for r in data["recommendations"]
        if r["category"] == "flaky_suspected"
    ]
    assert len(flaky) == 1, (
        f"expected exactly one flaky_suspected; got "
        f"{[r['category'] for r in data['recommendations']]}"
    )
    rec = flaky[0]
    assert rec["slots"]["test_id"] == _FLAKY_TEST_ID
    assert rec["slots"]["reruns_total"] == 2
    assert rec["slots"]["reruns_failed"] == 1

    # REQ-ORCH-005: carries a replay_result citation resolvable on disk.
    replay_cites = [
        c for c in rec["evidence_citations"] if c["kind"] == "replay_result"
    ]
    assert len(replay_cites) == 1
    assert replay_cites[0]["selector"]["classification"] == "inconsistent"

    run_id = data["run_reference"]["run_id"]
    result_path = (
        isolated_cwd
        / ".novetest"
        / "replay"
        / "results"
        / f"run_{run_id}"
        / "replay_result.json"
    )
    assert result_path.is_file(), f"persisted Replay Result missing: {result_path}"

    # Replay-execution runs persist as first-class Memory Entries
    # (original + 2 reruns), exactly like the standalone replay verb's.
    listed = run_cli(["memory", "list"])
    assert listed.returncode == 0
    assert listed.envelope()["data"]["count"] == 3

    # Snapshot the run-independent projection of the recommendation.
    assert _distill_recommendation(rec) == snapshot


def test_negative_reruns_rejected_end_to_end(
    isolated_cwd: Path, run_cli: Any
) -> None:
    """``--reruns=-1`` → exit 2 / ``invalid-flag`` through real argv parsing
    (decision §"Error paths"); no run is executed."""
    _materialize_flaky_workspace(isolated_cwd, seed="1")
    init = run_cli(["init"])
    assert init.returncode == 0, init.stdout + init.stderr

    result = run_cli(["test", "--reruns=-1"])
    assert result.returncode == 2, result.stdout + result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "invalid-flag"
    # The counter proves no native run executed: still at the seed value.
    assert (isolated_cwd / _COUNTER_FILENAME).read_text(encoding="utf-8") == "1"
