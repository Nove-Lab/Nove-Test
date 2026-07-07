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

from novetest.localization.failure_proximity import (
    _is_outside_workspace,
    _normalize_to_workspace_relative,
    derive_failure_proximity,
    parse_failure_log,
)
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


# Engine → ecosystem lookup for ``_make_run``. Mirrors the canonical
# pairs in ``run/engine_selector.py::_ENGINE_MARKER_TABLE``; unknown
# engines keep the pre-S7 "rust" default the cargo-shaped cases relied on.
_ENGINE_ECOSYSTEMS = {
    "pytest": "python",
    "jest": "javascript-typescript",
    "junit": "java",
    "go-test": "go",
    "gotest": "go",
    "cargo-test": "rust",
    "xunit": "dotnet",
}


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
        ecosystem=_ENGINE_ECOSYSTEMS.get(engine_name, "rust"),
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


# ---------------------------------------------------------------------------
# Windows path normalization fix (2026-06-09)
# ---------------------------------------------------------------------------
#
# Defect: the B2-2 slice (2026-06-08, commit 51ea1b6) added the
# ``_normalize_to_workspace_relative`` helper to align failure_proximity's
# ``code_location.file`` shape with the other Localization modes. Its
# regex + helper combo was Linux/macOS-correct but introduced 4 Windows CI
# failures the same day (CI run 27176933845, jobs 80227759401 / 404 / 408).
# Root cause:
#
# 1. ``_FILE_PATH_CHARS`` character class did not include ``:`` — so the
#    regex engine could not traverse the Windows drive prefix ``C:`` and
#    started its capture AFTER the drive colon, producing a malformed
#    drive-less path like ``Users\runneradmin\...\foo.py``. Downstream
#    ``Path.is_absolute()`` returned False (the captured path has neither
#    drive nor anchor), so the normalization helper returned the
#    malformed path verbatim.
#
# 2. ``str(WindowsPath('src/foo.py'))`` emits ``'src\\foo.py'`` (backslash
#    separator) on Windows. The envelope-wide contract is POSIX separators.
#    Pre-fix the helper used bare ``str(relative)`` which violated this.
#
# 3. ``Path.relative_to`` raises ``ValueError`` on cross-drive comparison
#    (``D:\\workspace`` vs ``C:\\Users\\...``) — the original ``try`` /
#    ``except`` in the helper caught this, but the audit recommendation
#    in the brief asked to factor the classification out as
#    ``_is_outside_workspace`` so the cross-drive safety is visible at
#    the call site.
#
# Tests pin the contract on Linux: the regex captures the drive prefix
# in both backslash and forward-slash form; the helper classifies
# cross-drive-like inputs as outside-workspace; the helper applies
# ``as_posix()`` separator normalization across OSes; the
# ``os.path.relpath`` fallback engages on the (currently-impossible
# under pathlib semantics) ``relative_to`` ValueError that escapes the
# ``_is_outside_workspace`` gate.


def test_parse_failure_log_captures_windows_drive_prefix_backslash() -> None:
    """Windows fix: the regex captures the ``C:\\`` drive prefix.

    Pre-fix (2026-06-08), ``_FILE_PATH_CHARS = r"[A-Za-z_./][\\w\\-./\\\\]*"``
    refused to traverse ``:`` between the drive letter and the path; the
    regex engine started capturing AFTER the drive (at ``Users``), losing
    the prefix. Post-fix the optional ``(?:[A-Za-z]:[\\\\/])?`` leading
    group consumes ``C:\\`` and the augmented first-char class
    ``[A-Za-z_./\\\\]`` lets the engine resume capture at the path
    separator that follows the drive.

    Linux-runnable because regex behavior depends only on the pattern +
    input string, not on the OS's path semantics. Empirically reproduced
    via ``python3 -c "import re; ..."`` on Linux before adding this pin.
    """
    text = r"C:\Users\runner\ws\src\foo.py:5: AssertionError"
    tuples = parse_failure_log("pytest", text)
    assert tuples == ((r"C:\Users\runner\ws\src\foo.py", 5),), (
        f"expected drive prefix preserved in regex capture; got {tuples!r}"
    )


