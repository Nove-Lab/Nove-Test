"""Renderers for the kind-discriminated engine-outcome blocks.

Coverage / Regression / Localization / Replay each project their result
onto a ``{"kind": ...}`` discriminated block that appears in MORE than one
verb's envelope (e.g. ``coverage_outcome`` shows up in ``run --coverage``,
``coverage show``, AND ``inspect``). These helpers render one such block to
a line (or list of lines) so the per-verb renderers and the composite
``inspect`` / ``compare`` views share a single formatting source of truth.

Every function is pure and defensive: a missing key falls back to a sane
default rather than raising, because a renderer must never crash on a
slightly-unexpected envelope (the JSON envelope is always available as the
machine-readable fallback).
"""

from __future__ import annotations

from typing import Any

from novetest.cli.renderers._format import (
    GLYPH_FAIL,
    GLYPH_OK,
    GLYPH_UNAVAILABLE,
    GLYPH_UNKNOWN,
    percent,
)


def _reason(block: dict[str, Any]) -> str:
    reason = block.get("reason") or "unknown"
    return f"unavailable ({reason})"


def coverage_outcome_line(block: dict[str, Any]) -> str:
    """One-line summary of a ``coverage_outcome`` block.

    ``fact-set`` → ``per-test · 10/11 statements (86.7%)`` (+ branches when
    the engine reported any); ``unavailable`` → ``— unavailable (<reason>)``.
    """

    if block.get("kind") != "fact-set":
        return f"{GLYPH_UNAVAILABLE} {_reason(block)}"
    summary = block.get("summary", {})
    granularity = block.get("mapping_granularity", "?")
    covered = summary.get("covered_statements", 0)
    total = summary.get("num_statements", 0)
    pct = percent(summary.get("percent_covered", 0.0))
    line = f"{GLYPH_OK} {granularity} · {covered}/{total} statements ({pct})"
    if summary.get("num_branches", 0):
        line += (
            f" · branches {summary.get('covered_branches', 0)}"
            f"/{summary.get('num_branches', 0)}"
        )
    return line


def coverage_delta_line(block: dict[str, Any]) -> str:
    """One-line summary of a ``coverage_delta`` block.

    ``delta`` → ``86.7% → 90.0% (Δ +3.3%) · files +1/-0/~2``;
    ``unavailable`` → ``— unavailable (<reason>)``.
    """

    if block.get("kind") != "delta":
        return f"{GLYPH_UNAVAILABLE} {_reason(block)}"
    before = block.get("summary_before", {}).get("percent_covered", 0.0)
    after = block.get("summary_after", {}).get("percent_covered", 0.0)
    delta = float(after) - float(before)
    added = len(block.get("files_added", []))
    removed = len(block.get("files_removed", []))
    changed = len(block.get("file_deltas", []))
    return (
        f"{percent(before)} → {percent(after)} (Δ {delta:+.1f}%) · "
        f"files +{added}/-{removed}/~{changed}"
    )


def regression_outcome_line(block: dict[str, Any]) -> str:
    """One-line summary of a ``regression_outcome`` block.

    ``fact-set`` → ``✓ clean · regressed=0 fixed=0 still_failing=0`` (or
    ``✗ regressions ...`` when any test regressed); ``unavailable`` →
    ``— unavailable (<reason>)``.
    """

    if block.get("kind") != "fact-set":
        return f"{GLYPH_UNAVAILABLE} {_reason(block)}"
    summary = block.get("summary", {})
    regressed = summary.get("regressed", 0)
    fixed = summary.get("fixed", 0)
    still_failing = summary.get("still_failing", 0)
    if regressed:
        glyph, status = GLYPH_FAIL, "regressions"
    else:
        glyph, status = GLYPH_OK, "clean"
    return (
        f"{glyph} {status} · regressed={regressed} fixed={fixed} "
        f"still_failing={still_failing}"
    )


def localization_outcome_lines(block: dict[str, Any]) -> list[str]:
    """Header + ranked-entry lines for a ``localization_outcome`` block.

    ``fact-set`` →::

        sbfl_per_test · ochiai · 6 entries · confidence=high
          1. symbol@7 in tests/test_counter.py (1.000)
          ...

    ``unavailable`` → a single ``— unavailable (<reason>)`` line.
    """

    if block.get("kind") != "fact-set":
        return [f"{GLYPH_UNAVAILABLE} {_reason(block)}"]
    entries = block.get("entries", [])
    mode = block.get("mode", "?")
    formula = block.get("formula", "?")
    confidence = block.get("confidence", "?")
    header = (
        f"{mode} · {formula} · {len(entries)} entries · confidence={confidence}"
    )
    lines = [header]
    for entry in entries:
        loc = entry.get("code_location", {})
        symbol = loc.get("symbol")
        primary_line = loc.get("primary_line", "?")
        file_path = loc.get("file", "?")
        if symbol:
            where = f"{symbol}@{primary_line} in {file_path}"
        else:
            where = f"{file_path}:{primary_line}"
        score = entry.get("score_normalized", 0.0)
        lines.append(f"  {entry.get('rank', '?')}. {where} ({float(score):.3f})")
    return lines


def replay_outcome_line(block: dict[str, Any]) -> str:
    """One-line summary of a ``replay_outcome`` block.

    ``reproducible`` → ``✓ reproducible · 3/3``; ``inconsistent`` →
    ``✗ inconsistent · 2/5 failed``; ``unable_to_replay`` →
    ``? unable_to_replay (<reason>)``; ``unavailable`` →
    ``? unavailable (<reason>)``.
    """

    if block.get("kind") != "replay-result":
        return f"{GLYPH_UNKNOWN} {_reason(block)}"
    classification = block.get("classification", "?")
    total = block.get("reruns_total", 0)
    failed = block.get("reruns_failed", 0)
    if classification == "reproducible":
        return f"{GLYPH_OK} {classification} · {total - failed}/{total}"
    if classification == "inconsistent":
        return f"{GLYPH_FAIL} {classification} · {failed}/{total} failed"
    reason = block.get("reason")
    suffix = f" ({reason})" if reason else ""
    return f"{GLYPH_UNKNOWN} {classification}{suffix}"
