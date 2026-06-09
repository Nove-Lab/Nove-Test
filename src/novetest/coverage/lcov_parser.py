"""Parser for LCOV coverage reports (``cargo llvm-cov nextest --lcov``).

Internal to the Coverage engine. Consumes the LCOV text file the cargo
adapter registers under ``RunRecord.artifact_paths["coverage_lcov"]``
and emits a structured ``CoverageFactSet``. This is the cargo-test
counterpart to ``parser.py`` (coverage.py JSON) and
``istanbul_parser.py`` (jest's ``coverage-final.json``). ``derive.py``
dispatches on ``engine_name``.

LCOV format primer
------------------

LCOV is a line-based text format originally produced by the GCC ``lcov``
tool. Each source file's coverage is bounded by an ``SF:<abs_path>``
opening record and a literal ``end_of_record`` closing record. Inside
the block, the records this parser HONORS are:

    DA:<line>,<hits>[,<md5>]         per-source-line execution counter
    LF:<total>                       lines-found summary
    LH:<lines_hit>                   lines-hit summary
    BRDA:<line>,<block>,<branch>,<hits>
                                     per-branch execution counter
                                     (``<hits>`` is ``-`` when never taken)
    BRF:<total>                      branches-found summary
    BRH:<branches_hit>               branches-hit summary

Records the parser ignores SILENTLY (LCOV-valid but no slot in our
``FileCoverage`` model — ignoring them is documented behavior, not a
parse failure):

    TN:<test_name>                   test name (always blank from
                                     ``cargo-llvm-cov`` in aggregate mode)
    FN:<line>,<function>             function-definition record
    FNDA:<hit>,<function>            per-function execution counter
    FNF:<total>                      functions-found summary
    FNH:<hit>                        functions-hit summary

Empty lines and ``#``-comment lines are skipped. Unknown ``KEY:`` records
are skipped silently — LCOV is an open-ended format and downstream
producers can add extensions.

Mapping decisions (cargo-test → frozen-schema)
----------------------------------------------

- ``mapping_granularity = "aggregate"``. ``cargo-llvm-cov nextest --lcov``
  merges coverage across the whole nextest run with no per-test
  attribution. The per-test ``--per-test-coverage`` slow-mode path is
  documented post-MVP in ``engine-adapters.md §5`` (line 363) and is
  out-of-scope here.

- ``file_path`` is workspace-relative POSIX. ``cargo-llvm-cov`` emits
  ABSOLUTE paths in ``SF:``; the parser relativizes them against
  ``workspace_root`` (the Run's workspace root, which is
  ``ProjectStore.path.parent`` — i.e. the ``.novetest/`` directory's
  parent IS the workspace root). Paths NOT under ``workspace_root``
  (rare: cargo build-script generated code, vendored
  ``target/...`` paths) are normalized to a ``../``-prefixed POSIX
  relpath via ``os.path.relpath`` against ``workspace_root`` — harmonized
  with the istanbul / cobertura parsers per the 2026-06-08 amendment to
  ``decisions/2026-05-15-coverage-facts-json-layout.md``. The original
  absolute ``SF:`` path is preserved in ``metadata["lcov_warnings"]``
  for forensic continuity (debuggers see the unresolved native string
  alongside the normalized one) but never appears in ``file_path``.

- ``line_contexts = {}`` and ``executed_lines`` / ``missing_lines`` are
  derived directly from ``DA`` records. A line counts as executed when
  any ``DA:<line>,<hits>`` with ``hits > 0`` exists; missing when only
  ``DA:<line>,0`` records exist. Duplicate ``DA`` entries for the same
  line are tolerated and their hits are summed (cargo-llvm-cov has been
  observed to emit per-instantiation duplicates for generics).

- ``excluded_lines = ()``. LCOV carries no exclusion concept — pytest's
  ``# pragma: no cover`` analog does not exist in LCOV's grammar.

- Branches: when ``BRDA`` records are present, each unique
  ``(line, block, branch_index)`` triple is recorded once. The pair
  surfaced in ``executed_branches`` / ``missing_branches`` is
  ``(line, branch_index)`` — note this DEVIATES from the
  coverage.py-derived semantic in
  ``models/coverage_fact_set.py`` (which documents the tuple as
  ``(from_line, to_line)``). LCOV's BRDA does not carry a destination
  line; the second integer is the LCOV branch index. The semantic is
  pinned in ``metadata["branch_arc_semantics"] = "lcov-line-index"``
  so future debuggers and the compare pipeline can disambiguate. When
  ``BRDA`` records are ABSENT (the cargo-llvm-cov default — see Manual
  Test's 2026-05-31 sweep), branch fields stay empty tuples and
  ``summary.num_branches == 0``. This is documented limitation, not a
  parse failure.

Validation
----------

The parser is strict about structural validity (raises
``CoverageJsonParseError`` from ``parser.py`` so ``derive`` surfaces it
uniformly as ``native-payload-corrupt``) but permissive about
unknown-record extensions:

- Empty file → raise.
- Missing file (handled in ``derive``, not here).
- ``end_of_record`` outside any ``SF:`` block → raise.
- New ``SF:`` while a previous block is still open → raise.
- ``DA``/``LF``/``LH``/``BRDA``/``BRF``/``BRH`` outside any ``SF:``
  block → raise.
- Trailing ``SF:`` block not closed by ``end_of_record`` → raise.
- ``LF`` / ``LH`` / ``BRF`` / ``BRH`` summary value disagrees with the
  parser-counted ``DA`` / ``BRDA`` tally → raise (safety guard against
  a producer truncating output mid-block).
- Malformed ``DA``/``BRDA`` (non-integer fields) → raise.
- Unknown ``KEY:`` records → skip silently.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novetest.coverage._paths import relpath_or_drive_stripped
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


# cargo-llvm-cov nextest --lcov merges per-nextest-run with no per-test
# attribution; ``aggregate`` is the only honest granularity.
_LCOV_MAPPING_GRANULARITY = "aggregate"

# LCOV record keys we explicitly recognize. Anything else inside an open
# SF: block is skipped silently.
_KEY_SF = "SF"
_KEY_DA = "DA"
_KEY_LF = "LF"
_KEY_LH = "LH"
_KEY_BRDA = "BRDA"
_KEY_BRF = "BRF"
_KEY_BRH = "BRH"
_KEY_END = "end_of_record"

# LCOV records we recognize but choose to ignore (FileCoverage has no
# per-function fields, and TN: from cargo-llvm-cov in aggregate mode is
# always blank). Listing them keeps the ``skipped silently`` set explicit
# rather than relying on the unknown-record catch-all — the catch-all is
# for FUTURE LCOV extensions, this set is for documented current ones.
_IGNORED_KEYS: frozenset[str] = frozenset({"TN", "FN", "FNDA", "FNF", "FNH"})


def parse_lcov(
    lcov_path: Path,
    *,
    run_reference: RunReference,
    engine_name: str,
    ecosystem: str,
    workspace_root: Path,
    derived_at: int | None = None,
) -> CoverageFactSet:
    """Build a ``CoverageFactSet`` from an LCOV file at ``lcov_path``.

    ``workspace_root`` is the directory the Run executed in; it is used to
    convert LCOV's absolute ``SF:`` paths to workspace-relative ones
    (decision 2026-05-15 #6). Callers typically pass
    ``ProjectStore.path.parent`` — the ``.novetest/`` directory's parent
    IS the workspace root.

    Raises ``CoverageJsonParseError`` (re-used from ``parser.py``) when
    the LCOV file is empty or has structurally invalid records. The
    underlying file IO error is also surfaced as
    ``CoverageJsonParseError`` so ``derive_coverage_facts`` can map it
    uniformly to the ``native-payload-corrupt`` unavailable outcome.
    """
    try:
        text = lcov_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - derive's path-exists guard catches this first
        raise CoverageJsonParseError(
            f"Could not read LCOV file {lcov_path}: {exc}"
        ) from exc
    if not text.strip():
        raise CoverageJsonParseError(f"LCOV file {lcov_path} is empty")

    warnings: list[str] = []
    files: list[FileCoverage] = []
    for block in _iter_file_blocks(text, lcov_path):
        files.append(_build_file_coverage(block, workspace_root, warnings))

    # Deterministic on-disk output (REQ-FOUND: deterministic structured
    # outputs for the same inputs). Sort by workspace-relative path.
    files.sort(key=lambda f: f.file_path)
    summary = _aggregate_summary(files)

    metadata: dict[str, Any] = {
        "coverage_format": "lcov",
        "branch_arc_semantics": "lcov-line-index",
    }
    if warnings:
        metadata["lcov_warnings"] = warnings

    return CoverageFactSet(
        run_reference=run_reference,
        engine_name=engine_name,
        ecosystem=ecosystem,
        mapping_granularity=_LCOV_MAPPING_GRANULARITY,
        summary=summary,
        files=tuple(files),
        derived_at=derived_at if derived_at is not None else int(time.time() * 1000),
        metadata=metadata,
    )


# --- internals ---------------------------------------------------------------


@dataclass(slots=True)
class _LcovFileBlock:
    """Mutable accumulator for one ``SF:`` ... ``end_of_record`` stanza.

    ``da_hits`` is per-line; LCOV permits duplicate ``DA`` entries for
    the same line (cargo-llvm-cov has been observed to emit them for
    generic instantiations) and the parser sums them.

    ``brda`` keeps the raw (line, block, branch, hits) quads so the
    builder can deduplicate by (line, block, branch) before populating
    ``executed_branches`` / ``missing_branches``.
    """

    source_file: str
    da_hits: dict[int, int] = field(default_factory=dict)
    brda: list[tuple[int, int, int, int]] = field(default_factory=list)
    declared_lf: int | None = None
    declared_lh: int | None = None
    declared_brf: int | None = None
    declared_brh: int | None = None


def _iter_file_blocks(text: str, source: Path) -> Iterator[_LcovFileBlock]:
    """Yield one ``_LcovFileBlock`` per ``SF:`` ... ``end_of_record`` stanza.

    Raises ``CoverageJsonParseError`` for structural mismatches (records
    outside an SF: block, nested SF: blocks, dangling SF: at EOF,
    ``end_of_record`` without an open SF:).
    """
    current: _LcovFileBlock | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # The end_of_record terminator has no value — handle before the
        # key:value split.
        if line == _KEY_END:
            if current is None:
                raise CoverageJsonParseError(
                    f"{source}:{lineno}: '{_KEY_END}' without preceding "
                    f"'{_KEY_SF}:'"
                )
            yield current
            current = None
            continue

        key, sep, rest = line.partition(":")
        if not sep:
            # Malformed lines without a ':' are tolerated to keep the
            # parser robust against LCOV producers that emit blank
            # decorative lines. They are not unknown records — they
            # are unparseable, so skipping is the safer choice than
            # raising on something downstream tooling may have planted.
            continue

        if key == _KEY_SF:
            if current is not None:
                raise CoverageJsonParseError(
                    f"{source}:{lineno}: new '{_KEY_SF}:' opens before "
                    f"previous '{_KEY_END}' (still inside "
                    f"{current.source_file!r})"
                )
            current = _LcovFileBlock(source_file=rest)
            continue

        if key in _IGNORED_KEYS:
            # Documented-ignore set: FileCoverage has no slot for
            # function-level data. Skipping silently is contractual.
            continue

        # Every other recognized record must be inside an SF: block.
        if current is None:
            raise CoverageJsonParseError(
                f"{source}:{lineno}: '{key}:' record outside any "
                f"'{_KEY_SF}:' block"
            )

        if key == _KEY_DA:
            line_no, hits = _parse_da(rest, source, lineno)
            current.da_hits[line_no] = current.da_hits.get(line_no, 0) + hits
        elif key == _KEY_LF:
            current.declared_lf = _parse_summary_int(rest, source, lineno, key)
        elif key == _KEY_LH:
            current.declared_lh = _parse_summary_int(rest, source, lineno, key)
        elif key == _KEY_BRDA:
            current.brda.append(_parse_brda(rest, source, lineno))
        elif key == _KEY_BRF:
            current.declared_brf = _parse_summary_int(rest, source, lineno, key)
        elif key == _KEY_BRH:
            current.declared_brh = _parse_summary_int(rest, source, lineno, key)
        # Else: unknown but well-formed record. LCOV is an open-ended
        # format and downstream producers (cargo-llvm-cov, geninfo, ...)
        # add their own extensions. Skipping is the documented behavior.

    if current is not None:
        raise CoverageJsonParseError(
            f"{source}: trailing '{_KEY_SF}:{current.source_file}' block "
            f"not closed by '{_KEY_END}'"
        )


def _parse_da(rest: str, source: Path, lineno: int) -> tuple[int, int]:
    """Parse a ``DA:<line>,<hits>[,<md5>]`` record's value portion."""
    parts = rest.split(",")
    if len(parts) < 2:
        raise CoverageJsonParseError(
            f"{source}:{lineno}: malformed '{_KEY_DA}:' record (need at "
            f"least line,hits): {rest!r}"
        )
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise CoverageJsonParseError(
            f"{source}:{lineno}: '{_KEY_DA}:' has non-integer line/hits: "
            f"{rest!r}"
        ) from exc


def _parse_brda(
    rest: str, source: Path, lineno: int,
) -> tuple[int, int, int, int]:
    """Parse a ``BRDA:<line>,<block>,<branch>,<hits>`` record's value portion.

    LCOV reserves ``<hits> == "-"`` for "branch was never executed",
    distinct from ``0`` which would mean "the branch's containing block
    was entered but the branch did not fire". Both map to "not covered"
    for our purposes; we collapse ``-`` to ``0``.
    """
    parts = rest.split(",")
    if len(parts) != 4:
        raise CoverageJsonParseError(
            f"{source}:{lineno}: malformed '{_KEY_BRDA}:' record (need "
            f"exactly 4 fields line,block,branch,hits): {rest!r}"
        )
    try:
        line_no = int(parts[0])
        block = int(parts[1])
        branch = int(parts[2])
        hits = 0 if parts[3] == "-" else int(parts[3])
    except ValueError as exc:
        raise CoverageJsonParseError(
            f"{source}:{lineno}: '{_KEY_BRDA}:' has non-integer fields: "
            f"{rest!r}"
        ) from exc
    return line_no, block, branch, hits


def _parse_summary_int(rest: str, source: Path, lineno: int, key: str) -> int:
    """Parse a single-integer summary record (LF / LH / BRF / BRH)."""
    try:
        return int(rest)
    except ValueError as exc:
        raise CoverageJsonParseError(
            f"{source}:{lineno}: '{key}:' has non-integer value: {rest!r}"
        ) from exc


def _build_file_coverage(
    block: _LcovFileBlock,
    workspace_root: Path,
    warnings: list[str],
) -> FileCoverage:
    """Translate one accumulated SF: block into a ``FileCoverage``."""
    file_path = _workspace_relative(block.source_file, workspace_root, warnings)

    executed_lines = tuple(
        sorted(ln for ln, hits in block.da_hits.items() if hits > 0)
    )
    missing_lines = tuple(
        sorted(ln for ln, hits in block.da_hits.items() if hits == 0)
    )
    da_total = len(block.da_hits)
    da_hit = len(executed_lines)

    if block.declared_lf is not None and block.declared_lf != da_total:
        raise CoverageJsonParseError(
            f"LCOV block for {file_path!r}: declared 'LF:{block.declared_lf}' "
            f"disagrees with parsed DA-record count {da_total}"
        )
    if block.declared_lh is not None and block.declared_lh != da_hit:
        raise CoverageJsonParseError(
            f"LCOV block for {file_path!r}: declared 'LH:{block.declared_lh}' "
            f"disagrees with parsed DA-hit count {da_hit}"
        )

    executed_branches, missing_branches, branch_total, branch_hit = (
        _build_branch_pairs(block, file_path)
    )

    summary = CoverageSummary(
        num_statements=da_total,
        covered_statements=da_hit,
        missing_statements=da_total - da_hit,
        excluded_statements=0,
        num_branches=branch_total,
        covered_branches=branch_hit,
        missing_branches=branch_total - branch_hit,
        percent_covered=_percent_covered(da_total, da_hit),
    )

    return FileCoverage(
        file_path=file_path,
        executed_lines=executed_lines,
        missing_lines=missing_lines,
        excluded_lines=(),
        executed_branches=executed_branches,
        missing_branches=missing_branches,
        summary=summary,
        # LCOV in aggregate mode carries no per-test attribution (TN: is
        # blank from cargo-llvm-cov), so the test-to-code map is empty.
        line_contexts={},
    )


def _build_branch_pairs(
    block: _LcovFileBlock, file_path: str,
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[int, int], ...],
    int,
    int,
]:
    """Compute executed/missing branch pairs + summary counters for one file.

    When ``block.brda`` is empty (the cargo-llvm-cov default — see module
    docstring), all four return slots are empty/zero — branch coverage is
    simply unreported.

    When ``BRDA`` records are present, each unique
    ``(line, block, branch_index)`` triple becomes a ``(line, branch_index)``
    pair in ``executed_branches`` (hits > 0) or ``missing_branches``
    (hits == 0). Per-triple hit counts are summed across duplicate BRDA
    entries before the >0 check, so an instantiation that fires the
    branch once doesn't end up in both buckets.
    """
    if not block.brda:
        return ((), (), 0, 0)

    aggregated: dict[tuple[int, int, int], int] = {}
    for ln, blk, br, hits in block.brda:
        triple = (ln, blk, br)
        aggregated[triple] = aggregated.get(triple, 0) + hits

    executed: list[tuple[int, int]] = []
    missing: list[tuple[int, int]] = []
    # Sort by the triple so executed/missing tuples themselves are
    # deterministic (the on-disk schema sorts files by path; per-file
    # branch lists must be reproducible too).
    for (ln, _blk, br), hits in sorted(aggregated.items()):
        pair = (ln, br)
        if hits > 0:
            executed.append(pair)
        else:
            missing.append(pair)

    branch_total = len(aggregated)
    branch_hit = len(executed)

    if block.declared_brf is not None and block.declared_brf != branch_total:
        raise CoverageJsonParseError(
            f"LCOV block for {file_path!r}: declared 'BRF:{block.declared_brf}' "
            f"disagrees with unique-BRDA count {branch_total}"
        )
    if block.declared_brh is not None and block.declared_brh != branch_hit:
        raise CoverageJsonParseError(
            f"LCOV block for {file_path!r}: declared 'BRH:{block.declared_brh}' "
            f"disagrees with hit-BRDA count {branch_hit}"
        )

    return tuple(executed), tuple(missing), branch_total, branch_hit


