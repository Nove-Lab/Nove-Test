"""Unit tests for the pytest Native Engine adapter.

These tests spawn a real pytest subprocess against the fixture projects.
The adapter sets ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` and explicitly loads
``-p pytest_jsonreport`` so the dev venv's plugins do not leak in — that
isolation is verified by exercising the adapter directly here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novetest.run.adapters.pytest_adapter import (
    PYTEST_REPORT_FILENAME,
    STDERR_LOG_FILENAME,
    STDOUT_LOG_FILENAME,
    run_pytest,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target


async def test_basic_fixture_produces_report(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    result = await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.returncode == 0
    assert result.payload["exitcode"] == 0
    report_path = result.artifact_paths["pytest_json_report"]
    assert report_path.name == PYTEST_REPORT_FILENAME
    assert report_path.is_file()
    stdout_path = result.artifact_paths["stdout"]
    stderr_path = result.artifact_paths["stderr"]
    assert stdout_path.name == STDOUT_LOG_FILENAME
    assert stderr_path.name == STDERR_LOG_FILENAME
    payload_on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload_on_disk["summary"]["total"] == 3
    assert payload_on_disk["summary"]["passed"] == 3


async def test_failing_fixture_returns_failed_payload(
    failing_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", failing_workspace)
    result = await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    # pytest returns 1 when one or more tests failed.
    assert result.returncode == 1
    summary = result.payload["summary"]
    assert isinstance(summary, dict)
    assert summary.get("failed", 0) >= 1


async def test_conftest_import_error_raises_unparseable(tmp_path: Path) -> None:
    """A conftest import error aborts pytest before the JSON plugin runs.

    pytest exits 4 with no report on disk; the adapter must surface that
    as a typed `AdapterInvocationError` rather than a parse exception so
    the CLI can map it to exit code 4 with structured guidance.
    """

    target = resolve_test_target("", tmp_path)
    (tmp_path / "conftest.py").write_text(
        "import does_not_exist  # noqa: F401\n", encoding="utf-8"
    )
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    assert exc_info.value.kind == "unparseable-output"


async def test_pytest_unavailable_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point sys.executable at a binary that cannot run ``-m pytest``."""

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "executable", "/bin/false")
    target = resolve_test_target("", tmp_path)
    with pytest.raises(AdapterInvocationError):
        await run_pytest(target, artifact_dir=tmp_path, timeout=30.0)
