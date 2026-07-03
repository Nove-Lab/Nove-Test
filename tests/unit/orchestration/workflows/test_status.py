"""Unit tests for the ``build_status_view`` workflow + ``StatusView.to_dict``.

Pins the Defect-6 fix (2026-06-01): ``status.sub_reports.*`` MUST reflect
on-disk derived facts for the latest run, agreeing with ``inspect``'s
sources of truth.

The Memory + engine ``get_*`` seams are monkeypatched at the ``status``
module so the unit tests never touch the filesystem. Each test pins one
slice of the contract:

- empty store → all flags ``unavailable``;
- single run with no derived facts → all flags ``unavailable``;
- coverage facts cached for latest run → ``sub_reports.coverage ==
  "available"`` (granularity-independent);
- localization findings cached for latest run →
  ``sub_reports.localization == "available"`` (mode-independent);
- regression pair cached → ``sub_reports.regression == "available"``;
- regression pair not cached but two runs exist →
  ``sub_reports.regression == "unavailable"`` (cache-only contract);
- single-run store → ``sub_reports.regression == "unavailable"`` (no
  comparable baseline);
- replay always ``unavailable`` (Phase 5 not shipped).

Plus an aggregate-granularity regression pin that captures the exact
Defect-6 reproduction shape: a cargo-style aggregate coverage fact set
on disk MUST surface as ``sub_reports.coverage == "available"`` (pre-fix
it surfaced as ``unavailable`` because the flag was hard-defaulted False
regardless of cache state).
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS as COV_REASON_MISSING
from novetest.localization import LocalizationUnavailable
from novetest.localization.results import REASON_MISSING_DERIVED_FACTS as LOC_REASON_MISSING
from novetest.models import MemoryEntry, ReplayResult, RunRecord, RunReference
from novetest.models.coverage_fact_set import CoverageFactSet, CoverageSummary
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration.workflows import status as status_module
from novetest.orchestration.workflows.status import StatusView, build_status_view
from novetest.regression import (
    REASON_MISSING_DERIVED_FACTS as REG_REASON_MISSING,
    RegressionUnavailable,
)
from novetest.replay import (
    REASON_MISSING_DERIVED_FACTS as REPLAY_REASON_MISSING,
    ReplayUnavailable,
)


# ---------------------------------------------------------------------------
# Synthetic helpers — stand-ins so the unit tests never touch a Project Store.
# ---------------------------------------------------------------------------


def _make_entry(
    run_id: str,
    *,
    created_at: int,
    target_expression: str = "tests/",
    tombstoned_at: int | None = None,
) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1,
        summary_counts={"passed": 1, "total": 1},
    )
    return MemoryEntry(
        entry_id=run_id,
        run_record=record,
        stored_at=created_at + 2,
        has_coverage_facts=False,
        tombstoned_at=tombstoned_at,
    )


def _make_coverage_fact_set(
    ref: RunReference, *, mapping_granularity: str = "per-test"
) -> CoverageFactSet:
    summary = CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=80.0,
    )
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity=mapping_granularity,
        summary=summary,
        files=(),
        derived_at=4,
    )


def _make_localization_finding(ref: RunReference) -> LocalizationFinding:
    loc = CodeLocation(
        kind="symbol",
        file="src/calc.py",
        symbol="buggy",
        line_range=(4, 5),
        primary_line=5,
        evidence_lines=(5,),
    )
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=loc,
        score_raw=1.0,
        score_normalized=1.0,
        formula="ochiai",
        alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
        related_failed_tests=("tests/test_calc.py::test_buggy",),
        evidence_citations=(citation,),
    )
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10,
        entries=(entry,),
        derived_at=99_000,
        metadata={},
    )


def _make_regression_fact_set(
    baseline_ref: RunReference, target_ref: RunReference
) -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=baseline_ref,
        target_run_reference=target_ref,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=100,
        summary=RegressionSummary(
            regressed=0,
            fixed=0,
            still_failing=0,
            still_passing=1,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=1,
            total_target_tests=1,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )


def _patch_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    history: list[MemoryEntry],
    baseline_ref: RunReference | None = None,
    coverage_result: CoverageFactSet | CoverageUnavailable | None = None,
    localization_result: LocalizationFinding | LocalizationUnavailable | None = None,
    regression_result: RegressionFactSet | RegressionUnavailable | None = None,
    replay_result: ReplayResult | ReplayUnavailable | None = None,
) -> dict[str, list[Any]]:
    """Stub every Memory + engine seam at the ``status`` module.

    Returns a dict of call-log lists (keys: ``coverage_calls``,
    ``localization_calls``, ``regression_calls``, ``replay_calls``,
    ``baseline_selector_calls``) so the caller can pin which retrieval
    calls actually happened — load-bearing for the "cache-only, no
    side-effect derive" invariant.

    ``baseline_ref`` is what the stubbed ``resolve_baseline_for_run``
    answers for the latest run — the Regression engine's shared
    engine-aware selector (D5 of
    ``decisions/2026-07-03-engine-selection-policy.md``); its own
    semantics (strictly-older, same target, same engine, tombstones
    excluded) are pinned against a real store in
    ``tests/unit/regression/test_baseline_resolution.py``. The default
    ``None`` = "no comparable baseline", which matches the real answer for
    every single-run history these tests seed.

    Default behaviours when ``*_result`` is None:
    - coverage: returns ``CoverageUnavailable(missing-derived-facts)``
    - localization: returns ``LocalizationUnavailable(missing_derived_facts)``
    - regression: returns ``RegressionUnavailable(missing-derived-facts)``

    These defaults represent the "fresh run, nothing derived yet" baseline
    that the empty + single-run-no-facts tests exercise.
    """

    monkeypatch.setattr(status_module, "list_run_history", lambda _store: history)

    baseline_selector_calls: list[MemoryEntry] = []

    def fake_resolve_baseline(_store: Any, entry: MemoryEntry) -> RunReference | None:
        baseline_selector_calls.append(entry)
        return baseline_ref

    monkeypatch.setattr(
        status_module, "resolve_baseline_for_run", fake_resolve_baseline
    )

    coverage_calls: list[RunReference] = []

    def fake_get_coverage(
        _store: Any, ref: RunReference
    ) -> CoverageFactSet | CoverageUnavailable:
        coverage_calls.append(ref)
        if coverage_result is not None:
            return coverage_result
        return CoverageUnavailable(
            reason=COV_REASON_MISSING,
            detail="No coverage_facts.json found for this run",
            run_reference=ref,
        )

    monkeypatch.setattr(status_module, "get_coverage_facts", fake_get_coverage)

    localization_calls: list[RunReference] = []

    def fake_get_localization(
        _store: Any, ref: RunReference
    ) -> LocalizationFinding | LocalizationUnavailable:
        localization_calls.append(ref)
        if localization_result is not None:
            return localization_result
        return LocalizationUnavailable(
            run_reference=ref,
            reason=LOC_REASON_MISSING,
            detail="findings not yet derived",
        )

    monkeypatch.setattr(
        status_module, "get_localization_findings", fake_get_localization
    )

    regression_calls: list[tuple[RunReference, RunReference]] = []

    def fake_get_regression(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> RegressionFactSet | RegressionUnavailable:
        regression_calls.append((baseline, target))
        if regression_result is not None:
            return regression_result
        return RegressionUnavailable(
            reason=REG_REASON_MISSING,
            detail="No regression_facts.json found for this pair",
            baseline_run_reference=baseline,
            target_run_reference=target,
        )

    monkeypatch.setattr(status_module, "get_regression_facts", fake_get_regression)

    replay_calls: list[RunReference] = []

    def fake_get_replay(
        _store: Any, ref: RunReference
    ) -> ReplayResult | ReplayUnavailable:
        replay_calls.append(ref)
        if replay_result is not None:
            return replay_result
        return ReplayUnavailable(
            run_reference=ref,
            reason=REPLAY_REASON_MISSING,
            detail="no replay attempt has been made for this run",
        )

    monkeypatch.setattr(status_module, "get_replay_result", fake_get_replay)

    return {
        "coverage_calls": coverage_calls,
        "localization_calls": localization_calls,
        "regression_calls": regression_calls,
        "replay_calls": replay_calls,
        "baseline_selector_calls": baseline_selector_calls,
    }


# ---------------------------------------------------------------------------
# Empty store — every flag stays unavailable; no retrieval calls made.
# ---------------------------------------------------------------------------


def test_empty_store_returns_zero_history_and_all_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A freshly-initialized store has no runs → no engine probes fire."""

    call_log = _patch_seams(monkeypatch, history=[])
    view = build_status_view(object())  # type: ignore[arg-type]

    assert isinstance(view, StatusView)
    assert view.latest_entry is None
    assert view.run_history_size == 0
    assert view.coverage_available is False
    assert view.regression_available is False
    assert view.localization_available is False
    assert view.replay_available is False
    # No retrieval calls fire on an empty store — short-circuit pin.
    assert call_log["coverage_calls"] == []
    assert call_log["localization_calls"] == []
    assert call_log["regression_calls"] == []

    payload = view.to_dict()
    assert payload["latest_run_reference"] is None
    assert payload["run_history_size"] == 0
    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports == {
        "coverage": "unavailable",
        "regression": "unavailable",
        "localization": "unavailable",
        "replay": "unavailable",
    }


