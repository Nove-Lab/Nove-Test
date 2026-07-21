"""End-to-end: junit (Maven + JaCoCo) ``--coverage`` → Coverage engine
derives facts from the REAL ``jacoco.xml`` artifact.

Closes ANA-15 (``design/reviews/2026-07-04-codebase-review/findings/
analysis-engines.md``): before this slice JaCoCo was the only coverage
parser with no real-artifact e2e. The sibling junit run test
(``tests/integration/run/test_junit_maven.py::
test_coverage_run_emits_jacoco_xml``) only asserts the ``jacoco.xml``
artifact EXISTS — it never feeds it to ``parse_jacoco_xml`` / the derive
path. ``parse_jacoco_xml`` was otherwise exercised solely by hand-written
inline XML, so a real-world JaCoCo report-shape change (DOCTYPE,
``<sessioninfo>``, ``<class>/<method>/<counter>`` nesting) would ship a
broken derive undetected.

This test spawns a **real** ``mvn -B test`` subprocess against the
``junit-maven-basic`` fixture, then drives the REAL derive path
(``coverage/derive_coverage_facts`` via ``run_target_in_store``) and
asserts structured ``CoverageFactSet`` content — not just parse-no-crash.
It mirrors the structure and skip-gating of the sibling
``test_dotnet_cobertura_derive.py`` / ``test_cargo_lcov_e2e.py`` derive
tests.

Skip-gates on ``java`` + ``mvn`` on PATH (and Windows, per the JUnit
adapter's Windows gate — decision 2026-06-03-junit-console-launcher-
vendor.md §R5). On java-equipped CI cells the release lane's
``NOVETEST_REQUIRE_ENGINES=junit`` gate (``tests/conftest.py``
``ENGINE_TEST_PATTERNS`` extension for ``tests/integration/coverage/
test_junit_``) turns the skip into a hard failure so this real-artifact
signal cannot silently vanish.
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


pytestmark = [
    pytest.mark.skipif(
        sys.platform.startswith("win"),
        reason=(
            "JUnit adapter gates Windows per decision "
            "2026-06-03-junit-console-launcher-vendor.md §R5"
        ),
    ),
    pytest.mark.skipif(
        shutil.which("java") is None or shutil.which("mvn") is None,
        reason="JDK 17+ and Maven 3.9+ required (see scripts/dev-host-setup.md §5)",
    ),
]


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "junit-maven-basic"
)


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture tree into ``dest`` so the run doesn't pollute the
    committed fixture with ``target/`` / ``.novetest/`` artifacts (mirrors
    the cargo / dotnet derive-test isolation pattern)."""
    target = dest / "junit-maven-basic"
    shutil.copytree(
        _FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns("target", ".novetest"),
    )
    return target


def _run_inspect_cli(
    workspace: Path, run_id: str
) -> tuple[int, dict[str, object], str]:
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


