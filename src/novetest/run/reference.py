"""Bind a fresh Run Reference to a Run Record."""

from __future__ import annotations

from dataclasses import replace

from novetest.models import RunRecord, RunReference
from novetest.utils.ulid import extract_timestamp_ms, generate_ulid


def assign_run_reference(run_record: RunRecord, *, run_id: str | None = None) -> RunRecord:
    """Return ``run_record`` bound to a freshly generated Run Reference.

    The ``run_id`` is a raw ULID (no ``run_`` prefix — Memory's path layout
    adds the prefix when materializing ``memory/runs/.../run_<ulid>/``,
    per `foundations.md` §4). The ULID's 48-bit timestamp prefix becomes
    ``RunReference.created_at``. ``run_id`` may be supplied to make test
    invocations deterministic.
    """

    ulid = run_id if run_id is not None else generate_ulid()
    reference = RunReference(
        run_id=ulid,
        created_at=extract_timestamp_ms(ulid),
    )
    return replace(run_record, run_reference=reference)
