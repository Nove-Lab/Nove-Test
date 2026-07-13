"""On-disk persistence helpers for ``ReplayResult``.

The path layout is **load-bearing**: Memory's ``_availability_flags`` probe
(``src/novetest/memory/store.py``) checks for
``<store>/replay/results/run_<original_run_id>/replay_result.json`` to
auto-flip ``MemoryEntry.has_replay_result``. Keep the filename and directory
layout exactly as named here.

The ``run_<id>`` segment uses the **original** run's id (the run being
replayed) — a Replay Result is keyed by the run it classifies, mirroring how
``coverage_facts.json`` / ``localization_findings.json`` key by their run.
The replay-execution Run Records themselves persist separately via Memory's
``store_run_evidence`` (they are first-class Memory Entries).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from novetest.memory import RUN_DIR_PREFIX, ProjectStore
from novetest.models.replay_result import ReplayResult
from novetest.models.run_reference import RunReference


REPLAY_RESULTS_DIRNAME = "results"
REPLAY_RESULT_FILENAME = "replay_result.json"


def replay_result_dir(store: ProjectStore, original_ref: RunReference) -> Path:
    """Return the directory where this original run's replay result lives."""
    return (
        store.path
        / "replay"
        / REPLAY_RESULTS_DIRNAME
        / f"{RUN_DIR_PREFIX}{original_ref.run_id}"
    )


def replay_result_path(store: ProjectStore, original_ref: RunReference) -> Path:
    """Return the absolute path to this original run's ``replay_result.json``."""
    return replay_result_dir(store, original_ref) / REPLAY_RESULT_FILENAME


def write_replay_result(
    store: ProjectStore, original_ref: RunReference, result: ReplayResult
) -> Path:
    """Persist ``result`` to its canonical location and return the path.

    Atomic write: serialize to a sibling tempfile in the same parent
    directory, then ``os.replace`` onto the canonical path so a crashed write
    never leaves a partially-written ``replay_result.json`` visible to
    Memory's probe. Same pattern as the Localization / Coverage persistence
    helpers. Re-writing an existing file is permitted (a fresh Replay Attempt
    refreshes the cached result).
    """
    target_dir = replay_result_dir(store, original_ref)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / REPLAY_RESULT_FILENAME

    payload = json.dumps(result.to_dict(), indent=2) + "\n"

    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".replay_result.", suffix=".tmp", dir=target_dir
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return target


def read_replay_result_raw(
    store: ProjectStore, original_ref: RunReference
) -> dict[str, object] | None:
    """Load the raw JSON dict for an original run's ``replay_result.json``.

    Returns ``None`` when the canonical file does not exist. The raw dict
    (rather than the parsed ``ReplayResult``) lets the retrieval layer
    surface a clean Unavailable for the missing-cache case without paying for
    the full ``from_dict`` decode.
    """
    target = replay_result_path(store, original_ref)
    if not target.is_file():
        return None
    raw = target.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"replay_result.json at {target} is not a JSON object")
    return parsed
