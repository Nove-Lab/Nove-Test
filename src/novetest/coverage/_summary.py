"""Shared ``CoverageSummary`` arithmetic for the native-coverage parsers.

Single-sources the summary math that lcov / jacoco / cobertura / istanbul
previously each carried locally, and that ``derive`` re-implements for its
post-filter summary rebuild (W2/S33, review finding ANA-06). Three seams:

- :func:`percent_covered` — the ONE home of the empty->100.0 percent
  convention ("zero coverable statements" reports 100.0, not 0.0). Any
  future change to this convention happens here and nowhere else.
- :func:`summary_from_counts` — the shared per-file summary builder.
  ``missing_statements`` / ``missing_branches`` are derived as
  ``num - covered`` and ``excluded_statements`` is always 0 (no native
  parser models exclusions; the coverage.py path echoes its engine totals
  through ``parser.py`` and does not use this module).
- :func:`aggregate_summary` — the top-level aggregation policy: EVERY
  counter is the SUM of the per-file counters (``missing_statements``
  included — no ``num - covered`` recompute), with ``percent_covered``
  recomputed from the summed statement counters.

Aggregation-policy note (ANA-06): the historical parsers split between
summing per-file ``missing_statements`` (jacoco, cobertura) and recomputing
``num - covered`` (lcov, istanbul). Sum-of-parts is chosen because it keeps
the top-level summary consistent with the persisted per-file summaries by
construction. The two policies are equivalent TODAY because every parser
emits per-file summaries satisfying ``missing == num - covered`` and
``excluded_statements == 0``; if a parser ever emits exclusions (breaking
that identity), sum-of-parts remains the faithful roll-up.

Percent-form note: the canonical expression is
``round(100.0 * covered / num, 2)`` — the integer product ``100.0 * covered``
is exact in binary floating point, so decimal-boundary ratios (e.g. 23/160
= exactly 14.375%) round correctly to 14.38. The historical alternative
``round(covered / num * 100.0, 2)`` (pre-S33 lcov/istanbul) accumulates a
division error first and lands on 14.37 for such boundary inputs — the two
forms agree everywhere else (~99.992% of ratios; verified by brute force to
n=4000 during S33).
"""

from __future__ import annotations

from collections.abc import Sequence

from novetest.models.coverage_fact_set import CoverageSummary, FileCoverage


def percent_covered(num_statements: int, covered_statements: int) -> float:
    """Statement-coverage percentage, rounded to 2 decimals.

    The empty->100.0 convention lives here and ONLY here: zero coverable
    statements means nothing was missed, so coverage reports 100.0.
    """
    if num_statements == 0:
        return 100.0
    return round(100.0 * covered_statements / num_statements, 2)


def summary_from_counts(
    *,
    num_statements: int,
    covered_statements: int,
    num_branches: int = 0,
    covered_branches: int = 0,
) -> CoverageSummary:
    """Build a per-file ``CoverageSummary`` from totals + covered counts.

    ``num_statements`` carries whatever statement basis the calling parser
    uses (true statements for istanbul, executable lines for lcov / jacoco /
    cobertura — see the ``CoverageSummary`` docstring for the ANA-04
    contract). Missing counters are the ``num - covered`` complements;
    ``excluded_statements`` is always 0 for native-parser output.
    """
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=num_statements - covered_statements,
        excluded_statements=0,
        num_branches=num_branches,
        covered_branches=covered_branches,
        missing_branches=num_branches - covered_branches,
        percent_covered=percent_covered(num_statements, covered_statements),
    )


def aggregate_summary(files: Sequence[FileCoverage]) -> CoverageSummary:
    """Roll per-file summaries up into the top-level ``CoverageSummary``.

    Sum-of-parts policy: every counter is the sum of the per-file counters
    (see the module docstring for why, and for the today-equivalence
    precondition). ``percent_covered`` is recomputed from the summed
    statement counters — an empty ``files`` yields all-zero counters and
    the 100.0 empty convention.
    """
    num_statements = sum(f.summary.num_statements for f in files)
    covered_statements = sum(f.summary.covered_statements for f in files)
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=sum(f.summary.missing_statements for f in files),
        excluded_statements=sum(f.summary.excluded_statements for f in files),
        num_branches=sum(f.summary.num_branches for f in files),
        covered_branches=sum(f.summary.covered_branches for f in files),
        missing_branches=sum(f.summary.missing_branches for f in files),
        percent_covered=percent_covered(num_statements, covered_statements),
    )


__all__ = ["percent_covered", "summary_from_counts", "aggregate_summary"]