async def test_run_coverage_on_junit_workspace_produces_jacoco_fact_set(
    tmp_path: Path,
) -> None:
    """End-to-end junit Coverage flow.

    1. Materialize the junit-maven-basic fixture (no target/ pre-state).
    2. Initialize a Project Store at the fixture root (creates ``.novetest/``);
       the pom.xml auto-detects+pins the junit engine.
    3. ``run_target_in_store("", store, collect_coverage=True)`` — invokes
       the junit adapter via the orchestration layer, which writes the REAL
       JaCoCo XML AND calls ``derive_coverage_facts`` (the ANA-15 gap: the
       real ``jacoco.xml`` now flows through ``parse_jacoco_xml``).
    4. Assert the FactSet is junit-shaped (engine="junit", ecosystem="java",
       granularity="aggregate", Calculator.java present with plausible
       counter-derived totals + real branch extraction).
    5. Assert the load-bearing ``coverage_facts.json`` exists so Memory's
       ``has_coverage_facts`` flag auto-flipped.
    6. Subprocess ``novetest inspect`` / ``coverage show`` — assert the
       coverage section surfaces the fact set on the wire.
    """
    workspace = _materialize_fixture(tmp_path)
    store = create_project_store(workspace)

    outcome = await run_target_in_store(
        "", store, timeout=400.0, collect_coverage=True
    )

    # --- §4: junit-shaped CoverageFactSet from the REAL jacoco.xml -------
    fact_set = outcome.coverage_outcome
    assert isinstance(fact_set, CoverageFactSet), (
        f"expected a CoverageFactSet from junit --coverage, got "
        f"{fact_set!r}; ANA-15 — the real jacoco.xml must flow through "
        f"derive's _JUNIT_ENGINE_NAME branch → parse_jacoco_xml"
    )
    assert fact_set.engine_name == "junit"
    assert fact_set.ecosystem == "java"
    # JaCoCo under default Surefire forkMode gives aggregate-only coverage.
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.metadata.get("coverage_format") == "jacoco-xml"
    assert (
        fact_set.metadata.get("branch_arc_semantics")
        == "jacoco-line-counter-index"
    )

    # Persisted paths are workspace-relative POSIX (decision 2026-05-15 #6)
    # and carry no per-test attribution in aggregate mode.
    for f in fact_set.files:
        assert not Path(f.file_path).is_absolute(), (
            f"expected workspace-relative path, got absolute: {f.file_path!r}"
        )
        assert not f.file_path.startswith("..")
        assert f.line_contexts == {}, (
            "aggregate mode has no per-test attribution; line_contexts "
            f"must be empty, got {f.line_contexts!r}"
        )

    # Calculator.java is the SuT. After ANA-05's disk-existence filter it
    # survives because the composed src/main/java path exists in the
    # standard Maven layout — a real end-to-end proof of that filter too.
    file_paths = {f.file_path for f in fact_set.files}
    assert "src/main/java/com/example/Calculator.java" in file_paths, (
        f"expected Calculator.java in fact set, got {sorted(file_paths)!r}"
    )

    # Plausible counter-derived totals (not just parse-no-crash): every
    # Calculator method is exercised, so covered statements are non-zero
    # and the divide() if-branch surfaces as >=2 branches with the covered
    # arm extracted — the real-artifact branch-extraction signal.
    calc = next(
        f
        for f in fact_set.files
        if f.file_path == "src/main/java/com/example/Calculator.java"
    )
    assert calc.summary.num_statements > 0
    assert calc.summary.covered_statements > 0
    assert calc.executed_lines, "expected non-empty executed lines"
    assert calc.summary.num_branches >= 2, (
        "divide()'s `if (b == 0)` is a two-arm branch; the real jacoco.xml "
        f"reports cb=2 on that line — got num_branches={calc.summary.num_branches}"
    )
    assert calc.executed_branches, (
        "both branch arms are covered (testDivide + testDivideByZero); the "
        "real-artifact covered-branch extraction must be non-empty"
    )
    # Aggregate roll-up is the sum-of-parts over surviving files.
    assert fact_set.summary.num_statements == sum(
        f.summary.num_statements for f in fact_set.files
    )
    assert fact_set.summary.covered_statements > 0

    # --- §5: Memory auto-flip — the load-bearing facts file is on disk ---
    run_id = fact_set.run_reference.run_id
    assert coverage_facts_path(store, run_id).is_file()
    assert outcome.memory_entry.has_coverage_facts is True
    flags = get_memory_entry_availability(store, fact_set.run_reference)
    assert flags["has_coverage_facts"] is True

    # --- get_coverage_facts round-trips the persisted CoverageFactSet ----
    cached = get_coverage_facts(store, fact_set.run_reference)
    assert isinstance(cached, CoverageFactSet)
    assert cached.engine_name == "junit"
    assert cached.ecosystem == "java"
    assert cached.files == fact_set.files

    # --- §6: novetest inspect <run_id> → coverage section available -----
    code, envelope, stderr = _run_inspect_cli(workspace, run_id)
    assert code == 0, (
        f"`novetest inspect {run_id}` exited {code}; stderr={stderr!r}"
    )
    assert envelope.get("ok") is True
    data = envelope.get("data")
    assert isinstance(data, dict)
    sub_reports = data.get("sub_reports")
    assert isinstance(sub_reports, dict)
    assert sub_reports.get("coverage") == "available", (
        f"junit run with coverage_facts on disk must surface coverage as "
        f"available; sub_reports={sub_reports!r}"
    )
    coverage_outcome = data.get("coverage_outcome")
    assert isinstance(coverage_outcome, dict)
    assert coverage_outcome.get("kind") == "fact-set"
    assert coverage_outcome.get("mapping_granularity") == "aggregate"

    # --- §6: novetest coverage show <run_id> → structured payload -------
    code, show_envelope, stderr = _run_coverage_show_cli(workspace, run_id)
    assert code == 0, (
        f"`novetest coverage show {run_id}` exited {code}; stderr={stderr!r}"
    )
    assert show_envelope.get("ok") is True
    show_data = show_envelope.get("data")
    assert isinstance(show_data, dict)
    show_outcome = show_data.get("coverage_outcome")
    assert isinstance(show_outcome, dict)
    assert show_outcome.get("kind") == "fact-set"
    assert show_outcome.get("mapping_granularity") == "aggregate"
