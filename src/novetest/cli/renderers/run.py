"""Text renderer for ``novetest run`` (command token ``"run"``)."""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import GLYPH_FAIL, run_status_glyph
from novetest.cli.renderers._outcomes import coverage_outcome_line

_FAILED_OUTCOMES = frozenset({"failed", "errored", "error"})


def render_run(envelope: Envelope) -> str:
    """Run summary line, failed-test list, and optional coverage line.

    ::

        ✓ passed · 3/3 · run_id=01HX...
          coverage: ✓ per-test · 10/11 statements (86.7%)
    """

    data = envelope.data
    entry = data.get("memory_entry", {})
    record = entry.get("run_record", {})
    status = record.get("status", "?")
    counts = record.get("summary_counts", {})
    passed = counts.get("passed", 0)
    total = counts.get("total", 0)
    run_id = record.get("run_reference", {}).get("run_id", "?")

    glyph = run_status_glyph(status)
    lines = [f"{glyph} {status} · {passed}/{total} · run_id={run_id}"]

    failed = [
        result
        for result in record.get("test_results", [])
        if result.get("outcome") in _FAILED_OUTCOMES
    ]
    if failed:
        lines.append("  failed tests:")
        for result in failed:
            lines.append(f"    {GLYPH_FAIL} {result.get('node_id', '?')}")

    coverage = data.get("coverage_outcome")
    if coverage is not None:
        lines.append(f"  coverage: {coverage_outcome_line(coverage)}")
    return "\n".join(lines)
