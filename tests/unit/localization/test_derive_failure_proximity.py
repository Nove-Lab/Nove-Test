"""``derive_failure_proximity`` mode — unit tests.

The ``failure_proximity`` mode is the no-coverage fallback. Inputs:

- ``record`` with failing tests whose ``failure_reference`` (inline for
  pytest/jest; on-disk for cargo/gotest) contains parseable file:line
  tuples.
- Optional ``regression_facts`` for the FLUCCS-style regression-aware
  prior (``score *= 1 + 0.5`` for files in the change set).

Output: a ``LocalizationFinding`` with:

- ``mode == "failure_proximity"`` and ``confidence == "low"``.
- Brief §7 deviation: ``alternate_scores_available == ()`` and per-entry
  ``alternate_scores == {}``.
- File-level ``CodeLocation`` (``kind == "file"``, ``symbol = None``).
- Per-file scores = count of failing tests mentioning the file (with
  regression boost when applicable).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.localization.failure_proximity import derive_failure_proximity
from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


def _make_run(
    *,
    workspace: Path,
    test_results: tuple[TestResult, ...],
    engine_name: str = "pytest",
    run_id: str = "01HFP000000000000000000001",
) -> tuple[object, RunRecord]:
    """Materialize a Project Store seeded with a single Run Record.

    Returns ``(store, record)``. The record is built locally (no
    ``conftest`` fixture) because failure_proximity mode tests vary
    ``engine_name`` and ``failure_reference`` shapes per case.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    ref = RunReference(run_id=run_id, created_at=1_700_000_000_000)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        engine_version=None,
        ecosystem="python" if engine_name == "pytest" else "rust",
        status="failed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=test_results,
    )
    store_run_evidence(store, record)
    handle = get_project_store_state(workspace / ".novetest")
    return handle, record


def _summary(num: int = 1) -> RegressionSummary:
    """Trivial RegressionSummary helper for fixtures that need one."""
    return RegressionSummary(
        regressed=num,
        fixed=0,
        still_failing=0,
        still_passing=0,
        still_skipped=0,
        newly_skipped=0,
        newly_active=0,
        added=0,
        removed=0,
        total_baseline_tests=num,
        total_target_tests=num,
    )


