"""Normalize a Native Result into a Run Record.

Public surface (`normalize_native_result`) is engine-agnostic; the function
dispatches on ``native_engine_context.engine_name`` to a per-engine
``_normalize_<engine>`` function. Phase 1 shipped pytest; Phase 2.5 added
jest; Phase 3 (adapter backlog slice #1) added go-test; Phase 3 (adapter
backlog slice #2) adds cargo-test. The dispatcher table stays — a
registry pattern is deferred until the surface motivates it (likely at
adapter #5 / #6, when junit + xunit land).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from novetest.models import FAIL_LIKE_OUTCOMES, RunRecord, RunReference, TestResult
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeEngineContext, NativeResult


_RESERVED_METADATA_KEYS: frozenset[str] = frozenset({"native_exit_code"})


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

    **Metadata contract** (per
    `decisions/2026-05-30-native-result-metadata-slot.md`): the returned
    record's ``metadata`` starts with the normalizer-owned key
    ``native_exit_code`` and then overlays every entry from
    ``native_result.metadata``. Adapter authors MUST NOT pre-populate
    ``native_exit_code`` in their ``NativeResult.metadata`` — that key
    is reserved for the normalizer. The strict-raise guard below
    catches the bug at write time rather than letting an adapter
    silently override the canonical exit code (PM preference at the
    decision; strict-over-lenient is also our project posture per
    `CLAUDE.md` Coding Guidelines).
    """

    engine_name = native_engine_context.engine_name
    if engine_name == "pytest":
        status, summary, test_results = _normalize_pytest_payload(native_result.payload)
    elif engine_name == "jest":
        status, summary, test_results = _normalize_jest_payload(
            native_result.payload, workspace_root=native_result.workspace_root
        )
    elif engine_name == "go-test":
        status, summary, test_results = _normalize_gotest_payload(
            native_result.payload, returncode=native_result.returncode
        )
    elif engine_name == "cargo-test":
        status, summary, test_results = _normalize_cargo_payload(
            native_result.payload, returncode=native_result.returncode
        )
    elif engine_name == "junit":
        status, summary, test_results = _normalize_junit_payload(
            native_result.payload, returncode=native_result.returncode
        )
    elif engine_name == "xunit":
        status, summary, test_results = _normalize_xunit_payload(
            native_result.payload, returncode=native_result.returncode
        )
    else:
        raise AdapterInvocationError(
            f"normalize_native_result has no handler for engine={engine_name!r}",
            kind="unparseable-output",
        )

    placeholder_reference = RunReference(run_id="", created_at=0)
    artifact_paths = {name: str(path) for name, path in native_result.artifact_paths.items()}

    # Strict-raise guard on the reserved key. Picked over pop-and-warn
    # because the project posture is "visible-not-silent": an adapter
    # author who accidentally writes the reserved key wants to learn
    # at test time, not have the normalizer silently swallow their
    # value. The guard is one branch — cheap in steady state.
    reserved_collisions = _RESERVED_METADATA_KEYS & native_result.metadata.keys()
    if reserved_collisions:
        offending = sorted(reserved_collisions)
        raise ValueError(
            f"NativeResult.metadata keys {offending!r} are reserved for "
            f"the normalizer; adapter for engine={engine_name!r} MUST "
            f"NOT pre-populate them. See "
            f"decisions/2026-05-30-native-result-metadata-slot.md."
        )

    metadata: dict[str, Any] = {"native_exit_code": native_result.returncode}
    metadata.update(native_result.metadata)

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
        metadata=metadata,
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


_PYTEST_OUTCOME_TO_OUTCOME: dict[str, str] = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "skipped",
    "xfailed": "xfailed",
    "xpassed": "xpassed",
    "error": "errored",
}


def _map_pytest_outcome(pytest_outcome: str) -> str:
    """Map pytest's own outcome vocabulary onto the Run Record's.

    pytest-json-report writes the *category* returned by pytest's
    ``pytest_report_teststatus`` hook (`plugin.py::pytest_runtest_logreport`),
    not the phase report's ``outcome`` — so a setup **or** teardown failure
    arrives as singular ``"error"``, a spelling that is NOT in
    ``FAIL_LIKE_OUTCOMES`` (`models/test_result.py`). Copying it verbatim was
    board row 49: a suite whose only trouble was an erroring fixture
    aggregated to ``status="passed"`` at exit 0.

    Unrecognized categories map to ``"unknown"`` rather than raising, matching
    `_map_jest_outcome` / `_GOTEST_ACTION_TO_OUTCOME` / `_CARGO_EVENT_TO_OUTCOME`:
    a plugin may register a new category (``"rerun"`` from
    pytest-rerunfailures is the canonical example) and an unseen spelling is
    not a reason to lose the whole run. Plugin autoload is disabled for our
    subprocess, so this is a guard, not an expected path.
    """

    return _PYTEST_OUTCOME_TO_OUTCOME.get(pytest_outcome, "unknown")


