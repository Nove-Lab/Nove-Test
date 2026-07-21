"""Unit tests for the top-level `novetest compare` CLI handler.

`compare <baseline> <target>` composes two engine calls — `compare_runs`
(Regression) and `compare_coverage_facts` (Coverage) — into one envelope.
Since W2/S23 the synthesis lives in the `build_compare_view` workflow
(`orchestration/workflows/compare.py`), so the engine seams are
monkeypatched at that module; the CLI handler is transport-only
(run_id resolution + envelope projection). Distinct from
`regression compare` (Regression only) and `coverage diff`
(Coverage only).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli.handlers import compare as app_module
from novetest.cli.output import OutputMode
from novetest.coverage import CoverageUnavailable
from novetest.coverage.compare import CoverageDelta, FileCoverageDelta
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.coverage_fact_set import CoverageSummary
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration.workflows import compare as compare_workflow
from novetest.regression import (
    REASON_ENGINE_MISMATCH,
    REASON_RUN_TOMBSTONED,
    RegressionUnavailable,
)


_BASELINE_ID = "01BASELINETESTTESTTESTTEST"
_TARGET_ID = "01TARGETTESTTESTTESTTESTTE"


def _make_memory_entry(run_id: str) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=1)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1,
        completed_at=2,
        summary_counts={"passed": 1, "total": 1},
    )
    return MemoryEntry(entry_id=ref.run_id, run_record=record, stored_at=3)


def _make_coverage_summary(percent: float = 80.0) -> CoverageSummary:
    return CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=percent,
    )


def _make_coverage_delta() -> CoverageDelta:
    return CoverageDelta(
        baseline_run_reference=RunReference(run_id=_BASELINE_ID, created_at=1),
        target_run_reference=RunReference(run_id=_TARGET_ID, created_at=2),
        baseline_granularity="per-test",
        target_granularity="per-test",
        summary_before=_make_coverage_summary(percent=70.0),
        summary_after=_make_coverage_summary(percent=90.0),
        files_added=(),
        files_removed=(),
        file_deltas=(
            FileCoverageDelta(
                file_path="changed.py",
                newly_covered_lines=(5,),
                newly_uncovered_lines=(),
                newly_covered_branches=(),
                newly_uncovered_branches=(),
                summary_before=_make_coverage_summary(percent=70.0),
                summary_after=_make_coverage_summary(percent=90.0),
            ),
        ),
    )


def _make_regression_summary() -> RegressionSummary:
    return RegressionSummary(
        regressed=0,
        fixed=1,
        still_failing=0,
        still_passing=12,
        still_skipped=0,
        newly_skipped=0,
        newly_active=0,
        added=0,
        removed=0,
        total_baseline_tests=13,
        total_target_tests=13,
    )


def _make_regression_fact_set() -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=RunReference(run_id=_BASELINE_ID, created_at=1),
        target_run_reference=RunReference(run_id=_TARGET_ID, created_at=2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=4,
        summary=_make_regression_summary(),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


@pytest.fixture
def stub_history(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [_make_memory_entry(_BASELINE_ID), _make_memory_entry(_TARGET_ID)]
    monkeypatch.setattr(
        _shared,
        "find_entry_by_run_id",
        lambda _store, run_id, *, skipped=None: next(
            (e for e in entries if e.run_record.run_reference.run_id == run_id),
            None,
        ),
    )


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


# ---------------------------------------------------------------------------
# Both blocks succeed
# ---------------------------------------------------------------------------


def test_compare_emits_both_blocks_on_full_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    monkeypatch.setattr(
        compare_workflow, "compare_runs", lambda *_a, **_k: _make_regression_fact_set()
    )
    monkeypatch.setattr(
        compare_workflow, "compare_coverage_facts", lambda *_a, **_k: _make_coverage_delta()
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.compare_cmd(_BASELINE_ID, _TARGET_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["command"] == "compare"
    assert payload["ok"] is True
    data = payload["data"]
    assert set(data.keys()) == {"regression_outcome", "coverage_delta"}
    assert data["regression_outcome"]["kind"] == "fact-set"
    assert data["coverage_delta"]["kind"] == "delta"
    # Both blocks reference the same pair.
    assert data["regression_outcome"]["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert data["coverage_delta"]["baseline_run_reference"]["run_id"] == _BASELINE_ID
    # Coverage block strips schema_version (same convention as `coverage diff`).
    assert "schema_version" not in data["coverage_delta"]


# ---------------------------------------------------------------------------
# Partial unavailability — the two engines decide independently
# ---------------------------------------------------------------------------


def test_compare_with_only_baseline_coverage_emits_coverage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Regression succeeds (test outcomes are sourced from the Run Records,
    which both exist) but Coverage propagates `missing-derived-facts` from
    `compare_coverage_facts` when one side lacks `coverage_facts.json`."""

    monkeypatch.setattr(
        compare_workflow, "compare_runs", lambda *_a, **_k: _make_regression_fact_set()
    )

    def fake_coverage(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> CoverageUnavailable:
        return CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="No coverage_facts.json for target",
            run_reference=target,
        )

    monkeypatch.setattr(compare_workflow, "compare_coverage_facts", fake_coverage)

    with pytest.raises(SystemExit) as exc_info:
        app_module.compare_cmd(_BASELINE_ID, _TARGET_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["data"]["regression_outcome"]["kind"] == "fact-set"
    delta = payload["data"]["coverage_delta"]
    assert delta["kind"] == "unavailable"
    assert delta["reason"] == REASON_MISSING_DERIVED_FACTS


def test_compare_with_neither_side_coverage_still_emits_regression(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Regression doesn't need coverage; the composed envelope still
    carries a full Regression `fact-set` block alongside the Coverage
    `unavailable` block."""

    monkeypatch.setattr(
        compare_workflow, "compare_runs", lambda *_a, **_k: _make_regression_fact_set()
    )
    monkeypatch.setattr(
        compare_workflow,
        "compare_coverage_facts",
        lambda _s, b, t: CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="Neither side has coverage facts",
            run_reference=b,
        ),
    )

    with pytest.raises(SystemExit):
        app_module.compare_cmd(_BASELINE_ID, _TARGET_ID)
    payload = _captured_envelope(capsys)
    assert payload["data"]["regression_outcome"]["kind"] == "fact-set"
    assert payload["data"]["coverage_delta"]["kind"] == "unavailable"


def test_compare_with_tombstoned_target_emits_regression_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Tombstoned target → regression Unavailable; coverage_delta is still
    present (whatever `compare_coverage_facts` returns for the pair —
    typically also unavailable for tombstoned-coverage cases, but the CLI
    composes whichever block each engine produces)."""

    baseline_ref = RunReference(run_id=_BASELINE_ID, created_at=1)
    target_ref = RunReference(run_id=_TARGET_ID, created_at=1)

    monkeypatch.setattr(
        compare_workflow,
        "compare_runs",
        lambda *_a, **_k: RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail="target",
            baseline_run_reference=baseline_ref,
            target_run_reference=target_ref,
        ),
    )
    monkeypatch.setattr(
        compare_workflow,
        "compare_coverage_facts",
        lambda _s, b, t: CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="target tombstoned",
            run_reference=t,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.compare_cmd(_BASELINE_ID, _TARGET_ID)
    assert exc_info.value.code == 0
    payload = _captured_envelope(capsys)
    regression = payload["data"]["regression_outcome"]
    assert regression["kind"] == "unavailable"
    assert regression["reason"] == REASON_RUN_TOMBSTONED
    # `coverage_delta` is always present in the `compare` envelope, even
    # when regression is unavailable — the two engines decide independently.
    assert "coverage_delta" in payload["data"]


def test_compare_with_engine_mismatch_carries_both_unavailable_blocks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Engine-mismatch regression Unavailable + coverage Unavailable both
    surface — `compare` does NOT short-circuit on either engine alone."""

    baseline_ref = RunReference(run_id=_BASELINE_ID, created_at=1)
    target_ref = RunReference(run_id=_TARGET_ID, created_at=1)
    monkeypatch.setattr(
        compare_workflow,
        "compare_runs",
        lambda *_a, **_k: RegressionUnavailable(
            reason=REASON_ENGINE_MISMATCH,
            detail="baseline engine_name='pytest' != target engine_name='jest'",
            baseline_run_reference=baseline_ref,
            target_run_reference=target_ref,
        ),
    )
    monkeypatch.setattr(
        compare_workflow,
        "compare_coverage_facts",
        lambda _s, b, t: CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="cross-engine",
            run_reference=b,
        ),
    )

    with pytest.raises(SystemExit):
        app_module.compare_cmd(_BASELINE_ID, _TARGET_ID)
    payload = _captured_envelope(capsys)
    assert payload["data"]["regression_outcome"]["kind"] == "unavailable"
    assert payload["data"]["regression_outcome"]["reason"] == REASON_ENGINE_MISMATCH
    assert payload["data"]["coverage_delta"]["kind"] == "unavailable"


# ---------------------------------------------------------------------------
# Not-found short-circuit
# ---------------------------------------------------------------------------


def test_compare_returns_not_found_for_fake_baseline_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Both engine calls must short-circuit when either run_id is unknown.
    Mirrors `regression compare` / `coverage diff`."""

    monkeypatch.setattr(
        _shared,
        "find_entry_by_run_id",
        lambda _store, run_id, *, skipped=None: None,
    )

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("engine called when baseline lookup failed")

    monkeypatch.setattr(compare_workflow, "compare_runs", must_not_be_called)
    monkeypatch.setattr(compare_workflow, "compare_coverage_facts", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.compare_cmd("fake-id", _TARGET_ID)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "compare"
    assert payload["errors"][0]["code"] == "not-found"
