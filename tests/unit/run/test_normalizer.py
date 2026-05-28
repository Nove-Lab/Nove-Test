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


def _jest_native_result(payload: dict[str, object], tmp_path: Path) -> NativeResult:
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
    )


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
            "testResults": [
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
            "testResults": [
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
    # Nodeid format: <file>::<ancestors>::<title>
    assert all("math" in tr.node_id for tr in record.test_results)
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
                "testResults": [
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
