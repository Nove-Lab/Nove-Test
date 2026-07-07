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
- ``collect_coverage=True`` adds ``--coverage --coverageReporters=json``
  plus ``--coverageDirectory=<...>/native/coverage`` and registers the
  resulting Istanbul ``coverage-final.json`` under the ``coverage_json``
  artifact key — the SAME key the pytest adapter uses, so the Coverage
  engine looks it up uniformly and dispatches format-handling on
  ``engine_name``.

Unlike pytest, jest has **no plugin-autoload concept**: there is no
``JEST_DISABLE_PLUGIN_AUTOLOAD`` equivalent. Workspace-local
``jest.config.js`` is honored as the user wrote it. This is intentional;
jest does not have the system-wide registry that motivated pytest's
isolation flag.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


JEST_REPORT_FILENAME = "jest-results.json"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
COVERAGE_DIR_NAME = "coverage"
# jest's `json` coverage reporter always names its output `coverage-final.json`.
COVERAGE_FINAL_FILENAME = "coverage-final.json"


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

    When ``collect_coverage`` is True, jest is invoked with
    ``--coverage --coverageReporters=json`` and
    ``--coverageDirectory=<artifact_dir>/native/coverage`` so Istanbul's
    ``coverage-final.json`` lands under the per-run artifact directory
    (never the workspace's default ``<rootDir>/coverage``). That file is
    registered in ``artifact_paths`` under ``coverage_json``. Defaults to
    False so non-coverage callers see byte-identical behavior.
    """

    # Defensive resolve: hardens against future callers passing a relative
    # ``artifact_dir``. See pytest_adapter.py for the full rationale —
    # the contract here is path-shape-agnostic but downstream construction
    # (``native_dir = artifact_dir / "native"`` and below) does not
    # re-resolve. Idempotent on absolute paths.
    artifact_dir = artifact_dir.resolve()

    native_dir = artifact_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    report_path = native_dir / JEST_REPORT_FILENAME
    stdout_path = native_dir / STDOUT_LOG_FILENAME
    stderr_path = native_dir / STDERR_LOG_FILENAME
    coverage_dir = native_dir / COVERAGE_DIR_NAME
    coverage_json_path = coverage_dir / COVERAGE_FINAL_FILENAME

    # Resolve `npx` up front. `shutil.which` honours Windows `PATHEXT`, so
    # it returns `npx.cmd` there — the SAME resolution the engine-readiness
    # probe (`readiness._assess_jest_readiness`) uses, so the readiness
    # guard and this exec can never disagree. An absent `npx` is reported
    # as a typed error here rather than letting a downstream
    # `FileNotFoundError` surface a less specific message.
    npx_path = shutil.which("npx")
    if npx_path is None:
        raise AdapterInvocationError(
            "`npx` not found on PATH; install Node.js >=18 and ensure "
            "`node`/`npx` are on PATH",
            kind="missing-binary",
            install_hint="install Node.js >=18 and ensure `node`/`npx` are on PATH",
        )

    # `npx jest` resolves to the workspace-local jest install when
    # `node_modules/.bin/jest` is present (which is what readiness gates on).
    # `--ci` disables watch + interactive UI; `--testLocationInResults`
    # is mandatory for mapping nodeids → file:line per engine-adapters.md §2;
    # `--watchman=false` makes Windows behavior predictable.
    argv: list[str] = [
        *_npx_launcher(npx_path, windows=os.name == "nt"),
        "jest",
        "--ci",
        "--json",
        "--testLocationInResults",
        f"--outputFile={report_path}",
        "--reporters=default",
        "--watchman=false",
    ]
    if collect_coverage:
        # `json` is the only reporter that produces `coverage-final.json`
        # (Istanbul's raw format). `--coverageDirectory` redirects the
        # report out of the workspace's default `<rootDir>/coverage` into
        # the per-run artifact dir so the SuT tree is never written to.
        argv.extend(
            [
                "--coverage",
                "--coverageReporters=json",
                f"--coverageDirectory={coverage_dir}",
            ]
        )
    if test_target.target_expression:
        # RUN-22: the `--` separator pins the target as a positional test
        # path pattern. Empirically verified on jest 29.7.0 / Node 22
        # (2026-07-07): `jest -- <pattern>` selects the same tests as the
        # bare positional, and a dash-leading value after `--` is treated
        # as a pattern (loud "No tests found") instead of being consumed
        # as a jest flag (`jest --listTests` lists files; `jest --
        # --listTests` does not). jest is the only bare-argv engine where
        # `--` achieves this — pytest/go/cargo use rejection instead (see
        # adapters/_target_guard.py).
        argv.extend(["--", test_target.target_expression])

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
        # `npx` was resolved above, so this is a narrow fallback: a TOCTOU
        # race (npx removed between resolution and exec) or, on Windows, a
        # missing `cmd.exe`. Still surface a typed error rather than a raw
        # Python traceback.
        raise AdapterInvocationError(
            "the jest launcher could not be executed; ensure Node.js >=18 "
            "is installed and `node`/`npx` are on PATH",
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

    if collect_coverage and not coverage_json_path.exists():
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise AdapterInvocationError(
            f"jest --coverage did not write {coverage_json_path}; "
            f"stderr tail: {stderr_text[-400:]}",
            kind="unparseable-output",
        )

    engine_version = _read_jest_version(test_target.workspace_path)

    artifact_paths: dict[str, Path] = {
        "jest_json_report": report_path,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    if collect_coverage:
        # Absolute Path at the adapter layer; Memory rewrites it to a
        # Project-Store-relative string. Only registered when coverage was
        # requested AND the file actually landed (asserted just above).
        artifact_paths["coverage_json"] = coverage_json_path

    return NativeResult(
        engine_name="jest",
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=engine_version,
    )


def _npx_launcher(npx_path: str, *, windows: bool) -> list[str]:
    """Build the launcher prefix that invokes jest through ``npx``.

    POSIX: ``npx`` (resolved to its absolute path by ``shutil.which``) is
    exec'd directly — it is a normal script with a shebang.

    Windows: ``npx`` is ``npx.cmd``, a *batch* shim. Windows
    ``CreateProcess`` — which ``asyncio.create_subprocess_exec`` calls —
    cannot execute ``.cmd``/``.bat`` files; it only runs real PE binaries
    (and appends only ``.exe`` when resolving a bare name, which is exactly
    why a bare ``npx`` fails there). So the shim must run through the
    command interpreter: ``cmd.exe /c npx ...``.

    The bare name ``npx`` (not ``npx_path``) is handed to ``cmd`` on
    purpose: ``cmd`` applies ``PATHEXT`` to locate ``npx.cmd`` — the exact
    resolution ``shutil.which`` already confirmed — and a *bare* first
    token sidesteps ``cmd /c``'s leading-quote-stripping rule, which would
    otherwise corrupt the command line when later arguments (e.g. a
    ``--outputFile=`` path) contain spaces and get quoted. ``cmd`` itself
    resolves because ``CreateProcess`` does append ``.exe`` to a bare name.
    """

    if windows:
        return ["cmd", "/c", "npx"]
    return [npx_path]


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
    "COVERAGE_DIR_NAME",
    "COVERAGE_FINAL_FILENAME",
    "JEST_REPORT_FILENAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "run_jest",
]
