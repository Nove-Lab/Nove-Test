"""Top-level Run engine orchestration.

`execute` and `execute_with_engine_context` implement the workflows in
`design/workflows/run.md` §1: readiness gate, adapter invocation,
normalization, and Run Reference assignment. The caller supplies the
artifacts directory (the orchestration slice is what binds it to
``.novetest/run/artifacts/run_<ulid>/`` in Phase 1).
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol

from novetest.models import RunRecord
from novetest.run.adapters.cargo_adapter import run_cargo
from novetest.run.adapters.dotnet_adapter import run_xunit
from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.adapters.junit_adapter import run_junit
from novetest.run.adapters.pytest_adapter import run_pytest
from novetest.run.errors import EngineNotReadyError, EngineNotSupportedError
from novetest.run.normalizer import normalize_native_result
from novetest.run.readiness import probe_engine
from novetest.run.reference import assign_run_reference
from novetest.run.types import (
    AdapterWarning,
    NativeEngineContext,
    NativeResult,
    TestTarget,
)


class _AdapterEntryPoint(Protocol):
    """The shared signature of every ``run_<engine>`` adapter entry."""

    def __call__(
        self,
        test_target: TestTarget,
        *,
        artifact_dir: Path,
        timeout: float | None,
        collect_coverage: bool,
    ) -> Awaitable[NativeResult]: ...


# THE dispatch table: engine_name -> adapter entry point. Module-level
# constant dict — the ``readiness._READINESS_PROBES`` house pattern, NOT
# a decorator registry (review roadmap §5 rejected-direction #1). Keys
# are pinned equal to the engine names of ``list_supported_engine_pairs()``
# by the divergence guard in ``tests/unit/run/test_engine.py``, so a
# seventh engine entering the supported matrix without an adapter entry
# (or an adapter entry without a matrix row) fails at test time.
_ADAPTER_ENTRY_POINTS: dict[str, _AdapterEntryPoint] = {
    "pytest": run_pytest,
    "jest": run_jest,
    "junit": run_junit,
    "go-test": run_gotest,
    "cargo-test": run_cargo,
    "xunit": run_xunit,
}


async def execute(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    engine: tuple[str, str],
    run_id: str | None = None,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> tuple[RunRecord, tuple[AdapterWarning, ...]]:
    """Execute ``test_target`` and return ``(RunRecord, adapter_warnings)``.

    ``engine`` is the externally resolved ``(ecosystem, engine_name)``
    pair — the store pin, or a transient ``--engine`` override (decision
    `2026-07-03-engine-selection-policy.md` D3). Readiness is probed for
    exactly that engine (`probe_engine`) and dispatch goes straight to
    it: NO marker detection runs on the hot path. Callers resolve the
    pair upstream (`orchestration.anchor_resolution.resolve_execution_engine`
    never returns ``None`` — it raises on failure), so there is no
    auto-detect fallback here (legacy ``engine=None`` branch removed by
    W2/S16, RUN-25).

    Sequence (mirroring `design/workflows/run.md` §1):
    1. Readiness gate — `probe_engine` on the supplied pair;
       short-circuit with EngineNotReadyError on any non-``ready`` state
       so callers can surface exit code 4 without spawning a subprocess.
    2. Invoke the adapter — `_ADAPTER_ENTRY_POINTS` dispatch.
    3. `normalize_native_result` — build the Run Record.
    4. `assign_run_reference` — stamp a fresh ULID-derived reference.

    ``collect_coverage`` is plumbed through to the adapter so a coverage-
    enabled run lands ``coverage_json`` / ``coverage_xml`` in
    ``RunRecord.artifact_paths``. Defaults to False so non-coverage callers
    see no behavior change.

    Returns the ``RunRecord`` paired with the adapter's warnings tuple
    (``NativeResult.warnings`` lifted unchanged). Warnings are transient
    envelope decorations per
    `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
    §"Option C follow-up slice scope" — they do NOT land on the Run
    Record, only on the JSON envelope's top-level ``warnings`` field via
    the orchestration / CLI projection at ``run_cmd`` /
    ``build_test_envelope``.
    """

    ecosystem, engine_name = engine
    readiness = await probe_engine(
        test_target.workspace_path, ecosystem, engine_name
    )
    if readiness.state != "ready":
        raise EngineNotReadyError(readiness)
    assert readiness.engine_context is not None  # always set on "ready"
    return await execute_with_engine_context(
        test_target,
        readiness.engine_context,
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
) -> tuple[RunRecord, tuple[AdapterWarning, ...]]:
    """Same as `execute` but reuses a pre-recorded Native Engine context.

    Used by Replay (Phase 5) to keep the same engine path as the original
    run. There is NO readiness gate in this function: the replay engine
    gates on the RECORDED engine via `readiness.probe_engine` BEFORE
    calling (W2/S38, ANA-13), so workspace drift between original and
    replay surfaces upstream as a hard not-ready result, never mid-dispatch.

    Returns the ``RunRecord`` paired with the adapter warnings tuple —
    same contract as ``execute``.
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
    record = assign_run_reference(record, run_id=run_id)
    warnings = native_result.warnings
    if not record.test_results and record.status == "passed":
        # Silent-green visibility (W1/S4, RUN-12, correction C1): the engine
        # ran to completion, exited clean, and collected ZERO tests — a
        # ``passed`` status here means nothing was executed. Decorate the run
        # with one loud warning at this single engine-agnostic site. It fires
        # for exactly the engines that reach it with a passed-empty RunRecord:
        # go / junit / xunit. jest and cargo raise ``AdapterInvocationError``
        # before a RunRecord exists (already loud — this site never sees
        # them), and pytest maps exit-5 to ``errored`` (separate concern), so
        # no engine branching is needed here. Transient envelope decoration
        # only — NOT persisted on RunRecord (reuses the warning channel of
        # ``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``).
        warnings = warnings + (
            AdapterWarning(
                code="zero-tests-collected",
                message=(
                    f"{resolved_context.engine_name} ran to completion but "
                    "collected zero tests; a 'passed' result here means "
                    "nothing was executed"
                ),
                details={"engine_name": resolved_context.engine_name},
            ),
        )
    return record, warnings


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
    adapter = _ADAPTER_ENTRY_POINTS.get(engine_name)
    if adapter is None:
        raise EngineNotSupportedError(
            f"adapter for {engine_name!r} not implemented yet"
        )
    return await adapter(
        test_target,
        artifact_dir=artifact_dir,
        timeout=timeout,
        collect_coverage=collect_coverage,
    )
