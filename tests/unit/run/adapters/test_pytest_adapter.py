"""Unit tests for the pytest Native Engine adapter.

These tests spawn a real pytest subprocess against the fixture projects.
The adapter sets ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` and explicitly loads
``-p pytest_jsonreport`` so the dev venv's plugins do not leak in — that
isolation is verified by exercising the adapter directly here.
"""

from __future__ import annotations

import json
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
    """Point sys.executable at a binary that cannot run ``-m pytest``."""

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "executable", "/bin/false")
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
