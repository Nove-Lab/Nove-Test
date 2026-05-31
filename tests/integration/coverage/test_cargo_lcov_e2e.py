"""End-to-end: cargo-test ``--coverage`` → Coverage engine derives facts.

Exercises the full cargo Coverage path — the cargo adapter writes
``coverage.lcov`` (via ``cargo llvm-cov nextest --lcov``), and Coverage's
NEW LCOV parser turns it into a real ``CoverageFactSet`` instead of
``CoverageUnavailable``. Closes the post-2026-05-31 carry-forward:
cargo runs participate in ``coverage show`` / ``coverage diff`` /
``inspect`` like the pytest, jest, and go-test ecosystems.

This test spawns a **real** ``cargo llvm-cov nextest --lcov`` subprocess.
It skips when any of ``cargo``, ``cargo-nextest``, or ``cargo-llvm-cov``
is not on ``PATH`` — same precondition pattern as
``tests/integration/run/test_cargo_coverage.py``. Current CI has no Rust
cell, so the test is expected to skip on every CI runner; a future
Release-side slice adds Rust to the matrix and the test becomes a real
gate.

Fixture: ``tests/fixtures/projects/cargo-test-basic-coverage/`` (NOT
modified — this test owns the Coverage engine flow downstream; the
adapter-level LCOV emission already has its own test at
``tests/integration/run/test_cargo_coverage.py``). The fixture's
``classifier.rs`` deliberately leaves the negative branch uncovered, so
``missing_lines`` is non-empty by contract.
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
    / "cargo-test-basic-coverage"
)


def _require_cargo_toolchain() -> None:
    """Skip when any of cargo / cargo-nextest / cargo-llvm-cov is missing.

    Mirrors the guard pattern in
    ``tests/integration/run/test_cargo_coverage.py:32`` — same trio of
    binaries are required by the cargo adapter, so the skip messages
    line up with the Run-side test for operator continuity.
    """
    if shutil.which("cargo") is None:
        pytest.skip("requires `cargo` on PATH")
    if shutil.which("cargo-nextest") is None:
        pytest.skip(
            "requires `cargo-nextest` (install: cargo install cargo-nextest "
            "--locked)"
        )
    if shutil.which("cargo-llvm-cov") is None:
        pytest.skip(
            "requires `cargo-llvm-cov` (install: cargo install cargo-llvm-cov)"
        )


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture project tree into ``dest`` and return its root.

    ``target/`` is excluded because the fixture's committed Cargo.lock
    pins a clean build; copying the build cache would slow the test
    (and the cargo path rebuilds anyway under the tmp ``CARGO_TARGET_DIR``).
    ``.novetest/`` is excluded so the test always starts from a fresh
    Project Store.
    """
    target = dest / "cargo-test-basic-coverage"
    shutil.copytree(
        _FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns("target", ".novetest"),
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


async def test_run_coverage_on_cargo_workspace_produces_cargo_fact_set(
    tmp_path: Path,
) -> None:
    """End-to-end cargo Coverage flow.

    1. Materialize the cargo-test-basic-coverage fixture.
    2. Initialize a Project Store at the fixture root (creates ``.novetest/``).
    3. ``run_target_in_store("", store, collect_coverage=True)`` — invokes
       cargo's adapter via the orchestration layer, which writes the LCOV
       artifact AND calls ``derive_coverage_facts`` to produce a
       ``CoverageFactSet``.
    4. Assert the FactSet is cargo-shaped (engine=cargo-test, ecosystem=rust,
       granularity=aggregate, files >= 2 with workspace-relative paths,
       at least one ``missing_lines`` non-empty).
    5. Assert the load-bearing ``coverage_facts.json`` file exists so
       Memory's ``has_coverage_facts`` flag auto-flipped.
    6. Subprocess ``novetest inspect <run_id>`` — assert
       ``sub_reports.coverage == "available"`` (was ``"unavailable"`` for
       cargo runs pre-this-slice).
    """
    _require_cargo_toolchain()

    workspace = _materialize_fixture(tmp_path)
    store = create_project_store(workspace)

    outcome = await run_target_in_store(
        "", store, timeout=300.0, collect_coverage=True
    )

    # --- §4 / §5: cargo-shaped CoverageFactSet on the run outcome --------
    fact_set = outcome.coverage_outcome
    assert isinstance(fact_set, CoverageFactSet), (
        f"expected a CoverageFactSet from cargo --coverage, got {fact_set!r}"
    )
    assert fact_set.engine_name == "cargo-test"
    assert fact_set.ecosystem == "rust"
    # cargo-llvm-cov in aggregate mode merges across all tests with no
    # per-test attribution — granularity is "aggregate" by contract.
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.metadata.get("coverage_format") == "lcov"

    # The fixture has two source files (arithmetic.rs + classifier.rs)
    # under src/. lib.rs is the crate root and is also covered. The
    # exact set depends on which files cargo-llvm-cov reports, but the
    # two with the tested business logic MUST be present.
    file_paths = {f.file_path for f in fact_set.files}
    # Persisted paths are workspace-relative POSIX per decision
    # 2026-05-15 #6.
    for f in fact_set.files:
        assert not Path(f.file_path).is_absolute(), (
            f"expected workspace-relative path, got absolute: {f.file_path!r}"
        )
        assert f.line_contexts == {}, (
            "cargo-llvm-cov aggregate mode has no per-test attribution; "
            f"line_contexts must be empty, got {f.line_contexts!r}"
        )
    # At least the two business-logic source files appear.
    assert any(p.endswith("arithmetic.rs") for p in file_paths), (
        f"expected arithmetic.rs in fact set, got files={sorted(file_paths)!r}"
    )
    assert any(p.endswith("classifier.rs") for p in file_paths), (
        f"expected classifier.rs in fact set, got files={sorted(file_paths)!r}"
    )

    # The fixture's classifier.rs deliberately leaves the negative branch
    # uncovered, so missing_lines must be non-empty somewhere.
    has_missing = any(f.missing_lines for f in fact_set.files)
    assert has_missing, (
        "fixture contract: the negative branch of classifier::classify is "
        "intentionally uncovered, so at least one file should report "
        "missing_lines; got all-covered fact set"
    )

    # --- Memory auto-flip: the load-bearing facts file is on disk -------
    run_id = fact_set.run_reference.run_id
    assert coverage_facts_path(store, run_id).is_file()
    assert outcome.memory_entry.has_coverage_facts is True
    flags = get_memory_entry_availability(store, fact_set.run_reference)
    assert flags["has_coverage_facts"] is True

    # --- get_coverage_facts round-trips the persisted CoverageFactSet ----
    cached = get_coverage_facts(store, fact_set.run_reference)
    assert isinstance(cached, CoverageFactSet)
    assert cached.engine_name == "cargo-test"
    assert cached.ecosystem == "rust"
    assert cached.files == fact_set.files

    # --- §5 step 5: novetest inspect <run_id> → sub_reports.coverage flip
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
        "cargo run with coverage_facts on disk must surface coverage as "
        f"available; sub_reports={sub_reports!r}"
    )
    # The inspect envelope's coverage_outcome should be the projected
    # `fact-set` discriminator, not `unavailable`.
    coverage_outcome = data.get("coverage_outcome")
    assert isinstance(coverage_outcome, dict)
    assert coverage_outcome.get("kind") == "fact-set"
    assert coverage_outcome.get("mapping_granularity") == "aggregate"
