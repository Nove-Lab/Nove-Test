"""``localization/candidate_filter.py`` — test-node exclusion primitives.

Five surfaces, tested independently of the SBFL pipeline:

- ``normalize_path`` — the comparison key that folds ``./`` prefixes and
  Windows separators so a node id's path half and a Coverage Fact file
  path for the SAME file compare equal.
- ``normalize_symbol`` — the node id's symbol half spelled the way the
  symbol resolver spells qualnames.
- ``discovered_test_nodes`` — Run Record node ids → ``{file: {symbol}}``.
  Ground truth, no name heuristics; ecosystems whose node ids carry no
  file path must degrade to a harmless no-match rather than a wrong
  exclusion.
- ``apply_test_file_exclusion`` — the filter itself: symbol granularity
  (a co-located file's production code survives), the "never return
  silence" revert rule, the suppressed side channel, and the path-base
  reconciliation that keeps a monorepo rootdir from silently no-opping.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from novetest.localization.candidate_filter import (
    SUPPRESSED_CAP,
    apply_test_file_exclusion,
    discovered_test_files,
    discovered_test_nodes,
    normalize_path,
    normalize_symbol,
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
    """Minimal stand-in for a ranking candidate: file, score, symbol.

    ``symbol=None`` is the file-level candidate — what ``sbfl_aggregate``
    always produces and what ``sbfl_per_test`` falls back to when the
    resolver cannot name the enclosing symbol.
    """

    file: str
    score: float
    symbol: str | None = None


def _whole_files(*files: str) -> dict[str, frozenset[str]]:
    """Test nodes whose symbols are unknown — whole-file exclusion."""
    return {file: frozenset() for file in files}


def _run(
    candidates: list[_Cand], test_nodes: dict[str, frozenset[str]]
) -> tuple[list[str], int, bool]:
    result = apply_test_file_exclusion(
        candidates,
        test_nodes=test_nodes,
        file_of=lambda c: c.file,
        symbol_of=lambda c: c.symbol,
        score_of=lambda c: c.score,
    )
    return (
        [c.file for c in result.candidates],
        result.excluded_count,
        result.reverted,
    )


def _exclude(
    candidates: list[_Cand], test_files: frozenset[str]
) -> tuple[list[str], int, bool]:
    return _run(candidates, _whole_files(*test_files))


# ---------------------------------------------------------------------------
# normalize_path / normalize_symbol
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


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ("test_a", "test_a"),
        ("TestKlass::test_m", "TestKlass.test_m"),
        ("test_a[1-2]", "test_a"),
        ("TestKlass::test_m[case-x]", "TestKlass.test_m"),
        ("suite::nested::case", "suite.nested.case"),
        ("", ""),
    ],
)
def test_normalize_symbol_matches_resolver_qualname_spelling(
    tail: str, expected: str
) -> None:
    assert normalize_symbol(tail) == expected


# ---------------------------------------------------------------------------
# discovered_test_nodes / discovered_test_files
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


def test_node_ids_group_their_symbols_by_owning_file() -> None:
    record = _record(
        (
            "tests/test_totals.py::test_a",
            "tests/test_totals.py::test_b[1-2]",
            "tests/sub/test_other.py::TestKlass::test_c",
        )
    )
    assert discovered_test_nodes(record) == {
        "tests/test_totals.py": frozenset({"test_a", "test_b"}),
        "tests/sub/test_other.py": frozenset({"TestKlass.test_c"}),
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

    The derived string is only ever compared against paths the coverage
    tool reported, so a package / class / crate prefix cannot mis-exclude
    a real source file — including through the path-suffix fallback, which
    needs a shared basename.
    """
    record = _record((node_id,), engine_name=engine_name, ecosystem=ecosystem)
    result = apply_test_file_exclusion(
        [_Cand(covered_file, 0.9, "divide")],
        test_nodes=discovered_test_nodes(record),
        file_of=lambda c: c.file,
        symbol_of=lambda c: c.symbol,
        score_of=lambda c: c.score,
    )
    assert [c.file for c in result.candidates] == [covered_file]
    assert result.excluded_count == 0
    assert result.reverted is False
    assert result.basis == "none"


def test_degenerate_node_id_with_empty_path_half_is_dropped() -> None:
    """``::test_a`` has no path half — it must not contribute ``""``."""
    record = _record(("::test_a", "tests/test_b.py::test_b"))
    assert discovered_test_files(record) == {"tests/test_b.py"}