def _aggregate_summary(files: list[FileCoverage]) -> CoverageSummary:
    """Sum per-file counters into the top-level ``CoverageSummary``."""
    num_statements = sum(f.summary.num_statements for f in files)
    covered_statements = sum(f.summary.covered_statements for f in files)
    num_branches = sum(f.summary.num_branches for f in files)
    covered_branches = sum(f.summary.covered_branches for f in files)
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=num_statements - covered_statements,
        excluded_statements=0,
        num_branches=num_branches,
        covered_branches=covered_branches,
        missing_branches=num_branches - covered_branches,
        percent_covered=_percent_covered(num_statements, covered_statements),
    )


def _percent_covered(num: int, covered: int) -> float:
    """Compute statement coverage percentage, rounded to 2 decimals.

    LCOV (like Istanbul) carries no top-level percent_covered we can
    echo, so we compute it. An empty file reports 100.0 (nothing to
    cover) — same convention as ``istanbul_parser``.
    """
    if num == 0:
        return 100.0
    return round(covered / num * 100.0, 2)


def _workspace_relative(
    abs_path: str,
    workspace_root: Path,
    warnings: list[str],
) -> str:
    """Convert an LCOV ``SF:`` path to a workspace-relative POSIX string.

    cargo-llvm-cov emits ABSOLUTE paths in ``SF:`` (e.g.
    ``/home/.../workspace/src/foo.rs``). Decision 2026-05-15 #6 mandates
    workspace-relative ``file_path`` for cross-run stability — the same
    fixture in a different temp workspace must produce comparable
    ``file_path`` values.

    Rare edge case: ``cargo-llvm-cov`` can report files OUTSIDE the
    workspace root (build-script generated code under ``target/``, paths
    walking up into rustc's standard library, etc.). Per the 2026-06-08
    amendment to ``decisions/2026-05-15-coverage-facts-json-layout.md``,
    the parser normalizes these to a ``../``-prefixed POSIX relpath via
    ``os.path.relpath`` — matching the istanbul and cobertura parsers so
    cross-ecosystem consumers see one uniform shape for outside-workspace
    paths. The original absolute ``SF:`` value is still surfaced in
    ``metadata['lcov_warnings']`` for forensic continuity (an operator
    debugging "why is `../../elsewhere/foo.rs` here?" can recover the
    native cargo-llvm-cov string without re-reading the LCOV file).
    """
    path = Path(abs_path)
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        # Outside-workspace: fall back to relpath (istanbul / cobertura
        # precedent) so `file_path` is never absolute. The shared
        # helper covers Windows cross-drive — ``os.path.relpath`` itself
        # raises ``ValueError`` when the drives differ, so a third
        # drive-stripped step is required for the 2026-06-09 Windows-CI
        # fix.
        relpath = relpath_or_drive_stripped(path, workspace_root)
        # The forensic warning text MUST stay POSIX-flavored — operators
        # and AI consumers see it across platforms, and the unit test
        # asserts a literal ``"/ws/cargo-project"`` substring. Coerce
        # workspace_root via ``Path.as_posix()`` so Windows-native
        # backslashes never leak into the warning.
        warnings.append(
            f"outside-workspace path (preserved as relpath "
            f"against workspace_root={Path(workspace_root).as_posix()!r}): "
            f"{abs_path} -> {relpath}"
        )
        return relpath
