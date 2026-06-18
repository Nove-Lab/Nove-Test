"""Text renderer for ``novetest compare`` (command token ``"compare"``).

Composite regression + coverage-delta view for a run pair.
"""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._outcomes import (
    coverage_delta_line,
    regression_outcome_line,
)


def render_compare(envelope: Envelope) -> str:
    data = envelope.data
    return "\n".join(
        [
            f"regression: {regression_outcome_line(data.get('regression_outcome', {}))}",
            f"coverage:   {coverage_delta_line(data.get('coverage_delta', {}))}",
        ]
    )
