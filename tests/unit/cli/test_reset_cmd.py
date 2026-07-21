"""Unit tests for the ``novetest reset --confirm`` CLI handler.

``reset_cmd`` is a thin transport wrapper: gate on ``--confirm``, run the
``reset_project_workspace`` workflow, map its exceptions onto the pinned
error envelopes, and project the happy-path result onto ``data``. The
workflow (and Memory's wipe primitive underneath it) is mocked here — the
composition itself is unit-tested in
``tests/unit/orchestration/workflows/test_reset.py`` and end-to-end in
``tests/integration/cli/test_reset_e2e.py`` (post-Memory-merge).

Memory's ``ProjectStoreNotFoundError`` ships in a sibling cycle; it is
injected via ``monkeypatch`` on ``novetest.memory`` (``raising=False``) so
the handler's lazy ``from novetest.memory import ProjectStoreNotFoundError``
resolves the same class object the fake workflow raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

import novetest.orchestration.workflows as workflows_pkg
from novetest.cli import _shared
from novetest.cli.handlers import onboarding as app_module
from novetest.cli.output import OutputMode
from novetest.memory import ProjectStoreCorruptError
from novetest.memory.project_store import ProjectStoreNotFoundError


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    return json.loads(out)


def _patch_workflow(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    """Point the handler's lazy workflow import at ``fake`` (an async callable)."""
    monkeypatch.setattr(workflows_pkg, "reset_project_workspace", fake)


def _happy_result() -> SimpleNamespace:
    """A deterministic ``ResetResult`` double mirroring the decision-doc shape.

    ``store.path`` is a plain ``str`` (not a ``Path``) so the snapshotted
    ``store_path`` stays POSIX on every OS — the handler only ``str()``s it.
    """
    readiness = SimpleNamespace(
        engine_context=SimpleNamespace(
            engine_name="pytest", ecosystem="python", engine_version="8.0.0"
        ),
        state="ready",
        evidence=["pyproject.toml"],
        issues=[],
    )
    init_result = SimpleNamespace(
        store=SimpleNamespace(
            path="/ws/.novetest",
            store_state="ready",
            initialized_at=1_719_215_123_000,
            # ORC-20: reset's success envelope mirrors init's pinned_engine
            # shape (a successful reset always carries a pin — the previous
            # pin, or the D1 choice for a legacy pin-less store).
            pinned_engine=SimpleNamespace(
                to_dict=lambda: {"ecosystem": "python", "engine_name": "pytest"}
            ),
        ),
        engine_readiness=readiness,
    )
    wipe_report = SimpleNamespace(
        previous_initialized_at=1_717_939_496_000,
        items_removed={
            "runs": 12,
            "tombstones": 1,
            "coverage_facts": 12,
            "regression_pairs": 7,
            "localization_findings": 8,
            "replay_results": 2,
        },
    )
    return SimpleNamespace(init_result=init_result, wipe_report=wipe_report)


# ---------------------------------------------------------------------------
# Case 1: --confirm missing → exit 2, confirm-required (workflow never runs)
# ---------------------------------------------------------------------------


def test_reset_without_confirm_exits_2_confirm_required(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    def must_not_run(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("workflow invoked without --confirm")

    _patch_workflow(monkeypatch, must_not_run)

    with pytest.raises(SystemExit) as exc_info:
        app_module.reset_cmd(confirm=False)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["command"] == "reset"
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "confirm-required"
    assert "--confirm" in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# Case 2: no store walked-up → exit 2, uninitialized
# ---------------------------------------------------------------------------


def test_reset_uninitialized_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def fake(_workspace: Path) -> Any:
        raise ProjectStoreNotFoundError("nothing to reset; run `novetest init`")

    _patch_workflow(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc_info:
        app_module.reset_cmd(confirm=True)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "uninitialized"


# ---------------------------------------------------------------------------
# Case 3: corrupt store → exit 5, store-corrupt (refusal — store left intact)
# ---------------------------------------------------------------------------


def test_reset_corrupt_store_exits_5_refuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def fake(_workspace: Path) -> Any:
        raise ProjectStoreCorruptError("store.json unreadable at /ws/.novetest")

    _patch_workflow(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc_info:
        app_module.reset_cmd(confirm=True)
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "store-corrupt"


# ---------------------------------------------------------------------------
# Case 4: wipe raises OSError mid-flight → exit 5, store-wipe-failed
# ---------------------------------------------------------------------------


def test_reset_wipe_oserror_exits_5(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def fake(_workspace: Path) -> Any:
        raise PermissionError("EACCES removing /ws/.novetest/runs")

    _patch_workflow(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc_info:
        app_module.reset_cmd(confirm=True)
    assert exc_info.value.code == 5

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "store-wipe-failed"


# ---------------------------------------------------------------------------
# Case 5: happy path → exit 0, projected data; + envelope snapshot pin
# ---------------------------------------------------------------------------


def test_reset_happy_path_projects_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def fake(_workspace: Path) -> Any:
        return _happy_result()

    _patch_workflow(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc_info:
        app_module.reset_cmd(confirm=True)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["command"] == "reset"
    assert payload["ok"] is True
    data = payload["data"]
    assert data["store_state"] == "ready"
    assert data["previous_initialized_at"] == 1_717_939_496_000
    assert data["initialized_at"] == 1_719_215_123_000
    assert data["items_removed"] == {
        "runs": 12,
        "tombstones": 1,
        "coverage_facts": 12,
        "regression_pairs": 7,
        "localization_findings": 8,
        "replay_results": 2,
    }
    assert data["engine_readiness"]["state"] == "ready"
    assert data["engine_readiness"]["engine"] == "pytest"
    # ORC-20: the additive pinned_engine key, shape identical to init's.
    assert data["pinned_engine"] == {"ecosystem": "python", "engine_name": "pytest"}


def test_reset_happy_path_envelope_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    snapshot: SnapshotAssertion,
) -> None:
    """Byte-pin of the full happy-path ``reset`` envelope (the contract the
    decision doc froze). Drift here is intentional-or-bug — fail loudly."""

    async def fake(_workspace: Path) -> Any:
        return _happy_result()

    _patch_workflow(monkeypatch, fake)

    with pytest.raises(SystemExit):
        app_module.reset_cmd(confirm=True)

    assert _captured_envelope(capsys) == snapshot
