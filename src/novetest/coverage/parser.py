"""Parser for coverage.py 7.x JSON reports.

Internal to the Coverage engine. Consumes the raw payload produced by Run
Team's pytest adapter (``--cov-report=json`` with ``show_contexts = True``
in ``.coveragerc``) and emits a structured ``CoverageFactSet``.

Relevant coverage.py JSON shape (per-file entry under ``files["<path>"]``):

    {
      "executed_lines":   [int, ...],
      "missing_lines":    [int, ...],
      "excluded_lines":   [int, ...],
      "executed_branches": [[from_line, to_line], ...],   // branch coverage
      "missing_branches":  [[from_line, to_line], ...],
      "summary": {
        "covered_lines":    int,
        "num_statements":   int,
        "percent_covered":  float,
        "missing_lines":    int,
        "excluded_lines":   int,
        "num_branches":     int,
        "covered_branches": int,
        "missing_branches": int
      },
      "contexts": {                       // only when show_contexts = True
        "<line>": ["<nodeid>|<phase>", ...]
      }
    }

Top-level ``totals`` block mirrors the per-file ``summary`` shape and gives
us the aggregate counters straight from coverage.py.

Branch-coverage fields are absent in non-branch coverage runs; we tolerate
that and treat the file as having zero branches.
"""

from __future__ import annotations

import time
from typing import Any

from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


# coverage.py emits contexts in the form ``"<nodeid>|<phase>"`` where
# ``<phase>`` is one of ``setup`` / ``run`` / ``teardown``. The empty
# string represents code executed outside any test context. We strip the
# phase suffix to produce clean nodeid strings for the test-to-code map.
_CONTEXT_SEPARATOR = "|"


class CoverageJsonParseError(ValueError):
    """Raised when the raw payload does not match coverage.py's documented shape."""


def parse_coverage_json(
    payload: dict[str, Any],
    *,
    run_reference: RunReference,
    engine_name: str,
    ecosystem: str,
    derived_at: int | None = None,
) -> CoverageFactSet:
    """Build a ``CoverageFactSet`` from a coverage.py 7.x JSON payload.

    ``mapping_granularity`` is inferred from the engine and the payload:
    - ``pytest`` + ``meta.show_contexts == True`` -> ``per-test``
    - ``pytest`` otherwise -> ``aggregate``
    - other engines default to ``aggregate``; later adapters (jest, go,
      etc.) will plug in their own granularity logic when this parser is
      generalized.

    Raises ``CoverageJsonParseError`` when required top-level keys are
    missing — that's a programmer / native-engine fault, not the same kind
    of "no coverage payload at all" condition we surface as
    ``CoverageUnavailable``.
    """
    files_raw = payload.get("files")
    totals_raw = payload.get("totals")
    if not isinstance(files_raw, dict):
        raise CoverageJsonParseError(
            "coverage.py JSON missing required top-level 'files' object"
        )
    if not isinstance(totals_raw, dict):
        raise CoverageJsonParseError(
            "coverage.py JSON missing required top-level 'totals' object"
        )

    meta = payload.get("meta") or {}
    show_contexts = bool(meta.get("show_contexts", False))
    granularity = _infer_mapping_granularity(engine_name, show_contexts)

    files: list[FileCoverage] = []
    # Sort by path for deterministic on-disk output (REQ-FOUND: deterministic
    # structured outputs for the same inputs).
    for path in sorted(files_raw.keys()):
        files.append(_parse_file_entry(path, dict(files_raw[path])))

    summary = _parse_summary(dict(totals_raw))

    metadata: dict[str, Any] = {}
    if "version" in meta:
        metadata["coverage_py_version"] = str(meta["version"])
    if "branch_coverage" in meta:
        metadata["branch_coverage"] = bool(meta["branch_coverage"])
    metadata["show_contexts"] = show_contexts

    return CoverageFactSet(
        run_reference=run_reference,
        engine_name=engine_name,
        ecosystem=ecosystem,
        mapping_granularity=granularity,
        summary=summary,
        files=tuple(files),
        derived_at=derived_at if derived_at is not None else int(time.time() * 1000),
        metadata=metadata,
    )


# --- internals ---------------------------------------------------------------


