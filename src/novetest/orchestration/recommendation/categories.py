"""Closed taxonomy v1 — 7 recommendation categories + trigger predicates.

Frozen by the Phase 6 entry brief §1. Bumping
``recommendation_schema_version`` past 1 is the only way to change the
slot keys per category post-Phase-6.

Module surface
--------------

- ``CATEGORY_*`` string constants (one per category).
- ``CATEGORIES_BY_PRIORITY`` — the ordered list (highest → lowest).
- ``CategoryHit`` — the synthesizer's intermediate per-trigger record.
- ``match_*`` functions — one per category; each takes a ``FactBundle`` and
  yields zero or more ``CategoryHit`` values.
- ``MATCHERS_BY_PRIORITY`` — ordered list of ``(priority, name, matcher)``.
- ``compound_resolution`` — drops constituents of ``regression_with_localization``.
- ``apply_mutual_exclusion`` — drops ``all_green`` whenever any other
  category fired, and drops every non-``unavailable_analysis`` hit when
  literally zero facts were available AND tests failed (brief §1
  "Mutual exclusion rules").

Determinism contract: every matcher iterates over deterministically-ordered
inputs and emits hits in deterministic order. Tied lookups are broken
lexicographically. Same ``FactBundle`` → same hit set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Final, Iterable

from novetest.models.regression_fact_set import TestTransition

from novetest.orchestration.recommendation.fact_bundle import (
    FactBundle,
    executed_as_suite,
    has_failed_tests,
    passed_count,
    run_is_clean,
    skipped_count,
    total_count,
)


# ---------------------------------------------------------------------------
# Category identifiers (closed taxonomy v1)
# ---------------------------------------------------------------------------


CATEGORY_REGRESSION_WITH_LOCALIZATION: Final[str] = "regression_with_localization"
CATEGORY_INVESTIGATE_LOCATION: Final[str] = "investigate_location"
CATEGORY_INVESTIGATE_REGRESSION: Final[str] = "investigate_regression"
CATEGORY_COVERAGE_GAP: Final[str] = "coverage_gap"
CATEGORY_FLAKY_SUSPECTED: Final[str] = "flaky_suspected"
CATEGORY_UNAVAILABLE_ANALYSIS: Final[str] = "unavailable_analysis"
CATEGORY_ALL_GREEN: Final[str] = "all_green"


# Closed enum used for envelope validation + ``categories`` priority lookups.
CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        CATEGORY_REGRESSION_WITH_LOCALIZATION,
        CATEGORY_INVESTIGATE_LOCATION,
        CATEGORY_INVESTIGATE_REGRESSION,
        CATEGORY_COVERAGE_GAP,
        CATEGORY_FLAKY_SUSPECTED,
        CATEGORY_UNAVAILABLE_ANALYSIS,
        CATEGORY_ALL_GREEN,
    }
)


# Priority numbers (lower = higher priority). Brief §1.
PRIORITIES: Final[dict[str, int]] = {
    CATEGORY_REGRESSION_WITH_LOCALIZATION: 1,
    CATEGORY_INVESTIGATE_LOCATION: 2,
    CATEGORY_INVESTIGATE_REGRESSION: 3,
    CATEGORY_COVERAGE_GAP: 4,
    CATEGORY_FLAKY_SUSPECTED: 5,
    CATEGORY_UNAVAILABLE_ANALYSIS: 6,
    CATEGORY_ALL_GREEN: 7,
}


# Investigation surfaces (categories that "owe the user an explanation"
# when an investigation could not be performed). Used by the mutual
# exclusion rule for ``all_green``.
INVESTIGATION_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        CATEGORY_REGRESSION_WITH_LOCALIZATION,
        CATEGORY_INVESTIGATE_LOCATION,
        CATEGORY_INVESTIGATE_REGRESSION,
        CATEGORY_COVERAGE_GAP,
        CATEGORY_FLAKY_SUSPECTED,
    }
)


# Localization-finding minimum bar for ``investigate_location`` trigger
# (brief §1): ``confidence in {high, medium}`` AND ``rank <= 3``.
INVESTIGATE_LOCATION_MAX_RANK: Final[int] = 3
INVESTIGATE_LOCATION_CONFIDENCES: Final[frozenset[str]] = frozenset({"high", "medium"})


# ---------------------------------------------------------------------------
# CategoryHit — the synthesizer's intermediate record.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CategoryHit:
    """One match emitted by a trigger predicate.

    ``primary_slot`` is the category-specific stable sort key (brief §1 —
    "Stable ordering rule"). Compound resolution + mutual exclusion read
    ``payload`` to learn what the hit referenced (e.g. the file/symbol
    for an ``investigate_location`` hit, the test_id for an
    ``investigate_regression`` hit) so they can detect overlap without
    re-running the matchers.

    ``payload`` is a flat ``dict[str, Any]`` keyed by the brief §1 slot
    keys — building the final ``Recommendation.slots`` is then a verbatim
    copy of this dict (see ``templates.py``).
    """

    category: str
    priority: int
    primary_slot: str
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trigger predicates — one per category.
# ---------------------------------------------------------------------------


def match_investigate_location(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger on Localization entries with confidence ≥ medium and rank ≤ 3.

    Brief §1 (priority 2). One hit per qualifying entry. Compound
    resolution may drop these later when ``regression_with_localization``
    swallows their constituents.

    ``score_normalized`` is taken from the entry directly. ``formula`` is
    the entry's primary formula (the engine's per-entry selection — for
    failure_proximity this is the ``"ochiai"`` placeholder per the
    Phase-4 mode-narrative convention, but the AI consumer reads
    ``mode`` for the discrimination signal).
    """

    finding = bundle.localization_findings
    if finding is None:
        return []
    if finding.confidence not in INVESTIGATE_LOCATION_CONFIDENCES:
        return []
    hits: list[CategoryHit] = []
    # Iterate in rank order (engine emits entries already sorted by rank;
    # filter by rank cap so a future engine change that emits more entries
    # cannot regress the closed taxonomy).
    for entry in finding.entries:
        if entry.rank > INVESTIGATE_LOCATION_MAX_RANK:
            continue
        loc = entry.code_location
        line_range = (
            [loc.line_range[0], loc.line_range[1]]
            if loc.line_range is not None
            else None
        )
        primary_slot = _primary_slot_for_location(
            file=loc.file,
            line_range=loc.line_range,
            primary_line=loc.primary_line,
        )
        payload: dict[str, Any] = {
            "symbol": loc.symbol,
            "file": loc.file,
            "primary_line": loc.primary_line,
            "line_range": line_range,
            "rank": entry.rank,
            "score_normalized": entry.score_normalized,
            "formula": entry.formula,
            "mode": finding.mode,
        }
        hits.append(
            CategoryHit(
                category=CATEGORY_INVESTIGATE_LOCATION,
                priority=PRIORITIES[CATEGORY_INVESTIGATE_LOCATION],
                primary_slot=primary_slot,
                payload=payload,
            )
        )
    return hits


