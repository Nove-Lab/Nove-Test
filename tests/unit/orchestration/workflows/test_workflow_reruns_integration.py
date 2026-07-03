"""``test_target_in_store`` × the opt-in ``--reruns`` Replay sub-workflow.

Unit-scope seam tests for the 2026-06-25 integration (decision
``2026-06-25-test-reruns-flag-and-replay-integration``): every engine the
workflow composes is monkeypatched at the ``workflows/test.py`` module
namespace, so these tests pin the COMPOSITION contract — when Replay is
invoked, with which arguments, and how its outcome lands on
``StageEligibility`` + ``FactBundle.replay_results`` — without running any
native engine.

API-adaptation note (recorded in the cycle handoff): the brief sketched a
per-failed-test ``replay_run(..., target=test_id)`` loop, but the Replay
engine's attempt granularity is the whole original run (no ``target``
parameter; persistence is keyed by original run id). The integrated
workflow therefore performs ONE whole-run attempt per invocation; these
tests pin that call shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import (
    REASON_MISSING_DERIVED_FACTS as COV_REASON_MISSING,
)
from novetest.localization import LocalizationUnavailable
from novetest.localization.results import (
    REASON_NO_COVERAGE as LOC_REASON_NO_COVERAGE,
)
from novetest.memory.project_store import PinnedEngine, ProjectStore
from novetest.models import MemoryEntry, ReplayResult, RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression import RegressionUnavailable
from novetest.regression.results import (
    REASON_NO_COMPARABLE_BASELINE as REG_REASON_NO_COMPARABLE_BASELINE,
)
from novetest.replay import REASON_ENGINE_NOT_READY, ReplayUnavailable

import novetest.orchestration.workflows.test as test_workflow


_RUN_ID = "01RERUNSRUN0000000000000A"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _record(*, failed: int) -> RunRecord:
    ref = RunReference(run_id=_RUN_ID, created_at=1000)
    results = tuple(
        TestResult(node_id=f"tests/test_x.py::test_{i}", outcome="failed")
        for i in range(failed)
    ) + (TestResult(node_id="tests/test_x.py::test_ok", outcome="passed"),)
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed" if failed else "passed",
        started_at=1000,
        completed_at=1001,
        summary_counts={
            "passed": 1,
            "failed": failed,
            "total": failed + 1,
        },
        test_results=results,
    )


def _entry(record: RunRecord) -> MemoryEntry:
    return MemoryEntry(
        entry_id=record.run_reference.run_id,
        run_record=record,
        stored_at=1002,
    )


def _replay_result(record: RunRecord) -> ReplayResult:
    return ReplayResult(
        run_reference=record.run_reference,
        classification="inconsistent",
        reruns_total=5,
        reruns_failed=2,
        test_id="tests/test_x.py::test_0",
    )


class _Seams:
    """Records the replay_run invocations the workflow makes."""

    def __init__(self) -> None:
        self.replay_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []


def _patch_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record: RunRecord,
    replay_outcome: ReplayResult | ReplayUnavailable | None,
) -> _Seams:
    """Stub every engine seam ``test_target_in_store`` composes.

    Coverage / Regression / Localization all return their Unavailable
    discriminators (the minimal best-effort path); Replay returns
    ``replay_outcome`` and records its invocation.
    """

    seams = _Seams()
    ref = record.run_reference
    entry = _entry(record)

    monkeypatch.setattr(
        test_workflow, "resolve_test_target", lambda expr, ws: object()
    )

    async def fake_execute(*args: Any, **kwargs: Any) -> tuple[RunRecord, tuple[Any, ...]]:
        return record, ()

    monkeypatch.setattr(test_workflow, "execute", fake_execute)
    monkeypatch.setattr(
        test_workflow, "store_run_evidence", lambda store, rec: entry
    )
    monkeypatch.setattr(
        test_workflow, "retrieve_run_evidence", lambda store, r: entry
    )
    monkeypatch.setattr(
        test_workflow,
        "derive_coverage_facts",
        lambda store, r: CoverageUnavailable(
            reason=COV_REASON_MISSING, detail="stubbed", run_reference=ref
        ),
    )
    monkeypatch.setattr(
        test_workflow,
        "resolve_latest_baseline",
        lambda store, target: RegressionUnavailable(
            reason=REG_REASON_NO_COMPARABLE_BASELINE,
            detail="stubbed",
            baseline_run_reference=None,
            target_run_reference=ref,
        ),
    )
    monkeypatch.setattr(
        test_workflow,
        "derive_localization_findings",
        lambda store, r: LocalizationUnavailable(
            run_reference=ref, reason=LOC_REASON_NO_COVERAGE, detail="stubbed"
        ),
    )

    async def fake_replay_run(
        *args: Any, **kwargs: Any
    ) -> ReplayResult | ReplayUnavailable:
        seams.replay_calls.append((args, kwargs))
        assert replay_outcome is not None, (
            "replay_run invoked although the test expected no attempt"
        )
        return replay_outcome

    monkeypatch.setattr(test_workflow, "replay_run", fake_replay_run)
    return seams


def _store(tmp_path: Path) -> ProjectStore:
    # Anchored-pin model (2026-07-03): execution workflows read the handle's
    # engine pin; a pin-less handle raises EngineNotReadyError before the
    # execute seam is reached, so the synthetic handle carries one.
    return ProjectStore(
        path=tmp_path / ".novetest",
        initialized_at=1,
        store_state="ready",
        pinned_engine=PinnedEngine(ecosystem="python", engine_name="pytest"),
    )


# ---------------------------------------------------------------------------
# Composition contract
# ---------------------------------------------------------------------------


async def test_failed_run_with_reruns_invokes_one_whole_run_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """1 failed test + ``reruns=5`` → exactly ONE ``replay_run`` call with
    ``reruns=5``; the result lands as a 1-element ``replay_results`` tuple
    (brief §4 — "synthesizer receives a replay_results tuple of length 1")
    and the eligibility slot transitions to ``available``.
    """
    record = _record(failed=1)
    result = _replay_result(record)
    seams = _patch_seams(monkeypatch, record=record, replay_outcome=result)
    store = _store(tmp_path)

    outcome = await test_workflow.test_target_in_store(
        "tests/", store, reruns=5
    )

    assert len(seams.replay_calls) == 1
    args, kwargs = seams.replay_calls[0]
    assert args == (store, record.run_reference)
    assert kwargs == {"reruns": 5, "timeout": 600.0}
    assert outcome.fact_bundle.replay_results == (result,)
    assert outcome.stage_eligibility.replay == "available"
    assert outcome.stage_eligibility.per_stage_reasons["replay"] is None
    # The inconsistent result makes flaky_suspected reachable end-to-end.
    assert "flaky_suspected" in [r.category for r in outcome.recommendations]


async def test_passing_run_with_reruns_skips_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """0 failed tests + ``reruns=5`` → replay loop skipped; the eligibility
    block byte-matches the no-``--reruns`` happy path (brief §4).
    """
    record = _record(failed=0)
    seams = _patch_seams(monkeypatch, record=record, replay_outcome=None)
    store = _store(tmp_path)

    with_flag = await test_workflow.test_target_in_store(
        "tests/", store, reruns=5
    )
    without_flag = await test_workflow.test_target_in_store("tests/", store)

    assert seams.replay_calls == []
    assert with_flag.fact_bundle.replay_results == ()
    assert with_flag.stage_eligibility.replay == "not_run"
    assert (
        with_flag.stage_eligibility.per_stage_reasons["replay"]
        == "replay_not_run"
    )
    assert (
        with_flag.stage_eligibility.to_dict()
        == without_flag.stage_eligibility.to_dict()
    )


async def test_default_reruns_zero_never_calls_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``reruns=0`` (the default) preserves the pre-integration behavior
    byte-for-byte even when the run has failed tests.
    """
    record = _record(failed=2)
    seams = _patch_seams(monkeypatch, record=record, replay_outcome=None)
    store = _store(tmp_path)

    outcome = await test_workflow.test_target_in_store("tests/", store)

    assert seams.replay_calls == []
    assert outcome.fact_bundle.replay_results == ()
    assert outcome.stage_eligibility.replay == "not_run"
    assert (
        outcome.stage_eligibility.per_stage_reasons["replay"]
        == "replay_not_run"
    )


