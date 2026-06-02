"""End-to-end Replay engine: the three Phase 5 DoD bullets.

Drives the real Run path (`run/execute_with_engine_context` via `replay_run`)
against materialized fixture projects — real pytest subprocesses, no mocks:

1. ``flaky-python`` + ``--reruns=5`` → ``inconsistent`` (DoD bullet 1,
   ``delivery-phasing.md:221``).
2. ``pytest-basic`` + ``--reruns=3`` → ``reproducible`` (DoD bullet 2,
   ``delivery-phasing.md:222``). Also pins NFR-REP-002 (classify + persist
   within 3 s once the replay Run Records are on disk).
3. ``pytest-basic`` with its test file deleted before replay →
   ``unable_to_replay`` (DoD bullet 3, ``delivery-phasing.md:223``). The
   stale-target scenario reuses ``pytest-basic`` (mutating the tmp copy)
   per the brief §4 "Alternative" — no dedicated fixture is added; the
   deleted-target run errors (pytest exit 5, no tests collected), which the
   classifier maps to ``unable_to_replay``.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from novetest.memory import list_run_history, retrieve_run_evidence
from novetest.models.replay_result import REPLAY_UNABLE_REASONS, ReplayResult
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.inspect import build_inspect_view
from novetest.orchestration.workflows.run import run_target_in_store
from novetest.replay import (
    classify_replay_consistency,
    get_replay_result,
    replay_run,
    write_replay_result,
)


_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"

_FLAKY_NODE_ID = "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"


def _materialize(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


async def test_flaky_python_with_reruns_5_yields_inconsistent(tmp_path: Path) -> None:
    """DoD bullet 1: ``novetest replay <flaky> --reruns=5`` → ``inconsistent``."""

    workspace = _materialize("flaky-python", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )
    original_ref = outcome.memory_entry.run_record.run_reference
    # Invocation 0 is even → the original run passes (deterministic capture).
    assert outcome.memory_entry.run_record.status == "passed"

    result = await replay_run(init.store, original_ref, reruns=5)

    assert isinstance(result, ReplayResult)
    assert result.classification == "inconsistent"
    assert result.reruns_total == 5
    assert result.reruns_failed >= 1
    # A single test is responsible for the divergence → it is the focal test.
    assert result.test_id == _FLAKY_NODE_ID
    assert result.reason is None
    assert len(result.per_rerun_outcomes) == 5

    # The replay-execution runs are first-class Memory Entries.
    assert result.replayed_run_reference is not None
    replayed_entry = retrieve_run_evidence(init.store, result.replayed_run_reference)
    assert replayed_entry.run_record.run_reference == result.replayed_run_reference
    # Five replay runs were persisted in addition to the original.
    history_ids = {
        e.run_record.run_reference.run_id for e in list_run_history(init.store)
    }
    assert original_ref.run_id in history_ids
    assert len(history_ids) == 6  # 1 original + 5 reruns

    # Cache round-trip (NFR-REP-001 + NFR-ORCH-002): the persisted result is
    # byte-identical to the engine's return value.
    cached = get_replay_result(init.store, original_ref)
    assert isinstance(cached, ReplayResult)
    assert cached.to_dict() == result.to_dict()

    # ``inspect`` surfaces the Replay section (§7.4): the discriminated block
    # + the flipped sub-report marker.
    view = build_inspect_view(init.store, original_ref.run_id)
    assert view is not None
    inspect_dict = view.to_dict()
    replay_block = inspect_dict["replay_outcome"]
    assert isinstance(replay_block, dict)
    assert replay_block["kind"] == "replay-result"
    assert replay_block["classification"] == "inconsistent"
    sub_reports = inspect_dict["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["replay"] == "available"


async def test_pytest_basic_yields_reproducible(tmp_path: Path) -> None:
    """DoD bullet 2: ``novetest replay <basic>`` (reruns>1) → ``reproducible``.

    Also pins NFR-REP-002: classify + persist within 3 s once the replay
    Run Records are available on disk (the budget excludes subprocess time).
    """

    workspace = _materialize("pytest-basic", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store("tests/", init.store, timeout=120.0)
    original_ref = outcome.memory_entry.run_record.run_reference

    result = await replay_run(init.store, original_ref, reruns=3)

    assert isinstance(result, ReplayResult)
    assert result.classification == "reproducible"
    assert result.reruns_total == 3
    assert result.reruns_failed == 0
    assert result.test_id is None
    assert result.reason is None

    # NFR-REP-002 smoke pin — read records from disk, then time the
    # classify + persist tail (NOT the subprocess reruns).
    original_record = retrieve_run_evidence(init.store, original_ref).run_record
    replayed_records = [
        e.run_record
        for e in list_run_history(init.store)
        if e.run_record.run_reference.run_id != original_ref.run_id
    ]
    assert len(replayed_records) == 3
    start = time.perf_counter()
    recomputed = classify_replay_consistency(original_record, replayed_records)
    write_replay_result(init.store, original_ref, recomputed)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"NFR-REP-002 violated: {elapsed:.3f}s"
    assert recomputed.classification == "reproducible"


async def test_replay_with_missing_target_yields_unable_to_replay(
    tmp_path: Path,
) -> None:
    """DoD bullet 3: a vanished Test Target → ``unable_to_replay`` (exit 0).

    The original run is captured normally; the workspace is then mutated by
    deleting the test file. The replay reruns collect nothing (pytest exit 5
    → errored Run Records), which the classifier maps to ``unable_to_replay``
    — a VALID classification, not a ``ReplayUnavailable`` error.
    """

    workspace = _materialize("pytest-basic", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store("tests/", init.store, timeout=120.0)
    original_ref = outcome.memory_entry.run_record.run_reference
    assert outcome.memory_entry.run_record.status == "passed"

    # Mutate the workspace AFTER capture: delete the test file(s).
    deleted = list((workspace / "tests").glob("test_*.py"))
    assert deleted, "fixture expected to ship at least one test file"
    for test_file in deleted:
        test_file.unlink()

    result = await replay_run(init.store, original_ref, reruns=3)

    assert isinstance(result, ReplayResult)
    assert result.classification == "unable_to_replay"
    assert result.reason in REPLAY_UNABLE_REASONS
    assert result.reason == "replay-run-errored"

    # Still a persisted, cache-readable result (citable like any other).
    cached = get_replay_result(init.store, original_ref)
    assert isinstance(cached, ReplayResult)
    assert cached.classification == "unable_to_replay"
