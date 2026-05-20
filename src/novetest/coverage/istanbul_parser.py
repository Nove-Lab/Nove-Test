"""Parser for Istanbul ``coverage-final.json`` reports (jest's json reporter).

Internal to the Coverage engine. Consumes the raw payload jest's
``--coverage --coverageReporters=json`` produces and emits a structured
``CoverageFactSet``. This is the jest counterpart to ``parser.py`` (which
handles coverage.py's JSON). ``derive.py`` dispatches on ``engine_name``.

Istanbul ``coverage-final.json`` is a JSON object keyed by ABSOLUTE source
file path; each value carries:

    {
      "path": "/abs/path/file.js",
      "statementMap": {"0": {"start": {"line": L, "column": C}, "end": {...}}, ...},
      "fnMap":        {"0": {...}, ...},
      "branchMap":    {"0": {"type": "...", "locations": [...]}, ...},
      "s": {"0": <hitCount>, ...},   // statement hit counts
      "f": {"0": <hitCount>, ...},   // function hit counts
      "b": {"0": [<hit>, ...], ...}  // branch hit counts per path location
    }

Istanbul -> frozen-schema mapping decisions (see the handoff
``agent-comms/handoffs/coverage-team-2026-05-20-jest-istanbul-parser.md``):

- ``mapping_granularity`` is ``aggregate``. jest's default ``--coverage``
  merges coverage across the whole run with no per-test attribution, so
  ``line_contexts`` stays empty (decision 2026-05-15 constraint #5).
- Istanbul tracks STATEMENTS. Statement hit counts (``s``) drive the
  ``*_statements`` summary counters; line numbers for ``executed_lines`` /
  ``missing_lines`` are derived from ``statementMap[].start.line``. A line
  counts as executed when ANY statement starting on it was hit.
- Istanbul's branch model (a branch point with N path locations) does not
  map onto coverage.py's ``[from_line, to_line]`` control-flow arcs without
  fabricating edges. Rather than emit misleading arcs that Localization
  (Phase 4) would consume as Code Locations, the jest path reports ZERO
  branches. This is a documented limitation, not a parse failure.
- ``percent_covered`` is computed (Istanbul JSON carries no summary block):
  ``100.0`` when there are no statements, else
  ``covered_statements / num_statements * 100`` rounded to 2 decimals
  (matching jest's own ``% Stmts`` text-table convention).
- ``file_path`` is made workspace-relative (decision 2026-05-15
  constraint #6) by relativizing the absolute Istanbul path against the
  Run's workspace root.

Parse-shape errors raise ``CoverageJsonParseError`` (reused from
``parser.py``) so ``derive_coverage_facts`` surfaces them uniformly as the
``native-payload-corrupt`` unavailable outcome.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


# jest's default ``--coverage`` produces a single merged report with no
# per-test attribution; ``aggregate`` is the only honest granularity.
_JEST_MAPPING_GRANULARITY = "aggregate"


def parse_istanbul_json(
    payload: dict[str, Any],
    *,
    run_reference: RunReference,
    engine_name: str,
    ecosystem: str,
    workspace_root: Path,
    derived_at: int | None = None,
) -> CoverageFactSet:
    """Build a ``CoverageFactSet`` from an Istanbul ``coverage-final.json``.

    ``payload`` is the whole Istanbul object — a map keyed by absolute file
    path. ``workspace_root`` is the directory the Run executed in; it is
    used to convert Istanbul's absolute paths to workspace-relative ones
    (decision 2026-05-15 constraint #6).

    An empty ``payload`` is a valid (if degenerate) zero-file report, not a
    corruption. Raises ``CoverageJsonParseError`` when a file entry does not
    match Istanbul's documented shape.
    """
    files: list[FileCoverage] = []
    for abs_path in payload:
        entry = payload[abs_path]
        if not isinstance(entry, dict):
            raise CoverageJsonParseError(
                f"Istanbul entry for {abs_path!r} is not an object"
            )
        rel_path = _workspace_relative(str(abs_path), workspace_root)
        files.append(_parse_istanbul_file(rel_path, entry))

    # Sort by path for deterministic on-disk output (REQ-FOUND: deterministic
    # structured outputs for the same inputs).
    files.sort(key=lambda f: f.file_path)
    summary = _aggregate_summary(files)

    return CoverageFactSet(
        run_reference=run_reference,
        engine_name=engine_name,
        ecosystem=ecosystem,
        mapping_granularity=_JEST_MAPPING_GRANULARITY,
        summary=summary,
        files=tuple(files),
        derived_at=derived_at if derived_at is not None else int(time.time() * 1000),
        metadata={"coverage_format": "istanbul", "branch_mapping": "omitted"},
    )


# --- internals ---------------------------------------------------------------


def _parse_istanbul_file(file_path: str, entry: dict[str, Any]) -> FileCoverage:
    """Translate one Istanbul per-file entry into a ``FileCoverage``."""
    statement_map = entry.get("statementMap")
    s_counts = entry.get("s")
    if not isinstance(statement_map, dict):
        raise CoverageJsonParseError(
            f"Istanbul entry for {file_path!r} missing 'statementMap' object"
        )
    if not isinstance(s_counts, dict):
        raise CoverageJsonParseError(
            f"Istanbul entry for {file_path!r} missing 's' (statement hits) object"
        )

    # A line is "executed" when ANY statement starting on it was hit, and
    # "missing" when it carries statements but none of them were hit.
    line_hit: dict[int, bool] = {}
    covered_statements = 0
    for idx, loc in statement_map.items():
        line = _statement_line(file_path, str(idx), loc)
        hit = _hit_count(file_path, str(idx), s_counts.get(idx, 0)) > 0
        if hit:
            covered_statements += 1
        line_hit[line] = line_hit.get(line, False) or hit

    executed_lines = tuple(sorted(ln for ln, hit in line_hit.items() if hit))
    missing_lines = tuple(sorted(ln for ln, hit in line_hit.items() if not hit))
    num_statements = len(statement_map)

    return FileCoverage(
        file_path=file_path,
        executed_lines=executed_lines,
        missing_lines=missing_lines,
        excluded_lines=(),
        # Istanbul branches do not map cleanly onto coverage.py arcs; the
        # jest path reports zero branches rather than fabricate Code
        # Locations (see module docstring).
        executed_branches=(),
        missing_branches=(),
        summary=_statement_summary(num_statements, covered_statements),
        line_contexts={},
    )


def _statement_line(file_path: str, idx: str, loc: Any) -> int:
    """Extract the 1-based start line of an Istanbul ``statementMap`` entry."""
    if not isinstance(loc, dict):
        raise CoverageJsonParseError(
            f"Istanbul statementMap[{idx}] for {file_path!r} is not an object"
        )
    start = loc.get("start")
    if not isinstance(start, dict) or "line" not in start:
        raise CoverageJsonParseError(
            f"Istanbul statementMap[{idx}] for {file_path!r} missing 'start.line'"
        )
    try:
        return int(start["line"])
    except (TypeError, ValueError) as exc:
        raise CoverageJsonParseError(
            f"Istanbul statementMap[{idx}] for {file_path!r} has non-integer "
            f"start.line: {start['line']!r}"
        ) from exc


def _hit_count(file_path: str, idx: str, raw: Any) -> int:
    """Validate and return an Istanbul statement hit count."""
    # ``bool`` is an ``int`` subclass but is never a valid hit count.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CoverageJsonParseError(
            f"Istanbul hit count 's[{idx}]' for {file_path!r} is not an "
            f"integer: {raw!r}"
        )
    return raw


def _statement_summary(num_statements: int, covered_statements: int) -> CoverageSummary:
    """Build a ``CoverageSummary`` from statement counts (zero branches)."""
    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=num_statements - covered_statements,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=_percent_covered(num_statements, covered_statements),
    )


def _aggregate_summary(files: list[FileCoverage]) -> CoverageSummary:
    """Sum per-file statement counters into the top-level summary."""
    num_statements = sum(f.summary.num_statements for f in files)
    covered_statements = sum(f.summary.covered_statements for f in files)
    return _statement_summary(num_statements, covered_statements)


def _percent_covered(num_statements: int, covered_statements: int) -> float:
    """Compute statement coverage percentage, rounded to 2 decimals.

    Istanbul's ``coverage-final.json`` carries no summary block, so unlike
    the coverage.py path we must compute this rather than echo an
    engine-reported value. An empty file reports 100.0 (nothing to cover).
    """
    if num_statements == 0:
        return 100.0
    return round(covered_statements / num_statements * 100.0, 2)


def _workspace_relative(abs_path: str, workspace_root: Path) -> str:
    """Convert an absolute Istanbul path to a workspace-relative POSIX path.

    Decision 2026-05-15 constraint #6: persisted ``file_path`` is always
    workspace-relative; absolute paths are a contract violation. POSIX
    separators keep the on-disk form deterministic across platforms and
    consistent with the pytest adapter's ``relative_files`` output.
    """
    path = Path(abs_path)
    try:
        relative = path.relative_to(workspace_root)
    except ValueError:
        # File outside the workspace root — fall back to a computed
        # relative path so we never persist an absolute one.
        relative = Path(os.path.relpath(path, workspace_root))
    return relative.as_posix()
