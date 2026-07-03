"""Unit tests for the anchored ``init`` workflow (D1 + D4 + D7 plumbing).

Pins ``workflows/init.py``'s three-way outcome union per decision
``2026-07-03-engine-selection-policy.md``:

- exactly one viable engine → store created + pinned (readiness informational);
- no marker → NOTHING created, D4 discovery report attached;
- ambiguous → NOTHING created, explicit ``--engine`` required;
- explicit ``engine`` pair → detection skipped, pin written (re-pin in place
  on an existing store, run history retained).

Readiness probes are monkeypatched in the ``init`` module namespace (and the
chooser comes from ``anchor_resolution``, patched there when a test needs to
prove it is NOT consulted); detection and discovery run for real against
fabricated marker files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import novetest.orchestration.anchor_resolution as anchor_module
import novetest.orchestration.workflows.init as init_module
from novetest.memory import create_project_store, get_project_store_state
from novetest.memory.project_store import set_pinned_engine
from novetest.orchestration.workflows.init import (
    InitEngineAmbiguous,
    InitializationResult,
    InitNoEngineDetected,
    initialize_project_workspace,
)
from novetest.run import EngineReadinessResult, NativeEngineContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_probe(
    monkeypatch: pytest.MonkeyPatch, ready_engines: set[str]
) -> list[str]:
    """Fake ``probe_engine`` in BOTH namespaces that call it."""

    probed: list[str] = []

    async def fake_probe(
        _workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        probed.append(engine_name)
        state = "ready" if engine_name in ready_engines else "engine-misconfigured"
        return EngineReadinessResult(
            state=state,
            engine_context=NativeEngineContext(
                ecosystem=ecosystem, engine_name=engine_name
            ),
            evidence=(),
            issues=() if state == "ready" else ("stubbed issue",),
        )

    monkeypatch.setattr(anchor_module, "probe_engine", fake_probe)
    monkeypatch.setattr(init_module, "probe_engine", fake_probe)
    return probed


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _mark_python(ws: Path) -> None:
    (ws / "pyproject.toml").write_text("[project]\n", encoding="utf-8")


def _mark_go(ws: Path) -> None:
    (ws / "go.mod").write_text("module example.com/x\n", encoding="utf-8")


def _store_json(ws: Path) -> dict[str, object]:
    raw = (ws / ".novetest" / "store.json").read_text(encoding="utf-8")
    parsed: dict[str, object] = json.loads(raw)
    return parsed


# ---------------------------------------------------------------------------
# D1 — single viable engine pins
# ---------------------------------------------------------------------------


async def test_single_ready_marker_creates_store_and_pins(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest"})

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitializationResult)
    assert result.engine_readiness.state == "ready"
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.to_dict() == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }
    assert _store_json(workspace)["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }


async def test_single_marker_not_ready_still_pins(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness stays informational (NFR-RUN-004): a misconfigured engine
    never blocks the store or the pin — the envelope names the issue."""

    _mark_python(workspace)
    _patch_probe(monkeypatch, ready_engines=set())

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitializationResult)
    assert result.engine_readiness.state == "engine-misconfigured"
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.engine_name == "pytest"


async def test_two_markers_single_ready_pins_the_ready_one(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"go-test"})

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitializationResult)
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.engine_name == "go-test"


# ---------------------------------------------------------------------------
# D1 — no marker: nothing created, D4 discovery report
# ---------------------------------------------------------------------------


async def test_markerless_workspace_creates_nothing_and_reports_candidates(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_probe(monkeypatch, ready_engines=set())
    backend = workspace / "backend"
    backend.mkdir()
    _mark_python(backend)

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitNoEngineDetected)
    assert result.scan_refused is False
    assert [c.to_dict() for c in result.candidates] == [
        {"path": "backend", "ecosystem": "python", "engine_name": "pytest"}
    ]
    assert not (workspace / ".novetest").exists()


async def test_markerless_at_home_refuses_scan(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4 bound 3: init at ``$HOME`` refuses the discovery scan outright."""

    _patch_probe(monkeypatch, ready_engines=set())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: workspace))
    sub = workspace / "would-be-found"
    sub.mkdir()
    _mark_python(sub)

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitNoEngineDetected)
    assert result.scan_refused is True
    assert result.candidates == ()
    assert not (workspace / ".novetest").exists()


# ---------------------------------------------------------------------------
# D1 — ambiguous: nothing created
# ---------------------------------------------------------------------------


async def test_ambiguous_workspace_creates_nothing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitEngineAmbiguous)
    assert [c.engine_name for c in result.candidates] == ["pytest", "go-test"]
    assert not (workspace / ".novetest").exists()


# ---------------------------------------------------------------------------
# --engine: explicit wins, re-pin in place
# ---------------------------------------------------------------------------


async def test_explicit_engine_skips_detection_and_pins(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--engine`` wins over detection in ALL cases — even a markerless dir."""

    _patch_probe(monkeypatch, ready_engines={"pytest"})

    async def must_not_choose(_ws: Path) -> None:
        raise AssertionError("detection ran despite explicit --engine")

    monkeypatch.setattr(init_module, "choose_workspace_engine", must_not_choose)

    result = await initialize_project_workspace(
        workspace, engine=("python", "pytest")
    )
    assert isinstance(result, InitializationResult)
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.engine_name == "pytest"


async def test_explicit_engine_repins_existing_store_in_place(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-init with ``--engine <other>``: same store, pin updated, run
    history retained — never a second ``.novetest/`` (decision D1)."""

    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})

    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")
    original_initialized_at = store.initialized_at
    run_marker = store.path / "memory" / "runs" / "run_SENTINEL"
    run_marker.mkdir(parents=True)
    (run_marker / "record.json").write_text("{}", encoding="utf-8")

    result = await initialize_project_workspace(workspace, engine=("go", "go-test"))
    assert isinstance(result, InitializationResult)
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.engine_name == "go-test"
    assert result.store.initialized_at == original_initialized_at
    assert (run_marker / "record.json").exists()  # history retained
    on_disk = get_project_store_state(workspace / ".novetest")
    assert on_disk.pinned_engine is not None
    assert on_disk.pinned_engine.engine_name == "go-test"


# ---------------------------------------------------------------------------
# Existing stores without --engine
# ---------------------------------------------------------------------------


async def test_reinit_on_pinned_store_is_idempotent(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing pin governs — detection does NOT re-run (D2 invariant)."""

    _mark_python(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest"})
    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")

    async def must_not_choose(_ws: Path) -> None:
        raise AssertionError("detection ran despite an existing pin")

    monkeypatch.setattr(init_module, "choose_workspace_engine", must_not_choose)

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitializationResult)
    assert result.store.pinned_engine is not None
    assert result.store.pinned_engine.engine_name == "pytest"


async def test_reinit_on_legacy_pinless_store_backfills(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest"})
    create_project_store(workspace)  # legacy shape: no pin

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitializationResult)
    assert result.store.pinned_engine is not None
    assert _store_json(workspace)["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }


async def test_reinit_on_legacy_ambiguous_store_leaves_store_intact(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ambiguous outcome never destroys an existing store."""

    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})
    create_project_store(workspace)

    result = await initialize_project_workspace(workspace)
    assert isinstance(result, InitEngineAmbiguous)
    assert (workspace / ".novetest" / "store.json").exists()
    assert "pinned_engine" not in _store_json(workspace)  # still legacy