_PYTEST_PHASES: tuple[str, ...] = ("setup", "call", "teardown")


def _pytest_failing_phase(test_entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the first phase, in pytest's own order, that itself failed.

    A per-test entry carries up to three phase objects — ``setup``, ``call``,
    ``teardown`` — and the crash text lives under the phase that raised, which
    is NOT always ``call`` (board row 56). Measured on pytest-json-report
    1.5.0 / pytest 9.0.3 against
    ``tests/fixtures/projects/pytest-fixture-error/``:

    - a **setup** error emits no ``call`` key at all — ``setup`` is
      ``outcome="failed"`` with ``crash`` + ``longrepr``, ``teardown`` passes;
    - a **teardown** error emits a *passing* ``call`` — ``teardown`` carries
      the crash;
    - a plain assertion failure carries it under ``call``, with ``setup`` and
      ``teardown`` both passing.

    A phase's own ``outcome`` uses pytest's report vocabulary
    (``passed`` / ``failed`` / ``skipped``) — singular ``"error"`` is an
    *item-level* category from ``pytest_report_teststatus`` and never appears
    here, so ``"failed"`` is the whole fail-like set at this level.

    Order matters for one measured shape: a test that fails in ``call`` **and**
    errors in ``teardown`` has two failing phases, and pytest's execution order
    picks ``call`` — the assertion that broke, which is also the text this
    function returned before row 56 widened it past ``call``.
    """

    for phase_name in _PYTEST_PHASES:
        phase = test_entry.get(phase_name)
        if isinstance(phase, Mapping) and phase.get("outcome") == "failed":
            return phase
    return None


def _pytest_phase_failure_text(phase: Mapping[str, Any]) -> str | None:
    """``<path>:<lineno>: <message>`` from the phase's ``crash``, else its
    ``longrepr``.

    The ``longrepr`` fallback is a real path, not a guard: a strict-xfail that
    passes has ``crash: null`` and ``longrepr: "[XPASS(strict)] <reason>"``.
    """

    crash = phase.get("crash")
    if isinstance(crash, Mapping):
        message = crash.get("message")
        path = crash.get("path")
        lineno = crash.get("lineno")
        if isinstance(message, str):
            location = ""
            if isinstance(path, str) and isinstance(lineno, int):
                location = f"{path}:{lineno}: "
            return f"{location}{message}"
    longrepr = phase.get("longrepr")
    if isinstance(longrepr, str):
        return longrepr
    return None


def _build_pytest_test_result(test_entry: Mapping[str, Any]) -> TestResult:
    node_id = str(test_entry.get("nodeid", ""))
    outcome = _map_pytest_outcome(str(test_entry.get("outcome", "unknown")))

    duration_ms: int | None = None
    duration_components = [
        _pytest_phase_duration(test_entry.get("setup")),
        _pytest_phase_duration(test_entry.get("call")),
        _pytest_phase_duration(test_entry.get("teardown")),
    ]
    accumulated = [d for d in duration_components if d is not None]
    if accumulated:
        duration_ms = int(round(sum(accumulated) * 1000))

    failure_reference: str | None = None
    if outcome in FAIL_LIKE_OUTCOMES:
        failing_phase = _pytest_failing_phase(test_entry)
        if failing_phase is not None:
            failure_reference = _pytest_phase_failure_text(failing_phase)

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
    """Boil the pytest exit code + per-test outcomes down to a Run status.

    Rules (in order) — the same convention `_aggregate_junit_status` /
    `_aggregate_xunit_status` already state:
    - Missing / non-int exit code, or one of ``(2, 3, 5)`` (internal error,
      usage error, no tests collected) → ``"errored"``: the suite did not run.
      This branch is decided before any per-test outcome is read.
    - Any fail-like TestResult (``"failed"`` OR ``"errored"``) → ``"failed"``.
      An erroring fixture reaches this line via `_map_pytest_outcome`; a run
      with errors but no outright failures is NOT green.
    - Otherwise → ``"passed"``.
    """

    exit_code = payload.get("exitcode")
    if not isinstance(exit_code, int):
        return "errored"
    if exit_code in (2, 3, 5):
        # pytest internal / usage error / no-tests-collected paths.
        return "errored"
    failures = sum(1 for tr in test_results if tr.outcome in FAIL_LIKE_OUTCOMES)
    if failures:
        return "failed"
    return "passed"


# ---------------------------------------------------------------------------
# jest payload normalization (jest --json schema)
# ---------------------------------------------------------------------------


def _normalize_jest_payload(
    payload: Mapping[str, Any],
    *,
    workspace_root: Path | None,
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize jest's ``--json`` output into a Run Record's components.

    Jest's payload shape (verified against jest 29.7.0's
    ``--json --outputFile`` report):
    ``{success, numPassedTests, numFailedTests, numPendingTests,
       numTodoTests, numTotalTests, testResults: [{name, status,
       assertionResults: [{ancestorTitles, title, fullName, status,
       duration, failureMessages, location}]}]}``.

    The TOP-LEVEL ``testResults`` key is the suite list; the per-suite
    assertion entries live under ``assertionResults`` (jest's report
    serializer renames the aggregated result's internal per-suite
    ``testResults`` field on write). A per-suite ``testResults`` list is
    read as a fallback so payloads carrying the internal (pre-serializer)
    field name still normalize — reading ONLY the fallback key was the
    W2-S11 bug (MT Issue 1): real jest reports never matched, and every
    jest run persisted zero per-test results while the top-level
    summary counts parsed fine.

    Nodeids are synthesized as
    ``<workspace-relative POSIX file>::<ancestors>::<title>`` so they
    are stable cross-host (RUN-13), human-readable, and align with how
    the pytest adapter shapes its nodeid string. ``workspace_root``
    (``NativeResult.workspace_root``) anchors the relativization; when
    it is absent or the suite file lies outside it, the raw suite path
    is kept in POSIX separators.
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
        suite_file_str = _jest_workspace_relative_posix(
            str(suite_file), workspace_root
        )
        per_suite = suite.get("assertionResults")
        if per_suite is None:
            # Fallback: the internal (pre-serializer) per-suite field name.
            per_suite = suite.get("testResults")
        if not isinstance(per_suite, list):
            continue
        for entry in per_suite:
            if not isinstance(entry, Mapping):
                continue
            flattened.append(_build_jest_test_result(suite_file_str, entry))

    status = _aggregate_jest_status(payload, tuple(flattened))
    return status, summary, tuple(flattened)


def _jest_workspace_relative_posix(
    suite_file: str, workspace_root: Path | None
) -> str:
    """Rewrite jest's absolute suite path to workspace-relative POSIX form.

    jest's per-suite ``name`` / ``testFilePath`` is an ABSOLUTE path in
    host-native separators (backslashes on Windows). node_ids must be
    stable cross-host (RUN-13) and match the documented
    ``<workspace-relative POSIX file>::…`` shape, so the prefix is
    relativized against the workspace root and emitted with ``/``
    separators on every platform. A suite file outside the workspace
    root (not expected from jest, whose rootDir IS the workspace) — or a
    missing root — keeps the raw path, still in POSIX separators, rather
    than crashing.

    Flavor pick: a backslash in the raw value means Windows separators
    (jest never emits ``\\`` inside a path component on POSIX hosts), so
    the string parses as `PureWindowsPath`; otherwise `PurePosixPath`.
    ``workspace_root`` is rendered into the SAME flavor before
    ``relative_to`` so canned payloads of either style resolve
    identically on both host families.
    """

    windows_flavor = "\\" in suite_file
    pure: PurePath = (
        PureWindowsPath(suite_file) if windows_flavor else PurePosixPath(suite_file)
    )
    if workspace_root is not None:
        root = str(workspace_root) if windows_flavor else workspace_root.as_posix()
        try:
            return pure.relative_to(root).as_posix()
        except ValueError:
            pass
    return pure.as_posix()


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
    if outcome in FAIL_LIKE_OUTCOMES and isinstance(failure_messages, list):
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
    failures = sum(1 for tr in test_results if tr.outcome in FAIL_LIKE_OUTCOMES)
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


# ---------------------------------------------------------------------------
# cargo-test payload normalization (libtest-json NDJSON event stream)
# ---------------------------------------------------------------------------


_CARGO_EVENT_TO_OUTCOME: dict[str, str] = {
    "ok": "passed",
    "failed": "failed",
    "ignored": "skipped",
}


def _normalize_cargo_payload(
    payload: Mapping[str, Any],
    *,
    returncode: int,
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize the cargo adapter's payload into Run Record components.

    Payload shape (set by `cargo_adapter.run_cargo`):

    ``{"events": [<event dict>...],
       "binaries": [<binary name>...],
       "failure_logs": {"<name>": "<rel path>", ...}}``

    (``nextest_version`` lives on ``NativeResult.metadata`` since the
    2026-05-30 typed-slot migration — payload now carries only
    per-test parsing state.)

    Each event dict mirrors nextest's libtest-json shape
    (``type``, ``event``, ``name``, optional ``stdout`` / ``stderr``).
    A TestResult is emitted for every terminal ``test`` event (``event``
    in ``{"ok", "failed", "ignored"}``) with a non-empty ``name``. The
    ``name`` field is used directly as the ``node_id`` — nextest's mode
    includes the binary path prefix in the name, so integration tests
    in ``tests/foo.rs`` arrive with a distinguishing prefix (e.g.
    ``cargo_test_basic--integration_test::test_add_via_integration``)
    naturally.

    Unknown terminal events (libtest may add new ones) map to
    ``outcome="unknown"`` rather than raising. Visible-not-silent per
    `decisions/2026-05-25-supported-engine-matrix.md` §2.

    Per-test durations are NOT typically present in libtest-json (they
    are aggregated at the suite level), so ``duration_ms`` defaults to
    ``None`` unless an ``exec_time`` field is observed on the event.
    """

    events_raw = payload.get("events")
    if not isinstance(events_raw, list):
        raise AdapterInvocationError(
            "cargo-test payload missing 'events' array",
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
        ev_type = event.get("type")
        if ev_type != "test":
            # Suite-level events (`started`, `ok`, `failed`) carry no
            # per-test row; they delimit test-binary blocks. Skip.
            continue
        ev_event = event.get("event")
        if not isinstance(ev_event, str):
            continue
        if ev_event == "started":
            # Lifecycle marker, not a terminal outcome — skip per the
            # gotest precedent.
            continue
        name = event.get("name")
        if not isinstance(name, str) or not name:
            continue

        # Map the event to an outcome string. Unknown event names
        # surface as `"unknown"` per defensive-parsing.
        outcome = _CARGO_EVENT_TO_OUTCOME.get(ev_event, "unknown")
        if outcome == "passed":
            summary["passed"] += 1
        elif outcome == "failed":
            summary["failed"] += 1
        elif outcome == "skipped":
            summary["skipped"] += 1
        # Unknown outcomes count toward `total` via len() below; the
        # imbalance is observable (visible-not-silent).

        duration_ms: int | None = None
        exec_time = event.get("exec_time")
        if isinstance(exec_time, (int, float)):
            # libtest-json's `exec_time` field is in seconds (mirrors
            # libtest's own JSON format on nightly). Convert to ms for
            # parity with go-test's `Elapsed * 1000`.
            duration_ms = int(round(float(exec_time) * 1000))

        failure_reference = failure_logs.get(name) if outcome == "failed" else None

        test_results.append(
            TestResult(
                node_id=name,
                outcome=outcome,
                duration_ms=duration_ms,
                failure_reference=failure_reference,
            )
        )

    summary["total"] = len(test_results)

    status = _aggregate_cargo_status(
        returncode=returncode,
        test_results=tuple(test_results),
    )
    return status, summary, tuple(test_results)


def _aggregate_cargo_status(
    *,
    returncode: int,
    test_results: tuple[TestResult, ...],
) -> str:
    """Decide passed / failed / errored from cargo-nextest signals.

    Same rule as go-test:
    - Any failing test → ``"failed"``.
    - No failing tests, returncode == 0 → ``"passed"``.
    - No failing tests, returncode != 0 → ``"errored"`` (a build script
      failure or post-test harness crash; the adapter's build-failure
      short-circuit handles the "no tests ran at all" case).
    """

    failures = sum(1 for tr in test_results if tr.outcome == "failed")
    if failures:
        return "failed"
    if returncode == 0:
        return "passed"
    return "errored"


# ---------------------------------------------------------------------------
# JUnit payload normalization (Maven Surefire / Gradle JUnit XML)
# ---------------------------------------------------------------------------


def _normalize_junit_payload(
    payload: Mapping[str, Any],
    *,
    returncode: int,
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize the junit adapter's payload into Run Record components.

    Payload shape (set by `junit_adapter.run_junit` per task brief §1.4):

    ``{"build_tool": "maven"|"gradle",
       "build_tool_version": "<mvn -v or gradle --version>",
       "jupiter_version": "<5.10.x | 5.11.x | ...>",
       "jdk_version": "<java -version major>",
       "reports": [{"path": ..., "format": ..., "module": ...}, ...],
       "tests": [{"identity", "unique_id", "status", "duration_ms",
                  "failure": {message, type, stack} | None,
                  "stdout", "stderr", "module"?}, ...],
       "summary": {"total", "passed", "failed", "skipped", "errored"},
       "failure_logs": {"<identity>": "<rel path>"},
       "warnings": [{"kind", "message"}, ...]}``

    Status aggregation mirrors gotest/cargo:
    - Any failing OR errored test → ``"failed"``.
    - No failing/errored tests, returncode == 0 → ``"passed"``.
    - No failing/errored tests, returncode != 0 → ``"errored"`` (build
      / harness failure after some tests ran).
    """

    tests_raw = payload.get("tests")
    if not isinstance(tests_raw, list):
        raise AdapterInvocationError(
            "junit payload missing 'tests' array",
            kind="unparseable-output",
        )

    failure_logs_raw = payload.get("failure_logs")
    failure_logs: Mapping[str, str] = (
        {str(k): str(v) for k, v in failure_logs_raw.items() if isinstance(v, str)}
        if isinstance(failure_logs_raw, Mapping)
        else {}
    )

    test_results: list[TestResult] = []
    summary: dict[str, int] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errored": 0,
    }
    for entry in tests_raw:
        if not isinstance(entry, Mapping):
            continue
        identity = str(entry.get("identity", ""))
        if not identity:
            continue
        status = str(entry.get("status", "unknown"))

        # `errored` and `failed` are normalized to the run record's
        # outcome vocabulary `"errored"` / `"failed"` directly — JUnit
        # XML's <error> vs <failure> distinction is preserved.
        if status in summary:
            summary[status] += 1

        duration_raw = entry.get("duration_ms")
        duration_ms = duration_raw if isinstance(duration_raw, int) else None

        failure_reference: str | None = None
        if status in FAIL_LIKE_OUTCOMES:
            failure_reference = failure_logs.get(identity)
            if failure_reference is None:
                # Adapter elected not to write a per-test log (e.g.
                # the <failure> element was empty). Surface the
                # failure message inline for parity with pytest's
                # inline failure_reference.
                failure_payload = entry.get("failure")
                if isinstance(failure_payload, Mapping):
                    message = failure_payload.get("message")
                    type_ = failure_payload.get("type")
                    parts: list[str] = []
                    if isinstance(type_, str) and type_:
                        parts.append(type_)
                    if isinstance(message, str) and message:
                        parts.append(message)
                    if parts:
                        failure_reference = ": ".join(parts)

        test_results.append(
            TestResult(
                node_id=identity,
                outcome=status,
                duration_ms=duration_ms,
                failure_reference=failure_reference,
            )
        )

    summary["total"] = len(test_results)

    status_agg = _aggregate_junit_status(
        returncode=returncode,
        test_results=tuple(test_results),
    )
    return status_agg, summary, tuple(test_results)


def _aggregate_junit_status(
    *,
    returncode: int,
    test_results: tuple[TestResult, ...],
) -> str:
    """Decide passed / failed / errored from JUnit signals.

    Maven/Gradle exit non-zero whenever a test failed OR a build step
    after compile crashed. The split:
    - Any failing/errored TestResult → ``"failed"``.
    - No failing tests, returncode == 0 → ``"passed"``.
    - No failing tests, returncode != 0 → ``"errored"``.
    """

    failures = sum(
        1 for tr in test_results if tr.outcome in FAIL_LIKE_OUTCOMES
    )
    if failures:
        return "failed"
    if returncode == 0:
        return "passed"
    return "errored"


# ---------------------------------------------------------------------------
# xunit payload normalization (Phase 2.5 sixth-and-last-ecosystem slice)
# ---------------------------------------------------------------------------


def _normalize_xunit_payload(
    payload: Mapping[str, Any],
    *,
    returncode: int,
) -> tuple[str, dict[str, int], tuple[TestResult, ...]]:
    """Normalize the dotnet/xunit adapter's payload into Run Record components.

    Payload shape (set by ``dotnet_adapter.run_xunit`` per task brief §3.1):

    ``{"csproj": "<rel path>",
       "xunit_major_version": 2 | 3 | 0,
       "xunit_version": "<2.6.0 | ...>",
       "coverlet_version": "<6.0.2 | ...>" | None,
       "coverage_mode": "per-test" | "aggregate" | None,
       "tests": [{"identity", "test_id", "class_name", "method_name",
                  "status", "duration_ms", "failure": {message, type, stack},
                  "stdout", "stderr"}, ...],
       "summary": {"total", "passed", "failed", "skipped", "errored"},
       "failure_logs": {"<identity>": "<rel path>"},
       "warnings": [{"kind", "message"}, ...]}``

    Status aggregation mirrors junit/gotest/cargo:
    - Any failing OR errored test → ``"failed"``.
    - No failing/errored tests, returncode == 0 → ``"passed"``.
    - No failing/errored tests, returncode != 0 → ``"errored"`` (build /
      VSTest harness failure after some tests ran — TRX still parses).
    """

    tests_raw = payload.get("tests")
    if not isinstance(tests_raw, list):
        raise AdapterInvocationError(
            "xunit payload missing 'tests' array",
            kind="unparseable-output",
        )

    failure_logs_raw = payload.get("failure_logs")
    failure_logs: Mapping[str, str] = (
        {str(k): str(v) for k, v in failure_logs_raw.items() if isinstance(v, str)}
        if isinstance(failure_logs_raw, Mapping)
        else {}
    )

    test_results: list[TestResult] = []
    summary: dict[str, int] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errored": 0,
    }
    for entry in tests_raw:
        if not isinstance(entry, Mapping):
            continue
        identity = str(entry.get("identity", ""))
        if not identity:
            continue
        status = str(entry.get("status", "unknown"))

        if status in summary:
            summary[status] += 1

        duration_raw = entry.get("duration_ms")
        duration_ms = duration_raw if isinstance(duration_raw, int) else None

        failure_reference: str | None = None
        if status in FAIL_LIKE_OUTCOMES:
            failure_reference = failure_logs.get(identity)
            if failure_reference is None:
                # Adapter elected not to write a per-test log (e.g. the
                # TRX <ErrorInfo> element was empty). Surface the failure
                # message inline for parity with pytest/junit's inline
                # failure_reference path.
                failure_payload = entry.get("failure")
                if isinstance(failure_payload, Mapping):
                    message = failure_payload.get("message")
                    type_ = failure_payload.get("type")
                    parts: list[str] = []
                    if isinstance(type_, str) and type_:
                        parts.append(type_)
                    if isinstance(message, str) and message:
                        parts.append(message)
                    if parts:
                        failure_reference = ": ".join(parts)

        test_results.append(
            TestResult(
                node_id=identity,
                outcome=status,
                duration_ms=duration_ms,
                failure_reference=failure_reference,
            )
        )

    summary["total"] = len(test_results)

    status_agg = _aggregate_xunit_status(
        returncode=returncode,
        test_results=tuple(test_results),
    )
    return status_agg, summary, tuple(test_results)


def _aggregate_xunit_status(
    *,
    returncode: int,
    test_results: tuple[TestResult, ...],
) -> str:
    """Decide passed / failed / errored from xunit / VSTest signals.

    ``dotnet test`` exits non-zero whenever any test failed OR a build
    step (compile) failed before test execution. The split mirrors
    ``_aggregate_junit_status`` because the semantic contract is the
    same — both build-tool-driven engines surface test failure as a
    non-zero process exit:
    - Any failing/errored TestResult → ``"failed"``.
    - No failing tests, returncode == 0 → ``"passed"``.
    - No failing tests, returncode != 0 → ``"errored"`` (e.g. compile
      failure that ran zero tests, or a VSTest harness error after some
      tests passed).

    Note: ``dotnet test``'s exit code is empirically ``1`` when ≥1 test
    fails (verified on equipped host SDK 8.0.421 + xunit 2.6.0). The
    `metadata.native_exit_code` forensic surface preserves this value
    regardless of the derived ``status``.
    """

    failures = sum(
        1 for tr in test_results if tr.outcome in FAIL_LIKE_OUTCOMES
    )
    if failures:
        return "failed"
    if returncode == 0:
        return "passed"
    return "errored"


__all__ = ["normalize_native_result"]
