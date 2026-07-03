---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-03
slug: engine-pin-store-primitives
related:
  - agent-comms/handoffs/memory-team-2026-07-03-engine-pin-store-primitives.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Verification request: Memory — engine-pin store field + walk-up discovery (anchored-pin D1/D2/D6)

## Merged

- **Commit**: `4196ee9` (single commit, code+comms) — rebased onto slice 1
  and FF-merged as slice 2/4 of the 2026-07-03 batch.
- **Source handoff**: `memory-team-2026-07-03-engine-pin-store-primitives.md`.
- **Merge mechanics**: one WORKLOG.md keep-both conflict (both slices add a
  top entry; memory's placed above test-reruns'). No other conflicts.

## Gate (on the merged tree)

- `env -u PYTHONPATH uv run mypy` → Success, 114 source files.
- Slice gate **1391 passed / 3 deselected / 47 snapshots** (= +18 memory
  tests); final batch tree 1418/3/47.
- Pre-merge review (code-reviewer): **MERGE-OK, zero blocking findings.**
  No-rewrite-on-load verified as a genuine byte comparison; malformed vs
  well-formed-unsupported pin distinction confirmed on the shape axis.

## Public surface (module-path-only — deliberately NOT in `novetest.memory.__all__`)

```python
from novetest.memory.project_store import (
    PinnedEngine,        # frozen dataclass: ecosystem, engine_name
    get_pinned_engine,   # (store) -> PinnedEngine | None  (disk-authoritative)
    set_pinned_engine,   # (store, ecosystem, engine_name) -> None (re-pin legal)
    find_nearest_store,  # (start: Path) -> Path | None  (returns ANCHOR dir,
)                        #  i.e. the directory CONTAINING .novetest/)
```

Same module-path convention as the wipe-primitive cycle — the 2026-06-25
kick-back was exactly a package-path import; consumers must NOT expect
`from novetest.memory import ...` for these four.

## Verification steps (all behaviors below observed live on the merged tree)

Run from the repo with `env -u PYTHONPATH uv run python`:

```python
import json, tempfile
from pathlib import Path
from novetest.memory.project_store import (
    PinnedEngine, get_pinned_engine, set_pinned_engine,
    find_nearest_store, create_project_store,
)

ws = Path(tempfile.mkdtemp()) / "ws"; ws.mkdir()
store = create_project_store(ws)
sj = ws / ".novetest" / "store.json"

# M1 — fresh store: pin None, key OMITTED (not null), load never rewrites
before = sj.read_bytes()
assert get_pinned_engine(store) is None
assert b"pinned_engine" not in before
assert sj.read_bytes() == before          # observed: byte-identical

# M2 — set pin, observed store.json content:
set_pinned_engine(store, "python", "pytest")
json.loads(sj.read_text())["pinned_engine"]
#   == {"ecosystem": "python", "engine_name": "pytest"}
get_pinned_engine(store)                  # PinnedEngine('python', 'pytest')

# M3 — invalid pair: ValueError PRE-mutation (store.json untouched)
snap = sj.read_bytes()
try: set_pinned_engine(store, "zig", "zig-test")
except ValueError: assert sj.read_bytes() == snap   # observed

# M4 — walk-up: nested dir -> anchor; outside store tree -> None
nested = ws / "src" / "pkg" / "deep"; nested.mkdir(parents=True)
assert find_nearest_store(nested) == ws   # observed
assert find_nearest_store(ws.parent) is None
```

M5 — package path deliberately rejects: none of the 4 symbols appear in
`novetest.memory.__all__` (observed).

Targeted suite: `env -u PYTHONPATH uv run pytest -q
tests/unit/memory/test_project_store.py` → 40 passed (22 + 18 new).

## Critical edge cases worth probing

1. **Legacy store no-rewrite (D6 precondition)**: any pre-pin `.novetest/`
   (e.g. an old fixture or a workspace initialized before this merge) must
   load with `pinned_engine → None` and its `store.json` must stay
   byte-identical across `get_project_store_state` / `get_pinned_engine` /
   `locate_project_store`. No `schema_version` bump — store.json stays v1.
2. **Malformed vs unknown pin**: a hand-edited `"pinned_engine": "pytest"`
   (wrong shape) → `ProjectStoreCorruptError`, never silent None (silent
   None would trigger a silent D6 re-detect overwriting user intent);
   a well-formed `{"ecosystem": "zig", "engine_name": "zig-test"}` loads
   TOLERANTLY (forward compat) — validation is write-time only.
3. **Metadata-less `.novetest/` dirs** are walked PAST by
   `find_nearest_store` (matches on `store.json` presence); a corrupt
   `store.json` IS found and raises at load time.
4. **Reviewer note for the future Orchestration consumer**:
   `ProjectStore.to_dict()` emits explicit `"pinned_engine": null` when
   unset while persistence OMITS the key — zero consumers today, but a
   future status-envelope consumer would surface the explicit null.
5. **Reviewer note**: empty-string pin `{"ecosystem": "", "engine_name": ""}`
   loads tolerantly (shape-only read validation) — it simply never matches
   the six-pair matrix at dispatch.
6. **Coupling proven in-batch**: `set_pinned_engine` validates via
   `from novetest.run.engine_selector import list_supported_engine_pairs`
   (deferred, function-local) — exercised green AGAINST the rewritten
   engine_selector merged as slice 3 (final combined gate + live M2/M3).

## Notes

- Handoff's file table mentioned an INDEX.md regen that is not in the diff
  (regen was a no-op — handoffs with `status: ready` are not categorized).
  Bookkeeping only.
- D1/D6 remain OPEN surface: nothing calls get/set yet — the pending
  Orchestration `anchored-init-and-verb-resolution` slice is the consumer.
