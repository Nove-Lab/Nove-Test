---
from: novetest-memory-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-25
slug: wipe-project-store-primitive
related:
  - agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
---

# Handoff: Memory — `wipe_project_store()` primitive

## Worktree

- **Path**: `/home/yjshin/dev/aispace/Nove-Test-memory-wipe-store-primitive`
- **Branch**: `memory-team/wipe-project-store-primitive`
- **Base**: `9f4dfe7` (main HEAD at start of cycle)
- **State**: single commit, working tree clean, ready for fast-forward / squash-merge.

## Files changed (4)

- `src/novetest/memory/project_store.py` — **MOD** (~80 LOC added)
  - +imports: `shutil`, `novetest.utils.ulid.generate_ulid`
  - +constants: `_WIPE_COUNT_SOURCES` (envelope key ↔ source dir/filename mapping), `_STAGING_DIR_PREFIX`
  - +class `WipeReport` (`@dataclass(slots=True, frozen=True)`, `store_path: Path`, `previous_initialized_at: int`, `items_removed: dict[str, int]`)
  - +exception `ProjectStoreNotFoundError(RuntimeError)`
  - +`wipe_project_store(store_path: Path) -> WipeReport`
  - +`_count_wipe_items(store_path: Path) -> dict[str, int]` (private helper)
  - No existing symbol modified or removed.
- `tests/unit/memory/test_project_store.py` — **MOD** (+6 tests at end of file, +2 imports, +1 helper)
  - Helper `_seed_artifact(path, body)` for terminal-artifact fixtures.
  - 6 new test cases (see "Test coverage" below).
- `design/interace-contract/memory.md` — **MOD** (new Section 3 "Store wipe primitive")
  - Signature table, atomicity guarantee, sequence of 6 steps, "primitive does NOT re-init" note.
- `WORKLOG.md` — **MOD** (new top entry).

## Test coverage (6 new cases, all green)

| # | Test | Property pinned |
|---|------|---|
| 1 | `test_wipe_happy_path_returns_report_and_deletes_tree` | End-to-end success: store + 1 fake run + 1 fake coverage fact → `WipeReport` with exact `items_removed` counts, store path gone, no staging orphan. |
| 2 | `test_wipe_refuses_when_store_missing` | Missing `.novetest/` path → `ProjectStoreNotFoundError`. |
| 3 | `test_wipe_refuses_when_metadata_missing` | Directory exists but no `store.json` → `ProjectStoreNotFoundError`. Directory left untouched. |
| 4 | `test_wipe_refuses_corrupt_store` | `store.json` present but unreadable → `ProjectStoreCorruptError`. **Live store NOT auto-wiped** (load-bearing safety property per decision doc). |
| 5 | `test_wipe_rmtree_failure_leaves_staging_orphan_not_live_store` | Monkeypatch `shutil.rmtree` to raise → live store path detached, staging orphan retains data, exception propagates as raw `OSError` (Orchestration translates to `store-wipe-failed`). |
| 6 | `test_wipe_then_create_project_store_succeeds` | Round-trip: wipe → `create_project_store(workspace)` rebuilds skeleton cleanly. Pins the post-wipe "no residual state" contract that `reset` relies on. |

## Verification results

- `env -u PYTHONPATH uv run pytest -q` (full suite): **1333 passed / 3 skipped / 0 failed / 40 snapshots passed**. (Baseline on main `9f4dfe7` was 1327 passed; delta = +6, exactly matches the new test count.)
- `env -u PYTHONPATH uv run mypy --strict src/novetest/memory src/novetest/models src/novetest/utils tests/unit/memory tests/unit/models tests/unit/utils`: **Success, 27 source files**.
- Sweeping the whole repo surfaces 126 mypy errors in other teams' test files (cli, integration/orchestration, etc.) — all pre-existing on `main` and out of Memory's charter. Not my territory.

## Schema-version implications

**None.** `wipe_project_store` does not touch any persisted schema:
- It reads `store.json` via the existing `_read_metadata` (which already enforces `SCHEMA_VERSION == 1`).
- It writes nothing; it only renames + rmtrees.
- The subsequent `create_project_store(workspace)` (Orchestration's responsibility, not this slice) writes the fresh `store.json` at the current `SCHEMA_VERSION`.

No `_v1.py` migration shim required. No `MemoryEntry` / `RunRecord` model touched.

## DoD bullets believed closed

None — per the task brief: "post-MVP addition, no `delivery-phasing.md` bullet exists yet; PM will add a Phase 7-adjacent bullet after merge."

## Test coverage gaps surfaced

- **OS / FS-level edge cases not unit-covered**: cross-filesystem rename (would silently degrade `Path.rename` from atomic-rename to copy-then-delete on some platforms), permission-denied on the `rename` itself, EBUSY on Windows, race between counting and rename (a peer writing into the live store after the count). The decision doc's exit-table covers these as `store-wipe-failed` on Orchestration's side, but a dedicated integration test under tests/integration/ would be cleaner. **Recommendation**: leave for the cross-OS release-matrix to catch; if a regression slips through, add a targeted integration test then.
- **Counting unit assumption**: my count of "runs" is the number of `record.json` files under `memory/runs/**`, mirroring `store._iter_all_records`. If Memory ever stores more than one `record.json` per run dir (currently impossible by construction), the count would over-report. Not a problem at v1; flagging for future schema evolution.
- **Orphan accumulation policy**: deliberately deferred to the future `vacuum` verb per decision doc §"Out of scope" (open question #6). A user who repeatedly crashes the `rmtree` step could accumulate `.novetest.deleting.<ulid>/` orphans indefinitely.

## Notes for Main Branch

- **Parallel cycle**: Orchestration's `agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md` is the consumer of this primitive. Their unit tests mock `wipe_project_store` (no merge ordering dependency), but their integration test (`tests/integration/test_reset_e2e.py`) gates on this primitive being on `main` first. Coordinate with PM if both worktrees are ready simultaneously — Memory should merge first.
- **Sequencing pin**: Decision doc §"Schedule pin" requires 0.1.x tagged on `main` before any reset-related merge. **`v0.1.2` is already tagged** (verified `git tag -l 'v0.1*'`), so the gate is satisfied.
- **No conflict footprint** with concurrent work: Memory's `src/novetest/memory/` and `tests/unit/memory/` are exclusive territory; the doc edit appends a new section to `design/interace-contract/memory.md`; WORKLOG.md is the standard merge-conflict-prone file but I appended at the top in the documented "newest on top" position.
- **Public surface added** (importable from `novetest.memory.project_store`): `wipe_project_store`, `WipeReport`, `ProjectStoreNotFoundError`. These are the exact symbol names Orchestration's task pre-committed to consuming.
