---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: record-only
created: 2026-05-26
slug: regression-activation
related:
  - handoffs/regression-team-2026-05-25-activation.md
  - tasks/regression-team-2026-05-25-activation.md
  - questions/regression-team-2026-05-25-charter-update.md
---

# Verification record: Regression team activation (comms-only slice)

## Merged commit

`d9b3032 comms(regression): activation handoff — charter-update question`

Source handoff:
[`handoffs/regression-team-2026-05-25-activation.md`](../handoffs/regression-team-2026-05-25-activation.md).

## Why this is a record doc (no Manual Test action requested)

This slice is **pure comms — zero source, zero tests, zero contract
docs touched.** The handoff itself states: "Standard merge into `main`;
no integration test gate needed (the comms-only commit pattern). No
verification request needed (no merged behavior to verify)."

Files modified by the merged commit:

```
agent-comms/INDEX.md                                          | 3 +-
agent-comms/handoffs/regression-team-2026-05-25-activation.md | 148 +
agent-comms/questions/regression-team-2026-05-25-charter-update.md | 531 +
```

No CLI surface, no behavior change, no envelope shift. Nothing to
exercise.

## Sanity gate (still re-run per charter)

The charter mandates re-running the gate after every merge, even
comms-only ones. Confirmed green on `main` @ `d9b3032`:

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit tests/integration` | **345 passed, 3 skipped** (unchanged from the immediately-prior Memory merge — comms-only slice cannot move test counts). |
| `uv run mypy` | **clean** (52 source files, `--strict`; unchanged — no source touched). |

## Conflict resolution

None. The Regression worktree was rebased onto `4964e3a` (post-Memory)
before fast-forward; `git rebase main` succeeded with no conflicts.
The only file overlap risk was `agent-comms/INDEX.md`, but Memory's
merge did not touch INDEX, so the rebase was a clean replay.

After both merges I re-ran `tools/regen_comms_index.py` to pick up
Memory's handoff (which Regression's own INDEX regen had missed because
it was generated from a base that did not yet include Memory's
handoff). That regen is staged with these verification files.

## What's actually in the slice

The deliverable is the **charter-update question file**
(`questions/regression-team-2026-05-25-charter-update.md`, 531 lines).
Sections:

- **A.** 9 convention proposals for the placeholder Regression charter
  (directory layout, baseline-pair identity, dataclass tree, transition
  taxonomy, output-diff strategy, persistence write-time, unavailable
  outcome, schema-versioning, Memory availability wiring).
- **B.** A single-sentence Reporting addition (handoff must flag
  contract changes for `decisions/` follow-up).
- **C.** 7 open questions / risks for PM (tombstoned baseline,
  envelope shapes, engine version drift, contract tuple-ordering
  ambiguity, `MemoryEntry.has_regression_facts` wiring, Coverage v2
  coupling, Localization input shape).

Routing it to PM is PM's call (this team does not write decisions or
edit charters).

## Highlights worth surfacing to PM (already flagged in handoff §"Open items")

1. **C.4 contract clarification.** `regression.md` interface contract
   describes `resolve_latest_baseline` output as "Pair of Run References
   (current, previous)", but the downstream workflow
   `compare_runs(rA, rB)` expects `(baseline=older, target=newer)`.
   Natural read of the contract inverts that direction. PM-side edit.
2. **C.5 Memory availability flag wiring.** When the first real
   Regression implementation slice ships, `MemoryEntry.has_regression_facts`
   must flip in lockstep. Memory's `_availability_flags` probe will
   need a directory-scan addition (the run ID can be in either
   position of the `run_<A>__run_<B>` pair key). Suggests a parallel
   Memory follow-up task when Regression's first slice is dispatched.

## DoD bullets believed closed

None. The handoff is explicit: "No `delivery-phasing.md` Phase 3 DoD
bullet closes from team activation alone." The activation produces the
foundation PM will use to dispatch the first real Regression
implementation slice next cycle.
