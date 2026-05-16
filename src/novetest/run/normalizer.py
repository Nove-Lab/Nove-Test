"""Normalize a Native Result into a Run Record.

Public surface (`normalize_native_result`) is engine-agnostic; the function
dispatches on ``native_engine_context.engine_name`` to a per-engine
``_normalize_<engine>`` function. Phase 1 shipped pytest; Phase 2.5 adds
jest. The dispatcher table is the minimum abstraction the second adapter
warrants — a registry pattern is deferred until a third lands.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from novetest.models import RunRecord, RunReference, TestResult
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeEngineContext, NativeResult


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

    engine_name = native_engine_context.engine_name
    if engine_name == "pytest":
        status, summary, test_results = _normalize_pytest_payload(native_result.payload)
    elif engine_name == "jest":
        status, summary, test_results = _normalize_jest_payload(native_result.payload)
    else:
        raise AdapterInvocationError(
            f"normalize_native_result has no handler for engine={engine_name!r}",
            kind="unparseable-output",
        )

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


# ---------------------------------------------------------------------------
# pytest payload normalization (pytest-json-report schema)
# ---------------------------------------------------------------------------


def _normalize_pytest_payload(
    payload: Mapping[str, Any],
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
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

    test_results = tuple(
        _build_pytest_test_result(t) for t in tests_raw if isinstance(t, Mapping)
    )
    status = _aggregate_pytest_status(payload, test_results)
    return status, summary, test_results


def _build_pytest_test_result(test_entry: Mapping[str, Any]) -> TestResult:
    node_id = str(test_entry.get("nodeid", ""))
    outcome = str(test_entry.get("outcome", "unknown"))
    call_phase = test_entry.get("call")
    call_phase_map = call_phase if isinstance(call_phase, Mapping) else None

    duration_ms: int | None = None
    duration_components = [
        _pytest_phase_duration(test_entry.get("setup")),
        _pytest_phase_duration(call_phase),
        _pytest_phase_duration(test_entry.get("teardown")),
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


def _pytest_phase_duration(phase: object) -> float | None:
    if not isinstance(phase, Mapping):
        return None
    duration = phase.get("duration")
    if isinstance(duration, (int, float)):
        return float(duration)
    return None


def _aggregate_pytest_status(
    payload: Mapping[str, Any], test_results: tuple[TestResult, ...]
) -> str:
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


# ---------------------------------------------------------------------------
# jest payload normalization (jest --json schema)
# ---------------------------------------------------------------------------


def _normalize_jest_payload(
    payload: Mapping[str, Any],
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize jest's ``--json`` output into a Run Record's components.

    Jest's payload shape (stable since Jest 20):
    ``{success, numPassedTests, numFailedTests, numPendingTests,
       numTodoTests, numTotalTests, testResults: [{name, status,
       testResults: [{ancestorTitles, title, fullName, status, duration,
       failureMessages, location}]}]}``.

    Nodeids are synthesized as ``<relative file>::<ancestors>::<title>``
    so they are stable, human-readable, and align with how the pytest
    adapter shapes its nodeid string.
    """

    summary = {
        "passed": _int_field(payload, "numPassedTests"),
        "failed": _int_field(payload, "numFailedTests"),
        "pending": _int_field(payload, "numPendingTests"),
        "todo": _int_field(payload, "numTodoTests"),
        "total": _int_field(payload, "numTotalTests"),
    }

    suites_raw = payload.get("testResults")
    if not isinstance(suites_raw, list):
        raise AdapterInvocationError(
            "jest JSON report missing 'testResults' array",
            kind="unparseable-output",
        )

    flattened: list[TestResult] = []
    for suite in suites_raw:
        if not isinstance(suite, Mapping):
            continue
        suite_file = suite.get("name") or suite.get("testFilePath") or ""
        suite_file_str = str(suite_file)
        per_suite = suite.get("testResults")
        if not isinstance(per_suite, list):
            continue
        for entry in per_suite:
            if not isinstance(entry, Mapping):
                continue
            flattened.append(_build_jest_test_result(suite_file_str, entry))

    status = _aggregate_jest_status(payload, tuple(flattened))
    return status, summary, tuple(flattened)


def _build_jest_test_result(suite_file: str, entry: Mapping[str, Any]) -> TestResult:
    ancestors_raw = entry.get("ancestorTitles")
    ancestors = (
        "::".join(str(a) for a in ancestors_raw if isinstance(a, str))
        if isinstance(ancestors_raw, list)
        else ""
    )
    title = str(entry.get("title", ""))
    node_id = "::".join(part for part in (suite_file, ancestors, title) if part)

    outcome = _map_jest_outcome(str(entry.get("status", "unknown")))

    duration_ms: int | None = None
    duration = entry.get("duration")
    if isinstance(duration, (int, float)):
        # jest reports durations in milliseconds (unlike pytest's seconds).
        duration_ms = int(round(float(duration)))

    failure_reference: str | None = None
    failure_messages = entry.get("failureMessages")
    if outcome in ("failed", "errored") and isinstance(failure_messages, list):
        joined = "\n".join(str(m) for m in failure_messages if isinstance(m, str))
        if joined:
            failure_reference = joined

    return TestResult(
        node_id=node_id,
        outcome=outcome,
        duration_ms=duration_ms,
        failure_reference=failure_reference,
    )


_JEST_STATUS_TO_OUTCOME = {
    "passed": "passed",
    "failed": "failed",
    "pending": "skipped",
    "skipped": "skipped",
    "todo": "skipped",
    "disabled": "skipped",
    "focused": "passed",
}


def _map_jest_outcome(jest_status: str) -> str:
    return _JEST_STATUS_TO_OUTCOME.get(jest_status, "unknown")


def _aggregate_jest_status(
    payload: Mapping[str, Any], test_results: tuple[TestResult, ...]
) -> str:
    """Decide passed / failed / errored from jest's payload.

    Jest's ``success`` field is the authoritative green signal. If
    ``success`` is missing or non-bool we fall back to counting failed
    tests; if neither is decisive we errored-out.
    """

    success = payload.get("success")
    if success is True:
        return "passed"
    failures = sum(1 for tr in test_results if tr.outcome in ("failed", "errored"))
    num_failed = payload.get("numFailedTests")
    if (isinstance(num_failed, int) and num_failed > 0) or failures:
        return "failed"
    if success is False:
        # Jest declared the run unsuccessful but no per-test failure was
        # parseable — surface as errored so the CLI can route through the
        # engine-error path rather than misreport as passed.
        return "errored"
    return "errored"


def _int_field(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    return int(value) if isinstance(value, int) else 0


__all__ = ["normalize_native_result"]
