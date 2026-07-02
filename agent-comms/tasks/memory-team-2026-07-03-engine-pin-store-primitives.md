---
from: novetest-pm-team
to: novetest-memory-team
type: task
status: pending
created: 2026-07-03
slug: engine-pin-store-primitives
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Task: Memory — engine-pin store field + walk-up store discovery

- **Owner**: novetest-memory-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` (D1, D2, D6)
- **Sequencing**: no dependencies — may start immediately. Runs in parallel
  with the Run and Regression slices; the Orchestration slice depends on
  this one merging first.

## Goal

Provide the three store-level primitives the anchored-pin model needs:
(1) a persisted engine **pin** in `store.json` with get/set accessors,
(2) **upward-walk** nearest-store discovery, (3) tolerant loading of
legacy (pre-pin) stores.

## In scope

### 1. `store.json` pin field

Add an optional field to the store metadata:

```json
"pinned_engine": {"ecosystem": "python", "engine_name": "pytest"}
```

- Absent (legacy store) → loads as `None`; no migration rewrite on load
  (backfill is triggered by Orchestration per D6, via your setter).
- Whether this warrants a `schema_version` bump is your call per your
  existing schema policy — PM's read: additive optional field, tolerant
  reader, no bump. Document the choice in the module docstring.

### 2. Accessors

- `get_pinned_engine(store) -> PinnedEngine | None`
- `set_pinned_engine(store, ecosystem, engine_name) -> None` — atomic
  rewrite with the same write-safety guarantees as existing `store.json`
  writes; overwriting an existing pin is legal (re-pin per D1).
- Validate the pair against the six supported pairs (REQ-RUN-006). The
  canonical pair list lives in Run's territory
  (`src/novetest/run/engine_selector.py::_SUPPORTED_PAIRS`) and Run is
  consolidating it this cycle — import it rather than duplicating; if the
  import direction violates layering, expose the constant via
  `src/novetest/models/` and coordinate with Run through a question file.

### 3. `find_nearest_store(start: Path) -> Path | None`

Walk **upward** from `start` to the filesystem root; return the first
directory containing `.novetest/`; `None` if the walk exhausts. No
downward traversal of any kind (decision D2). Nearest wins — no
multi-store semantics (this implements the Open Q #17 resolution).

## Out of scope

- Engine detection (Run team), CLI/workflow wiring and the D6 migration
  *flow* (Orchestration — you only supply get/set), `RunRecord` changes
  (`engine_name` already exists), readiness caching (Open Q #18 stays open).

## Pinned file list

- **Edit**: `src/novetest/memory/project_store.py` (schema + accessors);
  walk-up may live there or in a sibling module of your choosing.
- **Create**: unit tests under `tests/unit/memory/` — pin round-trip,
  re-pin overwrite, legacy store loads with `None`, invalid pair rejected,
  walk-up found-at-start / found-at-depth-N / not-found, corrupt-store
  behavior consistent with existing `store.json` conventions.

## Acceptance criteria

- Unit green on the full CI matrix; mypy clean.
- Legacy fixture store (no pin field) loads without error or rewrite.
- `WORKLOG.md` entry; handoff at
  `agent-comms/handoffs/memory-team-2026-07-03-engine-pin-store-primitives.md`
  noting the schema-version choice explicitly.

## Effort estimate (PM's read — challenge if you disagree)

~60 LOC production, ~150 LOC tests. One short cycle, comparable to the
2026-06-24 wipe-primitive slice.
