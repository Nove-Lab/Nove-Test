"""Renderer tests for ``novetest compare``."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_compare_regression_and_coverage_delta(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="compare",
        ok=True,
        data={
            "regression_outcome": {
                "kind": "fact-set",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "summary": {"regressed": 1, "fixed": 0, "still_failing": 0, "still_passing": 2},
            },
            "coverage_delta": {
                "kind": "delta",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "summary_before": {"percent_covered": 80.0},
                "summary_after": {"percent_covered": 86.66666666666667},
                "files_added": ["src/new.py"],
                "files_removed": [],
                "file_deltas": [{"file_path": "src/calc.py"}],
            },
        },
    )
    assert render_text(envelope) == snapshot


def test_compare_coverage_unavailable(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="compare",
        ok=True,
        data={
            "regression_outcome": {
                "kind": "fact-set",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "summary": {"regressed": 0, "fixed": 0, "still_failing": 0, "still_passing": 3},
            },
            "coverage_delta": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "missing-derived-facts",
                "detail": "baseline lacks coverage facts",
            },
        },
    )
    assert render_text(envelope) == snapshot
