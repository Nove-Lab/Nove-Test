"""Renderer tests for the ``regression`` sub-app (compare / latest)."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_regression_compare_clean(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="regression.compare",
        ok=True,
        data={
            "regression_outcome": {
                "kind": "fact-set",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "summary": {"regressed": 0, "fixed": 0, "still_failing": 0, "still_passing": 3},
            }
        },
    )
    assert render_text(envelope) == snapshot


def test_regression_compare_with_regressions(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="regression.compare",
        ok=True,
        data={
            "regression_outcome": {
                "kind": "fact-set",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "summary": {"regressed": 2, "fixed": 1, "still_failing": 0, "still_passing": 4},
            }
        },
    )
    assert render_text(envelope) == snapshot


def test_regression_latest_unavailable(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="regression.latest",
        ok=True,
        data={
            "regression_outcome": {
                "kind": "unavailable",
                "baseline_run_reference": None,
                "target_run_reference": None,
                "reason": "no-comparable-baseline",
                "detail": "",
            }
        },
    )
    assert render_text(envelope) == snapshot