def test_parse_failure_log_captures_windows_drive_prefix_forward_slash() -> None:
    """Windows fix: the regex captures the ``C:/`` (forward-slash) drive
    prefix.

    pytest's ``crash.path`` formatter on Windows sometimes emits the
    forward-slash variant (``C:/Users/runner/...``) — particularly when
    the path was constructed via ``PureWindowsPath`` and converted to
    string for the failure log. The regex's drive prefix group
    ``(?:[A-Za-z]:[\\\\/])?`` accepts both ``\\`` and ``/`` as the
    post-drive separator so both spellings are captured.
    """
    text = "C:/Users/runner/ws/src/foo.py:5: AssertionError"
    tuples = parse_failure_log("pytest", text)
    assert tuples == (("C:/Users/runner/ws/src/foo.py", 5),), (
        f"expected forward-slash drive prefix preserved; got {tuples!r}"
    )


def test_parse_failure_log_posix_paths_unchanged_post_windows_fix() -> None:
    """Regression guard: Linux paths still parse correctly after the
    Windows regex amendment.

    The optional drive prefix group is structurally inert on inputs that
    lack a drive segment — matches zero-length + the regex proceeds as
    before. Same for relative paths (the most common production form on
    every OS) and dotted ``./``-opening forms used by jest/cargo.
    """
    text = "/home/user/ws/src/foo.py:5: AssertionError"
    tuples = parse_failure_log("pytest", text)
    assert tuples == (("/home/user/ws/src/foo.py", 5),)


def test_is_outside_workspace_classifies_disjoint_paths_as_outside(
    tmp_path: Path,
) -> None:
    """The ``_is_outside_workspace`` audit helper returns True for any
    path that cannot be expressed as relative to the workspace root.

    On POSIX an unrelated absolute path triggers ``ValueError`` from
    ``Path.relative_to`` — same machinery Windows uses for cross-drive
    (``D:`` workspace vs ``C:`` file). The classifier's binary outcome
    is identical across OSes; what differs is the ``ValueError`` text
    (Windows: ``"path is on mount 'C:', start on mount 'D:'"``; POSIX:
    ``"'/elsewhere/file.py' is not in the subpath of '/workspace'"``)
    which the helper deliberately swallows.

    Linux-runnable because ``tmp_path`` provides a real workspace + a
    sibling out-of-workspace directory under a shared parent.
    """
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    inside_path = ws / "src" / "foo.py"
    outside_path = outside_dir / "file.py"

    assert _is_outside_workspace(inside_path, ws) is False
    assert _is_outside_workspace(outside_path, ws) is True
    # Boundary: workspace_root itself is "inside" because
    # ``ws.relative_to(ws) == PurePath('.')`` — the boundary belongs to
    # the "inside" half-plane.
    assert _is_outside_workspace(ws, ws) is False


def test_normalize_relative_input_passes_through_as_posix(tmp_path: Path) -> None:
    """Already-relative inputs round-trip through ``as_posix`` which is a
    no-op on POSIX (the test runner). On Windows the same call rewrites
    backslash separators to forward slashes — pinned via the regex test
    above as a Linux-runnable proxy for the Windows side.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    # POSIX-style relative input: idempotent.
    assert _normalize_to_workspace_relative("src/foo.py", ws) == "src/foo.py"
    # Dotted opener ``./src/foo.py`` collapses to ``src/foo.py`` via
    # ``PurePath`` normalization at construction time.
    assert _normalize_to_workspace_relative("./src/foo.py", ws) == "src/foo.py"


def test_normalize_outside_workspace_input_preserved_verbatim(
    tmp_path: Path,
) -> None:
    """Outside-workspace inputs are returned VERBATIM (NOT via
    ``as_posix``).

    Rationale (helper docstring): operators diagnosing a stdlib /
    cross-drive frame benefit from seeing the OS-native form — Windows
    operators recognize ``C:\\Users\\runneradmin\\...`` immediately;
    ``C:/Users/runneradmin/...`` requires an extra cognitive step. The
    helper preserves the input ``file_path`` string verbatim for
    outside-workspace paths; only inside-workspace paths get the POSIX
    separator rewrite. This deliberate asymmetry preserves the Defect-3
    (2026-05-31) defensive posture that the absolute spelling itself is
    the "not your code" semantic cue.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_path = outside_dir / "stdlib_sim.py"
    # Helper returns the OS-native string we passed in (NOT POSIX-formatted).
    result = _normalize_to_workspace_relative(str(outside_path), ws)
    assert result == str(outside_path)


