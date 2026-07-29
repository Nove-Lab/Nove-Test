"""``localization/candidate_filter.py`` — test-file exclusion primitives.

Three surfaces, tested independently of the SBFL pipeline:

- ``normalize_path`` — the comparison key that folds ``./`` prefixes and
  Windows separators so a node id's path half and a Coverage Fact file
  path for the SAME file compare equal.
- ``discovered_test_files`` — Run Record node ids → owning file paths.
  Ground truth, no name heuristics; ecosystems whose node ids carry no
  file path must degrade to a harmless no-match rather than a wrong
  exclusion.
- ``apply_test_file_exclusion`` — the filter itself plus the
  "never return silence" revert rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from novetest.localization.candidate_filter import (
    apply_test_file_exclusion,
    discovered_test_files,
    normalize_path,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


_REF = RunReference(run_id="01HFILTER00000000000000001", created_at=1_700_000_000_000)


def _record(
    node_ids: tuple[str, ...], *, engine_name: str = "pytest", ecosystem: str = "python"
) -> RunRecord:
    return RunRecord(
        run_reference=_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        engine_version=None,
        ecosystem=ecosystem,
        status="failed",
        started_at=_REF.created_at,
        completed_at=_REF.created_at + 1,
        test_results=tuple(
            TestResult(node_id=nid, outcome="passed", duration_ms=1)
            for nid in node_ids
        ),
    )


@dataclass(frozen=True)
class _Cand:
    """Minimal stand-in for a ranking candidate: a file plus a score."""

    file: str
    score: float


def _exclude(
    candidates: list[_Cand], test_files: frozenset[str]
) -> tuple[list[str], int, bool]:
    result = apply_test_file_exclusion(
        candidates,
        test_files=test_files,
        file_of=lambda c: c.file,
        score_of=lambda c: c.score,
    )
    return (
        [c.file for c in result.candidates],
        result.excluded_count,
        result.reverted,
    )


# ---------------------------------------------------------------------------
# normalize_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("tests/test_x.py", "tests/test_x.py"),
        ("./tests/test_x.py", "tests/test_x.py"),
        (".././tests/test_x.py", ".././tests/test_x.py"),
        ("././tests/test_x.py", "tests/test_x.py"),
        ("tests\\test_x.py", "tests/test_x.py"),
        (".\\tests\\test_x.py", "tests/test_x.py"),
        ("tests/", "tests"),
        ("", ""),
    ],
)
def test_normalize_path_folds_separators_and_dot_prefixes(
    raw: str, expected: str
) -> None:
    assert normalize_path(raw) == expected


def test_normalize_path_is_idempotent() -> None:
    once = normalize_path(".\\tests\\test_x.py")
    assert normalize_path(once) == once


# ---------------------------------------------------------------------------
# discovered_test_files
# ---------------------------------------------------------------------------


def test_pytest_node_ids_yield_their_file_half() -> None:
    record = _record(
        (
            "tests/test_totals.py::test_a",
            "tests/test_totals.py::test_b",
            "tests/sub/test_other.py::TestKlass::test_c",
        )
    )
    assert discovered_test_files(record) == {
        "tests/test_totals.py",
        "tests/sub/test_other.py",
    }


def test_jest_node_ids_yield_their_suite_file_half() -> None:
    record = _record(
        ("src/calc.test.ts::calculator::adds",), engine_name="jest", ecosystem="node"
    )
    assert discovered_test_files(record) == {"src/calc.test.ts"}


def test_passing_tests_count_too_not_just_failing() -> None:
    """A passing test's file is just as non-actionable a suspect."""
    record = RunRecord(
        run_reference=_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version=None,
        ecosystem="python",
        status="failed",
        started_at=_REF.created_at,
        completed_at=_REF.created_at + 1,
        test_results=(
            TestResult(node_id="tests/test_a.py::t", outcome="failed", duration_ms=1),
            TestResult(node_id="tests/test_b.py::t", outcome="passed", duration_ms=1),
            TestResult(node_id="tests/test_c.py::t", outcome="skipped", duration_ms=1),
        ),
    )
    assert discovered_test_files(record) == {
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_c.py",
    }