def _make_regression_facts(*, changed_files: tuple[str, ...]) -> RegressionFactSet:
    """Build a RegressionFactSet whose coverage_change blocks the given files.

    Builds a synthetic ``coverage_change`` dict in the same shape
    ``CoverageDelta.to_dict()`` produces — verified by the regression
    engine's tests. Files appear under ``files_added`` for the FLUCCS
    boost to fire (any of the three keys ``files_added``,
    ``files_removed``, ``file_deltas[*].file_path`` is sufficient).
    """
    coverage_change = {
        "schema_version": 1,
        "baseline_run_reference": {
            "run_id": "01HBASE000000000000000001",
            "created_at": 1_699_000_000_000,
            "schema_version": 1,
        },
        "target_run_reference": {
            "run_id": "01HTARGET00000000000000001",
            "created_at": 1_700_000_000_000,
            "schema_version": 1,
        },
        "baseline_granularity": "aggregate",
        "target_granularity": "aggregate",
        "summary_before": {
            "num_statements": 0, "covered_statements": 0, "missing_statements": 0,
            "excluded_statements": 0, "num_branches": 0, "covered_branches": 0,
            "missing_branches": 0, "percent_covered": 0.0,
        },
        "summary_after": {
            "num_statements": 0, "covered_statements": 0, "missing_statements": 0,
            "excluded_statements": 0, "num_branches": 0, "covered_branches": 0,
            "missing_branches": 0, "percent_covered": 0.0,
        },
        "files_added": list(changed_files),
        "files_removed": [],
        "file_deltas": [],
    }
    return RegressionFactSet(
        baseline_run_reference=RunReference(
            run_id="01HBASE000000000000000001", created_at=1_699_000_000_000
        ),
        target_run_reference=RunReference(
            run_id="01HTARGET00000000000000001", created_at=1_700_000_000_000
        ),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version=None,
        target_engine_version=None,
        derived_at=1_700_000_001_000,
        summary=_summary(0),
        test_transitions=(),
        output_diff=None,
        coverage_change=coverage_change,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_single_failure_ranks_named_file_top(tmp_path: Path) -> None:
    """One failing test mentioning src/foo.py:5 ranks src/foo.py top-1."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/test_foo.py::test_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:5: AssertionError\n+ assert add(2,3) == 6",
            ),
            TestResult(
                node_id="tests/test_foo.py::test_ok",
                outcome="passed",
                duration_ms=1,
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/test_foo.py::test_bug"}),
        regression_facts=None,
        top_n=10,
    )
    assert finding.mode == "failure_proximity"
    assert finding.confidence == "low"
    assert finding.alternate_scores_available == ()
    assert len(finding.entries) >= 1
    top = finding.entries[0]
    assert top.rank == 1
    assert top.code_location.kind == "file"
    assert top.code_location.file == "src/foo.py"
    assert top.code_location.symbol is None
    assert top.alternate_scores == {}
    # The parser also picks up the test file path; the test file ranks
    # alongside the SuT file. That's a known limitation of file-level
    # failure-proximity; both are valid "files mentioned in the failure".


def test_two_failing_tests_mentioning_same_file_aggregates(tmp_path: Path) -> None:
    """Two failing tests both pointing at src/foo.py → score = 2."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/test_a.py::test_one",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:5: AssertionError",
            ),
            TestResult(
                node_id="tests/test_a.py::test_two",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:9: AssertionError",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset(
            {"tests/test_a.py::test_one", "tests/test_a.py::test_two"}
        ),
        regression_facts=None,
        top_n=10,
    )
    foo = next(
        (e for e in finding.entries if e.code_location.file == "src/foo.py"),
        None,
    )
    assert foo is not None
    # Two distinct failing tests mention src/foo.py → raw score = 2.0.
    assert foo.score_raw == pytest.approx(2.0)
    # Two distinct lines mentioned: 5 and 9.
    assert tuple(sorted(foo.code_location.evidence_lines)) == (5, 9)
    assert set(foo.related_failed_tests) == {
        "tests/test_a.py::test_one",
        "tests/test_a.py::test_two",
    }


# ---------------------------------------------------------------------------
# Regression-aware reweighting (FLUCCS, Sohn & Yoo 2017)
# ---------------------------------------------------------------------------


def test_regression_boost_lifts_changed_file_score(tmp_path: Path) -> None:
    """Files in regression changed_files get ``score *= (1 + 0.5)``.

    Two distinct files each with one failing-test mention; the boosted
    file should rank ahead of the un-boosted one even though both have
    equal base counts.
    """
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t_a",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/changed.py:3: error",
            ),
            TestResult(
                node_id="tests/t.py::t_b",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/unchanged.py:7: error",
            ),
        ),
    )
    rf = _make_regression_facts(changed_files=("src/changed.py",))
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t_a", "tests/t.py::t_b"}),
        regression_facts=rf,
        top_n=10,
    )
    assert finding.metadata.get("regression_reweighted") is True
    assert finding.metadata.get("changed_files_count") == 1

    # changed.py: base 1.0 × 1.5 = 1.5; unchanged.py: 1.0.
    changed_entry = next(
        (e for e in finding.entries if e.code_location.file == "src/changed.py"),
        None,
    )
    unchanged_entry = next(
        (e for e in finding.entries if e.code_location.file == "src/unchanged.py"),
        None,
    )
    assert changed_entry is not None
    assert unchanged_entry is not None
    assert changed_entry.score_raw == pytest.approx(1.5)
    assert unchanged_entry.score_raw == pytest.approx(1.0)
    # Boosted file should rank #1.
    assert changed_entry.rank == 1
    assert unchanged_entry.rank == 2


