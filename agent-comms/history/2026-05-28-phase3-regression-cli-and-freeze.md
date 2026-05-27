---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-05-28
slug: phase3-regression-cli-and-freeze
related:
  - agent-comms/decisions/2026-05-28-regression-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/history/2026-05-27-phase3-regression-engine-complete.md
  - design/interace-contract/orchestration.md
  - design/implementation-plan/delivery-phasing.md
---

# History: Phase 3 Regression CLI surface + envelope freeze (cycle close 2026-05-28)

## What shipped this cycle

Single-team slice (Orchestration team) projected the now-100%-complete
Regression engine surface onto the CLI envelope. Pure projection — zero
engine / Memory / contract work.

Three new verbs + one new `inspect` section:

- `novetest regression compare <baseline> <target>` — wraps `compare_runs`.
- `novetest regression latest` — wraps `derive_latest_regression`.
- `novetest compare <baseline> <target>` — composed envelope with both
  `regression_outcome` AND `coverage_delta` under `data`. Distinct from
  `regression compare` (regression-only).
- `inspect <run_id>` — gains `data.regression_outcome` block;
  `data.sub_reports.regression` flips `"available"` ↔ `"unavailable"`
  based on the discriminated `kind`. Composed at the orchestration layer
  via `_resolve_inspect_regression` (baselines against the IMMEDIATE
  prior live run, NOT the global latest pair).

2 src files edited (no new src files), 5 new test files + 2 modified,
pytest **471 passed + 3 skipped** (was 442+3 pre-slice — +29 net), mypy
clean. Commits `c074226` (src) → `defc7a2` (handoff) → `6d24976`
(verification) → `7a86f44` (findings) → `884c310` (envelope freeze).
Manual Test verdict: **passed**, zero envelope divergences, zero bugs.

## Milestone — Phase 3 DoD bullets [156] [157] [158] all closed in one sweep

This is the load-bearing accomplishment for future agents to know.

| DoD bullet | What it requires | Closed by |
|---|---|---|
| `[156]` | `regression latest` resolves latest pair + returns Regression Facts | `c074226` |
| `[157]` | `compare` returns composed Regression + Coverage delta | `c074226` |
| `[158]` | `inspect` populates Regression section using resolved baseline | `c074226` |

