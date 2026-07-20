"""Unit tests for the `novetest regression compare` CLI handler.

Covers the orchestration-to-envelope projection: lookup → engine call →
envelope projection. The Regression engine seam (`compare_runs`) and the
Memory run_id lookup (`find_entry_by_run_id`, the single S18 predicate) are
monkeypatched at the `cli.app` module so the unit tests never touch the
filesystem. Envelopes are captured via
`capsys` (per the inspect/coverage slices' gotcha — fighting pytest's own
stdout capture with a second monkeypatch leads to silently empty buffers).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.regression_fact_set import (
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
    TestTransition,
)
from novetest.regression import (
    REASON_ENGINE_MISMATCH,
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_TOMBSTONED,
    REASON_TARGET_MISMATCH,
    RegressionUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BASELINE_ID = "01BASELINETESTTESTTESTTEST"
_TARGET_ID = "01TARGETTESTTESTTESTTESTTE"


def _make_memory_entry(run_id: str, *, created_at: int = 1) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=created_at,
        completed_at=created_at + 1,
        summary_counts={"passed": 1, "total": 1},
    )
    return MemoryEntry(entry_id=ref.run_id, run_record=record, stored_at=created_at + 2)


def _make_summary(**overrides: int) -> RegressionSummary:
    defaults: dict[str, int] = {
        "regressed": 0,
        "fixed": 1,
        "still_failing": 0,
        "still_passing": 12,
        "still_skipped": 0,
        "newly_skipped": 0,
        "newly_active": 0,
        "added": 1,
        "removed": 0,
        "total_baseline_tests": 13,
        "total_target_tests": 14,
    }
    defaults.update(overrides)
    return RegressionSummary(**defaults)


def _make_fact_set(
    *,
    baseline_id: str = _BASELINE_ID,
    target_id: str = _TARGET_ID,
    derived_at: int = 4,
) -> RegressionFactSet:
    baseline_ref = RunReference(run_id=baseline_id, created_at=1)
    target_ref = RunReference(run_id=target_id, created_at=2)
    transitions = (
        TestTransition(
            node_id="tests/x.py::test_a",
            category="fixed",
            baseline_outcome="failed",
            target_outcome="passed",
            baseline_failure_reference=None,
            target_failure_reference=None,
            baseline_duration_ms=12,
            target_duration_ms=9,
        ),
    )
    return RegressionFactSet(
        baseline_run_reference=baseline_ref,
        target_run_reference=target_ref,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=derived_at,
        summary=_make_summary(),
        test_transitions=transitions,
        output_diff=OutputDiffRecord(
            baseline_stdout_sha256="abc",
            target_stdout_sha256="def",
            baseline_stderr_sha256=None,
            target_stderr_sha256=None,
            stdout_identical=False,
            stderr_identical=True,
            baseline_stdout_path="run/artifacts/run_b/native/stdout.log",
            target_stdout_path="run/artifacts/run_t/native/stdout.log",
            baseline_stderr_path=None,
            target_stderr_path=None,
        ),
        coverage_change=None,
        warnings=(),
        metadata={},
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


@pytest.fixture
def stub_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the S18 run_id lookup (`find_entry_by_run_id`) to resolve both the
    baseline and target entries so `_resolve_run_reference` succeeds for both
    IDs."""

    entries = [_make_memory_entry(_BASELINE_ID), _make_memory_entry(_TARGET_ID)]
    monkeypatch.setattr(
        app_module,
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
# Happy path + envelope projection
# ---------------------------------------------------------------------------


def test_regression_compare_emits_fact_set_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    seen_args: list[tuple[RunReference, RunReference]] = []

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> RegressionFactSet:
        seen_args.append((baseline, target))
        return _make_fact_set()

    monkeypatch.setattr(app_module, "compare_runs", fake_compare)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_compare(_BASELINE_ID, _TARGET_ID)
    assert exc_info.value.code == 0
    # Argument order is load-bearing (decision §2): baseline first.
    assert seen_args == [
        (
            RunReference(run_id=_BASELINE_ID, created_at=1),
            RunReference(run_id=_TARGET_ID, created_at=1),
        )
    ]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "regression.compare"
    assert payload["ok"] is True
    outcome = payload["data"]["regression_outcome"]
    assert outcome["kind"] == "fact-set"
    # Envelope projection strips the persisted schema_version (envelope-level
    # `schema` already carries the version).
    assert "schema_version" not in outcome
    # All 9 summary categories + 2 totals = 11 keys per decision §3.
    assert len(outcome["summary"]) == 11
    assert outcome["summary"]["regressed"] == 0
    assert outcome["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert outcome["target_run_reference"]["run_id"] == _TARGET_ID
    assert outcome["baseline_engine_name"] == "pytest"
    assert outcome["target_engine_name"] == "pytest"
    assert isinstance(outcome["test_transitions"], list)
    assert outcome["test_transitions"][0]["node_id"] == "tests/x.py::test_a"
    assert outcome["test_transitions"][0]["category"] == "fixed"
    assert outcome["warnings"] == []
    assert outcome["metadata"] == {}


def test_regression_compare_cache_hit_path_preserves_derived_at(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A cache hit returns the same `derived_at` (the engine reads the same
    file). Two CLI calls projecting the same outcome → identical
    `derived_at` on the wire."""

    fixed_fact_set = _make_fact_set(derived_at=12345)
    monkeypatch.setattr(
        app_module, "compare_runs", lambda *_a, **_k: fixed_fact_set
    )

    derived_values: list[int] = []
    for _ in range(2):
        with pytest.raises(SystemExit):
            app_module.regression_compare(_BASELINE_ID, _TARGET_ID)
        payload = _captured_envelope(capsys)
        derived_values.append(payload["data"]["regression_outcome"]["derived_at"])
    assert derived_values == [12345, 12345]


# ---------------------------------------------------------------------------
# Unavailable propagation — exit 0, ok=true, data discriminator flips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason,detail",
    [
        (REASON_RUN_TOMBSTONED, "baseline"),
        (REASON_RUN_TOMBSTONED, "target"),
        (REASON_ENGINE_MISMATCH, "baseline engine_name='pytest' != target engine_name='jest'"),
        (REASON_TARGET_MISMATCH, "baseline target_expression='tests/' != target target_expression='other/'"),
    ],
)
def test_regression_compare_propagates_each_unavailable_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    reason: str,
    detail: str,
) -> None:
    baseline_ref = RunReference(run_id=_BASELINE_ID, created_at=1)
    target_ref = RunReference(run_id=_TARGET_ID, created_at=1)

    def fake_compare(
        _store: Any, baseline: RunReference, target: RunReference
    ) -> RegressionUnavailable:
        return RegressionUnavailable(
            reason=reason,
            detail=detail,
            baseline_run_reference=baseline,
            target_run_reference=target,
        )

    monkeypatch.setattr(app_module, "compare_runs", fake_compare)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_compare(_BASELINE_ID, _TARGET_ID)
    # Unavailable is data, not a transport error — exit 0, ok=true.
    assert exc_info.value.code == 0
    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["regression_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == reason
    assert outcome["detail"] == detail
    # Both references are populated — the consumer needs to know which side
    # is which (richer than Coverage's single-`run_reference` Unavailable).
    assert outcome["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert outcome["target_run_reference"]["run_id"] == _TARGET_ID


def test_regression_compare_tombstone_overrides_cache_per_decision_c1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Decision §C.1: when ``compare_runs`` returns ``REASON_RUN_TOMBSTONED``,
    the CLI surfaces it directly — even if the underlying cache file exists
    on disk. The CLI layer takes the engine's word as authoritative."""

    monkeypatch.setattr(
        app_module,
        "compare_runs",
        lambda _s, b, t: RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail="target",
            baseline_run_reference=b,
            target_run_reference=t,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_compare(_BASELINE_ID, _TARGET_ID)
    assert exc_info.value.code == 0
    outcome = _captured_envelope(capsys)["data"]["regression_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_TOMBSTONED
    assert outcome["detail"] == "target"


def test_regression_compare_unavailable_with_no_refs_carries_nulls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A `RegressionUnavailable` whose run references are both `None` (rare
    but valid per the dataclass default) projects them as JSON `null` —
    the field is present but explicitly null, mirroring Coverage's pattern."""

    monkeypatch.setattr(
        app_module,
        "compare_runs",
        lambda *_a, **_k: RegressionUnavailable(
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="defensive",
        ),
    )

    with pytest.raises(SystemExit):
        app_module.regression_compare(_BASELINE_ID, _TARGET_ID)
    outcome = _captured_envelope(capsys)["data"]["regression_outcome"]
    assert outcome["baseline_run_reference"] is None
    assert outcome["target_run_reference"] is None


# ---------------------------------------------------------------------------
# Not-found short-circuit — exit 2, structured error envelope
# ---------------------------------------------------------------------------


def test_regression_compare_returns_not_found_for_fake_baseline_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """A typo'd baseline_run_id short-circuits at `_resolve_run_reference`
    BEFORE `compare_runs` is called — returns the not-found envelope with
    exit 2, mirroring `coverage diff`."""

    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, run_id, *, skipped=None: None,
    )

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("compare_runs called when baseline lookup failed")

    monkeypatch.setattr(app_module, "compare_runs", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_compare("fake-baseline", _TARGET_ID)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "regression.compare"
    assert payload["errors"][0]["code"] == "not-found"


def test_regression_compare_returns_not_found_for_fake_target_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """The target side is checked AFTER the baseline — both must resolve
    for the engine call to fire."""

    baseline_only = [_make_memory_entry(_BASELINE_ID)]
    monkeypatch.setattr(
        app_module,
        "find_entry_by_run_id",
        lambda _store, run_id, *, skipped=None: next(
            (e for e in baseline_only if e.run_record.run_reference.run_id == run_id),
            None,
        ),
    )

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("compare_runs called when target lookup failed")

    monkeypatch.setattr(app_module, "compare_runs", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_compare(_BASELINE_ID, "fake-target")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "regression.compare"
    assert payload["errors"][0]["code"] == "not-found"