def test_normalize_inside_workspace_input_emits_posix_separators(
    tmp_path: Path,
) -> None:
    """Inside-workspace absolute inputs emit POSIX-separator output.

    On POSIX this is trivially true because ``PosixPath.relative_to(...)
    .as_posix()`` returns forward-slash form (the only form). The same
    code path on Windows uses ``WindowsPath.as_posix()`` which rewrites
    backslashes to forward slashes — pinned here as the Linux-runnable
    contract surface.

    The ``"\\\\" not in result`` sanity check is OS-invariant: even if
    a future Path implementation changed semantics, the absence of
    backslash in the envelope value is the load-bearing invariant the
    other Localization modes (sbfl_*) implicitly rely on.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    abs_inside = ws / "src" / "foo.py"
    result = _normalize_to_workspace_relative(str(abs_inside), ws)
    assert result == "src/foo.py", (
        f"expected POSIX-form workspace-relative path; got {result!r}"
    )
    # Sanity: no backslashes in the result, regardless of OS.
    assert "\\" not in result


def test_normalize_relpath_fallback_engages_when_relative_to_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense-in-depth: if ``_is_outside_workspace`` classifies a path
    as inside-workspace but ``Path.relative_to`` raises ``ValueError``
    anyway (pathological — cannot happen under current pathlib
    semantics, but future drift could surface it), the helper falls
    back to ``os.path.relpath``.

    The cross-drive case the brief specifically calls out as the
    motivation for this fallback ('Windows D:↔C:') is upstream-caught
    by ``_is_outside_workspace`` so the fallback is reached only by the
    pathological surface where ``_is_outside_workspace`` and
    ``relative_to`` disagree.

    We construct that scenario by patching ``_is_outside_workspace`` to
    return False (forcing the helper down the "inside" branch) AND
    patching ``Path.relative_to`` to raise ``ValueError`` (forcing the
    branch to engage the ``os.path.relpath`` fallback).
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    abs_path = ws / "src" / "foo.py"

    # Force the inside-workspace branch.
    monkeypatch.setattr(
        "novetest.localization.failure_proximity._is_outside_workspace",
        lambda *_: False,
    )

    # Force ``relative_to`` to raise so the helper engages the fallback.
    call_state = {"count": 0}

    def fake_relative_to(self: Path, *args: object, **kwargs: object) -> Path:
        call_state["count"] += 1
        raise ValueError("simulated disagreement with is_outside check")

    monkeypatch.setattr(Path, "relative_to", fake_relative_to)

    result = _normalize_to_workspace_relative(str(abs_path), ws)
    # ``os.path.relpath`` produces forward-slash on POSIX; the helper's
    # ``as_posix`` makes the result OS-invariant.
    assert result == "src/foo.py", (
        f"expected os.path.relpath fallback to produce POSIX-relative "
        f"path; got {result!r}"
    )
    assert call_state["count"] >= 1, "expected relative_to to be invoked"


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


# ---------------------------------------------------------------------------
# W1/S7 (ANA-02): junit / xunit end-state — non-empty findings on the
# default no-coverage path
# ---------------------------------------------------------------------------
#
# Pre-S7, ``resolve_failure_text`` routed neither junit nor xunit, so a
# junit/xunit failure run ALWAYS produced zero findings here while filing
# a misleading "failure_reference empty or unresolvable" warning per
# failing test. These tests pin the wave-1 §S7 exit criterion: a junit
# and an xunit failure run produce a NON-EMPTY failure_proximity finding.

# The junit per-test failure log, captured VERBATIM from the adapter on
# the equipped host (2026-07-07, Maven Surefire 3.2.5 + JDK 17.0.19 vs
# the junit-maven-basic fixture) — same ground truth pinned in
# ``test_failure_log_parser.py``.
_REAL_JUNIT_FAILURE_LOG = """\
[message] expected: <1> but was: <0>
[type] org.opentest4j.AssertionFailedError
[stack]
org.opentest4j.AssertionFailedError: expected: <1> but was: <0>
\tat org.junit.jupiter.api.AssertionFailureBuilder.build(AssertionFailureBuilder.java:151)
\tat org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:150)
\tat org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:531)
\tat com.example.CalculatorTest.testSubtract(CalculatorTest.java:27)
\tat java.base/java.lang.reflect.Method.invoke(Method.java:569)
"""

_RUN_ID = "01HFP000000000000000000001"


def _write_failure_log(store: object, relative: str, content: str) -> None:
    """Write an adapter-shaped per-test failure log into the store's
    run artifact dir (the surface ``resolve_failure_text`` reads)."""
    log_path = (
        store.path / "run" / "artifacts" / f"run_{_RUN_ID}" / relative  # type: ignore[attr-defined]
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8")


def test_junit_failure_run_produces_nonempty_finding(tmp_path: Path) -> None:
    """Wave-1 §S7 exit criterion, junit half: log-path fill.

    The failing test's ``failure_reference`` is the artifact-dir-relative
    log path (the normalizer's PRIMARY junit fill); the log is the real
    adapter-written shape. The finding must be non-empty, pointing at the
    package-relative reconstruction of the single user frame — with NO
    parse warnings.
    """
    store, record = _make_run(
        workspace=tmp_path / "ws",
        engine_name="junit",
        test_results=(
            TestResult(
                node_id="com.example.CalculatorTest#testSubtract",
                outcome="failed",
                duration_ms=12,
                failure_reference=(
                    "native/failures/com.example.CalculatorTest_testSubtract.log"
                ),
            ),
        ),
    )
    _write_failure_log(
        store,
        "native/failures/com.example.CalculatorTest_testSubtract.log",
        _REAL_JUNIT_FAILURE_LOG,
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"com.example.CalculatorTest#testSubtract"}),
        regression_facts=None,
        top_n=10,
    )
    assert finding.mode == "failure_proximity"
    assert finding.engine_name == "junit"
    assert len(finding.entries) == 1, (
        f"expected exactly the user frame; got "
        f"{[e.code_location.file for e in finding.entries]!r}"
    )
    top = finding.entries[0]
    assert top.code_location.file == "com/example/CalculatorTest.java"
    assert top.code_location.primary_line == 27
    assert top.related_failed_tests == (
        "com.example.CalculatorTest#testSubtract",
    )
    # Pre-S7 this run produced parse_warnings for EVERY failing test.
    assert "parse_warnings" not in finding.metadata


def test_xunit_failure_run_produces_nonempty_finding(tmp_path: Path) -> None:
    """Wave-1 §S7 exit criterion, xunit half: log-path fill.

    The xunit stack frame carries the ABSOLUTE source path (PDB debug
    info); when it lies under the run's workspace root the existing B2-2
    normalization rewrites it workspace-relative — pinned here on the
    junit/xunit path end to end.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    abs_source = workspace / "MathLib.Tests" / "MathTests.cs"
    # Real adapter-written log shape (dotnet SDK 8.0 + xunit 2.6,
    # 2026-07-07) with the workspace path parameterized.
    log_content = (
        "[message] Assert.Equal() Failure: Values differ\n"
        "Expected: 5\n"
        "Actual:   6\n"
        "[stack]\n"
        "   at MathLib.Tests.MathTests.TestSubtractIntentionallyFails() "
        f"in {abs_source}:line 32\n"
        "   at System.RuntimeMethodHandle.InvokeMethod(Object target, "
        "Void** arguments, Signature sig, Boolean isConstructor)\n"
    )
    store, record = _make_run(
        workspace=workspace,
        engine_name="xunit",
        test_results=(
            TestResult(
                node_id="MathLib.Tests.MathTests.TestSubtractIntentionallyFails",
                outcome="failed",
                duration_ms=40,
                failure_reference=(
                    "native/failures/"
                    "MathLib.Tests.MathTests.TestSubtractIntentionallyFails.log"
                ),
            ),
        ),
    )
    _write_failure_log(
        store,
        "native/failures/MathLib.Tests.MathTests.TestSubtractIntentionallyFails.log",
        log_content,
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset(
            {"MathLib.Tests.MathTests.TestSubtractIntentionallyFails"}
        ),
        regression_facts=None,
        top_n=10,
    )
    assert finding.mode == "failure_proximity"
    assert finding.engine_name == "xunit"
    assert len(finding.entries) == 1
    top = finding.entries[0]
    # Absolute PDB path inside the workspace → workspace-relative POSIX.
    assert top.code_location.file == "MathLib.Tests/MathTests.cs"
    assert top.code_location.primary_line == 32
    assert "parse_warnings" not in finding.metadata


def test_junit_inline_fallback_yields_honest_no_frames_warning(
    tmp_path: Path,
) -> None:
    """junit/xunit FALLBACK fill (inline ``"type: message"`` join, no
    per-test log on disk): the reference resolves to inline text, the
    text has no stack frame, and the warning honestly says "no parseable
    file:line references" — NOT the pre-S7 "empty or unresolvable"
    conflation (the reference is neither).
    """
    store, record = _make_run(
        workspace=tmp_path / "ws",
        engine_name="junit",
        test_results=(
            TestResult(
                node_id="com.example.CalculatorTest#testSubtract",
                outcome="failed",
                duration_ms=12,
                failure_reference=(
                    "org.opentest4j.AssertionFailedError: "
                    "expected: <1> but was: <0>"
                ),
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"com.example.CalculatorTest#testSubtract"}),
        regression_facts=None,
        top_n=10,
    )
    assert finding.entries == ()
    warnings = finding.metadata.get("parse_warnings")
    assert isinstance(warnings, list) and len(warnings) == 1
    assert "no parseable file:line references" in warnings[0]
    assert "unresolvable" not in warnings[0]


def test_parse_warning_wording_distinguishes_empty_from_unresolvable(
    tmp_path: Path,
) -> None:
    """W1/S7 warning-wording split: a truly EMPTY ``failure_reference``
    and an UNRESOLVABLE log path produce distinct reasons (both keep the
    contract's ``"<node_id>: <reason>"`` form)."""
    # Empty reference (any engine).
    store, record = _make_run(
        workspace=tmp_path / "ws-empty",
        engine_name="junit",
        test_results=(
            TestResult(
                node_id="com.example.T#empty",
                outcome="failed",
                duration_ms=1,
                failure_reference=None,
            ),
        ),
    )
    finding = derive_failure_proximity(
        store=store,
        record=record,
        failed_test_ids=frozenset({"com.example.T#empty"}),
        regression_facts=None,
        top_n=10,
    )
    warnings = finding.metadata.get("parse_warnings")
    assert isinstance(warnings, list) and len(warnings) == 1
    assert warnings[0] == "com.example.T#empty: failure_reference is empty"

    # Unresolvable log path (logfile engine, file never written).
    store2, record2 = _make_run(
        workspace=tmp_path / "ws-unres",
        engine_name="cargo-test",
        test_results=(
            TestResult(
                node_id="tests::t_gone",
                outcome="failed",
                duration_ms=1,
                failure_reference="native/failures/gone.log",
            ),
        ),
    )
    finding2 = derive_failure_proximity(
        store=store2,
        record=record2,
        failed_test_ids=frozenset({"tests::t_gone"}),
        regression_facts=None,
        top_n=10,
    )
    warnings2 = finding2.metadata.get("parse_warnings")
    assert isinstance(warnings2, list) and len(warnings2) == 1
    assert warnings2[0].startswith("tests::t_gone: ")
    assert "did not resolve" in warnings2[0]
    assert warnings2[0] != warnings[0]
