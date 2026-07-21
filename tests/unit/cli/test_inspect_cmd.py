"""Unit tests for the `novetest inspect` CLI handler.

Covers the thin handler contract: resolve store → call
`build_inspect_view` → project `view.to_dict()` onto the envelope, or
emit a structured `not-found` (exit 2) when the run_id does not resolve.
The workflow seam (`build_inspect_view`) and `_require_store` are
monkeypatched at the app module; envelopes are captured via `capsys`
(per the prior slice's gotcha — a second monkeypatch on `sys.stdout`
fights pytest's own capture and yields empty buffers).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli.handlers import inspect as app_module
from novetest.cli.output import OutputMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeView:
    """Stand-in for `InspectView` — the handler only calls `to_dict()`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return self._payload


_VIEW_PAYLOAD: dict[str, Any] = {
    "run_reference": {"run_id": "01TESTTESTTESTTESTTESTTEST", "created_at": 1},
    "run_summary": {
        "status": "passed",
        "target_expression": "tests/",
        "target_type": "directory",
        "engine_name": "pytest",
        "ecosystem": "python",
        "summary_counts": {"passed": 3, "failed": 0, "total": 3},
        "tombstoned": False,
    },
    "coverage_outcome": {
        "kind": "fact-set",
        "run_reference": {"run_id": "01TESTTESTTESTTESTTESTTEST", "created_at": 1},
        "mapping_granularity": "per-test",
        "summary": {"percent_covered": 80.0},
    },
    "sub_reports": {
        "coverage": "available",
        "regression": "unavailable",
        "localization": "unavailable",
        "replay": "unavailable",
    },
}


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


def test_inspect_emits_aggregated_view_when_run_resolves(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    run_id = "01TESTTESTTESTTESTTESTTEST"
    seen: list[tuple[object, str, object]] = []

    def fake_build(store: Any, rid: str, *, skipped: Any = None) -> _FakeView:
        seen.append((store, rid, skipped))
        return _FakeView(_VIEW_PAYLOAD)

    monkeypatch.setattr(app_module, "build_inspect_view", fake_build)

    with pytest.raises(SystemExit) as exc_info:
        app_module.inspect_cmd(run_id)
    assert exc_info.value.code == 0
    # The handler forwards the resolved store + raw run_id to the workflow,
    # plus a (fresh, empty) MEM-05 skip collector for the Q1-A miss check.
    assert seen == [(stub_store, run_id, [])]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "inspect"
    assert payload["ok"] is True
    data = payload["data"]
    assert data["run_reference"]["run_id"] == run_id
    assert data["run_summary"]["status"] == "passed"
    assert data["coverage_outcome"]["kind"] == "fact-set"
    assert data["sub_reports"]["regression"] == "unavailable"


def test_inspect_returns_not_found_for_unknown_run_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """`build_inspect_view` returns None → structured not-found, exit 2."""

    monkeypatch.setattr(
        app_module, "build_inspect_view", lambda _store, _rid, skipped=None: None
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.inspect_cmd("fake-id")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["command"] == "inspect"
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "not-found"
    assert "fake-id" in payload["errors"][0]["message"]
