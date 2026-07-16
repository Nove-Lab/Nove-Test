"""Shared subprocess + failure-log machinery for the six Native adapters.

Single source for the four mechanics that were copy-pasted (and had begun
to drift) across ``pytest`` / ``jest`` / ``gotest`` / ``cargo`` / ``junit``
/ ``dotnet`` adapters. Each adapter keeps its own argv construction and
payload parsing — only the shared, drift-prone plumbing lives here:

- ``prepare_artifact_dirs`` — resolve ``artifact_dir`` and create its
  ``native/`` subdir (the ``artifact_dir.resolve()`` + ``native_dir.mkdir``
  boilerplate every adapter opened with; RUN-23).
- ``run_and_capture`` — the timed ``run_subprocess`` spawn + stdout/stderr
  artifact write + the ONE standard ``AdapterInvocationError(kind="timed-out")``
  raise (RUN-23). Pins the timeout data contract in a single place so a
  future change to the timed-out envelope shape touches one site, not six.
- ``safe_failure_log_name`` — the single failure-log-basename sanitizer,
  replacing four private ``_safe_failure_log_name`` copies whose escape
  charsets had diverged to 3 / 3 / 11 / 16 characters (RUN-06). The default
  charset ALWAYS covers the Windows-reserved set ``<>:"/\\|?*`` plus space
  and tab; each engine adds only its own extras via ``extra_chars``.
- ``write_failure_log`` — assemble-content-then-write helper that (a) writes
  the POSIX **relative** path into ``failure_logs`` via ``.as_posix()``
  (RUN-04 — the four sites used ``str(...)``, leaking Windows backslashes
  into the persisted ``failure_reference`` that
  ``localization/failure_proximity.py`` re-reads), and (b) applies the
  unified **skip-if-empty** rule (RUN-17): an empty assembled log writes
  and registers nothing, so ``failure_reference`` present ⇒ the referenced
  log has content.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

from novetest.run.errors import AdapterInvocationError
from novetest.utils.asyncio_subprocess import SubprocessResult, run_subprocess


NATIVE_DIR_NAME: Final[str] = "native"

# The failure-log-basename escape charset always covers the Windows-reserved
# characters ``< > : " / \ | ? *`` plus whitespace (space / tab). ``cargo`` and
# ``gotest`` previously escaped only ``/ : \`` — writing an exotic parametrized
# test name to disk on Windows could hit ``OSError`` on the un-escaped reserved
# characters. Engines add their own extras (``#``, brackets, ``=`` …) via
# ``extra_chars``; the union is the single sanitizer contract.
_RESERVED_AND_WHITESPACE_CHARS: Final[frozenset[str]] = frozenset(
    '<>:"/\\|?*'
) | frozenset({" ", "\t"})


def prepare_artifact_dirs(artifact_dir: Path) -> tuple[Path, Path]:
    """Resolve ``artifact_dir`` and create its ``native/`` subdirectory.

    Returns ``(artifact_dir, native_dir)``. The resolve hardens against a
    future caller passing a relative ``artifact_dir``: production callers
    (the orchestration layer) build absolute paths under
    ``.novetest/run/artifacts/run_<ulid>/``, but the entry-point contract
    is path-shape-agnostic and downstream code composes
    ``artifact_dir / "native"`` etc. without re-resolving. A relative input
    would silently write artifacts under whatever cwd ``run_subprocess``
    inherits — invisible at the unit boundary, painful to debug. Idempotent
    on absolute paths (no-op + symlink follow).
    """

    artifact_dir = artifact_dir.resolve()
    native_dir = artifact_dir / NATIVE_DIR_NAME
    native_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir, native_dir


async def run_and_capture(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float | None,
    stdout_path: Path,
    stderr_path: Path,
    timeout_label: str,
) -> tuple[SubprocessResult, int, int]:
    """Spawn ``argv``, persist stdout/stderr, and pin the timed-out contract.

    The 5-step skeleton every adapter repeats (RUN-23): capture
    ``started_ms``, ``run_subprocess``, capture ``completed_ms``, write the
    stdout/stderr artifacts, then — on a wall-clock timeout — raise the ONE
    canonical ``AdapterInvocationError(kind="timed-out")``. The partial
    output is persisted BEFORE the timeout raise (matching every adapter's
    prior order) so a timed-out run still leaves diagnosable logs.

    Returns ``(result, started_ms, completed_ms)`` on the non-timeout path.
    ``timeout_label`` names the engine in the timeout message
    (e.g. ``"pytest"``, ``"go test"``, ``"mvn test"``). A
    ``FileNotFoundError`` from ``run_subprocess`` (a launcher TOCTOU race)
    propagates unchanged so the adapter can map it to its own typed
    ``missing-binary`` error.
    """

    started_ms = int(time.time() * 1000)
    result = await run_subprocess(argv, cwd=cwd, env=env, timeout=timeout)
    completed_ms = int(time.time() * 1000)

    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"{timeout_label} exceeded {timeout}s timeout",
            kind="timed-out",
        )
    return result, started_ms, completed_ms


def safe_failure_log_name(name: str, extra_chars: Iterable[str] = ()) -> str:
    """Convert a test node id into a filesystem-safe log basename (RUN-06).

    Replaces every Windows-reserved / whitespace character (``< > : " / \\
    | ? *``, space, tab) plus any engine-specific ``extra_chars`` with
    ``_``. Replacement is order-independent (the target ``_`` is never
    itself a source character), so the result is deterministic regardless
    of set-iteration order. A double-underscore in the output marks where a
    ``::`` / ``#`` separator lived; consumers needing a round-trip store the
    unescaped node id separately (the ``failure_logs`` mapping key does).
    """

    unsafe = _RESERVED_AND_WHITESPACE_CHARS | frozenset(extra_chars)
    out = name
    for bad in unsafe:
        out = out.replace(bad, "_")
    return out


def write_failure_log(
    *,
    node_id: str,
    content: str,
    failures_dir: Path,
    artifact_dir: Path,
    failure_logs: dict[str, str],
    extra_chars: Iterable[str] = (),
) -> None:
    """Write ``content`` to a per-test failure log and register its path.

    Applies the unified skip-if-empty rule (RUN-17): an empty ``content``
    writes and registers NOTHING, so a present ``failure_reference`` always
    points at a log with content (consumers fall back to their inline
    detail when it is absent). On a non-empty ``content`` the log lands at
    ``<failures_dir>/<safe-name>.log`` and its path RELATIVE to
    ``artifact_dir`` is registered under ``failure_logs[node_id]`` as a
    POSIX string (RUN-04: ``.as_posix()``, never a backslash-bearing
    ``str(PurePath)`` that would corrupt the persisted reference on
    Windows).
    """

    if not content:
        return
    safe_name = safe_failure_log_name(node_id, extra_chars)
    failures_dir.mkdir(parents=True, exist_ok=True)
    failure_path = failures_dir / f"{safe_name}.log"
    failure_path.write_text(content, encoding="utf-8")
    failure_logs[node_id] = failure_path.relative_to(artifact_dir).as_posix()


__all__ = [
    "NATIVE_DIR_NAME",
    "prepare_artifact_dirs",
    "run_and_capture",
    "safe_failure_log_name",
    "write_failure_log",
]