@pytest.mark.parametrize(
    ("engine_name", "ecosystem", "node_id", "covered_file"),
    [
        ("gotest", "go", "example.com/m/calc::TestDivide", "calc/calc.go"),
        ("cargo", "rust", "calculator::tests::divides", "src/calculator.rs"),
        ("junit", "jvm", "com.example.CalcTest#divides", "src/main/java/Calc.java"),
        ("dotnet", "dotnet", "Example.Tests.CalcTests.Divides", "Calc/Calc.cs"),
    ],
)
def test_pathless_node_ids_never_match_a_covered_file(
    engine_name: str, ecosystem: str, node_id: str, covered_file: str
) -> None:
    """Ecosystems whose node ids carry no file path degrade to a no-op.

    The derived string is only ever compared for EQUALITY against paths
    the coverage tool reported, so a package / class / crate prefix
    cannot mis-exclude a real source file.
    """
    record = _record((node_id,), engine_name=engine_name, ecosystem=ecosystem)
    test_files = discovered_test_files(record)
    kept, excluded, reverted = _exclude([_Cand(covered_file, 0.9)], test_files)
    assert kept == [covered_file]
    assert excluded == 0
    assert reverted is False


def test_degenerate_node_id_with_empty_path_half_is_dropped() -> None:
    """``::test_a`` has no path half — it must not contribute ``""``."""
    record = _record(("::test_a", "tests/test_b.py::test_b"))
    assert discovered_test_files(record) == {"tests/test_b.py"}


def test_node_id_path_half_is_normalized_before_matching() -> None:
    record = _record((".\\tests\\test_x.py::test_a",))
    assert discovered_test_files(record) == {"tests/test_x.py"}


# ---------------------------------------------------------------------------
# apply_test_file_exclusion
# ---------------------------------------------------------------------------


def test_excludes_test_file_candidates_and_counts_them() -> None:
    candidates = [
        _Cand("tests/test_x.py", 0.71),
        _Cand("src/bug.py", 0.63),
        _Cand("src/ok.py", 0.20),
    ]
    kept, excluded, reverted = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["src/bug.py", "src/ok.py"]
    assert excluded == 1
    assert reverted is False


def test_matches_across_separator_and_dot_prefix_differences() -> None:
    candidates = [_Cand("./tests/test_x.py", 0.71), _Cand("src/bug.py", 0.63)]
    kept, excluded, _ = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["src/bug.py"]
    assert excluded == 1


def test_no_match_is_a_verbatim_passthrough() -> None:
    candidates = [_Cand("src/bug.py", 0.63), _Cand("src/ok.py", 0.0)]
    kept, excluded, reverted = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["src/bug.py", "src/ok.py"]
    assert excluded == 0
    assert reverted is False


def test_conftest_and_test_helpers_are_not_excluded() -> None:
    """Only files that OWN a discovered test node are dropped.

    ``conftest.py`` holds no test node, so a defect in shared test
    infrastructure stays rankable — the rule is ground truth, not a
    ``tests/`` path heuristic.
    """
    candidates = [
        _Cand("tests/conftest.py", 0.71),
        _Cand("tests/helpers.py", 0.63),
        _Cand("tests/test_x.py", 0.90),
    ]
    kept, excluded, _ = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["tests/conftest.py", "tests/helpers.py"]
    assert excluded == 1


def test_reverts_when_every_positive_suspect_is_a_test_file() -> None:
    """The defect really IS in a test file → return the unfiltered ranking.

    Silence would be the worst answer; the caller surfaces ``reverted``
    so the consumer can see what happened.
    """
    candidates = [_Cand("tests/test_x.py", 0.71), _Cand("src/untouched.py", 0.0)]
    kept, excluded, reverted = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["tests/test_x.py", "src/untouched.py"]
    assert excluded == 1
    assert reverted is True


def test_no_revert_when_nothing_is_suspicious_anywhere() -> None:
    """All-zero scores → ``entries`` is empty either way; keep the filter."""
    candidates = [_Cand("tests/test_x.py", 0.0), _Cand("src/ok.py", 0.0)]
    kept, excluded, reverted = _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert kept == ["src/ok.py"]
    assert excluded == 1
    assert reverted is False


def test_empty_candidate_list_is_safe() -> None:
    kept, excluded, reverted = _exclude([], frozenset({"tests/test_x.py"}))
    assert kept == []
    assert excluded == 0
    assert reverted is False


def test_input_sequence_is_not_mutated() -> None:
    candidates = [_Cand("tests/test_x.py", 0.71), _Cand("src/bug.py", 0.63)]
    _exclude(candidates, frozenset({"tests/test_x.py"}))
    assert [c.file for c in candidates] == ["tests/test_x.py", "src/bug.py"]
