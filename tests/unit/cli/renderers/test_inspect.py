"""Renderer tests for ``novetest inspect``."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_inspect_mixed_sub_reports(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="inspect",
        ok=True,
        data={
            "run_reference": ref(),
            "run_summary": {
                "status": "passed",
                "target_expression": "",
                "target_type": "workspace",
                "engine_name": "pytest",
                "ecosystem": "python",
                "summary_counts": {"passed": 3, "total": 3},
                "tombstoned": False,
            },
            "coverage_outcome": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "missing-derived-facts",
                "detail": "run executed without --coverage",
            },
            "regression_outcome": {
                "kind": "fact-set",
                "baseline_run_reference": ref(),
                "target_run_reference": ref(),
                "summary": {"regressed": 0, "fixed": 0, "still_failing": 0, "still_passing": 3},
            },
            "localization_outcome": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "no_failed_tests",
                "detail": "run has no failed test results",
            },
            "replay_outcome": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "missing-derived-facts",
                "detail": "no replay attempt has been made for this run",
            },
            "sub_reports": {
                "coverage": "unavailable",
                "regression": "available",
                "localization": "unavailable",
                "replay": "unavailable",
            },
        },
    )
    assert render_text(envelope) == snapshot


def test_inspect_tombstoned_with_localization(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="inspect",
        ok=True,
        data={
            "run_reference": ref(),
            "run_summary": {
                "status": "failed",
                "target_expression": "tests/",
                "target_type": "path",
                "engine_name": "pytest",
                "ecosystem": "python",
                "summary_counts": {"passed": 2, "failed": 1, "total": 3},
                "tombstoned": True,
            },
            "coverage_outcome": {"kind": "unavailable", "reason": "missing-derived-facts"},
            "regression_outcome": {"kind": "unavailable", "reason": "no-comparable-baseline"},
            "localization_outcome": {
                "kind": "fact-set",
                "run_reference": ref(),
                "mode": "sbfl_per_test",
                "formula": "ochiai",
                "confidence": "high",
                "top_n": 10,
                "entries": [
                    {
                        "rank": 1,
                        "code_location": {
                            "symbol": "divide",
                            "primary_line": 7,
                            "file": "src/calc.py",
                        },
                        "score_normalized": 1.0,
                    }
                ],
            },
            "replay_outcome": {"kind": "unavailable", "reason": "missing-derived-facts"},
            "sub_reports": {
                "coverage": "unavailable",
                "regression": "unavailable",
                "localization": "available",
                "replay": "unavailable",
            },
        },
    )
    assert render_text(envelope) == snapshot