def match_investigate_regression(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger on Regression Facts containing ``regressed`` transitions.

    Brief §1 (priority 3). One hit per ``regressed`` (i.e. newly-failing
    this run) test. Phase 6 v1 ships only ``regression_kind = "newly_failing"``;
    ``"now_passing"`` is explicitly a v2 addition and is NOT emitted by
    this matcher.
    """

    rf = bundle.regression_facts
    if rf is None:
        return []
    baseline_ref = rf.baseline_run_reference.run_id
    target_ref = rf.target_run_reference.run_id
    hits: list[CategoryHit] = []
    for transition in _sorted_transitions(rf.test_transitions):
        if transition.category != "regressed":
            continue
        hits.append(
            CategoryHit(
                category=CATEGORY_INVESTIGATE_REGRESSION,
                priority=PRIORITIES[CATEGORY_INVESTIGATE_REGRESSION],
                primary_slot=transition.node_id,
                payload={
                    "test_id": transition.node_id,
                    "regression_kind": "newly_failing",
                    "run_reference_from": baseline_ref,
                    "run_reference_to": target_ref,
                },
            )
        )
    return hits


def match_regression_with_localization(bundle: FactBundle) -> list[CategoryHit]:
    """Compound: Regression Fact ∩ Localization Finding via ``related_failed_tests``.

    Brief §1 (priority 1) + the §1 "Compound rule" clarification: a
    regression on test T overlaps with a localization entry implicating
    file F iff T appears in the entry's ``related_failed_tests``. Pure
    file colocation is NOT a compound — that produces two independent
    recommendations.

    Emits one hit per (test_id, finding entry) overlap pair, in
    ``(file, primary_line, test_id)`` lexicographic order.
    """

    rf = bundle.regression_facts
    finding = bundle.localization_findings
    if rf is None or finding is None:
        return []
    # Map: test_id → regressed transition (newly failing this run).
    regressed_by_test: dict[str, TestTransition] = {
        t.node_id: t for t in rf.test_transitions if t.category == "regressed"
    }
    if not regressed_by_test:
        return []
    baseline_ref = rf.baseline_run_reference.run_id
    target_ref = rf.target_run_reference.run_id
    hits: list[CategoryHit] = []
    for entry in finding.entries:
        # The brief §1 compound rule pivots on Localization, not on the
        # regression-rank threshold — so we honor every entry regardless
        # of rank or confidence, provided the overlap fires. Constituents
        # (the bare ``investigate_location`` for this same (file, line)
        # AND the bare ``investigate_regression`` for this same test_id)
        # are dropped later by ``compound_resolution``.
        loc = entry.code_location
        for test_id in entry.related_failed_tests:
            if test_id not in regressed_by_test:
                continue
            line_range = (
                [loc.line_range[0], loc.line_range[1]]
                if loc.line_range is not None
                else None
            )
            primary_slot = _primary_slot_for_compound(
                file=loc.file,
                line_range=loc.line_range,
                primary_line=loc.primary_line,
                test_id=test_id,
            )
            payload: dict[str, Any] = {
                "test_id": test_id,
                "regression_kind": "newly_failing",
                "symbol": loc.symbol,
                "file": loc.file,
                "primary_line": loc.primary_line,
                "line_range": line_range,
                "rank": entry.rank,
                "score_normalized": entry.score_normalized,
                "formula": entry.formula,
                "mode": finding.mode,
                "run_reference_from": baseline_ref,
                "run_reference_to": target_ref,
            }
            hits.append(
                CategoryHit(
                    category=CATEGORY_REGRESSION_WITH_LOCALIZATION,
                    priority=PRIORITIES[CATEGORY_REGRESSION_WITH_LOCALIZATION],
                    primary_slot=primary_slot,
                    payload=payload,
                )
            )
    return hits


def match_coverage_gap(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger on uncovered lines that fall inside a Localization Finding's file.

    Brief §1 (priority 4). Reads Coverage Facts and Localization
    Findings; for each suspect entry whose file matches a Coverage
    ``FileCoverage`` whose ``missing_lines`` overlaps the entry's
    ``line_range`` (or ``primary_line`` when no range exists), emits one
    hit listing the intersecting missing lines.

    ``related_finding_id`` is the deterministic ``"entry_index_<i>"``
    handle (the same shape Localization uses for its in-set tied_with
    references — brief §1 carries this through unchanged).
    """

    coverage = bundle.coverage_facts
    finding = bundle.localization_findings
    if coverage is None or finding is None:
        return []
    coverage_by_file: dict[str, tuple[int, ...]] = {
        fc.file_path: fc.missing_lines for fc in coverage.files
    }
    hits: list[CategoryHit] = []
    for idx, entry in enumerate(finding.entries):
        loc = entry.code_location
        missing = coverage_by_file.get(loc.file)
        if not missing:
            continue
        # Determine the entry's line span. For symbol-level entries this
        # is ``line_range``; for file-level entries (no range) we treat
        # the single ``primary_line`` as the span.
        if loc.line_range is not None:
            span_start, span_end = loc.line_range
        else:
            span_start = span_end = loc.primary_line
        overlapping = sorted(
            line for line in missing if span_start <= line <= span_end
        )
        if not overlapping:
            continue
        hits.append(
            CategoryHit(
                category=CATEGORY_COVERAGE_GAP,
                priority=PRIORITIES[CATEGORY_COVERAGE_GAP],
                primary_slot=f"{loc.file}:{overlapping[0]}",
                payload={
                    "file": loc.file,
                    "lines": list(overlapping),
                    "mode": finding.mode,
                    "related_finding_id": f"entry_index_{idx}",
                },
            )
        )
    return hits


def match_flaky_suspected(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger on Replay Results classified ``inconsistent``.

    Brief §1 (priority 5), reachable from ``novetest test --reruns N``
    since the 2026-06-25 integration cycle: the integrated workflow
    populates ``bundle.replay_results`` with the Replay Attempt outcome(s)
    for the run (today at most one whole-run attempt; the tuple shape is
    forward-compatible with per-test replay scoping). One hit per result
    classified ``inconsistent``, emitted in tuple order — the tuple is
    deterministic, so the hit list is too.
    """

    hits: list[CategoryHit] = []
    for rr in bundle.replay_results:
        if rr.classification != "inconsistent":
            continue
        test_id = rr.test_id or ""
        hits.append(
            CategoryHit(
                category=CATEGORY_FLAKY_SUSPECTED,
                priority=PRIORITIES[CATEGORY_FLAKY_SUSPECTED],
                primary_slot=test_id,
                payload={
                    "test_id": test_id,
                    "reruns_total": rr.reruns_total,
                    "reruns_failed": rr.reruns_failed,
                    "run_reference": rr.run_reference.run_id,
                },
            )
        )
    return hits


def match_unavailable_analysis(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger when a stage is unavailable AND we owe the user an explanation.

    Brief §1 (priority 6). At most one hit per run — there's only one
    "we owe the user an explanation" surface. The compound mutual
    exclusion rule (brief §1 — "literally zero facts available AND tests
    failed → emit ONLY ``unavailable_analysis``") fires later in
    ``apply_mutual_exclusion``.

    We owe an explanation in **two** shapes:

    1. Tests failed (the original trigger) — analysis was wanted and some
       stage could not deliver it.
    2. The suite never executed (``run_record.status`` outside
       ``EXECUTED_RUN_STATUSES``, e.g. a pytest collection error). Zero
       collected tests means zero failures *by construction*, so the
       ``has_failed_tests`` gate alone silently excused this run — and
       ``all_green``, gated on the same vacuous predicate, claimed it
       instead. Delivery-phasing row 45.
    """

    unavailable_stages = bundle.stage_eligibility.unavailable_stages()
    if not unavailable_stages:
        return []
    if not has_failed_tests(bundle) and executed_as_suite(bundle):
        return []
    reasons_map = bundle.stage_eligibility.per_stage_reasons
    reason_per_stage: dict[str, str | None] = {
        stage: reasons_map.get(stage) for stage in unavailable_stages
    }
    return [
        CategoryHit(
            category=CATEGORY_UNAVAILABLE_ANALYSIS,
            priority=PRIORITIES[CATEGORY_UNAVAILABLE_ANALYSIS],
            primary_slot="",
            payload={
                "unavailable_stages": unavailable_stages,
                "reason_per_stage": reason_per_stage,
                "run_reference": bundle.run_reference.run_id,
            },
        )
    ]


def match_all_green(bundle: FactBundle) -> list[CategoryHit]:
    """Trigger when the run passed cleanly, with no regression and no flake.

    Brief §1 (priority 7). The mutual exclusion rule drops this hit
    later if any other (non-``all_green``) category fired. So the
    matcher's job is just: is the run "clean enough" to be a candidate?
    The candidate test is intentionally conservative — ``has_failed_tests``
    + the regression-summary check — rather than re-running every other
    matcher and observing zero output. The mutual exclusion step is the
    final arbiter; redundant signals are fine here.

    The FIRST gate is the run's own status, and it is an allow-list
    (``run_is_clean`` → ``status == "passed"``). Without it the matcher
    was vacuously satisfied by any run with zero collected tests: a
    pytest suite that fails to COLLECT persists ``status: "errored"`` with
    zero ``test_results``, so ``has_failed_tests`` is False "because
    nothing failed" when the truth is "because nothing ran", and the
    product told the agent "All tests green" about a suite that did not
    parse (delivery-phasing row 45). Reading the status here is what makes
    the two cases distinguishable; the counting predicates cannot tell
    them apart even in principle.
    """

    if not run_is_clean(bundle):
        return []
    if has_failed_tests(bundle):
        return []
    rf = bundle.regression_facts
    if rf is not None and rf.summary.regressed > 0:
        return []
    # ``flaky_suspected`` candidate? Any inconsistent Replay Result on the
    # bundle disqualifies ``all_green`` (mirrors the matcher's trigger).
    if any(rr.classification == "inconsistent" for rr in bundle.replay_results):
        return []
    return [
        CategoryHit(
            category=CATEGORY_ALL_GREEN,
            priority=PRIORITIES[CATEGORY_ALL_GREEN],
            primary_slot="",
            payload={
                "run_reference": bundle.run_reference.run_id,
                "total_tests": total_count(bundle),
                "passed": passed_count(bundle),
                "skipped": skipped_count(bundle),
            },
        )
    ]


# ---------------------------------------------------------------------------
# Priority-ordered registry
# ---------------------------------------------------------------------------


Matcher = Callable[[FactBundle], list[CategoryHit]]


# Tuple shape: (priority, category_name, matcher_fn). Ordered by priority
# asc to mirror the brief §1 priority table — synthesizer iterates this
# list verbatim.
MATCHERS_BY_PRIORITY: Final[tuple[tuple[int, str, Matcher], ...]] = (
    (PRIORITIES[CATEGORY_REGRESSION_WITH_LOCALIZATION],
     CATEGORY_REGRESSION_WITH_LOCALIZATION, match_regression_with_localization),
    (PRIORITIES[CATEGORY_INVESTIGATE_LOCATION],
     CATEGORY_INVESTIGATE_LOCATION, match_investigate_location),
    (PRIORITIES[CATEGORY_INVESTIGATE_REGRESSION],
     CATEGORY_INVESTIGATE_REGRESSION, match_investigate_regression),
    (PRIORITIES[CATEGORY_COVERAGE_GAP],
     CATEGORY_COVERAGE_GAP, match_coverage_gap),
    (PRIORITIES[CATEGORY_FLAKY_SUSPECTED],
     CATEGORY_FLAKY_SUSPECTED, match_flaky_suspected),
    (PRIORITIES[CATEGORY_UNAVAILABLE_ANALYSIS],
     CATEGORY_UNAVAILABLE_ANALYSIS, match_unavailable_analysis),
    (PRIORITIES[CATEGORY_ALL_GREEN],
     CATEGORY_ALL_GREEN, match_all_green),
)


# ---------------------------------------------------------------------------
# Compound + mutual exclusion rules
# ---------------------------------------------------------------------------


def compound_resolution(hits: list[CategoryHit]) -> list[CategoryHit]:
    """Drop constituents of ``regression_with_localization`` compounds.

    Brief §1 — "Compound rule": for each
    ``regression_with_localization`` hit covering
    ``(file=F, primary_line=L, test_id=T)``, drop the bare
    ``investigate_location`` hit on the SAME ``(file, primary_line)`` AND
    the bare ``investigate_regression`` hit on the SAME ``test_id``. Other
    categories (``coverage_gap``, ``flaky_suspected``,
    ``unavailable_analysis``, ``all_green``) are not affected.

    The drop conditions use closed-loop sets built from the compound
    payloads. The ``investigate_location`` key is the precise
    ``(file, primary_line)`` pair the compound fired on — NOT bare file
    membership — so a compound on ``(F, L, T)`` swallows only its genuine
    constituent and can no longer silently delete an unrelated
    ``investigate_location`` on the SAME file at a DIFFERENT symbol/line
    (ORC-12). The genuine constituent always shares the compound's
    ``(file, primary_line)`` because both project the same
    ``LocalizationEntry.code_location``.

    Subtle case: if two compounds fire on the same file but different
    lines (e.g. F:L1 for T1 and F:L2 for T2, both regressed), each
    swallows only the ``investigate_location`` at its own
    ``(file, primary_line)`` — a third ``investigate_location`` on F:L3
    with no overlapping compound survives.
    """

    compounds = [
        h for h in hits if h.category == CATEGORY_REGRESSION_WITH_LOCALIZATION
    ]
    if not compounds:
        return hits
    swallowed_locations: set[tuple[str, Any]] = set()
    swallowed_tests: set[str] = set()
    for c in compounds:
        swallowed_locations.add(
            (str(c.payload.get("file", "")), c.payload.get("primary_line"))
        )
        swallowed_tests.add(str(c.payload.get("test_id", "")))

    out: list[CategoryHit] = []
    for h in hits:
        if h.category == CATEGORY_INVESTIGATE_LOCATION:
            location = (str(h.payload.get("file", "")), h.payload.get("primary_line"))
            if location in swallowed_locations:
                continue
        elif h.category == CATEGORY_INVESTIGATE_REGRESSION:
            if str(h.payload.get("test_id", "")) in swallowed_tests:
                continue
        out.append(h)
    return out


def apply_mutual_exclusion(hits: list[CategoryHit]) -> list[CategoryHit]:
    """Apply the brief §1 mutual exclusion rules.

    Two rules:

    1. ``all_green`` MUST NOT coexist with any other category. If any
       non-``all_green`` hit fired, drop all ``all_green`` hits.
    2. ``unavailable_analysis`` coexists with other categories only when
       those categories triggered on partially-available facts. If
       literally zero facts are available AND tests failed, the matcher
       result will be exactly ``[unavailable_analysis]`` (because
       ``investigate_*`` / ``coverage_gap`` / ``flaky_suspected`` all
       require at least one fact-set, and ``all_green`` requires zero
       failures). In that case no exclusion fires here. The rule's
       intended-effect is therefore enforced by the matchers themselves
       — this function only needs to handle rule 1.
    """

    non_all_green = [h for h in hits if h.category != CATEGORY_ALL_GREEN]
    if non_all_green:
        return non_all_green
    return hits


# ---------------------------------------------------------------------------
# Internal helpers — stable primary_slot keys per category
# ---------------------------------------------------------------------------


def _primary_slot_for_location(
    *,
    file: str,
    line_range: tuple[int, int] | None,
    primary_line: int,
) -> str:
    """Stable sort key for ``investigate_location`` (brief §1).

    Format: ``{file}:{line_range[0] or primary_line}``. The fallback to
    ``primary_line`` handles symbol-resolver-less ecosystems (file-level
    findings) and the ``failure_proximity`` mode (no spectra, line-level
    fallback).
    """

    anchor = line_range[0] if line_range is not None else primary_line
    return f"{file}:{anchor}"


def _primary_slot_for_compound(
    *,
    file: str,
    line_range: tuple[int, int] | None,
    primary_line: int,
    test_id: str,
) -> str:
    """Stable sort key for ``regression_with_localization`` (brief §1).

    Format: ``{file}:{line_range[0] or primary_line}:{test_id}``.
    """

    anchor = line_range[0] if line_range is not None else primary_line
    return f"{file}:{anchor}:{test_id}"


def _sorted_transitions(
    transitions: Iterable[TestTransition],
) -> list[TestTransition]:
    """Deterministic iteration order for regression transitions.

    Sort by ``node_id`` lexicographically — matches the synthesizer's
    final sort key ``primary_slot = test_id`` so the matcher output is
    already in the order the final ``recommendations`` list will use.
    """

    return sorted(transitions, key=lambda t: t.node_id)


# ---------------------------------------------------------------------------
# Diagnostic helper — used by ``synthesizer.py`` for the determinism contract
# and by tests for human-readable assertion messages.
# ---------------------------------------------------------------------------


def categorize_hits(hits: Iterable[CategoryHit]) -> dict[str, int]:
    """Count hits per category. Pure helper, no side effects.

    Used by the determinism smoke test (``test_synthesis_determinism.py``)
    to assert byte-identity at category granularity even when the heavier
    full-JSON snapshot would mask small payload deltas.
    """

    counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    for h in hits:
        counts[h.category] += 1
    return counts


__all__ = [
    "CATEGORIES",
    "CATEGORY_ALL_GREEN",
    "CATEGORY_COVERAGE_GAP",
    "CATEGORY_FLAKY_SUSPECTED",
    "CATEGORY_INVESTIGATE_LOCATION",
    "CATEGORY_INVESTIGATE_REGRESSION",
    "CATEGORY_REGRESSION_WITH_LOCALIZATION",
    "CATEGORY_UNAVAILABLE_ANALYSIS",
    "CategoryHit",
    "INVESTIGATION_CATEGORIES",
    "INVESTIGATE_LOCATION_CONFIDENCES",
    "INVESTIGATE_LOCATION_MAX_RANK",
    "MATCHERS_BY_PRIORITY",
    "Matcher",
    "PRIORITIES",
    "apply_mutual_exclusion",
    "categorize_hits",
    "compound_resolution",
    "match_all_green",
    "match_coverage_gap",
    "match_flaky_suspected",
    "match_investigate_location",
    "match_investigate_regression",
    "match_regression_with_localization",
    "match_unavailable_analysis",
]
