"""Renderer tests for the ``memory`` sub-app (list / show / delete)."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def _entry(
    ref: Callable[..., dict[str, Any]],
    run_id: str,
    *,
    created_at: int,
    status: str = "passed",
    tombstoned: bool = False,
) -> dict[str, Any]:
    return {
        "entry_id": f"entry_{run_id}",
        "run_record": {
            "run_reference": ref(run_id, created_at),
            "status": status,
            "target_expression": "",
            "target_type": "workspace",
            "engine_name": "pytest",
            "engine_version": "9.0.3",
            "ecosystem": "python",
            "summary_counts": {"collected": 3, "passed": 3, "total": 3},
            "started_at": created_at + 80,
            "completed_at": created_at + 171,
            "test_results": [],
        },
        "stored_at": created_at + 200,
        "tombstoned_at": (created_at + 500) if tombstoned else None,
        "has_coverage_facts": False,
        "has_regression_facts": False,
        "has_localization_findings": False,
        "has_replay_result": False,
    }


def test_memory_list(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    entries = [
        _entry(ref, "01TESTRUN000000000000000000", created_at=1700000500000),
        _entry(
            ref,
            "01TESTRUN111111111111111111",
            created_at=1700000000000,
            status="failed",
            tombstoned=True,
        ),
    ]
    envelope = Envelope(
        command="memory.list", ok=True, data={"count": 2, "entries": entries}
    )
    assert render_text(envelope) == snapshot


def test_memory_list_empty(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="memory.list", ok=True, data={"count": 0, "entries": []}
    )
    assert render_text(envelope) == snapshot


def test_memory_show(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="memory.show",
        ok=True,
        data={
            "memory_entry": _entry(
                ref, "01TESTRUN000000000000000000", created_at=1700000000000
            )
        },
    )
    assert render_text(envelope) == snapshot


def test_memory_delete(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="memory.delete",
        ok=True,
        data={
            "memory_entry": _entry(
                ref,
                "01TESTRUN000000000000000000",
                created_at=1700000000000,
                tombstoned=True,
            )
        },
    )
    assert render_text(envelope) == snapshot
