---
from: novetest-pm-team
to: novetest-memory-team
type: task
status: pending
created: 2026-05-25
slug: find-runs-for-target
related:
  - design/interace-contract/memory.md
  - design/interace-contract/regression.md
  - design/workflows/regression.md
---

# Task: Implement `memory.find_runs_for_target` — Phase 3 prerequisite

## Why this task exists

Phase 3 (Regression Comparison) entry. Two Regression interfaces both
depend on this Memory function (per `design/workflows/regression.md`):

- `regression/resolve_latest_baseline(test_target)` → `memory/find_runs_for_target`
- `regression/check_regression_availability(run_reference)` → `memory/find_runs_for_target`

It is currently **unimplemented** — only mentioned in a doc comment in
`src/novetest/memory/store.py:16`. This slice ships the function so the
parallel Regression team activation, and next cycle's `compare_runs`
implementation, are unblocked.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-memory-team.md`
2. `src/novetest/memory/store.py` — especially `list_run_history`
   (lines ~103-120) and `_iter_all_records` — your implementation
   should mirror these patterns
3. `src/novetest/models/memory_entry.py` + `src/novetest/models/run_record.py`
4. `design/interace-contract/memory.md` — confirm Memory's contract
   surface conventions
5. `design/interace-contract/regression.md` + `design/workflows/regression.md`
   — see the two consumers, but you are NOT touching Regression code
6. `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` —
   defensive-parsing principle applies (gracefully handle missing fields)

## Pinned signature (do not deviate)

```python
def find_runs_for_target(
    store: ProjectStore,
    target_expression: str,
    *,
    include_tombstoned: bool = False,
) -> list[MemoryEntry]:
    """Return Memory Entries whose RunRecord.target_expression equals the
    given expression, newest-first by RunReference.created_at.

    Tombstoned runs are excluded by default. Callers performing baseline
    resolution (Regression) do not want deleted runs as viable baselines;
    callers wanting full history (audit / debugging) opt in via
    include_tombstoned=True.

    Returns an empty list when no run matches (not an error).
    """
```

The keyword-only `include_tombstoned` parameter is pinned by PM after
weighing two call sites:

- `resolve_latest_baseline` → wants `include_tombstoned=False` (default)
- `check_regression_availability` → same

A future audit-style caller may opt in. Do NOT add other filter
parameters (engine_name, target_type, etc.) — Phase 3's "comparability"
logic lives in the Regression layer, not in Memory.

## Implementation guidance (pinned)

- **File-scan implementation**, mirroring `list_run_history`. Use
  `_iter_all_records(store)`, filter on
  `resolved.record.target_expression == target_expression`, then on
  tombstone state, then sort newest-first by
  `record.run_reference.created_at` descending.
- Do **NOT** introduce a marker-file index
  (`memory/by_target/`). That is a separately-tracked
  open-question (delivery-phasing OQ#20) for "lazy when perf becomes
  noticeable" — not this slice.
- Do **NOT** modify `list_run_history` or any other existing function.
  Add the new function as a sibling.
- Export from `src/novetest/memory/__init__.py` alongside other public
  Memory surfaces.

## Files to write / modify

- `src/novetest/memory/store.py` — add `find_runs_for_target` (and any
  small private helper if cleanliness requires; do not refactor
  existing helpers).
- `src/novetest/memory/__init__.py` — re-export the new public name.
- `tests/unit/memory/test_store.py` — see test plan below.

## Files NOT to touch

- `src/novetest/regression/**` — empty placeholder; not yours.
- `src/novetest/coverage/**`, `src/novetest/orchestration/**`, `cli/**`
  — no consumers in this slice.
- `design/interace-contract/memory.md` — leave Memory's contract doc
  edits to a `questions/` round if you find a gap. The Phase 3 entry
  does not require a contract edit; this function is already named in
  Regression's workflow (binding) and aligns with Memory's existing
  shape.

## Test plan (mandatory; add to `tests/unit/memory/test_store.py`)

Each case writes Run Records via `store_run_evidence` (the real public
seam), then asserts `find_runs_for_target` output:

1. **Empty store** → returns `[]` (not None, not exception).
2. **No matching target_expression** → returns `[]`.
3. **Single matching run** → returns 1-element list whose
   `entry.run_record.target_expression == target_expression`.
4. **Multiple matching runs, mixed order of insertion** → returned
   list is sorted newest-first by `created_at` descending.
5. **Mix of matching + non-matching** → only matching entries returned.
6. **Tombstoned excluded by default** (`include_tombstoned=False`,
   which is the default): tombstone one of N matching runs via
   `delete_run_evidence`; `find_runs_for_target` returns the N-1 live
   runs only.
7. **Tombstoned included when opted in**
   (`include_tombstoned=True`): same setup as #6, returns all N runs
   (live + tombstoned).
8. **Same target_expression, different target_type** (if such a state
   is constructible — e.g. someone manually wrote two records) →
   document the behaviour you chose. PM expectation: filter on
   target_expression alone, so both come back. If you find this
   pathological, raise a `questions/` round.

## Verification commands (must pass before handoff)

- `uv run pytest -q tests/unit tests/integration` — green; +new tests.
- `uv run mypy` — clean (`--strict`).

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code. This is a small additive function — keep changes
surgical, no refactoring of `list_run_history` or `_iter_all_records`.

## Reporting

Write `agent-comms/handoffs/memory-team-<date>-find-runs-for-target.md`.
Append a `WORKLOG.md` entry (this slice touches `src/` + `tests/` so
the hook fires). Run `python3 tools/regen_comms_index.py` and stage
INDEX with the source.

**DoD bullets believed closed:** **None.** This is a Phase 3 prerequisite
infrastructure slice; no `delivery-phasing.md` Phase 3 DoD bullet closes
from it alone. State this explicitly in the handoff so PM does not
over-attribute.

## Companion task (PM note — not your responsibility)

The Regression team activation task
(`tasks/regression-team-2026-05-25-activation.md`) runs in parallel.
They will read your function's signature from the interface contracts
(which already name it); they do not need your implementation to
complete their activation. Zero file-area overlap.
