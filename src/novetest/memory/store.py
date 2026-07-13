"""Run-evidence persistence over the file-only Project Store.

Implements Section 2 of ``design/interace-contract/memory.md`` against the
``record.json``-per-run layout from ``foundations.md`` §4. Each run lives at::

    <store>/memory/runs/YYYY/MM/DD/run_<run_id>/record.json

The date path is derived from the run's ``created_at`` epoch-millisecond
stamp (the same value that the ULID prefix encodes — see
``novetest.utils.ulid``). Tombstones are a POSIX-atomic ``Path.rename`` from
``memory/runs/...`` to ``memory/tombstones/run_<id>/``; tombstoned records
remain readable to ``retrieve_run_evidence``.

Phase-1 scope: this module implements ``store_run_evidence``,
``retrieve_run_evidence``, ``list_run_history``, ``delete_run_evidence``, and
``get_memory_entry_availability``. ``find_runs_for_target`` lands here as the
Phase 3 prerequisite (consumed by Regression's baseline resolution and
availability check). ``find_latest_analyzable_run`` is deferred to the
Localization (Phase 4) slice.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from novetest.memory.project_store import (
    STORE_METADATA_FILENAME,
    ProjectStore,
    ProjectStoreCorruptError,
    ProjectStoreNotFoundError,
)
from novetest.models.memory_entry import MemoryEntry
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.utils.ulid import date_path_for_timestamp_ms


RECORD_FILENAME = "record.json"
RUN_DIR_PREFIX = "run_"


class RunEvidenceNotFoundError(LookupError):
    """Raised when a Run Reference resolves to neither a live nor a tombstoned record."""


class RunEvidenceAlreadyExistsError(RuntimeError):
    """Raised by ``store_run_evidence`` when the target run directory already exists."""


@dataclass(slots=True, frozen=True)
class SkippedRecord:
    """A ``record.json`` that failed to parse during a history scan (MEM-05).

    ``path`` is the corrupt file itself (torn write, hand-mangled JSON, or a
    future-schema record), so an operator can locate it without grepping;
    ``error`` is the parse failure's message. ``run_id`` is derived at skip
    time from the ``run_<ulid>`` directory name (``None`` when the directory
    does not carry the prefix), so run_id-addressed callers can recognize
    that a lookup miss was really a corrupt record (S42 exit-5 escalation).
    Scan interfaces (``list_run_history`` / ``find_runs_for_target``) SKIP
    such records and report them through an optional collector instead of
    letting one bad file kill the whole history walk. Targeted reads
    (``retrieve_run_evidence``) deliberately stay loud.
    """

    path: Path
    error: str
    run_id: str | None = None


@dataclass(slots=True, frozen=True)
class _ResolvedRecord:
    """Internal: a ``record.json`` plus where it lived on disk."""

    run_dir: Path
    record: RunRecord
    tombstoned: bool
    tombstoned_at: int | None


def store_run_evidence(store: ProjectStore, run_record: RunRecord) -> MemoryEntry:
    """Persist ``run_record`` under the active Project Store; return the Memory Entry.

    The caller (Run engine) is expected to have already written native
    artifacts under ``<store>/run/artifacts/run_<id>/...``. Memory only owns
    ``memory/runs/...`` and never touches the native bytes.

    The persisted ``record.json`` carries a ``stored_at`` epoch-ms stamp
    (MEM-04): Memory is the authority on when evidence was stored, so any
    caller-supplied ``run_record.stored_at`` is overwritten here. Read paths
    prefer this persisted value over the file mtime.
    """
    run_dir = _live_run_dir(store, run_record.run_reference)
    if run_dir.exists():
        raise RunEvidenceAlreadyExistsError(
            f"Run evidence already exists at {run_dir}; refusing to overwrite"
        )
    # MEM-01: re-verify the store is still initialized IMMEDIATELY before the
    # mkdir. A concurrent `reset` (wipe) atomically renames `.novetest/` away;
    # without this check `mkdir(parents=True)` would resurrect a store.json-less
    # skeleton that `find_nearest_store` skips forever — the run would be
    # silently orphaned. Failing loudly with the domain uninitialized error
    # turns silent run loss into a retryable failure. (A check-to-mkdir race
    # window remains — an advisory lock is the full fix; deliberately not built
    # in this slice.)
    if not (store.path / STORE_METADATA_FILENAME).is_file():
        raise ProjectStoreNotFoundError(
            f"Project Store at {store.path} is no longer initialized "
            f"({STORE_METADATA_FILENAME} missing — wiped by a concurrent reset?); "
            f"refusing to store run evidence for "
            f"run_id={run_record.run_reference.run_id!r}"
        )
    run_dir.mkdir(parents=True, exist_ok=False)
    stored_at = int(time.time() * 1000)
    record_path = run_dir / RECORD_FILENAME
    record_path.write_text(
        json.dumps(replace(run_record, stored_at=stored_at).to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return _build_memory_entry(
        store,
        record=run_record,
        stored_at=stored_at,
        tombstoned_at=None,
    )


def retrieve_run_evidence(
    store: ProjectStore, run_reference: RunReference
) -> MemoryEntry:
    """Return the Memory Entry for ``run_reference`` (live or tombstoned).

    Raises ``RunEvidenceNotFoundError`` if neither location holds the record.
    This targeted read stays LOUD on a corrupt record (MEM-05): the caller
    named one specific run, so a parse failure propagates instead of being
    skipped like the scan interfaces do.
    """
    resolved = _resolve(store, run_reference)
    return _entry_from_resolved(store, resolved)


def list_run_history(
    store: ProjectStore,
    *,
    skipped: list[SkippedRecord] | None = None,
) -> list[MemoryEntry]:
    """Return Memory Entries newest-first across both live and tombstoned runs.

    Per-record isolation (MEM-05): a ``record.json`` that fails to parse is
    skipped — and appended to the optional ``skipped`` collector — so one
    torn/corrupt/future-schema record cannot kill the whole history walk.
    """
    entries = [
        _entry_from_resolved(store, resolved)
        for resolved in _iter_all_records(store, skipped=skipped)
    ]
    # XCT-07: composite sort key (created_at, run_id) — the ULID string breaks
    # same-millisecond ties, so ordering never depends on FS enumeration order.
    entries.sort(
        key=lambda e: (
            e.run_record.run_reference.created_at,
            e.run_record.run_reference.run_id,
        ),
        reverse=True,
    )
    return entries


def find_runs_for_target(
    store: ProjectStore,
    target_expression: str,
    *,
    include_tombstoned: bool = False,
    skipped: list[SkippedRecord] | None = None,
) -> list[MemoryEntry]:
    """Return Memory Entries whose ``RunRecord.target_expression`` matches.

    Newest-first by ``(created_at, run_id)`` descending (the XCT-07 composite
    key; the ULID string breaks same-millisecond ties). Tombstoned runs
    are excluded by default; callers wanting full history (audit / debugging)
    opt in via ``include_tombstoned=True``. Returns an empty list when no run
    matches (not an error). Unparseable records are skipped, not fatal —
    see ``list_run_history`` (MEM-05); ``skipped`` collects them.

    Filtering is on ``target_expression`` alone — Phase 3 "comparability"
    semantics (target_type, engine compatibility, etc.) belong to the
    Regression layer, not Memory.
    """
    entries: list[MemoryEntry] = []
    for resolved in _iter_all_records(store, skipped=skipped):
        if resolved.record.target_expression != target_expression:
            continue
        if resolved.tombstoned and not include_tombstoned:
            continue
        entries.append(_entry_from_resolved(store, resolved))
    # XCT-07: same composite key as `list_run_history` — one ordering
    # convention across both scan interfaces.
    entries.sort(
        key=lambda e: (
            e.run_record.run_reference.created_at,
            e.run_record.run_reference.run_id,
        ),
        reverse=True,
    )
    return entries


def delete_run_evidence(
    store: ProjectStore, run_reference: RunReference
) -> MemoryEntry:
    """Tombstone the live run for ``run_reference``; return the post-tombstone entry.

    Order is **mutate-then-single-rename** (MEM-02): the fully-updated
    tombstoned ``record.json`` (``status="tombstoned"`` plus a stamped
    ``metadata["tombstoned_at"]``) is materialized at the LIVE location first —
    written to a sibling temp file and ``Path.replace``-d into place so the live
    ``record.json`` is never observed half-written — and only THEN is the
    directory moved to ``memory/tombstones/run_<id>/`` with a single
    POSIX-atomic ``Path.rename``.

    That order makes a crash mid-delete self-healing rather than permanently
    corrupt. The only residue a crash can leave is a *live*-located run whose
    ``record.json`` already says tombstoned (the move had not yet run); because
    ``_resolve`` keys ``tombstoned`` off *location*, a re-issued
    ``delete_run_evidence`` does not short-circuit — it re-stamps and completes
    the rename, so the ``MemoryEntry`` invariant (``tombstoned_at`` non-null iff
    soft-deleted) is restored. The former rename-then-write order could instead
    strand a *tombstone*-located record still carrying the original ``status``
    and ``tombstoned_at=None``, which the re-delete no-op made permanent.

    Re-deletion of an already-tombstoned run is a no-op that returns the
    existing entry.

    Tombstoning preserves the ORIGINAL ``stored_at`` (MEM-04): the rewrite
    carries the record's persisted stamp forward — or, for a legacy record
    without one, stamps the pre-rewrite file mtime (the best available
    approximation of the original store instant) — so deletion never shifts
    ``stored_at`` to deletion time. ``tombstoned_at`` remains the separate
    deletion timestamp.
    """
    resolved = _resolve(store, run_reference)
    if resolved.tombstoned:
        return _entry_from_resolved(store, resolved)

    stored_at = _stored_at_of(resolved)

    tombstoned_at = int(time.time() * 1000)
    new_metadata = dict(resolved.record.metadata)
    new_metadata["tombstoned_at"] = tombstoned_at
    tombstoned_record = replace(
        resolved.record,
        status="tombstoned",
        metadata=new_metadata,
        stored_at=stored_at,
    )
    # Materialize the tombstoned record at the LIVE location before moving it,
    # so any crash leaves a self-healing live record — never a permanently
    # invariant-violating tombstone. The single rename that follows carries an
    # already-complete record into the tombstone location atomically.
    _atomic_write_record(resolved.run_dir / RECORD_FILENAME, tombstoned_record)

    tombstone_dir = _tombstone_run_dir(store, run_reference)
    tombstone_dir.parent.mkdir(parents=True, exist_ok=True)
    resolved.run_dir.rename(tombstone_dir)

    return _build_memory_entry(
        store,
        record=replace(tombstoned_record, stored_at=None),
        stored_at=stored_at,
        tombstoned_at=tombstoned_at,
    )


def get_memory_entry_availability(
    store: ProjectStore, run_reference: RunReference
) -> dict[str, bool]:
    """Return per-derived-fact availability flags by probing the filesystem.

    All flags are derived from the presence of the corresponding artifact
    file under the peer engine's subdirectory. In Phase 1 no derivation has
    run yet, so the four ``has_*`` flags will always be ``False``; the
    ``tombstoned`` flag tracks the location of the Memory record.
    """
    resolved = _resolve(store, run_reference)
    flags = _availability_flags(store, resolved.record.run_reference.run_id)
    return {**flags, "tombstoned": resolved.tombstoned}


# --- internals ---------------------------------------------------------------


def _live_run_dir(store: ProjectStore, ref: RunReference) -> Path:
    y, m, d = date_path_for_timestamp_ms(ref.created_at)
    return store.path / "memory" / "runs" / y / m / d / f"{RUN_DIR_PREFIX}{ref.run_id}"


def _tombstone_run_dir(store: ProjectStore, ref: RunReference) -> Path:
    return store.path / "memory" / "tombstones" / f"{RUN_DIR_PREFIX}{ref.run_id}"


def _resolve(store: ProjectStore, ref: RunReference) -> _ResolvedRecord:
    live = _live_run_dir(store, ref)
    if (live / RECORD_FILENAME).is_file():
        record = _read_record(live / RECORD_FILENAME)
        return _ResolvedRecord(
            run_dir=live, record=record, tombstoned=False, tombstoned_at=None
        )
    tombstone = _tombstone_run_dir(store, ref)
    if (tombstone / RECORD_FILENAME).is_file():
        record = _read_record(tombstone / RECORD_FILENAME)
        ts_at = record.metadata.get("tombstoned_at")
        tombstoned_at = int(ts_at) if isinstance(ts_at, int) else None
        return _ResolvedRecord(
            run_dir=tombstone,
            record=record,
            tombstoned=True,
            tombstoned_at=tombstoned_at,
        )
    raise RunEvidenceNotFoundError(
        f"No run evidence for run_id={ref.run_id!r} in {store.path}"
    )


def _iter_all_records(
    store: ProjectStore,
    *,
    skipped: list[SkippedRecord] | None = None,
) -> Iterator[_ResolvedRecord]:
    """Yield every parseable record, live then tombstoned.

    Per-record isolation (MEM-05): a record that fails to parse is skipped —
    and reported to ``skipped`` when a collector is passed — so one bad file
    cannot poison the scan interfaces. Targeted reads go through ``_resolve``
    and stay loud.
    """
    runs_root = store.path / "memory" / "runs"
    if runs_root.is_dir():
        for record_path in runs_root.rglob(RECORD_FILENAME):
            record = _read_record_isolated(record_path, skipped)
            if record is None:
                continue
            yield _ResolvedRecord(
                run_dir=record_path.parent,
                record=record,
                tombstoned=False,
                tombstoned_at=None,
            )
    tombstones_root = store.path / "memory" / "tombstones"
    if tombstones_root.is_dir():
        for child in tombstones_root.iterdir():
            record_path = child / RECORD_FILENAME
            if record_path.is_file():
                record = _read_record_isolated(record_path, skipped)
                if record is None:
                    continue
                ts_at = record.metadata.get("tombstoned_at")
                tombstoned_at = int(ts_at) if isinstance(ts_at, int) else None
                yield _ResolvedRecord(
                    run_dir=child,
                    record=record,
                    tombstoned=True,
                    tombstoned_at=tombstoned_at,
                )


def _read_record(path: Path) -> RunRecord:
    """Parse one ``record.json``; corruption raises the typed storage error.

    Parse/shape failures — torn JSON, a wrong-shaped body, missing/mistyped
    keys, a future ``schema_version`` — are wrapped in
    ``ProjectStoreCorruptError`` with the corrupt file's path in the message
    (XCT-03 / S42), so every loud targeted read carries the typed storage
    error the CLI maps to ``store-corrupt`` / exit 5. ``OSError`` (file
    vanished mid-read) deliberately stays unwrapped — vanished-file
    semantics are unchanged.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        return RunRecord.from_dict(json.loads(raw))
    except (ValueError, TypeError, KeyError) as exc:
        # json.JSONDecodeError is a ValueError; RunRecord.from_dict raises
        # ValueError (incl. unsupported schema_version), TypeError, KeyError.
        raise ProjectStoreCorruptError(f"Corrupt run record at {path}: {exc}") from exc


