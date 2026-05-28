"""End-to-end integration-style tests for `novetest.run.engine.execute`.

These exercise the full Phase 1 happy path: readiness → engine selection →
adapter invocation → normalization → run-reference assignment. They
intentionally spawn real pytest subprocesses against the fixture projects
because the workflow's value is the wiring, not the individual steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.run import engine as engine_module
from novetest.run.engine import execute, execute_with_engine_context
from novetest.run.errors import EngineNotReadyError, EngineNotSupportedError
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import NativeEngineContext, NativeResult


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
    """Phase 2.5 added jest, so this test now uses xunit as the
    'still-unimplemented' example. junit / go-test / cargo-test would all
    behave identically; xunit is chosen so the test does not become stale
    if a follow-up slice adds another adapter.
    """

    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="dotnet", engine_name="xunit")
    with pytest.raises(EngineNotSupportedError):
        await execute_with_engine_context(
            target, context, artifact_dir=tmp_path, timeout=10.0
        )


async def test_execute_with_engine_context_dispatches_jest(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='jest')` must call ``run_jest``.

    Stubs ``run_jest`` at the engine seam so we observe dispatch without
    requiring Node.js. The same NativeResult-fake pattern as the pytest
    `test_execute_threads_collect_coverage_kwarg_into_adapter` case.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_jest(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "jest-results.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="jest",
            payload={
                "success": True,
                "numPassedTests": 0,
                "numFailedTests": 0,
                "numPendingTests": 0,
                "numTodoTests": 0,
                "numTotalTests": 0,
                "testResults": [],
            },
            artifact_paths={"jest_json_report": report_path},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="29.7.0",
        )

    monkeypatch.setattr(engine_module, "run_jest", fake_run_jest)
    target = resolve_test_target("__tests__/", jest_basic_workspace)
    context = NativeEngineContext(
        ecosystem="javascript-typescript", engine_name="jest"
    )
    record = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert record.engine_name == "jest"
    assert record.ecosystem == "javascript-typescript"
    assert record.engine_version == "29.7.0"


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


async def test_execute_threads_collect_coverage_kwarg_into_adapter(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute(collect_coverage=True)` must pass-through to ``run_pytest``.

    Stubs ``run_pytest`` at the engine seam so we observe the kwarg without
    actually invoking pytest (which would need ``pytest-cov`` plumbing
    that's exercised by the integration suite, not this unit test).
    """

    seen_kwargs: dict[str, Any] = {}

    async def fake_run_pytest(test_target: Any, **kwargs: Any) -> NativeResult:
        seen_kwargs.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "pytest-report.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="pytest",
            payload={
                "exitcode": 0,
                "summary": {"passed": 0, "total": 0},
                "tests": [],
                "duration": 0.0,
            },
            artifact_paths={"pytest_json_report": report_path},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="stub",
        )

    monkeypatch.setattr(engine_module, "run_pytest", fake_run_pytest)
    target = resolve_test_target("", basic_workspace)
    await execute(
        target,
        artifact_dir=tmp_path,
        timeout=10.0,
        collect_coverage=True,
    )
    assert seen_kwargs.get("collect_coverage") is True


async def test_execute_with_engine_context_dispatches_gotest(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='go-test')` must call ``run_gotest``.

    Stubs ``run_gotest`` at the engine seam so we observe dispatch without
    requiring Go to be installed. Same fake-NativeResult pattern as the
    jest dispatch test.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_gotest(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        events_path = native_dir / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        return NativeResult(
            engine_name="go-test",
            payload={"events": [], "packages": [], "failure_logs": {}},
            artifact_paths={
                "gotest_events_jsonl": events_path,
                "stdout": native_dir / "stdout.log",
                "stderr": native_dir / "stderr.log",
            },
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="1.23.4",
        )

    monkeypatch.setattr(engine_module, "run_gotest", fake_run_gotest)
    target = resolve_test_target("", gotest_basic_workspace)
    context = NativeEngineContext(ecosystem="go", engine_name="go-test")
    record = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert record.engine_name == "go-test"
    assert record.ecosystem == "go"
    assert record.engine_version == "1.23.4"
