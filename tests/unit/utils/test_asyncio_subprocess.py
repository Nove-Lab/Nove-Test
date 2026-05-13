"""Unit tests for `novetest.utils.asyncio_subprocess`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from novetest.utils.asyncio_subprocess import run_subprocess


async def test_captures_stdout(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "print('hello')"],
        cwd=tmp_path,
        timeout=10.0,
    )
    assert result.returncode == 0
    assert result.stdout.decode().strip() == "hello"
    assert result.stderr == b""
    assert result.timed_out is False


async def test_captures_stderr_and_returncode(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(7)"],
        cwd=tmp_path,
        timeout=10.0,
    )
    assert result.returncode == 7
    assert "boom" in result.stderr.decode()


async def test_timeout_marks_timed_out(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        timeout=0.2,
    )
    assert result.timed_out is True


async def test_env_replaces_when_provided(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import os; print(os.environ.get('NOVE_TEST_ENV', 'unset'))"],
        cwd=tmp_path,
        env={"NOVE_TEST_ENV": "yes", "PATH": "/usr/bin"},
        timeout=10.0,
    )
    assert result.stdout.decode().strip() == "yes"


async def test_empty_argv_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await run_subprocess([], cwd=tmp_path)
