"""Text renderers for the ``coverage`` sub-app: show / diff.

Command tokens ``"coverage.show"`` / ``"coverage.diff"``.
"""

from __future__ import annotations

from novetest.cli.output import Envelope
from novetest.cli.renderers._outcomes import (
    coverage_delta_line,
    coverage_outcome_line,
)


def render_coverage_show(envelope: Envelope) -> str:
    """Coverage summary line + run id (or unavailable reason)."""

    outcome = envelope.data.get("coverage_outcome", {})
    reference = outcome.get("run_reference") or {}
    run_id = reference.get("run_id", "?")
    return f"{coverage_outcome_line(outcome)} · run_id={run_id}"


def render_coverage_diff(envelope: Envelope) -> str:
    """Coverage delta headline + the resolved baseline → target pair."""

    delta = envelope.data.get("coverage_delta", {})
    line = coverage_delta_line(delta)
    baseline = delta.get("baseline_run_reference") or {}
    target = delta.get("target_run_reference") or {}
    if delta.get("kind") == "delta" and baseline and target:
        header = (
            f"coverage diff · {baseline.get('run_id', '?')} → "
            f"{target.get('run_id', '?')}"
        )
        return f"{header}\n  {line}"
    return f"coverage diff · {line}"
