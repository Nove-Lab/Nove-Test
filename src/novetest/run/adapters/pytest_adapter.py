"""pytest Native Engine adapter.

Invokes ``python -m pytest`` against a workspace, capturing the
``pytest-json-report`` JSON file plus stdout/stderr logs. Surface for
`run/engine.execute`; not registered through a generic registry yet
because Phase 1 only ships this one adapter.

Foundations §6 guarantees: child gets ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1``
so the dev venv's plugins do not leak in. The pytest-json-report plugin
is loaded explicitly with ``-p pytest_jsonreport``. When
``collect_coverage`` is requested, ``pytest_cov`` is loaded the same way
and a per-run ``.coveragerc`` is generated under ``artifact_dir`` so the
workspace's own coverage config is never modified. ``cwd`` is required
and must be the fixture / target workspace root.
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
COVERAGE_JSON_FILENAME = "coverage.json"
COVERAGE_XML_FILENAME = "coverage.xml"
COVERAGE_RC_FILENAME = ".coveragerc"


async def run_pytest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run pytest against ``test_target`` and return the parsed Native Result.

    ``artifact_dir`` is the per-run directory under
    ``.novetest/run/artifacts/run_<ulid>/`` where ``native/`` is created;
    in tests, pass a ``tmp_path``-rooted directory.

    When ``collect_coverage`` is True, pytest is invoked with the canonical
    coverage flags (`--cov=.`, `--cov-branch`, `--cov-context=test`,
    `--cov-report=json:<...>/coverage.json`,
    `--cov-report=xml:<...>/coverage.xml`) and a per-run ``.coveragerc``
    (written into ``artifact_dir``) that sets ``[json] show_contexts = True``
    so the JSON report carries the per-line `contexts` map the Coverage
    engine consumes. Defaults to False so Phase 1 callers see no behavior
    change.
    """

    # Defensive resolve: hardens against future callers passing a relative
    # ``artifact_dir``. Production callers (the orchestration layer) build
    # absolute paths under ``.novetest/run/artifacts/run_<ulid>/``, but the
    # entry-point contract is path-shape-agnostic and downstream code
    # composes ``artifact_dir / "native"`` etc. without re-resolving. A
    # relative input would silently write artifacts under whatever cwd
    # ``run_subprocess`` inherits — invisible at the unit boundary, painful
    # to debug. Idempotent on absolute paths (no-op + symlink follow).
    artifact_dir = artifact_dir.resolve()

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

    coverage_json_path: Path | None = None
    coverage_xml_path: Path | None = None
    if collect_coverage:
        coverage_json_path = native_dir / COVERAGE_JSON_FILENAME
        coverage_xml_path = native_dir / COVERAGE_XML_FILENAME
        rc_path = _write_coverage_rc(artifact_dir)
        argv.extend(
            [
                "-p",
                "pytest_cov",
                "--cov=.",
                "--cov-branch",
                "--cov-context=test",
                f"--cov-config={rc_path}",
                f"--cov-report=json:{coverage_json_path}",
                f"--cov-report=xml:{coverage_xml_path}",
            ]
        )

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
        if collect_coverage and "No module named" in stderr_text and "pytest_cov" in stderr_text:
            raise AdapterInvocationError(
                "pytest-cov plugin is not importable from the resolved "
                "interpreter; install with: pip install pytest-cov",
                kind="missing-plugin",
                install_hint="pip install pytest-cov",
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

    if collect_coverage:
        assert coverage_json_path is not None and coverage_xml_path is not None
        if not coverage_json_path.exists():
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            raise AdapterInvocationError(
                f"pytest-cov did not write coverage JSON to {coverage_json_path}; "
                f"stderr tail: {stderr_text[-400:]}",
                kind="unparseable-output",
            )

    engine_version = _read_pytest_version(test_target.workspace_path)

    artifact_paths: dict[str, Path] = {
        "pytest_json_report": report_path,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    if collect_coverage:
        assert coverage_json_path is not None and coverage_xml_path is not None
        artifact_paths["coverage_json"] = coverage_json_path
        artifact_paths["coverage_xml"] = coverage_xml_path

    return NativeResult(
        engine_name="pytest",
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=engine_version,
    )


def _write_coverage_rc(artifact_dir: Path) -> Path:
    """Generate a per-run ``.coveragerc`` under ``artifact_dir``.

    ``show_contexts`` is mandatory: ``--cov-context=test`` controls which
    context name coverage.py records *during* the run, but the per-line
    `contexts` map only lands in `coverage.json` when ``show_contexts``
    is enabled at report time. ``relative_files`` keeps emitted paths
    workspace-relative so Memory / Coverage do not have to strip absolute
    build prefixes. ``data_file`` is pinned under ``artifact_dir`` so
    coverage.py's intermediate SQLite cache never leaks into the SuT's
    workspace (default would land it in cwd).
    """

    rc_path = artifact_dir / COVERAGE_RC_FILENAME
    data_file = artifact_dir / ".coverage"
    rc_path.write_text(
        "[run]\n"
        "relative_files = True\n"
        "branch = True\n"
        f"data_file = {data_file}\n"
        "\n"
        "[json]\n"
        "show_contexts = True\n"
        "pretty_print = True\n",
        encoding="utf-8",
    )
    return rc_path


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
