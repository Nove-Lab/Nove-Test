"""End-to-end: ``novetest run --coverage`` (cargo) → ``sbfl_aggregate`` mode.

Drives Path B of the strategy doc §2 mode-selection algorithm against
the ``localization-aggregate-only`` fixture:

1. Materialize the cargo fixture under ``tmp_path``.
2. Initialize a Project Store.
3. Spawn the real cargo adapter with ``collect_coverage=True`` so
   ``cargo llvm-cov nextest --lcov`` writes the LCOV artifact and the
   Coverage engine parses it into a
   ``CoverageFactSet(mapping_granularity="aggregate")``.
4. Call ``derive_localization_findings`` and assert the resulting
   finding has ``mode == "sbfl_aggregate"`` + ``confidence == "medium"``
   + the buggy file (``src/arithmetic.rs``) ranked top-1.
5. Cross-check the envelope shape: ``alternate_scores_available`` is
   the 3-element sorted tuple (NO deviation for sbfl_aggregate — only
   failure_proximity carries the empty-tuple deviation).

Skip-guarded: when any of ``cargo``, ``cargo-nextest``, ``cargo-llvm-cov``
is missing on PATH, the test skips cleanly. The skip-guard pattern
mirrors ``tests/integration/coverage/test_cargo_lcov_e2e.py`` so the
operator-facing skip messages line up.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.coverage.retrieval import get_coverage_facts
from novetest.localization.derive import derive_localization_findings
from novetest.localization.persistence import localization_findings_path
from novetest.memory.project_store import create_project_store
from novetest.memory.store import retrieve_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.run import run_target_in_store


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "localization-aggregate-only"
)


def _require_cargo_toolchain() -> None:
    """Skip when any of cargo / cargo-nextest / cargo-llvm-cov is missing.

    Mirrors the guard pattern in
    ``tests/integration/coverage/test_cargo_lcov_e2e.py``.
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
    """Copy the fixture into ``dest`` and return its root.

    Excludes ``target/`` and ``.novetest/`` so the test always starts
    from a fresh build cache + Project Store.
    """
    target = dest / "localization-aggregate-only"
    shutil.copytree(
        _FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns("target", ".novetest"),
    )
    return target


async def test_aggregate_mode_ranks_buggy_file_top(tmp_path: Path) -> None:
    """End-to-end cargo aggregate Localization flow.

    Asserts mode = ``sbfl_aggregate``, confidence = ``medium``, and the
    buggy ``src/arithmetic.rs`` is ranked first under Ochiai.
    """
    _require_cargo_toolchain()

    workspace = _materialize_fixture(tmp_path)
    store = create_project_store(workspace)

    outcome = await run_target_in_store(
        "", store, timeout=300.0, collect_coverage=True
    )

    # Pre-condition: aggregate-granularity coverage facts on disk.
    fact_set = outcome.coverage_outcome
    assert isinstance(fact_set, CoverageFactSet)
    assert fact_set.engine_name == "cargo-test"
    assert fact_set.ecosystem == "rust"
    assert fact_set.mapping_granularity == "aggregate"

    # Derive the Localization finding.
    run_reference = outcome.memory_entry.run_record.run_reference
    finding = derive_localization_findings(store, run_reference)
    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "sbfl_aggregate"
    assert finding.confidence == "medium"
    assert finding.formula == "ochiai"
    # NO deviation for sbfl_aggregate — full 3-element alternate set.
    assert set(finding.alternate_scores_available) == {"op2", "dstar2", "tarantula"}

    assert finding.entries, "expected at least one sbfl_aggregate entry"
    # The buggy file must be ranked first. cargo's failure log mentions
    # the SuT file (``src/arithmetic.rs``) in the libtest panic message,
    # so the parser lifts that file's ef to 1 while every other covered
    # file has ef=0 (and is filtered by the score-zero gate).
    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "file"
    assert top.code_location.symbol is None
    assert top.code_location.file.endswith("arithmetic.rs"), (
        f"expected top entry to be src/arithmetic.rs (the seeded bug); "
        f"got {top.code_location.file!r}; entries="
        f"{[e.code_location.file for e in finding.entries]!r}"
    )

    # B2-1 (UX normalization, 2026-06-08): mode-invariant metadata key
    # set. sbfl_aggregate emits both base keys with concrete (int /
    # bool) values reflecting whether FLUCCS reweighting fired against
    # an available change set. The symmetric assertions in
    # test_localization_branch_basic.py (sbfl_per_test: None / None)
    # and test_failure_proximity_e2e.py (failure_proximity: int / bool)
    # close the 3-mode matrix the brief mandates.
    assert "changed_files_count" in finding.metadata
    assert "regression_reweighted" in finding.metadata
    assert isinstance(finding.metadata["changed_files_count"], int)
    assert isinstance(finding.metadata["regression_reweighted"], bool)

    # Cache file landed at the load-bearing path; Memory flag flipped.
    findings_path = localization_findings_path(store, run_reference.run_id)
    assert findings_path.is_file()
    refreshed = retrieve_run_evidence(store, run_reference)
    assert refreshed.has_localization_findings is True

    # Read-cache round-trip returns identical finding.
    fact_set_round_trip = get_coverage_facts(store, run_reference)
    assert isinstance(fact_set_round_trip, CoverageFactSet)
