---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-26
slug: phase3-entry
related:
  - questions/regression-team-2026-05-25-charter-update.md
  - decisions/2026-05-25-supported-engine-matrix.md
---

# History: Phase 3 entry — Memory prereq + Regression team activation

Two parallel slices opened Phase 3 (Regression Comparison). Memory
shipped the `find_runs_for_target` primitive Regression's baseline
resolution depends on; Regression team woke from a 5-month dormancy
and submitted a comprehensive charter-update proposal. Both merged
cleanly. No DoD bullets closed (intentional — Phase 3 closure is
sequenced across the next ~4 cycles, this slice is entry infrastructure).

## Cycle summary

| Slice | Commit | Outcome |
|---|---|---|
| Memory: `find_runs_for_target(store, target_expression, *, include_tombstoned=False)` | `4964e3a` | passed — Phase 3 prereq |
| Regression: team activation + charter-update question | `d9b3032` | passed — comprehensive proposal across A1-A9 + B + C1-C7 |

Both verifications written as `status: record-only` by Main Branch —
no Manual Test action requested.

## What closed

- **Phase 3 prerequisite**: Memory now exposes
  `find_runs_for_target` per `design/workflows/regression.md`'s
  binding contract. PM-pinned signature shipped verbatim:
  `MemoryEntry`-typed return, newest-first ordering, tombstone-exclude
  default. 8 unit tests covering the task's pinned test plan.
- **Regression team activation**: 5-month dormancy ended. Team
  delivered a 24KB charter-update question covering 9 convention
  proposals (regression_facts.json schema, baseline-pair identity,
  outcome transition taxonomy, native-output diff strategy, lazy
  persistence, unavailable outcome, schema versioning, Memory
  availability flag wiring) + reporting conventions + 7 open
  questions PM must resolve before first code slice. The question is
  the input PM uses to draft the next cycle's
  `decisions/regression-facts-json-layout.md` (mirroring Coverage's
  precedent).

No `delivery-phasing.md` DoD bullets fire from this slice; Phase 3
opens at 0/3.

## Load-bearing learnings

### 1. `status: record-only` — a useful new verification convention

Main Branch coined a verification status they hadn't used before:
`status: record-only`. Both this cycle's slices got `record-only`
verifications because:

- `find_runs_for_target` is a pure internal Python API — no CLI
  surface, no envelope change, fully covered by unit tests; nothing
  for Manual Test to exercise end-to-end.
- Regression activation is pure comms — zero source, zero tests,
  zero contract docs; no merged behavior to verify.

PM endorses this as a permanent convention. Saves a Manual Test
round-trip on slices that produce no user-facing surface change.
Two rules of thumb (going forward):

- Pure internal API change with full unit-test coverage and no
  envelope impact → `record-only`.
- Pure comms/docs change → `record-only`.
- Any change to a CLI verb, envelope shape, exit code, or user-visible
  behavior → standard verification with action requested.

If a future slice straddles the line, default to standard verification
(belt-and-suspenders). The `record-only` document still goes in
`verifications/` so the merge has an audit trail.

### 2. PM pre-flight step 0 caught Main Branch's push omission

Yesterday's charter edit (`git fetch && git status` as mandatory step 0)
fired in its first real session — Main Branch finished merging both
worktrees and writing both verifications, but did NOT push. PM's
pre-flight immediately detected "ahead by 3 commits" and surfaced
the omission before any cycle-cleanup operation could compound the
drift. PM pushed (PM-direct reconcile principle: fast-forward,
no source edits, courier-only).

This is exactly the failure mode the new step 0 was designed to
prevent. **Continue enforcing pre-flight step 0 ruthlessly.**

### 3. Greenfield-phase entry pacing — "wake up, propose, freeze, then code"

Phase 3 is greenfield: empty `src/novetest/regression/` until this
cycle. The entry pattern that worked:

1. PM dispatches an **activation task** that explicitly forbids code
   (`Files NOT to touch: src/novetest/regression/**`). Deliverable is
   a `questions/` file proposing conventions.
2. In parallel, PM dispatches the **upstream prerequisite** slice
   (Memory `find_runs_for_target`).
3. Next cycle: PM consumes the activation question, writes
   `decisions/regression-facts-json-layout.md` to freeze the schema,
   then dispatches the first real implementation slice.

This sequencing prevents the "team writes code against an unfrozen
schema, then we discover the schema is wrong" failure mode. Coverage
team's Phase 2 entry followed the same shape (decision-first, code-
after) and it worked. Use this for Phase 4 (Localization) and Phase 5
(Replay) entries.

### 4. PM-direct reconcile principle held up under second use

Yesterday introduced "PM may execute reconcile directly when (a)
fast-forward, (b) no source/test/workflow edits, (c) PM's own commits
are comms-only." This cycle's tail (push + worktree teardown +
history + transient cleanup) was a textbook fit:

- Pushing Main Branch's commits is courier work, not editing → OK
- Worktree/branch teardown is git plumbing → OK
- PM's cycle-cleanup commit touches only `agent-comms/**` → OK

Second instance survives the rule. Not yet enough for rule-of-three
promotion to PM charter, but the principle's mental model is sound.

## Pending — next cycle's input

The unique transient file kept (not deleted in this cleanup):

- **`questions/regression-team-2026-05-25-charter-update.md`** —
  Regression team's 24KB proposal. PM's next cycle action: read in
  full, draft `decisions/2026-05-XX-regression-facts-json-layout.md`,
  resolve open questions C.1 through C.7 with CEO. Then dispatch
  Regression's first real implementation slice (`compare_runs`).

Open questions in the charter-update needing PM/CEO decisions:

- **C.1**: Tombstoned-run-as-baseline (fail-soft vs fail-hard?)
- **C.2**: Envelope shapes for `regression compare` / `regression latest` / `inspect` Regression section
- **C.3**: Engine-version drift across compared runs (refuse, warn, ignore?)
- **C.4**: `resolve_latest_baseline` return-tuple ordering ambiguity (contract gap they spotted)
- **C.5**: `MemoryEntry.has_regression_facts` flip-time wiring
- **C.6**: Coverage schema evolution coupling
- **C.7**: Localization (Phase 4) input shape — preview now or defer?

Plus C.4 is technically a contract-doc gap: Regression team flagged
it but did not edit `design/interace-contract/regression.md`
unilaterally. PM resolution either edits the contract doc or pins
the answer in the new `decisions/` file.

## Process notes

- Both teams executed their tasks verbatim against the PM-pinned
  specs. Zero deviation, zero surprise.
- Worktree teardown was uncontroversial this time (vs yesterday's
  archival debate): both branches' work is fully on `main`, so
  "necessary work is reachable on the production branch" is
  trivially satisfied. No archive tags, no dormant refs.
- Cycle duration: ~30 min wall clock from CEO dispatch to cleanup.
  Greenfield-phase-entry slices are inherently faster than feature
  slices.
