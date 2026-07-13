"""Programmatic ``CoverageFactSet`` generator for the NFR-COV-002 benchmark.

Pure functions only — no disk I/O, stdlib + ``novetest.models`` +
``novetest.coverage._summary`` only. Builds large but fully deterministic
``CoverageFactSet`` instances so
``tests/perf/coverage/test_perf_compare.py`` can exercise
``compare_coverage_facts`` at the 50,000-covered-location scale NFR-COV-002
specifies.

A "covered location" is one entry in ``executed_lines`` OR one
``(from_line, to_line)`` pair in ``executed_branches``. The 50k target is
``sum(len(executed_lines) + len(executed_branches))`` across all files of one
fact set — see ``agent-comms/tasks/coverage-team-2026-05-20-coverage-compare-perf.md``.
``missing_lines`` / ``missing_branches`` do NOT count toward the target; a
modest number is included per file so ``FileCoverage.from_dict`` does
realistic deserialization work.

Summary math delegates to ``novetest.coverage._summary`` (W2/S35 residue of
the S33 dedup — this module used to carry private copies of the aggregate /
per-file / percent summary helpers). The plain ``from ... import`` is
deliberate: the S33 module-attribute-call convention is load-bearing only
inside the parsers that the divergence guard monkeypatches — do not "fix"
the style in either direction here.
"""

from __future__ import annotations

from novetest.coverage._summary import aggregate_summary, summary_from_counts
from novetest.models.coverage_fact_set import CoverageFactSet, FileCoverage
from novetest.models.run_reference import RunReference


# Fixed epoch-ms stamp so generated fact sets are byte-deterministic.
_CREATED_AT: int = 1_700_000_000_000

# Per-file uncovered counts. Excluded from the 50k covered-location target
# but present so ``from_dict`` deserialization cost is realistic.
_MISSING_LINES_PER_FILE: int = 8
_MISSING_BRANCHES_PER_FILE: int = 2

# How many executed lines / branches ``perturb_for_delta`` swaps out per file.
_SWAP_LINES: int = 5
_SWAP_BRANCHES: int = 1


def generate_fact_set(
    run_id: str,
    num_files: int,
    lines_per_file: int,
    branches_per_file: int,
    *,
    file_offset: int = 0,
) -> CoverageFactSet:
    """Build a deterministic ``aggregate``-granularity ``CoverageFactSet``.

    ``num_files`` files, each with ``lines_per_file`` executed lines and
    ``branches_per_file`` executed branch pairs — a covered-location count of
    ``num_files * (lines_per_file + branches_per_file)``. File paths are
    ``src/pkg/module_{j:04d}.py`` for ``j`` in
    ``[file_offset, file_offset + num_files)``, so two calls with different
    ``file_offset`` share a controllable subset of paths — the basis for the
    ``files_added`` / ``files_removed`` sets of a non-trivial delta.
    """
    files = tuple(
        _build_file(file_offset + i, lines_per_file, branches_per_file)
        for i in range(num_files)
    )
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=_CREATED_AT),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="aggregate",
        summary=aggregate_summary(files),
        files=files,
        derived_at=_CREATED_AT,
        metadata={"generator": "tests/perf/coverage/generate_large_fact_set.py"},
    )


def perturb_for_delta(fact_set: CoverageFactSet) -> CoverageFactSet:
    """Return a copy of ``fact_set`` with every file's coverage perturbed.

    Each file has its last ``_SWAP_LINES`` executed lines and last
    ``_SWAP_BRANCHES`` executed branch swapped for fresh locations. The swap
    keeps every counter identical (covered/missing counts are unchanged) so
    both sides of a comparison stay at the same covered-location total, while
    guaranteeing each common file yields a real ``FileCoverageDelta`` — a
    zero-change delta would be an unrealistically cheap benchmark.
    """
    perturbed = tuple(_perturb_file(f) for f in fact_set.files)
    return CoverageFactSet(
        run_reference=fact_set.run_reference,
        engine_name=fact_set.engine_name,
        ecosystem=fact_set.ecosystem,
        mapping_granularity=fact_set.mapping_granularity,
        summary=fact_set.summary,
        files=perturbed,
        derived_at=fact_set.derived_at,
        metadata=dict(fact_set.metadata),
    )


# --- internals ---------------------------------------------------------------


def _build_file(
    index: int, lines_per_file: int, branches_per_file: int
) -> FileCoverage:
    # Executed lines: even numbers 2, 4, ..., 2 * lines_per_file.
    executed_lines = tuple(range(2, 2 * lines_per_file + 2, 2))
    # Executed branches: adjacent even-line arcs (2, 4), (4, 6), ...
    executed_branches = tuple(
        (2 * b + 2, 2 * b + 4) for b in range(branches_per_file)
    )
    # Uncovered locations parked above the executed range — disjoint from it.
    base = 2 * lines_per_file + 3
    missing_lines = tuple(range(base, base + 2 * _MISSING_LINES_PER_FILE, 2))
    missing_branches = tuple(
        (base + 2 * b, base + 2 * b + 2) for b in range(_MISSING_BRANCHES_PER_FILE)
    )
    # Production per-file convention: missing = num - covered, excluded = 0,
    # percent over statements only (see ``_summary.summary_from_counts``).
    summary = summary_from_counts(
        num_statements=lines_per_file + _MISSING_LINES_PER_FILE,
        covered_statements=lines_per_file,
        num_branches=branches_per_file + _MISSING_BRANCHES_PER_FILE,
        covered_branches=branches_per_file,
    )
    return FileCoverage(
        file_path=f"src/pkg/module_{index:04d}.py",
        executed_lines=executed_lines,
        missing_lines=missing_lines,
        excluded_lines=(),
        executed_branches=executed_branches,
        missing_branches=missing_branches,
        summary=summary,
    )


def _perturb_file(f: FileCoverage) -> FileCoverage:
    # Fresh locations parked well above any line this generator emits.
    fresh_base = (max(f.executed_lines) if f.executed_lines else 0) + 101
    new_lines = tuple(range(fresh_base, fresh_base + 2 * _SWAP_LINES, 2))
    new_branches = tuple(
        (fresh_base + 2 * b, fresh_base + 2 * b + 2) for b in range(_SWAP_BRANCHES)
    )
    executed_lines = f.executed_lines[:-_SWAP_LINES] + new_lines
    executed_branches = f.executed_branches[:-_SWAP_BRANCHES] + new_branches
    return FileCoverage(
        file_path=f.file_path,
        executed_lines=executed_lines,
        missing_lines=f.missing_lines,
        excluded_lines=f.excluded_lines,
        executed_branches=executed_branches,
        missing_branches=f.missing_branches,
        summary=f.summary,
    )
