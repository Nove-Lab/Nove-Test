"""W1/S8 exit & error-code contract tests (ORC-03 / ORC-04 / ORC-23).

Pins the wire-contract honesty of the two execution verbs:

- **ORC-03** — ``EngineNotReadyError`` envelopes carry the readiness state
  as the COMPLETE error-code token (``engine-missing`` /
  ``engine-misconfigured``), never the doubled ``engine-engine-*`` prefix
  the old ``f"engine-{state}"`` projection emitted.
- **ORC-04** — ``status == "errored"`` is a persisted USER result:
  ``(ok=True, exit 3)``, same class as ``failed`` — for BOTH verbs, via
  the single shared ``cli/output.py::run_status_to_ok_exit`` helper.
- **ORC-23** — the markerless execution branch (pin-less legacy store,
  no engine marker at the anchor — orchestration's
  ``WorkspaceEngineUndetectedError``) maps to the D7 standard
  ``no-engine-detected`` token, matching ``init`` / ``reset``.

The verb handlers are exercised through the real ``cli/app.py`` functions
with the orchestration workflow monkeypatched (no subprocess); the
subprocess-level end-to-end contract lives in
``tests/integration/orchestration/test_exit_error_code_contract.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import novetest.cli.handlers.test as test_handler_module
from novetest.cli import _shared
from novetest.cli import app as app_module
from novetest.cli.handlers import run as run_handler
from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_USER_TESTS_FAILED,
    OutputMode,
    run_status_to_ok_exit,
)
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.orchestration.anchor_resolution import WorkspaceEngineUndetectedError
from novetest.orchestration.recommendation import FactBundle, StageEligibility
from novetest.orchestration.workflows.run import RunOutcome
from novetest.orchestration.workflows.test import TestOutcome
from novetest.run import (
    EngineNotReadyError,
    EngineReadinessResult,
    NativeEngineContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory_entry(status: str) -> MemoryEntry:
    ref = RunReference(run_id="01TESTTESTTESTTESTTESTTEST", created_at=1)
    record = RunRecord(
        run_reference=ref,
        target_expression="",
        target_type="auto",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=1,
        completed_at=2,
        summary_counts={"passed": 0, "total": 0},
    )
    return MemoryEntry(
        entry_id=ref.run_id,
        run_record=record,
        stored_at=3,
        has_coverage_facts=False,
    )


def _make_run_outcome(status: str) -> RunOutcome:
    return RunOutcome(
        memory_entry=_make_memory_entry(status),
        artifact_dir=Path("/tmp/stub"),
        coverage_outcome=None,
    )


def _make_test_outcome(status: str) -> TestOutcome:
    entry = _make_memory_entry(status)
    elig = StageEligibility(
        coverage="not_applicable",
        regression="not_applicable",
        localization="unavailable",
        replay="not_run",
        per_stage_reasons={
            "coverage": None,
            "regression": None,
            "localization": "no-failed-tests",
            "replay": "replay_not_run",
        },
    )
    bundle = FactBundle(
        run_reference=entry.run_record.run_reference,
        run_record=entry.run_record,
        stage_eligibility=elig,
        coverage_facts=None,
        regression_facts=None,
        localization_findings=None,
        replay_results=(),
    )
    return TestOutcome(
        memory_entry=entry,
        artifact_dir=Path("/tmp/stub"),
        stage_eligibility=elig,
        fact_bundle=bundle,
        recommendations=[],
        run_record_status=status,
    )


def _readiness(state: str, *, with_context: bool) -> EngineReadinessResult:
    return EngineReadinessResult(
        state=state,
        engine_context=(
            NativeEngineContext(ecosystem="python", engine_name="pytest")
            if with_context
            else None
        ),
        evidence=(),
        issues=("stubbed readiness issue",),
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(run_handler, "_require_store", lambda _cmd: sentinel)
    monkeypatch.setattr(test_handler_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


def _patch_run_workflow_raise(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
        raise exc

    monkeypatch.setattr(run_handler, "run_target_in_store", fake_workflow)


def _patch_test_workflow_raise(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> TestOutcome:
        raise exc

    monkeypatch.setattr(test_handler_module, "test_target_in_store", fake_workflow)


def _assert_no_doubled_prefix(payload: dict[str, Any]) -> None:
    """Exit criterion #1: no emitted error code carries `engine-engine-`."""
    for error in payload["errors"]:
        assert not error["code"].startswith("engine-engine-"), error["code"]


# ---------------------------------------------------------------------------
# ORC-04 — the single shared status→(ok, exit) mapping
# ---------------------------------------------------------------------------


class TestRunStatusToOkExit:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("passed", (True, EXIT_OK)),
            ("failed", (True, EXIT_USER_TESTS_FAILED)),
            ("errored", (True, EXIT_USER_TESTS_FAILED)),
            # Defensive else — out-of-vocabulary means an upstream bug.
            ("bogus-status", (False, EXIT_GENERIC)),
        ],
    )
    def test_mapping(self, status: str, expected: tuple[bool, int]) -> None:
        assert run_status_to_ok_exit(status) == expected

    def test_errored_never_reaches_the_defensive_branch(self) -> None:
        ok, exit_code = run_status_to_ok_exit("errored")
        assert ok is True
        assert exit_code == EXIT_USER_TESTS_FAILED


# ---------------------------------------------------------------------------
# ORC-04 — run/test symmetry: one helper, identical classification
# ---------------------------------------------------------------------------


