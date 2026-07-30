"""Test-file exclusion inside the two SBFL derivation paths.

Companion to ``test_candidate_filter.py`` (which unit-tests the filter
primitives in isolation). Here the filter is exercised through the real
``derive_localization_findings`` / ``_derive_aggregate`` pipelines, on a
miniature of the shape observed in wave-1 persona P1:

- more than one failing test, so a single failing test's own body carries
  ``nf > 0``;
- a defect line executed by passing tests too, so it carries ``ep > 0``.

The first test in this module is the CHARACTERIZATION: it pins the raw
``ef``/``ep``/``nf``/``np`` counts that make a failing test's own body
outscore the defect, independently of the fix. If the fix were reverted,
that test would still pass and every other test here would fail — which
is exactly the intended split between "why it happens" and "what we do
about it".
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.derive import (
    _compute_all_formula_scores,
    _count_vectors,
    _derive_aggregate,
    derive_localization_findings,
)
from novetest.localization.sbfl.spectra import build_spectra
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# ---------------------------------------------------------------------------
# The miniature "shared defect" project
# ---------------------------------------------------------------------------

_SOURCE = (
    "def invoice_total(sub, disc, tax):\n"   # line 1
    "    return sub - disc + sub * tax\n"    # line 2 — the defect
    "\n"
    "def helper(x):\n"                       # line 4
    "    return x\n"                         # line 5
)

_TEST_SOURCE = (
    "def test_a():\n"           # 1
    "    assert True\n"         # 2
    "\n"
    "def test_b():\n"           # 4
    "    assert True\n"         # 5
    "\n"
    "def test_c():\n"           # 7
    "    assert True\n"         # 8
    "\n"
    "def test_fail_1():\n"      # 10
    "    assert False\n"        # 11
    "\n"
    "def test_fail_2():\n"      # 13
    "    assert False\n"        # 14
)

_PASSING = (
    "tests/test_calc.py::test_a",
    "tests/test_calc.py::test_b",
    "tests/test_calc.py::test_c",
)
_FAILING = (
    "tests/test_calc.py::test_fail_1",
    "tests/test_calc.py::test_fail_2",
)
_ALL = _PASSING + _FAILING

_SOURCE_FILE = "src/calc.py"
_TEST_FILE = "tests/test_calc.py"

# ``invoice_total`` (lines 1-2, holding the defect) is executed by EVERY
# test — 3 passing + 2 failing. ``helper`` (lines 4-5) is executed by the
# passing tests only, so it scores 0 and drops out as unsuspicious. Each
# failing test's own body is executed only by itself.
_SOURCE_CONTEXTS: dict[int, tuple[str, ...]] = {
    1: _ALL,
    2: _ALL,
    4: _PASSING,
    5: _PASSING,
}
_TEST_CONTEXTS: dict[int, tuple[str, ...]] = {
    2: (_PASSING[0],),
    5: (_PASSING[1],),
    8: (_PASSING[2],),
    11: (_FAILING[0],),
    14: (_FAILING[1],),
}


def _seed(
    *,
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    source_contexts: dict[int, tuple[str, ...]] | None = None,
    test_contexts: dict[int, tuple[str, ...]] | None = None,
) -> tuple[Path, RunRecord, CoverageFactSet]:
    """Materialize the miniature project + its per-test Coverage Facts."""
    workspace = tmp_path / "ws"
    write_python_module(workspace / _SOURCE_FILE, _SOURCE)
    write_python_module(workspace / _TEST_FILE, _TEST_SOURCE)
    clear_resolver_cache()

    record = make_record(
        test_results=tuple(
            TestResult(
                node_id=nid,
                outcome="failed" if nid in _FAILING else "passed",
                duration_ms=1,
            )
            for nid in _ALL
        )
    )
    coverage = make_coverage(
        files=(
            make_file(_SOURCE_FILE, source_contexts or _SOURCE_CONTEXTS),
            make_file(_TEST_FILE, test_contexts or _TEST_CONTEXTS),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    return workspace, record, coverage


# ---------------------------------------------------------------------------
# Characterization — the mechanism, independent of the fix
# ---------------------------------------------------------------------------


def test_characterization_failing_test_body_outscores_the_defect(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
) -> None:
    """Why SBFL puts the failing tests on top — in raw counts.

    A failing test's own body is executed by exactly ONE failing test and
    by NO passing test (``ef=1, ep=0``). The defect it exposes is executed
    by the passing tests too (``ef=2, ep=3``). Under Ochiai, ``ep=0`` wins:
    0.7071 > 0.6325. Structural, not project-specific.

    (Ochiai = ``ef / sqrt((ef+nf) * (ef+ep))``, so ``np`` never enters the
    score — which is why 3 passing tests here reproduce the same two
    numbers the 5-passing-test wave-1 shape produced.)
    """
    _, record, coverage = _seed(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    spectra = build_spectra(coverage, frozenset(_FAILING), frozenset(_PASSING))
    ef, ep, nf, np_ = _count_vectors(spectra)
    ochiai = _compute_all_formula_scores((ef, ep, nf, np_))["ochiai"]
    index = {loc: j for j, loc in enumerate(spectra.locations)}

    defect = index[(_SOURCE_FILE, 2)]
    test_body = index[(_TEST_FILE, 11)]

    assert (int(ef[defect]), int(ep[defect]), int(nf[defect]), int(np_[defect])) == (
        2,
        3,
        0,
        0,
    )
    assert (
        int(ef[test_body]),
        int(ep[test_body]),
        int(nf[test_body]),
        int(np_[test_body]),
    ) == (1, 0, 1, 3)
    assert ochiai[defect] == pytest.approx(2 / (10**0.5))       # 0.6325
    assert ochiai[test_body] == pytest.approx(1 / (2**0.5))     # 0.7071
    assert ochiai[test_body] > ochiai[defect], (
        "characterization broken: the whole point is that a failing test's "
        "own body outscores the defect before the exclusion"
    )


# ---------------------------------------------------------------------------
# sbfl_per_test — the fix
# ---------------------------------------------------------------------------


def test_per_test_mode_ranks_the_defect_first_and_drops_test_files(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """No entry lives in a test file; the defect symbol is rank 1."""
    workspace, _, _ = _seed(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    finding = derive_localization_findings(store, default_ref)
    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "sbfl_per_test"

    assert [e.code_location.file for e in finding.entries] == [_SOURCE_FILE] * len(
        finding.entries
    )
    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.symbol == "invoice_total"
    assert top.score_raw == pytest.approx(2 / (10**0.5))


def test_per_test_mode_normalizes_and_ranks_on_the_filtered_set(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Ranks are dense + 1-based over real suspects, and the excluded
    0.7071 entry does not define the top of the [0, 1] range.

    Pre-fix the defect sat at rank 2 with ``score_normalized == 0.894``
    (0.6325 / 0.7071) — the wave-1 P1 number. Post-fix it is rank 1 at
    1.0 because the range is computed on the surviving candidates.
    """
    workspace, _, _ = _seed(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    finding = derive_localization_findings(store, default_ref)
    assert isinstance(finding, LocalizationFinding)

    top = finding.entries[0]
    assert top.rank == 1
    assert top.score_normalized == pytest.approx(1.0)
    assert [e.rank for e in finding.entries] == sorted(e.rank for e in finding.entries)
    assert finding.entries[0].rank == 1


def test_per_test_mode_reports_the_exclusion_in_metadata(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """The exclusion is auditable: "filtered N" vs "found nothing"."""
    workspace, _, _ = _seed(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    finding = derive_localization_findings(store, default_ref)
    assert isinstance(finding, LocalizationFinding)

    # 5 test-function symbols in tests/test_calc.py were dropped.
    assert finding.metadata["test_file_locations_excluded"] == 5
    assert finding.metadata["test_file_exclusion_reverted"] is False
    # Node-id paths met candidate paths head-on — no re-key was needed, so
    # ``excluded: 0`` would have meant "nothing to drop", not "no match".
    assert finding.metadata["test_file_exclusion_basis"] == "exact"
    # Nothing is deleted silently: the two failing test bodies were the
    # only removals that scored above zero, and they are named with the
    # score they would have ranked at.
    assert finding.metadata["test_file_locations_suppressed"] == [
        {
            "file": _TEST_FILE,
            "symbol": "test_fail_1",
            "score_raw": pytest.approx(1 / (2**0.5)),
        },
        {
            "file": _TEST_FILE,
            "symbol": "test_fail_2",
            "score_raw": pytest.approx(1 / (2**0.5)),
        },
    ]
    # Base keys unchanged (mode-invariant metadata contract).
    assert finding.metadata["changed_files_count"] is None
    assert finding.metadata["regression_reweighted"] is None


def test_per_test_mode_reverts_when_only_test_files_are_suspicious(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Defect really in the test file → ranking survives, flag surfaces.

    Source lines are executed by every test here (``ef=2, ep=3`` gives a
    positive Ochiai) — so to build the "only test files are suspicious"
    state the source is covered by the PASSING tests only (``ef=0`` →
    Ochiai 0). The user must not get an empty ``entries`` list.
    """
    workspace, _, _ = _seed(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
        source_contexts={1: _PASSING, 2: _PASSING, 4: _PASSING, 5: _PASSING},
    )
    store = get_project_store_state(workspace / ".novetest")
    finding = derive_localization_findings(store, default_ref)
    assert isinstance(finding, LocalizationFinding)

    assert finding.entries, "reverting exists precisely to avoid silence"
    assert finding.metadata["test_file_exclusion_reverted"] is True
    assert finding.metadata["test_file_locations_excluded"] == 5
    assert finding.entries[0].code_location.file == _TEST_FILE
    assert finding.entries[0].rank == 1


# ---------------------------------------------------------------------------
# sbfl_aggregate — the same rule on Path B
# ---------------------------------------------------------------------------


def _aggregate_summary(num: int) -> CoverageSummary:
    return CoverageSummary(
        num_statements=num,
        covered_statements=num,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


def _aggregate_file(file_path: str) -> FileCoverage:
    return FileCoverage(
        file_path=file_path,
        executed_lines=(1, 2),
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_aggregate_summary(2),
        line_contexts={},
    )


def _seed_aggregate(
    tmp_path: Path, *, covered_files: tuple[str, ...], failure_text: str
) -> tuple[object, RunRecord, CoverageFactSet]:
    """One failing + one passing test, aggregate coverage, both files covered."""
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    ref = RunReference(
        run_id="01HAGGEXCL00000000000000001", created_at=1_700_000_000_000
    )
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version=None,
        ecosystem="python",
        status="failed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(
                node_id="tests/test_calc.py::test_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference=failure_text,
            ),
            TestResult(
                node_id="tests/test_calc.py::test_ok", outcome="passed", duration_ms=1
            ),
        ),
    )
    store_run_evidence(store, record)
    coverage = CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="aggregate",
        summary=_aggregate_summary(2 * len(covered_files)),
        files=tuple(_aggregate_file(fp) for fp in covered_files),
        derived_at=ref.created_at + 500,
    )
    write_coverage_facts(store, coverage)
    return get_project_store_state(workspace / ".novetest"), record, coverage


def test_aggregate_mode_drops_the_test_file_named_by_its_own_traceback(
    tmp_path: Path,
) -> None:
    """A pytest traceback always names the failing test's own file.

    Aggregate mode derives ``ef`` from those frames, so the test file
    collects a hit from every failing test and outranks the source file
    it points at. The exclusion removes it; the source file becomes
    rank 1.
    """
    store, record, coverage = _seed_aggregate(
        tmp_path,
        covered_files=("tests/test_calc.py", "src/calc.py", "src/other.py"),
        failure_text="tests/test_calc.py:11: in test_bug\nsrc/calc.py:2: AssertionError",
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/test_calc.py::test_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert finding.mode == "sbfl_aggregate"
    assert [e.code_location.file for e in finding.entries] == ["src/calc.py"]
    assert finding.entries[0].rank == 1
    assert finding.metadata["test_file_locations_excluded"] == 1
    assert finding.metadata["test_file_exclusion_reverted"] is False
    assert finding.metadata["test_file_exclusion_basis"] == "exact"
    # Aggregate mode ranks FILES, so the suppressed suspect carries no
    # symbol — the mode has none to report (and none to narrow with).
    assert finding.metadata["test_file_locations_suppressed"] == [
        {
            "file": "tests/test_calc.py",
            "symbol": None,
            "score_raw": pytest.approx(1 / (2**0.5)),
        }
    ]
    # Base keys unchanged.
    assert finding.metadata["regression_reweighted"] is False
    assert finding.metadata["changed_files_count"] == 0


def test_aggregate_mode_reverts_when_the_trace_names_only_the_test_file(
    tmp_path: Path,
) -> None:
    """The failure_proximity-shaped case: nothing but the test file.

    Rather than an empty ranking, the unfiltered result comes back with
    ``test_file_exclusion_reverted: True``.
    """
    store, record, coverage = _seed_aggregate(
        tmp_path,
        covered_files=("tests/test_calc.py", "src/calc.py"),
        failure_text="tests/test_calc.py:11: AssertionError",
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/test_calc.py::test_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert [e.code_location.file for e in finding.entries] == ["tests/test_calc.py"]
    assert finding.metadata["test_file_exclusion_reverted"] is True
    assert finding.metadata["test_file_locations_excluded"] == 1


def test_aggregate_mode_is_a_no_op_when_no_test_file_is_covered(
    tmp_path: Path,
) -> None:
    """Coverage that excludes test files → nothing to drop, flags at zero."""
    store, record, coverage = _seed_aggregate(
        tmp_path,
        covered_files=("src/calc.py", "src/other.py"),
        failure_text="src/calc.py:2: AssertionError",
    )
    finding = _derive_aggregate(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=frozenset({"tests/test_calc.py::test_bug"}),
        regression_facts=None,
        top_n=10,
        formula="ochiai",
    )
    assert [e.code_location.file for e in finding.entries] == ["src/calc.py"]
    assert finding.metadata["test_file_locations_excluded"] == 0
    assert finding.metadata["test_file_exclusion_reverted"] is False
    # ``basis: none`` is what tells a reader this ``0`` is "the test file
    # was never a candidate", not "the paths failed to line up".
    assert finding.metadata["test_file_exclusion_basis"] == "none"
    assert finding.metadata["test_file_locations_suppressed"] == []
