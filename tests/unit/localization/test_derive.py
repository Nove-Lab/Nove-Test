"""``derive_localization_findings`` — the orchestrating function.

Each branch of the §7 pipeline gets coverage: not-found, tombstoned, no
failed tests, coverage unavailable, coverage-not-per-test, happy-path
(ranking + normalization + ties + truncation), cache-on-second-call.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.localization import derive
from novetest.localization.derive import derive_localization_findings
from novetest.localization.persistence import localization_findings_path
from novetest.localization.results import (
    REASON_NO_FAILED_TESTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.models.coverage_fact_set import CoverageFactSet, FileCoverage
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# Project source written by ``write_python_module`` for the happy-path
# tests. Defines three functions; the ``buggy`` one is the deliberate
# fault target.
_BUGGY_SOURCE = (
    "def safe(x):\n"          # line 1
    "    return x + 1\n"      # line 2
    "\n"
    "def buggy(x):\n"         # line 4
    "    return x * 0\n"      # line 5 — the bug
    "\n"
    "def neutral(x):\n"       # line 7
    "    return x\n"          # line 8
)


def _seed_buggy_project(
    *,
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    tombstone: bool = False,
) -> Path:
    """Seed a Project Store with 2 passing tests on ``safe`` + 1 failing on ``buggy``.

    Per-test coverage attribution makes the buggy function the high-
    suspicion target under Ochiai (ef=1, ep=0, nf=0, np_=2 → 1.0).
    """
    workspace = tmp_path / "ws"
    source_file = workspace / "src" / "calc.py"
    write_python_module(source_file, _BUGGY_SOURCE)
    clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_other_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1),
    )
    record = make_record(test_results=test_results)
    coverage = make_coverage(
        files=(
            make_file(
                "src/calc.py",
                {
                    1: ("tests/test_calc.py::test_safe", "tests/test_calc.py::test_other_safe"),
                    2: ("tests/test_calc.py::test_safe", "tests/test_calc.py::test_other_safe"),
                    4: ("tests/test_calc.py::test_buggy",),
                    5: ("tests/test_calc.py::test_buggy",),
                },
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage, tombstone=tombstone)
    return workspace


def test_no_run_evidence(tmp_path: Path) -> None:
    """Unknown run_id → REASON_NO_RUN_EVIDENCE."""
    store = create_project_store(tmp_path)
    unknown = RunReference(
        run_id="01HUNKNOWN0000000000000000", created_at=1_700_000_000_000
    )
    result = derive_localization_findings(store, unknown)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_NO_RUN_EVIDENCE


def test_tombstoned_run_not_analyzable(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
        tombstone=True,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_RUN_NOT_ANALYZABLE


def test_no_failed_tests(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="passed", duration_ms=1),
        ),
    )
    seed_store(workspace, record=record, coverage=None)
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_NO_FAILED_TESTS


def test_coverage_unavailable_routes_to_failure_proximity(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """No coverage + failed tests → Path C (``failure_proximity``).

    Strategy doc §2 + §5: when failed tests exist but coverage does not,
    return ``failure_proximity`` (with ``confidence: "low"``) rather than
    Unavailable — that is the degraded fallback per the design's "one
    nuance" rule.
    """
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(
                node_id="tests/a.py::t",
                outcome="failed",
                duration_ms=1,
                # Pytest-style inline failure_reference so the parser can
                # extract a (file, line) tuple for the ranking.
                failure_reference="src/foo.py:42: AssertionError",
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=None)
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "failure_proximity"
    assert result.confidence == "low"
    # Brief §7 deviation: failure_proximity carries empty alternate_scores_available.
    assert result.alternate_scores_available == ()


def test_coverage_aggregate_routes_to_sbfl_aggregate(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Aggregate coverage + failed tests → Path B (``sbfl_aggregate``).

    Strategy doc §2: granularity in
    {"aggregate", "per-test-file", "per-test-class"} routes to
    sbfl_aggregate. Confidence is ``"medium"`` per the table; the
    failure-only Ochiai floor is the default sub-variant (no Regression
    Facts present in this fixture).
    """
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(
                node_id="tests/a.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:7: AssertionError",
            ),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ()}),),
        mapping_granularity="aggregate",
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_aggregate"
    assert result.confidence == "medium"
    # All four formulas should be available (no deviation for sbfl_aggregate).
    assert set(result.alternate_scores_available) == {"op2", "dstar2", "tarantula"}


