"""Project Store handle, lifecycle, and discovery.

Implements the Section 1 interfaces of
``design/interace-contract/memory.md`` against the file-only layout pinned in
``design/implementation-plan/foundations.md`` §4. No SQLite, no caches — the
filesystem is the source of truth.

Schema note — engine pin (anchored-pin decision, 2026-07-03). ``store.json``
may carry an optional ``pinned_engine`` object::

    "pinned_engine": {"ecosystem": "python", "engine_name": "pytest"}

recording which engine the user anchored at ``init`` (decision D1 in
``agent-comms/decisions/2026-07-03-engine-selection-policy.md``). This is an
additive optional field with a tolerant reader: legacy (pre-pin) stores load
with ``pinned_engine=None`` and are NEVER rewritten on load — backfill happens
only through ``set_pinned_engine`` (Orchestration's D6 migration flow). Because
every store.json readable before this change remains readable unchanged,
``SCHEMA_VERSION`` stays at 1 (no bump). A *malformed* pin (wrong JSON shape)
is corruption, not absence — silently treating it as ``None`` would trigger a
silent D6 re-detect that overwrites user intent. A well-formed pin naming a
pair outside the currently supported matrix loads fine (forward tolerance for
stores pinned by newer novetest versions); pair validation is write-time only.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar, Self

from novetest.models.engine_matrix import SUPPORTED_ENGINE_PAIRS
from novetest.utils.ulid import generate_ulid


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

# Wipe-time accounting. Envelope keys are frozen by
# ``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``
# (the `items_removed` slot); source dirs are layout refinements of entries in
# ``_ENGINE_DIRS`` above. Terminal filenames mirror the artifacts probed by
# ``novetest.memory.store._availability_flags`` so this enumeration follows
# whatever the engines actually persist.
_WIPE_COUNT_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("memory/runs",           "record.json",                "runs"),
    ("memory/tombstones",     "record.json",                "tombstones"),
    ("coverage/facts",        "coverage_facts.json",        "coverage_facts"),
    ("regression/pairs",      "regression_facts.json",      "regression_pairs"),
    ("localization/findings", "localization_findings.json", "localization_findings"),
    ("replay/results",        "replay_result.json",         "replay_results"),
)
_STAGING_DIR_PREFIX = ".novetest.deleting."


@dataclass(slots=True, frozen=True)
class PinnedEngine:
    """The (ecosystem, engine) pair anchored in ``store.json`` at init time.

    Persisted as the optional ``pinned_engine`` object (see module docstring).
    Values are plain strings from the six-pair matrix (REQ-RUN-006) at write
    time; the reader deliberately does not re-validate pair membership.
    """

    ecosystem: str
    engine_name: str

    def to_dict(self) -> dict[str, Any]:
        return {"ecosystem": self.ecosystem, "engine_name": self.engine_name}


@dataclass(slots=True, frozen=True)
class ProjectStore:
    """Handle for an initialized ``.novetest/`` Project Store.

    ``path`` points at the ``.novetest/`` directory itself, not its workspace
    parent. The remaining fields mirror ``store.json``.

    ``pinned_engine`` reflects the pin *as of load time*; the handle is frozen,
    so after ``set_pinned_engine`` re-read via ``get_pinned_engine`` (disk is
    authoritative) rather than trusting a handle obtained earlier.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    path: Path
    initialized_at: int
    store_state: str
    schema_version: int = SCHEMA_VERSION
    pinned_engine: PinnedEngine | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "store_path": str(self.path),
            "initialized_at": self.initialized_at,
            "store_state": self.store_state,
            "pinned_engine": (
                self.pinned_engine.to_dict() if self.pinned_engine is not None else None
            ),
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
            pinned_engine=_parse_pinned_engine(path, d.get("pinned_engine")),
        )


