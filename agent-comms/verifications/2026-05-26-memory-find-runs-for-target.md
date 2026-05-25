---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: record-only
created: 2026-05-26
slug: memory-find-runs-for-target
related:
  - handoffs/memory-team-2026-05-25-find-runs-for-target.md
  - tasks/memory-team-2026-05-25-find-runs-for-target.md
---

# Verification record: `memory.find_runs_for_target` (Phase 3 prerequisite)

## Merged commit

`4964e3a feat(memory): add find_runs_for_target for Phase 3 prerequisite`

Source handoff:
[`handoffs/memory-team-2026-05-25-find-runs-for-target.md`](../handoffs/memory-team-2026-05-25-find-runs-for-target.md).

## Why this is a record doc (no Manual Test action requested)

`find_runs_for_target` is a **pure internal Python API** in
`novetest.memory.store`. It is consumed by the Regression engine (which
currently exists only as a placeholder package) and is not wired into
any CLI command in this slice. I grepped both `src/novetest/cli/` and
`src/novetest/orchestration/` — every existing call site uses
`list_run_history`, not the new function:

```
src/novetest/cli/app.py:37,315,333,374,439          → list_run_history
src/novetest/orchestration/workflows/inspect.py:22,82 → list_run_history
src/novetest/orchestration/workflows/status.py:14,51 → list_run_history
```

There is therefore **no CLI surface for Manual Test to exercise this
cycle.** The 8 unit tests in `tests/unit/memory/test_store.py` (added in
this commit) cover the function's contract end-to-end through the real
`store_run_evidence` + `delete_run_evidence` public seams. The first
real exercise of this API across a CLI boundary will come when
Regression's `compare_runs` slice ships next cycle — that slice will
get its own Manual Test verification request.

## Gate (post-merge, on `main` @ `d9b3032`)

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit tests/integration` | **345 passed, 3 skipped** (was 337+3 before this slice; +8 new tests in `tests/unit/memory/test_store.py`, all green; the 3 skips are the pre-existing Node-dependent jest integration tests, unrelated to this slice). |
| `uv run mypy` | **clean** (52 source files, `--strict`). |

Both matched the Memory team handoff's claimed counts exactly.

## Conflict resolution

None. Clean fast-forward from `7015dec` (handoff's stated base) →
`4964e3a`. No INDEX collision (Memory did not regenerate `INDEX.md`;
later Regression merge's INDEX regen also didn't pick up this handoff,
so I re-ran `tools/regen_comms_index.py` after both merges to capture
both handoff files in a single regen).

## Surface added (for next cycle's awareness)

`novetest.memory.find_runs_for_target(store, target_expression, *, include_tombstoned=False) -> list[MemoryEntry]`

- Pure additive sibling to `list_run_history`.
- File-scan via `_iter_all_records`; filters on `RunRecord.target_expression`.
- Drops tombstoned entries by default; opt-in via the keyword-only flag.
- Sort: newest-first by `RunReference.created_at` descending.
- Re-exported from `novetest.memory`.
- **Keyword-only `include_tombstoned` is load-bearing** (pinned in the
  task signature) — do not let any future refactor collapse it to a
  positional bool. Regression's two call sites use the default `False`;
  any audit-style caller opts in explicitly.

## Edge cases worth probing when CLI exposure lands

These do NOT need probing this cycle (no CLI yet), but flagging so the
next cycle's Regression slice keeps them in scope when it adds its CLI
surface:

1. **Same `target_expression`, differing `target_type` → both returned.**
   Memory filters on `target_expression` alone (test #8 covers this).
   Regression team should be aware that mixed `target_type` is
   intentionally not de-duplicated at the Memory layer.
2. **Tombstone behavior under `include_tombstoned=True`.** Returned
   entries carry `tombstoned_at != None` and `status == "tombstoned"`;
   callers that need to filter further must inspect those fields.
3. **Empty store / no-match cases** both return `[]` (not error).
4. **Sort stability across identical `created_at`** — task did not pin
   stable-sort behavior; the Python `sorted(..., reverse=True)` impl is
   stable, so insertion order breaks ties. Memory team did not test
   this explicitly. If Regression ever depends on tie-break order,
   surface it as a contract clarification.

## Schema-version implications

None. Pure read-side function over the existing v1 layout. No model
change, no persisted-entity change, no migration.

## DoD bullets believed closed

None. Phase 3 prerequisite infrastructure slice; no
`delivery-phasing.md` Phase 3 DoD bullet closes from it alone. Phase 3
DoD bullets fire when Regression wires `compare_runs` end-to-end next
cycle.
