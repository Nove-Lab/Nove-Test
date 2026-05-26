---
from: novetest-memory-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-26
slug: has-regression-facts
---

# Handoff: Memory `_availability_flags` — pin `has_regression_facts` semantics with 8 new test cases

## Summary

Lands the test surface specified by
`agent-comms/tasks/memory-team-2026-05-26-has-regression-facts.md` for
the Memory `_availability_flags` Regression branch — the implementation
(`_any_regression_pair_exists` + the `"has_regression_facts"` key in
`_availability_flags`) already shipped together with the
`find_runs_for_target` slice (commit `4964e3a`, merged
`2732310`). This slice is **test-only**: it nails down the 8 cases the
task brief enumerated so the contract pinned by
`decisions/2026-05-26-regression-facts-json-layout.md` §1 + §C.5 is
exercised before the Regression team's parallel `compare_runs` task
starts writing real `regression_facts.json` files.

No `src/` change. No new module. No model touch.

## Worktree

- Worktree: `/home/yjshin/dev/aispace/Nove-Test-memory-has-regression-facts`
- Branch: `memory-team/has-regression-facts`
- Base: `e80e3cf` (`main` head at task start; clean fetch+status confirmed pre-flight)

## Files changed

- `tests/unit/memory/test_store.py` — added a `# --- has_regression_facts`
  section (after `find_runs_for_target`) with 8 new tests + one private
  helper `_write_stub_regression_facts(pair_dir)` (creates the dir and
  writes a `{"schema_version": 1}` stub file — the probe checks
  existence only, never parses, per the task brief). Cases:
  1. **Cold store** — no `<store>/regression/pairs/` dir at all → flag
     False. Sanity-asserts `regression/pairs/` was never created (project
     store init materializes `regression/` empty, but `regression/pairs/`
     is born when Regression writes its first pair — the probe scans
     the `pairs/` subdir specifically).
  2. **Empty `pairs/` dir** → flag False.
  3. **Run is baseline (left) of a pair** (`run_<rid>__run_<other>/`) →
     flag True.
  4. **Run is target (right) of a pair** (`run_<other>__run_<rid>/`) →
     flag True. Confirms probe is positionally agnostic.
  5. **Run participates in three pairs** (mix of left & right positions) →
     flag True, idempotent.
  6. **Pair dir without `regression_facts.json`** → flag False. The
     deliberate "file is the truth, directory is the index" guard
     (simulates crashed mid-write or hand-deleted file).
  7. **Pairs exist for other runs only** → flag False. Confirms the
     substring needle `run_<rid>` does not accidentally match unrelated
     pair names.
  8. **Tombstoned run with stale matching pair** → flag True. Per
     decision §C.1, Memory reflects what's on disk; tombstone fail-hard
     is Regression's territory (availability ≠ usability).
- `WORKLOG.md` — appended a `2026-05-26 — phase3 / memory-has-regression-facts`
  entry at the top.

**No `src/` files were edited.** The probe implementation already
existed.

## Verification

- `git fetch && git status` (pre-flight) — clean, on `main` @ `e80e3cf`.
- `uv run pytest -q tests/unit/memory/test_store.py` — **33 passed** (was 25; +8 new).
- `uv run pytest -q tests/unit tests/integration` — **353 passed, 3 skipped**
  (was 348+3 before this slice; the 3 skips are the pre-existing
  Node-dependent jest integration tests).
- `uv run mypy` — **clean** (52 source files, `--strict`).

## Worklog

Yes — appended a `2026-05-26 — phase3 / memory-has-regression-facts`
entry to the top of `WORKLOG.md`. The slice touches `tests/`, so the
`check-worklog-before-commit.sh` hook would fire otherwise.

## Schema-version implications

**None.** Test-only addition over the existing v1 layout. No
`MemoryEntry` wire-shape change (`has_regression_facts` field has been
present since the model landed); no `record.json` change; no migration.

## DoD bullets believed closed (PM to verify)

- **`design/implementation-plan/delivery-phasing.md`** — **none.** Per the
  task brief's "Reporting back" section: Phase 3 DoD bullets close when
  CLI verbs ship (follow-up cycles). This slice is infrastructure that
  allows downstream consumers (`memory show <run_id>`,
  `inspect <run_id>`) to correctly reflect Regression activity through
  `has_regression_facts` once the parallel Regression `compare_runs`
  slice lands.

## Notes for Main Branch

- The task brief's pytest baseline was `345`, but the actual pre-slice
  baseline on `e80e3cf` was `348+3` (5 tests accumulated in intervening
  Regression activation cycles). `+8 new` lands at `353+3` regardless —
  the absolute count moved, the delta did not. PM may want the WORKLOG
  entry to reflect `353+3` rather than the brief's predicted `353+`.
- The implementation (`_any_regression_pair_exists` +
  `_availability_flags["has_regression_facts"]`) is unchanged from
  commit `4964e3a`. This handoff adds zero `src/` diff. The merge will
  be a pure `tests/unit/memory/test_store.py` + `WORKLOG.md` change.
- No file overlap with the Regression team's parallel
  `compare_runs` task. The two slices land independently.
- OQ #20 (marker-file index `<store>/memory/by_target/`) remains a
  deferred follow-up — not in scope here.
