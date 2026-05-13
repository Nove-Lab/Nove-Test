"""Bind a fresh Run Reference to a Run Record."""

from __future__ import annotations

from dataclasses import replace

from novetest.models import RunRecord, RunReference
from novetest.utils.ulid import new_ulid, timestamp_ms_from_ulid


def assign_run_reference(run_record: RunRecord, *, run_id: str | None = None) -> RunRecord:
    """Return ``run_record`` bound to a freshly generated Run Reference.

    The ULID's 48-bit timestamp prefix becomes ``RunReference.created_at``,
    so callers (Memory) can derive the ``memory/runs/YYYY/MM/DD/run_<ulid>/``
    path without consulting any index. ``run_id`` may be supplied to make
    test invocations deterministic.
    """

    ulid = run_id if run_id is not None else new_ulid()
    reference = RunReference(
        run_id=f"run_{ulid}",
        created_at=timestamp_ms_from_ulid(ulid),
    )
    return replace(run_record, run_reference=reference)
