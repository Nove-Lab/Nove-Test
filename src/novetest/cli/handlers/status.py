"""``novetest status`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``. Summarizes the active Project Store:
latest run + per-sub-report availability, via the cache-only
``build_status_view`` workflow. Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _store_corrupt_envelope,
)
from novetest.cli.output import EXIT_OK, EXIT_STORAGE, Envelope
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.workflows import build_status_view


def status() -> None:
    """Summarize the current Project Store: latest run + sub-report availability."""
    store = _require_store("status")
    try:
        view = build_status_view(store)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (the view's cache-only readers do targeted
        # reads via retrieve_run_evidence — TOCTOU): exit 5.
        _emit_and_exit(_store_corrupt_envelope("status", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(command="status", ok=True, data=view.to_dict()),
        EXIT_OK,
    )
