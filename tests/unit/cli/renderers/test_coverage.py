"""Renderer tests for the ``coverage`` sub-app (show / diff)."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_coverage_show_fact_set(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="coverage.show",
        ok=True,
        data={
            "coverage_outcome": {
                "kind": "fact-set",
                "mapping_granularity": "per-test",
                "run_reference": ref(),
                "summary": {
                    "covered_statements": 10,
                    "num_statements": 11,
                    "percent_covered": 86.66666666666667,
                    "covered_branches": 3,
                    "num_branches": 4,
                },
            }
        },
    )
    assert render_text(envelope) == snapshot


def test_coverage_show_unavailable(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="coverage.show",
        ok=True,
        data={
            "coverage_outcome": {
                "kind": "unavailable",
                "run_reference": ref(),
                "reason": "missing-derived-facts",
                "detail": "run executed without --coverage",
            }
        },
    )
    assert render_text(envelope) == snapshot


def test_coverage_diff(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="coverage.diff",
        ok=True,
        data={
            "coverage_delta": {
                "kind": "delta",
                "baseline_run_reference": ref("01TESTBASELINE00000000000000"),
                "target_run_reference": ref(),
                "baseline_granularity": "per-test",
                "target_granularity": "per-test",
                "summary_before": {"percent_covered": 80.0},
                "summary_after": {"percent_covered": 90.0},
                "files_added": ["src/new.py"],
                "files_removed": [],
                "file_deltas": [{"file_path": "src/calc.py"}, {"file_path": "src/util.py"}],
            }
        },
    )
    assert render_text(envelope) == snapshot
