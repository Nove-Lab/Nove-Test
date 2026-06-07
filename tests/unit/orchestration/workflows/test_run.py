"""Unit tests for the `run_target_in_store` workflow.

Focused on the orchestration wiring (Coverage derive hook, RunOutcome
shape, kwarg pass-through) — not the underlying engines. The seam mocked
here is the `derive_coverage_facts` import inside
`novetest.orchestration.workflows.run`, so we observe the call without
touching the filesystem-resident native payload that the real Coverage
engine consumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_NATIVE_PAYLOAD
from novetest.memory import create_project_store
from novetest.models import RunRecord, RunReference
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
)
from novetest.orchestration.workflows import run as run_workflow_module
from novetest.orchestration.workflows.run import RunOutcome, run_target_in_store


# ---------------------------------------------------------------------------
# Helpers — synthetic stand-ins so the unit tests never spawn pytest.
# ---------------------------------------------------------------------------


def _make_run_record(*, run_id: str = "01TESTTESTTESTTESTTESTTEST") -> RunRecord:
    ref = RunReference(run_id=run_id, created_at=1_700_000_000_000)
    return RunRecord(
        run_reference=ref,
        target_expression="",
        target_type="auto",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=1_700_000_000_000,
        completed_at=1_700_000_000_100,
        summary_counts={"passed": 1, "total": 1},
        artifact_paths={"pytest_json_report": "stub.json"},
    )


def _make_summary() -> CoverageSummary:
    return CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=80.0,
    )


def _make_fact_set(ref: RunReference) -> CoverageFactSet:
    return CoverageFactSet(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_make_summary(),
        files=(),
        derived_at=1_700_000_000_500,
    )


@pytest.fixture
def store(tmp_path: Path) -> Any:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return create_project_store(workspace)


@pytest.fixture
def stub_execute(monkeypatch: pytest.MonkeyPatch):
    """Stub `execute` so calls observe the kwarg without spawning pytest."""

    captured: dict[str, Any] = {}

    async def fake_execute(
        test_target: Any,
        *,
        artifact_dir: Path,
        run_id: str | None = None,
        timeout: float | None = 600.0,
        collect_coverage: bool = False,
    ) -> tuple[RunRecord, tuple[Any, ...]]:
        captured["collect_coverage"] = collect_coverage
        captured["artifact_dir"] = artifact_dir
        captured["run_id"] = run_id
        # The workflow expects artifact paths it can `relative_to(store.path)`.
        # We rebuild that on the fly here.
        artifact_dir.mkdir(parents=True, exist_ok=True)
        native_dir = artifact_dir / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "pytest-report.json"
        report_path.write_text("{}", encoding="utf-8")
        ref = RunReference(
            run_id=run_id or "01TESTTESTTESTTESTTESTTEST",
            created_at=1_700_000_000_000,
        )
        # Per 2026-06-06 envelope-warnings-projection slice, ``execute``
        # returns ``(RunRecord, adapter_warnings)``; stub a pytest-shaped
        # record with zero warnings (pytest emits none today).
        record = RunRecord(
            run_reference=ref,
            target_expression="",
            target_type=getattr(test_target, "target_type", "auto"),
            engine_name="pytest",
            ecosystem="python",
            status="passed",
            started_at=1_700_000_000_000,
            completed_at=1_700_000_000_100,
            summary_counts={"passed": 1, "total": 1},
            artifact_paths={"pytest_json_report": str(report_path)},
        )
        return record, ()

    monkeypatch.setattr(run_workflow_module, "execute", fake_execute)
    return captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_collect_coverage_false_does_not_invoke_derive(
    store: Any, stub_execute: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase-1 default behavior: no derive, no coverage_outcome on RunOutcome."""

    derive_calls: list[Any] = []

    def fake_derive(_store: Any, ref: RunReference) -> Any:
        derive_calls.append(ref)
        raise AssertionError("derive must not be called when collect_coverage=False")

    monkeypatch.setattr(run_workflow_module, "derive_coverage_facts", fake_derive)

    outcome = await run_target_in_store("", store)
    assert isinstance(outcome, RunOutcome)
    assert outcome.coverage_outcome is None
    assert stub_execute["collect_coverage"] is False
    assert derive_calls == []


async def test_collect_coverage_true_invokes_derive_with_persisted_run_reference(
    store: Any, stub_execute: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`derive_coverage_facts` is called with the just-persisted RunReference."""

    seen_refs: list[RunReference] = []

    def fake_derive(_store: Any, ref: RunReference) -> CoverageFactSet:
        seen_refs.append(ref)
        return _make_fact_set(ref)

    monkeypatch.setattr(run_workflow_module, "derive_coverage_facts", fake_derive)

    outcome = await run_target_in_store("", store, collect_coverage=True)
    assert stub_execute["collect_coverage"] is True
    assert len(seen_refs) == 1
    assert seen_refs[0].run_id == outcome.memory_entry.run_record.run_reference.run_id
    assert isinstance(outcome.coverage_outcome, CoverageFactSet)
    assert outcome.coverage_outcome.mapping_granularity == "per-test"


async def test_coverage_unavailable_outcome_is_forwarded(
    store: Any, stub_execute: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-COV-004: unavailable is a value, not an exception, and it flows up."""

    def fake_derive(_store: Any, ref: RunReference) -> CoverageUnavailable:
        return CoverageUnavailable(
            reason=REASON_MISSING_NATIVE_PAYLOAD,
            detail="stub: no native payload",
            run_reference=ref,
        )

    monkeypatch.setattr(run_workflow_module, "derive_coverage_facts", fake_derive)

    outcome = await run_target_in_store("", store, collect_coverage=True)
    assert isinstance(outcome.coverage_outcome, CoverageUnavailable)
    assert outcome.coverage_outcome.reason == REASON_MISSING_NATIVE_PAYLOAD
    # Memory entry is still returned; the run itself succeeded.
    assert outcome.memory_entry.run_record.status == "passed"
