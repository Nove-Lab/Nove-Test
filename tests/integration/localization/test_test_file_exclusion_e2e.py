"""Test-file exclusion against real pytest + coverage.py per-test payloads.

Two fixtures, one claim each:

- ``localization-shared-defect`` — the wave-1 persona-P1 shape (two
  failing tests; the defect line also executed by passing tests). Before
  the exclusion its ranking was, byte for byte, the ranking the P1
  envelope carried: the two failing test functions at rank 1 / 1.000,
  the defect at rank 2 / 0.894. This module pins the fixed ranking.
- ``localization-branch`` — the CLAIM BOUND. Its planted ``divide`` bug
  must still come out rank 1 at Ochiai 1.0. (Pre-exclusion it was TIED at
  rank 1 with ``test_divide_yields_quotient``, whose own body also scores
  exactly 1.0; the bug printed first only because the tie-break sorts by
  file path and ``localization_branch/`` < ``tests/``.)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from novetest.localization.candidate_filter import discovered_test_files
from novetest.localization.derive import derive_localization_findings
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _materialize(dest: Path, fixture_name: str) -> Path:
    target = dest / fixture_name
    shutil.copytree(
        _FIXTURES_ROOT / fixture_name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


async def _derive(tmp_path: Path, fixture_name: str) -> tuple[
    LocalizationFinding, frozenset[str]
]:
    workspace = _materialize(tmp_path, fixture_name)
    clear_resolver_cache()
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )
    record = outcome.memory_entry.run_record
    finding = derive_localization_findings(init.store, record.run_reference)
    assert isinstance(finding, LocalizationFinding), finding
    return finding, discovered_test_files(record)


async def test_shared_defect_fixture_ranks_the_defect_first(tmp_path: Path) -> None:
    """The defect is rank 1; no ranked entry lives in a test file."""
    finding, test_files = await _derive(tmp_path, "localization-shared-defect")

    assert finding.mode == "sbfl_per_test"
    assert test_files == {"tests/test_totals.py", "tests/test_helpers.py"}

    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.file == "shared_defect/totals.py"
    assert top.code_location.symbol == "invoice_total"
    assert top.score_normalized == 1.0

    assert not [e for e in finding.entries if e.code_location.file in test_files], (
        "a ranked entry still points at one of the run's own test files: "
        f"{[e.code_location.file for e in finding.entries]}"
    )

    # Auditable: the filter fired, and it did not have to be reverted.
    assert finding.metadata["test_file_locations_excluded"] > 0
    assert finding.metadata["test_file_exclusion_reverted"] is False


async def test_localization_branch_planted_bug_still_ranks_first(
    tmp_path: Path,
) -> None:
    """Claim bound: the historical per-test fixture is unchanged at rank 1.

    Its ``test_divide_yields_quotient`` body scores exactly the same 1.0 as
    ``divide`` (``ef=1, ep=0, nf=0``), so the exclusion is what removes the
    tie rather than what creates the rank-1 answer.
    """
    finding, test_files = await _derive(tmp_path, "localization-branch")

    assert finding.mode == "sbfl_per_test"
    top = finding.entries[0]
    assert top.rank == 1
    assert top.score_raw == 1.0
    assert top.code_location.symbol == "divide"
    assert top.code_location.file == "localization_branch/calculator.py"

    assert not [e for e in finding.entries if e.code_location.file in test_files]
    assert finding.metadata["test_file_locations_excluded"] > 0
    assert finding.metadata["test_file_exclusion_reverted"] is False