def _read_record_isolated(
    path: Path, skipped: list[SkippedRecord] | None
) -> RunRecord | None:
    """``_read_record`` for scan paths: parse failures skip, never propagate.

    Catches exactly the failure classes a bad ``record.json`` produces —
    ``ProjectStoreCorruptError`` (the typed wrap ``_read_record`` puts around
    torn JSON / wrong-shaped bodies / future ``schema_version`` since S42;
    a ``RuntimeError``, so it needs its own entry in the tuple), ``OSError``
    (file vanished mid-scan, e.g. a concurrent tombstone rename), and the
    residual raw ``ValueError``/``TypeError`` classes that can still escape
    unwrapped (e.g. ``UnicodeDecodeError`` from non-UTF-8 bytes at
    ``read_text``). Anything else is a bug and stays loud.
    """
    try:
        return _read_record(path)
    except (OSError, ValueError, TypeError, ProjectStoreCorruptError) as exc:
        if skipped is not None:
            dir_name = path.parent.name
            run_id = (
                dir_name[len(RUN_DIR_PREFIX):]
                if dir_name.startswith(RUN_DIR_PREFIX)
                and len(dir_name) > len(RUN_DIR_PREFIX)
                else None
            )
            skipped.append(SkippedRecord(path=path, error=str(exc), run_id=run_id))
        return None


