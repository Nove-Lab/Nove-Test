"""Regression subcommand handlers: ``regression compare`` / ``regression latest``.

Extracted verbatim from ``cli/app.py`` at the W3/S47 decomposition (ORC-01).
Pure motion — the wire contract is unchanged. (The top-level ``compare`` verb,
which composes Regression + Coverage, lives in ``handlers/compare.py``.)
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
from novetest.orchestration.projection import regression_outcome_payload
from novetest.regression import compare_runs, derive_latest_regression


def regression_compare(baseline_run_id: str, target_run_id: str) -> None:
    """Compare two specific Run Records and emit Regression Facts.

    Calls ``compare_runs(store, baseline_ref, target_ref)`` — the cache-
    aware entry point. On cache miss it derives and persists; on cache
    hit it reads. Tombstoned inputs surface ``REASON_RUN_TOMBSTONED`` per
    decision §C.1 even when a stale cached file exists on disk.

    A stale or fake ``run_id`` short-circuits BEFORE ``compare_runs`` is
    invoked: ``_resolve_run_reference`` emits a structured ``not-found``
    envelope and exits 2, mirroring ``coverage diff``. All other
    unavailable outcomes (engine-mismatch, target-mismatch, tombstoned,
    etc.) surface as ``regression_outcome.kind == "unavailable"`` with
    ``ok: true``, exit 0 — the transport succeeded, the unavailability
    is data.
    """

    store = _require_store("regression.compare")
    baseline_ref = _resolve_run_reference(store, "regression.compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "regression.compare", target_run_id)
    try:
        outcome = compare_runs(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("regression.compare", str(exc)), EXIT_STORAGE
        )
    _emit_and_exit(
        Envelope(
            command="regression.compare",
            ok=True,
            data={"regression_outcome": regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


def regression_latest() -> None:
    """Resolve the latest comparable pair for the active target and emit Regression Facts.

    Composes the engine's ``derive_latest_regression(store)`` end-to-end:
    latest live run → its ``target_expression`` → most recent prior live
    run on the same target → ``compare_runs`` of the pair. An empty store,
    or one whose runs are all tombstoned, surfaces
    ``regression_outcome.kind == "unavailable"`` with reason
    ``no-comparable-baseline``.
    """

    store = _require_store("regression.latest")
    try:
        outcome = derive_latest_regression(store)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("regression.latest", str(exc)), EXIT_STORAGE
        )
    _emit_and_exit(
        Envelope(
            command="regression.latest",
            ok=True,
            data={"regression_outcome": regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )
