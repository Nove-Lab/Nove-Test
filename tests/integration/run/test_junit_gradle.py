"""Integration tests for the JUnit adapter — Gradle path.

Spawns a real `gradle test --no-daemon` against the
`junit-gradle-basic` fixture. Skip-gated on `shutil.which("java")` and
`shutil.which("gradle")` (the fixture does NOT commit a gradlew
wrapper — see fixture's build.gradle.kts header comment for the
rationale).

Runtime expectation: ~45–120 seconds on first run (Gradle downloads
itself + JUnit Jupiter from gradle.org / Maven Central into the
per-user `~/.gradle/caches/` cache). Subsequent runs use the warm
cache and finish in ~20–30 s.

CLI-level smoke (Defect 4 closure per hotfix 2026-06-04): the
``test_cli_smoke_run_emits_envelope`` case exercises the full CLI →
orchestration → adapter wire surface end-to-end, which is what
catches Defect-1-class regressions. See the Maven sibling file's
docstring for rationale.
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
    shutil.which("java") is None or shutil.which("gradle") is None,
    reason="JDK 17+ and Gradle 7.6+ required (see scripts/dev-host-setup.md §5)",
)


FIXTURE_DIR = (
    Path(__file__).parents[2]
    / "fixtures"
    / "projects"
    / "junit-gradle-basic"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    dest = tmp_path / "junit-gradle-basic"
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
    assert result.returncode != 0  # one failing test in the fixture

    payload = result.payload
    assert payload["build_tool"] == "gradle"

    summary = payload.get("summary")
    assert isinstance(summary, dict)
    assert summary["total"] == 6
    assert summary["passed"] == 4
    assert summary["failed"] == 1
    assert summary["skipped"] == 1

    failure_logs_raw = payload.get("failure_logs")
    assert isinstance(failure_logs_raw, dict)
    # Defect 3 hotfix (2026-06-04): Gradle 8.5 / JUnit Platform 1.10+
    # emit `<testcase name="testSubtract()">` with trailing parens;
    # Maven Surefire strips them. The adapter's `_strip_trailing_parens`
    # normalizes both onto the Maven-canonical no-parens form so the
    # identity is byte-stable across build tools and downstream
    # (Localization, Replay) `test_id` lookups work uniformly.
    assert "com.example.CalculatorTest#testSubtract" in failure_logs_raw
    assert "com.example.CalculatorTest#testSubtract()" not in failure_logs_raw

    # Defect 1 hotfix: reports_dir staged under artifact_dir, not under
    # `<workspace>/build/test-results/test/` (where Gradle natively
    # writes). Without this the orchestration layer's `.relative_to`
    # rewrite raises and the CLI emits a `cli-error` envelope.
    assert "reports_dir" in result.artifact_paths
    reports_dir = result.artifact_paths["reports_dir"]
    assert reports_dir.is_relative_to(artifact_dir)
    assert reports_dir == artifact_dir / "native" / "reports"
    assert any(reports_dir.glob("TEST-*.xml"))

    assert result.metadata["build_tool"] == "gradle"
    assert result.metadata["console_launcher_version"] == "1.11.4"


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
    assert "coverage_xml" in result.artifact_paths
    coverage_xml = result.artifact_paths["coverage_xml"]
    assert coverage_xml.is_file()
    xml_text = coverage_xml.read_text(encoding="utf-8")
    assert "<report" in xml_text
    assert "Calculator" in xml_text

    # Defect 2 hotfix: coverage_xml is staged as the canonical
    # `jacoco.xml` basename under `artifact_dir/native/coverage/`
    # — Gradle's source basename is `jacocoTestReport.xml`; we collapse
    # both Maven and Gradle onto one canonical destination basename so
    # the Coverage engine dispatches on engine_name, not basename.
    assert coverage_xml.is_relative_to(artifact_dir)
    assert coverage_xml == artifact_dir / "native" / "coverage" / "jacoco.xml"


# ---------------------------------------------------------------------------
# CLI-level smoke (Defect 4 closure — Manual Test 2026-06-04 findings)
# ---------------------------------------------------------------------------


def test_cli_smoke_run_emits_envelope(workspace: Path) -> None:
    """End-to-end CLI smoke for the Gradle path. See Maven sibling for
    rationale and the canonical invocation shape."""

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
    assert run_result.returncode in (0, 1), (
        f"CLI returned exit {run_result.returncode}; "
        f"expected 0 (pass) or 1 (some test failed). "
        f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert isinstance(envelope["ok"], bool)
    if envelope["ok"]:
        assert envelope["data"]["run_record"]["engine_name"] == "junit"
