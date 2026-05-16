"""jest Native Engine adapter.

Invokes ``npx jest`` against a workspace, capturing the canonical
``--json --outputFile=<...>`` results file plus stdout/stderr logs. Surface
for `run/engine.execute`; registered through `engine.execute_with_engine_context`'s
explicit branch on ``engine_name == "jest"`` (no generic registry yet —
the second adapter does not motivate the abstraction).

Foundations parity with pytest_adapter:

- ``cwd`` is required and must be the workspace root containing
  ``package.json``.
- All native artifacts (the JSON results, stdout.log, stderr.log) land
  under ``<artifact_dir>/native/``. The orchestration layer rewrites
  those absolute paths to Project-Store-relative strings before
  persisting the Run Record.
- ``collect_coverage`` is **accepted but unwired** in this slice. The
  Coverage team's Istanbul-JSON parser slice has not landed; until it
  does, requesting coverage from the jest adapter is a no-op (no flags
  added, no Istanbul artifact emitted). Documented in the kwarg.

Unlike pytest, jest has **no plugin-autoload concept**: there is no
``JEST_DISABLE_PLUGIN_AUTOLOAD`` equivalent. Workspace-local
``jest.config.js`` is honored as the user wrote it. This is intentional;
jest does not have the system-wide registry that motivated pytest's
isolation flag.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


JEST_REPORT_FILENAME = "jest-results.json"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"


async def run_jest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run jest against ``test_target`` and return the parsed Native Result.

    ``artifact_dir`` is the per-run directory under
    ``.novetest/run/artifacts/run_<ulid>/`` where ``native/`` is created;
    in tests, pass a ``tmp_path``-rooted directory.

    ``collect_coverage`` is accepted for API parity with the pytest
    adapter but **is a no-op in this slice**. Once the Coverage team's
    Istanbul-JSON parser lands, this kwarg will gate
    ``--coverage --coverageReporters=json --coverageReporters=lcov`` per
    `design/implementation-plan/engine-adapters.md` §2.
    """

    del collect_coverage  # intentionally unwired; see docstring

    native_dir = artifact_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    report_path = native_dir / JEST_REPORT_FILENAME
    stdout_path = native_dir / STDOUT_LOG_FILENAME
    stderr_path = native_dir / STDERR_LOG_FILENAME

    # `npx jest` resolves to the workspace-local jest install when
    # `node_modules/.bin/jest` is present (which is what readiness gates on).
    # `--ci` disables watch + interactive UI; `--testLocationInResults`
    # is mandatory for mapping nodeids → file:line per engine-adapters.md §2;
    # `--watchman=false` makes Windows behavior predictable.
    argv: list[str] = [
        "npx",
        "jest",
        "--ci",
        "--json",
        "--testLocationInResults",
        f"--outputFile={report_path}",
        "--reporters=default",
        "--watchman=false",
    ]
    if test_target.target_expression:
        argv.append(test_target.target_expression)

    env = _build_child_env()
    started_ms = int(time.time() * 1000)
    try:
        result = await run_subprocess(
            argv,
            cwd=test_target.workspace_path,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        # `npx` is not on PATH (Node.js not installed). Surface the
        # actionable hint without bothering the user with a Python
        # traceback. Mirrors pytest_adapter's "missing-engine" semantics
        # but uses "missing-binary" because the missing thing is the
        # *binary on PATH*, not a Python module.
        raise AdapterInvocationError(
            "`npx` not found on PATH; install Node.js >=18 and ensure "
            "`node`/`npx` are on PATH",
            kind="missing-binary",
            install_hint="install Node.js >=18 and ensure `node`/`npx` are on PATH",
        ) from exc
    completed_ms = int(time.time() * 1000)

    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"jest exceeded {timeout}s timeout",
            kind="timed-out",
        )

    # jest exit codes: 0 = all passed, 1 = some tests failed (report still
    # valid), >=2 = config / no-tests-found / runtime error. The report file
    # is only written when jest got far enough to execute; usage / not-found
    # errors abort before the file lands.
    if not report_path.exists():
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        if _stderr_indicates_missing_jest(stderr_text):
            raise AdapterInvocationError(
                "jest is not importable from this workspace; install with: "
                "npm install --save-dev jest",
                kind="missing-plugin",
                install_hint="npm install --save-dev jest",
            )
        raise AdapterInvocationError(
            f"jest exited {result.returncode} without producing a JSON report; "
            f"stderr tail: {stderr_text[-400:]}",
            kind="unparseable-output",
        )

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterInvocationError(
            f"jest JSON report at {report_path} is not valid JSON: {exc}",
            kind="unparseable-output",
        ) from exc

    if not isinstance(payload, dict):
        raise AdapterInvocationError(
            "jest JSON report root must be an object",
            kind="unparseable-output",
        )

    engine_version = _read_jest_version(test_target.workspace_path)

    return NativeResult(
        engine_name="jest",
        payload=payload,
        artifact_paths={
            "jest_json_report": report_path,
            "stdout": stdout_path,
            "stderr": stderr_path,
        },
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=engine_version,
    )


def _build_child_env() -> dict[str, str]:
    env = os.environ.copy()
    # Match the surrounding `--ci` flag's intent at the env layer too: avoid
    # ANSI colors leaking into captured stdout/stderr, signal CI to any tools
    # that inspect env vars, and keep encoding deterministic.
    env["CI"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    return env


def _stderr_indicates_missing_jest(stderr_text: str) -> bool:
    """Heuristically detect `npx`'s 'jest not found in workspace' output.

    `npx` emits one of several messages when the requested binary is not
    resolvable from local ``node_modules`` (and `--no-install` semantics
    take effect): "could not determine executable to run", "npm ERR! 404",
    "command not found: jest", etc. We match on the union of stable
    fragments; false positives merely degrade `missing-plugin` to
    `unparseable-output`, which is still actionable.
    """

    needles = (
        "could not determine executable to run",
        "command not found",
        "Cannot find module",
        "npm ERR! 404",
        "no such file or directory",
    )
    return any(n in stderr_text for n in needles)


def _read_jest_version(workspace: Path) -> str | None:
    """Best-effort version read from the workspace's local jest install.

    Reads ``node_modules/jest/package.json``'s ``version`` field — one
    filesystem hit, no subprocess. Returns ``None`` silently on any
    read/parse failure: version is informational metadata, never
    load-bearing for the Run Record's correctness.
    """

    candidate = workspace / "node_modules" / "jest" / "package.json"
    if not candidate.is_file():
        return None
    try:
        meta = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = meta.get("version") if isinstance(meta, dict) else None
    return str(version) if isinstance(version, str) else None


__all__ = [
    "JEST_REPORT_FILENAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "run_jest",
]
