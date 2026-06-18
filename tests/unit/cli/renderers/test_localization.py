"""Renderer tests for the ``localization`` sub-app (default verb / latest)."""

from __future__ import annotations

from typing import Any, Callable

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def _entry(rank: int, symbol: str | None, line: int, file: str, score: float) -> dict[str, Any]:
    return {
        "rank": rank,
        "code_location": {
            "symbol": symbol,
            "primary_line": line,
            "file": file,
            "line_range": [line, line],
            "kind": "symbol" if symbol else "file",
        },
        "score_normalized": score,
        "score_raw": score,
        "formula": "ochiai",
    }


def test_localization_fact_set(
    snapshot: SnapshotAssertion, ref: Callable[..., dict[str, Any]]
) -> None:
    envelope = Envelope(
        command="localization",
        ok=True,
        data={
            "localization_outcome": {
                "kind": "fact-set",
                "run_reference": ref(),
                "mode": "sbfl_per_test",
                "formula": "ochiai",
                "confidence": "high",
                "top_n": 10,
                "entries": [
                    _entry(1, "divide", 7, "src/calc.py", 1.0),
                    _entry(2, "helper", 4, "src/calc.py", 0.707),
                    _entry(3, None, 11, "tests/test_calc.py", 0.0),
                ],
            }
        },
    )
    assert render_text(envelope) == snapshot


def test_localization_unavailable(
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
                "detail": "run has no failed test results",
            }
        },
    )
    assert render_text(envelope) == snapshot