def test_no_regression_facts_no_boost(tmp_path: Path) -> None:
    """Absent regression_facts → no boost, ``regression_reweighted=False``."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t_a",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:3: error",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t_a"}),
        regression_facts=None,
        top_n=10,
    )
    assert finding.metadata.get("regression_reweighted") is False
    assert finding.metadata.get("changed_files_count") == 0
    foo = next(
        (e for e in finding.entries if e.code_location.file == "src/foo.py"),
        None,
    )
    assert foo is not None
    assert foo.score_raw == pytest.approx(1.0)  # no boost applied


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unparseable_failure_log_emits_parse_warning(tmp_path: Path) -> None:
    """Failure log with no parseable file refs → warning in metadata,
    file does NOT enter the candidate set."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t",
                outcome="failed",
                duration_ms=1,
                # No file:line pattern in this message.
                failure_reference="Some opaque error without file refs",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t"}),
        regression_facts=None,
        top_n=10,
    )
    # Empty entries since no file ranks.
    assert finding.entries == ()
    warnings = finding.metadata.get("parse_warnings")
    assert isinstance(warnings, list)
    assert any("tests/t.py::t" in w for w in warnings)


def test_empty_failure_reference_emits_warning(tmp_path: Path) -> None:
    """Failing test with ``failure_reference=None`` → warning, no entry."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference=None,
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t"}),
        regression_facts=None,
        top_n=10,
    )
    assert finding.entries == ()
    warnings = finding.metadata.get("parse_warnings")
    assert isinstance(warnings, list)
    assert any("tests/t.py::t" in w for w in warnings)


def test_top_n_truncation(tmp_path: Path) -> None:
    """``top_n=1`` truncates to one entry even when several files match."""
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t_a",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/a.py:3: e",
            ),
            TestResult(
                node_id="tests/t.py::t_b",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/b.py:3: e",
            ),
            TestResult(
                node_id="tests/t.py::t_c",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/c.py:3: e",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset(
            {"tests/t.py::t_a", "tests/t.py::t_b", "tests/t.py::t_c"}
        ),
        regression_facts=None,
        top_n=1,
    )
    assert finding.top_n == 1
    assert len(finding.entries) == 1


# ---------------------------------------------------------------------------
# B2-2 file-path absoluteness normalization (UX, 2026-06-08)
# ---------------------------------------------------------------------------


def test_absolute_workspace_internal_path_normalized_to_relative(
    tmp_path: Path,
) -> None:
    """B2-2: an absolute file path under the workspace root is rewritten
    to workspace-relative form.

    Pytest's ``crash.path`` (and most other engines' tracebacks) carry
    absolute paths verbatim. Pre-normalization the failure_proximity
    mode emitted those paths absolute, while the other Localization
    modes emit repo-relative paths (because they source from
    CoverageFactSet whose adapter contract pre-normalizes). This test
    pins that the normalization actually fires on the production-shape
    input.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    abs_path_under_ws = workspace / "src" / "foo.py"
    store, record = _make_run(
        workspace=workspace,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference=(
                    f"{abs_path_under_ws}:5: AssertionError\n"
                    f"+ assert add(2,3) == 6"
                ),
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
    )
    assert len(finding.entries) == 1
    top = finding.entries[0]
    # The emitted file path is workspace-relative (NOT the absolute form
    # the parser extracted from the failure log).
    assert top.code_location.file == "src/foo.py", (
        f"expected workspace-relative path; got {top.code_location.file!r}"
    )
    # Sanity: not absolute, and is exactly the relative form.
    assert not Path(top.code_location.file).is_absolute()


