# Decision: `novetest reset` verb + Memory store-wipe primitive

- **Date**: 2026-06-24
- **Status**: approved by CEO
- **Authors**: PM (drafted), CEO (approved)
- **Updates**: `design/implementation-plan/delivery-phasing.md` (add reset verb to post-MVP queue), `design/workflows/orchestration.md` (new §reset section), `design/interace-contract/memory.md` (new `wipe_project_store()` API), `design/user-doc/{human,agent}/` (replace `rm -rf .novetest && novetest init` with `novetest reset --confirm`), `design/website-plan/handoff/docs/troubleshooting.md` (same)

---

## The decision (binding)

1. **Add a new top-level verb `novetest reset --confirm`** that wipes the active Project Store and re-runs `init` in one atomic operation.
2. **Memory team adds `wipe_project_store(store_path: Path) -> None`** in `src/novetest/memory/project_store.py` as the destructive primitive.
3. **Orchestration team registers `reset` in `src/novetest/cli/app.py`** with a `reset` workflow at `src/novetest/orchestration/workflows/reset.py` that calls `wipe_project_store(...)` then `initialize_project_workspace(...)`.
4. **The verb is scheduled for the first post-MVP slice** — *NOT* expanded into the current 0.1.x stable scope.

## Surface (frozen by this decision)

### Signature

```
novetest reset --confirm
```

- `--confirm` is **mandatory**. Without it, the verb exits **2** (`EXIT_USAGE`) with `errors[0].code = "confirm-required"` and a message naming the flag.
- No other flags at v1. (`--dry-run`, `--keep-history`, `--keep-coverage` deliberately deferred per YAGNI; revisit only on real demand.)

### Envelope (happy path)

```json
{
  "schema": "novetest/v1",
  "command": "reset",
  "ok": true,
  "data": {
    "store_path": "/abs/path/.novetest",
    "store_state": "ready",
    "previous_initialized_at": 1717939496000,
    "initialized_at": 1719215123000,
    "items_removed": { "runs": 12, "tombstones": 1, "coverage_facts": 12, "regression_pairs": 7, "localization_findings": 8, "replay_results": 2 },
    "engine_readiness": { /* identical shape to init's engine_readiness */ }
  },
  "errors": [],
  "warnings": []
}
```

Exit code: **0**.

### Error paths

| Trigger | Exit | `errors[0].code` | Recovery |
|---|---|---|---|
| `--confirm` missing | 2 | `confirm-required` | Re-invoke with `--confirm`. |
| No `.novetest/` found in walk-up | 2 | `uninitialized` | Run `novetest init` (nothing to reset). |
| `.novetest/store.json` exists but unreadable | 5 | `store-corrupt` | Inspect manually. **Reset deliberately refuses to proceed against a corrupt store** — surface to operator. (Rationale: a corrupt store may be a transient FS issue; auto-wiping is the wrong default.) |
| FS error during wipe (permission, EBUSY, etc.) | 5 | `store-wipe-failed` | The atomic-rename guard means the original `.novetest/` is still present on failure. Inspect FS state, retry. |

### Atomicity guarantee (load-bearing)

The wipe primitive **must NOT delete the live `.novetest/` in place.** Required sequence:

1. Resolve `store_path` via `locate_project_store()` (walk-up).
2. Compute `staging = store_path.parent / f".novetest.deleting.{ulid()}"`.
3. Atomic `Path.rename(store_path, staging)` (single `rename(2)` syscall on same FS).
4. `shutil.rmtree(staging)` (best-effort; if it fails, the live store is already detached so the user is in the "uninitialized" state — recoverable via a fresh `novetest init`).
5. Re-call `create_project_store(workspace_path)` to rebuild the skeleton + `store.json`.
6. Re-call `assess_engine_readiness(workspace_path)`.

A crash between steps 3 and 5 leaves an "uninitialized" workspace + an orphaned `.novetest.deleting.<ulid>/` directory. The next `novetest init` succeeds (orphan is ignored); a future GC verb (open question #6 `vacuum`) can sweep orphans by name pattern.

## Why now

- We just shipped the MVP user-doc set and **had to document `rm -rf .novetest && novetest init` as the official reset pattern in two places** (`troubleshooting.md` human + agent + website Docs handoff). That documentation acts as quantified evidence the gap is real.
- The CLI's three load-bearing positioning promises (envelope-determinism, cross-platform, agent-callable without shell) are all violated by the current `rm -rf` recommendation. The verb is the cheapest way to honor all three.

## Why this scope (not a bigger one)

- **No `--dry-run`**: the dry-run answer is `novetest memory list` + `novetest status` (existing verbs already show what's stored). Adding `--dry-run` to `reset` duplicates surface.
- **No partial-wipe flags (`--keep-history`, `--keep-coverage`, etc.)**: those overlap with the future `vacuum` verb (open question #6). Settling vacuum's design first is the right order; we don't want to ship two verbs with overlapping flag spaces.
- **No interactive confirm prompt**: the CLI is agent-first. Interactive prompts break agent invocation. A required `--confirm` flag is the agent-friendly equivalent.
- **No GC of orphaned `.novetest.deleting.<ulid>/` dirs at v1**: deferred to the future `vacuum` work. The orphan is benign (the next `init` works fine).

## Relationship to existing open questions

- **Q#6 (tombstone retention + `vacuum` semantics)** — adjacent but distinct. `vacuum` is per-entry garbage collection of tombstoned runs; `reset` is whole-store wipe. They coexist post-MVP. `vacuum` design must NOT preempt this verb.
- **Q#17 (Project Store discovery scope)** — resolved by `locate_project_store()`'s walk-up. `reset` inherits whatever scope walk-up settles on; no new policy.

## Schedule pin

- **NOT in 0.1.x stable.** Reset ships as the first verb of the post-MVP queue, after 0.1.x is tagged and released.
- Concrete entry condition: 0.1.x release tagged on `main`; no open `findings/` blockers.
- Concrete exit condition: `reset` + `--confirm` round-trips on Linux, macOS, Windows in the existing release-matrix; snapshot pin of the new envelope shape merged in CI; user-doc + website Docs updated.

## Implementation owners

- **Memory team** (`src/novetest/memory/project_store.py`): `wipe_project_store()` primitive + a unit test that covers the atomic-rename failure mode.
- **Orchestration team** (`src/novetest/cli/app.py`, `src/novetest/cli/renderers/`, `src/novetest/orchestration/workflows/`): the verb, the workflow, the renderer, the registry entry, integration test, snapshot pin.

PM coordinates handoff order (Memory primitive first, then Orchestration's verb consumes it).

## Out of scope for this decision

- The `vacuum` verb design (Q#6 — separate cycle).
- MCP transport for `reset` (Phase 7 inherits the verb when MCP is wired up).
- A `novetest workspaces reset` polyglot variant (would be added alongside the future `workspaces test` verb if/when that lands).
