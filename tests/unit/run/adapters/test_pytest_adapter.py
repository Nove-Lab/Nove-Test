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
