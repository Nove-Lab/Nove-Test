"""Unit tests for the Regression section of `build_inspect_view`.

Companion to ``test_inspect.py``: that file covers the Coverage section and
the container shape; this file pins the Regression-section composition
(`_resolve_inspect_regression`). Memory + Regression seams are
monkeypatched at the `inspect` module so the tests never touch the
filesystem.

Baseline selection is stubbed at the ``resolve_baseline_for_run`` seam —
the Regression engine's shared engine-aware selector (D5 of
``decisions/2026-07-03-engine-selection-policy.md``). The selector's OWN
semantics (strictly-older, same target, same engine, tombstones excluded)
are pinned against a real store in
``tests/unit/regression/test_baseline_resolution.py``; these tests pin the
composer: what inspect does with the selector's answer.
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS
from novetest.localization import LocalizationUnavailable
from novetest.localization.results import REASON_MISSING_DERIVED_FACTS as LOC_REASON_MISSING
from novetest.replay import (
    REASON_MISSING_DERIVED_FACTS as REPLAY_REASON_MISSING,
    ReplayUnavailable,
)
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration.workflows import inspect as inspect_module
from novetest.orchestration.workflows.inspect import build_inspect_view
from novetest.regression import (
    REASON_NO_COMPARABLE_BASELINE,
    REASON_RUN_TOMBSTONED,
    RegressionUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    run_id: str,
    *,
    created_at: int,
    target_expression: str = "tests/",
    tombstoned_at: int | None = None,
    engine_name: str = "pytest",
) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type="dir",
        engine_name=engine_name,
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


def _make_regression_fact_set(baseline_ref: RunReference, target_ref: RunReference) -> RegressionFactSet:
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
    retrieved: MemoryEntry,
    baseline_ref: RunReference | None,
    compare_result: RegressionFactSet | RegressionUnavailable | None,
) -> list[tuple[RunReference, RunReference]]:
    """Wire all four inspect seams. Returns a list captured `compare_runs`
    is called with — empty when `_resolve_inspect_regression` short-
    circuits at the "no comparable baseline" branch.

    ``baseline_ref`` is what the stubbed ``resolve_baseline_for_run``
    returns: the selector's answer for the inspected run (``None`` = no
    comparable baseline — single run, only tombstoned priors, only
    cross-engine priors, or only other-target runs; the discrimination
    lives in the real selector, pinned in ``tests/unit/regression/``)."""

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store, skipped=None: history)
    monkeypatch.setattr(
        inspect_module, "retrieve_run_evidence", lambda *_a, **_k: retrieved
    )
    monkeypatch.setattr(
        inspect_module,
        "resolve_baseline_for_run",
        lambda _store, _entry: baseline_ref,
    )
    # Coverage is the other engine in the inspect surface — keep it
    # unavailable here so the Regression-section tests stay focused.
    monkeypatch.setattr(
        inspect_module,
        "get_coverage_facts",
        lambda _s, ref: CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="coverage out of scope for these regression tests",
            run_reference=ref,
        ),
    )

    seen: list[tuple[RunReference, RunReference]] = []

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> RegressionFactSet | RegressionUnavailable:
        seen.append((baseline, target))
        if compare_result is None:
            raise AssertionError(
                "compare_runs called but no compare_result configured for this test"
            )
        return compare_result

    monkeypatch.setattr(inspect_module, "compare_runs", fake_compare)

    # Localization section — default to unavailable so the Regression-section
    # tests stay focused and don't hit the filesystem.
    monkeypatch.setattr(
        inspect_module,
        "get_localization_findings",
        lambda _store, ref: LocalizationUnavailable(
            run_reference=ref,
            reason=LOC_REASON_MISSING,
            detail="findings not yet derived",
        ),
    )

    # Replay section — default to unavailable so the Regression-section tests
    # stay focused and don't hit the filesystem.
    monkeypatch.setattr(
        inspect_module,
        "get_replay_result",
        lambda _store, ref: ReplayUnavailable(
            run_reference=ref,
            reason=REPLAY_REASON_MISSING,
            detail="no replay attempt has been made for this run",
        ),
    )

    return seen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_latest_of_two_runs_resolves_prior_as_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _make_entry("01PRIORPRIORPRIORPRIORPRIO", created_at=1)
    inspected = _make_entry("01INSPECTINSPECTINSPECTINS", created_at=2)
    expected_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, inspected.run_record.run_reference
    )

    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        baseline_ref=prior.run_record.run_reference,
        compare_result=expected_fact_set,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    # The composer called compare_runs(prior, inspected) — argument order
    # matches decision §2 (older=baseline, newer=target).
    assert seen == [(prior.run_record.run_reference, inspected.run_record.run_reference)]

    payload = view.to_dict()
    outcome = payload["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["baseline_run_reference"]["run_id"] == prior.run_record.run_reference.run_id
    assert outcome["target_run_reference"]["run_id"] == inspected.run_record.run_reference.run_id
    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"


def test_inspecting_an_old_run_uses_immediate_prior_not_global_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspecting a middle run in a 3-run history: the baseline is the run
    the selector answered for THIS run (its immediate comparable prior),
    NOT the global latest pair. The immediate-prior selection itself lives
    in the real ``resolve_baseline_for_run`` (pinned in
    ``tests/unit/regression/``); here we pin that the composer threads the
    selector's answer — not some other pair — into ``compare_runs``."""

    oldest = _make_entry("01OLDESTOLDESTOLDESTOLDEST", created_at=1)
    middle = _make_entry("01MIDDLEMIDDLEMIDDLEMIDDLE", created_at=2)
    newest = _make_entry("01NEWESTNEWESTNEWESTNEWEST", created_at=3)
    expected_fact_set = _make_regression_fact_set(
        oldest.run_record.run_reference, middle.run_record.run_reference
    )

    seen = _patch_seams(
        monkeypatch,
        history=[newest, middle, oldest],  # newest-first per list_run_history
        retrieved=middle,                    # the inspected run
        baseline_ref=oldest.run_record.run_reference,  # selector's answer
        compare_result=expected_fact_set,
    )

    view = build_inspect_view(object(), middle.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    # compare_runs was called once with the immediate prior (oldest), NOT
    # with the global latest pair (oldest, newest).
    assert seen == [(oldest.run_record.run_reference, middle.run_record.run_reference)]
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["baseline_run_reference"]["run_id"] == oldest.run_record.run_reference.run_id
    assert outcome["target_run_reference"]["run_id"] == middle.run_record.run_reference.run_id


def test_only_run_on_target_surfaces_no_comparable_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _make_entry("01ONLYRUNONLYRUNONLYRUNONL", created_at=5, target_expression="tests/")

    seen = _patch_seams(
        monkeypatch,
        history=[inspected],
        retrieved=inspected,
        baseline_ref=None,        # selector: no comparable baseline
        compare_result=None,      # compare_runs must NOT be called
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    # The composer populates target_run_reference with the inspected run's
    # reference and leaves baseline_run_reference null (no baseline exists).
    assert outcome["target_run_reference"]["run_id"] == inspected.run_record.run_reference.run_id
    assert outcome["baseline_run_reference"] is None
    assert outcome["detail"] == "tests/"
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "unavailable"


def test_bare_invocation_refusal_detail_renders_workspace_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W2/S27 (Gate-1 Q5b): a bare ``novetest test`` records an EMPTY
    ``target_expression``; the no-comparable-baseline refusal must render
    the pinned ``(entire workspace)`` placeholder instead of ``detail: ""``
    (mirrors regression's S36-close pin). Non-empty expressions are
    unchanged — pinned by
    ``test_only_run_on_target_surfaces_no_comparable_baseline`` above."""

    inspected = _make_entry(
        "01BAREINVOKEBAREINVOKEBARE", created_at=5, target_expression=""
    )
    seen = _patch_seams(
        monkeypatch,
        history=[inspected],
        retrieved=inspected,
        baseline_ref=None,        # selector: no comparable baseline
        compare_result=None,      # compare_runs must NOT be called
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    assert outcome["detail"] == "(entire workspace)"


def test_tombstoned_inspected_run_propagates_compare_run_tombstoned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tombstoned inspected run with a live prior reaches `compare_runs`,
    which fail-hards with `REASON_RUN_TOMBSTONED` per decision §C.1."""

    prior = _make_entry("01PRIORPRIORPRIORPRIORPRIO", created_at=1)
    inspected = _make_entry(
        "01TOMBSTONETOMBSTONETOMBST", created_at=2, tombstoned_at=999
    )
    inspected_ref = inspected.run_record.run_reference
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        # The selector ignores the input's own tombstone — the live prior
        # is still the answer; compare_runs is what fails hard (§C.1).
        baseline_ref=prior.run_record.run_reference,
        compare_result=RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail="target",
            baseline_run_reference=prior.run_record.run_reference,
            target_run_reference=inspected_ref,
        ),
    )

    view = build_inspect_view(object(), inspected_ref.run_id)  # type: ignore[arg-type]
    assert view is not None
    # The prior IS strictly older than the inspected, so compare_runs IS
    # called — and the engine fails hard with TOMBSTONED.
    assert seen == [(prior.run_record.run_reference, inspected_ref)]
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_TOMBSTONED


def test_live_inspected_with_only_tombstoned_priors_surfaces_no_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tombstoned priors are excluded inside the real selector (Memory's
    ``include_tombstoned=False`` convention — pinned in
    ``tests/unit/regression/``). At this seam that is a ``None`` answer,
    so the live inspected run reports no comparable baseline."""

    inspected = _make_entry("01LIVEINSPECTLIVEINSPECTIN", created_at=5)
    seen = _patch_seams(
        monkeypatch,
        history=[inspected],  # the tombstoned priors are elided from history too — irrelevant
        retrieved=inspected,
        baseline_ref=None,
        compare_result=None,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE


def test_other_target_siblings_are_excluded_by_the_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Target-expression partitioning lives inside the real selector
    (``find_runs_for_target``'s rule — pinned in ``tests/unit/regression/``);
    a run on a different target is a ``None`` answer at this seam."""

    other_target = _make_entry(
        "01OTHEROTHEROTHEROTHEROTHE", created_at=1, target_expression="other/"
    )
    inspected = _make_entry(
        "01SAMETARGETSAMETARGETSAME", created_at=2, target_expression="tests/"
    )
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, other_target],
        retrieved=inspected,
        baseline_ref=None,
        compare_result=None,
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE


