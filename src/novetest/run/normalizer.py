"""Normalize a Native Result into a Run Record.

Phase 1 only handles the pytest payload shape (the
``pytest-json-report`` schema). Adding another engine adds a new branch
keyed on ``native_engine_context.engine_name`` rather than a generic
dispatcher — Phase 1 ships only one engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from novetest.models import RunRecord, RunReference, TestResult
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeEngineContext, NativeResult


_PYTEST_OUTCOME_TO_RUN_STATUS = {
    "passed": "passed",
    "failed": "failed",
    "errored": "errored",
    "skipped": "passed",
}


def normalize_native_result(
    native_result: NativeResult,
    native_engine_context: NativeEngineContext,
    *,
    target_expression: str,
    target_type: str,
) -> RunRecord:
    """Convert ``native_result`` into a `RunRecord` with placeholder reference.

    The returned `RunRecord` carries a *placeholder* ``RunReference``
    (empty ``run_id``, ``created_at=0``); `assign_run_reference` replaces
    it. We split the two steps so a caller (Replay, later) can normalize
    without committing to a Run Reference if it intends to reuse one.
    """

    if native_engine_context.engine_name != "pytest":
        raise AdapterInvocationError(
            f"normalize_native_result has no Phase 1 handler for "
            f"engine={native_engine_context.engine_name!r}",
            kind="unparseable-output",
        )

    payload = native_result.payload
    summary_raw = payload.get("summary")
    if not isinstance(summary_raw, Mapping):
        raise AdapterInvocationError(
            "pytest JSON report missing 'summary' object",
            kind="unparseable-output",
        )
    summary = {str(k): int(v) for k, v in summary_raw.items() if isinstance(v, int)}

    tests_raw = payload.get("tests")
    if not isinstance(tests_raw, list):
        raise AdapterInvocationError(
            "pytest JSON report missing 'tests' array",
            kind="unparseable-output",
        )

    test_results = tuple(_build_test_result(t) for t in tests_raw if isinstance(t, Mapping))
    status = _aggregate_status(payload, test_results)

    placeholder_reference = RunReference(run_id="", created_at=0)
    artifact_paths = {name: str(path) for name, path in native_result.artifact_paths.items()}

    return RunRecord(
        run_reference=placeholder_reference,
        target_expression=target_expression,
        target_type=target_type,
        engine_name=native_engine_context.engine_name,
        ecosystem=native_engine_context.ecosystem,
        engine_version=native_result.engine_version,
        status=status,
        started_at=native_result.started_at_ms,
        completed_at=native_result.completed_at_ms,
        summary_counts=summary,
        test_results=test_results,
        artifact_paths=artifact_paths,
        metadata={"native_exit_code": native_result.returncode},
    )


def _build_test_result(test_entry: Mapping[str, Any]) -> TestResult:
    node_id = str(test_entry.get("nodeid", ""))
    outcome = str(test_entry.get("outcome", "unknown"))
    call_phase = test_entry.get("call")
    call_phase_map = call_phase if isinstance(call_phase, Mapping) else None

    duration_ms: int | None = None
    duration_components = [
        _phase_duration(test_entry.get("setup")),
        _phase_duration(call_phase),
        _phase_duration(test_entry.get("teardown")),
    ]
    accumulated = [d for d in duration_components if d is not None]
    if accumulated:
        duration_ms = int(round(sum(accumulated) * 1000))

    failure_reference: str | None = None
    if outcome in ("failed", "errored") and call_phase_map is not None:
        crash = call_phase_map.get("crash")
        if isinstance(crash, Mapping):
            message = crash.get("message")
            path = crash.get("path")
            lineno = crash.get("lineno")
            if isinstance(message, str):
                location = ""
                if isinstance(path, str) and isinstance(lineno, int):
                    location = f"{path}:{lineno}: "
                failure_reference = f"{location}{message}"
        if failure_reference is None:
            longrepr = call_phase_map.get("longrepr")
            if isinstance(longrepr, str):
                failure_reference = longrepr

    return TestResult(
        node_id=node_id,
        outcome=outcome,
        duration_ms=duration_ms,
        failure_reference=failure_reference,
    )


def _phase_duration(phase: object) -> float | None:
    if not isinstance(phase, Mapping):
        return None
    duration = phase.get("duration")
    if isinstance(duration, (int, float)):
        return float(duration)
    return None


def _aggregate_status(payload: Mapping[str, Any], test_results: tuple[TestResult, ...]) -> str:
    """Boil the pytest exit code + per-test outcomes down to a Run status."""

    exit_code = payload.get("exitcode")
    if not isinstance(exit_code, int):
        return "errored"
    if exit_code in (2, 3, 5):
        # pytest internal / usage error / no-tests-collected paths.
        return "errored"
    failures = sum(1 for tr in test_results if tr.outcome in ("failed", "errored"))
    if failures:
        return "failed"
    return "passed"


__all__ = ["normalize_native_result"]
