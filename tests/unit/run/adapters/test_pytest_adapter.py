"""Unit tests for the pytest Native Engine adapter.

These tests spawn a real pytest subprocess against the fixture projects.
The adapter sets ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` and explicitly loads
``-p pytest_jsonreport`` so the dev venv's plugins do not leak in — that
isolation is verified by exercising the adapter directly here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from novetest.run.adapters.pytest_adapter import (
    COVERAGE_JSON_FILENAME,
    COVERAGE_RC_FILENAME,
    COVERAGE_XML_FILENAME,
    PYTEST_REPORT_FILENAME,
    STDERR_LOG_FILENAME,
    STDOUT_LOG_FILENAME,
    run_pytest,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target
from novetest.utils.asyncio_subprocess import SubprocessResult


@pytest.fixture(autouse=True)
def _route_harness_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the shared-harness main-spawn seam back to this adapter (W2/S13).

    The main engine spawn moved into ``_harness.run_and_capture`` (which
    calls ``_harness.run_subprocess``); these tests still stub the seam on
    ``pytest_adapter.run_subprocess``. The adapter imports
    ``run_subprocess`` itself (the OQ-25/row-22 version query spawns the
    RESOLVED interpreter), so the setattr below re-pins the same real
    function and the harness call is late-bound to it — a test stubbing
    ``pytest_adapter.run_subprocess`` therefore intercepts BOTH the engine
    spawn and the version query. The REAL ``run_subprocess`` is the
    baseline so an unstubbed test never recurses.
    """

    import novetest.run.adapters.pytest_adapter as _adapter
    from novetest.run.adapters import _harness
    from novetest.utils.asyncio_subprocess import run_subprocess as _real

    monkeypatch.setattr(_adapter, "run_subprocess", _real, raising=False)

    async def _delegate(*args: object, **kwargs: object) -> object:
        return await _adapter.run_subprocess(*args, **kwargs)

    monkeypatch.setattr(_harness, "run_subprocess", _delegate)


