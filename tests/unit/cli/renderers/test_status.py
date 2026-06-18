"""Renderer tests for ``novetest status``."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_status_with_latest_run(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="status",
        ok=True,
        data={
            "latest_run_reference": ref(),
            "run_history_size": 2,
            "sub_reports": {
                "coverage": "available",
                "regression": "unavailable",
                "localization": "available",
                "replay": "unavailable",
            },
        },
    )
    assert render_text(envelope) == snapshot


def test_status_empty_store(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="status",
        ok=True,
        data={
            "latest_run_reference": None,
            "run_history_size": 0,
            "sub_reports": {
                "coverage": "unavailable",
                "regression": "unavailable",
                "localization": "unavailable",
                "replay": "unavailable",
            },
        },
    )
    assert render_text(envelope) == snapshot
