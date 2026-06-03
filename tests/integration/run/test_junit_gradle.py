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
"""

from __future__ import annotations

import shutil
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
    assert "com.example.CalculatorTest#testSubtract" in failure_logs_raw

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
