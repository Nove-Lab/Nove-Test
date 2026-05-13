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
``get_memory_entry_availability``. ``find_runs_for_target`` and
``find_latest_analyzable_run`` are deferred to the Regression (Phase 3) and
Localization (Phase 4) slices; they are not listed in Phase 1 "Interfaces in
scope".
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from novetest.memory.project_store import ProjectStore
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
    """
    run_dir = _live_run_dir(store, run_record.run_reference)
    if run_dir.exists():
        raise RunEvidenceAlreadyExistsError(
            f"Run evidence already exists at {run_dir}; refusing to overwrite"
        )
    run_dir.mkdir(parents=True, exist_ok=False)
    record_path = run_dir / RECORD_FILENAME
    record_path.write_text(
        json.dumps(run_record.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    stored_at = int(time.time() * 1000)
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
    """
    resolved = _resolve(store, run_reference)
    stored_at = _path_mtime_ms(resolved.run_dir / RECORD_FILENAME)
    return _build_memory_entry(
        store,
        record=resolved.record,
        stored_at=stored_at,
        tombstoned_at=resolved.tombstoned_at,
    )


def list_run_history(store: ProjectStore) -> list[MemoryEntry]:
    """Return Memory Entries newest-first across both live and tombstoned runs."""
    entries: list[MemoryEntry] = []
    for resolved in _iter_all_records(store):
        stored_at = _path_mtime_ms(resolved.run_dir / RECORD_FILENAME)
        entries.append(
            _build_memory_entry(
                store,
                record=resolved.record,
                stored_at=stored_at,
                tombstoned_at=resolved.tombstoned_at,
            )
        )
    entries.sort(key=lambda e: e.run_record.run_reference.created_at, reverse=True)
    return entries


def delete_run_evidence(
    store: ProjectStore, run_reference: RunReference
) -> MemoryEntry:
    """Tombstone the live run for ``run_reference``; return the post-tombstone entry.

    Tombstoning is a single ``Path.rename`` from ``memory/runs/...`` to
    ``memory/tombstones/run_<id>/`` (POSIX-atomic on the same filesystem),
    plus an in-place update of ``record.json`` that sets the status field to
    ``tombstoned`` and stamps ``metadata["tombstoned_at"]``. Re-deletion of
    an already-tombstoned run is a no-op that returns the existing entry.
    """
    resolved = _resolve(store, run_reference)
    if resolved.tombstoned:
        stored_at = _path_mtime_ms(resolved.run_dir / RECORD_FILENAME)
        return _build_memory_entry(
            store,
            record=resolved.record,
            stored_at=stored_at,
            tombstoned_at=resolved.tombstoned_at,
        )

    tombstone_dir = _tombstone_run_dir(store, run_reference)
    tombstone_dir.parent.mkdir(parents=True, exist_ok=True)
    resolved.run_dir.rename(tombstone_dir)

    tombstoned_at = int(time.time() * 1000)
    new_metadata = dict(resolved.record.metadata)
    new_metadata["tombstoned_at"] = tombstoned_at
    tombstoned_record = replace(
        resolved.record, status="tombstoned", metadata=new_metadata
    )
    (tombstone_dir / RECORD_FILENAME).write_text(
        json.dumps(tombstoned_record.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return _build_memory_entry(
        store,
        record=tombstoned_record,
        stored_at=_path_mtime_ms(tombstone_dir / RECORD_FILENAME),
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


def _iter_all_records(store: ProjectStore) -> Iterator[_ResolvedRecord]:
    runs_root = store.path / "memory" / "runs"
    if runs_root.is_dir():
        for record_path in runs_root.rglob(RECORD_FILENAME):
            yield _ResolvedRecord(
                run_dir=record_path.parent,
                record=_read_record(record_path),
                tombstoned=False,
                tombstoned_at=None,
            )
    tombstones_root = store.path / "memory" / "tombstones"
    if tombstones_root.is_dir():
        for child in tombstones_root.iterdir():
            record_path = child / RECORD_FILENAME
            if record_path.is_file():
                record = _read_record(record_path)
                ts_at = record.metadata.get("tombstoned_at")
                tombstoned_at = int(ts_at) if isinstance(ts_at, int) else None
                yield _ResolvedRecord(
                    run_dir=child,
                    record=record,
                    tombstoned=True,
                    tombstoned_at=tombstoned_at,
                )


def _read_record(path: Path) -> RunRecord:
    raw = path.read_text(encoding="utf-8")
    return RunRecord.from_dict(json.loads(raw))


def _path_mtime_ms(path: Path) -> int:
    return int(path.stat().st_mtime * 1000)


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
