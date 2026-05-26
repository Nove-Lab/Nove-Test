---
from: novetest-pm-team
to: novetest-memory-team
type: task
status: open
created: 2026-05-26
slug: has-regression-facts
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/tasks/regression-team-2026-05-26-compare-runs-impl.md
  - src/novetest/memory/store.py
  - src/novetest/models/memory_entry.py
---

# Task: Memory `_availability_flags` — flip `has_regression_facts` when a pair file exists

## Why this task exists

Phase 3 entry, parallel to the Regression team's first implementation slice. Decision `decisions/2026-05-26-regression-facts-json-layout.md` §C.5 assigns the `MemoryEntry.has_regression_facts` flip-time wiring to Memory (consistent with Coverage's precedent — Memory owns the probe; the engine team owns the file shape). Decision §1 pins the on-disk directory layout this probe scans:

```
<store>/regression/pairs/run_<baseline_run_id>__run_<target_run_id>/regression_facts.json
```

The flag must flip to `True` for a given run whenever ANY `regression_facts.json` referencing that run as either baseline OR target exists on disk.

This task ships parallel to the Regression engine task; no file overlap. The Regression engine task creates the file shape; this task makes Memory's availability flag react to it. Together they close the Memory↔Regression availability loop before any CLI verb consumes it.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — coding guidelines (Karpathy skill is mandatory on every code edit)
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/2026-05-26-regression-facts-json-layout.md` — **the directory naming this probe scans is pinned in §1; the C.5 resolution names this task explicitly**
4. `.claude/agents/novetest-memory-team.md` — your charter
5. `WORKLOG.md` top 5 entries
6. `src/novetest/memory/store.py` — locate `_availability_flags` (current impl scans `<store>/coverage/facts/run_<run_id>/coverage_facts.json` for the Coverage flag)
7. `src/novetest/models/memory_entry.py` — `has_regression_facts` field already exists (see memory_entry.py:42), this task only wires the probe to flip it

## Scope (what this slice MUST land)

### Files to edit

1. **`src/novetest/memory/store.py`** — extend `_availability_flags` with a Regression branch:
   - Scan `<store>/regression/pairs/` for any directory whose name contains `run_<run_id>` as a substring (the run_id appears in either the `run_<A>__run_<B>` baseline position OR the `run_<A>__run_<B>` target position).
   - When found AND the directory contains a `regression_facts.json` file → set `has_regression_facts = True`.
   - When `<store>/regression/pairs/` does not exist (cold store, no Regression activity yet) → flag stays `False` cleanly, no exception.
   - Surgical addition only. Do NOT refactor the Coverage probe; do NOT change the function signature; do NOT touch unrelated branches.
   - Implementation hint: `Path.glob(f"run_*__run_*")` to enumerate pair dirs, then a substring check `f"run_{run_id}" in dir.name`. Avoid `iterdir()` if it returns non-directory entries; filter by `is_dir()`.
   - Performance: `O(N pairs)` per probe is acceptable at v1. Phase 3 OQ #20 (marker-file index `memory/by_target/`) is a separate, deferred follow-up — NOT this slice.

### Files to add (tests)

2. **`tests/unit/memory/test_store.py`** — extend the existing `_availability_flags` test cluster with a `# --- has_regression_facts` section:
   - **Cold store** (no `<store>/regression/pairs/` dir) → flag is `False`.
   - **Empty pairs dir** (`<store>/regression/pairs/` exists but is empty) → flag is `False`.
   - **Run is baseline of a pair** → flag is `True`. Construct a stub pair dir `run_<run_id>__run_<other>/regression_facts.json`; verify `has_regression_facts` flips.
   - **Run is target of a pair** → flag is `True`. Construct `run_<other>__run_<run_id>/regression_facts.json`; verify flip.
   - **Run appears in multiple pairs** (both as baseline and target across different pairs) → flag is still `True` (idempotent).
   - **Pair dir exists but `regression_facts.json` missing** (e.g. crashed mid-write or hand-deleted) → flag is `False`. This is the deliberate "file is the truth, directory is the index" guard.
   - **Run does not appear in any pair** → flag is `False`.
   - **Tombstoned run with matching pair** (per decision §C.1, tombstoned runs may still have stale pair files on disk for audit) → flag is `True`. Memory's job is to reflect what's on disk; the Regression engine handles the tombstone fail-hard at compare time. (This is a deliberate design distinction: availability ≠ usability.)

   The stub `regression_facts.json` content can be a minimal valid JSON object (e.g. `{"schema_version": 1}`) — the probe checks existence only, not parseability. (If you find yourself parsing the file in the probe, you've gone too deep; the file shape is Regression Team's territory.)

### Files to NOT touch

- `src/novetest/models/memory_entry.py` — the `has_regression_facts` field already exists (see line 42). No model change.
- `src/novetest/regression/**` — the parallel Regression task is creating these files. Do not collide.
- `src/novetest/coverage/**` — out of scope.
- `pyproject.toml` — no new deps.

## Acceptance criteria

- `uv run pytest -q tests/unit tests/integration` → all green (current baseline 345; +8 new from this slice = 353+).
- `uv run mypy` → clean, `--strict`, no new source files (this is an edit-in-place slice).
- The integration test that already exercises `_availability_flags` end-to-end (find it via `grep -rn "_availability_flags\|has_coverage_facts" tests/integration/`) still passes; no regression in the Coverage flag's behavior.

## Out of scope (do NOT include in this slice)

- The Regression `compare_runs` impl — parallel task, Regression team's territory.
- OQ #20 marker-file index (`<store>/memory/by_target/`) — separate, deferred follow-up.
- `find_runs_for_target` extensions — landed last cycle.
- Any change to `MemoryEntry`'s wire shape or schema_version.
- `_availability_flags` probe for Localization (`has_localization_findings`) or Replay (`has_replay_result`) — Phase 4 / Phase 5 work, not this task.

## Verification

- Run `git fetch && git status` before starting and confirm you're on a clean `main` synced with origin (pre-flight discipline per `agent-comms/history/2026-05-25-duplicate-merge-cycle.md`).
- Karpathy skill MUST be invoked before each code edit (per `CLAUDE.md` Coding Guidelines).
- `uv run pytest -q tests/unit tests/integration` and `uv run mypy` both green before writing the handoff.
- Manual smoke (optional): in a tmp Project Store, hand-create `<store>/regression/pairs/run_AAA__run_BBB/regression_facts.json` with `{"schema_version": 1}`, then call `get_memory_entry_availability(store, "AAA")` and verify the returned object has `has_regression_facts=True`.

## Reporting back

Standard handoff at `agent-comms/handoffs/memory-team-2026-05-26-has-regression-facts.md`.

- "DoD bullets believed closed" should list **none** for `delivery-phasing.md` — Phase 3 DoD bullets close when CLI verbs ship (follow-up cycles). This slice is infrastructure that allows downstream consumers (like `memory show <run_id>` displaying the right availability flags after a Regression `compare_runs` has run) to reflect Regression activity.
- Note in the handoff if the test count for `tests/unit/memory/test_store.py` shifts in a way PM should reflect in the WORKLOG entry.
