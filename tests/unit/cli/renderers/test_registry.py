"""Renderer tests for the dispatch layer: errors, warnings, fallback, routing."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import (
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    not_implemented_envelope,
)
from novetest.cli.renderers import render_text


def test_error_uninitialized(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="status",
        ok=False,
        errors=(
            EnvelopeError(
                code="uninitialized",
                message=(
                    "No Project Store found in this directory or any ancestor. "
                    "Run `novetest init` to create one."
                ),
            ),
        ),
    )
    assert render_text(envelope) == snapshot


def test_error_with_install_hint_detail(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="run",
        ok=False,
        errors=(
            EnvelopeError(
                code="adapter-engine-missing",
                message="pytest is not installed",
                details={"install_hint": "pip install pytest"},
            ),
        ),
    )
    assert render_text(envelope) == snapshot


def test_error_not_implemented_stub(snapshot: SnapshotAssertion) -> None:
    assert render_text(not_implemented_envelope("future.verb")) == snapshot


def test_warnings_appended_after_body(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="localization",
        ok=True,
        data={
            "localization_outcome": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "no_failed_tests",
                "detail": "",
            }
        },
        warnings=(
            EnvelopeWarning(
                code="localization-formula-noop-in-mode",
                message="requested --formula='op2' is a no-op in 'failure_proximity' mode",
            ),
        ),
    )
    assert render_text(envelope) == snapshot


def test_fallback_for_unknown_command() -> None:
    envelope = Envelope(command="future.verb", ok=True, data={"x": 1})
    rendered = render_text(envelope)
    assert rendered.startswith("future.verb: no human renderer")
    assert "--output json" in rendered


def test_errors_gate_before_command_dispatch() -> None:
    # A known command (``test``) carrying errors must render the error block,
    # NOT the test renderer.
    envelope = Envelope(
        command="test",
        ok=False,
        errors=(EnvelopeError(code="engine-not-ready", message="pytest not ready"),),
    )
    rendered = render_text(envelope)
    assert rendered.startswith("✗ test")
    assert "engine-not-ready: pytest not ready" in rendered
