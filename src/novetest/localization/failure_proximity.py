"""``failure_proximity`` mode — rank files by failure-trace mentions.

Last-resort Localization mode for runs that have failed tests but no
coverage data at all (``CoverageFactSet`` unavailable). Algorithm
(strategy doc §2 "failure_proximity" + §"Most defensible fallback
hierarchy" item 3):

1. For each failing ``TestResult``, parse its ``failure_reference``
   into a sequence of ``(file, line)`` tuples using an engine-specific
   regex set.
2. Aggregate per-file occurrence counts across all failing tests.
3. If a ``RegressionFactSet`` is provided AND has changed files,
   multiply the per-file score by ``(1 + α)`` where ``α = 0.5`` —
   FLUCCS-style prior (Sohn & Yoo, ISSTA 2017).
4. Rank files by aggregated score, min-max normalize within the full
   ranking, dense-rank with ties, truncate to ``top_n``.
5. Produce a ``LocalizationFinding`` with ``mode = "failure_proximity"``,
   ``confidence = "low"``, file-level ``CodeLocation`` kind, and the
   v1 freeze-pinned envelope-shape deviation (per the task brief §7):

   - ``alternate_scores_available = ()`` (empty tuple) — no SBFL formulas
     were computed.
   - ``entries[*].alternate_scores = {}`` (empty dict) — same reason.

The ``formula`` field on both the finding and per-entry is set to
``"ochiai"`` as a placeholder so the closed-enum ``__post_init__``
validation passes; downstream consumers MUST gate on
``finding.mode == "failure_proximity"`` rather than ``formula`` to know
that no SBFL scores are present.

**Why this is NOT under ``sbfl/``**: failure_proximity is a different
ranking technique (heuristic frequency count + regression prior), not
SBFL. Keeping the module a sibling of ``sbfl/`` rather than a child
keeps the package taxonomy honest: ``sbfl/`` is reserved for the four
formula implementations + spectra builders that share an ``(ef, ep,
nf, np)`` interface.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

from novetest.memory.project_store import ProjectStore
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord


# FLUCCS-style regression-reweighting boost factor (Sohn & Yoo, ISSTA 2017).
# Multiplicative: ``score *= (1 + ALPHA)`` for files in the regression
# change set. ``0.5`` is the published tuned value in the FLUCCS paper.
_REGRESSION_BOOST_ALPHA: Final[float] = 0.5

# Evidence-line cap per file entry — mirrors derive.py's ``_EVIDENCE_LINE_CAP``
# so the LocalizationFinding's per-entry payload stays bounded.
_EVIDENCE_LINE_CAP: Final[int] = 10

# Outcome bucket — failed-like outcomes are the ones whose failure trace
# we care about. Mirrors ``derive.py::_FAILED_OUTCOMES``.
_FAILED_OUTCOMES: Final[frozenset[str]] = frozenset({"failed", "errored"})

# Placeholder formula string used on the LocalizationFinding so the
# closed-enum validation passes; failure_proximity does not compute any
# SBFL formula. Consumers MUST gate on ``finding.mode`` not ``formula``.
_PLACEHOLDER_FORMULA: Final[str] = "ochiai"


# ---------------------------------------------------------------------------
# Per-engine failure-log regex sets
# ---------------------------------------------------------------------------
#
# Each regex MUST capture (file_path, line_number) as groups 1 and 2.
# Best-effort posture: a regex that matches yields a tuple; no match
# yields nothing — we never raise on a malformed log. Multiple regexes
# per engine cover format variance within the same engine.

# Path chars: starts with an alpha/underscore/dot/slash (allow absolute and
# relative forms), then alphanumerics + path separators + dashes/dots.
# ``./`` and ``../`` opening segments are common in jest/cargo absolute frames.
_FILE_PATH_CHARS = r"[A-Za-z_./][\w\-./\\]*"
_PYTHON_FILE_CHARS = _FILE_PATH_CHARS

_PYTEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # Format A (preferred — set by ``pytest_adapter`` when ``crash`` block
    # is present): ``<path>:<lineno>: <message>``. Anchored at line start
    # or end of "File "<path>", line N" form is the secondary pattern.
    re.compile(rf"({_PYTHON_FILE_CHARS}\.py):(\d+):"),
    # Traceback file frame: ``File "<path>", line N, in <name>``.
    re.compile(rf'File "({_PYTHON_FILE_CHARS}\.py)", line (\d+)'),
)

_JS_FILE_EXT = r"(?:js|jsx|ts|tsx|mjs|cjs)"

_JEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # ``at <name> (<path>:<line>:<col>)`` — Node.js stack frame, the
    # common form in jest's ``failureMessages``.
    re.compile(rf"\(({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+\)"),
    # Bare ``at <path>:<line>:<col>`` — when no enclosing function name.
    re.compile(rf"\s+at\s+({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+"),
    # Jest's ``at Object.<anonymous> (<path>:<line>:<col>)`` — covered by
    # the first regex (parens form) but also handle the ``> N | ...``
    # diagnostic context line that jest prints alongside the trace
    # (the standalone ``<path>:<line>:<col>`` form before the stack).
    re.compile(rf"^\s*({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+", re.MULTILINE),
)

_CARGO_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # Standard libtest panic: ``thread '...' panicked at <path>:<line>:<col>``.
    re.compile(rf"panicked at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # ``assertion `...` failed at <path>:<line>:<col>`` — newer rustc forms.
    re.compile(rf"failed at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # NOTE: a third "defensive catch-all" regex (`\b(...)\.rs:(\d+):\d+`)
    # used to live here. It was DROPPED at 2026-05-31 (Defect 3 fix,
    # CEO-implied Option D) because cargo nextest's default stack
    # backtrace (no `RUST_BACKTRACE=1` needed) contains every frame's
    # path including Rust stdlib files like
    # ``/rustc/<hash>/library/core/src/panicking.rs:N:M``. The catch-all
    # would slurp those stdlib paths and tie them with the real bug
    # file at e_f=1; lexicographic tie-break (the algorithm sorts ties
    # by file path ascending) pushed `src/arithmetic.rs` to rank #4
    # behind three `/rustc/...` paths. Now only the two anchored
    # patterns above match — the panic-at frame is the load-bearing
    # extraction surface. Algorithm-side filter in ``_derive_aggregate``
    # (intersection with covered files) is the defense-in-depth layer
    # that catches any remaining stdlib-path leakage from future
    # adapter / rustc backtrace shape changes.
    #
    # Source: questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
)

_GOTEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # ``--- FAIL: TestX`` is followed by frames like ``  add_test.go:14: ...``.
    re.compile(rf"^\s+({_PYTHON_FILE_CHARS}\.go):(\d+):", re.MULTILINE),
    # Go panic-style stack frames: ``\t<path>:<line> +<offset>``.
    re.compile(rf"^\s+({_PYTHON_FILE_CHARS}\.go):(\d+)\s", re.MULTILINE),
)

# Engine-name keyed regex table. Unknown engines fall back to pytest's
# pattern (the most permissive — file-path-colon-lineno is a near-universal
# convention). This is "best-effort" per the task brief: a parser that
# finds nothing is acceptable; one that crashes is not.
_ENGINE_REGEX_TABLE: Final[dict[str, tuple[re.Pattern[str], ...]]] = {
    "pytest": _PYTEST_REGEXES,
    "jest": _JEST_REGEXES,
    "cargo-test": _CARGO_REGEXES,
    "gotest": _GOTEST_REGEXES,
    "go-test": _GOTEST_REGEXES,
}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def parse_failure_log(
    engine_name: str,
    failure_text: str,
) -> tuple[tuple[str, int], ...]:
    """Extract canonical ``(file, line)`` tuples from a failure-log string.

    Engine-keyed regex dispatch picks the right pattern set; unknown
    engines fall back to the pytest regexes (most permissive). The
    output preserves first-seen order and drops duplicates so a file
    mentioned at the same line in multiple stack frames counts once
    per failing test (the aggregation in ``derive_failure_proximity``
    deduplicates across tests separately).

    Returns an empty tuple when nothing matches — the caller decides
    whether to record a parse warning (the brief mandates a metadata
    ``parse_warnings`` entry on each test whose log was un-parseable).
    """
    if not failure_text:
        return ()
    regexes = _ENGINE_REGEX_TABLE.get(engine_name, _PYTEST_REGEXES)
    seen: set[tuple[str, int]] = set()
    results: list[tuple[str, int]] = []
    for pattern in regexes:
        for match in pattern.finditer(failure_text):
            file_path = match.group(1)
            try:
                line = int(match.group(2))
            except (ValueError, IndexError):
                continue
            key = (file_path, line)
            if key in seen:
                continue
            seen.add(key)
            results.append(key)
    return tuple(results)


def resolve_failure_text(
    store: ProjectStore,
    run_id: str,
    engine_name: str,
    failure_reference: str | None,
) -> str:
    """Resolve a ``TestResult.failure_reference`` into the raw failure-log text.

    Engine-dispatched: pytest and jest store the full failure text
    inline (the adapter normalizer concatenates ``crash.message`` or
    ``failureMessages``); cargo-test and gotest store a project-store-
    relative path to a per-test log file under
    ``<artifact_dir>/native/failures/<name>.log``.

    Returns the empty string when:
    - ``failure_reference`` is ``None`` or empty.
    - The engine is unrecognized (defensive — we'd rather return empty
      than misroute a path-string into the regex).
    - The expected log file does not exist on disk (artifact pruned or
      adapter quirk).

    Disk IO is best-effort: a permission error or invalid encoding
    returns the empty string rather than propagating. The downstream
    parser handles empty input by returning no matches.
    """
    if not failure_reference:
        return ""
    if engine_name in ("pytest", "jest"):
        return failure_reference
    if engine_name in ("cargo-test", "gotest", "go-test"):
        artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"
        log_path = artifact_dir / failure_reference
        if not log_path.is_file():
            return ""
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    # Unknown engine — defensively return empty rather than guess.
    return ""


def derive_failure_proximity(
    *,
    store: ProjectStore,
    record: RunRecord,
    failed_test_ids: frozenset[str],
    regression_facts: RegressionFactSet | None,
    top_n: int,
) -> LocalizationFinding:
    """Build the ``failure_proximity`` LocalizationFinding for this run.

    Preconditions (validated by the caller in ``derive.py``):

    - ``failed_test_ids`` is non-empty (otherwise the strategy doc §5
      says to return ``LocalizationUnavailable(REASON_NO_FAILED_TESTS)``).

    Empty findings are returned when every failing test's failure log
    is empty or un-parseable; ``finding.metadata["parse_warnings"]``
    enumerates the unfortunate test ids so consumers can investigate.
    """
    parse_warnings: list[str] = []
    file_to_failed_tests: dict[str, set[str]] = defaultdict(set)
    file_to_evidence_lines: dict[str, set[int]] = defaultdict(set)

    # Workspace root for path normalization (B2-2 UX normalization,
    # 2026-06-08). ``store.path`` is ``<workspace>/.novetest/``; the
    # workspace root sits one level up. Same pattern as
    # ``derive.py::_resolve_repo_path`` but the OPPOSITE direction
    # (abs → rel here; rel → abs there). Hoisted out of the loop so the
    # one-level-up resolution runs once per derivation, not once per
    # parsed tuple.
    workspace_root = store.path.parent

    for tr in record.test_results:
        if tr.outcome not in _FAILED_OUTCOMES:
            continue
        if tr.node_id not in failed_test_ids:
            # Defensive: ``failed_test_ids`` is the authoritative set
            # the caller computed; honor it even if the underlying
            # outcome filter would have picked up additional tests
            # (e.g. an "errored" outcome the caller chose to exclude).
            continue
        failure_text = resolve_failure_text(
            store, record.run_reference.run_id, record.engine_name, tr.failure_reference
        )
        if not failure_text:
            parse_warnings.append(
                f"{tr.node_id}: failure_reference empty or unresolvable"
            )
            continue
        tuples = parse_failure_log(record.engine_name, failure_text)
        if not tuples:
            parse_warnings.append(
                f"{tr.node_id}: no parseable file:line references in failure log"
            )
            continue
        for file_path, line in tuples:
            # B2-2: normalize the parser's emitted file path to
            # workspace-relative form. Most failure-log parsers (pytest's
            # ``crash.path``, cargo nextest's panic frame, etc.) carry
            # absolute paths verbatim; the other Localization modes
            # source from CoverageFactSet whose adapter contract yields
            # repo-relative paths. Normalize here so all three modes
            # emit a single mode-invariant ``code_location.file`` shape.
            relative_file = _normalize_to_workspace_relative(
                file_path, workspace_root
            )
            file_to_failed_tests[relative_file].add(tr.node_id)
            file_to_evidence_lines[relative_file].add(line)

    changed_files = _changed_files_from_regression(regression_facts)
    regression_reweighted = bool(changed_files) and bool(file_to_failed_tests)

    # Build per-file candidates with raw scores. The raw score is the
    # number of distinct failing tests whose failure trace mentions the
    # file (capped at total_failing for sanity). The regression prior
    # multiplies the score; the absolute scale is preserved so
    # ``score_raw`` stays explainable as "this many failing tests
    # mentioned this file" (boosted by 1.5x for changed-set hits).
    candidates: list[tuple[str, float, set[str], set[int]]] = []
    for file_path, tests in file_to_failed_tests.items():
        base_score = float(len(tests))
        if file_path in changed_files:
            base_score *= 1.0 + _REGRESSION_BOOST_ALPHA
        candidates.append(
            (file_path, base_score, tests, file_to_evidence_lines[file_path])
        )

    # Sort by score desc; tiebreak by file path ascending so two runs
    # with identical inputs produce identical rankings.
    candidates.sort(key=lambda c: (-c[1], c[0]))

    raw_scores = [c[1] for c in candidates]
    normalized = _min_max_normalize(raw_scores)
    ranks = _dense_ranks(raw_scores)

    truncated = candidates[:top_n]
    truncated_norm = normalized[:top_n]
    truncated_ranks = ranks[:top_n]

    by_rank: dict[int, list[int]] = defaultdict(list)
    for idx, rank in enumerate(truncated_ranks):
        by_rank[rank].append(idx)

    entries: list[LocalizationEntry] = []
    for idx, ((file_path, raw_score, failed_tests, evidence_lines), norm_score, rank) in enumerate(
        zip(truncated, truncated_norm, truncated_ranks, strict=True)
    ):
        peers = tuple(
            f"entry_index_{p}" for p in by_rank[rank] if p != idx
        )
        sorted_lines = tuple(sorted(evidence_lines))[:_EVIDENCE_LINE_CAP]
        # ``primary_line`` is required-int on the model. When evidence
        # lines exist (always true here — files only land in candidates
        # via the parser, which always produces a line number), use the
        # first one; otherwise sentinel 0 ("unknown line").
        primary_line = sorted_lines[0] if sorted_lines else 0

        related = tuple(sorted(failed_tests))
        citations: list[EvidenceCitation] = []
        for nodeid in related:
            citations.append(
                EvidenceCitation(
                    kind="test_result",
                    run_reference=record.run_reference,
                    selector={"test_id": nodeid, "outcome": "failed"},
                )
            )

        entries.append(
            LocalizationEntry(
                rank=rank,
                tied_with=peers,
                code_location=CodeLocation(
                    kind="file",
                    file=file_path,
                    symbol=None,
                    line_range=None,
                    primary_line=primary_line,
                    evidence_lines=sorted_lines,
                ),
                score_raw=raw_score,
                score_normalized=norm_score,
                formula=_PLACEHOLDER_FORMULA,
                # Brief §7 deviation: failure_proximity is NOT SBFL, so
                # alternate_scores is the empty dict.
                alternate_scores={},
                related_failed_tests=related,
                evidence_citations=tuple(citations),
            )
        )

    metadata: dict[str, Any] = {
        "regression_reweighted": regression_reweighted,
        "changed_files_count": len(changed_files),
    }
    if parse_warnings:
        metadata["parse_warnings"] = parse_warnings

    return LocalizationFinding(
        run_reference=record.run_reference,
        engine_name=record.engine_name,
        ecosystem=record.ecosystem,
        mode="failure_proximity",
        confidence="low",
        formula=_PLACEHOLDER_FORMULA,
        # Brief §7 deviation: empty tuple because no alternate SBFL formulas
        # were computed for this mode.
        alternate_scores_available=(),
        top_n=top_n,
        entries=tuple(entries),
        derived_at=int(time.time() * 1000),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _changed_files_from_regression(
    regression_facts: RegressionFactSet | None,
) -> frozenset[str]:
    """Extract the FLUCCS-style "changed files" set from a RegressionFactSet.

    Defined as the union of:
    - ``coverage_change.files_added`` (covered in target but not baseline)
    - ``coverage_change.files_removed`` (covered in baseline but not target)
    - ``coverage_change.file_deltas[*].file_path`` (covered in both but
      with newly-covered or newly-uncovered lines)

    Returns the empty frozenset when ``regression_facts`` is ``None`` or
    when its ``coverage_change`` block is absent — the regression boost
    is then a no-op. This matches the brief's "best-effort" stance:
    absence of Regression Facts is normal and does not affect the
    aggregate ranking apart from removing the prior.

    The ``RegressionFactSet.coverage_change`` field is a raw dict (per
    decision §C.6) embedded verbatim from ``CoverageDelta.to_dict()``;
    we read it defensively as ``Mapping``-shaped data without re-parsing
    into the typed model.
    """
    if regression_facts is None:
        return frozenset()
    cc = regression_facts.coverage_change
    if not isinstance(cc, dict):
        return frozenset()
    files: set[str] = set()
    for key in ("files_added", "files_removed"):
        raw = cc.get(key)
        if isinstance(raw, list):
            files.update(str(p) for p in raw if isinstance(p, str))
    deltas_raw = cc.get("file_deltas")
    if isinstance(deltas_raw, list):
        for delta in deltas_raw:
            if isinstance(delta, dict):
                fp = delta.get("file_path")
                if isinstance(fp, str):
                    files.add(fp)
    return frozenset(files)


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize into ``[0, 1]`` with all-zero on zero spread.

    Mirrors ``derive.py::_min_max_normalize`` so cross-mode ranking
    output stays consistent. Duplicated rather than imported to keep
    the failure_proximity module standalone; ``derive.py`` owns the
    canonical helper for SBFL paths.
    """
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi == lo:
        return [0.0 for _ in scores]
    span = hi - lo
    return [(s - lo) / span for s in scores]


