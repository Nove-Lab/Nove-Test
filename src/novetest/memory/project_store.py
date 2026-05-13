"""Project Store handle, lifecycle, and discovery.

Implements the Section 1 interfaces of
``design/interace-contract/memory.md`` against the file-only layout pinned in
``design/implementation-plan/foundations.md`` §4. No SQLite, no caches — the
filesystem is the source of truth.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self


SCHEMA_VERSION: int = 1
STORE_DIRNAME = ".novetest"
STORE_METADATA_FILENAME = "store.json"
ENV_NOVETEST_HOME = "NOVETEST_HOME"

# Engine subdirectories created by `create_project_store`. Each engine owns its
# subtree exclusively per `foundations.md` §4 layout; we materialize empty
# directories at init so peers do not race on first-write `mkdir`.
_TOP_LEVEL_DIRS: tuple[str, ...] = ("blobs",)
_ENGINE_DIRS: tuple[str, ...] = (
    "memory/runs",
    "memory/tombstones",
    "run",
    "coverage",
    "regression",
    "localization",
    "replay",
    "orchestration",
)


@dataclass(slots=True, frozen=True)
class ProjectStore:
    """Handle for an initialized ``.novetest/`` Project Store.

    ``path`` points at the ``.novetest/`` directory itself, not its workspace
    parent. The remaining fields mirror ``store.json``.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    path: Path
    initialized_at: int
    store_state: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "store_path": str(self.path),
            "initialized_at": self.initialized_at,
            "store_state": self.store_state,
        }

    @classmethod
    def _from_metadata(cls, path: Path, d: dict[str, Any]) -> Self:
        schema_version = d.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ProjectStoreCorruptError(
                f"Unsupported store schema_version={schema_version!r} at {path}; "
                f"supported={SCHEMA_VERSION}"
            )
        try:
            initialized_at = int(d["initialized_at"])
            store_state = str(d["store_state"])
        except KeyError as exc:
            raise ProjectStoreCorruptError(
                f"store.json at {path} missing required key: {exc.args[0]!r}"
            ) from exc
        return cls(
            path=path,
            initialized_at=initialized_at,
            store_state=store_state,
            schema_version=int(schema_version),
        )


class ProjectStoreCorruptError(RuntimeError):
    """Raised when a ``.novetest/`` directory exists but ``store.json`` is unreadable."""


def create_project_store(workspace_path: Path) -> ProjectStore:
    """Create or return an existing Project Store at ``<workspace_path>/.novetest/``.

    Idempotent: if a recognized ``store.json`` already exists, the existing
    handle is returned and durable state on disk is left untouched
    (REQ-MEM-006). If the directory exists but the metadata is missing, the
    skeleton is completed and metadata is written — this recovers from a
    partial init crash without destroying any pre-existing run records.
    """
    if not workspace_path.is_dir():
        raise FileNotFoundError(
            f"Workspace path is not an existing directory: {workspace_path}"
        )
    store_path = workspace_path / STORE_DIRNAME
    metadata_path = store_path / STORE_METADATA_FILENAME

    if metadata_path.exists():
        return _read_metadata(store_path)

    store_path.mkdir(parents=True, exist_ok=True)
    for rel in _TOP_LEVEL_DIRS + _ENGINE_DIRS:
        (store_path / rel).mkdir(parents=True, exist_ok=True)

    handle = ProjectStore(
        path=store_path,
        initialized_at=int(time.time() * 1000),
        store_state="ready",
    )
    _write_metadata(metadata_path, handle)
    return handle


def locate_project_store(
    start_path: Path,
    env: Mapping[str, str] | None = None,
) -> ProjectStore | None:
    """Walk up from ``start_path`` looking for an initialized Project Store.

    ``NOVETEST_HOME`` (env, or the passed ``env`` mapping) short-circuits the
    walk and pins the active store to that path — used by tests to keep
    ``tmp_path``-scoped runs hermetic per ``foundations.md`` §6.
    """
    source_env = env if env is not None else os.environ
    pinned = source_env.get(ENV_NOVETEST_HOME)
    if pinned:
        pinned_path = Path(pinned)
        if (pinned_path / STORE_METADATA_FILENAME).exists():
            return _read_metadata(pinned_path)
        return None

    current = start_path.resolve()
    # `current` may be a file (e.g. a CLI invocation pointed at a script);
    # walk up from its parent in that case.
    if current.is_file():
        current = current.parent
    while True:
        candidate = current / STORE_DIRNAME / STORE_METADATA_FILENAME
        if candidate.exists():
            return _read_metadata(current / STORE_DIRNAME)
        if current.parent == current:
            return None
        current = current.parent


def get_project_store_state(store_path: Path) -> ProjectStore:
    """Return the Project Store handle for an already-initialized ``store_path``."""
    return _read_metadata(store_path)


def _read_metadata(store_path: Path) -> ProjectStore:
    metadata_path = store_path / STORE_METADATA_FILENAME
    try:
        raw = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectStoreCorruptError(
            f"Project Store at {store_path} is missing {STORE_METADATA_FILENAME}"
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProjectStoreCorruptError(
            f"Project Store metadata at {metadata_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ProjectStoreCorruptError(
            f"Project Store metadata at {metadata_path} is not a JSON object"
        )
    return ProjectStore._from_metadata(store_path, parsed)


def _write_metadata(metadata_path: Path, store: ProjectStore) -> None:
    payload = {
        "schema_version": store.schema_version,
        "initialized_at": store.initialized_at,
        "store_state": store.store_state,
    }
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