class TestRunTestSymmetry:
    @pytest.mark.parametrize(
        "status", ["passed", "failed", "errored", "bogus-status"]
    )
    def test_run_and_test_classify_identically(
        self,
        status: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        """Same status in → identical (ok, exit) out of BOTH verbs."""

        async def fake_run_workflow(
            target: str, store: Any, **kwargs: Any
        ) -> RunOutcome:
            return _make_run_outcome(status)

        monkeypatch.setattr(run_handler, "run_target_in_store", fake_run_workflow)
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        run_exit = exc_info.value.code
        run_ok = _captured_envelope(capsys)["ok"]

        test_envelope, test_exit = build_test_envelope(_make_test_outcome(status))

        assert (run_ok, run_exit) == (test_envelope.ok, test_exit)
        assert (test_envelope.ok, test_exit) == run_status_to_ok_exit(status)

    def test_both_verbs_route_through_the_shared_helper(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        """Monkeypatching the ONE helper redirects BOTH verbs — proof the
        (ok, exit) pair is derived from the single shared definition."""

        sentinel_pair = (True, 42)
        monkeypatch.setattr(
            run_handler, "run_status_to_ok_exit", lambda _status: sentinel_pair
        )
        monkeypatch.setattr(
            test_handler_module,
            "run_status_to_ok_exit",
            lambda _status: sentinel_pair,
        )

        async def fake_run_workflow(
            target: str, store: Any, **kwargs: Any
        ) -> RunOutcome:
            return _make_run_outcome("passed")

        monkeypatch.setattr(run_handler, "run_target_in_store", fake_run_workflow)
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        assert exc_info.value.code == 42
        capsys.readouterr()  # drain

        _, test_exit = build_test_envelope(_make_test_outcome("passed"))
        assert test_exit == 42


# ---------------------------------------------------------------------------
# ORC-03 — readiness states are complete tokens (no doubled prefix)
# ---------------------------------------------------------------------------


class TestEngineNotReadyCodeTokens:
    @pytest.mark.parametrize(
        ("state", "with_context"),
        [("engine-missing", False), ("engine-misconfigured", True)],
    )
    def test_run_emits_readiness_state_verbatim(
        self,
        state: str,
        with_context: bool,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        _patch_run_workflow_raise(
            monkeypatch,
            EngineNotReadyError(_readiness(state, with_context=with_context)),
        )
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        assert exc_info.value.code == EXIT_ENGINE_MISSING

        payload = _captured_envelope(capsys)
        assert payload["ok"] is False
        assert payload["errors"][0]["code"] == state
        assert payload["data"]["engine_readiness"]["state"] == state
        _assert_no_doubled_prefix(payload)

    @pytest.mark.parametrize(
        ("state", "with_context"),
        [("engine-missing", False), ("engine-misconfigured", True)],
    )
    def test_test_emits_readiness_state_verbatim(
        self,
        state: str,
        with_context: bool,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        _patch_test_workflow_raise(
            monkeypatch,
            EngineNotReadyError(_readiness(state, with_context=with_context)),
        )
        with pytest.raises(SystemExit) as exc_info:
            app_module.test_cmd("")
        assert exc_info.value.code == EXIT_ENGINE_MISSING

        payload = _captured_envelope(capsys)
        assert payload["ok"] is False
        assert payload["errors"][0]["code"] == state
        assert payload["data"]["engine_readiness"]["state"] == state
        _assert_no_doubled_prefix(payload)


# ---------------------------------------------------------------------------
# ORC-23 — markerless execution branch emits the D7 standard token
# ---------------------------------------------------------------------------


class TestMarkerlessD7Token:
    def test_run_markerless_maps_to_no_engine_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        _patch_run_workflow_raise(
            monkeypatch,
            WorkspaceEngineUndetectedError(
                _readiness("engine-missing", with_context=False)
            ),
        )
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        assert exc_info.value.code == EXIT_ENGINE_MISSING

        payload = _captured_envelope(capsys)
        assert payload["errors"][0]["code"] == "no-engine-detected"
        # The carried readiness stays within run's three-state vocabulary.
        assert payload["data"]["engine_readiness"]["state"] == "engine-missing"
        _assert_no_doubled_prefix(payload)

    def test_test_markerless_maps_to_no_engine_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        _patch_test_workflow_raise(
            monkeypatch,
            WorkspaceEngineUndetectedError(
                _readiness("engine-missing", with_context=False)
            ),
        )
        with pytest.raises(SystemExit) as exc_info:
            app_module.test_cmd("")
        assert exc_info.value.code == EXIT_ENGINE_MISSING

        payload = _captured_envelope(capsys)
        assert payload["errors"][0]["code"] == "no-engine-detected"
        assert payload["data"]["engine_readiness"]["state"] == "engine-missing"
        _assert_no_doubled_prefix(payload)


# ---------------------------------------------------------------------------
# ORC-04 — errored run through the run verb handler
# ---------------------------------------------------------------------------


class TestErroredRunClassification:
    def test_run_errored_is_a_user_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
            return _make_run_outcome("errored")

        monkeypatch.setattr(run_handler, "run_target_in_store", fake_workflow)
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        assert exc_info.value.code == EXIT_USER_TESTS_FAILED

        payload = _captured_envelope(capsys)
        assert payload["ok"] is True
        assert payload["errors"] == []
        record = payload["data"]["memory_entry"]["run_record"]
        assert record["status"] == "errored"
