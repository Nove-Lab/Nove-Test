"""Top-level ``novetest compare`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``. Thin transport over the
``build_compare_view`` workflow, which emits both ``regression_outcome`` and
``coverage_delta`` in one envelope. Pure motion — the wire contract is
unchanged.
"""

from __future__ import annotations

from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _resolve_run_reference,
    _store_corrupt_envelope,
)
from novetest.cli.output import EXIT_OK, EXIT_STORAGE, Envelope
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.workflows import build_compare_view


def compare_cmd(baseline_run_id: str, target_run_id: str) -> None:
    """Composed Regression + Coverage view for a specific pair.

    Thin transport over the ``build_compare_view`` workflow
    (``orchestration/workflows/compare.py``), which emits both
    ``regression_outcome`` (from ``compare_runs``) and ``coverage_delta``
    (from ``compare_coverage_facts``) in the same envelope. When either
    side lacks coverage facts, ``coverage_delta`` surfaces
    ``kind: "unavailable"`` with the propagated reason — the same
    projection ``coverage diff`` emits. Distinct from
    ``regression compare`` (which emits ``regression_outcome`` only).
    """

    store = _require_store("compare")
    baseline_ref = _resolve_run_reference(store, "compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "compare", target_run_id)
    try:
        view = build_compare_view(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("compare", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(command="compare", ok=True, data=view.to_dict()),
        EXIT_OK,
    )
