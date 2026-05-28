"""Normalize a Native Result into a Run Record.

Public surface (`normalize_native_result`) is engine-agnostic; the function
dispatches on ``native_engine_context.engine_name`` to a per-engine
``_normalize_<engine>`` function. Phase 1 shipped pytest; Phase 2.5 added
jest; Phase 3 (adapter backlog slice #1) adds go-test. The dispatcher
table stays — a registry pattern is deferred until the surface motivates
it (probably at adapter #5).
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
    elif engine_name == "go-test":
        status, summary, test_results = _normalize_gotest_payload(
            native_result.payload, returncode=native_result.returncode
        )
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


# ---------------------------------------------------------------------------
# go-test payload normalization (`go test -json` NDJSON event stream)
# ---------------------------------------------------------------------------


_GOTEST_ACTION_TO_OUTCOME: dict[str, str] = {
    "pass": "passed",
    "fail": "failed",
    "skip": "skipped",
}


def _normalize_gotest_payload(
    payload: Mapping[str, Any],
    *,
    returncode: int,
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize the gotest adapter's payload into Run Record components.

    Payload shape (set by `gotest_adapter.run_gotest`):

    ``{"events": [<event dict>...],
       "packages": [<package name>...],
       "failure_logs": {"<Package>::<Test>": "<rel path>", ...}}``

    Each event dict mirrors ``go doc cmd/test2json``'s shape
    (``Time``, ``Action``, ``Package``, ``Test``, ``Output``, ``Elapsed``).
    A TestResult is emitted for every terminal action (``pass``/``fail``/``skip``)
    with a non-empty ``Test`` field — including parent tests of subtests
    (Go's runner emits a terminal action for them too; downstream
    consumers that want only leaves can filter on the ``/`` in ``node_id``).

    Unknown terminal actions (none expected today, but the
    defensive-parsing decision of 2026-05-25 requires graceful handling)
    map to outcome ``"unknown"`` rather than raising. Visible-not-silent.
    """

    events_raw = payload.get("events")
    if not isinstance(events_raw, list):
        raise AdapterInvocationError(
            "go-test payload missing 'events' array",
            kind="unparseable-output",
        )

    failure_logs_raw = payload.get("failure_logs")
    failure_logs: Mapping[str, str] = (
        {str(k): str(v) for k, v in failure_logs_raw.items() if isinstance(v, str)}
        if isinstance(failure_logs_raw, Mapping)
        else {}
    )

    test_results: list[TestResult] = []
    summary: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0}

    for event in events_raw:
        if not isinstance(event, Mapping):
            continue
        action = event.get("Action")
        if not isinstance(action, str):
            continue
        if action not in _GOTEST_ACTION_TO_OUTCOME and action != "fail":
            # Skip per-event filter cheaply; the meaningful set is the
            # three terminal-test actions plus the visible-not-silent
            # fallback for any future addition.
            if action in ("run", "pause", "cont", "output", "bench"):
                continue
        package = event.get("Package")
        test = event.get("Test")
        if not isinstance(package, str) or not package:
            continue
        if not isinstance(test, str) or not test:
            # Package-level terminal actions (e.g. final `fail` for the
            # whole package) carry no `Test` field — those are not test
            # results, only aggregate signals.
            continue

        # Map the action to an outcome string. Unknown actions land as
        # `"unknown"` per the supported-engine-matrix decision.
        outcome = _GOTEST_ACTION_TO_OUTCOME.get(action, "unknown")
        if outcome == "passed":
            summary["passed"] += 1
        elif outcome == "failed":
            summary["failed"] += 1
        elif outcome == "skipped":
            summary["skipped"] += 1
        # Unknown actions are counted toward `total` via the sum below
        # but are not in any of the three named buckets — intentional, so
        # the imbalance is observable.

        duration_ms: int | None = None
        elapsed = event.get("Elapsed")
        if isinstance(elapsed, (int, float)):
            duration_ms = int(round(float(elapsed) * 1000))

        node_id = f"{package}::{test}"
        failure_reference = failure_logs.get(node_id) if outcome == "failed" else None

        test_results.append(
            TestResult(
                node_id=node_id,
                outcome=outcome,
                duration_ms=duration_ms,
                failure_reference=failure_reference,
            )
        )

    summary["total"] = len(test_results)

    status = _aggregate_gotest_status(
        returncode=returncode,
        test_results=tuple(test_results),
    )
    return status, summary, tuple(test_results)


def _aggregate_gotest_status(
    *,
    returncode: int,
    test_results: tuple[TestResult, ...],
) -> str:
    """Decide passed / failed / errored from `go test -json` signals.

    Rules (in order):
    - Any failing test → ``"failed"``.
    - No failing tests, returncode == 0 → ``"passed"``.
    - No failing tests, returncode != 0 → ``"errored"`` (the build / test
      harness itself broke after at least one test ran; the adapter's
      build-failure short-circuit handles the "no tests ran at all" case).
    """

    failures = sum(1 for tr in test_results if tr.outcome == "failed")
    if failures:
        return "failed"
    if returncode == 0:
        return "passed"
    return "errored"


__all__ = ["normalize_native_result"]
