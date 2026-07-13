"""``build_spectra`` unit tests — matrix construction correctness.

The S30 (ANA-11) exclusion-contract section pins the pinned outcome
vocabulary: rows exist only for tests in ``failed_test_ids`` (the
``models.FAIL_LIKE_OUTCOMES`` bucket) or ``passed_test_ids`` (strictly
``passed``); everything else discovered in the coverage contexts —
``skipped`` / ``xfailed`` / ``xpassed`` / unattested nodeids — is
excluded from the SBFL sample.
"""

from __future__ import annotations

import numpy as np
import pytest

from novetest.localization.sbfl.spectra import (
    Spectra,
    SpectraBuildError,
    build_spectra,
)
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


_REF = RunReference(run_id="01HSPECTRA0000000000000000", created_at=1_700_000_000_000)

_NO_PASSED: frozenset[str] = frozenset()


def _summary() -> CoverageSummary:
    return CoverageSummary(
        num_statements=1,
        covered_statements=1,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


def _file(file_path: str, contexts: dict[int, tuple[str, ...]]) -> FileCoverage:
    return FileCoverage(
        file_path=file_path,
        executed_lines=tuple(sorted(contexts.keys())),
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_summary(),
        line_contexts=contexts,
    )


def _facts(files: tuple[FileCoverage, ...]) -> CoverageFactSet:
    return CoverageFactSet(
        run_reference=_REF,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_summary(),
        files=files,
        derived_at=_REF.created_at + 1000,
    )


def test_build_spectra_single_test_single_line() -> None:
    facts = _facts((_file("src/foo.py", {10: ("tests/test_foo.py::test_a",)}),))
    spectra = build_spectra(
        facts, frozenset({"tests/test_foo.py::test_a"}), _NO_PASSED
    )

    assert isinstance(spectra, Spectra)
    assert spectra.test_ids == ("tests/test_foo.py::test_a",)
    assert spectra.locations == (("src/foo.py", 10),)
    assert spectra.matrix.shape == (1, 1)
    assert int(spectra.matrix[0, 0]) == 1
    assert int(spectra.test_outcomes[0]) == 1  # failed


def test_build_spectra_orders_rows_and_columns_deterministically() -> None:
    """Test_ids sorted ascending; locations sorted by (file, line) ascending."""
    facts = _facts(
        (
            _file(
                "src/zoo.py",
                {
                    5: ("tests/b.py::t",),
                    3: ("tests/a.py::t",),
                },
            ),
            _file("src/aaa.py", {7: ("tests/a.py::t", "tests/b.py::t")}),
        )
    )
    spectra = build_spectra(
        facts, frozenset({"tests/a.py::t"}), frozenset({"tests/b.py::t"})
    )
    assert spectra.test_ids == ("tests/a.py::t", "tests/b.py::t")
    assert spectra.locations == (
        ("src/aaa.py", 7),
        ("src/zoo.py", 3),
        ("src/zoo.py", 5),
    )


def test_build_spectra_failed_test_outcome_vector_correct() -> None:
    """Failed tests in input ⇒ outcome row 1; passed tests ⇒ 0."""
    facts = _facts(
        (
            _file(
                "src/foo.py",
                {
                    1: ("tests/passing.py::t",),
                    2: ("tests/failing.py::t",),
                    3: (
                        "tests/passing.py::t",
                        "tests/failing.py::t",
                    ),
                },
            ),
        )
    )
    spectra = build_spectra(
        facts,
        frozenset({"tests/failing.py::t"}),
        frozenset({"tests/passing.py::t"}),
    )
    assert spectra.test_ids == ("tests/failing.py::t", "tests/passing.py::t")
    # Order: failing first (alphabetical), then passing.
    assert int(spectra.test_outcomes[0]) == 1
    assert int(spectra.test_outcomes[1]) == 0


def test_build_spectra_matrix_stamps_executions_correctly() -> None:
    facts = _facts(
        (
            _file(
                "src/m.py",
                {
                    1: ("tests/a.py::t",),
                    2: ("tests/b.py::t",),
                    3: ("tests/a.py::t", "tests/b.py::t"),
                },
            ),
        )
    )
    spectra = build_spectra(
        facts, frozenset({"tests/a.py::t"}), frozenset({"tests/b.py::t"})
    )
    expected = np.array(
        [
            [1, 0, 1],  # tests/a.py::t executed lines 1, 3
            [0, 1, 1],  # tests/b.py::t executed lines 2, 3
        ],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(spectra.matrix, expected)


def test_build_spectra_failed_test_without_coverage_appears_as_zero_row() -> None:
    """A failing test that never executed covered code still appears as a row.

    Necessary so ``ef`` (failing tests that executed a location) is counted
    correctly — without this row, the failing-test total would be wrong
    when one of the failures crashed before any covered code ran.
    """
    facts = _facts(
        (_file("src/foo.py", {1: ("tests/covered.py::t",)}),)
    )
    spectra = build_spectra(
        facts,
        frozenset({"tests/crashed.py::t", "tests/covered.py::t"}),
        _NO_PASSED,
    )
    assert "tests/crashed.py::t" in spectra.test_ids
    crashed_idx = spectra.test_ids.index("tests/crashed.py::t")
    assert int(spectra.matrix[crashed_idx].sum()) == 0
    assert int(spectra.test_outcomes[crashed_idx]) == 1


def test_build_spectra_raises_when_every_line_context_empty() -> None:
    """A per-test fact set with empty line_contexts everywhere is malformed."""
    facts = _facts(
        (
            FileCoverage(
                file_path="src/foo.py",
                executed_lines=(1, 2),
                missing_lines=(),
                excluded_lines=(),
                executed_branches=(),
                missing_branches=(),
                summary=_summary(),
                line_contexts={},
            ),
        )
    )
    with pytest.raises(SpectraBuildError):
        build_spectra(facts, frozenset({"tests/x.py::t"}), _NO_PASSED)


def test_build_spectra_ignores_lines_with_empty_context_tuples() -> None:
    """A line with an empty nodeids tuple is treated as unexecuted (skipped)."""
    facts = _facts(
        (
            _file(
                "src/foo.py",
                {
                    1: ("tests/a.py::t",),
                    2: (),  # explicitly empty — should NOT appear in spectra
                },
            ),
        )
    )
    spectra = build_spectra(facts, frozenset({"tests/a.py::t"}), _NO_PASSED)
    assert spectra.locations == (("src/foo.py", 1),)


# ---------------------------------------------------------------------------
# S30 / ANA-11 — exclusion contract: covered tests outside the pinned
# failed/passed vocabulary get NO spectra row.
# ---------------------------------------------------------------------------


def test_build_spectra_excludes_covered_test_outside_both_outcome_sets() -> None:
    """A covered ``xfailed``/``xpassed``-like nodeid (in neither outcome set)
    is EXCLUDED from the sample: no row, no ``ep`` contribution.

    Pre-S30, ``build_spectra`` inferred "not failed ⇒ passed" and gave the
    xpassed test a passing row, inflating ``ep`` for every line it stamped
    (the ANA-11 suspicion dilution). This test is the named ANA-11 A/B
    tripwire at the spectra layer.
    """
    facts = _facts(
        (
            _file(
                "src/foo.py",
                {
                    5: ("tests/t.py::t_fail", "tests/t.py::t_xpass"),
                    6: ("tests/t.py::t_xpass",),
                    7: ("tests/t.py::t_pass",),
                },
            ),
        )
    )
    spectra = build_spectra(
        facts,
        frozenset({"tests/t.py::t_fail"}),
        frozenset({"tests/t.py::t_pass"}),
    )
    # The xpassed test is not a row; the location it stamped stays a column.
    assert spectra.test_ids == ("tests/t.py::t_fail", "tests/t.py::t_pass")
    assert spectra.locations == (
        ("src/foo.py", 5),
        ("src/foo.py", 6),
        ("src/foo.py", 7),
    )
    # Line 5: only the failing row stamps it (no phantom passing stamp).
    passed_idx = spectra.test_ids.index("tests/t.py::t_pass")
    ep_line5 = int(spectra.matrix[passed_idx, 0])
    assert ep_line5 == 0
    # Line 6 was covered ONLY by the excluded test → all-zero column.
    assert int(spectra.matrix[:, 1].sum()) == 0
    # Outcome vector covers exactly the two sampled rows.
    np.testing.assert_array_equal(spectra.test_outcomes, np.array([1, 0], dtype=np.uint8))


def test_build_spectra_excluded_only_sample_degrades_to_failing_rows() -> None:
    """When every non-failed covered test is excluded (e.g. all-xfail),
    the sample degrades to failing rows only — ``ep`` and ``np_`` are 0,
    never inflated by the excluded tests."""
    facts = _facts(
        (
            _file(
                "src/foo.py",
                {
                    1: ("tests/t.py::t_fail", "tests/t.py::t_xfail"),
                    2: ("tests/t.py::t_xfail",),
                },
            ),
        )
    )
    spectra = build_spectra(facts, frozenset({"tests/t.py::t_fail"}), _NO_PASSED)
    assert spectra.test_ids == ("tests/t.py::t_fail",)
    assert spectra.matrix.shape == (1, 2)
    # The excluded test's exclusive line stays a column with zero stamps.
    np.testing.assert_array_equal(spectra.matrix, np.array([[1, 0]], dtype=np.uint8))


def test_build_spectra_passed_test_without_coverage_gets_no_row() -> None:
    """A ``passed_test_ids`` member never attested by any line context gets
    NO row (unlike failed tests): an unattested passing test carries no
    per-line evidence, and an all-zero passing row would shift ``np_``
    for every location."""
    facts = _facts((_file("src/foo.py", {1: ("tests/t.py::t_fail",)}),))
    spectra = build_spectra(
        facts,
        frozenset({"tests/t.py::t_fail"}),
        frozenset({"tests/t.py::t_pass_uncovered"}),
    )
    assert spectra.test_ids == ("tests/t.py::t_fail",)
