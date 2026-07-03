"""``cite_recommendation_evidence`` — pure projection from facts to citations.

Each recommendation MUST carry ≥1 evidence citation (REQ-ORCH-005); the
NFR-ORCH-002 round-trip contract additionally requires that every citation
carry enough state to be resolved back to its source via the canonical
retrieval interface (``memory/retrieve_run_evidence``,
``localization/get_localization_findings``, ``coverage/get_coverage_facts``,
``regression/get_regression_facts``, ``replay/get_replay_result``).

Brief §3 froze the citation shape — polymorphic by ``kind``, each carrying
a ``run_reference`` + a ``kind``-specific ``selector``. This file owns the
six per-``kind`` projections plus the per-category dispatch table.

Citation order rule (design doc §3): within a recommendation, citations
are stable-sorted by ``(kind, primary selector key)``. Same hit + same
bundle → byte-identical citation list.
"""

from __future__ import annotations

from typing import Any

from novetest.orchestration.recommendation.categories import (
    CATEGORY_ALL_GREEN,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_FLAKY_SUSPECTED,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_INVESTIGATE_REGRESSION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
    CategoryHit,
)
from novetest.orchestration.recommendation.fact_bundle import FactBundle


# ---------------------------------------------------------------------------
# Citation ``kind`` enum + sort order
# ---------------------------------------------------------------------------


KIND_LOCALIZATION_FINDING = "localization_finding"
KIND_COVERAGE_FACT = "coverage_fact"
KIND_REGRESSION_FACT = "regression_fact"
KIND_REPLAY_RESULT = "replay_result"
KIND_TEST_RESULT = "test_result"
KIND_RUN_REFERENCE = "run_reference"


CITATION_KIND_ORDER: tuple[str, ...] = (
    KIND_COVERAGE_FACT,
    KIND_LOCALIZATION_FINDING,
    KIND_REGRESSION_FACT,
    KIND_REPLAY_RESULT,
    KIND_RUN_REFERENCE,
    KIND_TEST_RESULT,
)


# ---------------------------------------------------------------------------
# Per-category dispatch
# ---------------------------------------------------------------------------


