"""Unit tests for the JUnit branch of `assess_engine_readiness`.

Covers the brief §5 + §10 doctor probe table for the JUnit path:
- Missing JDK / Maven / Gradle → `engine-misconfigured`.
- Missing Jupiter → `engine-misconfigured` with manifest-aware
  diagnostic specificity (JUnit 4 / TestNG dedicated messages).
- Windows OS gate.
- Happy path → `ready` with engine_version captured.

The `shutil.which` seam is monkey-patched per-test so the cases are
hermetic and don't depend on the host's installed toolchain.

**Windows OS-gate skip** (2026-06-09 cycle): the JUnit adapter is
intentionally gated against Windows per decision
``2026-06-03-junit-console-launcher-vendor.md`` §R5 (foundations Open
Question #16 — Windows binary pipeline not yet shipped). The
non-Windows-asserting tests below would observe ``engine-misconfigured``
on a real Windows host (the gate IS firing — which is correct) instead
of their expected ``ready`` / missing-binary diagnostics that assume the
host can actually run JUnit. We skip those tests on Windows with the
``_SKIP_IF_WINDOWS`` mark. The ``test_windows_os_gate`` case below uses
``monkeypatch.setattr(... sys.platform, "win32")`` to verify the gate
fires from a Linux/macOS CI host AND continues to pass on a real
Windows host — that is the gate-firing regression detection on both
sides of the OS axis. Restore by removing the per-test marks when Open
Question #16 lands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from novetest.run.readiness import assess_engine_readiness


_SKIP_IF_WINDOWS = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason=(
        "JUnit adapter gates Windows per decision "
        "2026-06-03-junit-console-launcher-vendor.md §R5; "
        "Open Question #16 (Windows binary pipeline) pending. "
        "Gate-firing verification lives in test_windows_os_gate "
        "(monkeypatches sys.platform → runs on both Windows and non-Windows)."
    ),
)


_POM_WITH_JUPITER = """<project>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
    </dependencies>
</project>"""


@pytest.fixture
def maven_workspace(tmp_path: Path) -> Path:
    """Maven workspace with Jupiter declared. Tests monkey-patch
    `shutil.which` to control the readiness outcome."""

    (tmp_path / "pom.xml").write_text(_POM_WITH_JUPITER, encoding="utf-8")
    return tmp_path


@_SKIP_IF_WINDOWS
async def test_ready_when_java_and_mvn_present(
    maven_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(maven_workspace)
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.ecosystem == "java"
    assert result.engine_context.engine_name == "junit"
    # Version captured from manifest.
    assert result.engine_context.engine_version == "5.10.2"


@_SKIP_IF_WINDOWS
async def test_missing_jdk(
    maven_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: None if name == "java" else f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(maven_workspace)
    assert result.state == "engine-misconfigured"
    assert any("java" in issue for issue in result.issues)


@_SKIP_IF_WINDOWS
async def test_missing_mvn(
    maven_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: None if name == "mvn" else f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(maven_workspace)
    assert result.state == "engine-misconfigured"
    assert any("mvn" in issue.lower() for issue in result.issues)


@_SKIP_IF_WINDOWS
async def test_missing_jupiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plain pom.xml with no JUnit dependency → `missing-jupiter`
    diagnosis."""

    (tmp_path / "pom.xml").write_text(
        "<project><dependencies></dependencies></project>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(tmp_path)
    assert result.state == "engine-misconfigured"
    assert any("Jupiter" in issue or "jupiter" in issue for issue in result.issues)


@_SKIP_IF_WINDOWS
async def test_junit4_specific_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JUnit 4 present (without Jupiter) → specific `JUnit 4`
    message rather than the generic `missing-jupiter`."""

    pom = """<project>
        <dependencies>
            <dependency>
                <artifactId>junit</artifactId>
                <version>4.13.2</version>
            </dependency>
        </dependencies>
    </project>"""
    (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(tmp_path)
    assert result.state == "engine-misconfigured"
    assert any("JUnit 4" in issue for issue in result.issues)


@_SKIP_IF_WINDOWS
async def test_testng_specific_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pom = """<project>
        <dependencies>
            <dependency>
                <groupId>org.testng</groupId>
                <artifactId>testng</artifactId>
                <version>7.10.2</version>
            </dependency>
        </dependencies>
    </project>"""
    (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    result = await assess_engine_readiness(tmp_path)
    assert result.state == "engine-misconfigured"
    assert any("TestNG" in issue for issue in result.issues)


@_SKIP_IF_WINDOWS
async def test_gradle_wrapper_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When gradle is not on PATH but `gradlew` wrapper is present in
    workspace, the probe should still be ready (no
    `missing-build-tool`)."""

    (tmp_path / "build.gradle.kts").write_text(
        """plugins { jacoco }
        dependencies {
            testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
        }""",
        encoding="utf-8",
    )
    (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "gradle":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr("novetest.run.readiness.shutil.which", fake_which)
    result = await assess_engine_readiness(tmp_path)
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "junit"


async def test_windows_os_gate(
    maven_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief §5 step 1: Windows surfaces `os-unsupported` even when
    the rest of the toolchain is present."""

    monkeypatch.setattr(
        "novetest.run.readiness.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr("novetest.run.readiness.sys.platform", "win32")
    result = await assess_engine_readiness(maven_workspace)
    assert result.state == "engine-misconfigured"
    assert any("Windows" in issue for issue in result.issues)
