---
from: novetest-regression-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-25
slug: activation
related:
  - agent-comms/tasks/regression-team-2026-05-25-activation.md
  - agent-comms/questions/regression-team-2026-05-25-charter-update.md
---

# Handoff: Regression team activation — charter-update proposal landed

## Worktree

- **Path:** `/home/yjshin/dev/novetest-regression-activation`
- **Branch:** `regression-activation`
- **Base commit:** `7015dec` (origin/main as of `git fetch` at session
  start; clean tree)

## Scope reminder

This is the activation cycle for the Regression team. Per
`tasks/regression-team-2026-05-25-activation.md`, no production code was
written; the deliverable is a `questions/` file proposing concrete
additions to the placeholder charter.

## Files written / modified

| Path | Type | Status |
|---|---|---|
| `agent-comms/questions/regression-team-2026-05-25-charter-update.md` | new | the deliverable |
| `agent-comms/INDEX.md` | regenerated | picks up the new question file |

**Files NOT touched** (explicitly per the task):

- `src/novetest/regression/**` — intentionally empty until the schema is
  frozen next cycle.
- `tests/**` — no code → no tests this slice.
- `.claude/agents/novetest-regression-team.md` — PM owns charter edits;
  this team proposes via the question file.
- `design/interace-contract/regression.md`,
  `design/workflows/regression.md` — binding contract; flagged C.4
  (return-tuple ordering) for PM clarification rather than editing.

## Verification

No automated verification — pure planning / reading / writing slice
(stated in the task's "Verification" section). The activation checklist
is satisfied:

- [x] All 8 documents in the task's pre-flight reading list were read in
      full:
  - [x] `design/interace-contract/regression.md`
  - [x] `design/workflows/regression.md`
  - [x] `design/interace-contract/coverage.md`
  - [x] `design/workflows/coverage.md`
  - [x] `design/interace-contract/memory.md`
  - [x] `design/workflows/memory.md`
  - [x] `src/novetest/models/coverage_fact_set.py`
  - [x] `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`
  - [x] `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`
  - [x] `agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md`
  - [x] `agent-comms/decisions/2026-05-25-supported-engine-matrix.md`
  - [x] `agent-comms/history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`
  - [x] `agent-comms/history/2026-05-21-phase2-complete-and-ci-batch.md`
  - [x] `agent-comms/tasks/memory-team-2026-05-25-find-runs-for-target.md`
  - [x] Companion: `requirements-specification/groups/regression.md`,
        `requirements-analysis/domain-model.md`,
        `src/novetest/coverage/{compare,results}.py`,
        `src/novetest/models/{memory_entry,run_record,test_result,run_reference}.py`.
- [x] The `charter-update` question file contains sections A
      (Conventions — 9 sub-items: directory layout, baseline-pair
      identity, dataclass tree, transition taxonomy, output-diff
      strategy, persistence write-time, unavailable outcome,
      schema-versioning, Memory availability wiring), B (Reporting —
      single-sentence addition, otherwise no divergence from the
      shared `agent-comms/README.md` handoff format), and C (7 open
      questions / risks: tombstoned baseline, envelope shapes, engine
      version drift, contract tuple ordering, MemoryEntry flag wiring,
      Coverage v2 coupling, Localization input shape).
- [x] Recommendations are concrete enough for PM to either lift A+B
      directly into the charter or route the schema sketch through a
      `decisions/2026-05-XX-regression-facts-json-layout.md` mirroring
      Coverage's facts-layout decision.
- [x] No source / test / contract files modified.

## Worklog entry text

**N/A.** Per the task: "No `WORKLOG.md` entry — this slice touches no
`src/` or `tests/`, so the hook does not fire. The handoff is the
record." The pre-tool-use commit hook
(`.claude/hooks/check-worklog-before-commit.sh`) only fires when
`src/`+`tests/` paths are staged; this slice stages only `agent-comms/`.

## DoD bullets believed closed

**None.** Stated explicitly in the task: "No `delivery-phasing.md` Phase
3 DoD bullet closes from team activation alone." The activation produces
the foundation PM will use to dispatch the first real implementation
slice (Phase 3 entry — likely `compare_runs` + facts persistence + the
companion Memory-side `has_regression_facts` probe per question C.5)
next cycle.

## Open items / surprises for the next team

1. **Contract-doc clarification needed (question C.4).** The
   `regression.md` interface contract phrases
   `resolve_latest_baseline`'s output as "Pair of Run References
   (current, previous)", but the workflow downstream
   (`compare_runs(rA, rB)`) is order-significant with `(baseline=older,
   target=newer)`. The natural read of the contract sentence inverts
   the direction. PM should either edit the sentence to read
   "(previous, current)" — i.e. `(baseline, target)` — or rename the
   tuple explicitly. Small PM-side fix; team did not edit
   unilaterally per the task's "Files NOT to touch".
2. **Question C.5 is the highest-priority follow-up for PM cycle
   planning.** When the first Regression implementation slice ships,
   `MemoryEntry.has_regression_facts` must flip in lockstep. Memory's
   `_availability_flags` probe needs a directory-scan addition (the
   run ID can be in either position of the `run_<A>__run_<B>` pair
   key). PM is the natural router — likely a parallel Memory-team task
   in the same cycle as Regression's first slice.
3. **No questions block the team from proceeding.** Section "Blocking"
   of the question file is `No`. If PM does not respond before the next
   cycle's dispatch, the team will treat the recommendations in
   section C as working assumptions.

## What happens next (per the task)

1. PM receives the `charter-update` question.
2. PM either edits `.claude/agents/novetest-regression-team.md`
   directly from sections A+B, or routes the schema sketch through a
   new `decisions/2026-05-XX-regression-facts-json-layout.md`.
3. PM may dispatch follow-up Memory-team task for the
   `has_regression_facts` probe (question C.5) at the same time as
   Regression's first implementation slice.
4. Next-cycle implementation slice (likely `compare_runs` + facts
   persistence) can then start from a frozen contract.

## Note for Main Branch

This worktree contains only `agent-comms/` changes — one new
`questions/` file and the regenerated `INDEX.md`. No source, no tests,
no design contracts touched. Standard merge into `main`; no integration
test gate needed (the comms-only commit pattern). No verification
request needed (no merged behavior to verify).
