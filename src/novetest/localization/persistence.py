"""On-disk persistence helpers for ``LocalizationFinding``.

The path layout is **load-bearing**: Memory's ``_availability_flags``
probe (``src/novetest/memory/store.py:_availability_flags``) checks for
``<store>/localization/findings/run_<run_id>/localization_findings.json``
to auto-flip ``MemoryEntry.has_localization_findings``. Keep the
filename and directory layout exactly as named here.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RUN_DIR_PREFIX
from novetest.models.localization_finding import LocalizationFinding


LOCALIZATION_FINDINGS_DIRNAME = "findings"
LOCALIZATION_FINDINGS_FILENAME = "localization_findings.json"


def localization_findings_dir(store: ProjectStore, run_id: str) -> Path:
    """Return the directory where this run's localization findings live."""
    return (
        store.path
        / "localization"
        / LOCALIZATION_FINDINGS_DIRNAME
        / f"{RUN_DIR_PREFIX}{run_id}"
    )


def localization_findings_path(store: ProjectStore, run_id: str) -> Path:
    """Return the absolute path to this run's ``localization_findings.json``."""
    return localization_findings_dir(store, run_id) / LOCALIZATION_FINDINGS_FILENAME


def write_localization_findings(
    store: ProjectStore, finding: LocalizationFinding
) -> Path:
    """Persist ``finding`` to its canonical location and return the path.

    Atomic write: serialize to a sibling tempfile in the same parent
    directory, then ``os.replace`` onto the canonical path so a crashed
    write never leaves a partially-written ``localization_findings.json``
    visible to Memory's probe. Same pattern as Coverage / Regression
    persistence helpers.

    The parent directory is created on demand. Re-writing an existing
    file is permitted (overwrite semantics) so a re-derivation refreshes
    the cached payload.
    """
    run_id = finding.run_reference.run_id
    target_dir = localization_findings_dir(store, run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / LOCALIZATION_FINDINGS_FILENAME

    payload = json.dumps(finding.to_dict(), indent=2) + "\n"

    # ``delete=False`` because we hand the file off to ``os.replace``
    # explicitly. ``dir=target_dir`` keeps the tempfile on the same
    # filesystem as the destination so ``replace`` stays atomic.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".localization_findings.", suffix=".tmp", dir=target_dir
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, target)
    except Exception:
        # Best-effort cleanup of the tempfile on failure; the underlying
        # exception still propagates so the caller sees it.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return target


def read_localization_findings_raw(
    store: ProjectStore, run_id: str
) -> dict[str, object] | None:
    """Load the raw JSON dict for a run's ``localization_findings.json``.

    Returns ``None`` when the canonical file does not exist. The raw
    dict (rather than the parsed ``LocalizationFinding``) lets the
    retrieval layer surface a clean Unavailable for missing-cache
    without paying for the full ``from_dict`` decode.
    """
    target = localization_findings_path(store, run_id)
    if not target.is_file():
        return None
    raw = target.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"localization_findings.json at {target} is not a JSON object"
        )
    return parsed
