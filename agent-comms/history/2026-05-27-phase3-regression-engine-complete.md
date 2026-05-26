---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-05-27
slug: phase3-regression-engine-complete
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/history/2026-05-26-phase3-entry.md
  - agent-comms/history/2026-05-26-phase3-regression-engine-and-memory-probe.md
  - design/interace-contract/regression.md
  - design/implementation-plan/delivery-phasing.md
---

# History: Phase 3 Regression engine surface complete (cycle close 2026-05-27)

## What shipped this cycle

Single-team slice (Regression team) added the three remaining
baseline-resolution / availability helpers on top of the foundational
comparison surface shipped 2026-05-26:

- `resolve_latest_baseline(store, target_expression) -> tuple[RunReference, RunReference] | RegressionUnavailable`
- `derive_latest_regression(store) -> RegressionFactSet | RegressionUnavailable`
- `check_regression_availability(store, run_reference) -> bool`

2 src modules edited (no new src files), 17 new unit + 2 new integration
tests, pytest **442 passed + 3 skipped** (was 423+3 pre-slice), mypy
clean. Commit `b32084d`; verification `342bc9d` (`status: record-only`,
Manual Test waived — no CLI surface to probe yet). No DoD bullets ticked
— engine-only completion.

## Milestone — `design/interace-contract/regression.md` engine surface 100% covered

This is the load-bearing fact future agents need to know.

All 7 rows of the Internal interface table in
`design/interace-contract/regression.md` are now implemented:

| Row | Function | Shipped in |
|---|---|---|
| 3 | `compare_runs` | `9c79792` (2026-05-26) |
| 4 | `resolve_latest_baseline` | `b32084d` (this cycle) |
| 5 | `derive_latest_regression` | `b32084d` (this cycle) |
| 6 | `get_regression_facts` | `9c79792` |
| 7 | `check_regression_availability` | `b32084d` (this cycle) |

Plus the two External rows (`novetest regression compare`, `novetest
regression latest`) which are CLI projections — out of scope for the
engine and the explicit territory of the upcoming Orchestration cycle.

**Implication for future work:** no further regression engine surface
is needed. The Orchestration CLI cycle is pure projection — it consumes
these entry points and emits envelope shapes (`regression_outcome` /
`regression_delta`, which PM freezes via `decisions/` after Manual Test
fields them — same ship→field-test→freeze cadence Coverage followed in
Phase 2). Localization Phase 4 will consume the engine surface directly
too; no new regression entry points are required there either.

## Load-bearing learnings

### 1. `status: record-only` verification is a stable convention now

Second successful application after the precedent set in cycle
`2026-05-26-phase3-regression-engine-and-memory-probe.md`. The pattern
is now codified: an engine-surface slice that ships **no CLI /
orchestration / envelope changes** waives Manual Test via Main Branch's
`status: record-only` verification — explicitly stating "no Manual Test
action requested" with the rationale. Manual Test re-engages on the next
slice that adds a user-facing surface.

Test surface coverage that justifies the waiver: 17 new unit + 2 new
integration tests, all exercising real Project Store seams (no Memory
mocks). The contract is verified end-to-end through the existing test
discipline — no exploratory probe adds signal.

Charter / decision codification is **not** needed yet; the convention is
stable enough that the next agent picking up Main Branch can pattern-match
on the two prior verification docs and apply the same `record-only`
discipline. If it appears a third time it might be worth a formal
`decisions/` entry; for now, the pair of history docs (this one +
`2026-05-26-phase3-regression-engine-and-memory-probe.md`) is sufficient
precedent.

### 2. Main Branch push omission — 2 cycles consecutive (escalation signal)

In both this cycle and the previous (`2026-05-26-phase3-regression-engine-and-memory-probe.md`),
Main Branch team committed the merge + verification locally but did NOT
push. Both times, PM's pre-flight step-0 (`git fetch && git status` —
codified after the 2026-05-25 duplicate-merge incident) caught the
omission immediately and PM pushed as courier.

**Diagnosis (provisional, not yet escalated to CEO):** Main Branch's
charter likely treats "merge complete" as the terminal step; push is
implicit. The terminal step needs to be **"merge + push to origin"**,
not just merge.

**Action deferred:** If it happens a 3rd time, raise as a `questions/`
to CEO for explicit charter edit (`.claude/agents/novetest-main-branch-team.md`)
or a `GOTCHAS.md` entry. Two data points are pattern-suggestive but not
yet a structural defect; charter edits should be load-bearing. PM-direct
courier push handles each instance cleanly in the meantime — fast-forward,
no PM-authored content involved, criteria for PM-direct reconcile met.

### 3. PM pre-flight step-0 keeps earning its keep

The `git fetch && git status` rule (codified `2ecdb75`, after the
2026-05-25 duplicate-merge) has now caught:
- The 2026-05-25 incident itself (12-commit-stale local main).
- The 2026-05-26 Main Branch push omission (cycle close caught at
  pre-flight when planning the next cycle).
- This cycle's Main Branch push omission (caught at handoff inspection
  — the verification was in local main but not yet in origin).

Three high-leverage saves with a near-zero-cost rule. Worth keeping
prominent in the PM charter; do not relax even if it feels routine.

## Pytest baseline drift — curiosity worth flagging

The Regression team's handoff observed: pre-slice pytest baseline on
`main` (`0b55baf`) was **423+3**, but the task brief PM wrote quoted
**415+3** from `7e5b7a5`. Between those two commits, only `0b55baf`
exists, and it's a **comms-only** commit (PM-authored task file +
INDEX regen — no `src/` or `tests/` changes). The 8-test delta should
not exist.

Three plausible explanations, none verified:
1. PM mis-quoted the 415 baseline in the task brief (most likely —
   415 may have been the count at an even-older commit `7015dec` or
   similar, and PM grabbed it without re-running pytest).
2. Worktree pytest-cache divergence — `uv run pytest` may incidentally
   reflect a slightly different collection set under a fresh worktree
   vs. a long-lived checkout. Unlikely given identical lockfile state.
3. The team mis-quoted the 423 baseline. Possible but `b32084d`'s
   author explicitly distinguishes "the task brief quoted 415" from
   "the actual pre-slice baseline on `main` is 423", implying they
   ran the check.

**Disposition:** not blocking; +19 delta + final 442 are independently
verifiable and matched between handoff and verification. PM should
adopt the discipline of running `uv run pytest -q tests/unit
tests/integration` once on the actual base commit when writing the
next task brief, and quote that count directly — eliminates the
ambiguity at the source.

## Worktree / branch hygiene

`novetest-regression-baseline-resolution` worktree + branch deleted
during this cleanup (clean fast-forward into main, no preservation
needed — load-bearing work is on `main` per `2026-05-25-duplicate-merge-cycle.md`
§3's "no loss" framing).

## What the next cycle is

The follow-up CLI cycle (Orchestration team): ship `novetest regression
compare <run_id1> <run_id2>` + `novetest regression latest` + `novetest
compare` orchestration verb + `inspect` Regression section wiring.
Closes Phase 3 DoD bullets `[156]`, `[157]`, `[158]` in `delivery-phasing.md`
in a single sweep. Manual Test re-engages; PM freezes `regression_outcome`
+ `regression_delta` envelope shapes via `decisions/` AFTER Manual Test
fields them (decision §C.2, same cadence Coverage followed in Phase 2).
