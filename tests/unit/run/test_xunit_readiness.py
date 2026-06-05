"""Unit tests for the xunit / .NET branch of ``assess_engine_readiness``.

Covers the brief §3.1 doctor probe table for the xunit path:
- Missing dotnet → ``engine-missing``.
- Missing csproj despite ``.csproj`` glob marker → ``engine-misconfigured``
  (TOCTOU defense).
- Missing xunit PackageReference → ``engine-misconfigured`` with
  framework-specific diagnostic (MSTest / NUnit dedicated messages).
- xUnit v3 → ``ready`` (adapter emits warning at run time; readiness is
  green so the user CAN run tests).
- Happy path → ``ready`` with engine_version captured from
  ``dotnet --version``.

The ``shutil.which`` seam is monkey-patched per-test so cases are
hermetic and don't depend on the host's installed toolchain.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.run.readiness import assess_engine_readiness


_CSPROJ_V2 = """\
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="coverlet.collector" Version="6.0.2" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
    <PackageReference Include="xunit" Version="2.6.0" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.3" />
  </ItemGroup>
</Project>
"""

_CSPROJ_V3 = """\
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="xunit" Version="3.0.0" />
  </ItemGroup>
</Project>
"""

_CSPROJ_MSTEST = """\
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="MSTest.TestFramework" Version="3.0.0" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""

_CSPROJ_NUNIT = """\
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="NUnit" Version="4.0.0" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""

_CSPROJ_NEITHER = """\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>
"""


@pytest.fixture
def workspace_with_xunit_v2(tmp_path: Path) -> Path:
    """Canonical xUnit v2 layout: ``MyLib.Tests/MyLib.Tests.csproj`` at
    depth 1. Mirrors the fixture shape."""

    test_dir = tmp_path / "MyLib.Tests"
    test_dir.mkdir()
    (test_dir / "MyLib.Tests.csproj").write_text(_CSPROJ_V2, encoding="utf-8")
    return tmp_path


@pytest.fixture
def workspace_with_xunit_v3(tmp_path: Path) -> Path:
    test_dir = tmp_path / "MyLib.Tests"
    test_dir.mkdir()
    (test_dir / "MyLib.Tests.csproj").write_text(_CSPROJ_V3, encoding="utf-8")
    return tmp_path


@pytest.fixture
def workspace_with_mstest(tmp_path: Path) -> Path:
    test_dir = tmp_path / "MyLib.Tests"
    test_dir.mkdir()
    (test_dir / "MyLib.Tests.csproj").write_text(_CSPROJ_MSTEST, encoding="utf-8")
    return tmp_path


@pytest.fixture
def workspace_with_nunit(tmp_path: Path) -> Path:
    test_dir = tmp_path / "MyLib.Tests"
    test_dir.mkdir()
    (test_dir / "MyLib.Tests.csproj").write_text(_CSPROJ_NUNIT, encoding="utf-8")
    return tmp_path


@pytest.fixture
def workspace_with_neither(tmp_path: Path) -> Path:
    test_dir = tmp_path / "MyLib.Tests"
    test_dir.mkdir()
    (test_dir / "MyLib.Tests.csproj").write_text(_CSPROJ_NEITHER, encoding="utf-8")
    return tmp_path


# Pretend ``dotnet --version`` succeeds and returns ``8.0.421\n`` by
# patching the subprocess seam. Tests that need a different SDK probe
# behavior override this.
@pytest.fixture
def stub_dotnet_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    from novetest.utils.asyncio_subprocess import SubprocessResult

    async def stub(
        argv: Any, *, cwd: Any, env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        return SubprocessResult(
            returncode=0, stdout=b"8.0.421\n", stderr=b"", timed_out=False,
        )

    # Patch the module-level run_subprocess that ``_probe_dotnet_sdk_version``
    # imports. We patch it on the readiness module since that's where the
    # async caller lives.
    monkeypatch.setattr("novetest.run.readiness.run_subprocess", stub)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_v2_workspace_with_dotnet_returns_ready(
    workspace_with_xunit_v2: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await assess_engine_readiness(workspace_with_xunit_v2)
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.ecosystem == "dotnet"
    assert result.engine_context.engine_name == "xunit"
    assert result.engine_context.engine_version == "8.0.421"


async def test_v3_workspace_with_dotnet_returns_ready(
    workspace_with_xunit_v3: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    """v3 detected at the adapter's run-time produces a warning but
    readiness itself is GREEN — the user CAN run tests, just not with
    coverage. This separation matches the JUnit pattern where v4/TestNG
    are misconfigured (no tests run) but JUnit Jupiter is ready."""

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await assess_engine_readiness(workspace_with_xunit_v3)
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"


# ---------------------------------------------------------------------------
# engine-missing: dotnet not on PATH
# ---------------------------------------------------------------------------


async def test_dotnet_missing_returns_engine_missing(
    workspace_with_xunit_v2: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = await assess_engine_readiness(workspace_with_xunit_v2)
    assert result.state == "engine-missing"
    assert result.engine_context is None
    assert any("dotnet" in issue for issue in result.issues)
    assert any("dev-host-setup.md §6" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# engine-misconfigured: csproj-related
# ---------------------------------------------------------------------------


async def test_csproj_gone_at_assessment_time_returns_misconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the candidate detector saw a ``*.csproj`` but it disappears
    before assessment (TOCTOU), surface as ``engine-misconfigured``
    rather than crashing. To exercise this, drop a temporary ``*.sln``
    that triggers the candidate path then delete the csproj."""

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    # Add a .sln to trigger candidate detection.
    (tmp_path / "MyLib.sln").write_text("# minimal", encoding="utf-8")
    result = await assess_engine_readiness(tmp_path)
    assert result.state == "engine-misconfigured"
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"


async def test_mstest_diagnostic(
    workspace_with_mstest: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await assess_engine_readiness(workspace_with_mstest)
    assert result.state == "engine-misconfigured"
    assert any("MSTest" in issue for issue in result.issues)
    assert any("xUnit v2" in issue for issue in result.issues)


async def test_nunit_diagnostic(
    workspace_with_nunit: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await assess_engine_readiness(workspace_with_nunit)
    assert result.state == "engine-misconfigured"
    assert any("NUnit" in issue for issue in result.issues)


async def test_neither_xunit_nor_mstest_nor_nunit_diagnostic(
    workspace_with_neither: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await assess_engine_readiness(workspace_with_neither)
    assert result.state == "engine-misconfigured"
    assert any("xUnit is not declared" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# SDK version detection — None when probe fails
# ---------------------------------------------------------------------------


async def test_sdk_version_none_when_dotnet_version_fails(
    workspace_with_xunit_v2: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed ``dotnet --version`` probe → engine_version=None silently
    (informational metadata only; never load-bearing)."""

    from typing import Any

    from novetest.utils.asyncio_subprocess import SubprocessResult

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    async def stub(
        argv: Any, *, cwd: Any, env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        return SubprocessResult(
            returncode=1, stdout=b"", stderr=b"oops",
            timed_out=False,
        )

    monkeypatch.setattr("novetest.run.readiness.run_subprocess", stub)
    result = await assess_engine_readiness(workspace_with_xunit_v2)
    # Readiness stays green; engine_version is None.
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.engine_version is None
