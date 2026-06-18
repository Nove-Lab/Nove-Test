"""Text renderers for the ``regression`` sub-app: compare / latest.

Command tokens ``"regression.compare"`` / ``"regression.latest"``. Both
render identically (headline + resolved pair); ``latest`` differs only in
how the engine resolved the pair, which is already reflected in the
references the block carries.
"""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._outcomes import regression_outcome_line


def _render(envelope: Envelope) -> str:
    outcome = envelope.data.get("regression_outcome", {})
    line = regression_outcome_line(outcome)
    baseline = outcome.get("baseline_run_reference") or {}
    target = outcome.get("target_run_reference") or {}
    if outcome.get("kind") == "fact-set" and baseline and target:
        return (
            f"{line}\n  baseline={baseline.get('run_id', '?')} "
            f"target={target.get('run_id', '?')}"
        )
    return line


def render_regression_compare(envelope: Envelope) -> str:
    return _render(envelope)


def render_regression_latest(envelope: Envelope) -> str:
    return _render(envelope)
