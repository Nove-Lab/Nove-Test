"""Canonical async subprocess invocation helper.

Implements the concurrent-pipe-drain pattern from
`design/implementation-plan/foundations.md` §3 so that Native Engine adapters
do not deadlock on full stdout/stderr pipes (a documented Windows
``subprocess.Popen`` failure mode). The helper is intentionally narrow at
Phase 0 / 1: capture mode with optional timeout. Streaming and signal-group
escalation arrive when a sub-product needs them.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class SubprocessResult:
    """Captured outcome of a finished subprocess."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool


async def run_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Run ``argv`` with concurrent stdout/stderr capture.

    ``cwd`` is required (foundations §3: never inherit the CLI's CWD).
    ``env`` replaces the child environment in full when provided; pass
    ``os.environ | overrides`` to inherit-with-overrides at the call site.
    On timeout, the child is terminated and ``timed_out=True`` is returned;
    any output drained before the kill is preserved.
    """

    if not argv:
        raise ValueError("argv must contain at least one element")
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.fspath(cwd),
        env=dict(env) if env is not None else None,
    )

    assert proc.stdout is not None and proc.stderr is not None
    stdout_task = asyncio.create_task(proc.stdout.read())
    stderr_task = asyncio.create_task(proc.stderr.read())

    timed_out = False
    try:
        if timeout is None:
            returncode = await proc.wait()
        else:
            returncode = await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        returncode = await proc.wait()

    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    return SubprocessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )
