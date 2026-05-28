"""Integration test for the gotest adapter against the ``gotest-basic`` fixture.

This test spawns a **real** ``go test -json`` subprocess. It skips when
``go`` is not on ``PATH``. The current CI matrix has no Go cell yet, so
this test is expected to skip on every CI runner; it is intended for
local-dev exercise and the matrix-extension follow-up (Release team).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects" / "gotest-basic"
)


def _require_go() -> None:
    if shutil.which("go") is None:
        pytest.skip("requires `go` on PATH")


async def test_gotest_basic_captures_failing_test_and_subtests(tmp_path: Path) -> None:
    _require_go()

    target = resolve_test_target("", FIXTURE_ROOT)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.engine_name == "go-test"
    # `TestSubtract` fails by fixture contract → non-zero return code.
    assert result.returncode != 0

    events = result.payload["events"]
    assert isinstance(events, list) and len(events) > 0
    packages = result.payload["packages"]
    assert isinstance(packages, list)
    assert "example.com/gotestbasic" in packages

    # Failure log written for TestSubtract.
    failure_logs = result.payload["failure_logs"]
    assert isinstance(failure_logs, dict)
    assert "example.com/gotestbasic::TestSubtract" in failure_logs
    failure_rel_path = failure_logs["example.com/gotestbasic::TestSubtract"]
    failure_log = tmp_path / str(failure_rel_path)
    assert failure_log.is_file()
    log_body = failure_log.read_text(encoding="utf-8")
    assert "FAIL: TestSubtract" in log_body or "want 5" in log_body

    # `events.jsonl` round-trips.
    events_path = result.artifact_paths["gotest_events_jsonl"]
    assert events_path.is_file()
    assert events_path.read_text(encoding="utf-8").splitlines()

    # Engine version was parsed from `go version`.
    assert result.engine_version is not None
    assert result.engine_version.startswith("1.")