def test_node_id_path_half_is_normalized_before_matching() -> None:
    record = _record((".\\tests\\test_x.py::test_a",))
    assert discovered_test_files(record) == {"tests/test_x.py"}


def test_a_node_id_without_a_symbol_half_marks_its_file_whole() -> None:
    """No symbol to narrow to → the file keeps the pre-narrowing rule.

    Order-independent: the symbol-less node wins even when a symboled
    node for the same file was seen first.
    """
    record = _record(("tests/test_x.py::test_a", "tests/test_x.py"))
    assert discovered_test_nodes(record) == {"tests/test_x.py": frozenset()}


# ---------------------------------------------------------------------------
# apply_test_file_exclusion — file-granular baseline (unknown symbols)
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


# ---------------------------------------------------------------------------
# Symbol granularity — L1 finding 2026-07-30, issue 2
# ---------------------------------------------------------------------------


def test_production_symbol_of_a_colocated_file_survives() -> None:
    """The file owns a test AND the defect; only the test goes.

    File-granular exclusion deleted ``invoice_total`` here — a silent
    false negative, since another file still scored positive so the
    revert never fired.
    """
    candidates = [
        _Cand("app/totals.py", 1.0, "test_total_discount_with_tax"),
        _Cand("app/totals.py", 0.71, "invoice_total"),
        _Cand("app/helpers.py", 0.71, "discount"),
    ]
    kept, excluded, reverted = _run(
        candidates, {"app/totals.py": frozenset({"test_total_discount_with_tax"})}
    )
    assert kept == ["app/totals.py", "app/helpers.py"]
    assert excluded == 1
    assert reverted is False


@pytest.mark.parametrize(
    "symbol",
    [
        "test_a",  # the node itself
        "test_a.inner",  # a closure defined inside the test body
        "TestKlass",  # the class that OWNS TestKlass.test_m
        "TestKlass.test_m",
        "TestKlass.test_m.inner",
    ],
)
def test_test_node_symbols_and_their_scopes_are_excluded(symbol: str) -> None:
    # ``src/bug.py`` scores positive so the revert cannot mask the result.
    kept, excluded, reverted = _run(
        [_Cand("tests/test_x.py", 0.9, symbol), _Cand("src/bug.py", 0.5, "f")],
        {"tests/test_x.py": frozenset({"test_a", "TestKlass.test_m"})},
    )
    assert kept == ["src/bug.py"]
    assert excluded == 1
    assert reverted is False


@pytest.mark.parametrize("symbol", ["test_ab", "helper", "Test_a", "atest_a"])
def test_similarly_named_non_test_symbols_survive(symbol: str) -> None:
    """Scope matching is on dot boundaries, not on characters."""
    kept, _excluded, _ = _run(
        [_Cand("tests/test_x.py", 0.9, symbol)],
        {"tests/test_x.py": frozenset({"test_a"})},
    )
    assert kept == ["tests/test_x.py"]


def test_file_level_candidate_of_a_test_file_is_still_excluded() -> None:
    """No symbol → nothing to narrow with → the safe default applies.

    This is what keeps ``sbfl_aggregate`` (file ranking, no symbols at
    all) behaving exactly as it did.
    """
    kept, excluded, _ = _run(
        [_Cand("tests/test_x.py", 0.9, None), _Cand("src/bug.py", 0.5, "f")],
        {"tests/test_x.py": frozenset({"test_a"})},
    )
    assert kept == ["src/bug.py"]
    assert excluded == 1


# ---------------------------------------------------------------------------
# The suppressed side channel — L1 finding 2026-07-30, issue 3
# ---------------------------------------------------------------------------


def _suppressed(
    candidates: list[_Cand], test_nodes: dict[str, frozenset[str]]
) -> list[tuple[str, str | None, float]]:
    result = apply_test_file_exclusion(
        candidates,
        test_nodes=test_nodes,
        file_of=lambda c: c.file,
        symbol_of=lambda c: c.symbol,
        score_of=lambda c: c.score,
    )
    return [(s.file, s.symbol, s.score_raw) for s in result.suppressed]


def test_removed_positive_candidates_are_reported_best_first() -> None:
    """Nothing is deleted silently.

    When the bug really is the test's expected value, the surviving
    ranking leads with innocent product code and the correct answer is
    the thing that was removed — it has to stay visible somewhere.
    """
    candidates = [
        _Cand("tests/test_money.py", 1.0, "test_cents_of_two_fifty"),
        _Cand("tests/test_money.py", 0.0, "test_cents_of_one"),
        _Cand("app/money.py", 0.5774, "cents"),
    ]
    nodes = {
        "tests/test_money.py": frozenset(
            {"test_cents_of_two_fifty", "test_cents_of_one"}
        )
    }
    assert _suppressed(candidates, nodes) == [
        ("tests/test_money.py", "test_cents_of_two_fifty", 1.0)
    ]


