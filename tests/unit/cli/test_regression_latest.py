"""Unit tests for the `novetest regression latest` CLI handler.

`regression latest` is a thin wrapper around `derive_latest_regression`:
resolve store → call the engine end-to-end composer → project the outcome
onto the envelope. Most branches live inside the engine; the CLI's only
job is correct projection and store handling.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli.handlers import regression as app_module
from novetest.cli.output import OutputMode
from novetest.models import RunReference
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.regression import (
    REASON_ENGINE_MISMATCH,
    REASON_NO_COMPARABLE_BASELINE,
    RegressionUnavailable,
)


_BASELINE_ID = "01BASELINETESTTESTTESTTEST"
_TARGET_ID = "01TARGETTESTTESTTESTTESTTE"


def _make_summary() -> RegressionSummary:
    return RegressionSummary(
        regressed=0,
        fixed=0,
        still_failing=0,
        still_passing=5,
        still_skipped=0,
        newly_skipped=0,
        newly_active=0,
        added=0,
        removed=0,
        total_baseline_tests=5,
        total_target_tests=5,
    )


def _make_fact_set() -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=RunReference(run_id=_BASELINE_ID, created_at=1),
        target_run_reference=RunReference(run_id=_TARGET_ID, created_at=2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=99,
        summary=_make_summary(),
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


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_regression_latest_emits_fact_set_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    seen_stores: list[Any] = []

    def fake_derive(store: Any) -> RegressionFactSet:
        seen_stores.append(store)
        return _make_fact_set()

    monkeypatch.setattr(app_module, "derive_latest_regression", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_latest()
    assert exc_info.value.code == 0
    # The handler forwards exactly the resolved store sentinel — no
    # transformation between `_require_store` and the engine call.
    assert seen_stores == [stub_store]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "regression.latest"
    assert payload["ok"] is True
    outcome = payload["data"]["regression_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert outcome["target_run_reference"]["run_id"] == _TARGET_ID
    assert "schema_version" not in outcome


def test_regression_latest_propagates_no_runs_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Empty store / all-tombstoned store: `derive_latest_regression`
    returns `REASON_NO_COMPARABLE_BASELINE, detail="no-runs"`. The CLI
    projects that as a unavailable block with exit 0."""

    monkeypatch.setattr(
        app_module,
        "derive_latest_regression",
        lambda _store: RegressionUnavailable(
            reason=REASON_NO_COMPARABLE_BASELINE,
            detail="no-runs",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_latest()
    assert exc_info.value.code == 0
    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["regression_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    assert outcome["detail"] == "no-runs"
    # Both refs null when the engine could not resolve either side.
    assert outcome["baseline_run_reference"] is None
    assert outcome["target_run_reference"] is None


def test_regression_latest_propagates_single_run_target_detail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """When the active target has only one run, the engine's
    `resolve_latest_baseline` returns `REASON_NO_COMPARABLE_BASELINE` with
    `detail=<target_expression>` (NOT `"no-runs"`) per the engine slice's
    pinned gotcha; `derive_latest_regression` propagates that detail
    verbatim. The CLI surfaces it as-is."""

    monkeypatch.setattr(
        app_module,
        "derive_latest_regression",
        lambda _store: RegressionUnavailable(
            reason=REASON_NO_COMPARABLE_BASELINE,
            detail="tests/",
        ),
    )

    with pytest.raises(SystemExit):
        app_module.regression_latest()
    outcome = _captured_envelope(capsys)["data"]["regression_outcome"]
    assert outcome["reason"] == REASON_NO_COMPARABLE_BASELINE
    # The detail is the active target_expression, not "no-runs" — useful
    # operator hint for the "I have only one run for this target" case.
    assert outcome["detail"] == "tests/"


def test_regression_latest_propagates_engine_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """The latest two runs share a target but differ on engine_name (pytest
    → jest). `derive_latest_regression` → `compare_runs` short-circuits
    with `REASON_ENGINE_MISMATCH`; the CLI projection carries both refs."""

    baseline_ref = RunReference(run_id=_BASELINE_ID, created_at=1)
    target_ref = RunReference(run_id=_TARGET_ID, created_at=2)
    monkeypatch.setattr(
        app_module,
        "derive_latest_regression",
        lambda _store: RegressionUnavailable(
            reason=REASON_ENGINE_MISMATCH,
            detail="baseline engine_name='pytest' != target engine_name='jest'",
            baseline_run_reference=baseline_ref,
            target_run_reference=target_ref,
        ),
    )

    with pytest.raises(SystemExit):
        app_module.regression_latest()
    outcome = _captured_envelope(capsys)["data"]["regression_outcome"]
    assert outcome["reason"] == REASON_ENGINE_MISMATCH
    assert outcome["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert outcome["target_run_reference"]["run_id"] == _TARGET_ID


def test_regression_latest_uninitialized_short_circuits_at_store(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    """`regression latest` takes no arguments — the only failure mode at the
    transport layer is "no Project Store". `_require_store` returns the
    `uninitialized` envelope and exits 2 before any engine call fires.
    Asserts the engine call short-circuit, not the envelope content (the
    uninitialized envelope is covered by `_require_store`'s own tests)."""

    def fake_require_store(_cmd: str) -> Any:
        import sys
        from novetest.cli.output import Envelope, EnvelopeError, emit_envelope

        emit_envelope(
            Envelope(
                command="regression.latest",
                ok=False,
                errors=(EnvelopeError(code="uninitialized", message="no store"),),
            ),
            _shared._active_mode,
        )
        sys.exit(2)

    monkeypatch.setattr(app_module, "_require_store", fake_require_store)

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError(
            "derive_latest_regression called when no Project Store"
        )

    monkeypatch.setattr(app_module, "derive_latest_regression", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.regression_latest()
    assert exc_info.value.code == 2
    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "uninitialized"
