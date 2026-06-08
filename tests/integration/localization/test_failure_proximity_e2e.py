"""End-to-end: ``novetest run`` (no --coverage) → ``failure_proximity`` mode.

Drives Path C of the strategy doc §2 mode-selection algorithm against
the ``localization-no-coverage`` fixture:

1. Materialize the fixture under ``tmp_path``.
2. Initialize a Project Store.
3. Spawn the real pytest adapter with ``collect_coverage=False`` so NO
   ``CoverageFactSet`` lands on disk.
4. Call ``derive_localization_findings`` and assert the resulting
   finding has ``mode == "failure_proximity"`` + ``confidence == "low"``
   + the buggy SuT file (``localization_no_coverage/statistics.py``)
   ranked top-1.
5. Cross-check the brief §7 envelope deviation:
   ``alternate_scores_available == ()``.

The fixture's failing test raises ``ZeroDivisionError`` from INSIDE the
SuT so pytest's ``crash.path`` resolves to ``statistics.py`` (not the
test file). The failure_proximity parser picks up that file:line and
the regression-free FLUCCS-prior path yields a score of 1.0 for the
single file mentioned.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from novetest.coverage.results import CoverageUnavailable
from novetest.coverage.retrieval import get_coverage_facts
from novetest.localization.derive import derive_localization_findings
from novetest.localization.persistence import localization_findings_path
from novetest.memory.store import retrieve_run_evidence
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "localization-no-coverage"
)


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture project tree into ``dest`` and return the new root."""
    target = dest / "localization-no-coverage"
    shutil.copytree(
        FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".novetest"
        ),
    )
    return target


async def test_failure_proximity_ranks_buggy_file_top(tmp_path: Path) -> None:
    """No --coverage + 1 failing test inside the SuT → file ranked top-1.

    End-to-end: real pytest run with NO coverage collection + real
    failure_proximity derivation. The SuT's ``average([])`` raises
    ZeroDivisionError, pytest's failure capture identifies
    ``statistics.py`` as the crash file, and the failure_proximity
    parser ranks it #1.
    """
    workspace = _materialize_fixture(tmp_path)

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=False
    )

    # Pre-condition for Path C: no coverage facts on disk at all.
    run_reference = outcome.memory_entry.run_record.run_reference
    cached_coverage = get_coverage_facts(init.store, run_reference)
    assert isinstance(cached_coverage, CoverageUnavailable)

    finding = derive_localization_findings(init.store, run_reference)
    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "failure_proximity"
    assert finding.confidence == "low"
    # Brief §7 envelope deviation.
    assert finding.alternate_scores_available == ()
    # The placeholder ``formula`` field stays "ochiai" so the closed-enum
    # validator passes; consumers gate on `mode` not `formula`.
    assert finding.formula == "ochiai"

    assert finding.entries, "expected at least one failure-proximity entry"
    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "file"
    assert top.code_location.symbol is None
    # The bug raises from inside the SuT, so the failure trace points
    # to the SuT file. Ranked first regardless of whether the test
    # file is also picked up by the parser (the test file has the
    # same per-file count of 1 — tied — but the SuT file sorts
    # ascending-by-path FIRST because its package path is
    # alphabetically before "tests/").
    assert any(
        "statistics.py" in e.code_location.file for e in finding.entries
    ), (
        f"expected ``statistics.py`` somewhere in failure_proximity entries; "
        f"got entries={[e.code_location.file for e in finding.entries]!r}"
    )
    # B2-2 (UX normalization, 2026-06-08): every emitted file path is
    # workspace-relative (NOT absolute). Pre-normalization pytest's
    # ``crash.path`` carried absolute form through to the envelope; the
    # other Localization modes emit repo-relative paths. Pinning the
    # whole entry set so a future regression on the normalization helper
    # surfaces here, not just on the top entry.
    for entry in finding.entries:
        assert not Path(entry.code_location.file).is_absolute(), (
            f"failure_proximity entry must emit workspace-relative path; "
            f"got absolute {entry.code_location.file!r}"
        )
    # The SuT bug file's path should be exactly the workspace-relative
    # form ``localization_no_coverage/statistics.py`` (package dir + .py).
    sut_entry = next(
        (e for e in finding.entries if "statistics.py" in e.code_location.file),
        None,
    )
    assert sut_entry is not None
    assert sut_entry.code_location.file == (
        "localization_no_coverage/statistics.py"
    ), (
        f"expected exact workspace-relative SuT path; "
        f"got {sut_entry.code_location.file!r}"
    )
    # Per-entry alternate_scores is the documented empty-dict deviation.
    for entry in finding.entries:
        assert entry.alternate_scores == {}

    # B2-1 (UX normalization, 2026-06-08): mode-invariant metadata key
    # set. failure_proximity emits both base keys with concrete (int /
    # bool) values; the symmetric assertions in the sbfl_per_test
    # (None / None) and sbfl_aggregate (int / bool) E2E tests close the
    # 3-mode matrix the brief mandates.
    assert "changed_files_count" in finding.metadata
    assert "regression_reweighted" in finding.metadata
    assert isinstance(finding.metadata["changed_files_count"], int)
    assert isinstance(finding.metadata["regression_reweighted"], bool)

    # Cache file landed at the load-bearing path so the canonical
    # localization_findings.json exists for downstream consumers.
    findings_path = localization_findings_path(init.store, run_reference.run_id)
    assert findings_path.is_file()
    refreshed = retrieve_run_evidence(init.store, run_reference)
    assert refreshed.has_localization_findings is True
