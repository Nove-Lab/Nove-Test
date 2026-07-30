"""Test-file exclusion against real pytest + coverage.py per-test payloads.

Four fixtures, one claim each:

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
- ``localization-colocated-tests`` — production code and collected tests
  in ONE file. The file-granular exclusion deleted the defect along with
  the tests (L1 finding, issue 2); symbol-granular exclusion keeps it.
- ``localization-wrong-expectation`` — the defect IS the test's expected
  value and the test also calls product code, so the revert cannot fire
  (L1 finding, issue 3). The ranking still leads with product code; the
  suppressed test symbol must be visible in ``metadata``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from novetest.localization.candidate_filter import discovered_test_files, normalize_path
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


async def _derive(
    tmp_path: Path, fixture_name: str, target: str = "tests/", subdir: str = ""
) -> tuple[LocalizationFinding, frozenset[str]]:
    workspace = _materialize(tmp_path, fixture_name) / subdir
    clear_resolver_cache()
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        target, init.store, timeout=120.0, collect_coverage=True
    )
    record = outcome.memory_entry.run_record
    finding = derive_localization_findings(init.store, record.run_reference)
    assert isinstance(finding, LocalizationFinding), finding
    return finding, discovered_test_files(record)


def _entry_keys(finding: LocalizationFinding) -> list[tuple[str, str | None]]:
    return [
        (normalize_path(e.code_location.file), e.code_location.symbol)
        for e in finding.entries
    ]


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

    # Both sides normalized: ``discovered_test_files`` folds separators,
    # ``code_location.file`` is raw, so on Windows a naive ``in`` compares
    # ``tests\test_totals.py`` against ``tests/test_totals.py`` and this
    # guard would pass vacuously — even if the filter had failed entirely.
    assert not [
        e
        for e in finding.entries
        if normalize_path(e.code_location.file) in test_files
    ], (
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

    # Normalized on both sides — see the sibling test for why.
    assert not [
        e
        for e in finding.entries
        if normalize_path(e.code_location.file) in test_files
    ]
    assert finding.metadata["test_file_locations_excluded"] > 0
    assert finding.metadata["test_file_exclusion_reverted"] is False


async def test_colocated_fixture_keeps_the_production_symbol_of_a_test_file(
    tmp_path: Path,
) -> None:
    """L1 issue 2: a co-located file's production symbols must survive.

    ``colocated/totals.py`` owns two collected test functions AND the
    seeded defect. File-granular exclusion dropped all three, leaving the
    ranking pointing only at innocent ``colocated/helpers.py`` symbols with
    ``test_file_exclusion_reverted: false`` — a silent false negative.
    """
    finding, test_files = await _derive(
        tmp_path, "localization-colocated-tests", target="colocated/"
    )

    assert finding.mode == "sbfl_per_test"
    assert test_files == {"colocated/totals.py"}

    keys = _entry_keys(finding)
    assert ("colocated/totals.py", "invoice_total") in keys, (
        f"the seeded defect was deleted with its file's tests: {keys}"
    )
    # ...and the test functions that share the file are still gone.
    assert not [symbol for _file, symbol in keys if str(symbol).startswith("test_")]

    assert finding.metadata["test_file_locations_excluded"] == 2
    assert finding.metadata["test_file_exclusion_reverted"] is False


async def test_wrong_expectation_fixture_surfaces_the_suppressed_test_symbol(
    tmp_path: Path,
) -> None:
    """L1 issue 3: the deleted top suspect must stay visible.

    The bug is the test's expected value, but the failing test also calls
    ``money.cents``, so a positively-scored candidate survives the
    exclusion and the revert cannot fire. The ranking therefore leads with
    correct product code; ``test_file_locations_suppressed`` is what stops
    that from being a *silent* wrong answer — it names the higher-scoring
    test symbol that was removed.
    """
    finding, _test_files = await _derive(tmp_path, "localization-wrong-expectation")

    assert finding.mode == "sbfl_per_test"
    top = finding.entries[0]
    assert (top.code_location.file, top.code_location.symbol) == (
        "wrong_expectation/money.py",
        "cents",
    )

    suppressed = finding.metadata["test_file_locations_suppressed"]
    assert suppressed == [
        {
            "file": "tests/test_money.py",
            "symbol": "test_cents_of_two_fifty",
            "score_raw": 1.0,
        }
    ]
    # The suppressed suspect outscores the entry the ranking now leads
    # with — the signal a consumer needs to distrust rank 1 here.
    assert suppressed[0]["score_raw"] > top.score_raw
    assert finding.metadata["test_file_exclusion_reverted"] is False


async def test_monorepo_rootdir_fixture_still_excludes_the_test_nodes(
    tmp_path: Path,
) -> None:
    """L1 issue 1: node ids rooted above the workspace must still match.

    ``pytest.ini`` sits one level above the novetest workspace, so pytest
    records ``svc/tests/test_totals.py::…`` while the Coverage Facts stay
    workspace-relative (``tests/test_totals.py``). The strict intersection
    is empty; before the path-suffix re-key the filter silently no-opped
    and the pre-fix ranking (failing test bodies at rank 1) came back with
    ``test_file_locations_excluded: 0`` — indistinguishable in the envelope
    from a healthy ecosystem no-op.
    """
    finding, test_files = await _derive(
        tmp_path, "localization-monorepo-rootdir", subdir="svc"
    )

    assert finding.mode == "sbfl_per_test"
    # Ground truth really is rooted above the workspace.
    assert test_files == {"svc/tests/test_totals.py", "svc/tests/test_helpers.py"}

    top = finding.entries[0]
    assert top.rank == 1
    assert (top.code_location.file, top.code_location.symbol) == (
        "shared_defect/totals.py",
        "invoice_total",
    )
    assert not [
        entry for entry in finding.entries if entry.code_location.file.endswith(".py")
        and entry.code_location.file.startswith("tests/")
    ]
    assert finding.metadata["test_file_locations_excluded"] == 7
    assert finding.metadata["test_file_exclusion_basis"] == "path_suffix"
