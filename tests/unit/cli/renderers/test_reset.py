"""Renderer tests for ``novetest reset`` text surface.

Snapshots the three-line summary across the full, all-zero, and partial
(zero-suppressed) ``items_removed`` shapes, plus the no-engine readiness
branch. Routes through ``render_text`` so the registry wiring is exercised.
"""

from __future__ import annotations

from typing import Any

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope, EnvelopeError
from novetest.cli.renderers import render_text

_READY = {
    "state": "ready",
    "engine": "pytest",
    "ecosystem": "python",
    "engine_version": "8.0.0",
    "evidence": ["pyproject.toml"],
    "issues": [],
}


def _reset_envelope(
    items_removed: dict[str, int], readiness: dict[str, Any]
) -> Envelope:
    return Envelope(
        command="reset",
        ok=True,
        data={
            "store_path": "/work/.novetest",
            "store_state": "ready",
            "previous_initialized_at": 1_717_939_496_000,
            "initialized_at": 1_719_215_123_000,
            "items_removed": items_removed,
            "engine_readiness": readiness,
            # ORC-20 additive envelope key. The text renderer deliberately
            # does not surface it (init's renderer doesn't either — the
            # readiness line already names the engine), so the snapshots
            # below must stay byte-identical with the key present.
            "pinned_engine": {"ecosystem": "python", "engine_name": "pytest"},
        },
    )


def test_render_reset_full(snapshot: SnapshotAssertion) -> None:
    envelope = _reset_envelope(
        {
            "runs": 12,
            "tombstones": 1,
            "coverage_facts": 12,
            "regression_pairs": 7,
            "localization_findings": 8,
            "replay_results": 2,
        },
        _READY,
    )
    assert render_text(envelope) == snapshot


def test_render_reset_all_zero_renders_nothing(snapshot: SnapshotAssertion) -> None:
    envelope = _reset_envelope(
        {
            "runs": 0,
            "tombstones": 0,
            "coverage_facts": 0,
            "regression_pairs": 0,
            "localization_findings": 0,
            "replay_results": 0,
        },
        _READY,
    )
    assert render_text(envelope) == snapshot


def test_render_reset_partial_suppresses_zeros_and_no_engine(
    snapshot: SnapshotAssertion,
) -> None:
    envelope = _reset_envelope(
        {
            "runs": 1,
            "tombstones": 0,
            "coverage_facts": 0,
            "regression_pairs": 0,
            "localization_findings": 0,
            "replay_results": 0,
        },
        {
            "state": "no-engine",
            "engine": None,
            "ecosystem": None,
            "engine_version": None,
            "evidence": [],
            "issues": ["no recognized test engine in workspace"],
        },
    )
    assert render_text(envelope) == snapshot


def test_render_reset_error_gates_to_error_block() -> None:
    envelope = Envelope(
        command="reset",
        ok=False,
        errors=(
            EnvelopeError(
                code="confirm-required",
                message="`novetest reset` is destructive. Pass --confirm to acknowledge.",
            ),
        ),
    )
    rendered = render_text(envelope)
    assert rendered.startswith("✗ reset")
    assert "confirm-required:" in rendered
