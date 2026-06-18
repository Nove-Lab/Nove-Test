"""Text renderer for ``novetest inspect`` (command token ``"inspect"``).

Composite single-run view: a run-summary header plus one line per
sub-report (coverage / regression / localization / replay). Each sub-line
re-uses the shared ``_outcomes`` block formatters so ``inspect`` agrees
with the dedicated per-engine verbs. The full Localization ranking is
intentionally NOT expanded here (only its header line) — ``inspect`` is a
summary; ``novetest localization <run_id>`` shows the ranked entries.
"""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import run_status_glyph, target_label
from novetest.cli.renderers._outcomes import (
    coverage_outcome_line,
    localization_outcome_lines,
    regression_outcome_line,
    replay_outcome_line,
)


def render_inspect(envelope: Envelope) -> str:
    data = envelope.data
    run_id = data.get("run_reference", {}).get("run_id", "?")
    summary = data.get("run_summary", {})
    status = summary.get("status", "?")
    engine = summary.get("engine_name", "?")
    ecosystem = summary.get("ecosystem", "?")
    target = target_label(summary.get("target_expression", ""))

    header = (
        f"{run_status_glyph(status)} {run_id} · {status} · "
        f"{engine} ({ecosystem}) · target={target}"
    )
    if summary.get("tombstoned"):
        header += " · tombstoned"

    localization_header = localization_outcome_lines(
        data.get("localization_outcome", {})
    )[0]
    lines = [
        header,
        "",
        f"  coverage      {coverage_outcome_line(data.get('coverage_outcome', {}))}",
        f"  regression    {regression_outcome_line(data.get('regression_outcome', {}))}",
        f"  localization  {localization_header}",
        f"  replay        {replay_outcome_line(data.get('replay_outcome', {}))}",
    ]
    return "\n".join(lines)
