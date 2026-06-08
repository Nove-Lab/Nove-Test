"""Unit tests for the ``dotnet`` / xUnit v2 Native Engine adapter.

The adapter spawns ``dotnet test`` as a subprocess. To avoid requiring
the .NET SDK in every CI cell, tests in this module stub
``run_subprocess`` via ``monkeypatch`` on
``novetest.run.adapters.dotnet_adapter.run_subprocess`` and route the
two probes (``dotnet --version`` + ``dotnet list package``) plus the
main ``dotnet test`` invocation to canned responses. Tests at the
``Test*`` class boundaries below cover the discrete adapter
responsibilities (project detection, version detection, runsettings
generation, argv composition, TRX parsing, etc.).

End-to-end real-`dotnet test` exercise lives in
``tests/integration/run/test_dotnet_*.py``; those skip-gate on
``shutil.which("dotnet")``.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest

import novetest.run.adapters.dotnet_adapter as adapter
from novetest.run.adapters.dotnet_adapter import (
    COVERLET_FLOOR_VERSION,
    ENGINE_NAME,
    RESULTS_DIR_NAME,
    RUNSETTINGS_FILENAME,
    TRX_FILENAME,
    WARNING_AMBIGUOUS_PROJECT,
    WARNING_COVERLET_ABSENT,
    WARNING_COVERLET_BELOW_FLOOR,
    WARNING_XUNIT_V3_DEFERRED,
    _COVERLET_RUNSETTINGS_AGGREGATE,
    _COVERLET_RUNSETTINGS_PER_TEST,
    _detect_test_project,
    _detect_xunit_major_version,
    _detect_xunit_resolved_version,
    _ensure_csproj_restored,
    _format_version,
    _glob_coverage_xml,
    _is_layout_ambiguous,
    _parse_coverlet_version_from_json,
    _parse_coverlet_version_from_text,
    _parse_semver,
    _parse_trx_duration_ms,
    _slugify_for_coverlet,
    _trx_outcome_to_status,
    run_xunit,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import TestTarget
from novetest.utils.asyncio_subprocess import SubprocessResult


_FAKE_DOTNET = "/usr/bin/dotnet"


@pytest.fixture(autouse=True)
def _stub_dotnet_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to a resolvable ``dotnet`` so the adapter's
    up-front PATH probe does not raise ``missing-binary`` before the
    stubbed subprocess is reached. Override in the missing-binary test."""

    monkeypatch.setattr(shutil, "which", lambda name: _FAKE_DOTNET)


# ---------------------------------------------------------------------------
# Canned TRX content used by parser tests
# ---------------------------------------------------------------------------


_MINIMAL_TRX = """\
<?xml version="1.0" encoding="utf-8"?>
<TestRun id="abc" name="run" xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Times creation="2026-06-05T00:00:00Z" queuing="2026-06-05T00:00:00Z" start="2026-06-05T00:00:00Z" finish="2026-06-05T00:00:01Z" />
  <Results>
    <UnitTestResult executionId="exec-1" testId="test-1" testName="MathLib.Tests.MathTests.TestAddPasses" computerName="host" duration="00:00:00.0024784" outcome="Passed" />
    <UnitTestResult executionId="exec-2" testId="test-2" testName="MathLib.Tests.MathTests.TestSubtractIntentionallyFails" computerName="host" duration="00:00:00.0007743" outcome="Failed">
      <Output>
        <ErrorInfo>
          <Message>Assert.Equal() Failure: Values differ
Expected: 5
Actual:   6</Message>
          <StackTrace>   at MathLib.Tests.MathTests.TestSubtractIntentionallyFails()</StackTrace>
        </ErrorInfo>
      </Output>
    </UnitTestResult>
    <UnitTestResult executionId="exec-3" testId="test-3" testName="MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)" computerName="host" duration="00:00:00.0000338" outcome="Passed" />
    <UnitTestResult executionId="exec-4" testId="test-4" testName="MathLib.Tests.MathTests.TestSkippedExample" computerName="host" duration="00:00:00.0000000" outcome="NotExecuted" />
  </Results>
  <TestDefinitions>
    <UnitTest name="MathLib.Tests.MathTests.TestAddPasses" id="test-1">
      <Execution id="exec-1" />
      <TestMethod className="MathLib.Tests.MathTests" name="TestAddPasses" adapterTypeName="executor://xunit/VsTestRunner2/netcoreapp" />
    </UnitTest>
    <UnitTest name="MathLib.Tests.MathTests.TestSubtractIntentionallyFails" id="test-2">
      <Execution id="exec-2" />
      <TestMethod className="MathLib.Tests.MathTests" name="TestSubtractIntentionallyFails" adapterTypeName="executor://xunit/VsTestRunner2/netcoreapp" />
    </UnitTest>
    <UnitTest name="MathLib.Tests.MathTests.TestParametrized" id="test-3">
      <Execution id="exec-3" />
      <TestMethod className="MathLib.Tests.MathTests" name="TestParametrized" adapterTypeName="executor://xunit/VsTestRunner2/netcoreapp" />
    </UnitTest>
    <UnitTest name="MathLib.Tests.MathTests.TestSkippedExample" id="test-4">
      <Execution id="exec-4" />
      <TestMethod className="MathLib.Tests.MathTests" name="TestSkippedExample" adapterTypeName="executor://xunit/VsTestRunner2/netcoreapp" />
    </UnitTest>
  </TestDefinitions>
</TestRun>
"""

_TRX_ALL_OUTCOMES = """\
<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Results>
    <UnitTestResult testId="t1" testName="T1" outcome="Passed" duration="00:00:00.001" />
    <UnitTestResult testId="t2" testName="T2" outcome="Failed" duration="00:00:00.002" />
    <UnitTestResult testId="t3" testName="T3" outcome="NotExecuted" duration="00:00:00.000" />
    <UnitTestResult testId="t4" testName="T4" outcome="Skipped" duration="00:00:00.000" />
    <UnitTestResult testId="t5" testName="T5" outcome="Inconclusive" duration="00:00:00.000" />
    <UnitTestResult testId="t6" testName="T6" outcome="Aborted" duration="00:00:00.000" />
    <UnitTestResult testId="t7" testName="T7" outcome="Error" duration="00:00:00.000" />
    <UnitTestResult testId="t8" testName="T8" outcome="Timeout" duration="00:00:00.000" />
    <UnitTestResult testId="t9" testName="T9" outcome="SomethingElse" duration="00:00:00.000" />
  </Results>
  <TestDefinitions />
</TestRun>
"""


# ---------------------------------------------------------------------------
# Subprocess stub factory
# ---------------------------------------------------------------------------


