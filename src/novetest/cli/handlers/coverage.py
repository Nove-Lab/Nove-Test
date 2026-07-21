"""Coverage subcommand handlers: ``coverage show`` / ``coverage diff``.

Extracted verbatim from ``cli/app.py`` at the W3/S47 decomposition (ORC-01).
Both are cache-read only — they never auto-derive. Pure motion — the wire
contract is unchanged.
"""

from __future__ import annotations

from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _resolve_run_reference,
    _store_corrupt_envelope,
)
from novetest.cli.output import EXIT_OK, EXIT_STORAGE, Envelope
from novetest.coverage import compare_coverage_facts, get_coverage_facts
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.projection import (
    coverage_delta_payload,
    coverage_outcome_payload,
)


def coverage_show(run_id: str) -> None:
    """Show the persisted Coverage Fact set for ``run_id``.

    Cache-read only — this verb never auto-derives. When the run exists
    but no ``coverage_facts.json`` is on disk, the envelope reports
    ``coverage_outcome.kind == "unavailable"`` with reason
    ``missing-derived-facts`` (the run was executed without
    ``novetest run --coverage``).
    """
    store = _require_store("coverage.show")
    ref = _resolve_run_reference(store, "coverage.show", run_id)
    try:
        outcome = get_coverage_facts(store, ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (record corrupted between the lookup scan
        # and the engine's targeted read — TOCTOU): storage error, exit 5.
        _emit_and_exit(_store_corrupt_envelope("coverage.show", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(
            command="coverage.show",
            ok=True,
            data={"coverage_outcome": coverage_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


def coverage_diff(baseline_run_id: str, target_run_id: str) -> None:
    """Diff the persisted Coverage Fact sets of two runs.

    Surfaces ``coverage_delta.kind == "delta"`` on success and
    ``coverage_delta.kind == "unavailable"`` when either side lacks
    derived facts (the unavailable outcome is propagated from
    ``compare_coverage_facts``).
    """
    store = _require_store("coverage.diff")
    baseline_ref = _resolve_run_reference(store, "coverage.diff", baseline_run_id)
    target_ref = _resolve_run_reference(store, "coverage.diff", target_run_id)
    try:
        outcome = compare_coverage_facts(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("coverage.diff", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(
            command="coverage.diff",
            ok=True,
            data={"coverage_delta": coverage_delta_payload(outcome)},
        ),
        EXIT_OK,
    )
