# Task: Memory — `wipe_project_store()` primitive

- **Owner**: novetest-memory-team
- **Status**: pending
- **Created**: 2026-06-24
- **Pinned decision**: `agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md`
- **Sibling task**: `agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md` (consumes this primitive)
- **Phase**: first slice **after** 0.1.x stable release tagged. Do **not** start until 0.1.x is on `main`.

## Goal

Add a single destructive primitive, `wipe_project_store(store_path: Path) -> WipeReport`, in `src/novetest/memory/project_store.py`. This is the only file you need to edit in `src/`. The Orchestration team will call this primitive from a new `reset` workflow they own.

## Why

The CLI today documents `rm -rf .novetest && novetest init` as the official "start over" pattern (see `design/user-doc/{human,agent}/troubleshooting.md` and `design/website-plan/handoff/docs/troubleshooting.md`). That out-of-band recommendation violates novetest's envelope-determinism / cross-platform / agent-first positioning. The new `reset` verb (Orchestration's task) replaces it. Your job is the destructive primitive underneath.

## Scope

### In scope (you do this)

1. New function in `src/novetest/memory/project_store.py`:

   ```python
   def wipe_project_store(store_path: Path) -> WipeReport: ...
   ```

   - `store_path` MUST be an already-resolved `.novetest/` directory (caller invoked `locate_project_store()` first).
   - Sequence (load-bearing per decision doc §"Atomicity guarantee"):
     a. Refuse if `store_path` does not exist or does not have a `store.json` (raise `ProjectStoreNotFoundError`, a new exception in this same file — sibling to the existing `ProjectStoreCorruptError`).
     b. Refuse if `store.json` is unreadable (re-raise `ProjectStoreCorruptError` via `_read_metadata`). **Do NOT auto-wipe a corrupt store.** That's a load-bearing safety property.
     c. Enumerate the items that will be removed (counts only — for the envelope `data.items_removed`). Walk the existing `_TOP_LEVEL_DIRS` + `_ENGINE_DIRS` enumeration to count entries; do NOT hardcode a parallel list. Counting may be done before or after the rename — use whichever keeps the function pure of partial-state risk.
     d. Compute `staging = store_path.parent / f".novetest.deleting.{<ulid>}"` using `novetest.utils.ulid` (already imported elsewhere in this team's code).
     e. `Path.rename(store_path, staging)` — single `rename(2)` syscall. On same filesystem this is atomic.
     f. `shutil.rmtree(staging, ignore_errors=False)`. If this raises, the live store is already detached (caller will surface `store-wipe-failed`); do NOT attempt to undo step e.
     g. Return `WipeReport`.

2. New return type at module top:

   ```python
   @dataclass(slots=True, frozen=True)
   class WipeReport:
       store_path: Path
       previous_initialized_at: int          # from store.json read in step b
       items_removed: dict[str, int]         # {"runs": N, "tombstones": N, "coverage_facts": N, "regression_pairs": N, "localization_findings": N, "replay_results": N}
   ```

   Keys in `items_removed` are pinned by the decision doc envelope shape — match them exactly.

3. New exception `ProjectStoreNotFoundError(RuntimeError)` for the "no store at this path" path. Place beside the existing `ProjectStoreCorruptError`.

4. Tests in `tests/unit/memory/test_project_store.py`:
   - happy path: create store, populate one fake run + one fake coverage fact file, wipe, assert `WipeReport.items_removed` matches counts, assert `store_path` no longer exists.
   - refuse path: store_path missing → raises `ProjectStoreNotFoundError`.
   - refuse path: store.json missing inside an existing directory → raises `ProjectStoreCorruptError`.
   - refuse path: store.json present but unparseable → raises `ProjectStoreCorruptError`.
   - atomicity property: simulate failure at the `shutil.rmtree` step (monkeypatch `shutil.rmtree` to raise). After the exception, assert the original `store_path` does NOT exist (it's at `staging`) and the staging dir is still on disk. (This documents the "rmtree failure leaves orphan, never destroys data half-way" property.)
   - re-init after wipe: wipe a store, then call `create_project_store(workspace)` again, assert it succeeds (proves the primitive doesn't leave residual state that breaks `init`).

### Out of scope (NOT your job)

- The `reset` verb itself, its workflow, its renderer, its CLI registration — those are Orchestration's task.
- Garbage collection of orphaned `.novetest.deleting.<ulid>/` directories (deferred per decision §"Out of scope").
- Updating user-doc / website-plan — PM will do that after both team handoffs land.
- Bumping `store_state` semantics — `wipe_project_store()` does not touch state; the subsequent `create_project_store()` call (Orchestration's responsibility) writes the fresh `store.json`.

## Pinned file list

- **Edit**: `src/novetest/memory/project_store.py` (only).
- **Edit (tests)**: `tests/unit/memory/test_project_store.py`.
- **Update doc**: `design/interace-contract/memory.md` — add the `wipe_project_store` signature + the atomicity guarantee + the `WipeReport` dataclass shape, in a new Section "Store wipe primitive". Keep prose tight; cite the decision doc.

Do NOT touch any file in `src/novetest/cli/**`, `src/novetest/orchestration/**`, or anything outside `src/novetest/memory/` and the test mirror.

## Acceptance criteria

- All 6 test cases above land green on Linux, macOS, Windows in CI (the standard release-matrix).
- `wipe_project_store()` is the ONLY new public symbol added to `project_store.py`. `WipeReport` + `ProjectStoreNotFoundError` are supporting types; the rest of the module is unchanged.
- `design/interace-contract/memory.md` documents the primitive.
- `WORKLOG.md` entry per the standard format.
- Handoff at `agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md` includes:
  - Pointer to the merged worktree.
  - "DoD bullets believed closed" list (none for this slice — it's a post-MVP addition, no `delivery-phasing.md` bullet exists yet; PM will add a Phase 7-adjacent bullet after merge).
  - Any test coverage gaps surfaced during the work.

## Coordination

- The Orchestration team's task explicitly waits for your handoff before its integration test can pass. The two worktrees can develop in parallel — the Orchestration team can mock `wipe_project_store()` in its unit tests — but the integration test (the round-trip `novetest reset --confirm`) requires your primitive landed.
- **Sequencing pin**: do not merge until 0.1.x is tagged on `main`. PM will signal the green light via `agent-comms/questions/` if there's any doubt.

## Effort estimate (PM's read — challenge if you disagree)

- ~60–90 LOC of production code in `project_store.py`.
- ~150–200 LOC of test code.
- ~40 LOC of doc update in `memory.md`.
- One short cycle. If this estimate balloons, surface via `agent-comms/questions/` before going wide on implementation.
