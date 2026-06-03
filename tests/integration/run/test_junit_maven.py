"""Integration tests for the JUnit adapter — Maven path.

Spawns a real `mvn -B test` against the `junit-maven-basic` fixture.
Skip-gated on `shutil.which("java") is None or shutil.which("mvn") is
None` so the test runs only on hosts equipped per
`scripts/dev-host-setup.md §5` (and per the polyglot-host-parity
contract `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`).

Runtime expectation: ~30–90 seconds on first run (Maven downloads
JUnit Jupiter from Maven Central into the per-user `~/.m2/repository/`
cache). Subsequent runs use the warm cache and finish in ~10–15 s.
"""

from __future__ import annotations

import shutil
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
    # Failing test still fails; coverage XML still emitted because the
    # JaCoCo agent is in the test phase and the report goal runs in the
    # test lifecycle.
    assert "coverage_xml" in result.artifact_paths
    coverage_xml = result.artifact_paths["coverage_xml"]
    assert coverage_xml.is_file()
    xml_text = coverage_xml.read_text(encoding="utf-8")
    assert "<report" in xml_text
    assert "Calculator" in xml_text