# ---------------------------------------------------------------------------
# Single run, no derived facts — flags all unavailable; retrievals fire and
# return Unavailable discriminators.
# ---------------------------------------------------------------------------


def test_single_run_with_no_derived_facts_reports_all_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One run, no derive ever called → all sub_reports unavailable."""

    entry = _make_entry("01RUN0000000000000000A", created_at=100)
    call_log = _patch_seams(monkeypatch, history=[entry])

    view = build_status_view(object())  # type: ignore[arg-type]

    assert view.latest_entry is entry
    assert view.run_history_size == 1
    assert view.coverage_available is False
    assert view.regression_available is False
    assert view.localization_available is False
    assert view.replay_available is False

    # Each engine's get_* was probed with the latest run's reference exactly once.
    assert len(call_log["coverage_calls"]) == 1
    assert call_log["coverage_calls"][0].run_id == "01RUN0000000000000000A"
    assert len(call_log["localization_calls"]) == 1
    assert call_log["localization_calls"][0].run_id == "01RUN0000000000000000A"
    # Single-run history → no priors → no regression cache lookup.
    assert call_log["regression_calls"] == []


# ---------------------------------------------------------------------------
# Coverage available — per-test granularity (pytest fixture path).
# ---------------------------------------------------------------------------


def test_coverage_per_test_facts_persisted_marks_coverage_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached per-test coverage facts → sub_reports.coverage == 'available'."""

    entry = _make_entry("01RUN0000000000000000B", created_at=200)
    coverage_fact_set = _make_coverage_fact_set(
        entry.run_record.run_reference, mapping_granularity="per-test"
    )
    _patch_seams(
        monkeypatch,
        history=[entry],
        coverage_result=coverage_fact_set,
    )

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.coverage_available is True
    assert view.localization_available is False
    assert view.regression_available is False
    assert view.replay_available is False

    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["coverage"] == "available"
    assert sub_reports["localization"] == "unavailable"
    assert sub_reports["regression"] == "unavailable"
    assert sub_reports["replay"] == "unavailable"