def test_cross_engine_prior_surfaces_no_comparable_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D5 behavior change (2026-07-03): a same-target prior produced by a
    DIFFERENT engine (pytest prior, jest inspected) is never selected — the
    real selector answers ``None`` — so inspect surfaces
    ``REASON_NO_COMPARABLE_BASELINE`` and ``compare_runs`` is NOT called.

    Pre-D5, the composer hand-picked the cross-engine prior and
    ``compare_runs`` refused it with ``REASON_ENGINE_MISMATCH``; that
    reason now remains reachable only via explicitly user-picked pairs
    (``regression compare <id1> <id2>`` — defense-in-depth guard, pinned
    in ``tests/unit/regression/test_compare.py``)."""

    prior = _make_entry(
        "01PRIORPYTESTPRIORPYTESTPR", created_at=1, engine_name="pytest"
    )
    inspected = _make_entry(
        "01INSPECTJESTINSPECTJESTIN", created_at=2, engine_name="jest"
    )
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        baseline_ref=None,        # the engine-scoped selector's real answer
        compare_result=None,      # compare_runs must NOT be called
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert seen == []
    outcome = view.to_dict()["regression_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    assert outcome["target_run_reference"]["run_id"] == inspected.run_record.run_reference.run_id
    assert outcome["baseline_run_reference"] is None


def test_composer_passes_inspected_entry_to_shared_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composer consults ``resolve_baseline_for_run`` with the
    INSPECTED run's Memory Entry (not the global latest) and threads its
    answer into ``compare_runs`` as the baseline — the structural pin that
    inspect routes baseline selection through the shared D5 selector."""

    prior = _make_entry("01PRIORSELECTORPRIORSELECT", created_at=1)
    inspected = _make_entry("01INSPECTSELECTORINSPECTSE", created_at=2)
    expected_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, inspected.run_record.run_reference
    )
    seen = _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        baseline_ref=prior.run_record.run_reference,
        compare_result=expected_fact_set,
    )

    # Override the selector stub with a logging fake (last setattr wins).
    selector_seen: list[MemoryEntry] = []

    def logging_selector(_store: Any, entry: MemoryEntry) -> RunReference:
        selector_seen.append(entry)
        return prior.run_record.run_reference

    monkeypatch.setattr(
        inspect_module, "resolve_baseline_for_run", logging_selector
    )

    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    assert selector_seen == [inspected]
    assert seen == [(prior.run_record.run_reference, inspected.run_record.run_reference)]


