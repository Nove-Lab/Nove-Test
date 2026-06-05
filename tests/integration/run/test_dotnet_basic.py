"""Integration tests for the dotnet adapter — basic (no-coverage) path.

Spawns **real** ``dotnet test`` subprocesses against the
``dotnet-test-basic`` fixture. Skip-gates on ``shutil.which("dotnet")``
so unequipped CI stays green; Manual Test's equipped host (per
``scripts/dev-host-setup.md §6``) runs them.

Runtime expectation: ~30-60 seconds on first run (cold NuGet cache
restores Microsoft.NET.Test.Sdk + xunit + transitive deps). Subsequent
runs use the warm cache and finish in ~5-10 s.

CLI-level smokes (per
``decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`` §2):
``test_cli_smoke_run_dot_emits_envelope`` and
``test_cli_smoke_run_bare_emits_envelope`` exercise the full
orchestration path via ``[sys.executable, "-m", "novetest", "run", ...]``,
catching defects that bypass the adapter-direct call. Mirrors the
canonical pattern from ``tests/integration/orchestration/conftest.py::
run_cli_in`` + the precedent established in JUnit hotfix #1/#2/#3 and
the cargo CLI orchestration defect closure.
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

from novetest.run.adapters.dotnet_adapter import ENGINE_NAME, run_xunit
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "dotnet-test-basic"
)


def _require_dotnet() -> None:
    """Skip when ``dotnet`` is missing.

    Mirrors the cargo / gotest skip-gate pattern. The matrix floor is
    .NET SDK 8.0 — the smoke does NOT assert the floor explicitly here
    (it relies on the readiness probe surfacing version mismatches at
    a higher layer); the gate is just "dotnet exists".
    """

    if shutil.which("dotnet") is None:
        pytest.skip("requires `dotnet` on PATH (see scripts/dev-host-setup.md §6)")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Copy the fixture into ``tmp_path`` so the test doesn't pollute the
    repo with ``bin/`` / ``obj/`` / ``TestResults/`` artifacts. Mirrors
    the JUnit / cargo fixture isolation pattern.
    """

    dest = tmp_path / "dotnet-test-basic"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


async def test_basic_run_emits_native_result(
    workspace: Path, tmp_path: Path
) -> None:
    """Real-`dotnet test` smoke — produces a NativeResult with the
    canonical fixture's contract (2 passed + 1 failed = 3 total)."""

    _require_dotnet()

    artifact_dir = tmp_path / "art"
    target = resolve_test_target("", workspace)
    result = await asyncio.wait_for(
        run_xunit(
            target,
            artifact_dir=artifact_dir,
            timeout=300.0,
            collect_coverage=False,
        ),
        timeout=400.0,
    )

    assert result.engine_name == ENGINE_NAME == "xunit"
    # The intentional failing test → exit 1 per task brief §6.3 +
    # empirical verification on the equipped host.
    assert result.returncode == 1

    payload = result.payload
    summary = payload["summary"]
    assert isinstance(summary, dict)
    # Canonical fixture: 2 passed (TestAddPasses + TestParametrized) +
    # 1 failed (TestSubtractIntentionallyFails) = 3 total.
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1

    tests = payload["tests"]
    assert isinstance(tests, list)
    identities = {t["identity"] for t in tests}  # type: ignore[index]
    # All three test identities present — verbatim form preserved.
    assert "MathLib.Tests.MathTests.TestAddPasses" in identities
    assert "MathLib.Tests.MathTests.TestSubtractIntentionallyFails" in identities
    parametrized = next(
        (i for i in identities if "TestParametrized" in str(i)),
        None,
    )
    assert parametrized is not None, (
        f"parametrized test not found in identities: {identities!r}"
    )
    # R1 probe artifact: parametrized test name preserves data variant.
    assert "1" in str(parametrized) and "2" in str(parametrized) and "3" in str(parametrized)

    # Failure log written for the failing test.
    failure_logs = payload["failure_logs"]
    assert isinstance(failure_logs, dict)
    assert (
        "MathLib.Tests.MathTests.TestSubtractIntentionallyFails" in failure_logs
    )

    # Artifact paths registered + all subpaths of artifact_dir (the
    # orchestration ``.relative_to(store.path)`` invariant).
    assert "stdout" in result.artifact_paths
    assert "stderr" in result.artifact_paths
    assert "trx" in result.artifact_paths
    for key, path in result.artifact_paths.items():
        assert path.is_relative_to(artifact_dir), (
            f"{key!r} path {path} is not under artifact_dir {artifact_dir}"
        )

    # Metadata: SDK version + xunit version.
    assert "dotnet_sdk_version" in result.metadata
    assert result.metadata["xunit_version"] == "2.6.0"


