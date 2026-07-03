"""Unit tests for the ``reset_project_workspace`` workflow composition.

The workflow composes three collaborators:

1. ``locate_project_store`` (Memory, package path ``novetest.memory``) —
   walk-up resolution.
2. ``wipe_project_store`` (Memory, **module path**
   ``novetest.memory.project_store``) — destructive primitive.
3. ``initialize_project_workspace`` (the existing ``init`` workflow).

These tests pin the **composition contract**: order (wipe strictly before
re-init), refusal-before-destruction (no store → raise, nothing wiped), and
that both sub-results are carried back on ``ResetResult``. The destructive
primitive is monkeypatched on its real module so no filesystem mutation
happens; the not-found path uses Memory's real ``ProjectStoreNotFoundError``
(the workflow imports it from the module path).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import novetest.memory as memory_pkg
import novetest.memory.project_store as project_store_mod
import novetest.orchestration.workflows.reset as reset_module
from novetest.memory.project_store import ProjectStoreNotFoundError
from novetest.orchestration.workflows.init import InitializationResult
from novetest.orchestration.workflows.reset import (
    ResetResult,
    reset_project_workspace,
)


def test_reset_composes_wipe_then_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: locate → wipe → re-init, in that order; ``ResetResult``
    carries both the wipe report and the init result."""

    call_log: list[str] = []
    init_kwargs: list[dict[str, Any]] = []
    store = SimpleNamespace(
        path=Path("/ws/.novetest"),
        pinned_engine=SimpleNamespace(ecosystem="python", engine_name="pytest"),
    )
    wipe_report = SimpleNamespace(
        store_path=Path("/ws/.novetest"),
        previous_initialized_at=1_700_000_000_000,
        items_removed={"runs": 3, "tombstones": 0},
    )
    init_result = InitializationResult(
        store=SimpleNamespace(),  # type: ignore[arg-type]
        engine_readiness=object(),  # type: ignore[arg-type]
    )

    def fake_locate(_workspace: Path) -> Any:
        call_log.append("locate")
        return store

    def fake_wipe(_store_path: Path) -> Any:
        call_log.append("wipe")
        return wipe_report

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        call_log.append("init")
        init_kwargs.append({"workspace": workspace, "engine": engine})
        return init_result

    # locate is on the package path; wipe is on the module path.
    monkeypatch.setattr(memory_pkg, "locate_project_store", fake_locate)
    monkeypatch.setattr(project_store_mod, "wipe_project_store", fake_wipe)
    monkeypatch.setattr(reset_module, "initialize_project_workspace", fake_init)

    result = asyncio.run(reset_project_workspace(Path("/ws")))

    assert isinstance(result, ResetResult)
    assert result.wipe_report is wipe_report
    assert result.init_result is init_result
    # Order is load-bearing: the store is wiped strictly before re-init.
    assert call_log == ["locate", "wipe", "init"]
    # Anchored-pin (2026-07-03): re-init happens at the wiped store's ANCHOR
    # (store.path.parent) and re-applies the previous pin explicitly.
    assert init_kwargs == [
        {"workspace": Path("/ws"), "engine": ("python", "pytest")}
    ]


def test_reset_raises_when_no_store_and_never_wipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No store in the walk-up → ``ProjectStoreNotFoundError`` raised BEFORE
    any destructive call. ``wipe_project_store`` / re-init never run."""

    call_log: list[str] = []

    def fake_locate(_workspace: Path) -> Any:
        call_log.append("locate")
        return None

    def must_not_wipe(_store_path: Path) -> Any:
        raise AssertionError("wipe_project_store called when no store present")

    async def must_not_init(_workspace: Path, *, engine: Any = None) -> Any:
        raise AssertionError("initialize_project_workspace called on refusal path")

    monkeypatch.setattr(memory_pkg, "locate_project_store", fake_locate)
    monkeypatch.setattr(project_store_mod, "wipe_project_store", must_not_wipe)
    monkeypatch.setattr(reset_module, "initialize_project_workspace", must_not_init)

    with pytest.raises(ProjectStoreNotFoundError) as exc_info:
        asyncio.run(reset_project_workspace(Path("/ws")))

    assert "nothing to reset" in str(exc_info.value)
    assert call_log == ["locate"]  # refused before wipe


def test_reset_carries_previous_pin_into_reinit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pinned store's engine is re-applied via init's explicit-engine path
    (reset wipes evidence, not intent — a dual-marker workspace must never
    go ambiguous on reset)."""

    init_kwargs: list[dict[str, Any]] = []
    store = SimpleNamespace(
        path=Path("/ws/.novetest"),
        pinned_engine=SimpleNamespace(ecosystem="rust", engine_name="cargo-test"),
    )
    init_result = InitializationResult(
        store=SimpleNamespace(),  # type: ignore[arg-type]
        engine_readiness=object(),  # type: ignore[arg-type]
    )

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        init_kwargs.append({"workspace": workspace, "engine": engine})
        return init_result

    monkeypatch.setattr(
        memory_pkg, "locate_project_store", lambda _ws: store
    )
    monkeypatch.setattr(
        project_store_mod,
        "wipe_project_store",
        lambda _p: SimpleNamespace(
            store_path=Path("/ws/.novetest"),
            previous_initialized_at=1,
            items_removed={},
        ),
    )
    monkeypatch.setattr(reset_module, "initialize_project_workspace", fake_init)

    result = asyncio.run(reset_project_workspace(Path("/ws/sub")))

    assert isinstance(result, ResetResult)
    assert init_kwargs == [
        {"workspace": Path("/ws"), "engine": ("rust", "cargo-test")}
    ]


