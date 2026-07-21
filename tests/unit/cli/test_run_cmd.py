"""Unit tests for the `novetest run` CLI handler.

Covers the orchestration-to-envelope projection that lives in the handler
itself: the `--coverage` / `-c` flag routes through to
`run_target_in_store(collect_coverage=True)`, and the `coverage_outcome`
on the returned `RunOutcome` is projected onto the envelope's wire shape
with the documented ``kind`` discriminator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli.handlers import run as app_module
from novetest.cli.output import OutputMode
from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_NATIVE_PAYLOAD
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.coverage_fact_set import CoverageFactSet, CoverageSummary
from novetest.orchestration.workflows.run import RunOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory_entry(*, has_coverage: bool = False) -> MemoryEntry:
    ref = RunReference(run_id="01TESTTESTTESTTESTTESTTEST", created_at=1)
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
    return MemoryEntry(
        entry_id=ref.run_id,
        run_record=record,
        stored_at=3,
        has_coverage_facts=has_coverage,
    )


def _make_fact_set() -> CoverageFactSet:
    ref = RunReference(run_id="01TESTTESTTESTTESTTESTTEST", created_at=1)
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=CoverageSummary(
            num_statements=10,
            covered_statements=8,
            missing_statements=2,
            excluded_statements=0,
            num_branches=2,
            covered_branches=1,
            missing_branches=1,
            percent_covered=80.0,
        ),
        files=(),
        derived_at=4,
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the active envelope mode so capsys sees a JSON-shaped envelope."""

    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


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
# Tests
# ---------------------------------------------------------------------------


def test_run_without_coverage_omits_coverage_outcome_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    seen_kwargs: dict[str, Any] = {}

    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
        seen_kwargs["target"] = target
        seen_kwargs["store"] = store
        seen_kwargs.update(kwargs)
        return RunOutcome(
            memory_entry=_make_memory_entry(),
            artifact_dir=Path("/tmp/stub"),
            coverage_outcome=None,
        )

    monkeypatch.setattr(app_module, "run_target_in_store", fake_workflow)

    with pytest.raises(SystemExit) as exc_info:
        app_module.run_cmd("tests/")
    assert exc_info.value.code == 0
    assert seen_kwargs["collect_coverage"] is False
    assert seen_kwargs["target"] == "tests/"

    payload = _captured_envelope(capsys)
    assert payload["command"] == "run"
    assert payload["ok"] is True
    data = payload["data"]
    assert "memory_entry" in data
    # NOT a null — the key must be absent so Phase 1 wire stays unchanged.
    assert "coverage_outcome" not in data


def test_run_with_coverage_emits_fact_set_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    seen_kwargs: dict[str, Any] = {}

    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
        seen_kwargs.update(kwargs)
        return RunOutcome(
            memory_entry=_make_memory_entry(has_coverage=True),
            artifact_dir=Path("/tmp/stub"),
            coverage_outcome=_make_fact_set(),
        )

    monkeypatch.setattr(app_module, "run_target_in_store", fake_workflow)

    with pytest.raises(SystemExit) as exc_info:
        app_module.run_cmd("", coverage=True)
    assert exc_info.value.code == 0
    assert seen_kwargs["collect_coverage"] is True

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["coverage_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["mapping_granularity"] == "per-test"
    assert outcome["summary"]["percent_covered"] == 80.0
    assert outcome["run_reference"]["run_id"] == "01TESTTESTTESTTESTTESTTEST"


def test_run_with_coverage_emits_unavailable_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
        return RunOutcome(
            memory_entry=_make_memory_entry(),
            artifact_dir=Path("/tmp/stub"),
            coverage_outcome=CoverageUnavailable(
                reason=REASON_MISSING_NATIVE_PAYLOAD,
                detail="stub: no payload",
                run_reference=RunReference(
                    run_id="01TESTTESTTESTTESTTESTTEST", created_at=1
                ),
            ),
        )

    monkeypatch.setattr(app_module, "run_target_in_store", fake_workflow)

    with pytest.raises(SystemExit) as exc_info:
        app_module.run_cmd("", coverage=True)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["coverage_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_MISSING_NATIVE_PAYLOAD
    assert outcome["detail"] == "stub: no payload"
    assert outcome["run_reference"]["run_id"] == "01TESTTESTTESTTESTTESTTEST"
