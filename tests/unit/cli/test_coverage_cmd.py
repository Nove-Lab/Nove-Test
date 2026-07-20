"""Unit tests for the `novetest coverage show` / `coverage diff` handlers.

Covers the orchestration-to-envelope projection for the two coverage
verbs: lookup → engine call → envelope projection. The Coverage engine
seams (`get_coverage_facts`, `compare_coverage_facts`) and the Memory run_id
lookup (`find_entry_by_run_id`, the single S18 predicate) are monkeypatched
so the unit tests never touch the
filesystem; envelopes are captured via pytest's `capsys` (per the prior
slice's gotcha — fighting pytest's own stdout capture with a second
monkeypatch leads to silently empty buffers).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.coverage import CoverageUnavailable
from novetest.coverage.compare import CoverageDelta, FileCoverageDelta
from novetest.coverage.results import (
    REASON_MISSING_DERIVED_FACTS,
)
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(percent: float = 80.0) -> CoverageSummary:
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


def _make_memory_entry(run_id: str = "01TESTTESTTESTTESTTESTTEST") -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=1)
    record = RunRecord(
        run_reference=ref,
        target_expression="",
        target_type="auto",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1,
        completed_at=2,
        summary_counts={"passed": 1, "total": 1},
    )
    return MemoryEntry(entry_id=ref.run_id, run_record=record, stored_at=3)


def _make_fact_set(run_id: str = "01TESTTESTTESTTESTTESTTEST") -> CoverageFactSet:
    ref = RunReference(run_id=run_id, created_at=1)
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_make_summary(),
        files=(),
        derived_at=4,
    )


def _make_delta(
    baseline_id: str = "01BASELINETESTTESTTESTTEST",
    target_id: str = "01TARGETTESTTESTTESTTESTTE",
) -> CoverageDelta:
    return CoverageDelta(
        baseline_run_reference=RunReference(run_id=baseline_id, created_at=1),
        target_run_reference=RunReference(run_id=target_id, created_at=2),
        baseline_granularity="per-test",
        target_granularity="per-test",
        summary_before=_make_summary(percent=70.0),
        summary_after=_make_summary(percent=90.0),
        files_added=("new_file.py",),
        files_removed=(),
        file_deltas=(
            FileCoverageDelta(
                file_path="changed_file.py",
                newly_covered_lines=(5, 7),
                newly_uncovered_lines=(),
                newly_covered_branches=(),
                newly_uncovered_branches=(),
                summary_before=_make_summary(percent=70.0),
                summary_after=_make_summary(percent=90.0),
            ),
        ),
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


# ---------------------------------------------------------------------------
# coverage show
# ---------------------------------------------------------------------------


def test_show_emits_fact_set_when_facts_present(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    run_id = "01TESTTESTTESTTESTTESTTEST"
    entry = _make_memory_entry(run_id)
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: entry if rid == run_id else None,
    )
    seen_ref: list[RunReference] = []

    def fake_get(_store: Any, ref: RunReference) -> CoverageFactSet:
        seen_ref.append(ref)
        return _make_fact_set(run_id)

    monkeypatch.setattr(app_module, "get_coverage_facts", fake_get)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show(run_id)
    assert exc_info.value.code == 0
    assert seen_ref and seen_ref[0].run_id == run_id

    payload = _captured_envelope(capsys)
    assert payload["command"] == "coverage.show"
    assert payload["ok"] is True
    outcome = payload["data"]["coverage_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["mapping_granularity"] == "per-test"
    assert outcome["summary"]["percent_covered"] == 80.0
    assert outcome["run_reference"]["run_id"] == run_id


def test_show_emits_unavailable_when_facts_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Run exists, but `coverage_facts.json` does not — this is the
    REQ-COV-004 unavailable branch surfaced at the CLI for the first time.
    """
    run_id = "01TESTTESTTESTTESTTESTTEST"
    entry = _make_memory_entry(run_id)
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: entry if rid == run_id else None,
    )

    def fake_get(_store: Any, ref: RunReference) -> CoverageUnavailable:
        return CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="No coverage_facts.json found for this run",
            run_reference=ref,
        )

    monkeypatch.setattr(app_module, "get_coverage_facts", fake_get)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show(run_id)
    # The verb itself succeeded; the *outcome* is unavailable.
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["coverage_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_MISSING_DERIVED_FACTS
    assert outcome["run_reference"]["run_id"] == run_id


def test_show_returns_not_found_for_unknown_run_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Mirror the `memory show` not-found pattern: exit 2, structured envelope."""
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: None,
    )

    # If lookup fails, `get_coverage_facts` MUST NOT be called.
    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("get_coverage_facts called for an unknown run_id")

    monkeypatch.setattr(app_module, "get_coverage_facts", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_show("fake-id")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "coverage.show"
    assert payload["errors"][0]["code"] == "not-found"


# ---------------------------------------------------------------------------
# coverage diff
# ---------------------------------------------------------------------------


def test_diff_emits_delta_when_both_runs_have_facts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    baseline_id = "01BASELINETESTTESTTESTTEST"
    target_id = "01TARGETTESTTESTTESTTESTTE"
    entries = [_make_memory_entry(baseline_id), _make_memory_entry(target_id)]
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: next(
            (e for e in entries if e.run_record.run_reference.run_id == rid),
            None,
        ),
    )

    seen_args: list[tuple[RunReference, RunReference]] = []

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> CoverageDelta:
        seen_args.append((baseline, target))
        return _make_delta(baseline_id, target_id)

    monkeypatch.setattr(app_module, "compare_coverage_facts", fake_compare)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_diff(baseline_id, target_id)
    assert exc_info.value.code == 0
    assert seen_args == [
        (
            RunReference(run_id=baseline_id, created_at=1),
            RunReference(run_id=target_id, created_at=1),
        )
    ]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "coverage.diff"
    assert payload["ok"] is True
    delta = payload["data"]["coverage_delta"]
    assert delta["kind"] == "delta"
    assert delta["baseline_run_reference"]["run_id"] == baseline_id
    assert delta["target_run_reference"]["run_id"] == target_id
    assert delta["baseline_granularity"] == "per-test"
    assert delta["target_granularity"] == "per-test"
    assert delta["summary_before"]["percent_covered"] == 70.0
    assert delta["summary_after"]["percent_covered"] == 90.0
    assert delta["files_added"] == ["new_file.py"]
    assert delta["files_removed"] == []
    assert len(delta["file_deltas"]) == 1
    assert delta["file_deltas"][0]["file_path"] == "changed_file.py"
    assert delta["file_deltas"][0]["newly_covered_lines"] == [5, 7]
    # Envelope projection strips the persisted schema_version (envelope-level
    # `schema` already carries the version).
    assert "schema_version" not in delta


def test_diff_emits_unavailable_when_one_side_lacks_facts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    baseline_id = "01BASELINETESTTESTTESTTEST"
    target_id = "01TARGETTESTTESTTESTTESTTE"
    entries = [_make_memory_entry(baseline_id), _make_memory_entry(target_id)]
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: next(
            (e for e in entries if e.run_record.run_reference.run_id == rid),
            None,
        ),
    )

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> CoverageUnavailable:
        return CoverageUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="No coverage_facts.json for baseline",
            run_reference=baseline,
        )

    monkeypatch.setattr(app_module, "compare_coverage_facts", fake_compare)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_diff(baseline_id, target_id)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    delta = payload["data"]["coverage_delta"]
    assert delta["kind"] == "unavailable"
    assert delta["reason"] == REASON_MISSING_DERIVED_FACTS
    assert delta["run_reference"]["run_id"] == baseline_id


def test_diff_returns_not_found_when_target_run_id_unknown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    baseline_id = "01BASELINETESTTESTTESTTEST"
    baseline_only = [_make_memory_entry(baseline_id)]
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, rid, *, skipped=None: next(
            (e for e in baseline_only if e.run_record.run_reference.run_id == rid),
            None,
        ),
    )

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("compare_coverage_facts called when target lookup failed")

    monkeypatch.setattr(app_module, "compare_coverage_facts", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.coverage_diff(baseline_id, "fake-target-id")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "coverage.diff"
    assert payload["errors"][0]["code"] == "not-found"