async def test_basic_fixture_produces_report(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    result = await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.returncode == 0
    assert result.payload["exitcode"] == 0
    report_path = result.artifact_paths["pytest_json_report"]
    assert report_path.name == PYTEST_REPORT_FILENAME
    assert report_path.is_file()
    stdout_path = result.artifact_paths["stdout"]
    stderr_path = result.artifact_paths["stderr"]
    assert stdout_path.name == STDOUT_LOG_FILENAME
    assert stderr_path.name == STDERR_LOG_FILENAME
    # Coverage emission is opt-in; the default run must not advertise it.
    assert "coverage_json" not in result.artifact_paths
    assert "coverage_xml" not in result.artifact_paths
    payload_on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload_on_disk["summary"]["total"] == 3
    assert payload_on_disk["summary"]["passed"] == 3


async def test_failing_fixture_returns_failed_payload(
    failing_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", failing_workspace)
    result = await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    # pytest returns 1 when one or more tests failed.
    assert result.returncode == 1
    summary = result.payload["summary"]
    assert isinstance(summary, dict)
    assert summary.get("failed", 0) >= 1


async def test_conftest_import_error_raises_unparseable(tmp_path: Path) -> None:
    """A conftest import error aborts pytest before the JSON plugin runs.

    pytest exits 4 with no report on disk; the adapter must surface that
    as a typed `AdapterInvocationError` rather than a parse exception so
    the CLI can map it to exit code 4 with structured guidance.
    """

    target = resolve_test_target("", tmp_path)
    (tmp_path / "conftest.py").write_text(
        "import does_not_exist  # noqa: F401\n", encoding="utf-8"
    )
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)
    assert exc_info.value.kind == "unparseable-output"


async def test_pytest_unavailable_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point sys.executable at a binary that exits non-zero on every invocation.

    The adapter spawns ``<sys.executable> -m pytest ...``. We need a real
    executable that exists, spawns successfully, and exits non-zero
    regardless of args — so the JSON report never lands and the adapter
    wraps the failure in ``AdapterInvocationError``. We write a tiny
    always-fail script under ``tmp_path`` rather than relying on
    ``/bin/false`` (Linux-only path; macOS ships ``/usr/bin/false`` and
    Windows has no such binary), so the test runs identically on every
    CI matrix cell.
    """

    import novetest.run.adapters.pytest_adapter as adapter

    if sys.platform == "win32":
        fake = tmp_path / "always_fail.bat"
        fake.write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")
    else:
        fake = tmp_path / "always_fail"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(0o755)

    monkeypatch.setattr(adapter.sys, "executable", str(fake))
    target = resolve_test_target("", tmp_path)
    with pytest.raises(AdapterInvocationError):
        await run_pytest(target, artifact_dir=tmp_path, timeout=30.0)


# ---------------------------------------------------------------------------
# Coverage emission (Phase 2 entry)
# ---------------------------------------------------------------------------


async def test_coverage_emission_produces_contexts_and_missing_branches(
    coverage_workspace: Path, tmp_path: Path
) -> None:
    """With ``collect_coverage=True`` the JSON report carries:

    - the per-line ``contexts`` map (proves ``show_contexts=True`` and
      ``--cov-context=test`` are both wired through);
    - a non-empty ``missing_lines`` or ``missing_branches`` entry for the
      fixture's deliberately-uncovered ``negative`` branch.

    Also asserts the new ``coverage_json`` / ``coverage_xml`` keys are
    present in ``artifact_paths``, the Cobertura XML lands on disk, and
    the per-run ``.coveragerc`` is written under ``artifact_dir``.
    """

    target = resolve_test_target("", coverage_workspace)
    result = await run_pytest(
        target,
        artifact_dir=tmp_path,
        timeout=120.0,
        collect_coverage=True,
    )
    assert result.returncode == 0
    assert result.payload["exitcode"] == 0

    coverage_json = result.artifact_paths["coverage_json"]
    coverage_xml = result.artifact_paths["coverage_xml"]
    assert coverage_json.name == COVERAGE_JSON_FILENAME
    assert coverage_xml.name == COVERAGE_XML_FILENAME
    assert coverage_json.is_file()
    assert coverage_xml.is_file()
    # The per-run .coveragerc and coverage.py's intermediate data file
    # must live under artifact_dir, never inside the workspace — the
    # adapter must not mutate the SuT.
    assert (tmp_path / COVERAGE_RC_FILENAME).is_file()
    assert not (coverage_workspace / COVERAGE_RC_FILENAME).exists()
    assert not (coverage_workspace / ".coverage").exists()

    coverage_payload = json.loads(coverage_json.read_text(encoding="utf-8"))
    files = coverage_payload["files"]
    classifier_key = next(
        (k for k in files if k.endswith("classifier.py")), None
    )
    assert classifier_key is not None, f"classifier.py missing from files: {list(files)!r}"
    classifier_entry = files[classifier_key]

    contexts = classifier_entry.get("contexts")
    assert isinstance(contexts, dict) and contexts, (
        "contexts map must be non-empty when show_contexts + --cov-context=test "
        f"are in effect; got: {contexts!r}"
    )
    # Each context list should reference at least one of the fixture's tests.
    flat_contexts = {ctx for ctxs in contexts.values() for ctx in ctxs}
    assert any(
        "test_classify_positive" in ctx or "test_classify_zero" in ctx
        for ctx in flat_contexts
    ), f"no test nodeid found in contexts: {flat_contexts!r}"

    summary = classifier_entry["summary"]
    missing_lines = classifier_entry.get("missing_lines") or []
    missing_branches = classifier_entry.get("missing_branches") or []
    # The deliberately-uncovered ``negative`` branch must show up somewhere.
    assert missing_lines or missing_branches, (
        f"deliberate gap not visible in coverage report: summary={summary!r}"
    )


async def test_coverage_missing_plugin_raises_missing_plugin(
    coverage_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``-p pytest_cov`` cannot import, surface ``missing-plugin``.

    We simulate the missing-plugin condition by pointing PYTHONPATH at an
    empty dir AND clearing the site-packages search — the cheapest way is
    to use a sentinel argv-prefix that drops pytest-cov's importability for
    the child only. Simplest reliable approach: swap the child env's
    ``PYTHONPATH`` to a directory containing a stub ``pytest_cov.py`` that
    raises on import. We use that here.
    """

    # Build a directory with a pytest_cov stub that fails to import.
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "pytest_cov.py").write_text(
        "raise ImportError('pytest_cov stub: deliberately broken')\n",
        encoding="utf-8",
    )

    import novetest.run.adapters.pytest_adapter as adapter

    original_build_env = adapter._build_child_env

    def patched_env() -> dict[str, str]:
        env = original_build_env()
        env["PYTHONPATH"] = str(sandbox)
        return env

    monkeypatch.setattr(adapter, "_build_child_env", patched_env)

    target = resolve_test_target("", coverage_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_pytest(
            target,
            artifact_dir=tmp_path,
            timeout=60.0,
            collect_coverage=True,
        )
    # Either the stub forces a `No module named pytest_cov` style import
    # error, or the early plugin failure aborts pytest before the JSON
    # report lands. Both routes converge on a typed error; we only require
    # that *some* AdapterInvocationError is raised with a well-known kind.
    assert exc_info.value.kind in {"missing-plugin", "unparseable-output"}


# ---------------------------------------------------------------------------
# Collection-error-under-coverage classification boundary (W2/S15 rider,
# routed from the W1/S8 close)
# ---------------------------------------------------------------------------
#
# pytest-cov writes NO coverage JSON when the session is interrupted during
# collection, but the pytest JSON report still lands and parses. That is a
# USER result (`status="errored"` → exit 3 per the documented contract at
# docs/agent/troubleshooting.md "Exit 3 is not an error"), NOT an adapter
# failure. The boundary: missing coverage JSON raises `unparseable-output`
# ONLY when pytest exited 0 (a clean run that produced no coverage is a
# genuine anomaly). Reverting the boundary in `run_pytest` fails
# `test_collection_error_with_coverage_returns_errored_result` with the
# old `AdapterInvocationError` — the A/B proof for wire delta B.


async def test_collection_error_with_coverage_returns_errored_result(
    tmp_path: Path,
) -> None:
    """REAL pytest: a broken test module (collection error, exit 2) under
    ``collect_coverage=True`` returns a NativeResult that normalizes to a
    persisted ``errored`` run — no raise, coverage artifacts omitted."""

    from novetest.run.normalizer import normalize_native_result
    from novetest.run.types import NativeEngineContext

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "test_broken_syntax.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8"
    )
    artifact_dir = tmp_path / "art"

    target = resolve_test_target("", workspace)
    result = await run_pytest(
        target,
        artifact_dir=artifact_dir,
        timeout=60.0,
        collect_coverage=True,
    )

    # pytest exits 2 on a collection error; the JSON report still parsed.
    assert result.returncode == 2
    assert result.payload["exitcode"] == 2
    # Coverage artifacts omitted — pytest-cov never wrote them.
    assert "coverage_json" not in result.artifact_paths
    assert "coverage_xml" not in result.artifact_paths
    # The report artifact is still registered (a persisted user result).
    assert result.artifact_paths["pytest_json_report"].is_file()

    record = normalize_native_result(
        result,
        NativeEngineContext(ecosystem="python", engine_name="pytest"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"


async def test_coverage_json_missing_on_clean_exit_still_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The KEEP side of the boundary: pytest exit 0 + parsed report but NO
    coverage JSON → the genuine-anomaly raise stays (`unparseable-output`)."""

    import novetest.run.adapters.pytest_adapter as adapter

    async def fake_run_subprocess(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        report_arg = next(
            a for a in argv if a.startswith("--json-report-file=")
        )
        Path(report_arg.split("=", 1)[1]).write_text(
            json.dumps(
                {"exitcode": 0, "summary": {"total": 1, "passed": 1}, "tests": []}
            ),
            encoding="utf-8",
        )
        # Deliberately does NOT write the --cov-report=json target.
        return SubprocessResult(
            returncode=0, stdout=b"", stderr=b"", timed_out=False
        )

    monkeypatch.setattr(adapter, "run_subprocess", fake_run_subprocess)

    target = resolve_test_target("", tmp_path)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_pytest(
            target,
            artifact_dir=tmp_path / "art",
            timeout=30.0,
            collect_coverage=True,
        )
    assert exc_info.value.kind == "unparseable-output"
    assert "coverage JSON" in str(exc_info.value)


async def test_coverage_json_missing_on_nonzero_exit_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stub twin of the real collection-error test: identical fake run
    except ``returncode=2`` → NO raise, coverage artifacts omitted. Pins
    the boundary discriminant to ``result.returncode`` exactly."""

    import novetest.run.adapters.pytest_adapter as adapter

    async def fake_run_subprocess(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        report_arg = next(
            a for a in argv if a.startswith("--json-report-file=")
        )
        Path(report_arg.split("=", 1)[1]).write_text(
            json.dumps(
                {"exitcode": 2, "summary": {"total": 0}, "tests": []}
            ),
            encoding="utf-8",
        )
        return SubprocessResult(
            returncode=2, stdout=b"", stderr=b"E   SyntaxError\n", timed_out=False
        )

    monkeypatch.setattr(adapter, "run_subprocess", fake_run_subprocess)

    target = resolve_test_target("", tmp_path)
    result = await run_pytest(
        target,
        artifact_dir=tmp_path / "art",
        timeout=30.0,
        collect_coverage=True,
    )
    assert result.returncode == 2
    assert "coverage_json" not in result.artifact_paths
    assert "coverage_xml" not in result.artifact_paths


# ---------------------------------------------------------------------------
# artifact_dir.resolve() hardening (2026-06-08, B2-4 cycle)
# ---------------------------------------------------------------------------
#
# `run_pytest` calls ``artifact_dir = artifact_dir.resolve()`` as the first
# line of the function body. The pair below pins the defensive behavior:
# (a) a relative ``artifact_dir`` lands artifacts at the cwd-anchored
# absolute path (silently writing under the wrong directory is the
# original-TODO failure mode); (b) an absolute ``artifact_dir`` is
# unchanged by the resolve. Both tests use the real pytest subprocess
# against ``basic_workspace`` because pytest is always present in the dev
# venv — the resolve is a path-shape invariant, not a subprocess
# invariant, so the runtime cost is identical to the existing happy-path
# test above.


async def test_relative_artifact_dir_resolves_against_cwd(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative ``artifact_dir`` should resolve against the test's cwd.

    Hardens against the long-standing TODO from 2026-05-16. Future callers
    that pass a relative path (intentionally or by bug) must land artifacts
    at a predictable absolute location, not silently under whatever cwd
    the subprocess inherits.
    """

    monkeypatch.chdir(tmp_path)
    rel_artifact_dir = Path("rel-art")
    expected_root = (tmp_path / "rel-art").resolve()

    target = resolve_test_target("", basic_workspace)
    result = await run_pytest(target, artifact_dir=rel_artifact_dir, timeout=60.0)

    # The native/ directory must exist at the cwd-anchored absolute path.
    assert (expected_root / "native").is_dir()
    # Every registered artifact path must be absolute AND nested under
    # the resolved root — proves the resolve flowed through to all
    # downstream Path compositions, not just the initial mkdir.
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert expected_root in path.parents, (
            f"{key} → {path} is not under {expected_root}"
        )


async def test_absolute_artifact_dir_unchanged_after_resolve(
    basic_workspace: Path,
    tmp_path: Path,
) -> None:
    """An absolute ``artifact_dir`` should round-trip through resolve.

    The resolve call is idempotent on absolute paths (no-op + symlink
    follow). The existing production caller shape — orchestration builds
    absolute paths under ``.novetest/run/artifacts/run_<ulid>/`` — must
    continue producing artifacts at exactly the input path, byte-identical
    to pre-hardening behavior.
    """

    abs_artifact_dir = (tmp_path / "abs-art").resolve()
    target = resolve_test_target("", basic_workspace)
    result = await run_pytest(target, artifact_dir=abs_artifact_dir, timeout=60.0)

    assert (abs_artifact_dir / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert abs_artifact_dir in path.parents, (
            f"{key} → {path} is not under {abs_artifact_dir}"
        )


async def test_argv_appends_valid_target_bare_without_separator(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid target keeps the exact pre-W1/S1 argv: bare final element,
    NO ``--`` separator.

    The frozen wave-1 text prescribed a ``--`` separator here, but on
    pytest 9.0.3 ``--`` does not terminate option parsing (empirically,
    2026-07-07: ``pytest -q -- --collect-only`` still runs collect-only
    mode), so it would pin nothing while implying safety. Dash-leading
    targets are rejected at the adapter boundary instead — see
    ``test_target_argv_hygiene.py``. This test pins the argv shape so a
    future "add the separator back" change has to confront the evidence.
    """

    import novetest.run.adapters.pytest_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        assert isinstance(argv, list)
        captured_argv.extend(argv)
        report_arg = next(
            a
            for a in argv
            if isinstance(a, str) and a.startswith("--json-report-file=")
        )
        report_path = Path(report_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {"exitcode": 0, "summary": {"total": 1, "passed": 1}, "tests": []}
            ),
            encoding="utf-8",
        )
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target(
        "tests/test_math_utils.py::test_add_positive", basic_workspace
    )
    await run_pytest(target, artifact_dir=tmp_path, timeout=60.0)

    assert captured_argv[-1] == "tests/test_math_utils.py::test_add_positive"
    assert "--" not in captured_argv


# ---------------------------------------------------------------------------
# Venv-first interpreter resolution + deterministic child env (RUN-11, RUN-24)
# ---------------------------------------------------------------------------
#
# foundations.md §3: run the SuT's own ``.venv`` pytest when present (critical
# for the §7 PyApp standalone binary, whose ``sys.executable`` is a bundled
# CPython that cannot see a project-venv-only pytest), else fall back to the
# current interpreter — never a bare ``pytest`` off PATH. The child env pins
# the deterministic trio (``PYTHONHASHSEED`` / ``CI`` / ``FORCE_COLOR``) and
# drops an inherited ``PYTHONPATH`` (RUN-24). Our fixtures carry no ``.venv``,
# so the in-repo gate exercises the fallback path unchanged; these tests
# synthesize both the POSIX and Windows ``.venv`` layouts.


def test_resolve_interpreter_prefers_posix_venv_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "platform", "linux")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "pytest").write_text("#!/bin/sh\n", encoding="utf-8")
    (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    assert adapter._resolve_pytest_interpreter(tmp_path) == str(venv_bin / "python")


def test_resolve_interpreter_prefers_windows_venv_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows layout: probe ``.venv/Scripts/pytest.exe``, return the sibling
    ``python.exe``. Exercised via the direct helper because ``sys.platform``
    is not ``win32`` on the CI matrix cell running this file."""

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    venv_scripts = tmp_path / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    (venv_scripts / "pytest.exe").write_bytes(b"MZ")

    assert adapter._resolve_pytest_interpreter(tmp_path) == str(
        venv_scripts / "python.exe"
    )


def test_resolve_interpreter_falls_back_to_sys_executable(tmp_path: Path) -> None:
    import novetest.run.adapters.pytest_adapter as adapter

    # No .venv in the workspace → the current interpreter (never bare pytest).
    assert adapter._resolve_pytest_interpreter(tmp_path) == sys.executable


def test_resolve_interpreter_falls_back_when_venv_lacks_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.venv`` present but WITHOUT pytest installed → fall back.

    Using novetest's own interpreter (which carries pytest) keeps the run
    working, matching the pre-RUN-11 behavior for a SuT that has a venv but
    never installed pytest into it. The probe keys on the pytest console
    script, not the mere existence of ``.venv``.
    """

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "platform", "linux")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")  # no pytest

    assert adapter._resolve_pytest_interpreter(tmp_path) == sys.executable


async def test_venv_pytest_flows_into_spawn_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a synthetic POSIX ``.venv`` makes the spawned ``argv[0]``
    the venv python, proving the resolution reaches the harness spawn.

    The ``-m pytest`` prefix is preserved — we invoke the venv's python with
    ``-m``, never the console script directly. The same stub also answers
    the row-22 version query, which must target the SAME venv python (its
    reply — not the parent's pytest version — becomes ``engine_version``).
    """

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "platform", "linux")
    workspace = tmp_path / "ws"
    venv_bin = workspace / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "pytest").write_text("#!/bin/sh\n", encoding="utf-8")
    (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    captured_argv: list[str] = []
    version_argv: list[str] = []

    async def capturing_stub(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        assert isinstance(argv, list)
        if "-c" in argv:  # the version query, not the engine spawn
            version_argv.extend(argv)
            return SubprocessResult(
                returncode=0, stdout=b"0.0.0+venv-probe\n", stderr=b"", timed_out=False
            )
        captured_argv.extend(argv)
        report_arg = next(
            a
            for a in argv
            if isinstance(a, str) and a.startswith("--json-report-file=")
        )
        report_path = Path(report_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {"exitcode": 0, "summary": {"total": 1, "passed": 1}, "tests": []}
            ),
            encoding="utf-8",
        )
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target("", workspace)
    result = await run_pytest(target, artifact_dir=tmp_path / "art", timeout=60.0)

    assert captured_argv[0] == str(venv_bin / "python")
    assert captured_argv[1:3] == ["-m", "pytest"]
    # Row 22: the version came from the venv python we ran, not from the
    # parent process's own pytest.
    assert version_argv[0] == str(venv_bin / "python")
    assert result.engine_version == "0.0.0+venv-probe"
    import pytest as _parent_pytest

    assert result.engine_version != _parent_pytest.__version__


# ---------------------------------------------------------------------------
# engine_version reports the pytest that ACTUALLY ran (board row 22)
# ---------------------------------------------------------------------------


async def test_read_pytest_version_uses_parent_import_for_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fast path: when the resolved interpreter IS this process's, the parent
    import cache answers exactly — and no subprocess is spawned (the
    perf rationale for keeping the in-process read)."""

    import novetest.run.adapters.pytest_adapter as adapter

    async def forbidden(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        raise AssertionError("sys.executable path must not spawn a subprocess")

    monkeypatch.setattr(adapter, "run_subprocess", forbidden)

    assert (
        await adapter._read_pytest_version(sys.executable, tmp_path)
        == pytest.__version__
    )


async def test_read_pytest_version_queries_a_resolved_venv_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row 22: a workspace ``.venv`` python is a DIFFERENT pytest install, so
    the version must come from THAT child — the parent's import cache would
    misstate it (observed live: venv 9.1.1 reported as the parent's 9.0.3)."""

    import novetest.run.adapters.pytest_adapter as adapter

    venv_python = str(tmp_path / ".venv" / "bin" / "python")
    captured_argv: list[str] = []

    async def stub(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        assert isinstance(argv, list)
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0, stdout=b"0.0.0+venv-probe\n", stderr=b"", timed_out=False
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    version = await adapter._read_pytest_version(venv_python, tmp_path)
    assert version == "0.0.0+venv-probe"
    assert version != pytest.__version__
    assert captured_argv[0] == venv_python
    assert captured_argv[1] == "-c"


async def test_read_pytest_version_degrades_to_none_on_exec_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RUN-26 guard: the resolved interpreter vanishing between resolution
    and spawn degrades to ``None`` (version is informational), never an
    exception escaping the adapter."""

    import novetest.run.adapters.pytest_adapter as adapter

    async def raising(
        argv: object,
        *,
        cwd: object,
        env: object | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(adapter, "run_subprocess", raising)

    assert (
        await adapter._read_pytest_version(
            str(tmp_path / ".venv" / "bin" / "python"), tmp_path
        )
        is None
    )


def test_build_child_env_sets_deterministic_trio() -> None:
    """RUN-11: the child env carries the deterministic pins on top of the
    pre-existing sanitization, none of which is dropped."""

    import novetest.run.adapters.pytest_adapter as adapter

    env = adapter._build_child_env()
    # New deterministic trio.
    assert env["PYTHONHASHSEED"] == "0"
    assert env["CI"] == "1"
    assert env["FORCE_COLOR"] == "0"
    # Pre-existing pins preserved.
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["NO_COLOR"] == "1"


def test_build_child_env_drops_inherited_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUN-24: an inherited ``PYTHONPATH`` must not reach the pytest child —
    a host-profile 3.x tree would otherwise land ahead of the SuT's deps."""

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setenv("PYTHONPATH", "/host/py310/site-packages")
    env = adapter._build_child_env()
    assert "PYTHONPATH" not in env
