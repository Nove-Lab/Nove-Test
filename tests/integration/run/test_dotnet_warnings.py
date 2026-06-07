"""Integration tests for the dotnet adapter's envelope-warnings projection.

Covers the two adapter-emitted warning kinds catalogued in
``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``
§"What MUST be retroactively projected to envelope top-level":

| Kind | Trigger |
|---|---|
| ``engine-misconfigured`` (canonical: ``coverage-requested-but-coverlet-absent``) | ``dotnet-test-basic`` fixture (no coverlet) + ``--coverage`` |
| ``xunit-v3-coverage-deferred`` | csproj declaring ``<PackageReference Include="xunit" Version="3.*" />`` + ``--coverage`` |

Per the 2026-06-06 envelope-warnings-projection slice (brief §1.2), each
test invokes the actual CLI subprocess against a copied + mutated
fixture and asserts:

1. ``envelope.warnings`` contains a record with the expected ``code``
2. The warning has a non-empty ``message``
3. The v1 metadata-channel keys (where applicable) are STILL populated
   per backward-compat criterion #2 of the decision

xUnit v3 deferral is exercised through the **adapter-direct + stubbed
subprocess** path rather than a CLI subprocess; xUnit v3 requires
Microsoft.Testing.Platform and the published ``xunit`` 3.x NuGet name
differs from the v2 package, so a CLI smoke would fail at
``dotnet restore`` and never reach the warning-projection assertion.
The adapter-direct test exercises the same warning-emit path because
the warning fires from csproj-string detection BEFORE any subprocess
runs. Documented deviation from brief §1.2's "CLI subprocess" mandate.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.run.adapters.dotnet_adapter import (
    WARNING_COVERLET_ABSENT,
    WARNING_XUNIT_V3_DEFERRED,
    run_xunit,
)
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _require_dotnet() -> None:
    if shutil.which("dotnet") is None:
        pytest.skip("requires `dotnet` on PATH (see scripts/dev-host-setup.md §6)")


@pytest.fixture
def coverage_absent_workspace(tmp_path: Path) -> Path:
    """Copy ``dotnet-test-basic`` (no ``coverlet.collector``) into ``tmp_path``.

    The base fixture's csproj declares no coverage tooling, so running
    ``novetest run --coverage`` against it triggers the
    ``engine-misconfigured`` /
    ``coverage-requested-but-coverlet-absent`` warning. Tests using this
    fixture stay isolated — they get a per-test copy so the source
    fixture's git state stays clean.
    """

    dest = tmp_path / "dotnet-test-basic"
    shutil.copytree(FIXTURE_ROOT / "dotnet-test-basic", dest)
    return dest


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    return subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def test_cli_smoke_coverage_absent_emits_envelope_warning(
    coverage_absent_workspace: Path,
) -> None:
    """``novetest run --coverage`` against a no-coverlet fixture surfaces the
    ``engine-misconfigured`` warning at ``envelope.warnings[]`` AND keeps the
    v1 metadata-channel bridge populated.

    Backward-compat criterion #2 of the 2026-06-06 decision is the load-
    bearing assertion: the legacy
    ``data.memory_entry.run_record.metadata.coverage_unavailable_kind``
    + ``..._message`` pair MUST still be present alongside the new
    ``envelope.warnings[]`` entry for one release cycle.
    """

    _require_dotnet()

    init_result = _spawn_novetest(
        coverage_absent_workspace, ["init"], timeout=60.0
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(
        coverage_absent_workspace, ["run", "--coverage"], timeout=600.0
    )
    # Canonical fixture has 1 intentionally-failing test → exit 3.
    assert run_result.returncode in (0, 3), (
        f"unexpected exit {run_result.returncode}; "
        f"stdout={run_result.stdout!r} stderr={run_result.stderr!r}"
    )

    envelope = json.loads(run_result.stdout)
    warnings_block = envelope.get("warnings", [])
    assert isinstance(warnings_block, list)

    # Find the coverage-absent warning by ``code`` (== adapter's
    # WARNING_COVERLET_ABSENT literal which is "engine-misconfigured").
    matching = [w for w in warnings_block if w.get("code") == WARNING_COVERLET_ABSENT]
    assert matching, (
        f"expected at least one envelope warning with code="
        f"{WARNING_COVERLET_ABSENT!r}; got warnings={warnings_block!r}"
    )
    coverage_warning = matching[0]
    # Non-empty message + actionable hint per the v1 catalog.
    assert coverage_warning.get("message")
    assert "coverlet.collector" in coverage_warning["message"]
    assert "PackageReference" in coverage_warning["message"]

    # Backward-compat criterion #2: the v1 metadata-channel bridge MUST
    # still populate alongside the new envelope.warnings[] projection.
    run_record = envelope["data"]["memory_entry"]["run_record"]
    metadata = run_record["metadata"]
    assert metadata.get("coverage_unavailable_kind") == "coverlet-absent-or-stale"
    assert metadata.get("coverage_unavailable_message")
    assert "coverlet.collector" in metadata["coverage_unavailable_message"]


async def test_xunit_v3_deferral_emits_envelope_warning_via_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xUnit v3 detection surfaces ``xunit-v3-coverage-deferred`` on
    ``NativeResult.warnings`` (which the orchestration → CLI projection
    lifts to ``envelope.warnings[]``).

    **Adapter-direct test by design** — see module docstring for the
    deviation rationale. The warning emit fires from csproj-string
    detection BEFORE any subprocess runs, so we mock ``run_subprocess``
    to return a stable TRX payload + zero-exit and assert the warning
    on the resulting ``NativeResult``.

    The integration boundary tested here is: real fixture → real
    adapter logic → real csproj parsing → real warning-emit + lift
    onto ``NativeResult.warnings``. The CLI-subprocess boundary is
    deferred to the unit-tested ``_adapter_to_envelope_warnings``
    helper which performs the field-by-field projection.
    """

    # Set up an xUnit v3 csproj by copying the basic fixture and
    # mutating the version. The fixture's test code doesn't compile
    # under v3 (different APIs) but the adapter never reaches the
    # subprocess invocation thanks to the stub below.
    workspace = tmp_path / "dotnet-test-xunit-v3"
    shutil.copytree(FIXTURE_ROOT / "dotnet-test-basic", workspace)
    csproj_path = workspace / "MathLib.Tests" / "MathLib.Tests.csproj"
    original = csproj_path.read_text(encoding="utf-8")
    mutated = original.replace(
        'Include="xunit" Version="2.6.0"',
        'Include="xunit" Version="3.0.0"',
    )
    assert mutated != original, (
        "csproj mutation failed — xunit 2.6.0 version pin not found"
    )
    csproj_path.write_text(mutated, encoding="utf-8")

    # Stub the subprocess seam at the adapter so we don't actually
    # invoke ``dotnet test`` (which would fail on the mutated v3
    # fixture without Microsoft.Testing.Platform infrastructure).
    from novetest.run.adapters import dotnet_adapter

    class _StubResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = b""
            self.stderr = b""
            self.timed_out = False

    async def stub_run_subprocess(*args: object, **kwargs: object) -> _StubResult:
        # The adapter probes ``dotnet --version`` first, then the
        # ``dotnet test`` invocation. Return zero exit + empty
        # streams for both — the TRX-glob branch handles the
        # no-TRX path via the result.returncode == 0 check (no
        # TRX + zero exit → no exception, just empty test list).
        argv = args[0] if args else []
        if isinstance(argv, list) and len(argv) >= 2 and argv[1] == "--version":
            stub = _StubResult()
            stub.stdout = b"8.0.421\n"
            return stub
        return _StubResult()

    monkeypatch.setattr(dotnet_adapter, "run_subprocess", stub_run_subprocess)

    target = resolve_test_target("", workspace)
    artifact_dir = tmp_path / "art"
    result = await asyncio.wait_for(
        run_xunit(target, artifact_dir=artifact_dir, timeout=60.0, collect_coverage=True),
        timeout=60.0,
    )

    # The adapter detected xunit v3 → emitted both the legacy
    # payload-warning AND the envelope-bound AdapterWarning. Verify
    # both surface for backward-compat (criterion #2).
    warnings = result.warnings
    matching = [w for w in warnings if w.code == WARNING_XUNIT_V3_DEFERRED]
    assert matching, (
        f"expected at least one AdapterWarning with code="
        f"{WARNING_XUNIT_V3_DEFERRED!r}; got warnings="
        f"{[(w.code, w.message) for w in warnings]!r}"
    )
    v3_warning = matching[0]
    assert v3_warning.message
    assert "xUnit v3" in v3_warning.message
    assert v3_warning.details.get("xunit_major_version") == 3

    # Backward-compat criterion #2: legacy payload["warnings"] still
    # populated. xunit-v3 doesn't use the metadata bridge (it's a
    # deferral, not a coverage_unavailable_kind path) — but the
    # payload bridge stays.
    payload_warnings = result.payload.get("warnings", [])
    assert isinstance(payload_warnings, list)
    legacy_matching = [
        w for w in payload_warnings
        if isinstance(w, dict) and w.get("kind") == WARNING_XUNIT_V3_DEFERRED
    ]
    assert legacy_matching, (
        f"expected legacy payload['warnings'] entry with kind="
        f"{WARNING_XUNIT_V3_DEFERRED!r}; got payload['warnings']="
        f"{payload_warnings!r}"
    )
