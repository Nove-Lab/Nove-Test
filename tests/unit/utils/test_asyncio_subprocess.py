"""Unit tests for `novetest.utils.asyncio_subprocess`."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import sys
import textwrap
import time
from pathlib import Path

import pytest

from novetest.utils.asyncio_subprocess import run_subprocess

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX process-group / setsid semantics",
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _await_pid_dead(pid: int, timeout: float) -> bool:
    """Poll ``pid`` until it is gone (a killed grandchild is a zombie briefly)."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        await asyncio.sleep(0.02)
    return not _pid_alive(pid)


# --- existing behaviour (regression pins) ------------------------------------


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


# --- W1/S3 hardening ---------------------------------------------------------


async def test_happy_path_result_fields_unchanged(tmp_path: Path) -> None:
    """Non-timeout, under-cap run: original fields intact, truncation flags off."""

    result = await run_subprocess(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.exit(3)",
        ],
        cwd=tmp_path,
        timeout=10.0,
    )
    assert result.returncode == 3
    assert result.stdout == b"out"
    assert result.stderr == b"err"
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


async def test_capture_cap_truncates_stdout_and_flags(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100_000)"],
        cwd=tmp_path,
        timeout=10.0,
        capture_limit=1024,
    )
    assert result.returncode == 0
    assert len(result.stdout) == 1024
    assert result.stdout == b"x" * 1024
    assert result.stdout_truncated is True
    assert result.stderr_truncated is False


async def test_capture_cap_truncates_stderr_and_flags(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import sys; sys.stderr.write('z' * 100_000)"],
        cwd=tmp_path,
        timeout=10.0,
        capture_limit=2048,
    )
    assert len(result.stderr) == 2048
    assert result.stderr == b"z" * 2048
    assert result.stderr_truncated is True
    assert result.stdout_truncated is False


async def test_capture_under_cap_is_intact(tmp_path: Path) -> None:
    result = await run_subprocess(
        [sys.executable, "-c", "import sys; sys.stdout.write('y' * 100)"],
        cwd=tmp_path,
        timeout=10.0,
        capture_limit=1024,
    )
    assert result.stdout == b"y" * 100
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


@_POSIX_ONLY
async def test_timeout_kills_process_tree(tmp_path: Path) -> None:
    """A same-group grandchild is dead after a timeout tree kill (RUN-15/MOD-01).

    The grandchild's stdio is redirected to /dev/null so it does not hold our
    pipe write-end — this isolates the orphan-kill behaviour from pipe drain.
    """

    pidfile = tmp_path / "grandchild.pid"
    quoted = shlex.quote(str(pidfile))
    # Non-interactive `sh -c` has job control OFF, so the backgrounded sleep
    # stays in the shell's process group and is reachable via killpg.
    script = f"sleep 30 >/dev/null 2>&1 & echo $! > {quoted}; wait"

    result = await run_subprocess(
        ["sh", "-c", script],
        cwd=tmp_path,
        timeout=0.3,
        kill_grace=0.3,
        drain_grace=0.5,
    )
    assert result.timed_out is True

    gpid = int(pidfile.read_text().strip())
    try:
        assert await _await_pid_dead(gpid, timeout=2.0), "grandchild survived the tree kill"
    finally:
        try:
            os.kill(gpid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@_POSIX_ONLY
async def test_pipe_drain_grace_bounds_return(tmp_path: Path) -> None:
    """A detached grandchild holding the pipe cannot hang the call (MOD-01 hang).

    The grandchild ``setsid``s out of the group (so the tree kill misses it) and
    keeps the inherited stdout pipe write-end open, which would block a naive
    EOF drain forever. The bounded drain must still return ``timed_out=True``;
    the outer ``wait_for`` makes an unbounded drain surface as a test failure.
    """

    pidfile = tmp_path / "detached.pid"
    child_code = textwrap.dedent(
        f"""
        import os, time
        if os.fork() == 0:
            os.setsid()  # escape the parent's process group -> survives killpg
            with open({str(pidfile)!r}, "w") as fh:
                fh.write(str(os.getpid()))
            time.sleep(30)  # keep fd 1 (our pipe write-end) open
        else:
            time.sleep(30)
        """
    )

    result = await asyncio.wait_for(
        run_subprocess(
            [sys.executable, "-c", child_code],
            cwd=tmp_path,
            timeout=0.3,
            kill_grace=0.3,
            drain_grace=0.4,
        ),
        timeout=6.0,
    )
    assert result.timed_out is True

    # Kill the detached grandchild so the abandoned pipe finally reaches EOF and
    # its transport closes on this loop (avoids a __del__-on-closed-loop warning).
    gpid = int(pidfile.read_text().strip())
    try:
        os.kill(gpid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await asyncio.sleep(0.1)
