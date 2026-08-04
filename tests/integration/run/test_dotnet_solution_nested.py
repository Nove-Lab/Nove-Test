"""Integration tests for the solution-rooted (`src/` + `tests/`) layout.

Spawns **real** ``dotnet test`` subprocesses against the
``dotnet-test-solution-nested`` fixture, whose projects sit at depth 2
under a root ``*.sln`` — the layout ``dotnet new sln`` conventions
produce and the one the ``dotnet-expensable`` evaluation seed uses.

The regression this module guards (2026-08-04):
``dotnet_adapter._detect_test_project`` globbed ``*.csproj`` +
``*/*.csproj`` only, so at the solution root it found **no** project.
``novetest init`` answered ``state: "engine-misconfigured"`` and
``novetest test`` exited **4**, on a solution ``dotnet test`` runs
perfectly. Any .NET user with a conventional ``src/`` + ``tests/``
solution hit it on ``init``. Filed as
``agent-comms/questions/run-team-2026-08-04-p7-dotnet-localization-reachability.md``.

Discovery-level unit coverage (solution folders, non-C# project types,
``..``-escape, BOM/CRLF, the sample-project decoy) lives in
``tests/unit/run/adapters/test_dotnet_adapter.py::TestSolutionLayoutDiscovery``
and needs no toolchain. What can ONLY be proven here is that the csproj
discovery picks really is runnable: that ``dotnet test`` accepts the
depth-2 project path from the solution root as cwd, and that the CLI
walks init → run → envelope end to end on it.

Skip-gates on ``shutil.which("dotnet")`` so unequipped CI stays green.
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
    ENGINE_NAME,
    WARNING_AMBIGUOUS_PROJECT,
    run_xunit,
)
from novetest.run.readiness import probe_engine
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "dotnet-test-solution-nested"
)


def _require_dotnet() -> None:
    if shutil.which("dotnet") is None:
        pytest.skip("requires `dotnet` on PATH (see scripts/dev-host-setup.md §6)")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Copy the fixture into ``tmp_path`` so ``bin/`` / ``obj/`` /
    ``TestResults/`` never land in the repo."""

    dest = tmp_path / "dotnet-test-solution-nested"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


async def test_readiness_at_the_solution_root_is_ready(workspace: Path) -> None:
    """THE `novetest init` regression, against a real ``dotnet``.

    Pre-fix: ``engine-misconfigured``, issue ".NET workspace markers
    detected but no *.csproj found…"."""

    _require_dotnet()

    result = await asyncio.wait_for(
        probe_engine(workspace, "dotnet", "xunit"), timeout=120.0
    )

    assert result.state == "ready", (
        f"readiness at the solution root is {result.state!r}: {result.issues!r}"
    )
    assert result.engine_context is not None
    assert result.engine_context.engine_name == "xunit"
    # The `.sln` is the marker that got the workspace detected at all —
    # and now also the file discovery reads to find the projects.
    assert "nested.sln" in result.evidence


async def test_nested_run_emits_native_result(
    workspace: Path, tmp_path: Path
) -> None:
    """Real-``dotnet test`` from the SOLUTION ROOT as cwd, against a
    csproj two levels down. Same 3-test contract as the flat sibling."""

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
    assert result.returncode == 1  # 1 intentionally-failing test

    payload = result.payload
    # The depth-2 project is what ran — recorded workspace-relative.
    assert payload["csproj"] == str(
        Path("tests") / "MathLib.Tests" / "MathLib.Tests.csproj"
    )

    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1

    tests = payload["tests"]
    assert isinstance(tests, list)
    identities = {t["identity"] for t in tests}  # type: ignore[index]
    assert "MathLib.Tests.MathTests.TestAddPasses" in identities
    assert "MathLib.Tests.MathTests.TestSubtractIntentionallyFails" in identities

    # The decoy never ran: `samples/TestBed` has no tests, so if it had
    # been selected this suite would be empty (or the run would have
    # failed outright).
    assert summary["total"] == 3, "the sample project was selected, not the tests"

    for key, path in result.artifact_paths.items():
        assert path.is_relative_to(artifact_dir), (
            f"{key!r} path {path} is not under artifact_dir {artifact_dir}"
        )


async def test_ambiguity_warning_names_the_nested_paths(
    workspace: Path, tmp_path: Path
) -> None:
    """A solution present ⇒ ``ambiguous-project-layout`` (novetest runs
    ONE project of the several a solution builds).

    Candidates must be reported as workspace-relative POSIX paths: with
    solution walking, two projects can share a basename at different
    depths and a bare filename would make them indistinguishable in the
    envelope."""

    _require_dotnet()

    target = resolve_test_target("", workspace)
    result = await asyncio.wait_for(
        run_xunit(target, artifact_dir=tmp_path / "art", timeout=300.0),
        timeout=400.0,
    )

    warning = next(
        (w for w in result.warnings if w.code == WARNING_AMBIGUOUS_PROJECT), None
    )
    assert warning is not None, (
        f"expected an {WARNING_AMBIGUOUS_PROJECT} warning; got "
        f"{[w.code for w in result.warnings]!r}"
    )
    assert warning.details["chosen_csproj"] == (
        "tests/MathLib.Tests/MathLib.Tests.csproj"
    )
    assert sorted(warning.details["csproj_candidates"]) == [
        "samples/TestBed/TestBed.csproj",
        "src/MathLib/MathLib.csproj",
        "tests/MathLib.Tests/MathLib.Tests.csproj",
    ]
    assert warning.details["sln_files"] == ["nested.sln"]
    # The message used to claim an alphabetical pick, which was never the
    # rule and is emphatically not the rule now.
    assert "alphabetically" not in warning.message


# ---------------------------------------------------------------------------
# CLI-level smoke (equip-and-exercise §2)
# ---------------------------------------------------------------------------


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


def test_cli_smoke_init_then_test_at_the_solution_root(workspace: Path) -> None:
    """The user-visible reproducer, end to end: ``novetest init`` reaches
    ``ready`` at the SOLUTION ROOT (not from inside ``tests/``) and
    ``novetest test .`` exits 3 with the fixture's known failure.

    Pre-fix this pair was ``engine-misconfigured`` + exit **4**."""

    _require_dotnet()

    init_result = _spawn_novetest(workspace, ["init"], timeout=120.0)
    assert init_result.returncode == 0, (
        f"`novetest init` failed: stdout={init_result.stdout!r} "
        f"stderr={init_result.stderr!r}"
    )
    init_envelope = json.loads(init_result.stdout)
    readiness = init_envelope["data"]["engine_readiness"]
    assert readiness["state"] == "ready", (
        f"init at the solution root reported {readiness['state']!r}: "
        f"{readiness.get('issues')!r}"
    )
    assert init_envelope["data"]["pinned_engine"]["engine_name"] == "xunit"

    test_result = _spawn_novetest(workspace, ["test", "."], timeout=600.0)
    assert test_result.returncode == 3, (
        f"expected exit 3 (EXIT_USER_TESTS_FAILED) on a fixture with one "
        f"intentionally-failing test; got {test_result.returncode}. Exit 4 "
        f"is the pre-fix engine-misconfigured signature. "
        f"stdout={test_result.stdout!r} stderr={test_result.stderr!r}"
    )
    envelope = json.loads(test_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert not any(
        error["code"] == "engine-misconfigured"
        for error in envelope["errors"]
    ), f"engine-misconfigured survived: {envelope['errors']!r}"