def test_absolute_path_outside_workspace_kept_absolute(tmp_path: Path) -> None:
    """B2-2 edge case: a parsed absolute path that lies OUTSIDE the
    workspace (e.g. stdlib / installed-package frame) is emitted
    verbatim as-is.

    Such paths cannot be made workspace-relative meaningfully; emitting
    them absolute surfaces an obvious "not your code" cue to consumers.
    Mirrors the Defect 3 defensive posture (2026-05-31, cargo stdlib
    catch-all dropped) — failure_proximity does not have an analogous
    covered-files intersection filter, so absolute-out-of-workspace is
    the next-best disambiguation signal.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    # A clearly out-of-workspace path. Use a sibling of the workspace
    # so the path actually exists on disk but is not under the workspace
    # root.
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_path = outside_dir / "stdlib_sim.py"
    store, record = _make_run(
        workspace=workspace,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference=f"{outside_path}:10: TypeError\n",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
    )
    assert len(finding.entries) == 1
    top = finding.entries[0]
    # Kept absolute verbatim because the path is outside workspace.
    assert top.code_location.file == str(outside_path), (
        f"expected absolute path preserved; got {top.code_location.file!r}"
    )
    assert Path(top.code_location.file).is_absolute()


def test_relative_path_passes_through_unchanged(tmp_path: Path) -> None:
    """B2-2 idempotence: an already-relative input parses + emits the
    same string. Pins that the normalization helper does not mangle
    already-relative inputs (the existing happy-path tests rely on
    this; this test makes the contract explicit).
    """
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t_bug",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:3: e",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t_bug"}),
        regression_facts=None,
        top_n=10,
    )
    assert len(finding.entries) == 1
    top = finding.entries[0]
    assert top.code_location.file == "src/foo.py"


def test_absolute_and_relative_for_same_file_collapse_to_relative(
    tmp_path: Path,
) -> None:
    """B2-2 collapse-on-normalization: two failing tests, one reporting
    the file absolute (the production pytest path) and the other
    reporting it relative (a hand-rolled hypothetical), should both
    aggregate into a single candidate at the normalized relative key.

    Pins that the normalization runs BEFORE aggregation — if it ran
    AFTER, the two forms would land in two distinct dict keys, the
    file would be ranked twice, and the ``score_raw`` would be ``1.0``
    for each instead of ``2.0`` for the combined entry.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    abs_path = workspace / "src" / "foo.py"
    store, record = _make_run(
        workspace=workspace,
        test_results=(
            TestResult(
                node_id="tests/t.py::t_abs",
                outcome="failed",
                duration_ms=1,
                failure_reference=f"{abs_path}:5: AssertionError",
            ),
            TestResult(
                node_id="tests/t.py::t_rel",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:9: AssertionError",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset(
            {"tests/t.py::t_abs", "tests/t.py::t_rel"}
        ),
        regression_facts=None,
        top_n=10,
    )
    foo = next(
        (e for e in finding.entries if e.code_location.file == "src/foo.py"),
        None,
    )
    assert foo is not None, (
        f"expected unified ``src/foo.py`` entry; got entries="
        f"{[e.code_location.file for e in finding.entries]!r}"
    )
    # Both tests contributed → score_raw == 2.0 (not 1.0 if the two
    # forms had landed in separate dict keys).
    assert foo.score_raw == pytest.approx(2.0)
    assert tuple(sorted(foo.code_location.evidence_lines)) == (5, 9)
    assert set(foo.related_failed_tests) == {
        "tests/t.py::t_abs",
        "tests/t.py::t_rel",
    }


def test_failure_proximity_envelope_shape_deviation_pinned(tmp_path: Path) -> None:
    """Pin the brief §7 deviation: empty alternate_scores fields.

    The 2026-05-30 envelope freeze pins the 12/9/6/3-key shape for
    sbfl_per_test; failure_proximity carries the same shape with two
    documented deviations:

    1. ``finding.alternate_scores_available == ()`` (empty tuple).
    2. ``entries[*].alternate_scores == {}`` (empty dict).

    Pinning these here so a future regression on the deviation surfaces
    immediately without manual envelope-grepping.
    """
    store, record = _make_run(
        workspace=tmp_path / "ws",
        test_results=(
            TestResult(
                node_id="tests/t.py::t",
                outcome="failed",
                duration_ms=1,
                failure_reference="src/foo.py:3: e",
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"tests/t.py::t"}),
        regression_facts=None,
        top_n=10,
    )
    # Deviation 1.
    assert finding.alternate_scores_available == ()
    # Deviation 2.
    for entry in finding.entries:
        assert entry.alternate_scores == {}
    # The `formula` field is still set to "ochiai" so the closed-enum
    # validator passes; consumers gate on `mode` to interpret this.
    assert finding.formula == "ochiai"
