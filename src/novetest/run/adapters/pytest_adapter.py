"""pytest Native Engine adapter.

Invokes ``python -m pytest`` against a workspace, capturing the
``pytest-json-report`` JSON file plus stdout/stderr logs. Surface for
`run/engine.execute`; not registered through a generic registry yet
because Phase 1 only ships this one adapter.

Foundations §6 guarantees: child gets ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1``
so the dev venv's plugins do not leak in. The pytest-json-report plugin is
loaded explicitly with ``-p pytest_jsonreport``. ``cwd`` is required and
must be the fixture / target workspace root.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


PYTEST_REPORT_FILENAME = "pytest-report.json"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"


async def run_pytest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
) -> NativeResult:
    """Run pytest against ``test_target`` and return the parsed Native Result.

    ``artifact_dir`` is the per-run directory under
    ``.novetest/run/artifacts/run_<ulid>/`` where ``native/`` is created;
    in tests, pass a ``tmp_path``-rooted directory.
    """

    native_dir = artifact_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    report_path = native_dir / PYTEST_REPORT_FILENAME
    stdout_path = native_dir / STDOUT_LOG_FILENAME
    stderr_path = native_dir / STDERR_LOG_FILENAME

    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytest_jsonreport",
        "--json-report",
        f"--json-report-file={report_path}",
        "-q",
    ]
    if test_target.target_expression:
        argv.append(test_target.target_expression)

    env = _build_child_env()
    started_ms = int(time.time() * 1000)
    result = await run_subprocess(
        argv,
        cwd=test_target.workspace_path,
        env=env,
        timeout=timeout,
    )
    completed_ms = int(time.time() * 1000)

    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"pytest exceeded {timeout}s timeout",
            kind="timed-out",
        )

    # pytest exit codes: 0 ok, 1 tests failed (report still valid), 2 usage,
    # 3 internal, 4 usage (deprecated), 5 no tests collected.
    if not report_path.exists():
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        if "No module named" in stderr_text and "pytest_jsonreport" in stderr_text:
            raise AdapterInvocationError(
                "pytest-json-report plugin is not importable from the resolved "
                "interpreter; install with: pip install pytest-json-report",
                kind="missing-plugin",
                install_hint="pip install pytest-json-report",
            )
        if "No module named pytest" in stderr_text:
            raise AdapterInvocationError(
                "pytest is not importable from the resolved interpreter; "
                "install with: pip install pytest",
                kind="missing-engine",
                install_hint="pip install pytest",
            )
        raise AdapterInvocationError(
            f"pytest exited {result.returncode} without producing a JSON report; "
            f"stderr tail: {stderr_text[-400:]}",
            kind="unparseable-output",
        )

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterInvocationError(
            f"pytest JSON report at {report_path} is not valid JSON: {exc}",
            kind="unparseable-output",
        ) from exc

    if not isinstance(payload, dict):
        raise AdapterInvocationError(
            "pytest JSON report root must be an object",
            kind="unparseable-output",
        )

    engine_version = _read_pytest_version(test_target.workspace_path)

    return NativeResult(
        engine_name="pytest",
        payload=payload,
        artifact_paths={
            "pytest_json_report": report_path,
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
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    return env


def _read_pytest_version(workspace: Path) -> str | None:
    """Best-effort version read from the *parent* interpreter import cache.

    A subprocess probe would double the cost of a typical Phase 1 run. The
    only correctness contract is "if pytest is importable here, report its
    version; otherwise None." Falls back to ``None`` silently rather than
    propagating import errors out of the adapter.
    """

    del workspace  # version probe is interpreter-scoped, not workspace-scoped
    try:
        import pytest
    except ImportError:
        return None
    version = getattr(pytest, "__version__", None)
    return str(version) if version is not None else None
