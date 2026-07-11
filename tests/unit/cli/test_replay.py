"""Unit tests for the ``novetest replay`` CLI envelope projection.

Pins the pure ``_build_replay_envelope`` mapping in ``cli/app.py`` — the
exit-code split (§5.3) — and the shared ``replay_outcome_payload`` wire
shape (§1.5; single-sourced in ``orchestration/projection.py`` since
W2/S23) without spawning a subprocess. The end-to-end engine behaviour is
covered by ``tests/integration/replay/``.
"""

from __future__ import annotations

from novetest.cli.app import _build_replay_envelope
from novetest.cli.output import EXIT_ENGINE_MISSING, EXIT_OK, EXIT_USAGE
from novetest.models.replay_result import ReplayResult
from novetest.models.run_reference import RunReference
from novetest.orchestration.projection import replay_outcome_payload
from novetest.replay import (
    REASON_CONTEXT_RECONSTRUCTION_FAILED,
    REASON_ENGINE_NOT_READY,
    REASON_MISSING_DERIVED_FACTS,
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    REASON_TOMBSTONED_ORIGINAL,
    ReplayUnavailable,
)


def _ref(run_id: str = "01REPLAY00000000000000A") -> RunReference:
    return RunReference(run_id=run_id, created_at=1_748_800_000_000)


def _result(classification: str, **kw: object) -> ReplayResult:
    return ReplayResult(
        run_reference=_ref(),
        classification=classification,
        reruns_total=kw.get("reruns_total", 5),  # type: ignore[arg-type]
        reruns_failed=kw.get("reruns_failed", 2),  # type: ignore[arg-type]
        test_id=kw.get("test_id"),  # type: ignore[arg-type]
        reason=kw.get("reason"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# replay_outcome_payload — wire shape (shared projection)
# ---------------------------------------------------------------------------


def test_payload_for_result_is_replay_result_kind_without_run_reference() -> None:
    result = _result("inconsistent", test_id="tests/t.py::t")
    payload = replay_outcome_payload(result)
    assert payload["kind"] == "replay-result"
    assert payload["classification"] == "inconsistent"
    assert payload["reruns_total"] == 5
    assert payload["reruns_failed"] == 2
    # schema_version + the (duplicated) original run_reference are dropped.
    assert "schema_version" not in payload
    assert "run_reference" not in payload


def test_payload_for_unavailable_is_unavailable_kind() -> None:
    unavailable = ReplayUnavailable(
        run_reference=_ref(),
        reason=REASON_TOMBSTONED_ORIGINAL,
        detail="tombstoned",
    )
    payload = replay_outcome_payload(unavailable)
    assert payload["kind"] == "unavailable"
    assert payload["reason"] == REASON_TOMBSTONED_ORIGINAL
    assert payload["detail"] == "tombstoned"
    assert "run_reference" in payload


# ---------------------------------------------------------------------------
# _build_replay_envelope — exit-code split (§5.3)
# ---------------------------------------------------------------------------


def test_result_any_classification_exits_zero() -> None:
    for classification in ("reproducible", "inconsistent"):
        envelope, code = _build_replay_envelope(_ref(), _result(classification))
        assert code == EXIT_OK
        assert envelope.ok is True
        assert envelope.command == "replay"
        assert envelope.data["original_run_reference"]["run_id"] == _ref().run_id


def test_unable_to_replay_is_a_success_outcome_exit_zero() -> None:
    result = _result(
        "unable_to_replay", reruns_total=3, reruns_failed=0, reason="replay-run-errored"
    )
    envelope, code = _build_replay_envelope(_ref(), result)
    assert code == EXIT_OK
    assert envelope.ok is True


def test_engine_not_ready_exits_four() -> None:
    unavailable = ReplayUnavailable(
        run_reference=_ref(), reason=REASON_ENGINE_NOT_READY, detail="missing"
    )
    envelope, code = _build_replay_envelope(_ref(), unavailable)
    assert code == EXIT_ENGINE_MISSING
    assert envelope.ok is False
    assert envelope.errors[0].code == f"replay-{REASON_ENGINE_NOT_READY}"


def test_target_missing_exits_four() -> None:
    unavailable = ReplayUnavailable(
        run_reference=_ref(), reason=REASON_TARGET_MISSING, detail="gone"
    )
    _, code = _build_replay_envelope(_ref(), unavailable)
    assert code == EXIT_ENGINE_MISSING


def test_original_not_found_exits_two() -> None:
    unavailable = ReplayUnavailable(
        run_reference=_ref(), reason=REASON_ORIGINAL_NOT_FOUND, detail="stale"
    )
    envelope, code = _build_replay_envelope(_ref(), unavailable)
    assert code == EXIT_USAGE
    assert envelope.ok is False


def test_structured_unavailable_reasons_exit_zero() -> None:
    for reason in (
        REASON_TOMBSTONED_ORIGINAL,
        REASON_CONTEXT_RECONSTRUCTION_FAILED,
        REASON_MISSING_DERIVED_FACTS,
    ):
        unavailable = ReplayUnavailable(run_reference=_ref(), reason=reason)
        envelope, code = _build_replay_envelope(_ref(), unavailable)
        assert code == EXIT_OK, reason
        assert envelope.ok is True, reason
        assert envelope.data["replay_outcome"]["kind"] == "unavailable"