def test_suppressed_is_capped_and_ordered_by_score() -> None:
    candidates = [_Cand("tests/test_x.py", 0.1 * n, f"test_{n}") for n in range(1, 9)]
    candidates.append(_Cand("src/bug.py", 0.05, "f"))
    reported = _suppressed(
        candidates,
        {"tests/test_x.py": frozenset(f"test_{n}" for n in range(1, 9))},
    )
    assert len(reported) == SUPPRESSED_CAP
    assert [symbol for _file, symbol, _score in reported] == [
        "test_8",
        "test_7",
        "test_6",
    ]


def test_nothing_is_reported_suppressed_when_the_exclusion_reverts() -> None:
    """Reverted means nothing was removed in the end."""
    assert (
        _suppressed(
            [_Cand("tests/test_x.py", 0.71, "test_a"), _Cand("src/ok.py", 0.0, "f")],
            {"tests/test_x.py": frozenset({"test_a"})},
        )
        == []
    )


# ---------------------------------------------------------------------------
# Path-base reconciliation — L1 finding 2026-07-30, issue 1
# ---------------------------------------------------------------------------


def _basis(candidates: list[_Cand], test_nodes: dict[str, frozenset[str]]) -> str:
    return apply_test_file_exclusion(
        candidates,
        test_nodes=test_nodes,
        file_of=lambda c: c.file,
        symbol_of=lambda c: c.symbol,
        score_of=lambda c: c.score,
    ).basis


def test_basis_is_exact_when_a_node_path_matches_a_candidate_path() -> None:
    assert (
        _basis(
            [_Cand("tests/test_x.py", 0.9, "test_a")],
            {"tests/test_x.py": frozenset({"test_a"})},
        )
        == "exact"
    )


def test_node_paths_rooted_above_the_workspace_are_reconciled() -> None:
    """The monorepo rootdir case: ``svc/tests/…`` vs ``tests/…``.

    Before the re-key the intersection was empty, the filter silently
    no-opped, and the envelope reported ``excluded: 0`` — the same value
    a healthy ecosystem no-op reports.
    """
    candidates = [
        _Cand("tests/test_totals.py", 0.71, "test_total"),
        _Cand("app/totals.py", 0.63, "invoice_total"),
    ]
    nodes = {"svc/tests/test_totals.py": frozenset({"test_total"})}
    assert _basis(candidates, nodes) == "path_suffix"
    kept, excluded, reverted = _run(candidates, nodes)
    assert kept == ["app/totals.py"]
    assert excluded == 1
    assert reverted is False


def test_candidate_paths_rooted_above_the_node_ids_are_reconciled() -> None:
    """The mirror case — the workspace root sits above the test rootdir."""
    candidates = [
        _Cand("svc/tests/test_totals.py", 0.71, "test_total"),
        _Cand("svc/app/totals.py", 0.63, "invoice_total"),
    ]
    nodes = {"tests/test_totals.py": frozenset({"test_total"})}
    assert _basis(candidates, nodes) == "path_suffix"
    kept, excluded, _ = _run(candidates, nodes)
    assert kept == ["svc/app/totals.py"]
    assert excluded == 1


def test_an_ambiguous_basename_is_never_guessed() -> None:
    """Two candidates qualify → no re-key, rather than a coin flip."""
    candidates = [
        _Cand("tests/test_x.py", 0.71, "test_a"),
        _Cand("a/tests/test_x.py", 0.71, "test_a"),
    ]
    nodes = {"svc/a/tests/test_x.py": frozenset({"test_a"})}
    assert _basis(candidates, nodes) == "none"
    kept, excluded, _ = _run(candidates, nodes)
    assert excluded == 0
    assert kept == ["tests/test_x.py", "a/tests/test_x.py"]


def test_a_shared_basename_that_is_not_a_path_suffix_does_not_match() -> None:
    """``other/tests/test_x.py`` is not ``svc/tests/test_x.py``."""
    candidates = [_Cand("other/tests/test_x.py", 0.71, "test_a")]
    assert _basis(candidates, {"svc/tests/test_x.py": frozenset({"test_a"})}) == "none"


def test_basis_is_none_when_the_run_discovered_no_test_nodes() -> None:
    assert _basis([_Cand("src/bug.py", 0.5, "f")], {}) == "none"