@dataclass(slots=True, frozen=True)
class WipeReport:
    """Outcome of a successful ``wipe_project_store`` invocation.

    Returned by ``wipe_project_store`` and consumed by Orchestration's
    ``reset`` workflow to build the user-facing envelope (slot names mirror
    the envelope's ``data.items_removed`` shape pinned by
    ``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``).
    """

    store_path: Path
    previous_initialized_at: int
    items_removed: dict[str, int]


class ProjectStoreCorruptError(RuntimeError):
    """Raised when a ``.novetest/`` directory exists but ``store.json`` is unreadable."""


class ProjectStoreNotFoundError(RuntimeError):
    """Raised when an operation expects a Project Store but the path holds none.

    Distinct from ``ProjectStoreCorruptError`` (which indicates the directory
    exists but ``store.json`` is unreadable). Callers — notably the destructive
    ``wipe_project_store`` primitive — use the distinction to decide between
    ``uninitialized`` and ``store-corrupt`` exit envelopes per the decision doc
    at ``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``.
    """


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
    _sweep_staging_residue(workspace_path)
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

    anchor = find_nearest_store(start_path)
    if anchor is None:
        return None
    return _read_metadata(anchor / STORE_DIRNAME)


def find_nearest_store(start: Path) -> Path | None:
    """Walk upward from ``start``; return the nearest anchor directory, or ``None``.

    Implements decision D2 of
    ``agent-comms/decisions/2026-07-03-engine-selection-policy.md``: every verb
    resolves its workspace by walking **upward** (git-style) from cwd to the
    filesystem root — never downward, nearest wins, no multi-store semantics.

    The returned path is the **workspace/anchor directory that contains**
    ``.novetest/`` (the store itself is at ``<returned>/.novetest/``), so D6
    migration callers can run engine detection at the anchor directly. ``start``
    itself is the first candidate; a ``start`` pointing at a file walks from its
    parent.

    Match predicate is ``<dir>/.novetest/store.json`` existence — the same
    predicate ``locate_project_store`` has always used (that function now
    delegates its walk here, so the two cannot diverge). Consequences,
    consistent with existing store.json conventions:

    - a ``.novetest/`` *without* ``store.json`` (partial-init crash shape) is
      not a store and is walked past to the next ancestor;
    - a ``.novetest/`` with a *corrupt* ``store.json`` IS found — this function
      never parses; loading the result (``get_project_store_state`` /
      ``locate_project_store``) raises ``ProjectStoreCorruptError`` there, so a
      broken store errors loudly instead of being silently shadowed by an
      ancestor.

    No ``NOVETEST_HOME`` handling here — that short-circuit belongs to
    ``locate_project_store``.
    """
    current = start.resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / STORE_DIRNAME / STORE_METADATA_FILENAME).exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def get_pinned_engine(store: ProjectStore) -> PinnedEngine | None:
    """Return the engine pin for ``store``, or ``None`` for a legacy (pre-pin) store.

    Reads ``store.json`` fresh from disk — the frozen handle may predate a
    ``set_pinned_engine`` call, and disk is authoritative. Reading NEVER
    rewrites the file (legacy stores stay byte-identical; backfill is the
    caller's explicit D6 flow via ``set_pinned_engine``). Raises
    ``ProjectStoreCorruptError`` if ``store.json`` is unreadable or the pin is
    malformed, consistent with every other metadata read.
    """
    return _read_metadata(store.path).pinned_engine


