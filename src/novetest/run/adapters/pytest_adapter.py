"""pytest Native Engine adapter.

Invokes ``python -m pytest`` against a workspace, capturing the
``pytest-json-report`` JSON file plus stdout/stderr logs. Surface for
`run/engine.execute`; not registered through a generic registry yet
because Phase 1 only ships this one adapter.

Foundations §3 child-process contract (RUN-11): the interpreter is
resolved venv-first (``_resolve_pytest_interpreter`` — the SuT's
``.venv`` pytest when present, else ``sys.executable``; never bare
``pytest`` off PATH), and the child env is sanitized on an allow-add
model with deterministic pins (``PYTHONHASHSEED=0`` / ``CI=1`` /
``FORCE_COLOR=0``) and an inherited ``PYTHONPATH`` dropped (RUN-24).
``_resolve_pytest_interpreter`` and ``_query_pytest_version`` are the
single resolution / version surfaces shared with `run/readiness.py`, so
the interpreter readiness declares ready is the interpreter that runs and
the version reported is the one that ran (board rows 25 and 22).

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
from pathlib import Path

from novetest.run.adapters._harness import prepare_artifact_dirs, run_and_capture
from novetest.run.adapters._target_guard import reject_dash_leading_target
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

    # Resolve ``artifact_dir`` + create ``native/`` (shared harness; the
    # resolve hardens against a relative ``artifact_dir`` — rationale in
    # ``_harness.prepare_artifact_dirs``).
    artifact_dir, native_dir = prepare_artifact_dirs(artifact_dir)
    report_path = native_dir / PYTEST_REPORT_FILENAME
    stdout_path = native_dir / STDOUT_LOG_FILENAME
    stderr_path = native_dir / STDERR_LOG_FILENAME

    interpreter = _resolve_pytest_interpreter(test_target.workspace_path)
    argv = [
        interpreter,
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

    # RUN-22 guard: pytest would consume a dash-leading target as a flag.
    # A `--` separator does NOT help — empirically (pytest 9.0.3,
    # 2026-07-07): `pytest -q -- --collect-only` still runs collect-only
    # mode, i.e. pytest's parser keeps matching options after `--`.
    # Rejection at this boundary is the only mechanism that pins the
    # target as a non-flag; valid targets keep the exact pre-W1/S1 argv.
    reject_dash_leading_target(
        test_target.target_expression, engine_label="pytest"
    )
    if test_target.target_expression:
        argv.append(test_target.target_expression)

    env = _build_child_env()
    result, started_ms, completed_ms = await run_and_capture(
        argv,
        cwd=test_target.workspace_path,
        env=env,
        timeout=timeout,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_label="pytest",
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

    coverage_written = False
    if collect_coverage:
        assert coverage_json_path is not None and coverage_xml_path is not None
        coverage_written = coverage_json_path.exists()
        if not coverage_written and result.returncode == 0:
            # A clean pytest exit that produced no coverage JSON is a
            # genuine anomaly — pytest-cov was requested and pytest
            # reported success, so the file MUST exist.
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            raise AdapterInvocationError(
                f"pytest-cov did not write coverage JSON to {coverage_json_path}; "
                f"stderr tail: {stderr_text[-400:]}",
                kind="unparseable-output",
            )
        # Non-zero exit + missing coverage JSON is NOT an adapter failure
        # (S15 rider, routed from the W1/S8 close): a collection/import
        # error interrupts pytest before pytest-cov writes its report,
        # but the pytest JSON report above parsed fine — that is a
        # persisted USER result (`status="errored"` → exit 3 per
        # docs/agent/troubleshooting.md "Exit 3 is not an error"), with
        # the coverage artifacts omitted so downstream `coverage` verbs
        # report unavailable for this run.

    engine_version = await _read_pytest_version(
        interpreter, test_target.workspace_path
    )

    artifact_paths: dict[str, Path] = {
        "pytest_json_report": report_path,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    if coverage_written:
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


def _resolve_pytest_interpreter(workspace: Path) -> str:
    """Resolve the interpreter to run ``-m pytest`` with (RUN-11).

    Venv-first, per ``foundations.md`` §3: if the target ``workspace`` ships
    a ``.venv`` whose pytest console script is present
    (``.venv/bin/pytest`` on POSIX, ``.venv/Scripts/pytest.exe`` on
    Windows), return that venv's Python interpreter so the child runs the
    SuT's own pytest and its plugins. Otherwise fall back to
    ``sys.executable`` (the interpreter running novetest). Never a bare
    ``pytest`` off PATH — PATH leakage is a recurring bug source.

    Why probe the console script but return the sibling *python*: the
    script's presence is the signal that pytest is installed in the venv,
    but we invoke ``<python> -m pytest`` (not the script directly) to keep
    the ``-m`` module-resolution semantics of the existing argv. A
    well-formed venv with pytest installed always carries the sibling
    python next to the script.

    This is deployment-mode-critical: under the ``foundations.md`` §7 PyApp
    standalone binary, ``sys.executable`` is the bundled CPython unpacked
    into the user data-dir, which cannot see a SuT's venv-only pytest — the
    exact failure RUN-11 describes. Falling back to ``sys.executable`` when
    no venv pytest exists preserves the pipx-into-venv deployment path
    (novetest's own interpreter carries pytest) unchanged.
    """

    venv = workspace / ".venv"
    if sys.platform == "win32":
        pytest_script = venv / "Scripts" / "pytest.exe"
        venv_python = venv / "Scripts" / "python.exe"
    else:
        pytest_script = venv / "bin" / "pytest"
        venv_python = venv / "bin" / "python"
    if pytest_script.exists():
        return str(venv_python)
    return sys.executable


def _build_child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    # Deterministic-env contract (RUN-11, foundations.md §3): pin the hash
    # seed, mark CI, and force color off so runs are reproducible.
    env["PYTHONHASHSEED"] = "0"
    env["CI"] = "1"
    env["FORCE_COLOR"] = "0"
    env.pop("PYTEST_ADDOPTS", None)
    # RUN-24: drop an inherited PYTHONPATH so a host-profile 3.x tree cannot
    # leak onto the child's sys.path ahead of the SuT's own dependencies.
    env.pop("PYTHONPATH", None)
    return env


async def _query_pytest_version(interpreter: str, workspace: Path) -> str | None:
    """Ask ``interpreter`` for its pytest version in a child process.

    Shared with `run/readiness.py`'s pytest probe so readiness and the
    adapter report the version of the SAME interpreter (board row 22) —
    one implementation, no forked logic.

    RUN-26 guard: an exec failure (the interpreter vanished or became
    non-executable between resolution and spawn) degrades to ``None``
    instead of crashing the caller; the version is informational metadata,
    never load-bearing for the Run Record's correctness.
    """

    try:
        result = await run_subprocess(
            [interpreter, "-c", "import pytest; print(pytest.__version__)"],
            cwd=workspace,
            timeout=15.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.decode("utf-8", errors="replace").strip()
    return version or None


async def _read_pytest_version(interpreter: str, workspace: Path) -> str | None:
    """Version of the pytest that ACTUALLY ran (board row 22).

    ``interpreter`` is `_resolve_pytest_interpreter`'s result:

    * ``sys.executable`` — the child IS this process's interpreter, so the
      parent's import cache answers exactly and for free. A subprocess
      probe here would double the cost of a typical Phase 1 run for no
      accuracy gain, so the parent-import fast path stays.
    * a workspace ``.venv`` python — a DIFFERENT pytest installation, so
      the parent's version is not the running one (observed live
      2026-07-20: venv pytest 9.1.1 reported as the parent's 9.0.3). The
      version must come from the resolved child.

    ``None`` silently on any failure, either way.
    """

    if interpreter == sys.executable:
        try:
            import pytest
        except ImportError:
            return None
        version = getattr(pytest, "__version__", None)
        return str(version) if version is not None else None
    return await _query_pytest_version(interpreter, workspace)