**Phase 3 CLI surface complete.** What's left in Phase 3:
- Engine-adapter completion: Cargo + JUnit + dotnet adapters (Run team
  territory — `delivery-phasing.md` line 150 "all six landed by end of
  Phase 3").
- Schema-additions DoD bullet (`delivery-phasing.md` line 152
  "Regression Fact tables; `regression_facts.json` per run pair") —
  already de-facto satisfied by `decisions/2026-05-26-regression-facts-json-layout.md`
  + the persisted `regression_facts.json`. PM may consider ticking
  this implicitly OR adding a final "schema additions complete"
  marker bullet — TBD next cycle.

## Envelope-shape freeze

`decisions/2026-05-28-regression-outcome-envelope-shape.md` pins the v1
wire shape, anchored on `RegressionFactSet.to_dict()` and
`RegressionUnavailable` as source-of-truth.

Four constraints AI consumers will pattern-match on:

1. **Discriminator `kind`** (`"fact-set"` | `"unavailable"`) — branch
   first.
2. **Independently nullable `*_run_reference` blocks on unavailable** —
   richer than Coverage's single-ref pattern; consumers can tell WHICH
   side failed.
3. **Top-level `schema_version` stripped on wire**; inner blocks
   (`*_run_reference`, `test_transitions[*]`, embedded `coverage_change`)
   retain theirs. Same precedent as `coverage_outcome` / `coverage_delta`.
4. **`detail` template conventions** — tombstone uses literal
   `"baseline"`/`"target"`/`"both"`; engine-mismatch and target-mismatch
   use a `"baseline X='a' != target X='b'"` template;
   `no-comparable-baseline` distinguishes empty store
   (`detail == "no-runs"`) from single-run-on-target
   (`detail == <target_expression>`).

The §4 template conventions were **discovered by Manual Test in the
wild**, not promised by the handoff or verification doc. Pinned now so
AI consumers can rely on them.

## Load-bearing learnings

### 1. Ship → field-test → freeze cadence works for Regression (3-cycle confirmation)

Decision `2026-05-26-regression-facts-json-layout.md` §C.2 codified the
cadence: ship the working draft, Manual Test fields it, PM freezes via
`decisions/`. Three cycles in a row pinned shape stability (engine →
baseline resolution → CLI), Manual Test exercised all 10 documented
scenarios + 5 edge cases on the third, and the freeze decision landed
with zero shape changes from the handoff's working draft.

The cadence is now battle-tested for both Coverage (Phase 2) and
Regression (Phase 3). Localization (Phase 4) and Replay (Phase 5) should
follow the same pattern: ship CLI working-draft → Manual Test fields →
PM `decisions/` freeze. Codifying this in the team charters is not
necessary yet; the precedent across two engines is strong enough.

### 2. Main Branch push omission pattern BROKE this cycle (escalation cancelled)

The prior history entry flagged 2 consecutive Main Branch push omissions
(2026-05-26 + 2026-05-27) and warned that a 3rd recurrence would
escalate to CEO for a charter edit. **It did not recur.** This cycle,
Main Branch pushed the merge + verification + findings commits cleanly
to origin. PM's pre-flight step-0 (`git fetch && git status`) confirmed
local = origin at session start.

**Disposition:** escalation cancelled. Two consecutive omissions
suggest either (a) the prior pattern was incidental (unlucky pair, not
systemic) or (b) the team self-corrected after seeing the prior cycle's
PM-direct courier push. Either way the corrective signal arrived
without charter intervention. Future PM should keep pre-flight step-0
prominent (it's the safety net), but no GOTCHAS or charter edit needed.

### 3. Manual Test's "freeze pin" recommendations are high-leverage

Manual Test recommended freezing 2 extras the verification doc did NOT
promise:
- Tombstone `detail` literal (`"baseline"`/`"target"`/`"both"`).
- Mismatch `detail` templates (`"baseline X='a' != target X='b'"`).

Both were behaviorally stable in the merged code and follow predictable
conventions — exactly the kind of micro-behavior an AI consumer relies
on but rarely gets pinned. PM should treat this as a permanent reviewer
duty: **at freeze time, ask Manual Test "what consistent behaviors did
you observe that the spec didn't promise?"** Those are the highest-ROI
additions to a freeze decision.

### 4. Manual Test workflow friction — Memory tombstone CLI is needed (deferred)

Manual Test had to exercise decision §C.1 (tombstone-after-cache
override) via a direct Python call to `delete_run_evidence` — no CLI
surface exists yet. **Not blocking** for this cycle, but it's a
workflow gap. Queueing for Memory team consideration after the Phase 3
adapter-completion work. See `delivery-phasing.md` Phase 5 backlog or
a Phase 3 closeout task to be drafted next cycle.

## Worktree / branch hygiene

Orchestration team's worktree (`/home/yjshin/dev/novetest-regression-cli`)
and branch (`worktree-regression-cli`) — handoff didn't explicitly
report deletion; PM should check at next session start and clean up if
present. Standard merge → push → worktree delete pattern.

## What the next cycle is

Three candidates for the CEO to choose among:

1. **Run team — adapter completion**: Cargo + JUnit + dotnet adapters
   to close Phase 3's engine-adapter DoD (`delivery-phasing.md` line
   150). Largest scope; could be split across multiple slices.
2. **Memory team — `novetest memory delete <run_id>` CLI verb**: closes
   the Manual Test workflow gap (Edge §C.1 tombstone path); also a
   natural prerequisite for future cleanup workflows. Smaller scope.
3. **Phase 4 entry prep — Localization team activation**: Phase 3 CLI
   surface is shippable; activating Localization in parallel would
   front-load Phase 4 risk while Run team finishes adapters. Per
   `.claude/agents/novetest-localization-team.md` "Activates at
   Phase 4 entry" — CEO judgment call on parallel-vs-sequential.

PM recommends raising as a planning question to CEO at next session
start rather than auto-selecting. Phase 3 closeout vs. Phase 4 entry
is a CEO-strategic call.
