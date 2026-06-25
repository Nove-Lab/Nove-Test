"""Unit tests for the ``reset_project_workspace`` workflow composition.

The workflow composes three collaborators:

1. ``locate_project_store`` (Memory) — walk-up resolution.
2. ``wipe_project_store`` (Memory, sibling cycle) — destructive primitive.
3. ``initialize_project_workspace`` (the existing ``init`` workflow).

These tests pin the **composition contract**: order (wipe strictly before
re-init), refusal-before-destruction (no store → raise, nothing wiped), and
that both sub-results are carried back on ``ResetResult``. The Memory
primitive lands in a sibling cycle, so it is injected via monkeypatch on
``novetest.memory`` (``raising=False`` creates the not-yet-shipped symbol);
the workflow's lazy per-call import reads the patched attribute.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import novetest.memory as memory_pkg
import novetest.orchestration.workflows.reset as reset_module
from novetest.orchestration.workflows.reset import (
    ResetResult,
    reset_project_workspace,
)


class _FakeProjectStoreNotFoundError(RuntimeError):
    """Stand-in for Memory's not-yet-shipped exception (a ``RuntimeError``)."""


def _install_memory_doubles(
    monkeypatch: pytest.MonkeyPatch,
    *,
    store: Any,
    wipe_report: Any,
    call_log: list[str],
) -> None:
    """Wire ``locate_project_store`` / ``wipe_project_store`` /
    ``ProjectStoreNotFoundError`` onto ``novetest.memory`` for one test."""

    def fake_locate(_workspace: Path) -> Any:
        call_log.append("locate")
        return store

    def fake_wipe(_store_path: Path) -> Any:
        call_log.append("wipe")
        return wipe_report

    monkeypatch.setattr(memory_pkg, "locate_project_store", fake_locate)
    monkeypatch.setattr(memory_pkg, "wipe_project_store", fake_wipe, raising=False)
    monkeypatch.setattr(
        memory_pkg,
        "ProjectStoreNotFoundError",
        _FakeProjectStoreNotFoundError,
        raising=False,
    )


def test_reset_composes_wipe_then_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: locate → wipe → re-init, in that order; ``ResetResult``
    carries both the wipe report and the init result."""

    call_log: list[str] = []
    store = SimpleNamespace(path=Path("/ws/.novetest"))
    wipe_report = SimpleNamespace(
        store_path=Path("/ws/.novetest"),
        previous_initialized_at=1_700_000_000_000,
        items_removed={"runs": 3, "tombstones": 0},
    )
    init_result = SimpleNamespace(store=SimpleNamespace(), engine_readiness=object())

    _install_memory_doubles(
        monkeypatch, store=store, wipe_report=wipe_report, call_log=call_log
    )

    async def fake_init(_workspace: Path) -> Any:
        call_log.append("init")
        return init_result

    monkeypatch.setattr(reset_module, "initialize_project_workspace", fake_init)

    result = asyncio.run(reset_project_workspace(Path("/ws")))

    assert isinstance(result, ResetResult)
    assert result.wipe_report is wipe_report
    assert result.init_result is init_result
    # Order is load-bearing: the store is wiped strictly before re-init.
    assert call_log == ["locate", "wipe", "init"]


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

    async def must_not_init(_workspace: Path) -> Any:
        raise AssertionError("initialize_project_workspace called on refusal path")

    monkeypatch.setattr(memory_pkg, "locate_project_store", fake_locate)
    monkeypatch.setattr(memory_pkg, "wipe_project_store", must_not_wipe, raising=False)
    monkeypatch.setattr(
        memory_pkg,
        "ProjectStoreNotFoundError",
        _FakeProjectStoreNotFoundError,
        raising=False,
    )
    monkeypatch.setattr(reset_module, "initialize_project_workspace", must_not_init)

    with pytest.raises(_FakeProjectStoreNotFoundError) as exc_info:
        asyncio.run(reset_project_workspace(Path("/ws")))

    assert "nothing to reset" in str(exc_info.value)
    assert call_log == ["locate"]  # refused before wipe
