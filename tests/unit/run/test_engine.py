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
    # Per 2026-06-06 envelope-warnings-projection slice, ``execute``
    # returns ``(RunRecord, adapter_warnings)``; pytest emits zero
    # warnings today so the tuple's second element is the empty tuple.
    record, warnings = await execute(target, artifact_dir=tmp_path, timeout=60.0)
    assert warnings == ()
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
    record, warnings = await execute(target, artifact_dir=tmp_path, timeout=60.0)
    assert warnings == ()
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
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=60.0
    )
    assert warnings == ()
    assert record.status == "passed"
    assert record.engine_name == "pytest"


async def test_execute_with_engine_context_rejects_unimplemented_engine(
    basic_workspace: Path, tmp_path: Path
) -> None:
    """All 6 native engines (pytest / jest / go-test / cargo-test / junit /
    xunit) are now implemented at Phase 2.5 close. To still exercise the
    "engine not implemented" raise path we synthesize an
    ``EngineNotSupportedError`` via a hypothetical future engine name
    (``"phpunit"``); the contract is "every unrecognized name raises",
    which stays load-bearing for forward compatibility with Phase 3+
    adapter additions.
    """

    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="php", engine_name="phpunit")
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
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "jest"
    assert record.ecosystem == "javascript-typescript"
    assert record.engine_version == "29.7.0"


async def test_run_id_can_be_pinned(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    record, _ = await execute(
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
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "go-test"
    assert record.ecosystem == "go"
    assert record.engine_version == "1.23.4"


async def test_execute_with_engine_context_dispatches_cargo(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='cargo-test')` must call
    ``run_cargo``.

    Stubs ``run_cargo`` at the engine seam so we observe dispatch without
    requiring the Rust toolchain to be installed. Same fake-NativeResult
    pattern as the gotest dispatch test.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_cargo(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        events_path = native_dir / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        return NativeResult(
            engine_name="cargo-test",
            payload={
                "events": [],
                "binaries": [],
                "failure_logs": {},
            },
            artifact_paths={
                "cargo_events_jsonl": events_path,
                "stdout": native_dir / "stdout.log",
                "stderr": native_dir / "stderr.log",
            },
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="1.74.0",
            # `nextest_version` rides the typed metadata slot post the
            # 2026-05-30 migration (was previously stashed in
            # `payload[...]` and silently dropped at the normalizer
            # seam — Issue 2 of the cargo E2E sweep).
            metadata={"nextest_version": "0.9.70"},
        )

    monkeypatch.setattr(engine_module, "run_cargo", fake_run_cargo)
    target = resolve_test_target("", cargo_test_basic_workspace)
    context = NativeEngineContext(ecosystem="rust", engine_name="cargo-test")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "cargo-test"
    assert record.ecosystem == "rust"
    assert record.engine_version == "1.74.0"
