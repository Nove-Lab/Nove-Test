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


def test_non_pytest_engine_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterInvocationError):
        normalize_native_result(
            _native_result({}, tmp_path),
            NativeEngineContext("javascript-typescript", "jest"),
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