def _make_run_subprocess_stub(
    *,
    dotnet_version: bytes = b"8.0.421\n",
    coverlet_json: bytes | None = None,
    coverlet_tabular: bytes | None = None,
    coverlet_returncode: int = 0,
    restore_returncode: int = 0,
    main_returncode: int = 0,
    main_stdout: bytes = b"",
    main_stderr: bytes = b"",
    main_timed_out: bool = False,
    captured_argv: list[list[str]] | None = None,
    captured_restore: list[list[str]] | None = None,
    call_log: list[str] | None = None,
    seed_trx: str | None = _MINIMAL_TRX,
    seed_coverage_xml: bool = False,
    seed_per_test_coverage_files: int = 0,
    raise_file_not_found: bool = False,
) -> Any:
    """Build an async stub for ``run_subprocess`` that emulates a run.

    Recognized argv shapes (matched by suffix tokens to stay tolerant
    of path-prefix variations):

    1. ``[dotnet, "--version"]`` → ``dotnet_version`` bytes (returncode 0)
    1.5 ``[dotnet, "restore", <csproj>]`` → ``restore_returncode`` (hotfix #1 F1a)
    2. ``[dotnet, "list", <csproj>, "package", "--include-transitive", "--format", "json"]``
       → ``coverlet_json`` bytes (None → empty projects list)
    3. ``[dotnet, "list", <csproj>, "package", "--include-transitive"]``
       (no ``--format``) → ``coverlet_tabular`` bytes (or empty)
    4. Anything else → the main ``dotnet test`` invocation. Captures argv,
       optionally seeds ``results.trx`` + ``coverage.cobertura.xml`` under
       ``<results-directory>``, returns the configured outcome.

    ``captured_argv`` is mutated in-place when the MAIN invocation runs —
    each call appends the full argv list. Tests that need to assert
    argv shape pass a list and inspect it after ``run_xunit`` returns.

    ``captured_restore`` (hotfix #1 F1a, 2026-06-06) is the separate
    capture list for ``dotnet restore`` invocations — kept distinct
    from ``captured_argv`` so existing tests that index
    ``captured[0]`` as the main call do not break.

    ``call_log`` (hotfix #1 F1a, 2026-06-06) is a parallel ordering
    tracker: every recognized call appends one of ``"version"`` /
    ``"restore"`` / ``"list-json"`` / ``"list-tabular"`` / ``"main"``.
    Tests that assert ordering (e.g. restore-before-probe) inspect
    this list.
    """

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if raise_file_not_found:
            raise FileNotFoundError(2, "No such file or directory: 'dotnet'")

        # 1. dotnet --version
        if (
            isinstance(argv, (list, tuple))
            and len(argv) == 2
            and argv[-1] == "--version"
        ):
            if call_log is not None:
                call_log.append("version")
            return SubprocessResult(
                returncode=0,
                stdout=dotnet_version,
                stderr=b"",
                timed_out=False,
            )

        # 1.5. dotnet restore <csproj>  (hotfix #1 F1a — 2026-06-06)
        if (
            isinstance(argv, (list, tuple))
            and len(argv) >= 2
            and argv[1] == "restore"
        ):
            if captured_restore is not None:
                captured_restore.append(list(argv))
            if call_log is not None:
                call_log.append("restore")
            return SubprocessResult(
                returncode=restore_returncode,
                stdout=b"",
                stderr=b"" if restore_returncode == 0 else b"restore failed",
                timed_out=False,
            )

        # 2. dotnet list package --include-transitive --format json
        if (
            isinstance(argv, (list, tuple))
            and "list" in argv
            and "package" in argv
            and "--format" in argv
        ):
            payload = coverlet_json or b'{"version":1,"parameters":"","projects":[]}'
            if call_log is not None:
                call_log.append("list-json")
            return SubprocessResult(
                returncode=coverlet_returncode,
                stdout=payload,
                stderr=b"",
                timed_out=False,
            )

        # 3. dotnet list package --include-transitive (tabular fallback)
        if (
            isinstance(argv, (list, tuple))
            and "list" in argv
            and "package" in argv
        ):
            payload = coverlet_tabular or b""
            if call_log is not None:
                call_log.append("list-tabular")
            return SubprocessResult(
                returncode=coverlet_returncode,
                stdout=payload,
                stderr=b"",
                timed_out=False,
            )

        # 4. Main invocation.
        if captured_argv is not None:
            captured_argv.append(list(argv))
        if call_log is not None:
            call_log.append("main")

        # Find ``--results-directory <path>`` so the stub can seed the
        # TRX file + per-test or aggregate coverage files (the parser
        # will read them post-run).
        results_dir: Path | None = None
        for i, tok in enumerate(argv):
            if isinstance(tok, str) and tok == "--results-directory" and i + 1 < len(argv):
                results_dir = Path(argv[i + 1])
                break
        if results_dir is not None and seed_trx is not None:
            results_dir.mkdir(parents=True, exist_ok=True)
            (results_dir / TRX_FILENAME).write_text(seed_trx, encoding="utf-8")
        if results_dir is not None and seed_coverage_xml:
            guid_dir = results_dir / "deadbeef-0000-4000-8000-000000000001"
            guid_dir.mkdir(parents=True, exist_ok=True)
            (guid_dir / "coverage.cobertura.xml").write_text(
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<coverage line-rate="1" lines-covered="2" lines-valid="2">'
                '<sources/><packages/></coverage>\n',
                encoding="utf-8",
            )
        if results_dir is not None and seed_per_test_coverage_files > 0:
            guid_dir = results_dir / "deadbeef-0000-4000-8000-000000000002"
            guid_dir.mkdir(parents=True, exist_ok=True)
            for idx in range(seed_per_test_coverage_files):
                (guid_dir / f"coverage.test{idx}.cobertura.xml").write_text(
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    f'<coverage line-rate="1" lines-covered="1" lines-valid="1" test-index="{idx}">'
                    '<sources/><packages/></coverage>\n',
                    encoding="utf-8",
                )

        return SubprocessResult(
            returncode=main_returncode,
            stdout=main_stdout,
            stderr=main_stderr,
            timed_out=main_timed_out,
        )

    return stub


def _seed_csproj(workspace: Path, *, content: str | None = None) -> Path:
    """Write a single ``MathLib.Tests/MathLib.Tests.csproj`` under ``workspace``.

    Default content references ``xunit Version="2.6.0"`` + Coverlet 6.0.2 to
    match the canonical fixture. Tests for the version-detection paths
    pass custom ``content`` to vary the manifest.
    """

    test_dir = workspace / "MathLib.Tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    csproj = test_dir / "MathLib.Tests.csproj"
    csproj.write_text(content if content is not None else (
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>\n'
        '  <ItemGroup>\n'
        '    <PackageReference Include="coverlet.collector" Version="6.0.2" />\n'
        '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />\n'
        '    <PackageReference Include="xunit" Version="2.6.0" />\n'
        '    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.3" />\n'
        '  </ItemGroup>\n'
        '</Project>\n'
    ), encoding="utf-8")
    return csproj


# ---------------------------------------------------------------------------
# TestProjectDetection
# ---------------------------------------------------------------------------


