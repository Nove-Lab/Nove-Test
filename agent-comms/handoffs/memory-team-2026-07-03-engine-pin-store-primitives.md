---
from: novetest-memory-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-03
slug: engine-pin-store-primitives
related:
  - agent-comms/tasks/memory-team-2026-07-03-engine-pin-store-primitives.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Handoff: Memory — engine-pin store field + walk-up store discovery

## Worktree

- **Path**: `/home/yjshin/dev/aispace/Nove-Test-memory-engine-pin`
- **Branch**: `memory-team/engine-pin-store-primitives`, based on main `5e7d5b5`
- Single commit, ready to verify + merge (working tree clean).

## Files changed

| File | Change |
| --- | --- |
| `src/novetest/memory/project_store.py` | MOD — `PinnedEngine` dataclass, `ProjectStore.pinned_engine` field, `get_pinned_engine` / `set_pinned_engine`, `find_nearest_store`, `_parse_pinned_engine`; `locate_project_store` walk delegated to `find_nearest_store`; module-docstring schema note |
| `tests/unit/memory/test_project_store.py` | MOD — +18 tests (engine-pin section + walk-up section), `test_handle_to_dict_shape` updated for the new `pinned_engine: None` key |
| `design/interace-contract/memory.md` | MOD — new §1.1 "Engine pin & anchor discovery" (3 interfaces + schema-version note) |
| `WORKLOG.md` | top entry `2026-07-03 — anchored-pin / engine-pin-store-primitives` |
| `agent-comms/handoffs/…` + `agent-comms/INDEX.md` | this handoff + index regen |

## Schema-version choice (task acceptance criterion — explicit)

**No `schema_version` bump; store.json stays v1.** `pinned_engine` is an
additive optional field with a tolerant reader:

- absent (legacy store) → loads as `None`; loading **never rewrites** the file
  (verified byte-identical across `get_project_store_state`,
  `get_pinned_engine`, `locate_project_store`, and idempotent
  `create_project_store` re-invocation);
- unset → key **omitted**, not `null` (fresh stores byte-stable vs. pre-pin);
- malformed pin → `ProjectStoreCorruptError` (never silent `None` — silent-None
  would trigger a silent D6 re-detect that overwrites user intent);
- well-formed pin outside the six-pair matrix → loads tolerantly (forward
  compatibility with newer novetest versions); pair validation is write-time
  only (`set_pinned_engine` raises `ValueError` pre-mutation).

Rationale documented in the module docstring per the task brief.

## Public surface added (exact import paths — module-path-only)

```python
from novetest.memory.project_store import (
    PinnedEngine,          # frozen-slots dataclass: ecosystem, engine_name; .to_dict()
    get_pinned_engine,     # (store) -> PinnedEngine | None   — disk-authoritative
    set_pinned_engine,     # (store, ecosystem, engine_name) -> None — re-pin legal (D1)
    find_nearest_store,    # (start: Path) -> Path | None     — D2 upward walk
)
```

**NOT re-exported in `novetest.memory.__init__`** — same deliberate module-path
convention as the wipe-primitive cycle (that cycle's kick-back was exactly a
package-path import; see WORKLOG 2026-06-25). Orchestration: import from the
paths above.

`find_nearest_store` returns the **anchor/workspace directory** (the directory
*containing* `.novetest/`), per the task text — the store itself is at
`<returned>/.novetest/`. This is what the D6 migration flow wants (detection
runs at the anchor). It matches on `store.json` presence without parsing
(same predicate `locate_project_store` always used — locate now delegates its
walk here, so the two cannot diverge): metadata-less `.novetest/` is walked
past; corrupt `store.json` IS found and raises `ProjectStoreCorruptError` at
load time. No `NOVETEST_HOME` handling (that stays in `locate_project_store`).

## Pair-list validation source (task §2 coordination point)

Used Run's **public accessor** `list_supported_engine_pairs()` (not the
private `_SUPPORTED_PAIRS`) via a **function-local deferred import** inside
`set_pinned_engine`. No import cycle exists (Run never imports Memory;
replay→run cross-engine imports are precedented), so no layering violation and
**no models/-relocation question was needed**. If Run's parallel consolidation
slice relocates the canonical list, the one deferred-import line is Memory's
only touchpoint. Zero edits to any Run-owned file (their slice is in flight).

## Verification (all `env -u PYTHONPATH`)

| Gate | Result |
| --- | --- |
| `pytest -q tests/unit tests/integration` | **1366 passed / 3 skipped / 0 failed, 44 snapshots** (= 1348 baseline + 18 new; 3 skips = known jest/Node host issue) |
| targeted `tests/unit/memory/test_project_store.py` | 40 passed (22 pre-existing + 18 new) |
| `mypy --strict` Memory trees (memory/models/utils + test mirrors) | Success, 27 files |
| `mypy --strict src/novetest` (whole tree) | **Success, 114 files** |
| `git diff main --name-only` | exactly the files listed above — zero out-of-charter footprint |

`ProjectStore.to_dict()` gained a `pinned_engine` key (explicit `None` when
unset) — grepped: zero consumers in `src/`, no envelope/snapshot impact
(44 snapshots all pass unchanged).

## Merge notes for Main Branch

- **Order**: this slice has no dependencies and can merge immediately.
  Orchestration's anchored-pin slice **depends on this merging first** (per
  its task brief). Run and Regression slices are parallel/independent — no
  file overlap with either (Memory touched nothing under `src/novetest/run/`).
- Combined-tree gate suggestion: `mypy --strict src/novetest` (expect Success,
  114+) and full pytest.

## DoD bullets believed closed (PM verifies + ticks)

- store.json `pinned_engine` field: additive, tolerant, no-rewrite-on-load ✔ (believed)
- get/set accessors with six-pair validation via Run's canonical list ✔ (believed)
- `find_nearest_store` upward walk: found-at-start / found-at-depth / not-found / nearest-wins ✔ (believed)
- Legacy fixture store loads without error or rewrite ✔ (believed)
- Unit green + mypy clean ✔ (believed)
- WORKLOG entry + this handoff noting the schema-version choice explicitly ✔ (believed)

## Process note

CLAUDE.md mandates the `andrej-karpathy-skills:karpathy-guidelines` skill via
the Skill tool before code edits; the Skill tool was not available in this
session's toolset, so the four principles were applied manually (design
decisions settled pre-edit; no schema bump / no new module; 1-src-file
footprint; tests derived from acceptance criteria). Reported honestly per
GOTCHAS.md convention.
