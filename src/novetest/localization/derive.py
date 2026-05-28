"""End-to-end SBFL derivation — the per-test path.

Pipeline (per design-of-record §1–§6 + task brief §7):

  1. retrieve_run_evidence       — raises → REASON_NO_RUN_EVIDENCE.
  2. tombstoned input            → REASON_RUN_NOT_ANALYZABLE.
  3. failed tests == 0           → REASON_NO_FAILED_TESTS.
  4. get_coverage_facts          — unavailable → REASON_NO_COVERAGE.
  5. coverage_facts.mapping_granularity != "per-test"
                                  → REASON_NO_COVERAGE (detail =
                                    "sbfl_aggregate not yet implemented").
  6. build_spectra.
  7. compute ef/ep/nf/np per location, call all 4 formulas.
  8. aggregate up to symbols via Python ast resolver (max(score) per
     symbol per design-of-record §3).
  9. min-max normalize within the FULL ranking (before truncation), dense
     1-based rank, compute tie groups, take top_n.
 10. attach EvidenceCitations per entry.
 11. assemble LocalizationFinding + persist via the atomic
     ``write_localization_findings`` helper.

The cache-aware entry ``derive_localization_findings`` mirrors the
``compare_runs`` / ``derive_coverage_facts`` pattern: read the cached
``localization_findings.json`` when present, otherwise derive fresh and
write. Tombstoned input short-circuits to ``REASON_RUN_NOT_ANALYZABLE``
regardless of cache state, matching the Regression engine's policy
(strategy doc §5 — strict on tombstoned inputs).
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from novetest.coverage.retrieval import get_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.localization.persistence import (
    read_localization_findings_raw,
    write_localization_findings,
)
from novetest.localization.results import (
    REASON_NO_COVERAGE,
    REASON_NO_FAILED_TESTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.localization.retrieval import check_localization_availability
from novetest.localization.sbfl.dstar import dstar2
from novetest.localization.sbfl.ochiai import ochiai
from novetest.localization.sbfl.op2 import op2
from novetest.localization.sbfl.spectra import Spectra, build_spectra
from novetest.localization.sbfl.tarantula import tarantula
from novetest.localization.symbol_resolver import resolve_python_symbol
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import (
    RunEvidenceNotFoundError,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


# Default presentation formula (design-of-record §1). The CLI ``--formula``
# flag (future Orchestration slice) overrides; the engine signature exposes
# ``formula`` so callers can pre-select today.
DEFAULT_FORMULA: str = "ochiai"

# Default top-N truncation (design-of-record §4).
DEFAULT_TOP_N: int = 10

# Per-symbol / per-file evidence-line cap. Limits the size of each entry's
# ``evidence_lines`` so a 200-line function does not dump 200 lines into the
# AI consumer's context. Top-K is by descending score within the symbol.
_EVIDENCE_LINE_CAP: int = 10

# Outcome bucket for "failed-like" — mirrors regression engine's
# _FAIL_LIKE but local: the Localization decision is "did this test
# FAIL?" with no need for the 3-bucket pass/fail/skip distinction.
_FAILED_OUTCOMES: frozenset[str] = frozenset({"failed", "errored"})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def derive_localization_findings(
    store: ProjectStore,
    run_reference: RunReference,
    *,
    top_n: int = DEFAULT_TOP_N,
    formula: str = DEFAULT_FORMULA,
) -> LocalizationFinding | LocalizationUnavailable:
    """Derive (or read cached) Localization Findings for ``run_reference``.

    Cache-aware: when a ``localization_findings.json`` already exists for
    this run, read and return it without re-deriving. Otherwise compute
    fresh and persist atomically. A future re-derivation (e.g. after a
    schema bump) bypasses the cache by deleting the cached file out of
    band — this slice does NOT auto-invalidate.

    ``top_n`` defaults to 10 (design-of-record §4). ``formula`` defaults
    to ``"ochiai"`` and selects which formula's score drives ``rank``;
    all four formulas are always computed and persisted under
    ``LocalizationEntry.alternate_scores``.
    """
    # 1. Resolve the run; surface RunEvidenceNotFoundError as Unavailable.
    try:
        entry = retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError as exc:
        return LocalizationUnavailable(
            run_reference=run_reference,
            reason=REASON_NO_RUN_EVIDENCE,
            detail=str(exc),
        )

    record = entry.run_record

    # 2. Tombstoned input → strict unavailable (strategy doc §5).
    if entry.tombstoned_at is not None:
        return LocalizationUnavailable(
            run_reference=record.run_reference,
            reason=REASON_RUN_NOT_ANALYZABLE,
            detail="run is tombstoned",
        )

    # Cache lookup BEFORE expensive coverage / spectra work. A cached
    # finding from a prior call is the cheapest path; only after a cache
    # miss do we re-run the full pipeline.
    cached_raw = read_localization_findings_raw(
        store, record.run_reference.run_id
    )
    if cached_raw is not None:
        return LocalizationFinding.from_dict(cached_raw)

    # 3. Failed tests present?
    failed_test_ids = frozenset(
        tr.node_id for tr in record.test_results if tr.outcome in _FAILED_OUTCOMES
    )
    if not failed_test_ids:
        return LocalizationUnavailable(
            run_reference=record.run_reference,
            reason=REASON_NO_FAILED_TESTS,
            detail="run has no failed test results",
        )

    # 4. Coverage Facts present?
    coverage = get_coverage_facts(store, record.run_reference)
    if isinstance(coverage, CoverageUnavailable):
        return LocalizationUnavailable(
            run_reference=record.run_reference,
            reason=REASON_NO_COVERAGE,
            detail=(
                "coverage facts unavailable; failure_proximity mode is not "
                "yet implemented (Phase 4 follow-up)"
            ),
        )

    # 5. Per-test granularity required for this slice.
    if coverage.mapping_granularity != "per-test":
        return LocalizationUnavailable(
            run_reference=record.run_reference,
            reason=REASON_NO_COVERAGE,
            detail=(
                f"coverage mapping_granularity={coverage.mapping_granularity!r} "
                "is not per-test; sbfl_aggregate mode is not yet implemented "
                "(Phase 4 follow-up)"
            ),
        )

    # 6-11. Build spectra, compute scores, rank, persist.
    finding = _derive_per_test(
        store=store,
        record=record,
        coverage=coverage,
        failed_test_ids=failed_test_ids,
        top_n=top_n,
        formula=formula,
    )
    write_localization_findings(store, finding)
    return finding


# ---------------------------------------------------------------------------
# Per-test pipeline (steps 6-11)
# ---------------------------------------------------------------------------


def _derive_per_test(
    *,
    store: ProjectStore,
    record: RunRecord,
    coverage: CoverageFactSet,
    failed_test_ids: frozenset[str],
    top_n: int,
    formula: str,
) -> LocalizationFinding:
    """Build the per-test SBFL finding. Caller has validated all preconditions."""
    spectra = build_spectra(coverage, failed_test_ids)
    counts = _count_vectors(spectra)
    scores = _compute_all_formula_scores(counts)

    # Aggregate line-level scores up to symbols (or file-level fallback).
    # Each entry candidate is a CodeLocation + per-formula score map.
    candidates = _aggregate_by_symbol(
        store=store,
        spectra=spectra,
        scores=scores,
    )

    # Sort by the selected formula's score descending; stable tie order is
    # by (file, primary_line) ascending so two runs with the same inputs
    # produce identical ranking.
    candidates.sort(
        key=lambda c: (
            -c.scores[formula],
            c.code_location.file,
            c.code_location.primary_line,
        )
    )

    # Min-max normalize within the FULL candidate set BEFORE truncation
    # (design-of-record §4 — "normalize the whole ranking so the
    # truncation does not concentrate the [0,1] range to a sub-window").
    raw_scores_full = [c.scores[formula] for c in candidates]
    normalized_full = _min_max_normalize(raw_scores_full)

    # Dense 1-based ranks computed against the FULL ranking too — so a
    # tie that straddles the truncation boundary still has a coherent
    # rank value when one half is dropped.
    dense_ranks = _dense_ranks([c.scores[formula] for c in candidates])

    # Truncate to top_n.
    truncated = candidates[:top_n]
    truncated_norm = normalized_full[:top_n]
    truncated_ranks = dense_ranks[:top_n]

    # ``tied_with`` resolution: for each entry in the truncated set,
    # collect the indices of OTHER truncated entries sharing the same
    # rank.
    by_rank: dict[int, list[int]] = defaultdict(list)
    for idx, rank in enumerate(truncated_ranks):
        by_rank[rank].append(idx)

    entries: list[LocalizationEntry] = []
    for idx, (candidate, norm_score, rank) in enumerate(
        zip(truncated, truncated_norm, truncated_ranks, strict=True)
    ):
        peers = [
            f"entry_index_{p}"
            for p in by_rank[rank]
            if p != idx
        ]
        entries.append(
            LocalizationEntry(
                rank=rank,
                tied_with=tuple(peers),
                code_location=candidate.code_location,
                score_raw=candidate.scores[formula],
                score_normalized=norm_score,
                formula=formula,
                alternate_scores={
                    name: candidate.scores[name]
                    for name in ("ochiai", "op2", "dstar2", "tarantula")
                    if name != formula
                },
                related_failed_tests=candidate.related_failed_tests,
                evidence_citations=_build_evidence_citations(
                    run_reference=record.run_reference,
                    candidate=candidate,
                ),
            )
        )

    alternate_available = tuple(
        sorted(name for name in ("ochiai", "op2", "dstar2", "tarantula") if name != formula)
    )

    # ``confidence: high`` because the per-test path is the strong SBFL
    # story (strategy doc §2 table). Aggregate / proximity modes will
    # carry ``"medium"`` / ``"low"`` respectively when those slices land.
    return LocalizationFinding(
        run_reference=record.run_reference,
        engine_name=record.engine_name,
        ecosystem=record.ecosystem,
        mode="sbfl_per_test",
        confidence="high",
        formula=formula,
        alternate_scores_available=alternate_available,
        top_n=top_n,
        entries=tuple(entries),
        derived_at=int(time.time() * 1000),
    )


# ---------------------------------------------------------------------------
# Spectra counts → per-location formula scores
# ---------------------------------------------------------------------------


def _count_vectors(
    spectra: Spectra,
) -> tuple[
    NDArray[np.int64], NDArray[np.int64], NDArray[np.int64], NDArray[np.int64]
]:
    """Compute ``(ef, ep, nf, np_)`` count vectors over the spectra.

    Definitions per location:
    - ``ef`` = number of failing tests that executed the location.
    - ``ep`` = number of passing tests that executed the location.
    - ``nf`` = number of failing tests that did NOT execute the location.
    - ``np_`` = number of passing tests that did NOT execute the location.

    ``matrix.astype(np.int64)`` is needed because uint8 sums saturate at
    255 with overflow semantics on large suites; int64 stays exact.
    """
    matrix = spectra.matrix.astype(np.int64)
    outcomes = spectra.test_outcomes.astype(np.int64)

    failed_mask = outcomes == 1
    passed_mask = outcomes == 0

    total_failed = int(failed_mask.sum())
    total_passed = int(passed_mask.sum())

    # Per-location column sums restricted to failed / passed rows.
    ef = matrix[failed_mask].sum(axis=0).astype(np.int64)
    ep = matrix[passed_mask].sum(axis=0).astype(np.int64)
    nf = total_failed - ef
    np_ = total_passed - ep
    return ef, ep, nf, np_


def _compute_all_formula_scores(
    counts: tuple[
        NDArray[np.int64], NDArray[np.int64], NDArray[np.int64], NDArray[np.int64]
    ],
) -> dict[str, NDArray[np.float64]]:
    """Apply all four formulas to the count vectors; return per-location scores."""
    ef, ep, nf, np_ = counts
    return {
        "ochiai": ochiai(ef, ep, nf, np_),
        "op2": op2(ef, ep, nf, np_),
        "dstar2": dstar2(ef, ep, nf, np_),
        "tarantula": tarantula(ef, ep, nf, np_),
    }


# ---------------------------------------------------------------------------
# Symbol aggregation
# ---------------------------------------------------------------------------


class _Candidate:
    """In-flight ranking candidate before normalization / dense-rank assignment.

    Plain class (not ``dataclass(frozen=True)``) because we sort a list of
    these by mutable score keys — a frozen dataclass adds no value and
    costs an extra ``replace`` per sort step.
    """

    __slots__ = (
        "code_location",
        "scores",
        "related_failed_tests",
        "evidence_lines_with_score",
    )

    def __init__(
        self,
        *,
        code_location: CodeLocation,
        scores: dict[str, float],
        related_failed_tests: tuple[str, ...],
        evidence_lines_with_score: tuple[tuple[int, float], ...],
    ) -> None:
        self.code_location = code_location
        self.scores = scores
        self.related_failed_tests = related_failed_tests
        # The lines + their scores, sorted by score desc then line asc.
        # Used by ``_build_evidence_citations`` to populate the
        # ``coverage_fact`` selector's ``lines`` field.
        self.evidence_lines_with_score = evidence_lines_with_score


def _aggregate_by_symbol(
    *,
    store: ProjectStore,
    spectra: Spectra,
    scores: dict[str, NDArray[np.float64]],
) -> list[_Candidate]:
    """Roll line-level scores up to symbols (or file-level fallback).

    For each ``(file, line)`` location: ask the Python resolver for the
    enclosing symbol. Group locations by ``(file, symbol_or_None)`` and
    take the **max** score per formula across the group (design-of-record
    §3 — "Do NOT use mean — mean dilutes by symbol size").

    Locations whose resolver returns ``(None, None)`` (module-level code,
    non-Python files, parse errors) are grouped into a single
    ``CodeLocation(kind="file")`` per file — file-level fallback per
    strategy doc §3.

    The ``primary_line`` for each group is the line with the maximum
    score on the SELECTED formula's ranking (computed elsewhere); here
    we record the per-line score map for downstream evidence-line
    selection.
    """
    # Group line-indices by ``(file, qualname_or_None, line_range_or_None)``.
    # Keying by line_range ensures two distinct same-named methods on
    # nested classes don't collide — though we only resolve one symbol
    # per file's lines so this is defensive.
    groups: dict[
        tuple[str, str | None, tuple[int, int] | None], list[int]
    ] = defaultdict(list)

    for j, (file_path, line) in enumerate(spectra.locations):
        absolute = _resolve_repo_path(store, file_path)
        qualname, line_range = resolve_python_symbol(absolute, line)
        key = (file_path, qualname, line_range)
        groups[key].append(j)

    candidates: list[_Candidate] = []
    for (file_path, qualname, line_range), col_indices in groups.items():
        max_scores: dict[str, float] = {}
        for formula_name, score_vector in scores.items():
            max_scores[formula_name] = float(score_vector[col_indices].max())

        # Top-K evidence lines within the group by Ochiai score (the
        # default / canonical formula). Using the default formula for
        # evidence-line selection keeps the evidence stable across the
        # CLI ``--formula`` flag — switching the presentation formula
        # changes the rank ordering but not the evidence lines on each
        # entry.
        ochiai_per_line = [
            (int(spectra.locations[j][1]), float(scores["ochiai"][j]))
            for j in col_indices
        ]
        ochiai_per_line.sort(key=lambda x: (-x[1], x[0]))
        truncated_lines = tuple(ochiai_per_line[:_EVIDENCE_LINE_CAP])

        # primary_line = the line with the maximum default-formula score;
        # tiebreak by line number ascending.
        primary_line = truncated_lines[0][0]
        evidence_lines = tuple(line for line, _score in truncated_lines)

        # Related failed tests = union of failed-test nodeids that hit
        # any of the lines inside this group.
        related = _related_failed_tests(spectra, col_indices)

        code_location = CodeLocation(
            kind="symbol" if qualname is not None else "file",
            file=file_path,
            symbol=qualname,
            line_range=line_range,
            primary_line=primary_line,
            evidence_lines=evidence_lines,
        )
        candidates.append(
            _Candidate(
                code_location=code_location,
                scores=max_scores,
                related_failed_tests=related,
                evidence_lines_with_score=truncated_lines,
            )
        )
    return candidates


def _resolve_repo_path(store: ProjectStore, file_path: str) -> Path:
    """Resolve a Project-Store-relative file path to an absolute path.

    ``CoverageFactSet.files[*].file_path`` is project-relative when the
    coverage.py adapter is configured with ``relative_files=True``. The
    project root sits one level up from ``store.path`` (the ``.novetest/``
    directory). For absolute paths we leave them untouched — defensive
    against future engine variants.
    """
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    project_root = store.path.parent
    return (project_root / candidate).resolve()


def _related_failed_tests(
    spectra: Spectra, col_indices: list[int]
) -> tuple[str, ...]:
    """Return the sorted-unique nodeids of failed tests touching any column."""
    failed_mask = spectra.test_outcomes == 1
    failed_row_indices = np.flatnonzero(failed_mask)
    matched_tests: set[str] = set()
    for i in failed_row_indices:
        # Any (i, j) with j in col_indices = the test touched some line
        # in this symbol.
        row = spectra.matrix[i, col_indices]
        if int(row.sum()) > 0:
            matched_tests.add(spectra.test_ids[i])
    return tuple(sorted(matched_tests))


# ---------------------------------------------------------------------------
# Normalization / ranking
# ---------------------------------------------------------------------------


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of scores into [0, 1].

    Returns all-zero when the input has zero spread (all scores equal) —
    that case has no ranking information to preserve; surfacing 0.0
    rather than 0/0 keeps the schema clean.
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

    "Dense" = ties share a rank, and the next distinct value skips to
    the next rank (no gap). So scores ``[0.9, 0.8, 0.8, 0.7]`` yield
    ``[1, 2, 2, 3]``.

    Caller must sort first. ``sorted_scores`` is assumed monotonically
    non-increasing.
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


# ---------------------------------------------------------------------------
# Evidence citations
# ---------------------------------------------------------------------------


def _build_evidence_citations(
    *,
    run_reference: RunReference,
    candidate: _Candidate,
) -> tuple[EvidenceCitation, ...]:
    """Build the per-entry EvidenceCitation tuple.

    Two citation kinds for the per-test path:
    - One ``test_result`` citation per related failed test (selector =
      ``{"test_id": <nodeid>, "outcome": "failed"}``).
    - One ``coverage_fact`` citation per file naming the evidence lines
      (selector = ``{"file": <path>, "lines": [<int>, ...]}``).

    The wire shape is a working draft per the task brief; PM freezes it
    after Manual Test fields it.
    """
    citations: list[EvidenceCitation] = []
    for nodeid in candidate.related_failed_tests:
        citations.append(
            EvidenceCitation(
                kind="test_result",
                run_reference=run_reference,
                selector={"test_id": nodeid, "outcome": "failed"},
            )
        )
    lines_for_citation = [
        line for line, _score in candidate.evidence_lines_with_score
    ]
    citations.append(
        EvidenceCitation(
            kind="coverage_fact",
            run_reference=run_reference,
            selector={
                "file": candidate.code_location.file,
                "lines": sorted(lines_for_citation),
            },
        )
    )
    return tuple(citations)


# ---------------------------------------------------------------------------
# Latest-run resolution (mirrors Regression's resolve_latest_baseline +
# derive_latest_regression composition pattern in compare.py)
# ---------------------------------------------------------------------------


def resolve_latest_analyzable_run(
    store: ProjectStore,
) -> RunReference | LocalizationUnavailable:
    """Return the most-recent ``RunReference`` for which Localization is derivable.

    "Analyzable" = ``check_localization_availability(store, ref)`` returns
    ``True`` — the cheap precondition probe in ``retrieval.py`` (per-test
    coverage path: not-tombstoned ∧ has-failed-tests ∧ has-coverage ∧
    ``mapping_granularity == "per-test"``).

    Walks ``list_run_history`` newest-first (Memory's guarantee) and
    returns the first matching ``RunReference``. The probe is cheap —
    each candidate costs one ``retrieve_run_evidence`` + a coverage
    cache stat — so a linear scan is acceptable at v1. If a future
    profiling slice shows hot-loop cost, an indexed `find_*` helper on
    the Memory side is the obvious next step (mirrors Regression's
    ``find_runs_for_target`` precedent).

    Returns ``LocalizationUnavailable`` (with ``run_reference=None``)
    when no analyzable run exists:

    - Empty store → ``REASON_NO_RUN_EVIDENCE`` with
      ``detail="no runs in store"``.
    - Store has runs but none are analyzable →
      ``REASON_RUN_NOT_ANALYZABLE`` with
      ``detail="no analyzable runs in store (N candidates checked)"``
      where ``N`` is the count actually probed (so operators can
      distinguish "0 runs total" from "10 runs, none qualify").

    Pure read; never invokes ``derive_localization_findings`` and never
    writes to disk.
    """
    history = list_run_history(store)
    if not history:
        return LocalizationUnavailable(
            run_reference=None,
            reason=REASON_NO_RUN_EVIDENCE,
            detail="no runs in store",
        )
    probed = 0
    for entry in history:
        probed += 1
        run_reference = entry.run_record.run_reference
        if check_localization_availability(store, run_reference):
            return run_reference
    return LocalizationUnavailable(
        run_reference=None,
        reason=REASON_RUN_NOT_ANALYZABLE,
        detail=f"no analyzable runs in store ({probed} candidates checked)",
    )


def derive_latest_localization(
    store: ProjectStore,
    *,
    formula: str = DEFAULT_FORMULA,
    top_n: int = DEFAULT_TOP_N,
) -> LocalizationFinding | LocalizationUnavailable:
    """Compose ``resolve_latest_analyzable_run`` + ``derive_localization_findings``.

    Pure composition — no additional logic beyond plumbing. If
    ``resolve_latest_analyzable_run`` returns ``LocalizationUnavailable``,
    that result is propagated as-is (the caller sees the same reason /
    detail). Otherwise the resolved ``RunReference`` is handed straight
    to ``derive_localization_findings`` along with the caller's
    ``formula`` / ``top_n`` selectors.

    Defaults match ``derive_localization_findings`` exactly so the two
    are interchangeable from a kwargs surface POV (``formula="ochiai"``,
    ``top_n=10``).
    """
    resolved = resolve_latest_analyzable_run(store)
    if isinstance(resolved, LocalizationUnavailable):
        return resolved
    return derive_localization_findings(
        store, resolved, top_n=top_n, formula=formula
    )


__all__: list[str] = [
    "DEFAULT_FORMULA",
    "DEFAULT_TOP_N",
    "derive_latest_localization",
    "derive_localization_findings",
    "resolve_latest_analyzable_run",
]