def _dense_ranks(sorted_scores: list[float]) -> list[int]:
    """Return 1-based dense ranks for a DESC-sorted list of scores.

    Mirrors ``derive.py::_dense_ranks`` — same dense-rank convention so
    the ``rank`` field has identical semantics across all three modes.
    """
    ranks: list[int] = []
    current_rank = 0
    previous_score: float | None = None
    for score in sorted_scores:
        if previous_score is None or score != previous_score:
            current_rank += 1
            previous_score = score
        ranks.append(current_rank)
    return ranks


def _normalize_to_workspace_relative(
    file_path: str, workspace_root: Path
) -> str:
    """Normalize a parsed failure-log file path to workspace-relative form.

    Returns workspace-relative path when the input is absolute AND lies
    under ``workspace_root``; otherwise returns ``file_path`` unchanged.
    Idempotent on already-relative inputs (the common case for the
    existing fixture tests).

    Brief (B2-2 UX normalization, 2026-06-08): failure_proximity emits
    absolute paths in production because pytest's ``crash.path``, cargo
    nextest's panic frame, jest stack traces, etc. carry absolute paths
    verbatim. Other Localization modes (sbfl_per_test, sbfl_aggregate)
    are sourced from CoverageFactSet whose adapter contract yields
    repo-relative paths. This helper aligns failure_proximity with the
    envelope-wide convention. Spec pinned in
    ``design/interace-contract/localization.md`` §"Result shape —
    mode-invariant".

    Paths OUTSIDE the workspace (e.g. ``/usr/lib/python/.../stdlib.py``
    in pytest tracebacks, or ``/rustc/<hash>/.../panicking.rs`` frames
    in cargo) are left absolute — they cannot be made workspace-
    relative meaningfully and surface as an obvious "not your code" cue
    to consumers. This is a defensive contract: the parser's catch-all
    patterns (notably the dropped cargo catch-all from Defect 3, 2026-
    05-31) historically leaked stdlib paths; preserving absolute form
    for such paths keeps the existing Defect-3 defensive posture intact
    (the aggregate mode's covered-files intersection drops them; the
    failure_proximity mode does NOT have an analogous filter and the
    absolute form is the next-best disambiguation signal).

    Note: this helper does NOT call ``Path.resolve()`` on either side.
    Symlinks / case-insensitive filesystems / NFS mounts may cause a
    workspace path to look like ``/A/ws/file.py`` while the failure log
    emits ``/B/ws/file.py`` (same underlying inode via symlink). Such
    paths fall through to the "kept absolute" branch — same posture as
    paths genuinely outside the workspace. A future cycle can add a
    symlink-resolving variant if the corner case surfaces in Manual
    Test; for v1 the conservative non-resolving form is sufficient.
    """
    candidate = Path(file_path)
    if not candidate.is_absolute():
        return file_path
    try:
        relative = candidate.relative_to(workspace_root)
    except ValueError:
        # Not under workspace_root (e.g. stdlib path); keep absolute as-is.
        return file_path
    return str(relative)