def _infer_mapping_granularity(engine_name: str, show_contexts: bool) -> str:
    """Map (engine, payload-shape) -> CoverageFactSet.mapping_granularity."""
    if engine_name == "pytest":
        return "per-test" if show_contexts else "aggregate"
    # Other ecosystems' adapters land in Phase 2.5/3; until then we treat
    # them as aggregate so the field is always populated (mandatory).
    return "aggregate"


def _parse_file_entry(file_path: str, entry: dict[str, Any]) -> FileCoverage:
    executed_lines = tuple(int(x) for x in entry.get("executed_lines", []))
    missing_lines = tuple(int(x) for x in entry.get("missing_lines", []))
    excluded_lines = tuple(int(x) for x in entry.get("excluded_lines", []))
    executed_branches = tuple(
        _branch_pair(b) for b in entry.get("executed_branches", [])
    )
    missing_branches = tuple(
        _branch_pair(b) for b in entry.get("missing_branches", [])
    )

    summary_raw = entry.get("summary")
    if not isinstance(summary_raw, dict):
        raise CoverageJsonParseError(
            f"file entry for {file_path!r} missing required 'summary' object"
        )
    summary = _parse_summary(dict(summary_raw))

    contexts_raw = entry.get("contexts") or {}
    line_contexts: dict[int, tuple[str, ...]] = {}
    if isinstance(contexts_raw, dict):
        for line_str, raw_nodeids in contexts_raw.items():
            cleaned = _clean_context_nodeids(raw_nodeids)
            if cleaned:
                line_contexts[int(line_str)] = cleaned

    return FileCoverage(
        file_path=file_path,
        executed_lines=executed_lines,
        missing_lines=missing_lines,
        excluded_lines=excluded_lines,
        executed_branches=executed_branches,
        missing_branches=missing_branches,
        summary=summary,
        line_contexts=line_contexts,
    )


def _parse_summary(raw: dict[str, Any]) -> CoverageSummary:
    """Translate a coverage.py ``summary`` / ``totals`` dict to ``CoverageSummary``.

    coverage.py uses ``covered_lines`` / ``missing_lines`` (line-count
    integers) and ``num_statements`` for the file/total. We rename to
    ``covered_statements`` / ``missing_statements`` in our model to avoid
    name collision with the file-level ``missing_lines: list[int]`` array
    (statements-by-line-numbers vs missing-count would otherwise share a
    key in different scopes).
    """
    try:
        num_statements = int(raw["num_statements"])
        covered_statements = int(raw["covered_lines"])
        missing_statements = int(raw["missing_lines"])
        percent_covered = float(raw["percent_covered"])
    except KeyError as exc:
        raise CoverageJsonParseError(
            f"coverage.py summary block missing required key: {exc.args[0]!r}"
        ) from exc

    excluded_statements = int(raw.get("excluded_lines", 0))
    num_branches = int(raw.get("num_branches", 0))
    covered_branches = int(raw.get("covered_branches", 0))
    missing_branches = int(raw.get("missing_branches", 0))

    return CoverageSummary(
        num_statements=num_statements,
        covered_statements=covered_statements,
        missing_statements=missing_statements,
        excluded_statements=excluded_statements,
        num_branches=num_branches,
        covered_branches=covered_branches,
        missing_branches=missing_branches,
        percent_covered=percent_covered,
    )


def _branch_pair(raw: Any) -> tuple[int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise CoverageJsonParseError(
            f"branch arc must be a 2-element sequence, got {raw!r}"
        )
    return (int(raw[0]), int(raw[1]))


def _clean_context_nodeids(raw: Any) -> tuple[str, ...]:
    """Extract nodeids from coverage.py's per-line contexts list.

    Coverage.py contexts have shape ``"<nodeid>|<phase>"`` (or just ``""``
    for non-test-attributed execution). We:
    - drop entries whose nodeid is empty (module-import / global-scope
      execution we cannot attribute to a test)
    - strip the ``|<phase>`` suffix so the same nodeid across setup/call/
      teardown phases collapses to a single attribution
    - de-duplicate while preserving sort order so output is deterministic
    """
    if not isinstance(raw, list):
        return ()
    seen: set[str] = set()
    nodeids: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        nodeid = entry.split(_CONTEXT_SEPARATOR, 1)[0]
        if not nodeid:
            continue
        if nodeid in seen:
            continue
        seen.add(nodeid)
        nodeids.append(nodeid)
    nodeids.sort()
    return tuple(nodeids)
