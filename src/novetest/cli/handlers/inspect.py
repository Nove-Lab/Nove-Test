"""``novetest inspect <run_id>`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``. Composes the aggregated single-run
view (Run Record + Coverage / Regression / Localization / Replay sections)
via ``build_inspect_view``. Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

from novetest.cli._shared import (
    _emit_and_exit,
    _lookup_miss_exit,
    _require_store,
    _store_corrupt_envelope,
)
from novetest.cli.output import EXIT_OK, EXIT_STORAGE, Envelope
from novetest.memory import ProjectStoreCorruptError, SkippedRecord
from novetest.orchestration.workflows import build_inspect_view


def inspect_cmd(run_id: str) -> None:
    """Show the aggregated single-run view for ``run_id``.

    Composes the Run Record summary with the persisted Coverage Facts (the
    same ``coverage_outcome`` block ``coverage show`` emits), a Regression
    section computed against the most-recent live prior run on the same
    target, AND a Localization section read cache-only from the per-run
    ``localization_findings.json`` (the same ``localization_outcome`` block
    ``novetest localization`` emits) — each flips its
    ``sub_reports[...]`` marker from ``"unavailable"`` to ``"available"``
    when its evidence resolves. Replay remains present-but-``unavailable``
    until its engine lands in Phase 5. ``inspect`` spawns no engine
    subprocess (it runs no test); its Coverage / Localization / Replay
    sections are strictly cache-only reads. Its Regression section, by
    contrast, COMPOSES ``resolve_baseline_for_run`` + ``compare_runs`` and so
    DERIVES the pair's facts on a cache miss (self-heal) — the intended
    ORC-25 asymmetry with ``status``, which is strictly cache-only (Gate-1
    D3=A, 2026-07-20; see ``workflows/inspect.py``).

    A stale or fake ``run_id`` surfaces a structured ``not-found`` error
    (exit 2), mirroring ``memory show``. Tombstoned runs remain inspectable.
    An id whose record is corrupt on disk escalates to ``store-corrupt``
    (exit 5) instead — the Gate-1 Q1-A addressed-lookup convention
    (``_lookup_miss_exit``); warning-free like every non-memory verb.
    """
    store = _require_store("inspect")
    skipped: list[SkippedRecord] = []
    try:
        view = build_inspect_view(store, run_id, skipped=skipped)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("inspect", str(exc)), EXIT_STORAGE)
    if view is None:
        _lookup_miss_exit("inspect", run_id, skipped)
    _emit_and_exit(
        Envelope(command="inspect", ok=True, data=view.to_dict()),
        EXIT_OK,
    )