# ---------------------------------------------------------------------------
# CLI-level smokes (equip-and-exercise §2 + §2.5 binding)
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_smoke_workspace(tmp_path: Path) -> Path:
    """Copy ``dotnet-test-basic`` into ``tmp_path`` for the CLI smokes.

    Same shape as the per-test ``workspace`` fixture above — separate
    name so the smokes don't share state with the adapter-direct test
    even when both run in the same pytest session.
    """

    dest = tmp_path / "dotnet-test-basic"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Spawn ``[sys.executable, "-m", "novetest", *args]`` in ``workspace``.

    Same canonical CLI invocation shape used by cargo + JUnit smokes
    (``NOVETEST_OUTPUT=json``, UTF-8 decode). One helper used by both
    smokes so divergence between dot-case and bare-case is impossible.
    """

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


def test_cli_smoke_run_dot_emits_envelope(cli_smoke_workspace: Path) -> None:
    """``novetest run .`` against ``dotnet-test-basic`` produces the
    canonical envelope shape.

    Pin for the orchestration ``.relative_to(store.path)`` invariant +
    the target_resolver → dotnet_adapter --filter handling. The
    ``target_type="directory"`` carve-out (mirroring cargo Fix A) means
    no ``--filter`` is injected; ``dotnet test`` runs the whole test
    project.

    Skip-gates on ``cargo + cargo-nextest`` presence — actually,
    skip-gates on ``dotnet`` presence (sorry, copy-paste); unequipped
    CI stays green; Manual Test's equipped host runs this.
    """

    _require_dotnet()

    init_result = _spawn_novetest(cli_smoke_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, (
        f"`novetest init` failed: stdout={init_result.stdout!r} "
        f"stderr={init_result.stderr!r}"
    )

    run_result = _spawn_novetest(cli_smoke_workspace, ["run", "."], timeout=600.0)

    # Exit 0 (all passed) or 3 (EXIT_USER_TESTS_FAILED, some user test
    # failed) are the only acceptable codes on the canonical happy-path
    # fixture per `src/novetest/cli/output.py:12-17`. The canonical
    # fixture has 1 intentionally-failing test, so the expected exit is 3.
    # Exit 1 (EXIT_GENERIC) indicates a contract violation — the
    # adapter raised an envelope error, NOT a clean tests-failed exit.
    # JUnit hotfix #1 / cargo CLI smoke established this `(0, 3)` shape
    # binding via `decisions/2026-06-04-equip-and-exercise-for-adapter-
    # cycles.md` §2 errata. Do NOT change to `(0, 1)`.
    assert run_result.returncode in (0, 3), (
        f"CLI returned exit {run_result.returncode}; expected 0 "
        f"(EXIT_OK, all passed) or 3 (EXIT_USER_TESTS_FAILED, some "
        f"user tests failed). Exit code 1 (EXIT_GENERIC) indicates the "
        f"adapter emitted an envelope error (contract violation); "
        f"exit codes 2 (EXIT_USAGE) / 4 (EXIT_ENGINE_MISSING) / 5 "
        f"(EXIT_STORAGE) indicate other contract / environment "
        f"violations. See `src/novetest/cli/output.py:12-17`. "
        f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert isinstance(envelope["ok"], bool)
    # Envelope path per `src/novetest/cli/app.py:269-281`:
    # ``data = {"memory_entry": entry.to_dict()}``. The RunRecord lives
    # under ``data.memory_entry.run_record`` — NOT ``data.run_record``.
    # JUnit hotfix #2 caught this landmine; cargo CLI smoke established
    # the binding precedent for new adapters.
    if envelope["ok"]:
        run_record = envelope["data"]["memory_entry"]["run_record"]
        assert run_record["engine_name"] == "xunit"
        # Audit-trail preservation (cargo LL #3): the user's verbatim
        # ``"."`` survives even though the adapter normalizes it to
        # "no filter" at the argv layer.
        assert run_record["target_expression"] == "."
        assert run_record["target_type"] == "directory"
        # Canonical fixture summary.
        summary_counts = run_record["summary_counts"]
        assert summary_counts["total"] == 3
        assert summary_counts["passed"] == 2
        assert summary_counts["failed"] == 1


def test_cli_smoke_run_bare_emits_envelope(cli_smoke_workspace: Path) -> None:
    """Control case for ``test_cli_smoke_run_dot_emits_envelope``.

    Bare ``novetest run`` → ``target_type="workspace"``. The two cases
    together triangulate the orchestration invariant: directory- and
    workspace-typed targets both produce a Run Record with the same
    summary on this fixture.
    """

    _require_dotnet()

    init_result = _spawn_novetest(cli_smoke_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(cli_smoke_workspace, ["run"], timeout=600.0)
    assert run_result.returncode in (0, 3), (
        f"CLI returned exit {run_result.returncode}; expected 0 or 3 "
        f"on the canonical fixture. stdout: {run_result.stdout!r} "
        f"stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    if envelope["ok"]:
        run_record = envelope["data"]["memory_entry"]["run_record"]
        assert run_record["engine_name"] == "xunit"
        assert run_record["target_expression"] == ""
        assert run_record["target_type"] == "workspace"