# ---------------------------------------------------------------------------
# Defect 6 regression pin: aggregate granularity must ALSO surface as
# `available` — the original Manual Test reproduction was a cargo
# aggregate run whose facts existed on disk but `status` reported as
# `unavailable` because the flag was hard-defaulted False.
# ---------------------------------------------------------------------------


def test_defect6_aggregate_granularity_coverage_facts_marks_coverage_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cargo-shape aggregate coverage facts cached → coverage 'available'.

    Pre-fix, this scenario surfaced as ``unavailable`` regardless of
    on-disk state — the symptom Manual Test reproduced verbatim on
    ``/tmp/d4-cargo``. The flag must be granularity-independent because
    ``get_coverage_facts`` is granularity-agnostic; this test pins that
    invariant against accidental re-introduction of a per-test gate.
    """

    entry = _make_entry("01CARGOAGG0000000000000A", created_at=300)
    aggregate_facts = _make_coverage_fact_set(
        entry.run_record.run_reference, mapping_granularity="aggregate"
    )
    _patch_seams(monkeypatch, history=[entry], coverage_result=aggregate_facts)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.coverage_available is True
    assert view.to_dict()["sub_reports"] == {
        "coverage": "available",
        "regression": "unavailable",
        "localization": "unavailable",
        "replay": "unavailable",
    }


# ---------------------------------------------------------------------------
# Localization available — findings cached for the latest run.
# ---------------------------------------------------------------------------


def test_localization_findings_persisted_marks_localization_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached localization findings → sub_reports.localization == 'available'."""

    entry = _make_entry("01RUN0000000000000000C", created_at=400)
    finding = _make_localization_finding(entry.run_record.run_reference)
    _patch_seams(monkeypatch, history=[entry], localization_result=finding)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.localization_available is True
    assert view.coverage_available is False
    assert view.regression_available is False
    assert view.replay_available is False

    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["localization"] == "available"
    assert sub_reports["coverage"] == "unavailable"


