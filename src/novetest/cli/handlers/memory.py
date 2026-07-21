"""Memory subcommand handlers: ``memory list`` / ``show`` / ``delete``.

Extracted verbatim from ``cli/app.py`` at the W3/S47 decomposition (ORC-01),
including the MEM-05 ``_corrupt_record_warnings`` projector these verbs own.
Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

from novetest.cli._shared import (
    _emit_and_exit,
    _lookup_miss_exit,
    _require_store,
    _store_corrupt_envelope,
)
from novetest.cli.output import (
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
)
from novetest.memory import (
    ProjectStoreCorruptError,
    RunEvidenceNotFoundError,
    SkippedRecord,
    delete_run_evidence,
    find_entry_by_run_id,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models import RunReference


def _corrupt_record_warnings(
    skipped: list[SkippedRecord],
) -> tuple[EnvelopeWarning, ...]:
    """Project MEM-05 scan skips onto envelope ``warnings[]`` entries.

    One warning per skipped record; the message carries the corrupt file's
    path verbatim so an operator can locate it without grepping. Emitted only
    by the memory verbs — non-CLI consumers of the scan interfaces get the
    isolation (skip, don't crash) without a warning channel.
    """
    return tuple(
        EnvelopeWarning(
            code="corrupt-run-record-skipped",
            message=f"Skipped unreadable run record at {s.path}: {s.error}",
            details={"path": str(s.path)},
        )
        for s in skipped
    )


def memory_list() -> None:
    """List Run History newest-first."""
    store = _require_store("memory.list")
    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)
    _emit_and_exit(
        Envelope(
            command="memory.list",
            ok=True,
            data={
                "count": len(entries),
                "entries": [e.to_dict() for e in entries],
            },
            warnings=_corrupt_record_warnings(skipped),
        ),
        EXIT_OK,
    )


def memory_show(run_id: str) -> None:
    """Show the Memory Entry for ``run_id`` (live or tombstoned)."""
    store = _require_store("memory.show")
    skipped: list[SkippedRecord] = []
    target = find_entry_by_run_id(store, run_id, skipped=skipped)
    warnings = _corrupt_record_warnings(skipped)
    if target is None:
        # Q1-A: a miss on an id the scan skipped-as-corrupt escalates to
        # store-corrupt / exit 5; genuinely-absent ids stay not-found.
        _lookup_miss_exit("memory.show", run_id, skipped, warnings=warnings)
    ref = target.run_record.run_reference
    try:
        entry = retrieve_run_evidence(store, ref)
    except RunEvidenceNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="memory.show",
                ok=False,
                errors=(EnvelopeError(code="not-found", message=str(exc)),),
                warnings=warnings,
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        # Residual loud path (scan hit, then the targeted read found the
        # record corrupt — TOCTOU): typed storage error → exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("memory.show", str(exc), warnings=warnings),
            EXIT_STORAGE,
        )
    _emit_and_exit(
        Envelope(
            command="memory.show",
            ok=True,
            data={"memory_entry": entry.to_dict()},
            warnings=warnings,
        ),
        EXIT_OK,
    )


def memory_delete(run_id: str) -> None:
    """Tombstone the Memory Entry for ``run_id`` (POSIX-atomic rename)."""
    store = _require_store("memory.delete")
    skipped: list[SkippedRecord] = []
    target = find_entry_by_run_id(store, run_id, skipped=skipped)
    warnings = _corrupt_record_warnings(skipped)
    if target is None:
        # Q1-A: a corrupt record CANNOT be tombstoned (tombstoning re-writes
        # the parsed record) — exit 5 with the path is the honest outcome;
        # manual removal of the named run dir is the recovery (docs).
        _lookup_miss_exit("memory.delete", run_id, skipped, warnings=warnings)
    ref = RunReference(
        run_id=target.run_record.run_reference.run_id,
        created_at=target.run_record.run_reference.created_at,
    )
    try:
        entry = delete_run_evidence(store, ref)
    except RunEvidenceNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="memory.delete",
                ok=False,
                errors=(EnvelopeError(code="not-found", message=str(exc)),),
                warnings=warnings,
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        # Residual loud path (record turned corrupt between scan and the
        # tombstone's own targeted read — TOCTOU): exit 5, nothing mutated.
        _emit_and_exit(
            _store_corrupt_envelope("memory.delete", str(exc), warnings=warnings),
            EXIT_STORAGE,
        )
    _emit_and_exit(
        Envelope(
            command="memory.delete",
            ok=True,
            data={"memory_entry": entry.to_dict()},
            warnings=warnings,
        ),
        EXIT_OK,
    )
