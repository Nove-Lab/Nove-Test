"""Unit tests for `novetest.run.normalizer`."""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.run.errors import AdapterInvocationError
from novetest.run.normalizer import normalize_native_result
from novetest.run.types import NativeEngineContext, NativeResult


def _native_result(payload: dict[str, object], tmp_path: Path) -> NativeResult:
    return NativeResult(
        engine_name="pytest",
        payload=payload,
        artifact_paths={
            "pytest_json_report": tmp_path / "pytest-report.json",
            "stdout": tmp_path / "stdout.log",
            "stderr": tmp_path / "stderr.log",
        },
        returncode=0,
        started_at_ms=1_700_000_000_000,
        completed_at_ms=1_700_000_000_500,
        engine_version="8.0.0",
    )


PASSING_PAYLOAD: dict[str, object] = {
    "exitcode": 0,
    "summary": {"passed": 2, "total": 2, "collected": 2},
    "tests": [
        {
            "nodeid": "tests/test_x.py::test_a",
            "outcome": "passed",
            "setup": {"outcome": "passed", "duration": 0.001},
            "call": {"outcome": "passed", "duration": 0.002},
            "teardown": {"outcome": "passed", "duration": 0.001},
        },
        {
            "nodeid": "tests/test_x.py::test_b",
            "outcome": "passed",
            "call": {"outcome": "passed", "duration": 0.004},
        },
    ],
}


FAILING_PAYLOAD: dict[str, object] = {
    "exitcode": 1,
    "summary": {"passed": 1, "failed": 1, "total": 2, "collected": 2},
    "tests": [
        {
            "nodeid": "tests/test_x.py::test_ok",
            "outcome": "passed",
            "call": {"outcome": "passed", "duration": 0.001},
        },
        {
            "nodeid": "tests/test_x.py::test_bad",
            "outcome": "failed",
            "call": {
                "outcome": "failed",
                "duration": 0.002,
                "crash": {
                    "path": "tests/test_x.py",
                    "lineno": 7,
                    "message": "assert 1 == 2",
                },
                "longrepr": "def test_bad():\n>   assert 1 == 2",
            },
        },
    ],
}


def test_passing_payload_yields_passed_status(tmp_path: Path) -> None:
    record = normalize_native_result(
        _native_result(PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("python", "pytest", "8.0.0"),
        target_expression="tests/",
        target_type="directory",
    )
    assert record.status == "passed"
    assert record.summary_counts == {"passed": 2, "total": 2, "collected": 2}
    assert record.engine_name == "pytest"
    assert record.ecosystem == "python"
    assert record.engine_version == "8.0.0"
    assert len(record.test_results) == 2
    assert {tr.outcome for tr in record.test_results} == {"passed"}
    assert "pytest_json_report" in record.artifact_paths


def test_failing_payload_yields_failed_status_and_failure_reference(tmp_path: Path) -> None:
    record = normalize_native_result(
        _native_result(FAILING_PAYLOAD, tmp_path),
        NativeEngineContext("python", "pytest"),
        target_expression="tests/",
        target_type="directory",
    )
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].node_id == "tests/test_x.py::test_bad"
    assert failed[0].failure_reference is not None
    assert "assert 1 == 2" in failed[0].failure_reference


