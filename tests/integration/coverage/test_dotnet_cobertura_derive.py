"""End-to-end: dotnet (.NET / xUnit v2 + Coverlet) ``--coverage`` →
Coverage engine derives facts from Cobertura XML.

Closes the 6th-engine promise from Phase 2/3 (per
``agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md``
§"Load-bearing lessons" 6). Before this slice, ``dotnet test
--coverage`` left ``coverage_outcome.kind = "unavailable"`` even with a
fully-populated Cobertura XML at
``artifact_paths["coverage_xml"]`` because the Coverage engine had no
Cobertura derive path — only a JaCoCo one. After this slice, the same
run path produces a real ``CoverageFactSet`` (engine="xunit",
mapping_granularity="aggregate") and ``coverage_outcome.kind`` flips to
``"fact-set"``; downstream ``coverage show`` / ``coverage diff`` /
``inspect`` populate the Coverage section.

This test spawns a **real** ``dotnet test --collect:"XPlat Code
Coverage" --settings <runsettings>`` subprocess against the
``dotnet-test-basic-coverage`` fixture (pins Coverlet 6.0.2). Skip-gates
on ``shutil.which("dotnet")`` — same posture as
``tests/integration/run/test_dotnet_coverage.py``. The §2.5
equip-and-exercise binding gate (per decision
``2026-06-04-equip-and-exercise-for-adapter-cycles.md``) requires this
test to actually EXECUTE (not skip) on the originating team's
pre-handoff host AND on Main Branch's pre-merge host.

R1 probe per decision ``2026-06-03-coverlet-pertestcoverage-key.md`` §3
amended: per-test mode is empirically inert on Coverlet 6.0.x XPlat —
``mapping_granularity == "aggregate"`` is the asserted v1 contract. If
a future Coverlet release fixes the XPlat pipe, the per-test glob
inside the dotnet adapter auto-detects per-test files and granularity
promotes; the assertion below would then need a v2 amendment.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.coverage import get_coverage_facts
from novetest.coverage.persistence import coverage_facts_path
from novetest.memory.project_store import create_project_store
from novetest.memory.store import get_memory_entry_availability
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.orchestration.workflows.run import run_target_in_store


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "dotnet-test-basic-coverage"
)


def _require_dotnet() -> None:
    if shutil.which("dotnet") is None:
        pytest.skip(
            "requires `dotnet` on PATH (see scripts/dev-host-setup.md §6)"
        )


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture tree into ``dest`` and return its root.

    Excludes ``bin/`` / ``obj/`` / ``TestResults/`` / ``.novetest/`` so
    the test always starts from the clean fresh-fixture state (the
    F1c reproducer pattern from the dotnet hotfix #1 cycle —
    ``dotnet restore`` must materialize ``obj/project.assets.json``
    from scratch so the Coverlet probe sees the resolved package).
    """
    target = dest / "dotnet-test-basic-coverage"
    shutil.copytree(
        _FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns(
            "bin", "obj", "TestResults", ".novetest"
        ),
    )
    return target


def _run_inspect_cli(workspace: Path, run_id: str) -> tuple[int, dict[str, object], str]:
    """Subprocess-invoke ``novetest inspect <run_id> --output json``."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", "inspect", run_id],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload: dict[str, object] = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, payload, result.stderr


def _run_coverage_show_cli(
    workspace: Path, run_id: str
) -> tuple[int, dict[str, object], str]:
    """Subprocess-invoke ``novetest coverage show <run_id>``."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", "coverage", "show", run_id],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload: dict[str, object] = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, payload, result.stderr


