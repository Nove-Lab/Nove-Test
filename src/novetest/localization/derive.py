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
from novetest.localization.failure_proximity import (
    derive_failure_proximity,
    parse_failure_log,
    resolve_failure_text,
)
from novetest.localization.persistence import (
    read_localization_findings_raw,
    write_localization_findings,
)
from novetest.localization.results import (
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
    find_runs_for_target,
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
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.regression.results import RegressionUnavailable
from novetest.regression.retrieval import get_regression_facts


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

    # 4. Coverage Facts present? Mode selection per strategy doc §2:
    #    - Path A (per-test coverage)       → ``sbfl_per_test``
    #    - Path B (aggregate / per-test-*)  → ``sbfl_aggregate`` (FLUCCS-reweighted
    #      when Regression Facts exist; failure-only Ochiai floor otherwise)
    #    - Path C (no coverage at all)      → ``failure_proximity``
    coverage = get_coverage_facts(store, record.run_reference)
    regression_facts = try_get_latest_regression_facts(store, record)

    finding: LocalizationFinding
    if isinstance(coverage, CoverageUnavailable):
        # Path C: failure_proximity (no coverage at all).
        finding = derive_failure_proximity(
            store=store,
            record=record,
            failed_test_ids=failed_test_ids,
            regression_facts=regression_facts,
            top_n=top_n,
        )
    elif coverage.mapping_granularity == "per-test":
        # Path A: existing sbfl_per_test (unchanged).
        finding = _derive_per_test(
            store=store,
            record=record,
            coverage=coverage,
            failed_test_ids=failed_test_ids,
            top_n=top_n,
            formula=formula,
        )
    else:
        # Path B: sbfl_aggregate — covers ``aggregate``, ``per-test-file``,
        # ``per-test-class`` (the latter two degrade to file-level here
        # at v1; symbol-level upgrade is post-MVP per strategy doc §3).
        finding = _derive_aggregate(
            store=store,
            record=record,
            coverage=coverage,
            failed_test_ids=failed_test_ids,
            regression_facts=regression_facts,
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
# Aggregate pipeline — Path B (strategy doc §2 + FLUCCS-style reweighting)
# ---------------------------------------------------------------------------


# FLUCCS-style regression-reweighting boost factor (Sohn & Yoo, ISSTA 2017).
# Multiplicative: ``score *= (1 + ALPHA)`` for files in the regression
# change set. ``0.5`` is the published tuned value in the FLUCCS paper.
_REGRESSION_BOOST_ALPHA: float = 0.5


def _derive_aggregate(
    *,
    store: ProjectStore,
    record: RunRecord,
    coverage: CoverageFactSet,
    failed_test_ids: frozenset[str],
    regression_facts: RegressionFactSet | None,
    top_n: int,
    formula: str,
) -> LocalizationFinding:
    """Build the file-level ``sbfl_aggregate`` finding.

    Algorithm (strategy doc §2 + task brief §"Scope §1"):

    1. For each failing test, parse its failure_reference into the set
       of files mentioned by the failure trace. This is the "did this
       failing test touch this file" approximation since per-test
       attribution is unavailable.
    2. Build per-file counts:
       - ``ef`` = number of failing tests whose trace mentions the file.
       - ``ep`` = total passing tests if file appears in aggregate coverage
                  (i.e. ANY test executed code in this file), else 0.
                  This is the brief's "passing component approximated from
                  aggregate minus failing" — degenerated to "passing tests
                  hit every covered file" because per-test mapping is
                  absent. The approximation is conservative: it
                  overestimates ``ep`` for files not touched by passing
                  tests, depressing their Ochiai score and reducing
                  false-positive ranks.
       - ``nf = total_failing - ef``
       - ``np = total_passing - ep``
    3. Apply all four SBFL formulas via the existing
       ``_compute_all_formula_scores`` helper — formulas are mode-
       agnostic vector ops over count tuples.
    4. If a non-empty regression "changed_files" set is available, apply
       FLUCCS-style reweighting: ``score *= (1 + 0.5)`` for files in the
       set. Applied to ALL four formulas so alternate_scores stay
       consistent with the primary formula's reweighting.
    5. Sort candidates by the selected formula desc, tie-break by file
       path ascending. Filter out non-positive-score candidates for the
       selected formula (the file is unsuspicious and shouldn't pad the
       top_n list with noise). Min-max normalize within the surviving
       candidate set; dense-rank with ties; truncate to ``top_n``.

    File-level granularity is the v1 fallback per strategy doc §3 (no
    symbol resolver for non-Python languages yet). The brief authorizes
    this fallback explicitly under §"File-level granularity is
    acceptable for v1".

    Confidence is ``"medium"`` per strategy doc §2 table for both the
    regression-reweighted sub-variant and the failure-only Ochiai floor;
    callers see ``metadata["regression_reweighted"]`` to disambiguate.
    """
    # Step 1: per-failing-test failure-log parses.
    file_to_failed_tests: dict[str, set[str]] = defaultdict(set)
    file_to_evidence_lines: dict[str, set[int]] = defaultdict(set)
    parse_warnings: list[str] = []

    for tr in record.test_results:
        if tr.outcome not in _FAILED_OUTCOMES:
            continue
        if tr.node_id not in failed_test_ids:
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
            file_to_failed_tests[file_path].add(tr.node_id)
            file_to_evidence_lines[file_path].add(line)

    # Step 2: per-file count vectors over the COVERED file set.
    #
    # Defect 3 fix (2026-05-31): restrict candidates to files in the
    # project's coverage scope. Failure-trace paths that aren't in
    # ``coverage.files`` (e.g. Rust stdlib frames like
    # ``/rustc/<hash>/library/core/src/panicking.rs:N:M`` that the
    # parser may extract from cargo nextest's default stack backtrace)
    # are dropped here. The parser-side regex was tightened in parallel
    # (catch-all dropped in ``failure_proximity._CARGO_REGEXES``) — this
    # algorithm-side filter is the defense-in-depth layer.
    #
    # Trade-off: a workspace file mentioned in a failure trace but NOT
    # in any test's coverage would also be dropped here. Per the Defect 3
    # analysis, this is bounded — files with zero coverage typically
    # don't appear in failing-test panic traces anyway (they weren't
    # executed by any test). The practical loss is small; the noise
    # rejection is large.
    #
    # Source: questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
    covered_files = {f.file_path for f in coverage.files}
    all_files = sorted(covered_files)

    total_failing = len(failed_test_ids)
    total_passing = sum(
        1 for tr in record.test_results if tr.outcome == "passed"
    )

    n = len(all_files)
    ef_array = np.zeros(n, dtype=np.int64)
    ep_array = np.zeros(n, dtype=np.int64)
    for j, file_path in enumerate(all_files):
        ef_array[j] = len(file_to_failed_tests.get(file_path, set()))
        # Brief approximation: ep ≈ total_passing if file is in aggregate
        # coverage, else 0. Without per-test attribution we cannot do
        # better than this binary "is this file ever-covered" gate.
        ep_array[j] = total_passing if file_path in covered_files else 0
    nf_array = total_failing - ef_array
    np_array = total_passing - ep_array

    # Step 3: apply all four formulas via the canonical helper. Re-uses
    # the same numpy implementations as per-test mode — formulas are
    # mode-agnostic.
    scores = _compute_all_formula_scores((ef_array, ep_array, nf_array, np_array))

    # Step 4: FLUCCS-style regression reweighting (Sohn & Yoo 2017).
    changed_files = _changed_files_from_regression(regression_facts)
    regression_reweighted = bool(changed_files) and any(
        f in changed_files for f in all_files
    )
    if regression_reweighted:
        boost_mask = np.array(
            [1 + _REGRESSION_BOOST_ALPHA if f in changed_files else 1.0 for f in all_files],
            dtype=np.float64,
        )
        for formula_name in ("ochiai", "op2", "dstar2", "tarantula"):
            scores[formula_name] = scores[formula_name] * boost_mask

    # Step 5: sort, filter unsuspicious entries, normalize, rank, truncate.
    candidates: list[tuple[str, dict[str, float], frozenset[str], tuple[int, ...]]] = []
    for j, file_path in enumerate(all_files):
        per_formula = {
            name: float(scores[name][j])
            for name in ("ochiai", "op2", "dstar2", "tarantula")
        }
        evidence_lines = tuple(
            sorted(file_to_evidence_lines.get(file_path, set()))
        )[:_EVIDENCE_LINE_CAP]
        candidates.append(
            (
                file_path,
                per_formula,
                frozenset(file_to_failed_tests.get(file_path, set())),
                evidence_lines,
            )
        )

    candidates.sort(key=lambda c: (-c[1][formula], c[0]))

    # Drop non-positive-score candidates for the SELECTED formula —
    # padding top_n with zero-Ochiai files defeats the point of the
    # ranking. We keep candidates with score > 0 to preserve the
    # "informative" signal. The per-test path doesn't filter because its
    # candidates list is small by construction (one entry per covered
    # symbol); aggregate mode's candidates list spans every covered file
    # so unfiltered noise dominates.
    candidates = [c for c in candidates if c[1][formula] > 0]

    raw_scores_full = [c[1][formula] for c in candidates]
    normalized_full = _min_max_normalize(raw_scores_full)
    dense_ranks_full = _dense_ranks(raw_scores_full)

    truncated = candidates[:top_n]
    truncated_norm = normalized_full[:top_n]
    truncated_ranks = dense_ranks_full[:top_n]

    by_rank: dict[int, list[int]] = defaultdict(list)
    for idx, rank in enumerate(truncated_ranks):
        by_rank[rank].append(idx)

    entries: list[LocalizationEntry] = []
    for idx, ((file_path, per_formula, related, evidence_lines), norm_score, rank) in enumerate(
        zip(truncated, truncated_norm, truncated_ranks, strict=True)
    ):
        peers = tuple(
            f"entry_index_{p}" for p in by_rank[rank] if p != idx
        )
        primary_line = evidence_lines[0] if evidence_lines else 0
        related_sorted = tuple(sorted(related))

        citations: list[EvidenceCitation] = []
        for nodeid in related_sorted:
            citations.append(
                EvidenceCitation(
                    kind="test_result",
                    run_reference=record.run_reference,
                    selector={"test_id": nodeid, "outcome": "failed"},
                )
            )
        citations.append(
            EvidenceCitation(
                kind="coverage_fact",
                run_reference=record.run_reference,
                selector={
                    "file": file_path,
                    "lines": list(evidence_lines),
                },
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
                    evidence_lines=evidence_lines,
                ),
                score_raw=per_formula[formula],
                score_normalized=norm_score,
                formula=formula,
                alternate_scores={
                    name: per_formula[name]
                    for name in ("ochiai", "op2", "dstar2", "tarantula")
                    if name != formula
                },
                related_failed_tests=related_sorted,
                evidence_citations=tuple(citations),
            )
        )

    alternate_available = tuple(
        sorted(
            name
            for name in ("ochiai", "op2", "dstar2", "tarantula")
            if name != formula
        )
    )

    metadata: dict[str, object] = {
        "regression_reweighted": regression_reweighted,
        "changed_files_count": len(changed_files),
    }
    if parse_warnings:
        metadata["parse_warnings"] = parse_warnings

    return LocalizationFinding(
        run_reference=record.run_reference,
        engine_name=record.engine_name,
        ecosystem=record.ecosystem,
        mode="sbfl_aggregate",
        confidence="medium",
        formula=formula,
        alternate_scores_available=alternate_available,
        top_n=top_n,
        entries=tuple(entries),
        derived_at=int(time.time() * 1000),
        metadata=metadata,
    )


def _changed_files_from_regression(
    regression_facts: RegressionFactSet | None,
) -> frozenset[str]:
    """Extract the FLUCCS-style "changed files" set from a RegressionFactSet.

    Mirrors ``failure_proximity._changed_files_from_regression`` — both
    modes consume the same regression prior. Duplicated here rather than
    cross-imported so each mode module owns its own helper and there is
    no circular-import temptation (failure_proximity is imported by
    derive.py; derive importing failure_proximity for the helper would
    be one-way and fine, but the duplication is trivially small and
    keeps the two modes self-contained for unit-test reasoning).
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


# ---------------------------------------------------------------------------
# Regression-facts probe — best-effort, never raises, never derives
# ---------------------------------------------------------------------------


def try_get_latest_regression_facts(
    store: ProjectStore,
    record: RunRecord,
) -> RegressionFactSet | None:
    """Best-effort lookup of cached Regression Facts for ``record``.

    Returns the ``RegressionFactSet`` whose ``target_run_reference``
    matches this record AND whose ``baseline_run_reference`` is the
    most-recent comparable prior run (same ``target_expression``).
    Returns ``None`` when:

    - No prior comparable run exists in the store (typical first run).
    - The prior pair has no cached ``regression_facts.json`` (Regression
      hasn't been derived yet for the pair).
    - Any lookup operation raises — Localization should never abort due
      to a Regression layer's failure mode.

    **Pure read** — never invokes ``derive_regression_facts``. Mode
    selection in ``derive_localization_findings`` treats the absence of
    Regression Facts as normal: the FLUCCS reweighting is skipped and
    the floor (failure-only Ochiai) is used instead, both at
    ``confidence: "medium"``.

    Sibling resolution follows Regression's ``resolve_latest_baseline``
    pattern: ``find_runs_for_target`` returns newest-first, and we pick
    the most recent entry STRICTLY older than ``record``. This matches
    the Regression engine's pair semantics so any cached
    ``regression_facts.json`` was derived from the same baseline pair we
    just resolved.
    """
    try:
        siblings = find_runs_for_target(
            store, record.target_expression, include_tombstoned=False
        )
    except Exception:  # noqa: BLE001 - best-effort: never abort the caller.
        return None

    target_run_id = record.run_reference.run_id
    target_created = record.run_reference.created_at
    # ``find_runs_for_target`` is newest-first; iterate in that order
    # and pick the first STRICTLY older non-self sibling.
    baseline_ref: RunReference | None = None
    for sibling in siblings:
        sibling_ref = sibling.run_record.run_reference
        if sibling_ref.run_id == target_run_id:
            continue
        if sibling_ref.created_at >= target_created:
            continue
        baseline_ref = sibling_ref
        break
    if baseline_ref is None:
        return None

    try:
        result = get_regression_facts(store, baseline_ref, record.run_reference)
    except Exception:  # noqa: BLE001 - same posture as above.
        return None
    if isinstance(result, RegressionUnavailable):
        return None
    return result


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
    "try_get_latest_regression_facts",
]