def set_pinned_engine(store: ProjectStore, ecosystem: str, engine_name: str) -> None:
    """Persist (or overwrite) the engine pin in ``store``'s ``store.json``.

    Overwriting an existing pin is legal — decision D1's re-pin-in-place: same
    store, pin updated, run history untouched. The pair is validated against
    the six supported pairs (REQ-RUN-006, the shared
    ``models.engine_matrix.SUPPORTED_ENGINE_PAIRS`` domain constant — XCT-13
    killed the former upward import from ``run``); unsupported pairs raise
    ``ValueError`` before any disk mutation. The rewrite carries the same
    write-safety guarantees as every existing ``store.json`` write (an atomic
    same-directory temp write + ``os.replace`` — XCT-04, via
    ``_write_metadata``), and re-reads the metadata from disk first so a stale
    handle cannot clobber fields changed since the handle was loaded.
    """
    pair = (ecosystem, engine_name)
    if pair not in SUPPORTED_ENGINE_PAIRS:
        raise ValueError(
            f"Unsupported (ecosystem, engine) pair {pair!r}; supported pairs: "
            + ", ".join(f"({e!r}, {n!r})" for e, n in SUPPORTED_ENGINE_PAIRS)
        )
    current = _read_metadata(store.path)
    updated = replace(
        current,
        pinned_engine=PinnedEngine(ecosystem=ecosystem, engine_name=engine_name),
    )
    _write_metadata(store.path / STORE_METADATA_FILENAME, updated)


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
    """Serialize ``store`` metadata and write it atomically to ``metadata_path``.

    The single choke point for every ``store.json`` metadata write
    (``create_project_store`` and ``set_pinned_engine`` both route here), so
    the atomic-write guarantee below applies to all of them (XCT-04).
    """
    payload: dict[str, Any] = {
        "schema_version": store.schema_version,
        "initialized_at": store.initialized_at,
        "store_state": store.store_state,
    }
    # Additive optional field: omitted entirely when unset, so a pre-pin
    # store.json never grows a key it did not have (see module docstring).
    if store.pinned_engine is not None:
        payload["pinned_engine"] = store.pinned_engine.to_dict()
    _atomic_write_json(metadata_path, payload)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON to ``path`` atomically (XCT-04).

    The bytes are staged in a sibling ``<name>.tmp`` file in the SAME directory
    and then ``os.replace``-d onto ``path`` — an atomic rename on POSIX and
    Windows. A crash or a concurrent reader therefore never observes a torn
    ``store.json``: the file is either the previous complete content or the new
    complete content. This closes XCT-04's torn-write window (a bare
    ``write_text`` could be interrupted mid-write and leave an unparseable
    store, tripping ``ProjectStoreCorruptError`` on the next read). No fsync
    ceremony is required — ``os.replace`` alone closes the finding's scenario.
    """
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _parse_pinned_engine(store_path: Path, raw: object) -> PinnedEngine | None:
    """Parse the optional ``pinned_engine`` value from ``store.json``.

    Absent (``None``) is the legacy shape and loads as ``None``. Anything
    present must be a two-string-key object; malformation is corruption (NOT
    silently ``None`` — see module docstring). Pair membership in the
    supported matrix is deliberately not checked here (forward tolerance).
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProjectStoreCorruptError(
            f"store.json at {store_path} has malformed pinned_engine "
            f"(expected object, got {type(raw).__name__})"
        )
    ecosystem = raw.get("ecosystem")
    engine_name = raw.get("engine_name")
    if not isinstance(ecosystem, str) or not isinstance(engine_name, str):
        raise ProjectStoreCorruptError(
            f"store.json at {store_path} has malformed pinned_engine "
            f"(expected string 'ecosystem' and 'engine_name' keys, got {raw!r})"
        )
    return PinnedEngine(ecosystem=ecosystem, engine_name=engine_name)