class TestProjectDetection:
    """``_detect_test_project`` + ``_is_layout_ambiguous`` behavior."""

    def test_canonical_lib_plus_test_split_not_ambiguous(
        self, tmp_path: Path
    ) -> None:
        """The library + test project split (1 lib csproj + 1 test csproj
        at depth-1) is the canonical .NET pattern and MUST NOT trigger
        the ``ambiguous-project-layout`` warning."""

        (tmp_path / "MyLib").mkdir()
        (tmp_path / "MyLib" / "MyLib.csproj").write_text("<Project/>")
        (tmp_path / "MyLib.Tests").mkdir()
        (tmp_path / "MyLib.Tests" / "MyLib.Tests.csproj").write_text("<Project/>")

        chosen, all_csprojs, all_slns = _detect_test_project(tmp_path)
        assert chosen is not None
        assert chosen.name == "MyLib.Tests.csproj"
        assert len(all_csprojs) == 2
        assert all_slns == []
        assert _is_layout_ambiguous(all_csprojs, all_slns) is False

    def test_single_csproj_at_root_not_ambiguous(self, tmp_path: Path) -> None:
        """A flat single-csproj layout (just ``Tests.csproj`` at the root)
        works without ambiguity."""

        (tmp_path / "Tests.csproj").write_text("<Project/>")
        chosen, all_csprojs, all_slns = _detect_test_project(tmp_path)
        assert chosen is not None
        assert chosen.name == "Tests.csproj"
        assert _is_layout_ambiguous(all_csprojs, all_slns) is False

    def test_multiple_test_projects_is_ambiguous(self, tmp_path: Path) -> None:
        """Two test-named csprojs (e.g. unit + integration) IS ambiguous.
        The adapter picks alphabetically; the warning surfaces."""

        (tmp_path / "MyLib").mkdir()
        (tmp_path / "MyLib" / "MyLib.csproj").write_text("<Project/>")
        (tmp_path / "MyLib.Tests").mkdir()
        (tmp_path / "MyLib.Tests" / "MyLib.Tests.csproj").write_text("<Project/>")
        (tmp_path / "MyLib.Integration.Tests").mkdir()
        (tmp_path / "MyLib.Integration.Tests" / "MyLib.Integration.Tests.csproj").write_text("<Project/>")

        chosen, all_csprojs, all_slns = _detect_test_project(tmp_path)
        assert chosen is not None
        # Alphabetical-first test-named: ``MyLib.Integration.Tests.csproj``
        # comes before ``MyLib.Tests.csproj`` (case-insensitive sort).
        assert chosen.name == "MyLib.Integration.Tests.csproj"
        assert _is_layout_ambiguous(all_csprojs, all_slns) is True

    def test_sln_present_is_ambiguous(self, tmp_path: Path) -> None:
        """A ``.sln`` file alongside csprojs warrants the warning until
        solution-file walking lands."""

        (tmp_path / "Tests.csproj").write_text("<Project/>")
        (tmp_path / "MyLib.sln").write_text("# minimal sln")
        chosen, all_csprojs, all_slns = _detect_test_project(tmp_path)
        assert chosen is not None
        assert _is_layout_ambiguous(all_csprojs, all_slns) is True

    def test_no_csproj_returns_none(self, tmp_path: Path) -> None:
        chosen, all_csprojs, all_slns = _detect_test_project(tmp_path)
        assert chosen is None
        assert all_csprojs == []
        assert all_slns == []

    def test_prefers_test_named_over_lib_named(self, tmp_path: Path) -> None:
        """When BOTH library and test csprojs exist, ``Tests`` wins
        regardless of alphabetical order. (Lib path 'A.csproj' would come
        before 'B.Tests.csproj' alphabetically; we MUST pick B.Tests.)"""

        (tmp_path / "A").mkdir()
        (tmp_path / "A" / "A.csproj").write_text("<Project/>")
        (tmp_path / "B.Tests").mkdir()
        (tmp_path / "B.Tests" / "B.Tests.csproj").write_text("<Project/>")
        chosen, _, _ = _detect_test_project(tmp_path)
        assert chosen is not None
        assert chosen.name == "B.Tests.csproj"

    async def test_no_csproj_raises_project_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the workspace has no csproj, ``run_xunit`` MUST raise
        ``project-not-found`` BEFORE spawning any subprocess."""

        monkeypatch.setattr(adapter, "run_subprocess", _make_run_subprocess_stub())
        target = TestTarget("", "workspace", tmp_path)
        artifact_dir = tmp_path / "art"
        with pytest.raises(AdapterInvocationError) as exc_info:
            await run_xunit(target, artifact_dir=artifact_dir, timeout=10.0)
        assert exc_info.value.kind == "project-not-found"


# ---------------------------------------------------------------------------
# TestXunitVersionDetection
# ---------------------------------------------------------------------------


class TestXunitVersionDetection:
    """``_detect_xunit_major_version`` + ``_detect_xunit_resolved_version``."""

    def test_v2_pattern_returns_2(self) -> None:
        csproj = '<Project><ItemGroup><PackageReference Include="xunit" Version="2.6.0" /></ItemGroup></Project>'
        assert _detect_xunit_major_version(csproj) == 2

    def test_v2_pattern_2_9_x(self) -> None:
        csproj = '<Project><ItemGroup><PackageReference Include="xunit" Version="2.9.3" /></ItemGroup></Project>'
        assert _detect_xunit_major_version(csproj) == 2

    def test_v3_pattern_returns_3(self) -> None:
        csproj = '<Project><ItemGroup><PackageReference Include="xunit" Version="3.0.0" /></ItemGroup></Project>'
        assert _detect_xunit_major_version(csproj) == 3

    def test_v3_glob_pattern(self) -> None:
        """``Version="3.*"`` (project-wide minor-version pin) also matches v3."""

        csproj = '<Project><ItemGroup><PackageReference Include="xunit" Version="3.*" /></ItemGroup></Project>'
        assert _detect_xunit_major_version(csproj) == 3

    def test_v3_prerelease_pattern(self) -> None:
        """``Version="3.0.0-beta1"`` ALSO matches v3."""

        csproj = '<Project><ItemGroup><PackageReference Include="xunit" Version="3.0.0-beta1" /></ItemGroup></Project>'
        assert _detect_xunit_major_version(csproj) == 3

    def test_no_xunit_returns_zero(self) -> None:
        csproj = (
            '<Project><ItemGroup>'
            '<PackageReference Include="MSTest.TestFramework" Version="3.0.0" />'
            '</ItemGroup></Project>'
        )
        assert _detect_xunit_major_version(csproj) == 0

    def test_xunit_dot_subpackage_does_not_match_root(self) -> None:
        """``xunit.runner.visualstudio`` MUST NOT match the bare ``xunit``
        pattern — the lookahead ``(?![.])`` enforces this."""

        csproj = (
            '<Project><ItemGroup>'
            '<PackageReference Include="xunit.runner.visualstudio" Version="2.5.3" />'
            '</ItemGroup></Project>'
        )
        assert _detect_xunit_major_version(csproj) == 0

    def test_empty_csproj_returns_zero(self) -> None:
        assert _detect_xunit_major_version("") == 0

    def test_resolved_version_extracts_value(self) -> None:
        csproj = '<PackageReference Include="xunit" Version="2.6.5" />'
        assert _detect_xunit_resolved_version(csproj) == "2.6.5"

    def test_resolved_version_none_when_missing(self) -> None:
        assert _detect_xunit_resolved_version("") is None
        assert (
            _detect_xunit_resolved_version("<Project/>")
            is None
        )


# ---------------------------------------------------------------------------
# TestCoverletVersionDetection
# ---------------------------------------------------------------------------


class TestCoverletVersionDetection:
    """``_parse_coverlet_version_from_json`` + ``_parse_coverlet_version_from_text``
    + ``_parse_semver`` + version-tuple comparison."""

    def test_json_top_level_package(self) -> None:
        json_bytes = (
            b'{"version":1,"parameters":"","projects":['
            b'{"path":"x.csproj","frameworks":['
            b'{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","requestedVersion":"6.0.2","resolvedVersion":"6.0.2"}],'
            b'"transitivePackages":[]}]}]}'
        )
        assert _parse_coverlet_version_from_json(json_bytes) == (6, 0, 2)

    def test_json_transitive_package(self) -> None:
        """Coverlet pulled in transitively (rare but possible — e.g. via a
        metapackage) is also detected."""

        json_bytes = (
            b'{"version":1,"parameters":"","projects":['
            b'{"path":"x.csproj","frameworks":['
            b'{"framework":"net8.0","topLevelPackages":[],'
            b'"transitivePackages":[{"id":"coverlet.collector","resolvedVersion":"6.0.4"}]}]}]}'
        )
        assert _parse_coverlet_version_from_json(json_bytes) == (6, 0, 4)

    def test_json_returns_none_when_absent(self) -> None:
        json_bytes = (
            b'{"version":1,"parameters":"","projects":['
            b'{"path":"x.csproj","frameworks":['
            b'{"framework":"net8.0","topLevelPackages":['
            b'{"id":"xunit","requestedVersion":"2.6.0","resolvedVersion":"2.6.0"}],'
            b'"transitivePackages":[]}]}]}'
        )
        assert _parse_coverlet_version_from_json(json_bytes) is None

    def test_json_invalid_payload_returns_none(self) -> None:
        assert _parse_coverlet_version_from_json(b"not json at all") is None

    def test_json_empty_payload_returns_none(self) -> None:
        assert _parse_coverlet_version_from_json(b"{}") is None

    def test_tabular_top_level(self) -> None:
        text = (
            "Project 'MathLib.Tests' has the following package references\n"
            "   [net8.0]:\n"
            "   Top-level Package                                Requested   Resolved\n"
            "   > coverlet.collector                             6.0.2       6.0.2\n"
            "   > Microsoft.NET.Test.Sdk                         17.8.0      17.8.0\n"
        )
        assert _parse_coverlet_version_from_text(text) == (6, 0, 2)

    def test_tabular_transitive_only(self) -> None:
        text = (
            "   Transitive Package                          Resolved\n"
            "   > coverlet.collector                        6.0.4\n"
        )
        assert _parse_coverlet_version_from_text(text) == (6, 0, 4)

    def test_tabular_returns_none_when_absent(self) -> None:
        text = (
            "   Top-level Package                                Requested   Resolved\n"
            "   > xunit                                           2.6.0       2.6.0\n"
        )
        assert _parse_coverlet_version_from_text(text) is None

    def test_tabular_empty_returns_none(self) -> None:
        assert _parse_coverlet_version_from_text("") is None

    def test_semver_parse_simple(self) -> None:
        assert _parse_semver("6.0.2") == (6, 0, 2)

    def test_semver_parse_with_prerelease(self) -> None:
        assert _parse_semver("6.0.2-beta1") == (6, 0, 2)

    def test_semver_parse_with_build_metadata(self) -> None:
        assert _parse_semver("6.0.2+abc") == (6, 0, 2)

    def test_semver_parse_invalid(self) -> None:
        assert _parse_semver("not.a.version") is None
        assert _parse_semver("6.0") is None
        assert _parse_semver("") is None

    def test_version_tuple_below_floor(self) -> None:
        assert (6, 0, 1) < COVERLET_FLOOR_VERSION

    def test_version_tuple_at_floor(self) -> None:
        assert (6, 0, 2) >= COVERLET_FLOOR_VERSION

    def test_version_tuple_above_floor(self) -> None:
        assert (6, 0, 4) > COVERLET_FLOOR_VERSION
        assert (7, 0, 0) > COVERLET_FLOOR_VERSION

    def test_format_version_round_trip(self) -> None:
        assert _format_version((6, 0, 2)) == "6.0.2"


# ---------------------------------------------------------------------------
# TestRunsettingsGeneration
# ---------------------------------------------------------------------------


class TestRunsettingsGeneration:
    """Per-test + aggregate runsettings template generation."""

    def test_per_test_template_matches_decision_verbatim(self) -> None:
        """The per-test template MUST contain the decision §1.1 verbatim
        sequence: ``<PerTestCoverage>true</PerTestCoverage>`` AND
        ``<SingleHit>false</SingleHit>`` AS SIBLINGS under ``<Configuration>``
        AND the ``cobertura,opencover,json,lcov`` Format list. A future
        refactor that drops any of these elements regresses the
        Coverlet contract."""

        template = _COVERLET_RUNSETTINGS_PER_TEST
        assert "<PerTestCoverage>true</PerTestCoverage>" in template
        assert "<SingleHit>false</SingleHit>" in template
        assert "<Format>cobertura,opencover,json,lcov</Format>" in template
        assert 'friendlyName="XPlat Code Coverage"' in template

    def test_aggregate_template_drops_per_test_keeps_singlehit(self) -> None:
        """The aggregate template MUST drop ``<PerTestCoverage>`` per
        decision §5 AND keep ``<SingleHit>false</SingleHit>`` (decision
        §"Why <SingleHit>false</SingleHit> is mandatory")."""

        template = _COVERLET_RUNSETTINGS_AGGREGATE
        assert "<PerTestCoverage>" not in template
        assert "<SingleHit>false</SingleHit>" in template
        assert 'friendlyName="XPlat Code Coverage"' in template

    def test_generation_writes_per_test_file(self, tmp_path: Path) -> None:
        from novetest.run.adapters.dotnet_adapter import _generate_runsettings

        runsettings = _generate_runsettings(tmp_path, mode="per-test")
        assert runsettings.is_file()
        assert runsettings.name == RUNSETTINGS_FILENAME
        assert runsettings.read_text() == _COVERLET_RUNSETTINGS_PER_TEST

    def test_generation_writes_aggregate_file(self, tmp_path: Path) -> None:
        from novetest.run.adapters.dotnet_adapter import _generate_runsettings

        runsettings = _generate_runsettings(tmp_path, mode="aggregate")
        assert runsettings.is_file()
        assert runsettings.read_text() == _COVERLET_RUNSETTINGS_AGGREGATE


# ---------------------------------------------------------------------------
# TestArgvComposition
# ---------------------------------------------------------------------------


class TestArgvComposition:
    """``run_xunit`` argv composition under different coverage / target paths."""

    async def test_no_coverage_no_filter(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Workspace target + no coverage → bare ``dotnet test <csproj>
        --logger trx --results-directory``."""

        captured: list[list[str]] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(captured_argv=captured),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_workspace)
        await run_xunit(target, artifact_dir=artifact_dir, timeout=60.0)
        assert len(captured) == 1, f"expected one main call, got: {captured}"
        argv = captured[0]
        assert argv[0] == _FAKE_DOTNET
        assert argv[1] == "test"
        assert "--logger" in argv
        assert f"trx;LogFileName={TRX_FILENAME}" in argv
        assert "--results-directory" in argv
        # No coverage flags.
        assert "--collect:XPlat Code Coverage" not in argv
        assert "--settings" not in argv
        # No filter.
        assert "--filter" not in argv

    async def test_coverage_v2_coverlet_present_adds_collect_and_settings(
        self,
        dotnet_test_basic_coverage_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Coverage requested + v2 + Coverlet >= 6.0.2 → argv adds
        ``--collect:XPlat Code Coverage`` + ``--settings <runsettings>``."""

        captured: list[list[str]] = []
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","requestedVersion":"6.0.2","resolvedVersion":"6.0.2"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                captured_argv=captured, coverlet_json=json_payload,
                seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_coverage_workspace)
        await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        argv = captured[0]
        assert "--collect:XPlat Code Coverage" in argv
        assert "--settings" in argv
        # The settings path lives under the artifact_dir (hermetic per-run).
        settings_idx = argv.index("--settings")
        settings_path = Path(argv[settings_idx + 1])
        assert settings_path.is_relative_to(artifact_dir)
        assert settings_path.name == RUNSETTINGS_FILENAME

    async def test_coverage_v3_detected_omits_coverage_flags(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v3 detected → no ``--collect`` + no ``--settings`` + warning."""

        # Seed a workspace with an xUnit v3 csproj.
        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws, content=(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            '  <ItemGroup>\n'
            '    <PackageReference Include="xunit" Version="3.0.0" />\n'
            '  </ItemGroup>\n'
            '</Project>\n'
        ))
        captured: list[list[str]] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(captured_argv=captured),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        argv = captured[0]
        assert "--collect:XPlat Code Coverage" not in argv
        assert "--settings" not in argv
        warnings_kinds = [w["kind"] for w in result.payload["warnings"]]
        assert WARNING_XUNIT_V3_DEFERRED in warnings_kinds

    async def test_coverage_coverlet_absent_omits_coverage_flags(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Coverage requested but Coverlet absent → no ``--collect`` +
        ``engine-misconfigured`` warning + ``coverage_xml`` artifact omitted."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws)  # has Coverlet in source but stub returns empty
        # Override the stub: even though the seeded csproj names Coverlet,
        # the JSON probe returns no packages so the adapter's resolution
        # is "absent". This simulates a stale assets file or pre-restore
        # state.
        captured: list[list[str]] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                captured_argv=captured,
                coverlet_json=b'{"version":1,"parameters":"","projects":[]}',
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        argv = captured[0]
        assert "--collect:XPlat Code Coverage" not in argv
        assert "--settings" not in argv
        warnings_kinds = [w["kind"] for w in result.payload["warnings"]]
        assert WARNING_COVERLET_ABSENT in warnings_kinds
        assert "coverage_xml" not in result.artifact_paths

    async def test_coverage_coverlet_below_floor_falls_back_to_aggregate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Coverlet 6.0.1 (below floor) → aggregate runsettings + warning
        + coverage IS still requested (with degraded runsettings) so the
        user gets aggregate-mode data."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws)
        captured: list[list[str]] = []
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","requestedVersion":"6.0.1","resolvedVersion":"6.0.1"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                captured_argv=captured, coverlet_json=json_payload,
                seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        argv = captured[0]
        assert "--collect:XPlat Code Coverage" in argv
        settings_idx = argv.index("--settings")
        settings_path = Path(argv[settings_idx + 1])
        assert settings_path.read_text() == _COVERLET_RUNSETTINGS_AGGREGATE
        warnings_kinds = [w["kind"] for w in result.payload["warnings"]]
        assert WARNING_COVERLET_BELOW_FLOOR in warnings_kinds

    async def test_filter_added_for_nodeid_target(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-directory non-empty target_expression → ``--filter
        FullyQualifiedName~<expr>`` appended."""

        captured: list[list[str]] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(captured_argv=captured),
        )
        artifact_dir = tmp_path / "art"
        # Construct a nodeid target explicitly so the filter is added.
        target = TestTarget(
            target_expression="MathLib.Tests.MathTests.TestAddPasses",
            target_type="nodeid",
            workspace_path=dotnet_test_basic_workspace,
        )
        await run_xunit(target, artifact_dir=artifact_dir, timeout=60.0)
        argv = captured[0]
        assert "--filter" in argv
        filter_idx = argv.index("--filter")
        assert argv[filter_idx + 1] == "FullyQualifiedName~MathLib.Tests.MathTests.TestAddPasses"

    async def test_directory_target_omits_filter(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``target_type="directory"`` (the ``novetest run .`` case) does
        NOT inject a filter — mirrors the cargo Fix A pattern."""

        captured: list[list[str]] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(captured_argv=captured),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target(".", dotnet_test_basic_workspace)
        assert target.target_type == "directory"
        assert target.target_expression == "."
        await run_xunit(target, artifact_dir=artifact_dir, timeout=60.0)
        argv = captured[0]
        assert "--filter" not in argv


# ---------------------------------------------------------------------------
# TestTrxParsing
# ---------------------------------------------------------------------------


class TestTrxParsing:
    """``_parse_trx_results`` + ``_trx_outcome_to_status`` +
    ``_parse_trx_duration_ms`` + failure detail extraction."""

    def test_outcome_passed(self) -> None:
        assert _trx_outcome_to_status("Passed") == "passed"

    def test_outcome_failed(self) -> None:
        assert _trx_outcome_to_status("Failed") == "failed"

    def test_outcome_notexecuted_skipped(self) -> None:
        assert _trx_outcome_to_status("NotExecuted") == "skipped"
        assert _trx_outcome_to_status("Skipped") == "skipped"

    def test_outcome_inconclusive_skipped(self) -> None:
        assert _trx_outcome_to_status("Inconclusive") == "skipped"

    def test_outcome_error_family_errored(self) -> None:
        assert _trx_outcome_to_status("Aborted") == "errored"
        assert _trx_outcome_to_status("Error") == "errored"
        assert _trx_outcome_to_status("Timeout") == "errored"

    def test_outcome_unknown_defaults_to_errored(self) -> None:
        """Defensive default — a new TRX outcome value surfaces as a
        visible errored status rather than a silent passed."""

        assert _trx_outcome_to_status("SomethingNew") == "errored"

    def test_outcome_case_insensitive(self) -> None:
        assert _trx_outcome_to_status("passed") == "passed"
        assert _trx_outcome_to_status("FAILED") == "failed"

    def test_duration_parses_microseconds(self) -> None:
        # 7 fractional digits = 100 ns ticks. 7743 ticks = 7743 * 100 ns
        # = 774_300 ns = 0.7743 ms → rounded down to 0 ms (ticks // 10000).
        assert _parse_trx_duration_ms("00:00:00.0007743") == 0

    def test_duration_parses_milliseconds(self) -> None:
        # 0.001 second = 1 ms. ``1000000`` ticks = 100 ms.
        assert _parse_trx_duration_ms("00:00:00.0010000") == 1

    def test_duration_parses_full_second(self) -> None:
        assert _parse_trx_duration_ms("00:00:01.2345678") == 1234

    def test_duration_parses_minutes_and_hours(self) -> None:
        assert _parse_trx_duration_ms("01:02:03.0") == (
            3_600_000 + 2 * 60_000 + 3_000
        )

    def test_duration_invalid_returns_zero(self) -> None:
        assert _parse_trx_duration_ms("") == 0
        assert _parse_trx_duration_ms("not a duration") == 0

    def test_full_trx_parse(self, tmp_path: Path) -> None:
        """Parse the minimal TRX with 4 tests (1 pass + 1 fail + 1 param
        pass + 1 skip). All outcomes round-trip; failure detail captured."""

        from novetest.run.adapters.dotnet_adapter import _parse_trx_results

        trx_path = tmp_path / "results.trx"
        trx_path.write_text(_MINIMAL_TRX)
        parsed_tests: list[dict[str, Any]] = []
        failure_logs: dict[str, str] = {}
        failures_dir = tmp_path / "failures"
        _parse_trx_results(
            trx_path,
            parsed_tests=parsed_tests,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=tmp_path,
        )
        assert len(parsed_tests) == 4
        statuses = {t["identity"]: t["status"] for t in parsed_tests}
        assert statuses["MathLib.Tests.MathTests.TestAddPasses"] == "passed"
        assert statuses["MathLib.Tests.MathTests.TestSubtractIntentionallyFails"] == "failed"
        assert statuses["MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)"] == "passed"
        assert statuses["MathLib.Tests.MathTests.TestSkippedExample"] == "skipped"
        # Failure log written for the failed test only.
        assert "MathLib.Tests.MathTests.TestSubtractIntentionallyFails" in failure_logs
        rel_path = failure_logs["MathLib.Tests.MathTests.TestSubtractIntentionallyFails"]
        log_path = tmp_path / rel_path
        assert log_path.is_file()
        log_text = log_path.read_text()
        assert "Assert.Equal" in log_text
        assert "Values differ" in log_text

    def test_all_outcomes_round_trip(self, tmp_path: Path) -> None:
        """The ALL-OUTCOMES TRX: 1 pass + 1 fail + 3 skipped (NotExecuted /
        Skipped / Inconclusive) + 4 errored (Aborted / Error / Timeout /
        SomethingElse)."""

        from novetest.run.adapters.dotnet_adapter import _parse_trx_results

        trx_path = tmp_path / "results.trx"
        trx_path.write_text(_TRX_ALL_OUTCOMES)
        parsed_tests: list[dict[str, Any]] = []
        failure_logs: dict[str, str] = {}
        failures_dir = tmp_path / "failures"
        _parse_trx_results(
            trx_path,
            parsed_tests=parsed_tests,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=tmp_path,
        )
        statuses = [t["status"] for t in parsed_tests]
        assert statuses.count("passed") == 1
        assert statuses.count("failed") == 1
        assert statuses.count("skipped") == 3
        assert statuses.count("errored") == 4

    def test_parametrized_identity_preserved_verbatim(self, tmp_path: Path) -> None:
        """The parametrized testName ``"...TestParametrized(a: 1, b: 2,
        expected: 3)"`` MUST round-trip verbatim — Replay / Regression /
        Localization keys depend on byte-stable identities."""

        from novetest.run.adapters.dotnet_adapter import _parse_trx_results

        trx_path = tmp_path / "results.trx"
        trx_path.write_text(_MINIMAL_TRX)
        parsed_tests: list[dict[str, Any]] = []
        failure_logs: dict[str, str] = {}
        failures_dir = tmp_path / "failures"
        _parse_trx_results(
            trx_path,
            parsed_tests=parsed_tests,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=tmp_path,
        )
        identities = {t["identity"] for t in parsed_tests}
        assert (
            "MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)"
            in identities
        )

    def test_malformed_trx_raises_unparseable(self, tmp_path: Path) -> None:
        from novetest.run.adapters.dotnet_adapter import _parse_trx_results

        trx_path = tmp_path / "results.trx"
        trx_path.write_text("<<not valid xml")
        parsed_tests: list[dict[str, Any]] = []
        failure_logs: dict[str, str] = {}
        failures_dir = tmp_path / "failures"
        with pytest.raises(AdapterInvocationError) as exc_info:
            _parse_trx_results(
                trx_path,
                parsed_tests=parsed_tests,
                failure_logs=failure_logs,
                failures_dir=failures_dir,
                artifact_dir=tmp_path,
            )
        assert exc_info.value.kind == "unparseable-output"


# ---------------------------------------------------------------------------
# TestCobertúraCorrelation
# ---------------------------------------------------------------------------


class TestCoberturaCorrelation:
    """Coverage glob behavior + slug-correlation forward-compat."""

    def test_glob_finds_aggregate_only(self, tmp_path: Path) -> None:
        """Default Coverlet 6.0.x behavior — only aggregate
        ``coverage.cobertura.xml`` files appear."""

        guid_dir = tmp_path / "abcd1234"
        guid_dir.mkdir()
        (guid_dir / "coverage.cobertura.xml").write_text("<coverage/>")
        per_test, aggregate = _glob_coverage_xml(tmp_path)
        assert per_test == []
        assert aggregate is not None
        assert aggregate.name == "coverage.cobertura.xml"

    def test_glob_finds_per_test_when_present(self, tmp_path: Path) -> None:
        """Future Coverlet that honors PerTestCoverage → per-test glob
        matches; aggregate is also present (Coverlet writes both)."""

        guid_dir = tmp_path / "abcd1234"
        guid_dir.mkdir()
        (guid_dir / "coverage.cobertura.xml").write_text("<coverage/>")
        (guid_dir / "coverage.test1.cobertura.xml").write_text("<coverage/>")
        (guid_dir / "coverage.test2.cobertura.xml").write_text("<coverage/>")
        per_test, aggregate = _glob_coverage_xml(tmp_path)
        assert len(per_test) == 2
        assert all(p.name.startswith("coverage.test") for p in per_test)
        assert aggregate is not None

    def test_glob_excludes_non_cobertura_siblings(self, tmp_path: Path) -> None:
        """``coverage.json`` / ``coverage.opencover.xml`` / ``coverage.info``
        MUST NOT be picked up by either glob."""

        guid_dir = tmp_path / "abcd1234"
        guid_dir.mkdir()
        (guid_dir / "coverage.cobertura.xml").write_text("<coverage/>")
        (guid_dir / "coverage.json").write_text("{}")
        (guid_dir / "coverage.opencover.xml").write_text("<CoverageSession/>")
        (guid_dir / "coverage.info").write_text("lcov stuff")
        per_test, aggregate = _glob_coverage_xml(tmp_path)
        assert per_test == []  # opencover XML is NOT per-test cobertura
        assert aggregate is not None
        assert aggregate.name == "coverage.cobertura.xml"

    def test_glob_no_results_dir_returns_empty(self, tmp_path: Path) -> None:
        per_test, aggregate = _glob_coverage_xml(tmp_path / "does-not-exist")
        assert per_test == []
        assert aggregate is None

    def test_slugify_for_coverlet_replaces_unsafe_chars(self) -> None:
        """Per the R1 probe — parametrized names contain `(`, `)`, `,`, `:`,
        ` ` which the slugifier must collapse safely."""

        name = "MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)"
        slug = _slugify_for_coverlet(name)
        # No path-unsafe chars remain.
        for bad in ("<", ">", "/", "\\", "(", ")", ",", ":", " "):
            assert bad not in slug
        # Collapses runs of underscores.
        assert "__" not in slug
        # Identifier core survives.
        assert "TestParametrized" in slug

    def test_slugify_truncates_long_names(self) -> None:
        long_name = "x" * 500
        slug = _slugify_for_coverlet(long_name)
        assert len(slug) == 250


# ---------------------------------------------------------------------------
# TestStatusAggregation (delegates to normalizer; tested via normalizer)
# ---------------------------------------------------------------------------


class TestStatusAggregation:
    """``_aggregate_xunit_status`` in the normalizer — mirror tests for the
    full status table."""

    def test_aggregate_passed_when_returncode_zero_no_failures(self) -> None:
        from novetest.run.normalizer import _aggregate_xunit_status
        from novetest.models import TestResult

        assert _aggregate_xunit_status(
            returncode=0,
            test_results=(TestResult(node_id="t1", outcome="passed"),),
        ) == "passed"

    def test_aggregate_failed_when_any_failure(self) -> None:
        from novetest.run.normalizer import _aggregate_xunit_status
        from novetest.models import TestResult

        assert _aggregate_xunit_status(
            returncode=1,
            test_results=(
                TestResult(node_id="t1", outcome="passed"),
                TestResult(node_id="t2", outcome="failed"),
            ),
        ) == "failed"

    def test_aggregate_errored_when_returncode_nonzero_no_failures(self) -> None:
        from novetest.run.normalizer import _aggregate_xunit_status

        # Empty test_results + non-zero exit → "errored" (compile failure
        # before any test ran).
        assert _aggregate_xunit_status(
            returncode=1,
            test_results=(),
        ) == "errored"

    def test_aggregate_failed_overrides_returncode(self) -> None:
        """Even if returncode is 0 (theoretical), the presence of any
        failed/errored test takes precedence."""

        from novetest.run.normalizer import _aggregate_xunit_status
        from novetest.models import TestResult

        assert _aggregate_xunit_status(
            returncode=0,
            test_results=(TestResult(node_id="t1", outcome="failed"),),
        ) == "failed"


# ---------------------------------------------------------------------------
# TestMetadataPopulation
# ---------------------------------------------------------------------------


class TestMetadataPopulation:
    """``NativeResult.metadata`` carries forensic surfaces per task brief §2.7."""

    async def test_dotnet_sdk_version_populated(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(dotnet_version=b"8.0.421\n"),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(target, artifact_dir=tmp_path, timeout=60.0)
        assert result.metadata["dotnet_sdk_version"] == "8.0.421"
        assert result.engine_version == "8.0.421"

    async def test_xunit_version_metadata(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            adapter, "run_subprocess", _make_run_subprocess_stub(),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(target, artifact_dir=tmp_path, timeout=60.0)
        # The basic fixture pins xunit 2.6.0.
        assert result.metadata["xunit_version"] == "2.6.0"

    async def test_native_exit_code_preserved_in_normalized_record(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The normalizer overlays ``native_exit_code`` onto metadata —
        this is the cargo LL #1 forensic surface preservation.

        We verify the NORMALIZED RunRecord here (not just the NativeResult)
        because ``native_exit_code`` is the normalizer's reserved key per
        ``decisions/2026-05-30-native-result-metadata-slot.md``; the
        adapter MUST NOT pre-populate it.
        """

        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(main_returncode=1),
        )
        # Drive the full normalization path through ``execute_with_engine_context``.
        from novetest.run.engine import execute_with_engine_context
        from novetest.run.types import NativeEngineContext

        target = resolve_test_target("", dotnet_test_basic_workspace)
        context = NativeEngineContext(ecosystem="dotnet", engine_name="xunit")
        record, _warnings = await execute_with_engine_context(
            target, context, artifact_dir=tmp_path, timeout=60.0,
        )
        assert record.metadata.get("native_exit_code") == 1
        assert record.engine_name == "xunit"
        assert record.status == "failed"


# ---------------------------------------------------------------------------
# TestEngineMisconfiguredWarnings (already covered above; this is the
# explicit doctor / engine-misconfigured surface)
# ---------------------------------------------------------------------------


class TestEngineMisconfiguredWarnings:
    """Coverlet absent / below-floor / dotnet missing — warning shapes
    pinned for AI consumers + recommendation synthesis."""

    async def test_dotnet_missing_raises_typed_error(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: None)
        target = resolve_test_target("", dotnet_test_basic_workspace)
        with pytest.raises(AdapterInvocationError) as exc_info:
            await run_xunit(target, artifact_dir=tmp_path, timeout=10.0)
        assert exc_info.value.kind == "missing-binary"
        assert exc_info.value.install_hint is not None
        assert "dev-host-setup.md §6" in exc_info.value.install_hint

    async def test_launcher_exec_failure_maps_to_missing_binary(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A ``FileNotFoundError`` from the spawn itself (TOCTOU race)
        still maps to ``missing-binary``."""

        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(raise_file_not_found=True),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        with pytest.raises(AdapterInvocationError) as exc_info:
            await run_xunit(target, artifact_dir=tmp_path, timeout=10.0)
        assert exc_info.value.kind == "missing-binary"

    async def test_coverlet_below_floor_warning_message_names_floor(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The below-floor warning message MUST name both the detected
        version AND the floor — AI consumers need both to recommend a
        fix without re-reading the decision document."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws)
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","resolvedVersion":"6.0.0"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                coverlet_json=json_payload, seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        warnings = [w for w in result.payload["warnings"] if w["kind"] == WARNING_COVERLET_BELOW_FLOOR]
        assert len(warnings) == 1
        assert "6.0.0" in warnings[0]["message"]
        assert "6.0.2" in warnings[0]["message"]


# ---------------------------------------------------------------------------
# TestXunitV3DeferralWarning
# ---------------------------------------------------------------------------


class TestXunitV3DeferralWarning:
    """xUnit v3 detection emits ``xunit-v3-coverage-deferred`` warning
    + runs tests WITHOUT coverage flags."""

    async def test_v3_emits_warning_with_specific_kind(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws, content=(
            '<Project>\n'
            '  <ItemGroup>\n'
            '    <PackageReference Include="xunit" Version="3.0.0" />\n'
            '  </ItemGroup>\n'
            '</Project>\n'
        ))
        monkeypatch.setattr(
            adapter, "run_subprocess", _make_run_subprocess_stub(),
        )
        target = resolve_test_target("", ws)
        artifact_dir = tmp_path / "art"
        result = await run_xunit(
            target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True
        )
        warnings = [w for w in result.payload["warnings"] if w["kind"] == WARNING_XUNIT_V3_DEFERRED]
        assert len(warnings) == 1
        message = warnings[0]["message"]
        assert "xUnit v3" in message
        assert "deferred" in message.lower() or "not yet supported" in message.lower()
        # No coverage_xml artifact when v3 — coverage was skipped.
        assert "coverage_xml" not in result.artifact_paths


# ---------------------------------------------------------------------------
# TestEndToEndStubbed (the canonical adapter happy path with all surfaces)
# ---------------------------------------------------------------------------


class TestEndToEndStubbed:
    """Full ``run_xunit`` against the canonical fixture + stubbed subprocess
    — pins the contract between the adapter and the normalizer."""

    async def test_happy_path_returns_native_result_with_all_surfaces(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(main_returncode=1),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(target, artifact_dir=tmp_path, timeout=60.0)
        assert result.engine_name == ENGINE_NAME == "xunit"
        assert result.returncode == 1  # 1 failed
        assert result.payload["summary"] == {
            "total": 4,
            "passed": 2,
            "failed": 1,
            "skipped": 1,
            "errored": 0,
        }
        # All three artifact path keys present.
        assert "stdout" in result.artifact_paths
        assert "stderr" in result.artifact_paths
        assert "trx" in result.artifact_paths
        # All paths are absolute and under tmp_path.
        for key, path in result.artifact_paths.items():
            assert path.is_absolute(), f"{key!r} path is not absolute: {path}"
            assert path.is_relative_to(tmp_path), f"{key!r} path is not under tmp_path: {path}"

    async def test_timeout_maps_to_typed_error(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                main_returncode=-9, main_timed_out=True,
            ),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        with pytest.raises(AdapterInvocationError) as exc_info:
            await run_xunit(target, artifact_dir=tmp_path, timeout=0.1)
        assert exc_info.value.kind == "timed-out"


# ---------------------------------------------------------------------------
# TestPreRestore (hotfix #1 F1a — 2026-06-06)
# ---------------------------------------------------------------------------


class TestPreRestore:
    """``_ensure_csproj_restored`` + its placement before
    ``_probe_coverlet_version`` on the coverage path.

    Closes the verdict-blocking D1 defect Manual Test caught on
    2026-06-05 (``findings/manual-test-team-2026-06-05-phase2.5-dotnet-
    adapter.md``): the probe ran on a freshly-copied project that had
    no ``obj/project.assets.json`` (the assets file is materialized by
    ``dotnet restore``), the probe returned None, and the adapter
    silently no-op'd the ``--coverage`` flag.

    Fix: ``_ensure_csproj_restored`` runs ``dotnet restore <csproj>``
    BEFORE the probe on the coverage path. These tests pin the
    placement + the call shape + the failure-tolerance contract.
    """

    async def test_restore_invoked_before_probe_on_coverage_path(
        self,
        dotnet_test_basic_coverage_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The canonical ordering — restore MUST happen before list-json
        probe on the coverage path. This is the binding ordering: if it
        ever flips, D1 reopens because the probe runs against a
        no-assets-file state."""

        call_log: list[str] = []
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","requestedVersion":"6.0.2","resolvedVersion":"6.0.2"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                coverlet_json=json_payload,
                call_log=call_log,
                seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_coverage_workspace)
        await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        # restore MUST appear in the call log.
        assert "restore" in call_log, (
            f"_ensure_csproj_restored was not invoked on coverage path; "
            f"call_log={call_log!r}"
        )
        # restore MUST appear BEFORE the list-json probe.
        restore_idx = call_log.index("restore")
        list_idx = call_log.index("list-json")
        assert restore_idx < list_idx, (
            f"restore ran AFTER list-json probe; ordering broken. "
            f"call_log={call_log!r}. This regresses D1 (Manual Test "
            f"2026-06-05) — the probe needs obj/project.assets.json "
            f"from restore."
        )
        # And both MUST happen before the main `dotnet test`.
        main_idx = call_log.index("main")
        assert list_idx < main_idx, (
            f"list-json ran AFTER main `dotnet test`; ordering broken. "
            f"call_log={call_log!r}"
        )

    async def test_restore_not_invoked_on_non_coverage_path(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-coverage runs MUST NOT pay the restore cost. The
        probe-and-restore composition is gated by ``collect_coverage``;
        bare ``novetest run`` paths stay zero-overhead.

        ``dotnet test`` itself performs an implicit restore when it
        runs, so the user's project still ends up correctly built; we
        just don't FORCE an extra restore from this adapter on the
        non-coverage path where the probe isn't called at all."""

        call_log: list[str] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(call_log=call_log),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_workspace)
        await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=False,
        )
        assert "restore" not in call_log, (
            f"restore invoked on non-coverage path; should be coverage-"
            f"path-only. call_log={call_log!r}"
        )
        assert "list-json" not in call_log
        assert "list-tabular" not in call_log

    async def test_restore_not_invoked_on_xunit_v3_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """xUnit v3 detected + coverage requested → v3 deferral fires
        BEFORE the probe (and therefore before restore). The probe
        path is short-circuited; restore should not happen either."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws, content=(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            '  <ItemGroup>\n'
            '    <PackageReference Include="xunit" Version="3.0.0" />\n'
            '  </ItemGroup>\n'
            '</Project>\n'
        ))
        call_log: list[str] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(call_log=call_log),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        assert "restore" not in call_log, (
            f"restore invoked on xunit v3 path; should short-circuit "
            f"before restore. call_log={call_log!r}"
        )
        assert "list-json" not in call_log

    async def test_restore_failure_tolerated_proceeds_to_probe(
        self,
        dotnet_test_basic_coverage_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-zero exit from ``dotnet restore`` MUST NOT raise. The
        probe still runs (a pre-existing ``obj/`` from a prior run
        may still satisfy it), and if the probe ALSO returns None the
        F1b safety-net surfaces a structured warning."""

        call_log: list[str] = []
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                restore_returncode=1,
                # Probe returns no packages too — exercises the safety-net path.
                coverlet_json=b'{"version":1,"parameters":"","projects":[]}',
                call_log=call_log,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_coverage_workspace)
        # MUST NOT raise even though restore failed.
        result = await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        # Restore was attempted.
        assert "restore" in call_log
        # Probe ran after restore failure (the "pre-existing obj/" tolerance).
        assert "list-json" in call_log
        assert call_log.index("restore") < call_log.index("list-json")
        # F1b safety-net fired (probe also returned None).
        assert result.metadata.get("coverage_unavailable_kind") == (
            "coverlet-absent-or-stale"
        )

    async def test_restore_subprocess_args_match_contract(
        self,
        dotnet_test_basic_coverage_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The captured restore argv MUST be exactly
        ``[dotnet, "restore", <csproj_absolute_path>]``. Tests against
        ad-hoc args (e.g. ``--force``, ``--locked-mode``, etc.) — we
        want the minimal, user-defaults-preserving invocation."""

        captured_restore: list[list[str]] = []
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","resolvedVersion":"6.0.2"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                coverlet_json=json_payload,
                captured_restore=captured_restore,
                seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", dotnet_test_basic_coverage_workspace)
        await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        assert len(captured_restore) == 1, (
            f"expected exactly one restore call; got {captured_restore!r}"
        )
        argv = captured_restore[0]
        assert argv[0] == _FAKE_DOTNET
        assert argv[1] == "restore"
        # The third arg MUST be a path that ends in `.csproj` (the
        # test project's csproj path under workspace). Exact path
        # depends on test_basic_coverage workspace layout; sanity-
        # check shape rather than fix the prefix.
        assert argv[2].endswith(".csproj"), (
            f"third restore arg should be a csproj path; got {argv[2]!r}"
        )
        # No extra args — minimal invocation.
        assert len(argv) == 3, (
            f"restore argv has unexpected extra tokens: {argv!r}"
        )

    async def test_ensure_csproj_restored_direct_invocation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct invocation of the helper MUST call run_subprocess with
        the canonical 3-token argv + 300s timeout. Locking the timeout
        prevents accidental regressions where a short timeout would
        truncate cold-NuGet-cache restores on fresh hosts."""

        captured_args: list[Any] = []
        captured_kwargs: list[dict[str, Any]] = []

        async def capture_stub(
            argv: Any, *, cwd: Any, env: Any | None = None, timeout: float | None = None,
        ) -> SubprocessResult:
            captured_args.append(list(argv))
            captured_kwargs.append({"cwd": cwd, "timeout": timeout})
            return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

        monkeypatch.setattr(adapter, "run_subprocess", capture_stub)
        csproj_path = tmp_path / "Tests" / "Tests.csproj"
        csproj_path.parent.mkdir(parents=True, exist_ok=True)
        csproj_path.write_text("<Project/>")
        await _ensure_csproj_restored(
            "/usr/bin/dotnet", csproj_path, tmp_path
        )
        assert captured_args == [["/usr/bin/dotnet", "restore", str(csproj_path)]]
        assert captured_kwargs[0]["cwd"] == tmp_path
        assert captured_kwargs[0]["timeout"] == 300.0


# ---------------------------------------------------------------------------
# TestEnvelopeSafetyNet (hotfix #1 F1b — 2026-06-06)
# ---------------------------------------------------------------------------


class TestEnvelopeSafetyNet:
    """``metadata["coverage_unavailable_{kind,message}"]`` surfacing for the
    "probe returned None despite --coverage" path.

    Pins the F1b safety-net contract: when restore happens but the
    probe still returns None, the user-visible envelope at
    ``data.memory_entry.run_record.metadata`` MUST carry both the
    ``coverage_unavailable_kind`` (machine-readable) and the
    ``coverage_unavailable_message`` (human-readable). On the happy
    path (Coverlet present + version ≥ floor) BOTH keys MUST be
    absent.

    A formal envelope ``warnings`` projection (top-level
    ``envelope["warnings"]`` field with ``EnvelopeWarning`` shape) is
    deferred to a follow-up cross-team slice — see
    ``agent-comms/questions/run-team-2026-06-06-envelope-warnings-
    projection.md``. The metadata-surface here is the in-charter v1.
    """

    async def test_metadata_carries_coverage_unavailable_when_probe_returns_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Coverage requested + Coverlet truly absent → both metadata
        keys populated with the expected kind and a non-empty message."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws)  # csproj has Coverlet, but stub returns empty
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                coverlet_json=b'{"version":1,"parameters":"","projects":[]}',
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        # Machine-readable kind — pinned literal for AI-consumer parsers.
        assert result.metadata.get("coverage_unavailable_kind") == (
            "coverlet-absent-or-stale"
        )
        # Human-readable message — non-empty, mentions both `--coverage`
        # and `coverlet.collector` so the user can act on it without
        # reading the source.
        message = result.metadata.get("coverage_unavailable_message", "")
        assert message, "coverage_unavailable_message should be non-empty"
        assert "coverlet.collector" in message
        assert "--coverage" in message

    async def test_metadata_omits_coverage_unavailable_when_probe_succeeds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Happy path — Coverlet 6.0.2 present + ≥ floor → BOTH F1b
        keys absent. We do NOT want a no-op safety-net key on the
        successful path (would confuse AI parsers / dashboards
        scanning for the warning)."""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws)
        json_payload = (
            b'{"version":1,"parameters":"","projects":[{"path":"x.csproj",'
            b'"frameworks":[{"framework":"net8.0",'
            b'"topLevelPackages":[{"id":"coverlet.collector","resolvedVersion":"6.0.2"}],'
            b'"transitivePackages":[]}]}]}'
        )
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(
                coverlet_json=json_payload, seed_coverage_xml=True,
            ),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        assert "coverage_unavailable_kind" not in result.metadata
        assert "coverage_unavailable_message" not in result.metadata
        # Sanity — happy path actually populated coverlet_version.
        assert result.metadata.get("coverlet_version") == "6.0.2"

    async def test_metadata_omits_coverage_unavailable_on_non_coverage_path(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-coverage runs MUST NOT carry the F1b safety-net keys.
        The probe path is short-circuited by ``not collect_coverage``,
        so the absence-of-Coverlet path is never reached."""

        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(),
        )
        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(
            target, artifact_dir=tmp_path, timeout=60.0
        )
        assert "coverage_unavailable_kind" not in result.metadata
        assert "coverage_unavailable_message" not in result.metadata

    async def test_metadata_omits_coverage_unavailable_on_xunit_v3_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """xUnit v3 deferral has its OWN payload warning
        (``xunit-v3-coverage-deferred``); the F1b safety-net is for
        the v2-Coverlet-absent path specifically. v3 + --coverage
        MUST not carry coverage_unavailable_* keys.

        (The Run team may later promote the v3 deferral to a separate
        metadata key surface; for now it lives in payload only.)"""

        ws = tmp_path / "ws"
        ws.mkdir()
        _seed_csproj(ws, content=(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            '  <ItemGroup>\n'
            '    <PackageReference Include="xunit" Version="3.0.0" />\n'
            '  </ItemGroup>\n'
            '</Project>\n'
        ))
        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(),
        )
        artifact_dir = tmp_path / "art"
        target = resolve_test_target("", ws)
        result = await run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=60.0,
            collect_coverage=True,
        )
        assert "coverage_unavailable_kind" not in result.metadata
        assert "coverage_unavailable_message" not in result.metadata
        # Sanity — v3 warning IS in payload.
        warnings_kinds = [w["kind"] for w in result.payload["warnings"]]
        assert WARNING_XUNIT_V3_DEFERRED in warnings_kinds


# ---------------------------------------------------------------------------
# Module-level engine name pin
# ---------------------------------------------------------------------------


def test_engine_name_constant() -> None:
    """The ENGINE_NAME literal is pinned because engine_selector,
    normalizer, coverage derive dispatch, and CLI envelope all match on
    it. Changing this string is a breaking contract change."""

    assert ENGINE_NAME == "xunit"


# ---------------------------------------------------------------------------
# artifact_dir.resolve() hardening (2026-06-08, B2-4 cycle)
# ---------------------------------------------------------------------------
#
# `run_xunit` calls ``artifact_dir = artifact_dir.resolve()`` as the
# first line of the function body. See ``test_pytest_adapter.py``'s
# parallel block for the long-form rationale.


class TestArtifactDirResolveHardening:
    async def test_relative_artifact_dir_resolves_against_cwd(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A relative ``artifact_dir`` should resolve against the test's cwd."""

        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(),
        )
        monkeypatch.chdir(tmp_path)
        rel_artifact_dir = Path("rel-art")
        expected_root = (tmp_path / "rel-art").resolve()

        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(target, artifact_dir=rel_artifact_dir, timeout=60.0)

        assert (expected_root / "native").is_dir()
        for key, path in result.artifact_paths.items():
            assert path.is_absolute(), f"{key} → {path} is not absolute"
            assert expected_root in path.parents, (
                f"{key} → {path} is not under {expected_root}"
            )

    async def test_absolute_artifact_dir_unchanged_after_resolve(
        self,
        dotnet_test_basic_workspace: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An absolute ``artifact_dir`` should round-trip through resolve."""

        monkeypatch.setattr(
            adapter, "run_subprocess",
            _make_run_subprocess_stub(),
        )
        abs_artifact_dir = (tmp_path / "abs-art").resolve()
        target = resolve_test_target("", dotnet_test_basic_workspace)
        result = await run_xunit(target, artifact_dir=abs_artifact_dir, timeout=60.0)

        assert (abs_artifact_dir / "native").is_dir()
        for key, path in result.artifact_paths.items():
            assert path.is_absolute(), f"{key} → {path} is not absolute"
            assert abs_artifact_dir in path.parents, (
                f"{key} → {path} is not under {abs_artifact_dir}"
            )
