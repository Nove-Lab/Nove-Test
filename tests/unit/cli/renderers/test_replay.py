"""Renderer tests for ``novetest replay``."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def _replay_envelope(
    ref: Callable[..., dict[str, Any]], outcome: dict[str, Any]
) -> Envelope:
    return Envelope(
        command="replay",
        ok=True,
        data={"original_run_reference": ref(), "replay_outcome": outcome},
    )


def test_replay_reproducible(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = _replay_envelope(
        ref,
        {
            "kind": "replay-result",
            "classification": "reproducible",
            "reruns_total": 3,
            "reruns_failed": 0,
            "test_id": None,
            "reason": None,
        },
    )
    assert render_text(envelope) == snapshot


def test_replay_inconsistent(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = _replay_envelope(
        ref,
        {
            "kind": "replay-result",
            "classification": "inconsistent",
            "reruns_total": 5,
            "reruns_failed": 2,
            "test_id": "tests/test_flaky.py::test_timing",
            "reason": None,
        },
    )
    assert render_text(envelope) == snapshot


def test_replay_unable(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = _replay_envelope(
        ref,
        {
            "kind": "replay-result",
            "classification": "unable_to_replay",
            "reruns_total": 0,
            "reruns_failed": 0,
            "test_id": None,
            "reason": "no-replayed-runs",
        },
    )
    assert render_text(envelope) == snapshot
