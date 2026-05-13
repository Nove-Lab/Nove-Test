"""End-to-end integration-style tests for `novetest.run.engine.execute`.

These exercise the full Phase 1 happy path: readiness → engine selection →
adapter invocation → normalization → run-reference assignment. They
intentionally spawn real pytest subprocesses against the fixture projects
because the workflow's value is the wiring, not the individual steps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.run.engine import execute, execute_with_engine_context
from novetest.run.errors import EngineNotReadyError, EngineNotSupportedError
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import NativeEngineContext


async def test_execute_pytest_basic_returns_all_passed(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    record = await execute(target, artifact_dir=tmp_path, timeout=60.0)
    assert record.status == "passed"
    assert record.engine_name == "pytest"
    assert record.ecosystem == "python"
    assert len(record.run_reference.run_id) == 26  # raw ULID
    assert record.summary_counts["passed"] == 3
    assert record.summary_counts["total"] == 3
    assert all(tr.outcome == "passed" for tr in record.test_results)
    # Native artifacts were captured under the per-run artifact_dir.
    json_report = Path(record.artifact_paths["pytest_json_report"])
    assert json_report.is_file()


async def test_execute_pytest_failing_captures_failure(
    failing_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", failing_workspace)
    record = await execute(target, artifact_dir=tmp_path, timeout=60.0)
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_reference is not None


async def test_execute_short_circuits_for_empty_no_engine(
    empty_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", empty_workspace)
    artifact_dir = tmp_path / "should-not-be-created"
    with pytest.raises(EngineNotReadyError) as exc_info:
        await execute(target, artifact_dir=artifact_dir, timeout=10.0)
    assert exc_info.value.readiness.state == "engine-missing"
    # No subprocess spawned → no native artifacts laid down.
    assert not artifact_dir.exists()


async def test_execute_with_engine_context_runs_pytest(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="python", engine_name="pytest")
    record = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=60.0
    )
    assert record.status == "passed"
    assert record.engine_name == "pytest"


async def test_execute_with_engine_context_rejects_unimplemented_engine(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="javascript-typescript", engine_name="jest")
    with pytest.raises(EngineNotSupportedError):
        await execute_with_engine_context(
            target, context, artifact_dir=tmp_path, timeout=10.0
        )


async def test_run_id_can_be_pinned(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    record = await execute(
        target,
        artifact_dir=tmp_path,
        run_id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
        timeout=60.0,
    )
    assert record.run_reference.run_id == "01HZZZZZZZZZZZZZZZZZZZZZZZ"
