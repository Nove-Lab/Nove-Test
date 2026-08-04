"""Unit tests for the xunit / .NET branch of ``probe_engine``.

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

from novetest.run.readiness import probe_engine


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
    result = await probe_engine(workspace_with_xunit_v2, "dotnet", "xunit")
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
    result = await probe_engine(workspace_with_xunit_v3, "dotnet", "xunit")
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
    result = await probe_engine(workspace_with_xunit_v2, "dotnet", "xunit")
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
    result = await probe_engine(tmp_path, "dotnet", "xunit")
    assert result.state == "engine-misconfigured"
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"


async def test_mstest_diagnostic(
    workspace_with_mstest: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(workspace_with_mstest, "dotnet", "xunit")
    assert result.state == "engine-misconfigured"
    assert any("MSTest" in issue for issue in result.issues)
    assert any("xUnit v2" in issue for issue in result.issues)


async def test_nunit_diagnostic(
    workspace_with_nunit: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(workspace_with_nunit, "dotnet", "xunit")
    assert result.state == "engine-misconfigured"
    assert any("NUnit" in issue for issue in result.issues)


async def test_neither_xunit_nor_mstest_nor_nunit_diagnostic(
    workspace_with_neither: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(workspace_with_neither, "dotnet", "xunit")
    assert result.state == "engine-misconfigured"
    assert any("xUnit is not declared" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Nested `src/` + `tests/` solution layout (2026-08-04 regression)
# ---------------------------------------------------------------------------
#
# `novetest init` at the root of a `dotnet new sln`-shaped solution
# answered `engine-misconfigured` — the projects sit at depth 2 and the
# depth-1 glob never saw them, even though the `.sln` that names them is
# what made the workspace .NET in the first place. Readiness is the
# surface the user actually hit (`init`, and `test`'s pre-flight, which
# exited 4); the discovery unit tests live next to the adapter in
# `tests/unit/run/adapters/test_dotnet_adapter.py`.


async def test_depth_two_solution_layout_is_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    """THE `novetest init` regression, at the readiness surface."""

    src_dir = tmp_path / "src" / "Expensable"
    src_dir.mkdir(parents=True)
    (src_dir / "Expensable.csproj").write_text(_CSPROJ_NEITHER, encoding="utf-8")
    tests_dir = tmp_path / "tests" / "Expensable.Tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "Expensable.Tests.csproj").write_text(
        _CSPROJ_V2, encoding="utf-8"
    )
    # Real solutions are UTF-8 **with BOM**, CRLF, backslash-separated.
    (tmp_path / "expensable.sln").write_bytes(
        "\r\n".join(
            [
                "",
                "Microsoft Visual Studio Solution File, Format Version 12.00",
                'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = '
                '"Expensable", "src\\Expensable\\Expensable.csproj", '
                '"{1FA66788-629D-4467-A9B3-C9DE4576EB73}"',
                "EndProject",
                'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = '
                '"Expensable.Tests", '
                '"tests\\Expensable.Tests\\Expensable.Tests.csproj", '
                '"{9BC5DD25-FF11-4188-94DC-FD99CFFA9154}"',
                "EndProject",
            ]
        ).encode("utf-8-sig")
    )

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(tmp_path, "dotnet", "xunit")

    assert result.state == "ready", (
        f"solution-root readiness regressed to {result.state!r}: "
        f"{result.issues!r}"
    )
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"


async def test_solution_with_no_project_files_stays_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.sln`` naming nothing that exists is still a misconfigured
    workspace — the fallback must not go green on the sln's mere
    presence, and the diagnostic must name all three discovery sources
    so the user knows where novetest looked."""

    (tmp_path / "empty.sln").write_text(
        "Microsoft Visual Studio Solution File, Format Version 12.00\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(tmp_path, "dotnet", "xunit")

    assert result.state == "engine-misconfigured"
    assert any("*.sln" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# RUN-14 (W1/S2): readiness ↔ adapter csproj-selection coherence
# ---------------------------------------------------------------------------
#
# Readiness once re-implemented the test-csproj filter locally with a
# smaller token set ("test" only vs the adapter's tests/test/specs/spec)
# and diverged: it could answer `ready` after probing a csproj the
# adapter never runs, or block a runnable workspace. The fix
# single-sources the selection through `_detect_test_project`; these
# tests construct both RUN-14 layouts and assert that the csproj
# readiness judges IS the csproj the adapter will hand to `dotnet test`.


async def test_run14_readiness_probes_the_adapter_chosen_specs_csproj(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    """Layout: ``Z.Test`` (xunit v2) + ``A.Specs`` (MSTest).

    Both declare ``Microsoft.NET.Test.Sdk``, so discovery's tier-1
    (self-declared test project) filter keeps BOTH, both names match the
    token tier, and the adapter picks the sort-first ``A.Specs.csproj``
    — which is MSTest, so the run novetest would launch is not one it
    supports. Readiness must judge that SAME csproj and answer
    ``engine-misconfigured`` (naming it), not a false ``ready`` earned
    by probing ``Z.Test.csproj`` the adapter never runs.

    (Before the 2026-08-04 nested-discovery slice this layout used
    ``_CSPROJ_NEITHER`` for ``A.Specs``; discovery now prefers the
    project that declares itself a test project, so a *plain library*
    named ``.Specs`` no longer beats a real test project — see
    ``test_nested_discovery_prefers_declared_test_project_over_named_library``
    in ``tests/unit/run/adapters/test_dotnet_adapter.py``. The RUN-14
    invariant under test here is unchanged: whatever discovery picks,
    readiness judges exactly that file.)"""

    from novetest.run.adapters.dotnet_adapter import _detect_test_project

    z_dir = tmp_path / "Z.Test"
    z_dir.mkdir()
    (z_dir / "Z.Test.csproj").write_text(_CSPROJ_V2, encoding="utf-8")
    a_dir = tmp_path / "A.Specs"
    a_dir.mkdir()
    (a_dir / "A.Specs.csproj").write_text(_CSPROJ_MSTEST, encoding="utf-8")

    adapter_chosen, _, _ = _detect_test_project(tmp_path)
    assert adapter_chosen is not None
    assert adapter_chosen.name == "A.Specs.csproj"

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(tmp_path, "dotnet", "xunit")

    assert result.state == "engine-misconfigured"
    # The diagnostic names the adapter's choice — proof readiness read
    # the same file the adapter will execute against.
    assert any("MSTest detected" in issue for issue in result.issues), (
        f"readiness diverged from the adapter: expected the MSTest "
        f"diagnostic for {adapter_chosen.name!r}, got {result.issues!r}"
    )


async def test_run14_reverse_specs_only_xunit_workspace_is_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_dotnet_version: None,
) -> None:
    """Reverse layout: ``Zeta.Specs`` (xunit v2) + ``Alpha`` (plain
    library), no test-token project name anywhere.

    The old local filter matched neither name and fell back to
    ``all_csprojs[0]`` = ``Alpha.csproj`` (no xunit) → it blocked a
    perfectly runnable workspace as ``engine-misconfigured``. The
    adapter matches the ``specs`` token and runs ``Zeta.Specs.csproj``;
    readiness must reach the same verdict: ``ready``."""

    from novetest.run.adapters.dotnet_adapter import _detect_test_project

    alpha_dir = tmp_path / "Alpha"
    alpha_dir.mkdir()
    (alpha_dir / "Alpha.csproj").write_text(_CSPROJ_NEITHER, encoding="utf-8")
    zeta_dir = tmp_path / "Zeta.Specs"
    zeta_dir.mkdir()
    (zeta_dir / "Zeta.Specs.csproj").write_text(_CSPROJ_V2, encoding="utf-8")

    adapter_chosen, _, _ = _detect_test_project(tmp_path)
    assert adapter_chosen is not None
    assert adapter_chosen.name == "Zeta.Specs.csproj"

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    result = await probe_engine(tmp_path, "dotnet", "xunit")

    assert result.state == "ready", (
        f"readiness diverged from the adapter: the adapter runs "
        f"{adapter_chosen.name!r} (xunit v2, runnable) but readiness "
        f"answered {result.state!r} with issues {result.issues!r}"
    )
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"


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
    result = await probe_engine(workspace_with_xunit_v2, "dotnet", "xunit")
    # Readiness stays green; engine_version is None.
    assert result.state == "ready"
    assert result.engine_context is not None
    assert result.engine_context.engine_version is None
