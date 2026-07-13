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
    REASON_NO_COVERAGE,
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


# ---------------------------------------------------------------------------
# S30 — SBFL score correctness: ANA-10 (dstar2 denominator-zero inversion),
# ANA-11 (outcome-exclusion contract), passing-definition SSoT.
# ---------------------------------------------------------------------------


# All-fail run source for the ANA-10 scenario. ``bug``'s body is covered
# by BOTH failing tests (ef=2, ep=0, nf=0 → D* denominator 0); ``noise``'s
# body by only one (ef=1, nf=1 → finite D* = 1.0).
_ALL_FAIL_SOURCE = (
    "def bug(x):\n"          # line 1
    "    return x - 1\n"     # line 2 — covered by BOTH failing tests
    "\n"
    "def noise(x):\n"        # line 4
    "    return x\n"         # line 5 — covered by ONE failing test
)


def _seed_all_fail_project(
    *,
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
) -> Path:
    """Seed the ANA-10 all-fail run: 2 failing tests, ZERO passing tests."""
    workspace = tmp_path / "ws"
    source_file = workspace / "src" / "allfail.py"
    write_python_module(source_file, _ALL_FAIL_SOURCE)
    clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_af.py::test_one", outcome="failed", duration_ms=1),
        TestResult(node_id="tests/test_af.py::test_two", outcome="failed", duration_ms=1),
    )
    record = make_record(test_results=test_results)
    coverage = make_coverage(
        files=(
            make_file(
                "src/allfail.py",
                {
                    2: (
                        "tests/test_af.py::test_one",
                        "tests/test_af.py::test_two",
                    ),
                    5: ("tests/test_af.py::test_one",),
                },
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    return workspace


def test_dstar2_all_fail_run_ranks_bug_above_noise(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-10 end-to-end: under ``--formula dstar2`` the true bug (covered
    by every failing test, no passing test → denominator 0) ranks STRICTLY
    ABOVE the finite-denominator noise line.

    Pre-S30, the ``denom == 0 → 0.0`` fill scored ``bug`` at 0.0 and
    ``noise`` at 1.0 — the exact ranking inversion of the finding. This
    is the named ANA-10 A/B tripwire at the derive layer.
    """
    workspace = _seed_all_fail_project(
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

    assert len(result.entries) >= 2
    top = result.entries[0]
    assert top.rank == 1
    assert top.code_location.symbol == "bug"
    # ceiling (max finite dstar2 = noise's 1.0) + ef^2 (4) = 5.0.
    assert top.score_raw == pytest.approx(5.0)
    noise_entry = next(
        e for e in result.entries if e.code_location.symbol == "noise"
    )
    assert noise_entry.score_raw == pytest.approx(1.0)
    assert top.score_raw > noise_entry.score_raw


def test_dstar2_all_fail_run_persists_finite_json_floats(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-10 serialization constraint: the maximum-suspicion mapping stays
    finite everywhere — ``score_raw``, ``score_normalized`` AND every
    ``alternate_scores`` value — and the persisted JSON never carries the
    non-standard ``Infinity`` / ``NaN`` tokens."""
    import json
    import math

    workspace = _seed_all_fail_project(
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

    for entry in result.entries:
        assert math.isfinite(entry.score_raw)
        assert math.isfinite(entry.score_normalized)
        for name, value in entry.alternate_scores.items():
            assert math.isfinite(value), f"{name} is not finite: {value!r}"
    # Strict-JSON serialization succeeds (allow_nan=False rejects inf/nan)...
    json.dumps(result.to_dict(), allow_nan=False)
    # ...and the payload persisted by ``write_localization_findings`` has
    # no Infinity/NaN token either.
    raw = localization_findings_path(store, default_ref.run_id).read_text(
        encoding="utf-8"
    )
    assert "Infinity" not in raw
    assert "NaN" not in raw


def test_covered_xpassed_test_does_not_dilute_per_test_suspicion(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-11 end-to-end: an ``xpassed`` test covering the buggy line is
    EXCLUDED from the SBFL sample — it must not count as a passing
    execution (``ep``) of the bug.

    Pre-S30, ``build_spectra`` inferred "not failed ⇒ passed", so the
    covered xpassed test inflated ``ep`` for the buggy line and Ochiai
    dropped from 1.0 to 1/sqrt(2). This is the named ANA-11 A/B tripwire
    at the derive layer.
    """
    workspace = tmp_path / "ws"
    source_file = workspace / "src" / "calc.py"
    write_python_module(source_file, _BUGGY_SOURCE)
    clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_xpass", outcome="xpassed", duration_ms=1),
    )
    record = make_record(test_results=test_results)
    coverage = make_coverage(
        files=(
            make_file(
                "src/calc.py",
                {
                    1: ("tests/test_calc.py::test_safe",),
                    2: ("tests/test_calc.py::test_safe",),
                    # The xpassed test covers the buggy lines too.
                    4: (
                        "tests/test_calc.py::test_buggy",
                        "tests/test_calc.py::test_xpass",
                    ),
                    5: (
                        "tests/test_calc.py::test_buggy",
                        "tests/test_calc.py::test_xpass",
                    ),
                },
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)

    top = result.entries[0]
    assert top.code_location.symbol == "buggy"
    # ef=1, ep=0 (xpassed excluded), nf=0 → Ochiai 1/sqrt(1*1) = 1.0.
    # With the pre-S30 inference ep=1 → 1/sqrt(2) ≈ 0.707.
    assert top.score_raw == pytest.approx(1.0)
    # The excluded test never surfaces as a related failed test either.
    assert "tests/test_calc.py::test_xpass" not in top.related_failed_tests


# ---------------------------------------------------------------------------
# S31 — per-test path robustness: ANA-07 (empty per-test contexts → the
# ``no-coverage`` discriminant, not an exception) and ANA-08 (selected-formula
# score > 0 filter before truncation; all-zero → empty entries).
# ---------------------------------------------------------------------------


def test_per_test_empty_contexts_is_unavailable_no_coverage_not_an_exception(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-07 A/B tripwire (Gate-1 Q2): a fact set claiming per-test
    granularity whose every ``line_contexts`` is EMPTY returns
    ``LocalizationUnavailable(reason="no-coverage")`` — it must NOT let
    ``SpectraBuildError`` ride through the public entry to the CLI
    blanket handler (``cli-error`` / exit 1)."""
    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    # ``mapping_granularity`` defaults to "per-test"; the single covered
    # line carries an empty nodeid tuple — no per-test attribution at all.
    coverage = make_coverage(files=(make_file("src/foo.py", {1: ()}),))
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")

    result = derive_localization_findings(store, default_ref)

    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_NO_COVERAGE
    assert result.detail is not None
    assert "per-test coverage has no line contexts" in result.detail
    # The detail carries the offending run_id for operators.
    assert default_ref.run_id in result.detail
    # Unavailable outcomes are never cached — a later (repaired) derive
    # must re-attempt the pipeline rather than replay this state.
    assert not localization_findings_path(store, default_ref.run_id).exists()


def test_per_test_zero_score_symbols_never_pad_entries(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-08 A/B tripwire (Gate-1 Q3a): symbols whose selected-formula
    score is 0 are filtered BEFORE truncation. The buggy fixture yields
    ``buggy`` (ef=1 → Ochiai 1.0) and ``safe`` (ef=0 → Ochiai 0.0);
    pre-S31 the ``safe`` symbol padded ``entries`` with
    ``score_raw == 0.0`` noise."""
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

    # Exactly the one positive-score symbol — no zero-score padding.
    assert [e.code_location.symbol for e in result.entries] == ["buggy"]
    for entry in result.entries:
        assert entry.score_raw > 0
    # With the noise gone there is nothing to tie with.
    assert result.entries[0].tied_with == ()


def test_per_test_all_zero_scores_yield_empty_entries(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-08 (Gate-1 Q3a): when every candidate's selected-formula score
    is 0 — here the failing test executed NO covered line, so ef=0
    everywhere — the finding is returned with EMPTY ``entries``: the
    honest "no suspects". The ranking/tie assembly must tolerate the
    empty case."""
    workspace = tmp_path / "ws"
    source_file = workspace / "src" / "calc.py"
    write_python_module(source_file, _BUGGY_SOURCE)
    clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1),
    )
    record = make_record(test_results=test_results)
    # Only the PASSING test appears in the line contexts — the failing
    # test contributes an all-zero row, so ef=0 for every location.
    coverage = make_coverage(
        files=(
            make_file(
                "src/calc.py",
                {
                    1: ("tests/test_calc.py::test_safe",),
                    2: ("tests/test_calc.py::test_safe",),
                },
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")

    result = derive_localization_findings(store, default_ref)

    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_per_test"
    assert result.entries == ()


def test_aggregate_filter_and_score_values_unchanged_by_s31(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """S31 regression pin: the aggregate path's own >0 filter and score
    values are byte-stable across the per-test filter change. One file
    is mentioned by the failing trace (ef=1, ep=1 → Ochiai 1/sqrt(2));
    a second covered-but-unmentioned file (ef=0) stays filtered out."""
    import math

    workspace = tmp_path / "ws"
    record = make_record(
        test_results=(
            TestResult(
                node_id="tests/a.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:7: AssertionError",
            ),
            TestResult(node_id="tests/a.py::t_ok", outcome="passed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(
            make_file("src/foo.py", {1: ()}),
            make_file("src/bar.py", {1: ()}),
        ),
        mapping_granularity="aggregate",
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")

    result = derive_localization_findings(store, default_ref)

    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_aggregate"
    # Exactly the trace-mentioned file; the ef=0 file never pads.
    assert [e.code_location.file for e in result.entries] == ["src/foo.py"]
    # Value pin: ef=1, ep=1, nf=0, np=0 → Ochiai 1/sqrt((1+0)*(1+1)).
    assert result.entries[0].score_raw == pytest.approx(1.0 / math.sqrt(2.0))


def test_decorator_line_location_gains_symbol_precision(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
) -> None:
    """ANA-22 at the finding layer (Gate-1 Q3b): a suspicious line ON a
    decorator resolves to the decorated function (``kind: "symbol"``)
    instead of degrading to ``kind: "file"``."""
    workspace = tmp_path / "ws"
    source = (
        "def deco(f):\n"     # line 1
        "    return f\n"     # line 2
        "\n"
        "@deco\n"            # line 4 — the suspicious decorator line
        "def buggy():\n"     # line 5
        "    return 0\n"     # line 6
    )
    source_file = workspace / "src" / "decorated.py"
    write_python_module(source_file, source)
    clear_resolver_cache()

    record = make_record(
        test_results=(
            TestResult(node_id="tests/test_d.py::test_fail", outcome="failed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(
            make_file(
                "src/decorated.py",
                {4: ("tests/test_d.py::test_fail",)},
            ),
        ),
    )
    seed_store(workspace, record=record, coverage=coverage)
    store = get_project_store_state(workspace / ".novetest")

    result = derive_localization_findings(store, default_ref)

    assert isinstance(result, LocalizationFinding)
    assert len(result.entries) == 1
    location = result.entries[0].code_location
    assert location.kind == "symbol"
    assert location.symbol == "buggy"
    assert location.line_range == (4, 6)


# ---------------------------------------------------------------------------
# S30 — passing-definition SSoT: both SBFL modes draw the passing sample
# from the ONE ``_passed_test_ids`` helper (strictly ``passed``).
# ---------------------------------------------------------------------------


def test_passed_outcomes_ssot_value_is_pinned() -> None:
    """The Localization passing bucket is exactly ``{"passed"}`` — a future
    vocabulary change must be a loud, deliberate edit to THIS line (and a
    re-read of the ANA-11 exclusion contract)."""
    assert derive._PASSED_OUTCOMES == frozenset({"passed"})


def test_both_sbfl_modes_source_passing_from_the_shared_helper(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    seed_store: Callable[..., object],
    default_ref: RunReference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wiring pin: ``_derive_per_test`` AND ``_derive_aggregate`` both call
    ``derive._passed_test_ids`` — re-inlining a local passing definition in
    either mode (the pre-S30 divergence) fails this test loudly."""
    calls: list[str] = []
    real = derive._passed_test_ids

    def _spy(record: RunRecord) -> frozenset[str]:
        calls.append(record.run_reference.run_id)
        return real(record)

    monkeypatch.setattr(derive, "_passed_test_ids", _spy)

    # Per-test mode.
    per_test_ws = _seed_buggy_project(
        tmp_path=tmp_path / "per_test",
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
        seed_store=seed_store,
    )
    store = get_project_store_state(per_test_ws / ".novetest")
    result = derive_localization_findings(store, default_ref)
    assert isinstance(result, LocalizationFinding)
    assert result.mode == "sbfl_per_test"
    assert calls, "per-test mode must resolve passing via _passed_test_ids"

    # Aggregate mode.
    calls.clear()
    agg_ws = tmp_path / "aggregate" / "ws"
    record = make_record(
        test_results=(
            TestResult(
                node_id="tests/a.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:7: AssertionError",
            ),
            TestResult(node_id="tests/a.py::t_ok", outcome="passed", duration_ms=1),
        ),
    )
    coverage = make_coverage(
        files=(make_file("src/foo.py", {1: ()}),),
        mapping_granularity="aggregate",
    )
    seed_store(agg_ws, record=record, coverage=coverage)
    agg_store = get_project_store_state(agg_ws / ".novetest")
    agg_result = derive_localization_findings(agg_store, default_ref)
    assert isinstance(agg_result, LocalizationFinding)
    assert agg_result.mode == "sbfl_aggregate"
    assert calls, "aggregate mode must resolve passing via _passed_test_ids"


def test_no_inline_passed_literal_comparison_in_sbfl_modules() -> None:
    """Source guard: neither ``derive.py`` nor ``sbfl/spectra.py`` compares
    an outcome against an inline ``"passed"`` literal — the ONLY home of
    the passing definition is ``_PASSED_OUTCOMES`` / ``_passed_test_ids``
    (mirrors the S25 FAIL_LIKE_OUTCOMES SSoT posture)."""
    import ast

    from novetest.localization.sbfl import spectra as spectra_module

    for module in (derive, spectra_module):
        module_file = module.__file__
        assert module_file is not None
        tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            for operand in operands:
                assert not (
                    isinstance(operand, ast.Constant) and operand.value == "passed"
                ), (
                    f"{module.__name__} line {node.lineno}: inline 'passed' "
                    "comparison — use the _passed_test_ids SSoT instead"
                )
