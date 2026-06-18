"""Text renderers for the ``localization`` sub-app: default verb / latest.

Command tokens ``"localization"`` / ``"localization.latest"``. Both render
the ranked SBFL entries; ``latest`` differs only in which run the engine
resolved (reflected in the run id appended to the header).
"""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._outcomes import localization_outcome_lines


def _render(envelope: Envelope) -> str:
    outcome = envelope.data.get("localization_outcome", {})
    lines = localization_outcome_lines(outcome)
    reference = outcome.get("run_reference") or {}
    run_id = reference.get("run_id", "?")
    # Append the run id to the header line (lines[0] always exists).
    lines[0] = f"{lines[0]} · run_id={run_id}"
    return "\n".join(lines)


def render_localization(envelope: Envelope) -> str:
    return _render(envelope)


def render_localization_latest(envelope: Envelope) -> str:
    return _render(envelope)
