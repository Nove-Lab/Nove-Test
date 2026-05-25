---
from: novetest-memory-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-25
slug: find-runs-for-target
---

# Handoff: implement `memory.find_runs_for_target` — Phase 3 prerequisite

## Summary

Implements `find_runs_for_target` per
`agent-comms/tasks/memory-team-2026-05-25-find-runs-for-target.md` and
the pinned signature there. The function is a pure additive sibling to
`list_run_history` in `src/novetest/memory/store.py`; it unblocks the
parallel Regression team activation
(`tasks/regression-team-2026-05-25-activation.md`) and the next-cycle
`compare_runs` implementation, both of which consume this function per
`design/workflows/regression.md`.

## Worktree

- Worktree: `../novetest-find-runs-for-target`
- Branch: `memory-find-runs-for-target`
- Base: `7015dec` (`main` head at task start)

## Files changed

- `src/novetest/memory/store.py`
  - Added `find_runs_for_target(store, target_expression, *, include_tombstoned=False) -> list[MemoryEntry]`
    as a sibling to `list_run_history`. File-scan via `_iter_all_records`,
    filter on `record.target_expression`, drop tombstoned unless opted in,
    sort newest-first by `run_reference.created_at` descending.
  - Updated module docstring: moved `find_runs_for_target` out of the
    "deferred" list; `find_latest_analyzable_run` remains deferred to Phase 4.
  - No edit to `list_run_history`, `_iter_all_records`, or any other
    existing function.
- `src/novetest/memory/__init__.py` — re-exported `find_runs_for_target`
  in the existing `from novetest.memory.store import (...)` block and
  added it to `__all__` (alphabetical).
- `tests/unit/memory/test_store.py` — 8 new tests under a
  `# --- find_runs_for_target` section header, all going through the
  real `store_run_evidence` (+ `delete_run_evidence` where needed)
  public seams. Cases mirror the task's test plan #1-#8 exactly:
  empty store → `[]`; no match → `[]`; single match; multiple matches
  sorted newest-first across three distinct `created_at` values
  inserted out of order; mixed matching/non-matching; tombstoned
  excluded by default; tombstoned included when opted in
  (with `tombstoned_at` + `status == "tombstoned"` assertions); same
  `target_expression` with differing `target_type` — both returned
  (PM-expected behaviour: Memory filters on `target_expression` alone).

## Verification

- `uv run pytest -q tests/unit tests/integration` → **345 passed, 3 skipped**
  (was 337+3 before this slice; +8 new tests, all green; the 3 skips are
  the pre-existing Node-dependent jest integration tests, unrelated).
- `uv run mypy` → **clean** (52 source files, `--strict`).

## Worklog

Yes — appended a `2026-05-25 — phase3-entry / memory-find-runs-for-target`
entry to the top of `WORKLOG.md` (this slice touches `src/` + `tests/`,
so the `check-worklog-before-commit.sh` hook would fire otherwise).

## Schema-version implications

**None.** Pure additive read-side function over the existing v1 layout.
No model change, no persisted-entity change, no migration.

## Notes for Main Branch

- The keyword-only `include_tombstoned` is load-bearing (the `*,` in the
  signature is pinned by PM). Both Regression call sites use the default
  `False`; a future audit-style caller opts in explicitly. Do not let any
  refactor collapse it to a positional bool.
- Contract docs (`design/interace-contract/memory.md`) deliberately NOT
  touched — the function was already named in Regression's workflow
  (binding) and Memory's existing surface; the task scoped contract
  edits to a future `questions/` round if a gap surfaces.
- Zero file-area overlap with the parallel Regression activation task.

## DoD bullets believed closed

**None.** This is a Phase 3 prerequisite infrastructure slice; no
`delivery-phasing.md` Phase 3 DoD bullet closes from it alone. The
actual Phase 3 DoD bullets fire when Regression wires `compare_runs`
end-to-end next cycle.