def wipe_project_store(store_path: Path) -> WipeReport:
    """Destructively remove the Project Store at ``store_path``.

    ``store_path`` MUST be a resolved ``.novetest/`` directory (callers obtain
    it via ``locate_project_store`` first). The destructive sequence is pinned
    by ``agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md``
    §"Atomicity guarantee":

    1. Refuse if no Project Store is present (``ProjectStoreNotFoundError``).
    2. Refuse if ``store.json`` is unreadable (``ProjectStoreCorruptError``).
       A corrupt store is **deliberately not** auto-wiped — that's a
       load-bearing safety property; a transient FS issue must not destroy
       user data on retry.
    3. Count terminal artifacts (for ``items_removed`` accounting) BEFORE any
       mutation, so a counting failure leaves the live store untouched.
    4. Compute ``staging = store_path.parent / f".novetest.deleting.{ulid}"``.
    5. Single-syscall ``Path.rename(store_path, staging)`` — POSIX-atomic on
       the same filesystem. After this step the live store is detached.
    6. ``shutil.rmtree(staging, ignore_errors=False)``. If this raises, the
       live store is already detached; the orphaned staging dir is the
       caller's problem (Orchestration surfaces ``store-wipe-failed``). The
       primitive does NOT attempt to undo the rename — re-attaching a
       half-deleted tree would defeat the atomic-detach guarantee.

    Returns the ``WipeReport`` (store path, previous ``initialized_at``, and
    per-category removal counts).

    Entry also best-effort reaps ``.novetest.deleting.*`` residue from earlier
    failed wipes (MEM-03). The sweep runs BEFORE the not-found refusal —
    deliberately: the canonical leak scenario is a wipe whose ``rmtree`` failed
    after the detach rename, so the retry finds no ``store.json`` and would
    otherwise never reach a sweep placed later.
    """
    _sweep_staging_residue(store_path.parent)
    if not (store_path / STORE_METADATA_FILENAME).exists():
        raise ProjectStoreNotFoundError(
            f"No Project Store at {store_path}; nothing to wipe"
        )
    # _read_metadata raises ProjectStoreCorruptError on unreadable/invalid JSON.
    handle = _read_metadata(store_path)
    items_removed = _count_wipe_items(store_path)

    staging = store_path.parent / f"{_STAGING_DIR_PREFIX}{generate_ulid()}"
    store_path.rename(staging)
    shutil.rmtree(staging, ignore_errors=False)

    return WipeReport(
        store_path=store_path,
        previous_initialized_at=handle.initialized_at,
        items_removed=items_removed,
    )


def _sweep_staging_residue(parent: Path) -> None:
    """Best-effort reap of orphaned ``.novetest.deleting.*`` staging trees (MEM-03).

    A wipe whose ``rmtree`` failed after the detach rename leaves a
    ``.novetest.deleting.<ulid>`` tree that nothing re-reads — before this
    sweep it leaked forever. ``create_project_store`` and ``wipe_project_store``
    call this at entry so init/reset reclaim the space. Strictly best-effort:
    scan or removal failures are swallowed — the sweep must NEVER fail the
    verb it rides on. Only directories carrying the staging prefix are
    touched; the live ``.novetest/`` can never match.
    """
    try:
        candidates = [
            child
            for child in parent.iterdir()
            if child.name.startswith(_STAGING_DIR_PREFIX) and child.is_dir()
        ]
    except OSError:
        return
    for candidate in candidates:
        try:
            shutil.rmtree(candidate, ignore_errors=True)
        except OSError:
            continue


def sweep_staging_residue(workspace_path: Path) -> None:
    """Best-effort reap of orphaned ``.novetest.deleting.*`` trees (public).

    Thin public wrapper over the MEM-03 entry sweep
    (``_sweep_staging_residue``) with the same contract: strictly
    best-effort, NEVER raises, and touches only directories carrying the
    staging prefix directly under ``workspace_path``. Exists for non-memory
    callers — the reset workflow's uninitialized refusal path (S42 rider)
    reclaims residue through this instead of importing a private symbol.
    """
    _sweep_staging_residue(workspace_path)


def _count_wipe_items(store_path: Path) -> dict[str, int]:
    """Return ``{envelope_key: count}`` for every category in ``_WIPE_COUNT_SOURCES``.

    Categories with no on-disk artifacts return 0; missing source directories
    (engines whose subtree was never written to) are treated the same as empty
    ones, never as errors.
    """
    counts: dict[str, int] = {}
    for relpath, filename, envelope_key in _WIPE_COUNT_SOURCES:
        root = store_path / relpath
        counts[envelope_key] = (
            sum(1 for _ in root.rglob(filename)) if root.is_dir() else 0
        )
    return counts
