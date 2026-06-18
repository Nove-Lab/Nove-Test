"""Renderer tests for ``novetest run``."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def _entry(
    ref: Callable[..., dict[str, Any]],
    *,
    status: str,
    counts: dict[str, int],
    test_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "entry_id": "entry_0",
        "run_record": {
            "run_reference": ref(),
            "status": status,
            "target_expression": "",
            "target_type": "workspace",
            "engine_name": "pytest",
            "engine_version": "9.0.3",
            "ecosystem": "python",
            "summary_counts": counts,
            "test_results": test_results,
        },
        "stored_at": 1700000000100,
        "tombstoned_at": None,
    }


def test_run_passed(snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]) -> None:
    envelope = Envelope(
        command="run",
        ok=True,
        data={
            "memory_entry": _entry(
                ref,
                status="passed",
                counts={"collected": 3, "passed": 3, "total": 3},
                test_results=[
                    {"node_id": "tests/test_a.py::test_one", "outcome": "passed"},
                ],
            )
        },
    )
    assert render_text(envelope) == snapshot


def test_run_failed_lists_failures(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="run",
        ok=True,
        data={
            "memory_entry": _entry(
                ref,
                status="failed",
                counts={"collected": 3, "passed": 2, "failed": 1, "total": 3},
                test_results=[
                    {"node_id": "tests/test_a.py::test_one", "outcome": "passed"},
                    {"node_id": "tests/test_a.py::test_two", "outcome": "failed"},
                    {"node_id": "tests/test_a.py::test_three", "outcome": "passed"},
                ],
            )
        },
    )
    assert render_text(envelope) == snapshot


def test_run_with_coverage_outcome(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="run",
        ok=True,
        data={
            "memory_entry": _entry(
                ref,
                status="passed",
                counts={"passed": 2, "total": 2},
                test_results=[],
            ),
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
            },
        },
    )
    assert render_text(envelope) == snapshot