# ---------------------------------------------------------------------------
# Localization mode-independence — failure_proximity findings (no coverage
# matrix) MUST also surface as available, mirroring the Defect-4 mode
# dispatch alignment for `localization latest`.
# ---------------------------------------------------------------------------


def test_localization_failure_proximity_findings_mark_localization_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """failure_proximity mode finding → sub_reports.localization == 'available'."""

    entry = _make_entry("01RUN0000000000000000D", created_at=500)
    ref = entry.run_record.run_reference
    # failure_proximity mode-specific deviations per
    # `agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md`
    # §"failure_proximity deviations": alternate_scores_available is empty,
    # entries carry empty alternate_scores dicts. Pin both.
    loc = CodeLocation(
        kind="file",
        file="src/buggy.rs",
        symbol=None,
        line_range=None,
        primary_line=None,
        evidence_lines=(),
    )
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests::failing", "outcome": "failed"},
    )
    # failure_proximity mode reuses the closed-enum ``"ochiai"`` placeholder
    # in the entry/finding formula slot (see
    # ``src/novetest/localization/failure_proximity.py::_PLACEHOLDER_FORMULA``):
    # mode discrimination flows via ``finding.mode == "failure_proximity"``,
    # not via the formula field. This pin keeps in lockstep with that
    # engine-side convention.
    fp_entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=loc,
        score_raw=2.0,
        score_normalized=1.0,
        formula="ochiai",
        alternate_scores={},
        related_failed_tests=("tests::failing",),
        evidence_citations=(citation,),
    )
    finding = LocalizationFinding(
        run_reference=ref,
        engine_name="cargo-test",
        ecosystem="rust",
        mode="failure_proximity",
        confidence="low",
        formula="ochiai",
        alternate_scores_available=(),
        top_n=10,
        entries=(fp_entry,),
        derived_at=99_000,
        metadata={},
    )
    _patch_seams(monkeypatch, history=[entry], localization_result=finding)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.localization_available is True


# ---------------------------------------------------------------------------
# Regression available — pair cache exists for (most_recent_prior, latest).
# ---------------------------------------------------------------------------