def test_internal_error_exit_code_yields_errored(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "exitcode": 3,
        "summary": {"total": 0, "collected": 0},
        "tests": [],
    }
    record = normalize_native_result(
        _native_result(payload, tmp_path),
        NativeEngineContext("python", "pytest"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"


def test_duration_is_summed_across_phases(tmp_path: Path) -> None:
    record = normalize_native_result(
        _native_result(PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("python", "pytest"),
        target_expression="tests/",
        target_type="directory",
    )
    durations = [tr.duration_ms for tr in record.test_results]
    assert durations[0] == 4  # 0.001 + 0.002 + 0.001 -> 0.004s -> 4ms
    assert durations[1] == 4  # call 0.004 -> 4ms


def test_unimplemented_engine_raises(tmp_path: Path) -> None:
    """Phase 2.5 implemented jest, so this test now uses xunit as the
    'unimplemented' example. Any of junit / go-test / cargo-test / xunit
    would behave identically.
    """

    with pytest.raises(AdapterInvocationError):
        normalize_native_result(
            _native_result({}, tmp_path),
            NativeEngineContext("dotnet", "xunit"),
            target_expression="",
            target_type="workspace",
        )


def test_missing_summary_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterInvocationError):
        normalize_native_result(
            _native_result({"exitcode": 0, "tests": []}, tmp_path),
            NativeEngineContext("python", "pytest"),
            target_expression="",
            target_type="workspace",
        )


def test_artifact_paths_serialized_as_strings(tmp_path: Path) -> None:
    record = normalize_native_result(
        _native_result(PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("python", "pytest"),
        target_expression="tests/",
        target_type="directory",
    )
    for value in record.artifact_paths.values():
        assert isinstance(value, str)


# ---------------------------------------------------------------------------
# jest payload normalization (Phase 2.5)
# ---------------------------------------------------------------------------


def _jest_native_result(
    payload: dict[str, object],
    tmp_path: Path,
    *,
    workspace_root: Path | None = Path("/abs"),
) -> NativeResult:
    return NativeResult(
        engine_name="jest",
        payload=payload,
        artifact_paths={
            "jest_json_report": tmp_path / "jest-results.json",
            "stdout": tmp_path / "stdout.log",
            "stderr": tmp_path / "stderr.log",
        },
        returncode=0,
        started_at_ms=1_700_000_000_000,
        completed_at_ms=1_700_000_000_500,
        engine_version="29.7.0",
        workspace_root=workspace_root,
    )


# Canned payloads mirror the REAL jest 29.7.0 `--json --outputFile` report
# shape: the per-suite assertion entries live under `assertionResults`
# (W2-S11 / MT Issue 1 — the normalizer used to read only the internal
# pre-serializer key `testResults`, which real reports never carry, so
# every jest run normalized to ZERO per-test results).
JEST_PASSING_PAYLOAD: dict[str, object] = {
    "success": True,
    "numPassedTests": 2,
    "numFailedTests": 0,
    "numPendingTests": 0,
    "numTodoTests": 0,
    "numTotalTests": 2,
    "testResults": [
        {
            "name": "/abs/__tests__/math.test.js",
            "status": "passed",
            "assertionResults": [
                {
                    "ancestorTitles": ["math"],
                    "title": "add returns the sum of two integers",
                    "status": "passed",
                    "duration": 5,
                    "failureMessages": [],
                },
                {
                    "ancestorTitles": ["math"],
                    "title": "subtract works",
                    "status": "passed",
                    "duration": 3,
                    "failureMessages": [],
                },
            ],
        }
    ],
}


JEST_FAILING_PAYLOAD: dict[str, object] = {
    "success": False,
    "numPassedTests": 1,
    "numFailedTests": 1,
    "numPendingTests": 0,
    "numTodoTests": 0,
    "numTotalTests": 2,
    "testResults": [
        {
            "name": "/abs/__tests__/math.test.js",
            "status": "failed",
            "assertionResults": [
                {
                    "ancestorTitles": ["math"],
                    "title": "add works",
                    "status": "passed",
                    "duration": 2,
                    "failureMessages": [],
                },
                {
                    "ancestorTitles": ["math"],
                    "title": "subtract works",
                    "status": "failed",
                    "duration": 4,
                    "failureMessages": [
                        "Error: expect(received).toBe(expected)\n\nExpected: 6\nReceived: 7"
                    ],
                },
            ],
        }
    ],
}


def test_jest_passing_payload_yields_passed_status(tmp_path: Path) -> None:
    record = normalize_native_result(
        _jest_native_result(JEST_PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("javascript-typescript", "jest", "29.7.0"),
        target_expression="__tests__/",
        target_type="directory",
    )
    assert record.status == "passed"
    assert record.engine_name == "jest"
    assert record.ecosystem == "javascript-typescript"
    assert record.engine_version == "29.7.0"
    assert record.summary_counts["passed"] == 2
    assert record.summary_counts["failed"] == 0
    assert record.summary_counts["total"] == 2
    assert len(record.test_results) == 2
    assert {tr.outcome for tr in record.test_results} == {"passed"}
    # Nodeid format: <workspace-relative POSIX file>::<ancestors>::<title>
    assert [tr.node_id for tr in record.test_results] == [
        "__tests__/math.test.js::math::add returns the sum of two integers",
        "__tests__/math.test.js::math::subtract works",
    ]
    assert "jest_json_report" in record.artifact_paths


def test_jest_failing_payload_yields_failed_status_and_failure_reference(
    tmp_path: Path,
) -> None:
    record = normalize_native_result(
        _jest_native_result(JEST_FAILING_PAYLOAD, tmp_path),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="__tests__/",
        target_type="directory",
    )
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_reference is not None
    assert "Expected: 6" in failed[0].failure_reference


def test_jest_duration_is_milliseconds_per_test(tmp_path: Path) -> None:
    """jest reports per-test duration in ms (unlike pytest's seconds)."""

    record = normalize_native_result(
        _jest_native_result(JEST_PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="",
        target_type="workspace",
    )
    durations = [tr.duration_ms for tr in record.test_results]
    assert durations == [5, 3]


def test_jest_missing_test_results_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterInvocationError):
        normalize_native_result(
            _jest_native_result({"success": True}, tmp_path),
            NativeEngineContext("javascript-typescript", "jest"),
            target_expression="",
            target_type="workspace",
        )


def test_jest_success_false_with_no_per_test_failures_is_errored(tmp_path: Path) -> None:
    """A jest run whose ``success: false`` cannot be attributed to any
    parseable per-test failure is surfaced as ``errored`` (typically a
    config error or suite-level import failure).
    """

    payload: dict[str, object] = {
        "success": False,
        "numPassedTests": 0,
        "numFailedTests": 0,
        "numTotalTests": 0,
        "testResults": [],
    }
    record = normalize_native_result(
        _jest_native_result(payload, tmp_path),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"


def test_jest_pending_test_maps_to_skipped_outcome(tmp_path: Path) -> None:
    """jest's ``pending`` / ``todo`` statuses both map to ``skipped`` in TestResult."""

    payload: dict[str, object] = {
        "success": True,
        "numPassedTests": 0,
        "numFailedTests": 0,
        "numPendingTests": 1,
        "numTodoTests": 1,
        "numTotalTests": 2,
        "testResults": [
            {
                "name": "/abs/__tests__/x.test.js",
                "status": "passed",
                "assertionResults": [
                    {
                        "ancestorTitles": ["g"],
                        "title": "pending case",
                        "status": "pending",
                        "duration": 0,
                        "failureMessages": [],
                    },
                    {
                        "ancestorTitles": ["g"],
                        "title": "todo case",
                        "status": "todo",
                        "duration": 0,
                        "failureMessages": [],
                    },
                ],
            }
        ],
    }
    record = normalize_native_result(
        _jest_native_result(payload, tmp_path),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="",
        target_type="workspace",
    )
    assert {tr.outcome for tr in record.test_results} == {"skipped"}
    assert record.status == "passed"


def test_jest29_assertion_results_yield_non_empty_test_results(tmp_path: Path) -> None:
    """MT Issue 1 canary (W2-S11): the jest-29 report shape — per-suite
    ``assertionResults`` — MUST produce per-test results. Pre-fix the
    normalizer read only the internal per-suite ``testResults`` key, so a
    real report flattened to an EMPTY tuple while summary counts parsed
    fine (silently starving regression compare / localization / replay).
    """

    record = normalize_native_result(
        _jest_native_result(JEST_PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("javascript-typescript", "jest", "29.7.0"),
        target_expression="__tests__/",
        target_type="directory",
    )
    assert len(record.test_results) == 2
    assert {tr.outcome for tr in record.test_results} == {"passed"}


def test_jest_legacy_nested_testresults_key_still_parses(tmp_path: Path) -> None:
    """Fallback pin: a payload nesting assertions under the per-suite
    ``testResults`` key (jest's internal pre-serializer field name)
    normalizes identically to the ``assertionResults`` shape."""

    payload: dict[str, object] = {
        "success": True,
        "numPassedTests": 1,
        "numFailedTests": 0,
        "numTotalTests": 1,
        "testResults": [
            {
                "name": "/abs/__tests__/math.test.js",
                "status": "passed",
                "testResults": [
                    {
                        "ancestorTitles": ["math"],
                        "title": "add works",
                        "status": "passed",
                        "duration": 2,
                        "failureMessages": [],
                    },
                ],
            }
        ],
    }
    record = normalize_native_result(
        _jest_native_result(payload, tmp_path),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="",
        target_type="workspace",
    )
    assert [tr.node_id for tr in record.test_results] == [
        "__tests__/math.test.js::math::add works"
    ]
    assert record.test_results[0].outcome == "passed"


def _jest_single_suite_payload(suite_name: str) -> dict[str, object]:
    """One-suite, one-test jest-29-shaped payload for node_id shape pins."""

    return {
        "success": True,
        "numPassedTests": 1,
        "numFailedTests": 0,
        "numTotalTests": 1,
        "testResults": [
            {
                "name": suite_name,
                "status": "passed",
                "assertionResults": [
                    {
                        "ancestorTitles": ["math"],
                        "title": "add works",
                        "status": "passed",
                        "duration": 1,
                        "failureMessages": [],
                    },
                ],
            }
        ],
    }


def _normalize_single_suite(
    suite_name: str, workspace_root: Path | None, tmp_path: Path
) -> str:
    record = normalize_native_result(
        _jest_native_result(
            _jest_single_suite_payload(suite_name),
            tmp_path,
            workspace_root=workspace_root,
        ),
        NativeEngineContext("javascript-typescript", "jest"),
        target_expression="",
        target_type="workspace",
    )
    (test_result,) = record.test_results
    return test_result.node_id


def test_jest_node_id_posix_suite_path_is_workspace_relative(tmp_path: Path) -> None:
    """RUN-13: an absolute POSIX suite path relativizes against the
    workspace root — node_ids are neither absolute nor host-specific."""

    node_id = _normalize_single_suite(
        "/repo/__tests__/math.test.js", Path("/repo"), tmp_path
    )
    assert node_id == "__tests__/math.test.js::math::add works"


def test_jest_node_id_windows_suite_path_is_workspace_relative(tmp_path: Path) -> None:
    """RUN-13: an absolute Windows-style suite path (backslashes, drive
    letter) yields the SAME workspace-relative POSIX node_id — a run
    recorded on Windows compares cleanly against one recorded on POSIX."""

    node_id = _normalize_single_suite(
        "C:\\repo\\__tests__\\math.test.js", Path("C:\\repo"), tmp_path
    )
    assert node_id == "__tests__/math.test.js::math::add works"
    assert "\\" not in node_id


def test_jest_suite_file_outside_workspace_root_falls_back_to_raw_posix(
    tmp_path: Path,
) -> None:
    """Edge pin: a suite file NOT under the workspace root (should not
    happen for jest, whose rootDir is the workspace) keeps the raw path
    in POSIX separators instead of crashing."""

    node_id = _normalize_single_suite(
        "/elsewhere/x.test.js", Path("/repo"), tmp_path
    )
    assert node_id == "/elsewhere/x.test.js::math::add works"


def test_jest_node_id_without_workspace_root_keeps_raw_posix(tmp_path: Path) -> None:
    """Edge pin: no workspace root recorded (``NativeResult.workspace_root``
    is None) — the raw suite path survives, but still in POSIX separators."""

    node_id = _normalize_single_suite(
        "C:\\repo\\__tests__\\math.test.js", None, tmp_path
    )
    assert node_id == "C:/repo/__tests__/math.test.js::math::add works"


# ---------------------------------------------------------------------------
# go-test payload normalization (Phase 3 adapter backlog #1)
# ---------------------------------------------------------------------------


def _gotest_native_result(
    payload: dict[str, object],
    tmp_path: Path,
    *,
    returncode: int = 0,
) -> NativeResult:
    return NativeResult(
        engine_name="go-test",
        payload=payload,
        artifact_paths={
            "gotest_events_jsonl": tmp_path / "events.jsonl",
            "stdout": tmp_path / "stdout.log",
            "stderr": tmp_path / "stderr.log",
        },
        returncode=returncode,
        started_at_ms=1_700_000_000_000,
        completed_at_ms=1_700_000_000_500,
        engine_version="1.23.4",
    )


GOTEST_PASSING_PAYLOAD: dict[str, object] = {
    "events": [
        {"Action": "run", "Package": "example.com/foo", "Test": "TestAdd"},
        {
            "Action": "output", "Package": "example.com/foo",
            "Test": "TestAdd", "Output": "--- PASS: TestAdd (0.00s)\n",
        },
        {"Action": "pass", "Package": "example.com/foo", "Test": "TestAdd", "Elapsed": 0.003},
        {"Action": "run", "Package": "example.com/foo", "Test": "TestSub"},
        {"Action": "pass", "Package": "example.com/foo", "Test": "TestSub", "Elapsed": 0.001},
        # Package-level terminal action — no `Test` field; must NOT produce a row.
        {"Action": "pass", "Package": "example.com/foo", "Elapsed": 0.004},
    ],
    "packages": ["example.com/foo"],
    "failure_logs": {},
}


GOTEST_FAILING_PAYLOAD: dict[str, object] = {
    "events": [
        {"Action": "run", "Package": "example.com/foo", "Test": "TestPass"},
        {"Action": "pass", "Package": "example.com/foo", "Test": "TestPass", "Elapsed": 0.001},
        {"Action": "run", "Package": "example.com/foo", "Test": "TestFail"},
        {
            "Action": "output", "Package": "example.com/foo",
            "Test": "TestFail", "Output": "    foo_test.go:10: assertion failed\n",
        },
        {"Action": "fail", "Package": "example.com/foo", "Test": "TestFail", "Elapsed": 0.002},
        {"Action": "fail", "Package": "example.com/foo", "Elapsed": 0.003},
    ],
    "packages": ["example.com/foo"],
    "failure_logs": {
        "example.com/foo::TestFail": "native/failures/example.com_foo__TestFail.log",
    },
}


def test_gotest_passing_payload_yields_passed_status(tmp_path: Path) -> None:
    record = normalize_native_result(
        _gotest_native_result(GOTEST_PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("go", "go-test", "1.23.4"),
        target_expression="./...",
        target_type="workspace",
    )
    assert record.status == "passed"
    assert record.engine_name == "go-test"
    assert record.ecosystem == "go"
    assert record.engine_version == "1.23.4"
    assert record.summary_counts["passed"] == 2
    assert record.summary_counts["failed"] == 0
    assert record.summary_counts["total"] == 2
    assert len(record.test_results) == 2
    # node_id format: <Package>::<Test>
    assert {tr.node_id for tr in record.test_results} == {
        "example.com/foo::TestAdd",
        "example.com/foo::TestSub",
    }
    # Elapsed (seconds, float) → duration_ms (int).
    durations = {tr.node_id: tr.duration_ms for tr in record.test_results}
    assert durations["example.com/foo::TestAdd"] == 3
    assert durations["example.com/foo::TestSub"] == 1


def test_gotest_failing_payload_yields_failed_status_and_failure_reference(
    tmp_path: Path,
) -> None:
    record = normalize_native_result(
        _gotest_native_result(GOTEST_FAILING_PAYLOAD, tmp_path, returncode=1),
        NativeEngineContext("go", "go-test"),
        target_expression="./...",
        target_type="workspace",
    )
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].node_id == "example.com/foo::TestFail"
    assert failed[0].failure_reference == "native/failures/example.com_foo__TestFail.log"


def test_gotest_subtests_produce_parent_and_child_test_results(tmp_path: Path) -> None:
    """A parent test with subtests produces TestResult rows for both the
    parent AND each subtest — Go really does emit terminal actions for
    each. Downstream consumers can filter on `/` in node_id if they want
    only leaves.
    """

    payload: dict[str, object] = {
        "events": [
            {"Action": "run", "Package": "example.com/foo", "Test": "TestParent"},
            {"Action": "run", "Package": "example.com/foo", "Test": "TestParent/zero"},
            {"Action": "pass", "Package": "example.com/foo", "Test": "TestParent/zero", "Elapsed": 0},
            {"Action": "run", "Package": "example.com/foo", "Test": "TestParent/one"},
            {"Action": "pass", "Package": "example.com/foo", "Test": "TestParent/one", "Elapsed": 0},
            {"Action": "pass", "Package": "example.com/foo", "Test": "TestParent", "Elapsed": 0.002},
        ],
        "packages": ["example.com/foo"],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _gotest_native_result(payload, tmp_path),
        NativeEngineContext("go", "go-test"),
        target_expression="",
        target_type="workspace",
    )
    node_ids = {tr.node_id for tr in record.test_results}
    assert "example.com/foo::TestParent" in node_ids
    assert "example.com/foo::TestParent/zero" in node_ids
    assert "example.com/foo::TestParent/one" in node_ids
    assert all(tr.outcome == "passed" for tr in record.test_results)


def test_gotest_skip_action_maps_to_skipped_outcome(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "events": [
            {"Action": "run", "Package": "example.com/foo", "Test": "TestX"},
            {"Action": "skip", "Package": "example.com/foo", "Test": "TestX", "Elapsed": 0},
        ],
        "packages": ["example.com/foo"],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _gotest_native_result(payload, tmp_path),
        NativeEngineContext("go", "go-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "passed"  # returncode=0, no failures
    assert record.summary_counts["skipped"] == 1
    assert {tr.outcome for tr in record.test_results} == {"skipped"}


def test_gotest_unknown_terminal_action_maps_to_unknown_outcome(tmp_path: Path) -> None:
    """Per the supported-engine-matrix decision (`2026-05-25`): unknown
    terminal actions (none expected today, but Go MAY add one) map to
    ``"unknown"`` rather than raising. Visible-not-silent.
    """

    payload: dict[str, object] = {
        "events": [
            {"Action": "run", "Package": "example.com/foo", "Test": "TestX"},
            # `aborted` is a hypothetical future Go action not in the
            # current `pass | fail | skip` set; the dispatcher's `if
            # action not in (...): continue` clause is the path under test.
            # We can't directly trigger an `unknown` row that way because
            # the parser drops non-terminal actions; instead, the
            # `unknown` outcome shows up via the defensive `if action in
            # ("run", "pause", "cont", "output", "bench"): continue`
            # bypass for any action NOT in the named set. To make this
            # visible, supply a terminal-looking action of an unknown
            # name and verify the result.
            {"Action": "aborted", "Package": "example.com/foo", "Test": "TestX", "Elapsed": 0.5},
        ],
        "packages": ["example.com/foo"],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _gotest_native_result(payload, tmp_path),
        NativeEngineContext("go", "go-test"),
        target_expression="",
        target_type="workspace",
    )
    outcomes = [tr.outcome for tr in record.test_results]
    assert outcomes == ["unknown"]


def test_gotest_returncode_nonzero_with_no_failures_yields_errored(tmp_path: Path) -> None:
    """A non-zero exit with no failing tests (e.g. test binary crash after
    a successful test ran) surfaces as ``errored`` so callers do not
    misread the run as ``passed``.
    """

    record = normalize_native_result(
        _gotest_native_result(GOTEST_PASSING_PAYLOAD, tmp_path, returncode=2),
        NativeEngineContext("go", "go-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"


def test_gotest_missing_events_array_raises(tmp_path: Path) -> None:
    """A payload missing the top-level ``events`` array is unparseable —
    the adapter is the only writer and should always include it.
    """

    with pytest.raises(AdapterInvocationError) as exc_info:
        normalize_native_result(
            _gotest_native_result({"packages": []}, tmp_path),
            NativeEngineContext("go", "go-test"),
            target_expression="",
            target_type="workspace",
        )
    assert exc_info.value.kind == "unparseable-output"


# ---------------------------------------------------------------------------
# cargo-test payload normalization (Phase 3 adapter backlog #2)
# ---------------------------------------------------------------------------


def _cargo_native_result(
    payload: dict[str, object],
    tmp_path: Path,
    *,
    returncode: int = 0,
) -> NativeResult:
    return NativeResult(
        engine_name="cargo-test",
        payload=payload,
        artifact_paths={
            "cargo_events_jsonl": tmp_path / "events.jsonl",
            "stdout": tmp_path / "stdout.log",
            "stderr": tmp_path / "stderr.log",
        },
        returncode=returncode,
        started_at_ms=1_700_000_000_000,
        completed_at_ms=1_700_000_000_500,
        engine_version="1.74.0",
    )


CARGO_PASSING_PAYLOAD: dict[str, object] = {
    "events": [
        {"type": "suite", "event": "started", "test_count": 2},
        {"type": "test", "event": "started", "name": "my_crate::tests::test_add"},
        {
            "type": "test",
            "event": "ok",
            "name": "my_crate::tests::test_add",
            "exec_time": 0.003,
        },
        {"type": "test", "event": "started", "name": "my_crate::tests::test_sub"},
        {
            "type": "test",
            "event": "ok",
            "name": "my_crate::tests::test_sub",
            "exec_time": 0.001,
        },
        {"type": "suite", "event": "ok", "passed": 2, "failed": 0},
    ],
    "binaries": [],
    "failure_logs": {},
}


CARGO_FAILING_PAYLOAD: dict[str, object] = {
    "events": [
        {"type": "suite", "event": "started", "test_count": 2},
        {"type": "test", "event": "started", "name": "my_crate::tests::test_ok"},
        {"type": "test", "event": "ok", "name": "my_crate::tests::test_ok", "exec_time": 0.002},
        {"type": "test", "event": "started", "name": "my_crate::tests::test_bad"},
        {
            "type": "test",
            "event": "failed",
            "name": "my_crate::tests::test_bad",
            "stdout": "thread 'tests::test_bad' panicked at 'assertion `left == right` failed'\n",
            "exec_time": 0.001,
        },
        {"type": "suite", "event": "failed", "passed": 1, "failed": 1},
    ],
    "binaries": [],
    "failure_logs": {
        "my_crate::tests::test_bad": "native/failures/my_crate__tests__test_bad.log",
    },
}


def test_cargo_passing_payload_yields_passed_status(tmp_path: Path) -> None:
    record = normalize_native_result(
        _cargo_native_result(CARGO_PASSING_PAYLOAD, tmp_path),
        NativeEngineContext("rust", "cargo-test", "1.74.0"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "passed"
    assert record.engine_name == "cargo-test"
    assert record.ecosystem == "rust"
    assert record.engine_version == "1.74.0"
    assert record.summary_counts["passed"] == 2
    assert record.summary_counts["failed"] == 0
    assert record.summary_counts["total"] == 2
    assert len(record.test_results) == 2
    # node_id = libtest-json `name` field, used directly.
    assert {tr.node_id for tr in record.test_results} == {
        "my_crate::tests::test_add",
        "my_crate::tests::test_sub",
    }
    # exec_time (seconds, float) → duration_ms (int).
    durations = {tr.node_id: tr.duration_ms for tr in record.test_results}
    assert durations["my_crate::tests::test_add"] == 3
    assert durations["my_crate::tests::test_sub"] == 1


def test_cargo_failing_payload_yields_failed_status_and_failure_reference(
    tmp_path: Path,
) -> None:
    record = normalize_native_result(
        _cargo_native_result(CARGO_FAILING_PAYLOAD, tmp_path, returncode=1),
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].node_id == "my_crate::tests::test_bad"
    assert (
        failed[0].failure_reference
        == "native/failures/my_crate__tests__test_bad.log"
    )


def test_cargo_integration_test_node_id_distinguishes_binary(tmp_path: Path) -> None:
    """Integration tests in `tests/foo.rs` arrive with a binary-prefixed
    `name` in nextest mode (e.g. `my_crate--integration_test::test_x`).
    The normalizer uses ``name`` directly as node_id, so the binary
    prefix surfaces verbatim — downstream consumers can distinguish
    unit-test vs integration-test rows by the `--` substring or by
    parsing the prefix.
    """

    payload: dict[str, object] = {
        "events": [
            {
                "type": "test",
                "event": "ok",
                "name": "my_crate--integration_test::test_x",
                "exec_time": 0.001,
            },
        ],
        "binaries": ["my_crate--integration_test"],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _cargo_native_result(payload, tmp_path),
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )
    assert len(record.test_results) == 1
    assert record.test_results[0].node_id == "my_crate--integration_test::test_x"


def test_cargo_ignored_event_maps_to_skipped(tmp_path: Path) -> None:
    """libtest's ``ignored`` event (``#[ignore]``) maps to ``skipped``.

    Aggregate status stays ``passed`` when returncode is 0.
    """

    payload: dict[str, object] = {
        "events": [
            {"type": "test", "event": "ignored", "name": "my_crate::tests::test_x"},
        ],
        "binaries": [],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _cargo_native_result(payload, tmp_path),
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "passed"
    assert record.summary_counts["skipped"] == 1
    assert {tr.outcome for tr in record.test_results} == {"skipped"}


def test_cargo_unknown_terminal_event_maps_to_unknown_outcome(tmp_path: Path) -> None:
    """Per the supported-engine-matrix decision: unknown terminal events
    map to ``"unknown"`` rather than raising. Visible-not-silent.
    """

    payload: dict[str, object] = {
        "events": [
            # `aborted` is a hypothetical future libtest event not in the
            # current `ok | failed | ignored` set; the parser drops the
            # known-non-terminal `started` event but falls through to
            # outcome-mapping for any other terminal-shaped event.
            {
                "type": "test",
                "event": "aborted",
                "name": "my_crate::tests::test_x",
                "exec_time": 0.5,
            },
        ],
        "binaries": [],
        "failure_logs": {},
    }
    record = normalize_native_result(
        _cargo_native_result(payload, tmp_path),
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )
    outcomes = [tr.outcome for tr in record.test_results]
    assert outcomes == ["unknown"]


def test_cargo_returncode_nonzero_with_no_failures_yields_errored(
    tmp_path: Path,
) -> None:
    """Non-zero exit with no failing tests (e.g. build-script post-test
    crash) surfaces as ``errored`` so callers do not misread the run as
    ``passed``.
    """

    record = normalize_native_result(
        _cargo_native_result(CARGO_PASSING_PAYLOAD, tmp_path, returncode=101),
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"


def test_cargo_missing_events_array_raises(tmp_path: Path) -> None:
    """A payload missing the top-level ``events`` array is unparseable —
    the adapter is the only writer and should always include it.
    """

    with pytest.raises(AdapterInvocationError) as exc_info:
        normalize_native_result(
            _cargo_native_result({"binaries": []}, tmp_path),
            NativeEngineContext("rust", "cargo-test"),
            target_expression="",
            target_type="workspace",
        )
    assert exc_info.value.kind == "unparseable-output"


# ---------------------------------------------------------------------------
# NativeResult.metadata typed-slot overlay (Phase 3, Issue 2 follow-up;
# `decisions/2026-05-30-native-result-metadata-slot.md` — option (b))
# ---------------------------------------------------------------------------


def _native_result_with_metadata(
    payload: dict[str, object],
    tmp_path: Path,
    *,
    metadata: dict[str, str],
    returncode: int = 0,
) -> NativeResult:
    """Build a cargo-shaped `NativeResult` carrying the given typed metadata.

    Engine choice is incidental — these tests exercise the normalizer's
    overlay logic, not cargo-specific parsing. Cargo is used because it
    is the only engine that already populates `metadata` (so the test
    surface stays close to real-world usage), but the overlay
    contract is engine-agnostic.
    """

    return NativeResult(
        engine_name="cargo-test",
        payload=payload,
        artifact_paths={
            "cargo_events_jsonl": tmp_path / "events.jsonl",
            "stdout": tmp_path / "stdout.log",
            "stderr": tmp_path / "stderr.log",
        },
        returncode=returncode,
        started_at_ms=1_700_000_000_000,
        completed_at_ms=1_700_000_000_500,
        engine_version="1.74.0",
        metadata=metadata,
    )


def test_metadata_overlay_passes_through_adapter_keys(tmp_path: Path) -> None:
    """Positive case: the normalizer must overlay every key the adapter
    set on `NativeResult.metadata` onto the `RunRecord.metadata` dict,
    sitting alongside the normalizer-owned `native_exit_code`.

    This is the Issue-2 resolution check: pre-migration, the cargo
    adapter stashed `nextest_version` in `payload[...]` and the
    normalizer silently dropped it; post-migration, the typed slot
    surfaces verbatim. The strict `dict[str, str]` typing prevents
    accidental `None` smuggling.
    """

    native = _native_result_with_metadata(
        CARGO_PASSING_PAYLOAD,
        tmp_path,
        metadata={"nextest_version": "0.9.137", "runner_profile": "ci-fast"},
    )
    record = normalize_native_result(
        native,
        NativeEngineContext("rust", "cargo-test", "1.74.0"),
        target_expression="",
        target_type="workspace",
    )

    # Normalizer-owned key still authoritative.
    assert record.metadata["native_exit_code"] == 0
    # Adapter-provided keys overlay verbatim.
    assert record.metadata["nextest_version"] == "0.9.137"
    assert record.metadata["runner_profile"] == "ci-fast"
    # The three are the only keys in the resulting metadata dict — no
    # accidental serialization noise creeps in.
    assert set(record.metadata) == {
        "native_exit_code",
        "nextest_version",
        "runner_profile",
    }


def test_metadata_overlay_defaults_to_only_native_exit_code(tmp_path: Path) -> None:
    """Default case: an adapter that stashes nothing in `metadata`
    leaves the `RunRecord.metadata` dict equal to the historical
    pre-migration shape (`{"native_exit_code": <int>}`).

    Regression-pins the public contract for the three adapters that do
    NOT yet populate `metadata` (pytest, jest, gotest — audited in
    this slice, no record-bound payload fields found).
    """

    native = _native_result_with_metadata(
        CARGO_PASSING_PAYLOAD,
        tmp_path,
        metadata={},  # adapter set nothing
        returncode=7,
    )
    record = normalize_native_result(
        native,
        NativeEngineContext("rust", "cargo-test"),
        target_expression="",
        target_type="workspace",
    )

    assert record.metadata == {"native_exit_code": 7}


def test_metadata_overlay_rejects_reserved_native_exit_code_key(
    tmp_path: Path,
) -> None:
    """Negative case: an adapter that pre-populates `native_exit_code`
    in its `NativeResult.metadata` is a programming error — the key is
    reserved for the normalizer (the only layer that knows the
    canonical exit code from the subprocess result).

    The normalizer raises `ValueError` rather than silently dropping
    the adapter's value or letting it shadow the canonical one.
    Strict-raise was picked over pop-and-warn at the
    metadata-slot decision; the project posture is
    "visible-not-silent" per `CLAUDE.md`. This guards against the
    drift the decision explicitly closed: silent payload-stash
    convention.
    """

    native = _native_result_with_metadata(
        CARGO_PASSING_PAYLOAD,
        tmp_path,
        # The value here doesn't matter — type is `str` per the typed
        # slot, but the guard fires on key presence, not value.
        metadata={"native_exit_code": "99"},
    )
    with pytest.raises(ValueError) as exc_info:
        normalize_native_result(
            native,
            NativeEngineContext("rust", "cargo-test"),
            target_expression="",
            target_type="workspace",
        )
    # Error message identifies both the offending key and the engine
    # so an adapter author can locate the bug from the traceback alone.
    msg = str(exc_info.value)
    assert "native_exit_code" in msg
    assert "cargo-test" in msg
    assert "reserved" in msg.lower()
