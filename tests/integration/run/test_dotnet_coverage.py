"""Integration tests for the dotnet adapter's coverage path.

Spawns a **real** ``dotnet test --collect:"XPlat Code Coverage"
--settings <runsettings>`` subprocess against the
``dotnet-test-basic-coverage`` fixture (which pins Coverlet 6.0.2
explicitly). Skip-gates on ``shutil.which("dotnet")`` AND a brief
``dotnet --version`` probe that confirms the SDK is reachable; same
posture as the basic-path integration test.

Empirical finding (2026-06-05; documented in
``agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-
empirically-inert.md``): ``<PerTestCoverage>true</PerTestCoverage>``
in the XPlat data collector path is inert on Coverlet 6.0.x — only
the aggregate ``coverage.cobertura.xml`` is emitted. The adapter
falls back to aggregate-mode glob automatically and the test asserts
the fallback path.

R1 probe per ``decisions/2026-06-03-coverlet-pertestcoverage-key.md``
§R1: the parametrized fixture test exercises the slug-correlation
shape. With per-test glob returning zero files today, R1 collapses to
"aggregate emits valid Cobertura with non-zero ``lines-covered``"; if
a future Coverlet release fixes the XPlat path, the per-test assertion
auto-promotes via ``_glob_coverage_xml``.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.dotnet_adapter import run_xunit
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "dotnet-test-basic-coverage"
)


def _require_dotnet() -> None:
    if shutil.which("dotnet") is None:
        pytest.skip("requires `dotnet` on PATH (see scripts/dev-host-setup.md §6)")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    dest = tmp_path / "dotnet-test-basic-coverage"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


async def test_coverage_run_emits_cobertura_xml(
    workspace: Path, tmp_path: Path
) -> None:
    """Real `dotnet test --collect XPlat Code Coverage` produces a
    valid Cobertura XML under ``artifact_dir/native/TestResults/.../
    coverage.cobertura.xml`` with non-zero ``lines-covered``."""

    _require_dotnet()

    artifact_dir = tmp_path / "art"
    target = resolve_test_target("", workspace)
    result = await asyncio.wait_for(
        run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=400.0,
            collect_coverage=True,
        ),
        timeout=500.0,
    )

    # Coverlet 6.0.2 detected from the fixture's PackageReference.
    assert result.payload["coverlet_version"] == "6.0.2"

    # coverage_xml artifact registered. Empirically aggregate-only on
    # Coverlet 6.0.x — the `coverage_mapping_granularity` metadata
    # reflects the actually-realized mode (not the requested mode).
    assert "coverage_xml" in result.artifact_paths
    coverage_path = result.artifact_paths["coverage_xml"]
    assert coverage_path.is_file(), (
        f"coverage_xml is not a file: {coverage_path}; "
        f"expected aggregate-mode behavior — see "
        f"agent-comms/questions/run-team-2026-06-05-coverlet-"
        f"pertestcoverage-empirically-inert.md"
    )
    assert coverage_path.is_relative_to(artifact_dir), (
        f"coverage_xml {coverage_path} not under artifact_dir "
        f"{artifact_dir} — orchestration `.relative_to(store.path)` "
        f"invariant would fail"
    )

    # Valid Cobertura with measurable coverage.
    coverage_text = coverage_path.read_text(encoding="utf-8")
    assert "<coverage " in coverage_text
    # ``MathOps`` lines (``Add`` and ``Subtract``) were exercised by
    # the test methods. `lines-covered="2"` is the canonical equipped-
    # host observation; tolerate ``lines-covered="0"`` only if a future
    # Coverlet release fundamentally changes the format (which would
    # be a separate issue worth its own slice).
    assert 'lines-covered="' in coverage_text
    # Carve out the lines-covered count.
    import re
    match = re.search(r'lines-covered="(\d+)"', coverage_text)
    assert match is not None
    lines_covered = int(match.group(1))
    assert lines_covered >= 2, (
        f"expected ≥2 lines-covered (MathOps.Add + Subtract); got "
        f"{lines_covered}. Coverage XML:\n{coverage_text[:500]}"
    )

    # metadata.coverage_mapping_granularity reflects the realized mode.
    granularity = result.metadata.get("coverage_mapping_granularity")
    assert granularity in ("aggregate", "per-test"), (
        f"unexpected granularity: {granularity!r}"
    )

    # R1 probe outcome: with Coverlet 6.0.x XPlat path producing no
    # per-test files, granularity is `aggregate` today. If a future
    # Coverlet release emits per-test files, the glob auto-detects
    # them and granularity promotes to `per-test` automatically.
    # The test passes either way.


async def test_coverage_runsettings_landed_under_artifact_dir(
    workspace: Path, tmp_path: Path
) -> None:
    """The hermetic per-run runsettings MUST land at
    ``<artifact_dir>/native/coverlet.runsettings`` so postmortem
    inspection finds it next to stdout.log / stderr.log / TRX."""

    _require_dotnet()

    artifact_dir = tmp_path / "art"
    target = resolve_test_target("", workspace)
    result = await asyncio.wait_for(
        run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=400.0,
            collect_coverage=True,
        ),
        timeout=500.0,
    )
    assert "runsettings" in result.artifact_paths
    runsettings_path = result.artifact_paths["runsettings"]
    assert runsettings_path.name == "coverlet.runsettings"
    assert runsettings_path.is_relative_to(artifact_dir)
    assert runsettings_path.parent.name == "native"
    # Decision §1.1 verbatim content.
    text = runsettings_path.read_text(encoding="utf-8")
    assert '<PerTestCoverage>true</PerTestCoverage>' in text
    assert '<SingleHit>false</SingleHit>' in text
    assert 'friendlyName="XPlat Code Coverage"' in text


async def test_coverage_run_on_fresh_fixture_with_no_prior_restore(
    tmp_path: Path,
) -> None:
    """Hotfix #1 F1c (2026-06-06) — explicit pin of the D1 reproducer.

    Manual Test 2026-06-05 caught a verdict-blocking defect: the
    adapter's ``_probe_coverlet_version`` ran
    ``dotnet list <csproj> package --include-transitive --format json``
    BEFORE ``dotnet test``. That command requires
    ``obj/project.assets.json`` (a ``dotnet restore`` artifact), which a
    freshly-copied user project does NOT have. The probe returned None,
    the adapter treated Coverlet as absent, and ``novetest run
    --coverage`` silently degraded to a no-coverage run.

    The fix (F1a, ``_ensure_csproj_restored`` before the probe) closes
    the gap. This test pins it explicitly by:

    1. Copying the fixture into a per-test ``tmp_path`` (guaranteed
       fresh by pytest's per-function scope).
    2. Asserting **no ``obj/``** exists under the copied workspace
       pre-test. This is the precondition the pre-hotfix adapter
       failed under — making it explicit guards against future
       fixture pollution that would mask the regression.
    3. Running ``run_xunit`` with ``collect_coverage=True``.
    4. Asserting ``payload["coverlet_version"] == "6.0.2"`` (the
       fixture's pinned version). Pre-hotfix: this fails with
       ``coverlet_version is None``. Post-hotfix: passes.
    5. Asserting NO ``coverage_unavailable_*`` metadata keys (F1b
       safety-net is the inverse of the happy path).
    6. Asserting the cobertura XML is on disk under
       ``<artifact_dir>/native/...``.

    Per Manual Test findings §"Why Main Branch's gate didn't see this":
    the mystery is some external NuGet / packages-cache state on Main
    Branch's host that incidentally satisfied the probe without
    restore. THIS test forces the fresh state explicitly so the
    regression cannot mask itself again — both Run team's gate and
    Main Branch's gate must execute it on a truly-fresh workspace.

    Audit of the other two coverage tests
    (``test_coverage_run_emits_cobertura_xml`` +
    ``test_coverage_runsettings_landed_under_artifact_dir``): both use
    a module-level ``workspace`` fixture that ``shutil.copytree``s
    ``FIXTURE_ROOT`` into ``tmp_path`` per test. The fixture source
    (``tests/fixtures/projects/dotnet-test-basic-coverage/``) is
    git-clean and ``.gitignore``-protected against ``obj/`` / ``bin/``
    pollution. The two existing tests would therefore ALSO have failed
    on Manual Test's reproducer if they ran. The hypothesis disposition
    (H1/H2/H3 in the brief §5): H2 (pre-committed obj/) is REJECTED —
    fixture source verified clean. H1 (cross-test pollution) is
    REJECTED — both tests use per-function ``tmp_path``. H3 (external
    NuGet config / packages cache state on Main Branch's host) is the
    most plausible standing hypothesis; F1a closes the dependency
    regardless of its origin.
    """

    _require_dotnet()

    workspace = tmp_path / "dotnet-test-basic-coverage"
    shutil.copytree(FIXTURE_ROOT, workspace)

    # Explicit fresh-state pin: obj/ MUST NOT exist before run_xunit.
    # This is the precondition the pre-hotfix adapter failed under.
    obj_dir = workspace / "MathLib.Tests" / "obj"
    assert not obj_dir.exists(), (
        f"fixture source pollution: {obj_dir} exists in the freshly-"
        f"copied workspace. The fixture source must be git-clean — "
        f"check tests/fixtures/projects/dotnet-test-basic-coverage/ "
        f"for stray bin/, obj/, TestResults/ directories."
    )

    artifact_dir = tmp_path / "art"
    target = resolve_test_target("", workspace)
    result = await asyncio.wait_for(
        run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=400.0,
            collect_coverage=True,
        ),
        timeout=500.0,
    )

    # Post-hotfix: Coverlet probe succeeds because adapter ran
    # `dotnet restore` BEFORE the probe.
    # Pre-hotfix: this assertion FAILS with `coverlet_version is None`
    # — that is the exact D1 reproducer.
    assert result.payload["coverlet_version"] == "6.0.2", (
        f"Coverlet version not detected on freshly-copied fixture; "
        f"D1 reproducer regressed. payload['coverlet_version']="
        f"{result.payload['coverlet_version']!r}. The adapter's "
        f"`dotnet restore` call before the probe should have "
        f"produced obj/project.assets.json — check the stderr.log "
        f"artifact for restore failures."
    )

    # F1b safety-net metadata MUST be absent — Coverlet IS present.
    assert "coverage_unavailable_kind" not in result.metadata, (
        f"coverage_unavailable_kind set despite successful probe: "
        f"{result.metadata.get('coverage_unavailable_kind')!r}. "
        f"The F1b safety-net should only fire when the probe returns "
        f"None after restore."
    )
    assert "coverage_unavailable_message" not in result.metadata

    # Cobertura artifact registered under artifact_dir (the
    # orchestration `.relative_to(store.path)` invariant).
    assert "coverage_xml" in result.artifact_paths, (
        f"coverage_xml artifact missing despite Coverlet detected; "
        f"artifact_paths keys: {list(result.artifact_paths.keys())!r}"
    )
    coverage_path = result.artifact_paths["coverage_xml"]
    assert coverage_path.is_file(), (
        f"coverage_xml is not a file: {coverage_path}. Coverlet 6.0.x "
        f"on XPlat path produces aggregate coverage.cobertura.xml — "
        f"see agent-comms/questions/run-team-2026-06-05-coverlet-"
        f"pertestcoverage-empirically-inert.md"
    )
    assert coverage_path.is_relative_to(artifact_dir)

    # Now obj/ SHOULD exist (proof that restore actually ran).
    assert obj_dir.exists(), (
        f"obj/ directory not materialized post-run; restore may not "
        f"have actually run. dotnet restore should produce {obj_dir}/"
        f"project.assets.json."
    )