def _atomic_write_record(record_path: Path, record: RunRecord) -> None:
    """Write ``record`` to ``record_path`` atomically via a sibling temp file.

    The bytes are staged in ``<name>.tmp`` in the same directory, then
    ``Path.replace``-d onto ``record_path``. ``Path.replace`` is a same-dir
    atomic rename, so a reader (or a crash) never observes a torn ``record.json``:
    the file is either the previous content or the complete new content.
    """
    payload = json.dumps(record.to_dict(), indent=2) + "\n"
    tmp_path = record_path.with_name(record_path.name + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(record_path)


def _path_mtime_ms(path: Path) -> int:
    return int(path.stat().st_mtime * 1000)


def _stored_at_of(resolved: _ResolvedRecord) -> int:
    """The entry's ``stored_at``: persisted stamp, else file-mtime fallback.

    Records written since MEM-04 carry ``stored_at`` inside ``record.json``;
    that persisted value wins. Legacy records (absent key) fall back to the
    ``record.json`` mtime — the pre-MEM-04 derivation, kept forever so old
    stores stay readable without rewriting them.
    """
    if resolved.record.stored_at is not None:
        return resolved.record.stored_at
    return _path_mtime_ms(resolved.run_dir / RECORD_FILENAME)


def _entry_from_resolved(store: ProjectStore, resolved: _ResolvedRecord) -> MemoryEntry:
    """Build the Memory Entry for a resolved on-disk record.

    ``stored_at`` is surfaced at the MemoryEntry level only — the nested
    ``run_record`` wire projection stays byte-identical to pre-MEM-04
    envelopes, so the persisted stamp is stripped off the record here.
    """
    stored_at = _stored_at_of(resolved)
    record = resolved.record
    if record.stored_at is not None:
        record = replace(record, stored_at=None)
    return _build_memory_entry(
        store,
        record=record,
        stored_at=stored_at,
        tombstoned_at=resolved.tombstoned_at,
    )


def _any_regression_pair_exists(store: ProjectStore, run_id: str) -> bool:
    pairs_root = store.path / "regression" / "pairs"
    if not pairs_root.is_dir():
        return False
    needle = f"{RUN_DIR_PREFIX}{run_id}"
    for pair_dir in pairs_root.iterdir():
        if needle in pair_dir.name and (pair_dir / "regression_facts.json").is_file():
            return True
    return False


def _build_memory_entry(
    store: ProjectStore,
    *,
    record: RunRecord,
    stored_at: int,
    tombstoned_at: int | None,
) -> MemoryEntry:
    flags = _availability_flags(store, record.run_reference.run_id)
    return MemoryEntry(
        entry_id=record.run_reference.run_id,
        run_record=record,
        stored_at=stored_at,
        has_coverage_facts=flags["has_coverage_facts"],
        has_regression_facts=flags["has_regression_facts"],
        has_localization_findings=flags["has_localization_findings"],
        has_replay_result=flags["has_replay_result"],
        tombstoned_at=tombstoned_at,
    )


def _availability_flags(store: ProjectStore, run_id: str) -> dict[str, bool]:
    run_subdir = f"{RUN_DIR_PREFIX}{run_id}"
    return {
        "has_coverage_facts": (
            store.path / "coverage" / "facts" / run_subdir / "coverage_facts.json"
        ).is_file(),
        "has_regression_facts": _any_regression_pair_exists(store, run_id),
        "has_localization_findings": (
            store.path / "localization" / "findings" / run_subdir
            / "localization_findings.json"
        ).is_file(),
        "has_replay_result": (
            store.path / "replay" / "results" / run_subdir / "replay_result.json"
        ).is_file(),
    }