def test_regression_pair_cached_marks_regression_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached regression_facts.json for (prior, latest) → regression 'available'."""

    prior = _make_entry("01PRIOR000000000000000A", created_at=600)
    latest = _make_entry("01LATEST00000000000000A", created_at=700)
    # list_run_history is newest-first; pair-selection is the shared
    # selector — stubbed to answer the prior (mirrors inspect).
    history = [latest, prior]
    fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, latest.run_record.run_reference
    )
    call_log = _patch_seams(
        monkeypatch,
        history=history,
        baseline_ref=prior.run_record.run_reference,
        regression_result=fact_set,
    )

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.regression_available is True
    assert view.coverage_available is False
    assert view.localization_available is False

    # The pair-selection contract: most-recent strictly-older sibling is
    # baseline, latest is target. Pin the exact arg order.
    assert len(call_log["regression_calls"]) == 1
    baseline_arg, target_arg = call_log["regression_calls"][0]
    assert baseline_arg.run_id == "01PRIOR000000000000000A"
    assert target_arg.run_id == "01LATEST00000000000000A"


# ---------------------------------------------------------------------------
# Regression pair selection routes through the shared engine-aware selector
# (D5, 2026-07-03) — the same seam `inspect` composes, so the two verbs
# agree by construction.
# ---------------------------------------------------------------------------


def test_regression_flag_consults_shared_selector_with_latest_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_latest_regression_available`` asks ``resolve_baseline_for_run``
    for the LATEST entry's baseline (exactly once) and probes the cache
    with the selector's answer. The selector's engine filter itself is
    pinned against a real store in ``tests/unit/regression/``."""

    prior = _make_entry("01PRIORSEL0000000000000A", created_at=2_000)
    latest = _make_entry("01LATESTSEL000000000000A", created_at=2_100)
    call_log = _patch_seams(
        monkeypatch,
        history=[latest, prior],
        baseline_ref=prior.run_record.run_reference,
    )

    build_status_view(object())  # type: ignore[arg-type]
    assert call_log["baseline_selector_calls"] == [latest]
    # The cache probe used the selector's answer as the baseline side.
    assert len(call_log["regression_calls"]) == 1
    baseline_arg, target_arg = call_log["regression_calls"][0]
    assert baseline_arg.run_id == "01PRIORSEL0000000000000A"
    assert target_arg.run_id == "01LATESTSEL000000000000A"


# ---------------------------------------------------------------------------
# Regression unavailable — pair not cached even though two runs exist.
# This is the load-bearing "cache-only, no derive on read" pin.
# ---------------------------------------------------------------------------


def test_regression_pair_not_cached_keeps_regression_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two runs, no compare ever called → regression stays unavailable.

    ``status`` MUST NOT call ``compare_runs`` (which derives on cache
    miss) — pinned by the no-side-effect contract. The default
    ``regression_result`` (Unavailable / missing-derived-facts) drives
    this case.
    """

    prior = _make_entry("01PRIOR000000000000000B", created_at=800)
    latest = _make_entry("01LATEST00000000000000B", created_at=900)
    call_log = _patch_seams(
        monkeypatch,
        history=[latest, prior],
        baseline_ref=prior.run_record.run_reference,
        # No regression_result → fake_get_regression returns Unavailable.
    )

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.regression_available is False
    # The cache-read call still fires (with the correct pair args) — we
    # just don't derive on miss.
    assert len(call_log["regression_calls"]) == 1


# ---------------------------------------------------------------------------
# Regression unavailable — only one run on the target.
# ---------------------------------------------------------------------------


def test_regression_single_run_returns_unavailable_without_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single run on target → selector answers None → no regression cache
    lookup fires."""

    only = _make_entry("01ONLY000000000000000A", created_at=1_000)
    call_log = _patch_seams(monkeypatch, history=[only], baseline_ref=None)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.regression_available is False
    # No comparable baseline → short-circuit before the cache read.
    assert call_log["regression_calls"] == []


# ---------------------------------------------------------------------------
# Regression unavailable — only tombstoned priors (find_runs_for_target with
# include_tombstoned=False filters them out at the Memory seam).
# ---------------------------------------------------------------------------


