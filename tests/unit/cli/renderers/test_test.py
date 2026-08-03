"""Renderer tests for the integrated ``novetest test`` verb."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_test_all_green(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="test",
        ok=True,
        data={
            "run_reference": ref(),
            "stage_eligibility": {
                "coverage": "available",
                "regression": "unavailable",
                "localization": "unavailable",
                "replay": "not_run",
            },
            "recommendation_schema_version": 1,
            "recommendations": [
                {
                    "recommendation_id": "rec_x_aaaa",
                    "category": "all_green",
                    "priority": 7,
                    "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
                    "slots": {"passed": 3, "skipped": 0, "total_tests": 3},
                    "evidence_citations": [
                        {"kind": "run_reference", "run_reference": ref(), "selector": {}}
                    ],
                }
            ],
        },
    )
    assert render_text(envelope) == snapshot


def test_test_investigate_and_unavailable(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="test",
        ok=True,
        data={
            "run_reference": ref(),
            "stage_eligibility": {
                "coverage": "available",
                "regression": "unavailable",
                "localization": "sbfl_per_test",
                "replay": "not_run",
            },
            "recommendation_schema_version": 1,
            "recommendations": [
                {
                    "recommendation_id": "rec_x_bbbb",
                    "category": "investigate_location",
                    "priority": 2,
                    "summary": "Investigate `divide`@7 in `src/calc.py` (rank 1, ochiai=1.000, sbfl_per_test).",
                    "slots": {"file": "src/calc.py", "primary_line": 7, "rank": 1},
                    "evidence_citations": [
                        {
                            "kind": "localization_finding",
                            "run_reference": ref(),
                            "finding_id": "loc_run_x",
                            "selector": {"rank": 1, "file": "src/calc.py", "primary_line": 7},
                            "mode": "sbfl_per_test",
                        }
                    ],
                },
                {
                    "recommendation_id": "rec_x_cccc",
                    "category": "unavailable_analysis",
                    "priority": 6,
                    "summary": "Downstream analysis incomplete: regression (no-comparable-baseline).",
                    "slots": {"unavailable_stages": ["regression"]},
                    "evidence_citations": [
                        {"kind": "run_reference", "run_reference": ref(), "selector": {}}
                    ],
                },
            ],
        },
    )
    assert render_text(envelope) == snapshot


def test_test_no_recommendations_is_single_line(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="test",
        ok=True,
        data={
            "run_reference": ref(),
            "stage_eligibility": {},
            "recommendation_schema_version": 1,
            "recommendations": [],
        },
    )
    assert render_text(envelope) == snapshot