def test_sub_reports_regression_flips_across_available_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `sub_reports["regression"]` marker must reflect the actual
    outcome — `"available"` only when a `RegressionFactSet` lands."""

    # Case 1: available (fact-set)
    prior = _make_entry("01PRIORAAAAAAAAAAAAAAAAAAA", created_at=1)
    inspected = _make_entry("01TARGETAAAAAAAAAAAAAAAAAA", created_at=2)
    expected_fact_set = _make_regression_fact_set(
        prior.run_record.run_reference, inspected.run_record.run_reference
    )
    _patch_seams(
        monkeypatch,
        history=[inspected, prior],
        retrieved=inspected,
        baseline_ref=prior.run_record.run_reference,
        compare_result=expected_fact_set,
    )
    view = build_inspect_view(object(), inspected.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "available"

    # Case 2: unavailable (single-run target)
    only = _make_entry("01ONLYBBBBBBBBBBBBBBBBBBBB", created_at=10)
    _patch_seams(
        monkeypatch,
        history=[only],
        retrieved=only,
        baseline_ref=None,
        compare_result=None,
    )
    view = build_inspect_view(object(), only.run_record.run_reference.run_id)  # type: ignore[arg-type]
    assert view is not None
    sub_reports = view.to_dict()["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["regression"] == "unavailable"
