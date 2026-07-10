"""Unit tests for the ``novetest test --reruns N`` flag (CLI transport).

``test_cmd`` stays thin: validate the flag, forward ``reruns`` to
``test_target_in_store``, project the outcome via ``build_test_envelope``
(unchanged). The workflow is mocked here — its composition is unit-tested
in ``tests/unit/orchestration/workflows/test_workflow_reruns_integration.py``
and end-to-end in ``tests/integration/cli/test_test_cmd_with_reruns.py``.

Pinned by decision ``2026-06-25-test-reruns-flag-and-replay-integration``:

- default ``0`` = pre-flag behavior byte-for-byte (envelope identity test
  + syrupy snapshot),
- negative values → ``invalid-flag`` / exit 2, mirroring ``--formula``,
- the ``--reruns N > 0`` happy envelope differs ONLY via
  ``stage_eligibility.replay`` + the recommendations content (snapshot).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.models import MemoryEntry, ReplayResult, RunRecord
from novetest.models.run_reference import RunReference
from novetest.orchestration.recommendation import (
    CATEGORY_FLAKY_SUSPECTED,
    FactBundle,
    PRIORITIES,
    Recommendation,
    StageEligibility,
)
from novetest.orchestration.workflows.test import TestOutcome


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    return json.loads(out)


# ---------------------------------------------------------------------------
# Deterministic TestOutcome doubles
# ---------------------------------------------------------------------------


def _make_outcome(*, with_replay: bool) -> TestOutcome:
    ref = RunReference(run_id="01TESTRUN0000000000000000A", created_at=1000)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=1000,
        completed_at=1001,
        summary_counts={"passed": 0, "failed": 1, "total": 1},
    )
    entry = MemoryEntry(
        entry_id=ref.run_id,
        run_record=record,
        stored_at=1002,
    )
    if with_replay:
        replay_results: tuple[ReplayResult, ...] = (
            ReplayResult(
                run_reference=ref,
                classification="inconsistent",
                reruns_total=5,
                reruns_failed=2,
                test_id="tests/test_a.py::test_flaky",
            ),
        )
        replay_state, replay_reason = "available", None
    else:
        replay_results = ()
        replay_state, replay_reason = "not_run", "replay_not_run"
    elig = StageEligibility(
        coverage="unavailable",
        regression="unavailable",
        localization="unavailable",
        replay=replay_state,
        per_stage_reasons={
            "coverage": "missing-derived-facts",
            "regression": "no-comparable-baseline",
            "localization": "no-coverage",
            "replay": replay_reason,
        },
    )
    bundle = FactBundle(
        run_reference=ref,
        run_record=record,
        stage_eligibility=elig,
        coverage_facts=None,
        regression_facts=None,
        localization_findings=None,
        replay_results=replay_results,
    )
    recommendations: list[Recommendation] = []
    if with_replay:
        recommendations.append(
            Recommendation(
                recommendation_id="rec_01TESTRUN0000000000000000A_flaky0",
                category=CATEGORY_FLAKY_SUSPECTED,
                priority=PRIORITIES[CATEGORY_FLAKY_SUSPECTED],
                summary=(
                    "tests/test_a.py::test_flaky diverged in 2 of 5 replay "
                    "reruns — suspected flaky."
                ),
                slots={
                    "test_id": "tests/test_a.py::test_flaky",
                    "reruns_total": 5,
                    "reruns_failed": 2,
                    "run_reference": ref.run_id,
                },
                evidence_citations=[
                    {
                        "kind": "replay_result",
                        "run_reference": {"run_id": ref.run_id, "created_at": 1000},
                        "selector": {
                            "classification": "inconsistent",
                            "test_id": "tests/test_a.py::test_flaky",
                        },
                    }
                ],
            )
        )
    return TestOutcome(
        memory_entry=entry,
        artifact_dir=Path("/tmp/x"),
        stage_eligibility=elig,
        fact_bundle=bundle,
        recommendations=recommendations,
        run_record_status="failed",
    )


class _WorkflowSpy:
    """Async ``test_target_in_store`` double recording forwarded kwargs."""

    def __init__(self, outcome: TestOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, target: str, store: Any, **kwargs: Any) -> TestOutcome:
        self.calls.append({"target": target, **kwargs})
        return self.outcome


def _patch_seams(
    monkeypatch: pytest.MonkeyPatch, spy: _WorkflowSpy
) -> None:
    monkeypatch.setattr(app_module, "_require_store", lambda cmd: object())
    monkeypatch.setattr(app_module, "test_target_in_store", spy)


# ---------------------------------------------------------------------------
# Flag forwarding — accepted values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reruns", [0, 1, 5, 100])
def test_reruns_value_forwarded_to_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    reruns: int,
) -> None:
    spy = _WorkflowSpy(_make_outcome(with_replay=False))
    _patch_seams(monkeypatch, spy)

    with pytest.raises(SystemExit) as exc_info:
        app_module.test_cmd(reruns=reruns)
    assert exc_info.value.code == 3  # status "failed" → EXIT_USER_TESTS_FAILED

    assert spy.calls == [{"target": "", "reruns": reruns, "engine": None}]
    payload = _captured_envelope(capsys)
    assert payload["command"] == "test"
    assert payload["ok"] is True


def test_bare_invocation_defaults_to_zero_reruns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    spy = _WorkflowSpy(_make_outcome(with_replay=False))
    _patch_seams(monkeypatch, spy)

    with pytest.raises(SystemExit):
        app_module.test_cmd()

    assert spy.calls == [{"target": "", "reruns": 0, "engine": None}]
    _captured_envelope(capsys)  # drain


# ---------------------------------------------------------------------------
# Negative value → invalid-flag, exit 2, workflow never invoked
# ---------------------------------------------------------------------------


def test_negative_reruns_rejected_with_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def must_not_run(*_a: Any, **_k: Any) -> TestOutcome:
        raise AssertionError("workflow invoked despite invalid --reruns")

    monkeypatch.setattr(app_module, "_require_store", lambda cmd: object())
    monkeypatch.setattr(app_module, "test_target_in_store", must_not_run)

    with pytest.raises(SystemExit) as exc_info:
        app_module.test_cmd(reruns=-1)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["command"] == "test"
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid-flag"
    assert "--reruns" in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# Default-path byte identity + snapshots
# ---------------------------------------------------------------------------


def test_reruns_zero_envelope_byte_identical_to_bare_invocation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    """``--reruns 0`` (explicit) and no flag emit byte-identical envelopes
    for the same workflow outcome — the decision's zero-regression pin.
    """
    spy = _WorkflowSpy(_make_outcome(with_replay=False))
    _patch_seams(monkeypatch, spy)

    with pytest.raises(SystemExit):
        app_module.test_cmd()
    bare = capsys.readouterr().out

    with pytest.raises(SystemExit):
        app_module.test_cmd(reruns=0)
    explicit_zero = capsys.readouterr().out

    assert bare == explicit_zero


def test_default_envelope_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the no-``--reruns`` envelope so future flag work cannot drift
    the default path (``stage_eligibility.replay`` stays ``not_run``).
    """
    spy = _WorkflowSpy(_make_outcome(with_replay=False))
    _patch_seams(monkeypatch, spy)

    with pytest.raises(SystemExit):
        app_module.test_cmd()

    assert _captured_envelope(capsys) == snapshot


def test_reruns_happy_envelope_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the ``--reruns N > 0`` happy-path envelope (decision §"Envelope"):
    same shape as the default path; ``stage_eligibility.replay`` is
    ``available`` and a ``flaky_suspected`` recommendation appears.
    """
    spy = _WorkflowSpy(_make_outcome(with_replay=True))
    _patch_seams(monkeypatch, spy)

    with pytest.raises(SystemExit) as exc_info:
        app_module.test_cmd(reruns=5)
    assert exc_info.value.code == 3

    payload = _captured_envelope(capsys)
    assert payload["data"]["stage_eligibility"]["replay"] == "available"
    assert [r["category"] for r in payload["data"]["recommendations"]] == [
        CATEGORY_FLAKY_SUSPECTED
    ]
    assert payload == snapshot
