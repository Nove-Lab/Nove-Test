"""Integration tests for the JUnit adapter — Maven path.

Spawns a real `mvn -B test` against the `junit-maven-basic` fixture.
Skip-gated on `shutil.which("java") is None or shutil.which("mvn") is
None` so the test runs only on hosts equipped per
`scripts/dev-host-setup.md §5` (and per the polyglot-host-parity
contract `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`).

Runtime expectation: ~30–90 seconds on first run (Maven downloads
JUnit Jupiter from Maven Central into the per-user `~/.m2/repository/`
cache). Subsequent runs use the warm cache and finish in ~10–15 s.

CLI-level smoke (Defect 4 closure per hotfix 2026-06-04): the
``test_cli_smoke_run_emits_envelope`` case spawns the real CLI via
``subprocess.run`` to exercise the orchestration layer's
``.relative_to(store.path)`` invariant. Without this, adapter
contract violations like Defect 1 (reports_dir set to a native
out-of-store path) remain invisible to the team's local gate AND
Main Branch's pre-merge gate — the original 2026-06-03 JUnit cycle
was verdict-failed by Manual Test exactly because the adapter-
direct integration tests bypassed the wire surface.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.run.adapters.junit_adapter import run_junit
from novetest.run.types import TestTarget


pytestmark = pytest.mark.skipif(
    shutil.which("java") is None or shutil.which("mvn") is None,
    reason="JDK 17+ and Maven 3.9+ required (see scripts/dev-host-setup.md §5)",
)


FIXTURE_DIR = (
    Path(__file__).parents[2]
    / "fixtures"
    / "projects"
    / "junit-maven-basic"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Copy the fixture into tmp_path so the test doesn't pollute the
    repo with `target/` artifacts. Mirrors the cargo / gotest fixture
    isolation pattern.
    """

    dest = tmp_path / "junit-maven-basic"
    shutil.copytree(FIXTURE_DIR, dest)
    return dest


async def test_basic_run_emits_native_result(
    workspace: Path, tmp_path: Path
) -> None:
    artifact_dir = tmp_path / "art"
    target = TestTarget(
        target_expression="",
        target_type="workspace",
        workspace_path=workspace,
    )
    result = await run_junit(
        target,
        artifact_dir=artifact_dir,
        timeout=300.0,
        collect_coverage=False,
    )

    assert result.engine_name == "junit"
    # exit non-zero because the fixture has one deliberately failing test.
    assert result.returncode != 0

    payload = result.payload
    assert payload["build_tool"] == "maven"

    tests_raw = payload.get("tests")
    assert isinstance(tests_raw, list)
    summary = payload.get("summary")
    assert isinstance(summary, dict)
    # 4 passed + 1 failed + 1 skipped = 6 tests in the fixture.
    assert summary["total"] == 6
    assert summary["passed"] == 4
    assert summary["failed"] == 1
    assert summary["skipped"] == 1

    # Failure log written for the one failing test.
    failure_logs_raw = payload.get("failure_logs")
    assert isinstance(failure_logs_raw, dict)
    assert "com.example.CalculatorTest#testSubtract" in failure_logs_raw

    # Artifact paths registered.
    assert "stdout" in result.artifact_paths
    assert "stderr" in result.artifact_paths
    assert "reports_dir" in result.artifact_paths

    # Defect 1 hotfix (2026-06-04): the reports_dir MUST be staged under
    # the per-run artifact_dir (a subpath of `store.path`), NOT the
    # native Maven `target/surefire-reports/` directory. Otherwise the
    # orchestration layer's ``.relative_to(store.path)`` rewrite at
    # ``workflows/run.py:85-88`` raises and the CLI returns a
    # `cli-error` envelope on every JUnit run.
    reports_dir = result.artifact_paths["reports_dir"]
    assert reports_dir.is_relative_to(artifact_dir), (
        f"reports_dir {reports_dir} is not under artifact_dir {artifact_dir}; "
        "Defect 1 regression — adapter must stage under artifact_dir/native/reports"
    )
    assert reports_dir == artifact_dir / "native" / "reports"
    # The staged dir actually contains the JUnit XML the parser read.
    assert any(reports_dir.glob("TEST-*.xml"))

    # Metadata pin for the vendored launcher version (always present).
    assert result.metadata["console_launcher_version"] == "1.11.4"
    assert result.metadata["build_tool"] == "maven"


