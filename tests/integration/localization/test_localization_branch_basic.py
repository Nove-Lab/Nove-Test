"""End-to-end SBFL: ``novetest run --coverage`` → ``derive_localization_findings``.

Drives the entire per-test path against the ``localization-branch``
fixture:

1. Materialize the fixture under ``tmp_path``.
2. Initialize a Project Store.
3. Spawn the real pytest adapter with ``--cov-context=test`` to write
   the run's per-test ``CoverageFactSet``.
4. Call ``derive_localization_findings`` and assert the buggy
   ``divide`` function is ranked top-1 with Ochiai score 1.0.
5. Cross-check Memory's ``has_localization_findings`` flag flipped on
   the post-derivation Memory Entry refresh.

Mirrors the structure of the orchestration-layer
``test_run_with_coverage_against_pytest_coverage_fixture`` test. The
test exercises real subprocess + real coverage.py — there is no
mocking. The same pytest-coverage dev dependency that underpins the
existing pytest-coverage integration tests is sufficient here, so no
new skip-guard infrastructure is needed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from novetest.coverage.retrieval import get_coverage_facts
from novetest.localization.derive import derive_localization_findings
from novetest.localization.persistence import localization_findings_path
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory.store import retrieve_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "localization-branch"
)


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture project tree into ``dest`` and return the new root."""
    target = dest / "localization-branch"
    shutil.copytree(
        FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".novetest"
        ),
    )
    return target


async def test_localization_ranks_buggy_function_top(
    tmp_path: Path,
) -> None:
    """Top-1 entry under Ochiai is ``calculator.divide`` with score 1.0.

    End-to-end: real pytest run with per-test coverage attribution +
    real SBFL derivation. The fixture's deliberate fault yields ef=1,
    ep=0 for ``divide``'s body, which Ochiai maps to suspicion 1.0.
    Every other function's body is touched only by passing tests, so
    their Ochiai suspicion is 0.
    """
    workspace = _materialize_fixture(tmp_path)
    clear_resolver_cache()

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )

    # Pre-conditions for the SBFL path: per-test coverage with the
    # failing test attributable to the buggy function's line.
    assert outcome.memory_entry.has_coverage_facts is True
    coverage = outcome.coverage_outcome
    assert isinstance(coverage, CoverageFactSet)
    assert coverage.mapping_granularity == "per-test"

    # Drive the engine. The slice writes the canonical
    # ``localization_findings.json`` and Memory flips the flag.
    run_reference = outcome.memory_entry.run_record.run_reference
    finding = derive_localization_findings(init.store, run_reference)
    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "sbfl_per_test"
    assert finding.confidence == "high"
    assert finding.formula == "ochiai"
    assert finding.entries, "expected at least one ranked entry"

    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "symbol"
    assert top.code_location.symbol == "divide"
    assert top.code_location.file.endswith("calculator.py")
    # Ochiai score for the divide function under failing-only coverage
    # is exactly 1.0.
    assert top.score_raw == 1.0

    # The failing test must be among the related failed tests of the top entry.
    assert any(
        "test_divide_yields_quotient" in nodeid
        for nodeid in top.related_failed_tests
    )

    # Cache file landed at the load-bearing path; Memory's flag flipped.
    findings_path = localization_findings_path(init.store, run_reference.run_id)
    assert findings_path.is_file()
    refreshed = retrieve_run_evidence(init.store, run_reference)
    assert refreshed.has_localization_findings is True

    # Sanity-check the cache-then-derive seam by calling again. Same
    # fact set returned.
    second = derive_localization_findings(init.store, run_reference)
    assert isinstance(second, LocalizationFinding)
    assert second == finding


async def test_get_coverage_facts_round_trip_on_fixture(tmp_path: Path) -> None:
    """Sanity: per-test coverage round-trips before SBFL runs — keeps the
    SBFL test focused on its own surface even when the coverage path
    has a regression."""
    workspace = _materialize_fixture(tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )

    run_reference = outcome.memory_entry.run_record.run_reference
    cached = get_coverage_facts(init.store, run_reference)
    assert isinstance(cached, CoverageFactSet)
    assert cached.mapping_granularity == "per-test"
    # The fixture's bug line is covered by exactly one (failing) test.
    calculator = next(
        (f for f in cached.files if f.file_path.endswith("calculator.py")), None
    )
    assert calculator is not None
    assert calculator.line_contexts, "expected per-test contexts to be populated"
