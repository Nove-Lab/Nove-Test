"""Unit tests for `novetest.coverage._summary` (W2/S33, ANA-06).

The shared module is the single home of the empty->100.0 percent
convention, the per-file summary builder, and the sum-of-parts aggregation
policy that the four native parsers (lcov / jacoco / cobertura / istanbul)
and ``derive``'s post-filter rebuild delegate to.
"""

from __future__ import annotations

from novetest.coverage._summary import (
    aggregate_summary,
    percent_covered,
    summary_from_counts,
)
from novetest.models.coverage_fact_set import CoverageSummary, FileCoverage


def _file(summary: CoverageSummary, path: str = "src/a.py") -> FileCoverage:
    return FileCoverage(
        file_path=path,
        executed_lines=(),
        missing_lines=(),
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=summary,
        line_contexts={},
    )


# --- percent_covered ----------------------------------------------------------


def test_percent_empty_reports_100() -> None:
    """The empty->100.0 convention: zero coverable statements = nothing missed."""
    assert percent_covered(0, 0) == 100.0


def test_percent_typical_rounding() -> None:
    assert percent_covered(3, 2) == 66.67
    assert percent_covered(2, 1) == 50.0
    assert percent_covered(4, 3) == 75.0
    assert percent_covered(1, 1) == 100.0
    assert percent_covered(5, 0) == 0.0


def test_percent_uses_exact_integer_first_form() -> None:
    """Pins the canonical ``round(100.0 * covered / num, 2)`` ordering.

    23/160 is exactly 14.375%; the integer product ``100.0 * 23`` is exact
    in binary floating point so the boundary rounds correctly to 14.38.
    The historical ``round(covered / num * 100.0, 2)`` ordering (pre-S33
    lcov / istanbul) divides first, lands below the boundary, and yields
    14.37 — this test fails if anyone reintroduces that form.
    """
    assert percent_covered(160, 23) == 14.38


# --- summary_from_counts --------------------------------------------------------


def test_summary_from_counts_statements_only() -> None:
    summary = summary_from_counts(num_statements=3, covered_statements=2)
    assert summary == CoverageSummary(
        num_statements=3,
        covered_statements=2,
        missing_statements=1,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=66.67,
    )


def test_summary_from_counts_with_branches() -> None:
    summary = summary_from_counts(
        num_statements=4,
        covered_statements=3,
        num_branches=2,
        covered_branches=1,
    )
    assert summary.num_branches == 2
    assert summary.covered_branches == 1
    assert summary.missing_branches == 1
    # percent_covered is statement-based; branches never affect it.
    assert summary.percent_covered == 75.0


def test_summary_from_counts_empty_file() -> None:
    summary = summary_from_counts(num_statements=0, covered_statements=0)
    assert summary.percent_covered == 100.0
    assert summary.missing_statements == 0


# --- aggregate_summary ----------------------------------------------------------


def test_aggregate_sums_every_counter() -> None:
    files = [
        _file(
            summary_from_counts(
                num_statements=3,
                covered_statements=2,
                num_branches=2,
                covered_branches=1,
            ),
            "src/a.py",
        ),
        _file(
            summary_from_counts(num_statements=2, covered_statements=1),
            "src/b.py",
        ),
    ]
    total = aggregate_summary(files)
    assert total == CoverageSummary(
        num_statements=5,
        covered_statements=3,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=60.0,
    )


def test_aggregate_empty_files_is_all_zero_with_100_percent() -> None:
    total = aggregate_summary([])
    assert total.num_statements == 0
    assert total.covered_statements == 0
    assert total.missing_statements == 0
    assert total.num_branches == 0
    assert total.percent_covered == 100.0


def test_aggregate_is_sum_of_parts_not_recompute() -> None:
    """The chosen ANA-06 policy: counters are summed from per-file summaries.

    A hand-built per-file summary that violates the ``missing ==
    num - covered`` identity (impossible via the shared builder today, the
    documented equivalence precondition) must be rolled up AS IS — proving
    the aggregate reads per-file counters rather than recomputing.
    """
    weird = CoverageSummary(
        num_statements=10,
        covered_statements=6,
        missing_statements=3,  # NOT num - covered (one excluded)
        excluded_statements=1,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=60.0,
    )
    total = aggregate_summary([_file(weird)])
    assert total.missing_statements == 3
    assert total.excluded_statements == 1
    # percent IS recomputed from the summed statement counters.
    assert total.percent_covered == 60.0