def cite_recommendation_evidence(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """Project the supporting facts onto the citation list for one hit.

    Brief §1 (per-category Citations column) drives the dispatch:

    - ``regression_with_localization`` → 1 regression_fact + 1
      localization_finding + 1 test_result (≥3 citations).
    - ``investigate_location`` → 1 localization_finding + ≥1 test_result
      (one per ``related_failed_tests`` entry).
    - ``investigate_regression`` → 1 regression_fact + 1 test_result.
    - ``coverage_gap`` → 1 coverage_fact + 1 localization_finding.
    - ``flaky_suspected`` → 1 replay_result + 1 test_result.
    - ``unavailable_analysis`` → 1 run_reference (bare; the
      ``reason_per_stage`` slot carries the actual diagnostic).
    - ``all_green`` → 1 run_reference.

    Returns the citation list pre-sorted via ``_sort_citations``; the
    template builder does NOT re-sort.
    """

    category = hit.category
    if category == CATEGORY_REGRESSION_WITH_LOCALIZATION:
        cites = _compound_citations(hit, bundle)
    elif category == CATEGORY_INVESTIGATE_LOCATION:
        cites = _investigate_location_citations(hit, bundle)
    elif category == CATEGORY_INVESTIGATE_REGRESSION:
        cites = _investigate_regression_citations(hit, bundle)
    elif category == CATEGORY_COVERAGE_GAP:
        cites = _coverage_gap_citations(hit, bundle)
    elif category == CATEGORY_FLAKY_SUSPECTED:
        cites = _flaky_suspected_citations(hit, bundle)
    elif category == CATEGORY_UNAVAILABLE_ANALYSIS:
        cites = _unavailable_analysis_citations(hit, bundle)
    elif category == CATEGORY_ALL_GREEN:
        cites = _all_green_citations(hit, bundle)
    else:
        raise ValueError(f"Unknown category={category!r}")
    return _sort_citations(cites)


# ---------------------------------------------------------------------------
# Per-category builders
# ---------------------------------------------------------------------------


def _compound_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """One regression_fact + one localization_finding + one test_result."""

    cites: list[dict[str, Any]] = []
    if bundle.regression_facts is not None:
        cites.append(_regression_fact_citation(hit, bundle))
    if bundle.localization_findings is not None:
        cites.append(_localization_finding_citation(hit, bundle))
    cites.append(_test_result_citation(hit, bundle, test_id=str(hit.payload.get("test_id"))))
    return cites


def _investigate_location_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """One localization_finding + one test_result per related failed test.

    Only one test_result per recommendation is required (REQ-ORCH-005
    minimum is ≥1 citation). To keep the wire shape concise and the
    sort-key cardinality low, we emit ONLY the first
    ``related_failed_tests`` entry as the test_result citation;
    additional related tests are referenceable via the
    ``localization_finding`` citation which round-trips back to the full
    list. This matches the design doc §3 example shape.
    """

    cites: list[dict[str, Any]] = []
    if bundle.localization_findings is None:
        return cites
    cites.append(_localization_finding_citation(hit, bundle))
    # Pick the (deterministically sorted) first related failed test as the
    # test_result citation; the localization_finding citation references
    # the full set via its selector.
    entry = _find_entry_for_location(hit, bundle)
    if entry is not None and entry.related_failed_tests:
        first_test = sorted(entry.related_failed_tests)[0]
        cites.append(_test_result_citation(hit, bundle, test_id=first_test))
    return cites


def _investigate_regression_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """One regression_fact + one test_result."""

    cites: list[dict[str, Any]] = []
    if bundle.regression_facts is not None:
        cites.append(_regression_fact_citation(hit, bundle))
    cites.append(_test_result_citation(hit, bundle, test_id=str(hit.payload.get("test_id"))))
    return cites


def _coverage_gap_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """One coverage_fact (file + lines selector) + one localization_finding."""

    cites: list[dict[str, Any]] = []
    if bundle.coverage_facts is not None:
        cites.append(
            {
                "kind": KIND_COVERAGE_FACT,
                "run_reference": bundle.coverage_facts.run_reference.to_dict(),
                "selector": {
                    "file": hit.payload.get("file"),
                    "lines": list(hit.payload.get("lines") or []),
                },
                "mode": bundle.coverage_facts.mapping_granularity,
            }
        )
    if bundle.localization_findings is not None:
        cites.append(_localization_finding_citation(hit, bundle))
    return cites


def _flaky_suspected_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """One replay_result + one test_result.

    The replay_result citation references the Replay Result THIS hit was
    emitted from — matched deterministically on the hit payload's
    ``(run_reference, test_id)`` pair against ``bundle.replay_results``
    (first match wins; the matcher copies both keys from the result, so a
    match always exists for matcher-produced hits). The test_result
    citation alone still satisfies the REQ-ORCH-005 ≥1-citation floor for
    defensively-constructed hits with no matching result.
    """

    cites: list[dict[str, Any]] = []
    source = next(
        (
            rr
            for rr in bundle.replay_results
            if rr.run_reference.run_id == hit.payload.get("run_reference")
            and (rr.test_id or "") == hit.payload.get("test_id")
        ),
        None,
    )
    if source is not None:
        cites.append(
            {
                "kind": KIND_REPLAY_RESULT,
                "run_reference": source.run_reference.to_dict(),
                "selector": {
                    "classification": source.classification,
                    "test_id": source.test_id,
                },
            }
        )
    cites.append(_test_result_citation(hit, bundle, test_id=str(hit.payload.get("test_id"))))
    return cites


def _unavailable_analysis_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """Bare ``run_reference`` citation — no fact source.

    The ``reason_per_stage`` slot already encodes the diagnostic; the
    citation just gives the AI consumer a round-trip hook back to the
    run via ``memory/list_run_history``.
    """

    return [
        {
            "kind": KIND_RUN_REFERENCE,
            "run_reference": bundle.run_reference.to_dict(),
            "selector": {},
        }
    ]


def _all_green_citations(
    hit: CategoryHit, bundle: FactBundle
) -> list[dict[str, Any]]:
    """Bare ``run_reference`` citation."""

    return [
        {
            "kind": KIND_RUN_REFERENCE,
            "run_reference": bundle.run_reference.to_dict(),
            "selector": {},
        }
    ]


# ---------------------------------------------------------------------------
# Per-kind citation projections (the resolvable selectors)
# ---------------------------------------------------------------------------


def _localization_finding_citation(
    hit: CategoryHit, bundle: FactBundle
) -> dict[str, Any]:
    """Project a Localization Finding citation.

    ``finding_id`` follows the engine's persisted shape — for now we use
    the per-run handle ``"loc_run_<run_id>"`` (deterministic, derivable
    from the run_reference). The selector carries ``rank`` so the
    consumer can resolve to the exact entry via index-after-fetch.
    """

    assert bundle.localization_findings is not None
    finding = bundle.localization_findings
    return {
        "kind": KIND_LOCALIZATION_FINDING,
        "run_reference": finding.run_reference.to_dict(),
        "finding_id": f"loc_run_{finding.run_reference.run_id}",
        "selector": {
            "rank": hit.payload.get("rank"),
            "file": hit.payload.get("file"),
            "primary_line": hit.payload.get("primary_line"),
        },
        "mode": finding.mode,
    }


def _regression_fact_citation(
    hit: CategoryHit, bundle: FactBundle
) -> dict[str, Any]:
    """Project a Regression Fact citation.

    Carries both baseline + target run references so the round-trip
    interface (``regression/get_regression_facts(baseline, target)``)
    can be invoked directly without an extra resolution step.
    """

    assert bundle.regression_facts is not None
    rf = bundle.regression_facts
    return {
        "kind": KIND_REGRESSION_FACT,
        "run_reference_from": rf.baseline_run_reference.to_dict(),
        "run_reference_to": rf.target_run_reference.to_dict(),
        "selector": {
            "test_id": hit.payload.get("test_id"),
            "regression_kind": hit.payload.get("regression_kind"),
        },
    }


def _test_result_citation(
    hit: CategoryHit, bundle: FactBundle, *, test_id: str
) -> dict[str, Any]:
    """Project a Test Result citation.

    The outcome string is read from the Run Record's ``test_results``
    when the test_id matches; otherwise we default to ``"failed"`` (the
    only category that wires a test_result citation is one that already
    knows the test failed — investigate_regression, investigate_location,
    flaky_suspected, regression_with_localization).
    """

    outcome = "failed"
    for tr in bundle.run_record.test_results:
        if tr.node_id == test_id:
            outcome = tr.outcome
            break
    return {
        "kind": KIND_TEST_RESULT,
        "run_reference": bundle.run_reference.to_dict(),
        "test_id": test_id,
        "outcome": outcome,
        "selector": {"test_id": test_id},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_entry_for_location(
    hit: CategoryHit, bundle: FactBundle
) -> Any:
    """Locate the LocalizationEntry referenced by a location-keyed hit.

    Matches on ``(file, primary_line)`` — the same anchor used in the
    primary_slot. Returns ``None`` when no entry matches (which the
    matcher guarantees won't happen for ``investigate_location`` /
    ``regression_with_localization`` hits, but the defensive ``None``
    keeps the helper total).
    """

    finding = bundle.localization_findings
    if finding is None:
        return None
    target_file = hit.payload.get("file")
    target_line = hit.payload.get("primary_line")
    for entry in finding.entries:
        loc = entry.code_location
        if loc.file == target_file and loc.primary_line == target_line:
            return entry
    return None


def _sort_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable-sort citations by (kind index, primary selector key).

    Design doc §3 mandates this. Kind index uses
    ``CITATION_KIND_ORDER`` so the ordering is closed-vocabulary-pinned;
    secondary key is a lexicographic dump of the citation body so two
    citations with the same ``kind`` (e.g. two ``test_result`` cites
    inside a compound) are still byte-identically ordered.
    """

    kind_index = {k: i for i, k in enumerate(CITATION_KIND_ORDER)}
    return sorted(
        citations,
        key=lambda c: (
            kind_index.get(str(c.get("kind", "")), len(CITATION_KIND_ORDER)),
            _selector_sort_key(c),
        ),
    )


def _selector_sort_key(citation: dict[str, Any]) -> str:
    """Build a deterministic secondary sort key for a citation.

    Concatenates the kind-specific selector fields in a stable order.
    For citations without a ``selector`` (impossible in practice; the
    fallback exists for type completeness), we use the empty string.
    """

    selector = citation.get("selector") or {}
    parts = []
    # Sorted iteration to keep the key stable regardless of insertion order.
    for key in sorted(selector.keys()):
        parts.append(f"{key}={selector[key]}")
    return "|".join(parts)


__all__ = [
    "CITATION_KIND_ORDER",
    "KIND_COVERAGE_FACT",
    "KIND_LOCALIZATION_FINDING",
    "KIND_REGRESSION_FACT",
    "KIND_REPLAY_RESULT",
    "KIND_RUN_REFERENCE",
    "KIND_TEST_RESULT",
    "cite_recommendation_evidence",
]
