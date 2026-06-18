"""Renderer tests for ``novetest init``."""

from __future__ import annotations

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def _init_envelope(readiness: dict[str, object]) -> Envelope:
    return Envelope(
        command="init",
        ok=True,
        data={
            "store_path": "/work/.novetest",
            "store_state": "ready",
            "initialized_at": 1700000000000,
            "engine_readiness": readiness,
        },
    )


def test_init_engine_ready(snapshot: SnapshotAssertion) -> None:
    envelope = _init_envelope(
        {
            "state": "ready",
            "engine": "pytest",
            "ecosystem": "python",
            "engine_version": "9.0.3",
            "evidence": ["pyproject.toml"],
            "issues": [],
        }
    )
    assert render_text(envelope) == snapshot


def test_init_no_engine_detected(snapshot: SnapshotAssertion) -> None:
    envelope = _init_envelope(
        {
            "state": "no-engine",
            "engine": None,
            "ecosystem": None,
            "engine_version": None,
            "evidence": [],
            "issues": ["no recognized test engine in workspace"],
        }
    )
    assert render_text(envelope) == snapshot