async def test_coverage_run_emits_jacoco_xml(
    workspace: Path, tmp_path: Path
) -> None:
    artifact_dir = tmp_path / "art"
    target = TestTarget(
        target_expression="",
        target_type="workspace",
        workspace_path=workspace,
    )
    result = await run_junit(
        target,
        artifact_dir=artifact_dir,
        timeout=300.0,
        collect_coverage=True,
    )
    # Failing test still surfaces as exit 3 (EXIT_USER_TESTS_FAILED); the
    # `-Dmaven.test.failure.ignore=true` flag (hotfix #2, 2026-06-04)
    # lets Maven continue past the Surefire failure so the subsequent
    # `jacoco:report` goal actually runs and writes
    # ``target/site/jacoco/jacoco.xml``. Without that flag, Maven aborts
    # at the test phase and JaCoCo XML is never serialized — that was
    # the Defect 2 reopen Manual Test caught on 2026-06-04 after the
    # first hotfix attempt.
    assert "coverage_xml" in result.artifact_paths
    coverage_xml = result.artifact_paths["coverage_xml"]
    assert coverage_xml.is_file()
    xml_text = coverage_xml.read_text(encoding="utf-8")
    assert "<report" in xml_text
    assert "Calculator" in xml_text

    # Defect 2 hotfix (2026-06-04): coverage_xml is staged under
    # ``artifact_dir/native/coverage/jacoco.xml`` — not the native Maven
    # ``target/site/jacoco/jacoco.xml`` — so the orchestration layer's
    # ``.relative_to(store.path)`` rewrite holds. (The original cycle
    # never populated `coverage_xml` at all, even with JaCoCo wired in
    # the fixture's pom.xml.)
    assert coverage_xml.is_relative_to(artifact_dir)
    assert coverage_xml == artifact_dir / "native" / "coverage" / "jacoco.xml"


# ---------------------------------------------------------------------------
# CLI-level smoke (Defect 4 closure — Manual Test 2026-06-04 findings)
# ---------------------------------------------------------------------------


def test_cli_smoke_run_emits_envelope(workspace: Path) -> None:
    """End-to-end CLI smoke — catches Defect-1-class regressions.

    Calls ``python -m novetest run`` via subprocess (not ``run_junit``
    directly) so the orchestration layer's ``.relative_to(store.path)``
    invariant is actually exercised. The 2026-06-03 cycle landed a
    contract violation that was structurally invisible to the
    adapter-direct integration tests above — this case forecloses the
    regression class.

    Mirrors the canonical pattern from
    ``tests/integration/orchestration/conftest.py::run_cli_in``: same
    interpreter (``sys.executable``), ``-m novetest``, ``NOVETEST_OUTPUT
    =json`` for stable envelope shape, UTF-8 decode.
    """

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"

    init_result = subprocess.run(
        [sys.executable, "-m", "novetest", "init"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = subprocess.run(
        [sys.executable, "-m", "novetest", "run"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    # Exit 0 (all passed) or 3 (EXIT_USER_TESTS_FAILED, some user test
    # failed) are the only acceptable codes on the canonical happy-path
    # fixture. Hotfix #1 shipped a buggy `(0, 1)` here — Manual Test
    # caught it on 2026-06-04 because EXIT_GENERIC=1 doesn't fire on
    # a clean user-tests-failed exit; the canonical fixture intentionally
    # contains a failing test and the CLI reports it via the dedicated
    # EXIT_USER_TESTS_FAILED=3 channel (see `src/novetest/cli/output.py:
    # 12-17`).
    assert run_result.returncode in (0, 3), (
        f"CLI returned exit {run_result.returncode}; "
        f"expected 0 (EXIT_OK, all passed) or 3 (EXIT_USER_TESTS_FAILED, "
        f"some user tests failed). Exit codes 1 (EXIT_GENERIC), "
        f"2 (EXIT_USAGE), 4 (EXIT_ENGINE_MISSING), 5 (EXIT_STORAGE) all "
        f"indicate contract or environment violations and MUST not "
        f"occur on the canonical happy-path fixture. See "
        f"src/novetest/cli/output.py:12-17. "
        f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert isinstance(envelope["ok"], bool)
    if envelope["ok"]:
        assert envelope["data"]["run_record"]["engine_name"] == "junit"