def test_regression_only_tombstoned_priors_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tombstone exclusion lives inside the real selector (Memory's
    ``include_tombstoned=False`` convention — pinned in
    ``tests/unit/regression/``): a latest run whose only prior is
    tombstoned gets a ``None`` answer → no cache lookup fires → False.

    Pins that ``status`` delegates tombstone handling to the shared
    selector rather than re-implementing the check locally.
    """

    tombstoned_prior = _make_entry(
        "01TOMB0000000000000000A", created_at=1_100, tombstoned_at=1_150
    )
    latest = _make_entry("01LATEST00000000000000C", created_at=1_200)
    # The tombstoned prior is in `history` for the size count; the selector
    # (stubbed to its real answer, None) never surfaces it.
    history = [latest, tombstoned_prior]
    call_log = _patch_seams(monkeypatch, history=history, baseline_ref=None)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.regression_available is False
    # Selector answered None → no cache lookup attempted.
    assert call_log["regression_calls"] == []
    # run_history_size still reflects all entries (matches list_run_history).
    assert view.run_history_size == 2


# ---------------------------------------------------------------------------
# Replay (Phase 5 entry) — cache-only probe, mirroring the other three.
# ---------------------------------------------------------------------------


def _make_replay_result(ref: RunReference) -> ReplayResult:
    return ReplayResult(
        run_reference=ref,
        classification="inconsistent",
        reruns_total=5,
        reruns_failed=2,
        test_id="tests/test_flaky.py::test_flaky",
        per_rerun_outcomes=("passed", "failed", "passed", "passed", "failed"),
        consistency_summary={
            "original_passed": 1,
            "replay_passed": 3,
            "replay_failed": 2,
        },
        attempted_at=1_748_800_000_000,
    )


def test_replay_no_cached_result_keeps_replay_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With coverage + localization + regression cached but NO replay result
    on disk, replay stays ``unavailable`` (cache-only probe returns
    Unavailable). Pins that the flag tracks the cache, not the other three."""

    prior = _make_entry("01PRIORALL000000000000A", created_at=1_300)
    latest = _make_entry("01LATESTALL00000000000A", created_at=1_400)
    coverage_fact_set = _make_coverage_fact_set(
        latest.run_record.run_reference, mapping_granularity="per-test"
    )
    localization_finding = _make_localization_finding(latest.run_record.run_reference)
    regression_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, latest.run_record.run_reference
    )
    call_log = _patch_seams(
        monkeypatch,
        history=[latest, prior],
        baseline_ref=prior.run_record.run_reference,
        coverage_result=coverage_fact_set,
        localization_result=localization_finding,
        regression_result=regression_fact_set,
    )

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.coverage_available is True
    assert view.localization_available is True
    assert view.regression_available is True
    assert view.replay_available is False

    # Replay cache was probed exactly once with the latest run's ref.
    assert len(call_log["replay_calls"]) == 1
    assert call_log["replay_calls"][0].run_id == "01LATESTALL00000000000A"

    payload = view.to_dict()
    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports == {
        "coverage": "available",
        "regression": "available",
        "localization": "available",
        "replay": "unavailable",
    }


def test_replay_result_persisted_marks_replay_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached ``replay_result.json`` for the latest run →
    ``sub_reports.replay == 'available'`` (classification-independent)."""

    entry = _make_entry("01REPLAY00000000000000A", created_at=1_600)
    result = _make_replay_result(entry.run_record.run_reference)
    _patch_seams(monkeypatch, history=[entry], replay_result=result)

    view = build_status_view(object())  # type: ignore[arg-type]
    assert view.replay_available is True
    assert view.coverage_available is False

    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["replay"] == "available"


# ---------------------------------------------------------------------------
# Wire shape regression pin — to_dict shape is byte-identical for the
# all-available scenario.
# ---------------------------------------------------------------------------


def test_to_dict_shape_pins_all_keys_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the four required ``sub_reports`` keys + the two top-level
    keys (``latest_run_reference`` + ``run_history_size``). Defends
    against accidental key renames during future engine additions."""

    entry = _make_entry("01SHAPECHECK0000000000A", created_at=1_500)
    _patch_seams(monkeypatch, history=[entry])

    payload = build_status_view(object()).to_dict()  # type: ignore[arg-type]
    assert set(payload.keys()) == {
        "latest_run_reference",
        "run_history_size",
        "sub_reports",
    }
    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert set(sub_reports.keys()) == {
        "coverage",
        "regression",
        "localization",
        "replay",
    }
