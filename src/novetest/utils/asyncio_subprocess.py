"""Canonical async subprocess invocation helper.

Implements the concurrent-pipe-drain pattern from
`design/implementation-plan/foundations.md` §3 so that Native Engine adapters
do not deadlock on full stdout/stderr pipes (a documented Windows
``subprocess.Popen`` failure mode). Every native adapter and readiness probe
routes through this single helper.

Subprocess lifecycle hardening (W1/S3, findings RUN-15/MOD-01, RUN-27/MOD-02):

* **Tree kill on timeout.** POSIX spawns the child in its own session
  (``start_new_session=True``) so the whole process *group* — the test binary,
  forked JVM/testhost/node worker, etc. — can be signalled: SIGTERM first, a
  bounded grace, then SIGKILL via ``os.killpg``. Windows terminates the tree
  best-effort with ``taskkill /T /F`` (untested on this Linux host; exercised by
  the CI matrix).
* **Bounded pipe drain.** The final stdout/stderr collection can never block
  forever: a grandchild that inherited (and kept open) our pipe write-end while
  escaping the group kill would otherwise hold ``read()`` at a missing EOF. The
  drain is bounded by ``drain_grace``; whatever was captured before the grace
  expired is preserved.
* **Capture cap.** Each stream retains at most ``capture_limit`` bytes; overflow
  is drained-and-discarded (keeping the child from blocking on a full pipe and
  the orchestrator from OOM) and flagged via ``stdout_truncated`` /
  ``stderr_truncated``.

On the non-timeout happy path with output under the cap, the four original
result fields are byte-identical to the pre-hardening behaviour.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"

# Per-stream retention cap. The envelope only ever surfaces a short stderr tail,
# so full retention of a runaway stream is pure OOM risk.
_DEFAULT_CAPTURE_LIMIT = 16 * 1024 * 1024  # 16 MiB
# Grace between the polite SIGTERM and the forceful SIGKILL of the process group.
_DEFAULT_KILL_GRACE = 5.0
# Grace for the final pipe drain to reach EOF after the child has been waited on.
_DEFAULT_DRAIN_GRACE = 5.0

_READ_CHUNK = 64 * 1024


@dataclass(slots=True, frozen=True)
class SubprocessResult:
    """Captured outcome of a finished subprocess."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class _StreamDrainer:
    """Reads a stream to EOF, retaining at most ``limit`` bytes.

    Retention is capped but draining continues past the cap so the child never
    blocks on a full pipe; the surplus is discarded and ``truncated`` is set.
    The buffer lives on the instance (not the task's return value) so a partial
    capture survives task cancellation when the drain is abandoned on grace
    expiry.
    """

    __slots__ = ("_stream", "_limit", "buffer", "truncated")

    def __init__(self, stream: asyncio.StreamReader, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self.buffer = bytearray()
        self.truncated = False

    async def run(self) -> None:
        while True:
            chunk = await self._stream.read(_READ_CHUNK)
            if not chunk:
                return
            room = self._limit - len(self.buffer)
            if room <= 0:
                self.truncated = True
            elif len(chunk) <= room:
                self.buffer.extend(chunk)
            else:
                self.buffer.extend(chunk[:room])
                self.truncated = True


def _killpg(pid: int, sig: int) -> None:
    """Signal the process group led by ``pid`` (POSIX), ignoring a gone group."""

    # POSIX-only; process-group signals do not exist on Windows (which uses
    # taskkill /T). The direct sys.platform check — not the _IS_WINDOWS alias —
    # lets mypy mark the os.killpg call below unreachable under --platform win32.
    if sys.platform == "win32":
        return
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


async def _terminate_tree(proc: asyncio.subprocess.Process, *, kill_grace: float) -> None:
    """Kill the child's whole process tree and reap the direct child."""

    if sys.platform == "win32":
        # Best-effort tree kill; untested on this Linux host (CI matrix covers it).
        # Direct sys.platform check (not the _IS_WINDOWS alias) so mypy statically
        # narrows the POSIX tail below — incl. signal.SIGKILL — unreachable under
        # --platform win32.
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            proc.kill()
        else:
            await killer.wait()
        await proc.wait()
        return

    # POSIX: the child leads its own group (start_new_session=True), so its pid
    # is the pgid. SIGKILL is only sent while the child is still unreaped, so pid
    # reuse cannot misfire the group signal.
    _killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=kill_grace)
    except asyncio.TimeoutError:
        _killpg(proc.pid, signal.SIGKILL)
        await proc.wait()


async def _finish_drain(
    stdout_task: asyncio.Task[None],
    stderr_task: asyncio.Task[None],
    *,
    grace: float,
) -> None:
    """Await both drains, bounded by ``grace``; abandon partial reads on expiry."""

    gathered = asyncio.gather(stdout_task, stderr_task)
    try:
        await asyncio.wait_for(gathered, timeout=grace)
    except asyncio.TimeoutError:
        stdout_task.cancel()
        stderr_task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)


async def run_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    capture_limit: int = _DEFAULT_CAPTURE_LIMIT,
    kill_grace: float = _DEFAULT_KILL_GRACE,
    drain_grace: float = _DEFAULT_DRAIN_GRACE,
) -> SubprocessResult:
    """Run ``argv`` with concurrent, byte-capped stdout/stderr capture.

    ``cwd`` is required (foundations §3: never inherit the CLI's CWD).
    ``env`` replaces the child environment in full when provided; pass
    ``os.environ | overrides`` to inherit-with-overrides at the call site.

    On timeout the child's whole process tree is terminated and
    ``timed_out=True`` is returned; output drained before the kill is preserved.
    Each stream retains at most ``capture_limit`` bytes, setting
    ``stdout_truncated`` / ``stderr_truncated`` on overflow. The final drain is
    bounded by ``drain_grace`` so a surviving pipe-holding grandchild cannot
    block the call forever.
    """

    if not argv:
        raise ValueError("argv must contain at least one element")

    # POSIX-only: put the child in its own session so its whole process group can
    # be signalled on timeout. Ignored on Windows (which uses taskkill /T).
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.fspath(cwd),
        env=dict(env) if env is not None else None,
        start_new_session=not _IS_WINDOWS,
    )

    assert proc.stdout is not None and proc.stderr is not None
    stdout_drainer = _StreamDrainer(proc.stdout, capture_limit)
    stderr_drainer = _StreamDrainer(proc.stderr, capture_limit)
    stdout_task = asyncio.create_task(stdout_drainer.run())
    stderr_task = asyncio.create_task(stderr_drainer.run())

    timed_out = False
    try:
        if timeout is None:
            returncode = await proc.wait()
        else:
            returncode = await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        await _terminate_tree(proc, kill_grace=kill_grace)
        returncode = proc.returncode if proc.returncode is not None else -1

    await _finish_drain(stdout_task, stderr_task, grace=drain_grace)
    return SubprocessResult(
        returncode=returncode,
        stdout=bytes(stdout_drainer.buffer),
        stderr=bytes(stderr_drainer.buffer),
        timed_out=timed_out,
        stdout_truncated=stdout_drainer.truncated,
        stderr_truncated=stderr_drainer.truncated,
    )