# ---------------------------------------------------------------------------
# Legacy pin-less stores: the D1 choice happens BEFORE the wipe
# ---------------------------------------------------------------------------


def test_reset_refuses_legacy_ambiguous_store_before_wipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ambiguous anchor refuses while the store is still intact — reset
    never destroys state it cannot rebuild (code-review should-fix #1)."""

    from novetest.orchestration.anchor_resolution import AmbiguousEngines
    from novetest.orchestration.workflows.init import InitEngineAmbiguous
    from novetest.run import EngineCandidate

    store = SimpleNamespace(path=Path("/ws/.novetest"), pinned_engine=None)
    candidates = (
        EngineCandidate(ecosystem="python", engine_name="pytest"),
        EngineCandidate(ecosystem="go", engine_name="go-test"),
    )

    async def fake_choose(_ws: Path) -> Any:
        return AmbiguousEngines(candidates=candidates)

    def must_not_wipe(_store_path: Path) -> Any:
        raise AssertionError("wipe_project_store called on the refusal path")

    async def must_not_init(_workspace: Path, *, engine: Any = None) -> Any:
        raise AssertionError("initialize_project_workspace called on refusal path")

    monkeypatch.setattr(memory_pkg, "locate_project_store", lambda _ws: store)
    monkeypatch.setattr(reset_module, "choose_workspace_engine", fake_choose)
    monkeypatch.setattr(project_store_mod, "wipe_project_store", must_not_wipe)
    monkeypatch.setattr(reset_module, "initialize_project_workspace", must_not_init)

    result = asyncio.run(reset_project_workspace(Path("/ws")))
    assert isinstance(result, InitEngineAmbiguous)
    assert result.candidates == candidates


def test_reset_legacy_unambiguous_store_wipes_with_chosen_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single pre-wipe choice locks the engine pair for the re-init."""

    from novetest.orchestration.anchor_resolution import ChosenEngine
    from novetest.orchestration.workflows.init import InitializationResult

    call_log: list[str] = []
    init_kwargs: list[dict[str, Any]] = []
    store = SimpleNamespace(path=Path("/ws/.novetest"), pinned_engine=None)

    async def fake_choose(_ws: Path) -> Any:
        call_log.append("choose")
        return ChosenEngine(
            ecosystem="python",
            engine_name="pytest",
            readiness=object(),  # type: ignore[arg-type]
        )

    def fake_wipe(_store_path: Path) -> Any:
        call_log.append("wipe")
        return SimpleNamespace(
            store_path=Path("/ws/.novetest"),
            previous_initialized_at=1,
            items_removed={},
        )

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        call_log.append("init")
        init_kwargs.append({"workspace": workspace, "engine": engine})
        return InitializationResult(
            store=SimpleNamespace(),  # type: ignore[arg-type]
            engine_readiness=object(),  # type: ignore[arg-type]
        )

    monkeypatch.setattr(memory_pkg, "locate_project_store", lambda _ws: store)
    monkeypatch.setattr(reset_module, "choose_workspace_engine", fake_choose)
    monkeypatch.setattr(project_store_mod, "wipe_project_store", fake_wipe)
    monkeypatch.setattr(reset_module, "initialize_project_workspace", fake_init)

    result = asyncio.run(reset_project_workspace(Path("/ws")))
    assert isinstance(result, ResetResult)
    assert call_log == ["choose", "wipe", "init"]  # choice strictly first
    assert init_kwargs == [
        {"workspace": Path("/ws"), "engine": ("python", "pytest")}
    ]
