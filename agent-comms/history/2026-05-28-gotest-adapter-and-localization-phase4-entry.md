---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-05-28
slug: gotest-adapter-and-localization-phase4-entry
related:
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/decisions/2026-05-28-regression-outcome-envelope-shape.md
  - agent-comms/history/2026-05-28-phase3-regression-cli-and-freeze.md
  - design/implementation-plan/delivery-phasing.md
---

# History: parallel cycle close — `go test` adapter + Localization Phase 4 entry + Localization freeze (2026-05-28)

## What shipped this cycle

Single PM dispatch queued **two independent slices in parallel**; both
landed clean, both Manual-Test verdicts were `passed`, both findings
surfaced PM-decision-tier items the CEO triaged in one pass.

| Slice | Commit | What landed | Verdict |
|---|---|---|---|
| Run team — `go test` adapter (Phase 3 adapter #1) | `adf7bac` | 3rd native engine adapter (after pytest, jest) — `go-test` engine_name, `gotest_events_jsonl` artifact key, `GOTOOLCHAIN=local` pin, build-failure detection, engine-missing readiness | passed |
| Localization team — Phase 4 entry (SBFL per-test) | `bbb0356` | Localization engine surface: `derive_localization_findings`, `get_localization_findings`, `check_localization_availability`; 12-key `LocalizationFinding` persisted at `<store>/localization/findings/run_<id>/localization_findings.json`; 4 `LocalizationUnavailable` reason codes; Memory `has_localization_findings` availability flag wiring | passed |

Test gate observed by Manual Test on the merged tip: **588 passed + 3
skipped** (mypy clean, 69 source files). Localization slice contributed
+87 unit/integration tests; gotest slice contributed the adapter
suite tests folded into the same gate.

## Cycle close — freeze + reconcile

The CEO triage produced two `decisions/` outputs that this commit pair
closes the cycle around:

1. **Freeze: Localization Finding schema v1** (`46c9fec`,
   `decisions/2026-05-28-localization-finding-shape.md`). Pins 7
   schema items + cache-semantics + a §N "test code is NOT filtered"
   ruling + a §X open-refinement note for `REASON_MISSING_DERIVED_FACTS`
   split. Same ship → field-test → freeze cadence Coverage
   (`2026-05-16`) and Regression (`2026-05-28`) followed.
2. **Q3 reconcile: `engine_name` enum text** (this commit,
   `decisions/2026-05-28-regression-outcome-envelope-shape.md` lines
   49–50). The Regression envelope's `engine_name` enum was textually
   `"go"`; Manual Test's gotest verification confirmed the actual
   wire value is `"go-test"`. Text reconciled.

## DoD bullets

**No DoD bullets ticked this cycle.** This is deliberate:

- Phase 3 §3 bullets (lines 156–158 of `delivery-phasing.md`) were all
  closed in the prior cycle (`2026-05-28-phase3-regression-cli-and-freeze.md`).
  The `go test` adapter slice closes Phase 3's "Engine adapter
  coverage: all six landed by end of Phase 3" prose-level commitment
  by **one of three remaining** (cargo + JUnit + dotnet still open),
  but that prose has no individual DoD-bullet.
- Phase 4 §4 bullets (lines 186–189) all require the `novetest
  localization` CLI verb / `--formula` flag / NFR-LOC-002 perf
  measurement / multi-fixture mode validation. The Phase 4 entry slice
  ships only the engine surface — same engine-only discipline the
  Regression cycle followed at its Phase 3 entry.

The next Localization slice (CLI verb cycle) closes Phase 4 DoD
bullets #1, #2, and #4 in one sweep, mirroring the Regression CLI
cycle's pattern.

## §N field-tested decision — test code in localization output

This is the **load-bearing fact** future agents need to know.

CEO ruled 2026-05-28: Localization output may include test code lines
in the ranking, and this is intended behavior. NOT filtered, no
`is_test_code` discriminator, no path-prefix heuristic.

Rationale (pinned in §N of the freeze decision):
1. Test code itself can be the defect source; filtering hides the bug.
2. SBFL math (Ochiai) naturally degrades a failing-test's-own-body
   score as `1/√totalfail`. The "rank-1 tie between bug and test body"
   observed in the Phase-4-entry verification fixture is a
   single-failing-test (`totalfail = 1`) corner case, not a
   representative failure mode.

Concrete numbers from the analysis (verified during freeze drafting):

| totalfail | Failing test body's Ochiai | Production bug's Ochiai | rank-1 outcome |
|---|---|---|---|
| 1 | 1.000 | 1.000 | tied (current fixture) |
| 2 | 0.707 | ~1.000 | bug separates |
| 5 | 0.447 | ~1.000 | bug clearly above |
| 10 | 0.316 | ~1.000 | bug dominates |

Implication for future agents: do NOT propose a test-path filter
without re-opening this decision. The math handles the realistic case;
the fixture demonstrates the adversarial corner.

## Load-bearing learnings

### 1. Ship → field-test → freeze cadence is now 3-for-3

Three consecutive freeze decisions have used this pattern:
- Coverage outcome (`2026-05-16`) — wiring slice → Manual Test fielded
  → freeze.
- Regression outcome (`2026-05-28`) — Phase 3 CLI slice → Manual Test
  fielded → freeze with 2 bonus pin recommendations folded in.
- Localization finding (`2026-05-28`, this cycle) — Phase 4 entry
  slice → Manual Test fielded → freeze with `alternate_scores_available`
  list/bool correction + 4 reason codes verified + `LocalizationUnavailable.to_dict()`
  known gap surfaced.

Manual Test's "field-test the working draft for wire-format details"
discipline has caught at least one drift point in each of the three
cycles. The convention is durably load-bearing — not a one-off.

### 2. CEO product-challenge during freeze drafting is high-leverage

In two consecutive freeze cycles (Regression 2026-05-28; Localization
this cycle), the CEO pushed back on PM's initial wire-format proposal
with a product/math/architectural question that meaningfully reshaped
the decision:

- Regression cycle: CEO challenged independent-nullability of refs
  in the `unavailable` shape; PM verified and pinned correctly.
- Localization cycle: CEO challenged the proposed `is_test_code`
  filter with two product points (test code can be buggy; SBFL math
  degrades test-body rank with N). PM ran the math, confirmed CEO's
  intuition, and replaced the filter proposal with §N "intended
  behavior" documentation — a structurally better decision.

The lesson is general: when PM drafts a freeze with multiple plausible
options, the CEO's product instinct frequently improves the proposal
in a way the LGTM path would have lost. PM should explicitly invite
challenge on borderline schema items, not treat the recommendation as
load-bearing.

### 3. Parallel-slice dispatch worked clean — no Main Branch push omission

Two independent slices, two team worktrees, one verification batch
(both verifications in commit `cfef4c9`), one findings batch (both
findings in commit `8e013d0`), one Main Branch push (`8e013d0`). No
courier-push pattern this cycle. The Main Branch push-omission
escalation watch from `2026-05-27-phase3-regression-engine-complete.md`
§2 ("Diagnosis (provisional, not yet escalated to CEO)") is
**negative-confirmed for this cycle** — Main Branch pushed both
verifications and the merged tip at the natural close points.

Status of the escalation watch: open observations 2 (2026-05-26
+ 2026-05-27), recovery 1 (this cycle). Not a structural defect; no
charter edit needed. PM pre-flight step-0 continues to backstop.

## Deferred / queued for next cycle

| Item | Owner | Trigger |
|---|---|---|
| Q2 — split `run_not_analyzable` into `missing_derived_facts` (per §X of freeze) | Localization team | task brief next planning cycle; ships before next CLI verb dispatch |
| Q4 — `engine-engine-missing` error code polish | Run team | bundled with Phase 3 adapter completion (cargo + JUnit + dotnet) — likely a 1-line cleanup at that batch close |
| `go-test` row in supported-engine-matrix | PM | bundled with Phase 3 adapter completion — matrix gets all four new rows (`go-test`, `cargo-test`, `dotnet-test`, `junit`) in one update |
| Phase 3 adapter completion (cargo + JUnit + dotnet) | Run team | Phase 3 closeout cycle |
| `LocalizationUnavailable.to_dict()` addition | Localization team | bundled with Localization CLI verb cycle (it needs this for envelope projection anyway) |
| Phase 4 follow-up modes (`sbfl_aggregate`, `failure_proximity`) | Localization team | post Phase 4 CLI verb; reserved enum values already in freeze |

## Worktree / branch hygiene

Both team worktrees (`novetest-run-gotest`,
`novetest-localization-phase4-entry`) were already deleted by Main
Branch during the merge cycle (clean fast-forward into main on both,
no preservation needed — load-bearing work is on `main` per
`2026-05-25-duplicate-merge-cycle.md` §3 "no loss" framing).

## What the next cycle is

Three live candidates for the next PM dispatch (CEO planning call):

1. **Phase 3 adapter completion** — Run team ships cargo + JUnit +
   dotnet adapters. Closes "all six landed by end of Phase 3" prose
   commitment; bundles Q4 polish + matrix update.
2. **Localization CLI verb cycle** — Orchestration + Localization
   joint. Closes Phase 4 DoD bullets #1, #2, #4 in one sweep
   (mirroring Regression CLI cycle). Bundles Q2 split + adds
   `LocalizationUnavailable.to_dict()`.
3. **Memory `delete` CLI workflow polish** — Manual Test surfaced
   tombstone-CLI friction in the prior regression cycle; deferred
   from there. Smaller surface than either of the above.

PM should brief these three options to CEO at next session start (after
pre-flight step 0).