async def test_run_coverage_on_dotnet_workspace_produces_xunit_fact_set(
    tmp_path: Path,
) -> None:
    """End-to-end dotnet Coverage flow.

    1. Materialize the dotnet-test-basic-coverage fixture (no obj/ pre-state).
    2. Initialize a Project Store at the fixture root (creates ``.novetest/``).
    3. ``run_target_in_store("", store, collect_coverage=True)`` — invokes
       the dotnet adapter via the orchestration layer, which writes the
       Cobertura XML AND calls ``derive_coverage_facts`` to produce a
       ``CoverageFactSet``.
    4. Assert the FactSet is xunit-shaped (engine="xunit", ecosystem="dotnet",
       granularity="aggregate", at least MathOps.cs covered, branches=0).
    5. Assert the load-bearing ``coverage_facts.json`` file exists so
       Memory's ``has_coverage_facts`` flag auto-flipped.
    6. Subprocess ``novetest inspect <run_id>`` — assert
       ``sub_reports.coverage == "available"`` AND
       ``coverage_outcome.kind == "fact-set"`` (the headline gap this
       slice closes; was ``"unavailable"`` pre-slice even with Cobertura
       on disk).
    7. Subprocess ``novetest coverage show <run_id>`` — assert structured
       per-file coverage is returned.
    """
    _require_dotnet()

    workspace = _materialize_fixture(tmp_path)
    store = create_project_store(workspace)

    outcome = await run_target_in_store(
        "", store, timeout=500.0, collect_coverage=True
    )

    # --- §4 / §5: xunit-shaped CoverageFactSet on the run outcome -------
    fact_set = outcome.coverage_outcome
    assert isinstance(fact_set, CoverageFactSet), (
        f"expected a CoverageFactSet from dotnet --coverage, got "
        f"{fact_set!r}; this is the headline gap the slice closes — "
        f"check that derive's _XUNIT_ENGINE_NAME branch dispatches"
    )
    assert fact_set.engine_name == "xunit"
    assert fact_set.ecosystem == "dotnet"
    # Coverlet XPlat path is aggregate-effective-default per amended
    # decision 2026-06-03 §3. If this assertion ever flips to
    # ``per-test``, that's a positive signal (a future Coverlet release
    # fixed the empirically-inert XPlat pipe); the parser auto-promotes.
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.metadata.get("coverage_format") == "cobertura-xml"
    assert (
        fact_set.metadata.get("branch_arc_semantics") == "branches-omitted"
    ), "v1 ships lines-only per task brief §2.3"

    # Persisted file paths are workspace-relative POSIX per decision
    # 2026-05-15 #6.
    for f in fact_set.files:
        assert not Path(f.file_path).is_absolute(), (
            f"expected workspace-relative path, got absolute: {f.file_path!r}"
        )
        assert f.line_contexts == {}, (
            "aggregate mode has no per-test attribution; line_contexts "
            f"must be empty, got {f.line_contexts!r}"
        )

    # MathOps.cs is the canonical source under test (Add + Subtract). At
    # least one file should appear with the MathOps.cs basename.
    file_paths = {f.file_path for f in fact_set.files}
    assert any(p.endswith("MathOps.cs") for p in file_paths), (
        f"expected MathOps.cs in fact set, got files={sorted(file_paths)!r}"
    )

    # Branches deferred per task brief §2.3 — v1 must report zero
    # branches across all files even though the Coverlet XML carries
    # ``branch="true"`` + ``condition-coverage`` attrs on some lines.
    assert all(f.summary.num_branches == 0 for f in fact_set.files), (
        "v1 ships lines-only; per-line branch facts should be zero"
    )
    assert fact_set.summary.num_branches == 0

    # --- Memory auto-flip: the load-bearing facts file is on disk -------
    run_id = fact_set.run_reference.run_id
    assert coverage_facts_path(store, run_id).is_file()
    assert outcome.memory_entry.has_coverage_facts is True
    flags = get_memory_entry_availability(store, fact_set.run_reference)
    assert flags["has_coverage_facts"] is True

    # --- get_coverage_facts round-trips the persisted CoverageFactSet ----
    cached = get_coverage_facts(store, fact_set.run_reference)
    assert isinstance(cached, CoverageFactSet)
    assert cached.engine_name == "xunit"
    assert cached.ecosystem == "dotnet"
    assert cached.files == fact_set.files

    # --- §6 step 6: novetest inspect <run_id> → coverage section flip ---
    code, envelope, stderr = _run_inspect_cli(workspace, run_id)
    assert code == 0, (
        f"`novetest inspect {run_id}` exited {code}; stderr={stderr!r}"
    )
    assert envelope.get("command") == "inspect"
    assert envelope.get("ok") is True
    data = envelope.get("data")
    assert isinstance(data, dict)
    sub_reports = data.get("sub_reports")
    assert isinstance(sub_reports, dict)
    assert sub_reports.get("coverage") == "available", (
        f"dotnet run with coverage_facts on disk must surface coverage "
        f"as available; sub_reports={sub_reports!r}. This is the "
        f"headline carry-forward closure from Phase 2/3."
    )
    coverage_outcome = data.get("coverage_outcome")
    assert isinstance(coverage_outcome, dict), (
        f"expected coverage_outcome dict in inspect envelope; got "
        f"{coverage_outcome!r}"
    )
    assert coverage_outcome.get("kind") == "fact-set", (
        f"coverage_outcome.kind must be 'fact-set' (was 'unavailable' "
        f"pre-slice); got {coverage_outcome!r}"
    )
    assert coverage_outcome.get("mapping_granularity") == "aggregate"

    # --- §6 step 7: novetest coverage show <run_id> → structured payload
    code, show_envelope, stderr = _run_coverage_show_cli(workspace, run_id)
    assert code == 0, (
        f"`novetest coverage show {run_id}` exited {code}; "
        f"stderr={stderr!r}"
    )
    assert show_envelope.get("ok") is True
    show_data = show_envelope.get("data")
    assert isinstance(show_data, dict)
    show_outcome = show_data.get("coverage_outcome")
    assert isinstance(show_outcome, dict)
    assert show_outcome.get("kind") == "fact-set"
    assert show_outcome.get("mapping_granularity") == "aggregate"
