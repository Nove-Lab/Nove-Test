"""Top-level Run engine orchestration.

`execute` and `execute_with_engine_context` implement the workflows in
`design/workflows/run.md` §1: readiness gate, optional engine selection,
adapter invocation, normalization, and Run Reference assignment. The
caller supplies the artifacts directory (the orchestration slice is what
binds it to ``.novetest/run/artifacts/run_<ulid>/`` in Phase 1).
"""

from __future__ import annotations

from pathlib import Path

from novetest.models import RunRecord
from novetest.run.adapters.cargo_adapter import run_cargo
from novetest.run.adapters.dotnet_adapter import run_xunit
from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.adapters.junit_adapter import run_junit
from novetest.run.adapters.pytest_adapter import run_pytest
from novetest.run.engine_selector import select_native_engine
from novetest.run.errors import EngineNotReadyError, EngineNotSupportedError
from novetest.run.normalizer import normalize_native_result
from novetest.run.readiness import assess_engine_readiness
from novetest.run.reference import assign_run_reference
from novetest.run.types import NativeEngineContext, NativeResult, TestTarget


async def execute(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    run_id: str | None = None,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> RunRecord:
    """Execute ``test_target`` and return a Run Record.

    Sequence (mirroring `design/workflows/run.md` §1):
    1. `assess_engine_readiness` — short-circuit with EngineNotReadyError on
       any non-``ready`` state so callers can surface exit code 4 without
       spawning a subprocess.
    2. `select_native_engine` — pick the engine for the resolved target.
    3. Invoke the adapter (`run_pytest`).
    4. `normalize_native_result` — build the Run Record.
    5. `assign_run_reference` — stamp a fresh ULID-derived reference.

    ``collect_coverage`` is plumbed through to the adapter so a coverage-
    enabled run lands ``coverage_json`` / ``coverage_xml`` in
    ``RunRecord.artifact_paths``. Defaults to False so non-coverage callers
    see no behavior change.
    """

    readiness = await assess_engine_readiness(test_target.workspace_path)
    if readiness.state != "ready":
        raise EngineNotReadyError(readiness)
    engine_context = select_native_engine(test_target)
    return await execute_with_engine_context(
        test_target,
        engine_context,
        artifact_dir=artifact_dir,
        run_id=run_id,
        timeout=timeout,
        collect_coverage=collect_coverage,
    )


async def execute_with_engine_context(
    test_target: TestTarget,
    native_engine_context: NativeEngineContext,
    *,
    artifact_dir: Path,
    run_id: str | None = None,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> RunRecord:
    """Same as `execute` but reuses a pre-recorded Native Engine context.

    Used by Replay (Phase 5) to keep the same engine path as the original
    run. Phase 1 still gates on `assess_engine_readiness` because workspace
    state can drift between original and replay; the readiness state is
    advisory to the caller, not to the workflow shape.
    """

    native_result = await _invoke_adapter(
        native_engine_context,
        test_target,
        artifact_dir=artifact_dir,
        timeout=timeout,
        collect_coverage=collect_coverage,
    )
    # Prefer the version the adapter actually observed.
    resolved_context = NativeEngineContext(
        ecosystem=native_engine_context.ecosystem,
        engine_name=native_engine_context.engine_name,
        engine_version=native_result.engine_version
        or native_engine_context.engine_version,
    )
    record = normalize_native_result(
        native_result,
        resolved_context,
        target_expression=test_target.target_expression,
        target_type=test_target.target_type,
    )
    return assign_run_reference(record, run_id=run_id)


async def _invoke_adapter(
    native_engine_context: NativeEngineContext,
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None,
    collect_coverage: bool,
) -> NativeResult:
    """Dispatch to the per-engine adapter or raise `EngineNotSupportedError`."""

    engine_name = native_engine_context.engine_name
    if engine_name == "pytest":
        return await run_pytest(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    if engine_name == "jest":
        return await run_jest(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    if engine_name == "go-test":
        return await run_gotest(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    if engine_name == "cargo-test":
        return await run_cargo(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    if engine_name == "junit":
        return await run_junit(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    if engine_name == "xunit":
        return await run_xunit(
            test_target,
            artifact_dir=artifact_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
        )
    raise EngineNotSupportedError(
        f"adapter for {engine_name!r} not implemented yet"
    )
