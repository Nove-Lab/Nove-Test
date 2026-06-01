"""End-to-end: ``derive_latest_localization`` against non-per-test fixtures.

Closes Defect 4 (carry-forward from 2026-06-01 cycle): the ``latest``
discoverability path used to gate on per-test coverage only, which made
``novetest localization latest`` return ``run_not_analyzable`` for cargo
/ go / jest aggregate-coverage runs AND for coverage-less runs — even
though the explicit ``<run_id>`` path handled them correctly via the
3-mode dispatcher in ``derive_localization_findings``.

Per ``agent-comms/history/2026-06-01-localization-phase4-modes-and-
cargo-defect-cascade.md`` §"Defect 4" the gate in
``check_localization_availability`` was relaxed to match the dispatch:
a non-tombstoned entry with at least one failed test is analyzable
regardless of coverage shape.

This module is the canonical "latest verb works for all 3 modes"
regression-pin:

| Path | Fixture                       | Coverage?    | Expected mode      |
|------|-------------------------------|--------------|--------------------|
| A    | localization-aggregate-only   | yes (LCOV)   | sbfl_aggregate     |
| B    | localization-no-coverage      | NO           | failure_proximity  |
| C    | localization-branch (pytest)  | yes (--cov)  | sbfl_per_test      |

Path A is cargo-skip-guarded (mirrors ``test_aggregate_mode_e2e.py``);
Paths B and C only need pytest + Python.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.localization import derive_latest_localization
from novetest.localization.persistence import localization_findings_path
from novetest.memory.project_store import create_project_store
from novetest.memory.store import retrieve_run_evidence
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _materialize_fixture(dest: Path, fixture_name: str) -> Path:
    """Copy the fixture project tree into ``dest`` and return the new root."""
    target = dest / fixture_name
    shutil.copytree(
        _FIXTURES_ROOT / fixture_name,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".novetest", "target"
        ),
    )
    return target


def _require_cargo_toolchain() -> None:
    """Skip when any of cargo / cargo-nextest / cargo-llvm-cov is missing.

    Mirrors the guard pattern in ``test_aggregate_mode_e2e.py``.
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


# --- Path A: sbfl_aggregate (cargo) -----------------------------------------


async def test_latest_verb_returns_aggregate_finding_for_cargo_fixture(
    tmp_path: Path,
) -> None:
    """Defect 4 regression-pin (Path A): ``derive_latest_localization``
    against ``localization-aggregate-only`` returns a populated finding
    with ``mode == "sbfl_aggregate"``.

    Pre-Defect-4 this would have returned
    ``LocalizationUnavailable(reason="run_not_analyzable")`` because
    cargo's aggregate-granularity coverage failed the per-test-only
    gate. The ranking check itself (arithmetic.rs ranked #1) is owned
    by ``test_aggregate_mode_e2e.py``; here we only assert the
    discoverability path returns a fact-set rather than an unavailable.
    """
    _require_cargo_toolchain()

    workspace = _materialize_fixture(tmp_path, "localization-aggregate-only")
    store = create_project_store(workspace)

    outcome = await run_target_in_store(
        "", store, timeout=300.0, collect_coverage=True
    )
    # Establish the precondition: a failing run with aggregate coverage
    # landed in the store. (If this assertion fires, the test is broken,
    # not Defect 4.)
    run_reference = outcome.memory_entry.run_record.run_reference
    assert run_reference is not None

    finding = derive_latest_localization(store)
    assert isinstance(finding, LocalizationFinding), (
        f"Defect 4: expected LocalizationFinding from `latest` verb against "
        f"aggregate-coverage cargo run; got {finding!r}"
    )
    assert finding.mode == "sbfl_aggregate"
    assert finding.confidence == "medium"
    assert finding.run_reference.run_id == run_reference.run_id

    # Cache landed at the canonical path and Memory flag flipped.
    findings_path = localization_findings_path(store, run_reference.run_id)
    assert findings_path.is_file()
    refreshed = retrieve_run_evidence(store, run_reference)
    assert refreshed.has_localization_findings is True


# --- Path B: failure_proximity (no coverage) --------------------------------


async def test_latest_verb_returns_failure_proximity_finding_for_no_coverage_fixture(
    tmp_path: Path,
) -> None:
    """Defect 4 regression-pin (Path B): ``derive_latest_localization``
    against ``localization-no-coverage`` returns a populated finding
    with ``mode == "failure_proximity"``.

    Pre-Defect-4 this would have returned
    ``LocalizationUnavailable(reason="run_not_analyzable")`` because no
    coverage at all failed the per-test-only gate. The ranking check
    itself (statistics.py picked up from the failure trace) is owned by
    ``test_failure_proximity_e2e.py``; here we only assert the
    discoverability path returns a fact-set rather than an unavailable.
    """
    workspace = _materialize_fixture(tmp_path, "localization-no-coverage")

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=False
    )
    run_reference = outcome.memory_entry.run_record.run_reference
    assert run_reference is not None

    finding = derive_latest_localization(init.store)
    assert isinstance(finding, LocalizationFinding), (
        f"Defect 4: expected LocalizationFinding from `latest` verb against "
        f"coverage-less run; got {finding!r}"
    )
    assert finding.mode == "failure_proximity"
    assert finding.confidence == "low"
    assert finding.run_reference.run_id == run_reference.run_id

    # Cache landed at the canonical path and Memory flag flipped.
    findings_path = localization_findings_path(init.store, run_reference.run_id)
    assert findings_path.is_file()
    refreshed = retrieve_run_evidence(init.store, run_reference)
    assert refreshed.has_localization_findings is True


# --- Path C: sbfl_per_test (regression-pin) ---------------------------------


async def test_latest_verb_still_returns_per_test_finding_for_branch_fixture(
    tmp_path: Path,
) -> None:
    """Defect 4 regression-pin (Path C): the relaxed gate must NOT
    change the per-test path's behavior.

    ``localization-branch`` is the canonical per-test fixture; the
    Defect 4 gate-relaxation must leave its mode/confidence selection
    unchanged. If a future refactor accidentally routed per-test
    coverage through the aggregate path, this test would catch it.
    """
    workspace = _materialize_fixture(tmp_path, "localization-branch")

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )
    run_reference = outcome.memory_entry.run_record.run_reference
    assert run_reference is not None

    finding = derive_latest_localization(init.store)
    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "sbfl_per_test"
    assert finding.confidence == "high"
    assert finding.run_reference.run_id == run_reference.run_id
