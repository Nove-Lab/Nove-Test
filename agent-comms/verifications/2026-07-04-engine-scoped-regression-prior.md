---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-07-04
slug: engine-scoped-regression-prior
related:
  - agent-comms/handoffs/localization-team-2026-07-03-engine-scoped-regression-prior.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Verification: localization engine-scoped regression-prior (D5 Finding B — Wave 2, 2/3)

## Merged commit

- **`4818642`** `localization: engine-scoped regression-prior via shared resolve_baseline_for_run (D5 Finding B)`
  (rebase of worktree commit `a09208c` off `7c6ece6` onto `17a61f8`; ONE conflict — `WORKLOG.md`, both slices prepend an entry — resolved incoming-on-top per convention, zero source conflicts)
- Wave-2 cohort tip: **`76a4ffb`**

## Source handoff

- `agent-comms/handoffs/localization-team-2026-07-03-engine-scoped-regression-prior.md`

## Merge gate (combined tip `76a4ffb`, equipped host)

- pytest full suite → **1511 passed / 5 skipped / 0 failed**, 49 snapshots
- mypy → **Success, 116 source files**

## What changed (behavior — NO envelope changes)

`try_get_latest_regression_facts` (localization/derive.py) no longer does
an engine-blind "newest strictly-older sibling" scan; prior-pair selection
now delegates to Regression's shared engine-aware selector
`resolve_baseline_for_run(store, entry)` (D5). In a mixed-engine store the
FLUCCS `changed_files` reweighting (aggregate + failure-proximity modes)
now activates from the same-engine pair one step back instead of silently
degrading to "no regression prior". Best-effort posture unchanged (never
raises, cache-only `get_regression_facts` read, `None` on any failure).

**API note (internal)**: second param changed `record: RunRecord` →
`entry: MemoryEntry`. Merge-gate grep at `76a4ffb` confirms ZERO callers
outside `src/novetest/localization/` (sole production caller
`derive_localization_findings`, same file) — the parallel Orchestration
slice did NOT grow a caller.

## Verification steps for Manual Test

1. **Acceptance test (the behavioral proof)**:
   ```bash
   env -u PYTHONPATH uv run pytest -q tests/unit/localization/test_regression_prior.py -v
   ```
   → 6 passed. The key case is
   `test_mixed_engine_store_applies_fluccs_reweighting`: series
   [pytest, cargo-test, pytest] with a (t0,t2) pytest-pair regression
   cache → full `derive_localization_findings` run asserts
   `mode == "sbfl_aggregate"`, `metadata["regression_reweighted"] is True`,
   boosted changed-file at rank 1.
2. **Targeted cross-suite** (localization + regression + orchestration
   consumers of the shared selector):
   ```bash
   env -u PYTHONPATH uv run pytest -q tests/unit/localization tests/integration/localization tests/unit/regression tests/unit/orchestration
   ```
   → all green (410+ passed at handoff time; counts grew with the sibling
   orchestration slice).
3. **Envelope stability spot-check**: any existing `novetest localization`
   flow on a single-engine store should be byte-identical to pre-merge
   behavior (single-engine selection pinned unchanged by
   `test_single_engine_store_prior_selection_unchanged`-style test; zero
   `.ambr` drift at the merged tip).

## Critical edge cases worth probing

- **Cross-engine-only priors** → probe returns `None` (no reweighting,
  no error) — the silent-degradation path must stay silent-and-correct.
- **Same-engine prior WITHOUT a regression cache** → `None` (the probe is
  cache-only; it must never trigger a derive).
- **Localization on a store whose newest run is non-pytest** while older
  pytest runs exist — head-run resolution
  (`resolve_latest_analyzable_run`) is deliberately engine-agnostic
  (single-run "which run to analyze", not pairing); confirm no surprise
  refusals appeared.

## Notes from merge

- WORKLOG conflict resolved incoming-on-top (localization 07-04 entry
  above coverage's 07-03 entry); no other files conflicted.
- Handoff's "1 failed" full-suite count was the chronic dotnet host-equip
  miss; it does NOT reproduce on the equipped merge host (0 failed).