def test_per_test_happy_path_ranks_buggy_function_top(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_per_test"
    assert result.confidence == "high"
    assert result.formula == "ochiai"
    assert set(result.alternate_scores_available) == {"op2", "dstar2", "tarantula"}

    assert len(result.entries) >= 1
    top = result.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "symbol"
    assert top.code_location.symbol == "buggy"
    assert top.code_location.file == "src/calc.py"
    assert top.score_raw == pytest.approx(1.0)
    assert top.score_normalized == pytest.approx(1.0)
    assert set(top.alternate_scores.keys()) == {"op2", "dstar2", "tarantula"}
    assert "tests/test_calc.py::test_buggy" in top.related_failed_tests
    kinds = {c.kind for c in top.evidence_citations}
    assert kinds == {"test_result", "coverage_fact"}


def test_per_test_writes_canonical_path(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    target = localization_findings_path(store, default_ref.run_id)
    assert target.is_file()


def test_per_test_cache_hit_does_not_re_derive(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second ``derive_localization_findings`` call reads cache, not the pipeline."""
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    first = derive_localization_findings(store, default_ref)
    assert isinstance(first, LocalizationFinding)

    def _must_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("build_spectra should not be called on a cache hit")

    monkeypatch.setattr(derive, "build_spectra", _must_not_run)

    second = derive_localization_findings(store, default_ref)
    assert isinstance(second, LocalizationFinding)
    assert second == first


def test_top_n_truncation(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref, top_n=1)
    assert isinstance(result, LocalizationFinding)
    assert len(result.entries) <= 1
    assert result.top_n == 1


def test_non_default_formula_drives_ranking(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref, formula="dstar2")
    assert isinstance(result, LocalizationFinding)
    assert result.formula == "dstar2"
    assert "ochiai" in result.alternate_scores_available
    assert "dstar2" not in result.alternate_scores_available
    for entry in result.entries:
        assert "dstar2" not in entry.alternate_scores


def test_persisted_payload_round_trips(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    import json

    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    fresh = derive_localization_findings(store, default_ref)
    assert isinstance(fresh, LocalizationFinding)
    target = localization_findings_path(store, default_ref.run_id)
    raw = json.loads(target.read_text(encoding="utf-8"))
    restored = LocalizationFinding.from_dict(raw)
    assert restored == fresh


def test_file_level_fallback_for_module_level_code(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """Lines outside any function fall back to ``CodeLocation(kind="file")``."""
    workspace = tmp_path / "ws"
    source = (
        "GLOBAL = 42\n"            # line 1 — module-level
        "\n"
        "def compute_global():\n"  # line 3
        "    return GLOBAL\n"      # line 4
    )
    source_file = workspace / "src" / "modlevel.py"
    write_python_module(source_file, source)
    clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_modlevel.py::test_fail", outcome="failed", duration_ms=1),
    )
    record = make_record(test_results=test_results)
    coverage = make_coverage(
        files=(
            make_file(
                "src/modlevel.py",
                {1: ("tests/test_modlevel.py::test_fail",)},
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert len(result.entries) >= 1
    file_entry = next(
        (e for e in result.entries if e.code_location.kind == "file"), None
    )
    assert file_entry is not None
    assert file_entry.code_location.symbol is None
    assert file_entry.code_location.line_range is None


# ---------------------------------------------------------------------------
# B2-1 metadata shape normalization (UX, 2026-06-08)
# ---------------------------------------------------------------------------


def test_per_test_metadata_has_mode_invariant_keys_with_none_values(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """B2-1: per-test mode emits the same ``metadata`` key set as the
    aggregate / failure_proximity modes (``changed_files_count`` +
    ``regression_reweighted``) with ``None`` values.

    The asymmetry pre-2026-06-08 was that ``sbfl_per_test`` returned an
    empty ``metadata`` dict, while ``sbfl_aggregate`` /
    ``failure_proximity`` returned the two regression-tracking keys.
    AI consumers had to branch on ``finding.mode`` before reading
    metadata. Post-normalization the three modes share a single key set
    contract.

    ``None`` (vs ``0`` / ``False``) is the principled discriminator:
    per-test mode does NOT consult Regression Facts (no FLUCCS
    reweighting in this mode per strategy doc §2), so ``None`` reads
    as "this mode does not consult Regression Facts at all" — distinct
    from the aggregate / failure_proximity modes returning ``0`` /
    ``False`` when Regression Facts are absent or the change set is
    empty.

    Spec pinned in ``design/interace-contract/localization.md``
    §"Result shape — mode-invariant".
    """
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_per_test"

    # Both base keys present.
    assert "changed_files_count" in result.metadata
    assert "regression_reweighted" in result.metadata
    # Both base keys have None values (per-test mode does not consult
    # RegressionFactSet — structural noop discriminator).
    assert result.metadata["changed_files_count"] is None
    assert result.metadata["regression_reweighted"] is None


def test_per_test_metadata_survives_persistence_roundtrip(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """B2-1: the per-test normalized ``metadata`` keys survive
    ``LocalizationFinding.to_dict()`` → JSON → ``from_dict()`` so the
    cache reader returns the same shape the producer wrote.

    The persistence-layer ``write_localization_findings`` /
    ``read_localization_findings_raw`` pair is the same path
    ``derive_localization_findings`` follows on cache hit; pinning the
    roundtrip explicitly prevents a future ``dict[str, Any]`` →
    ``dict[str, SomethingTighter`` refactor from accidentally dropping
    ``None`` values during JSON serialization.
    """
    workspace = _seed_buggy_project(
        tmp_path=tmp_path,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(workspace / ".novetest")
    derive_localization_findings(store, default_ref)
    # Second call goes through the cache reader.
    cached = derive_localization_findings(store, default_ref)
    assert isinstance(cached, LocalizationFinding)
    assert cached.mode == "sbfl_per_test"
    assert cached.metadata["changed_files_count"] is None
    assert cached.metadata["regression_reweighted"] is None