async def test_replay_unavailable_is_best_effort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ``ReplayUnavailable`` attempt outcome does NOT fail the invocation
    (decision §"Error paths"): the eligibility slot carries the reason,
    the bundle stays replay-empty, and synthesis still fires.
    """
    record = _record(failed=1)
    unavailable = ReplayUnavailable(
        run_reference=record.run_reference,
        reason=REASON_ENGINE_NOT_READY,
        detail="engine readiness state='missing'",
    )
    seams = _patch_seams(
        monkeypatch, record=record, replay_outcome=unavailable
    )
    store = _store(tmp_path)

    outcome = await test_workflow.test_target_in_store(
        "tests/", store, reruns=3
    )

    assert len(seams.replay_calls) == 1
    assert outcome.fact_bundle.replay_results == ()
    assert outcome.stage_eligibility.replay == "unavailable"
    assert (
        outcome.stage_eligibility.per_stage_reasons["replay"]
        == REASON_ENGINE_NOT_READY
    )
    # Synthesis still produced output (unavailable_analysis fires: tests
    # failed AND stages — replay included — were unavailable).
    categories = [r.category for r in outcome.recommendations]
    assert "unavailable_analysis" in categories
    # The replay stage is listed among the unavailable stages it explains.
    ua = next(r for r in outcome.recommendations if r.category == "unavailable_analysis")
    assert "replay" in ua.slots["unavailable_stages"]
