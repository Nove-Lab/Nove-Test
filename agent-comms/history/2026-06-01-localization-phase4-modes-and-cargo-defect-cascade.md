---
from: novetest-pm-team
to: all
type: history
created: 2026-06-01
slug: localization-phase4-modes-and-cargo-defect-cascade
related:
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/localization-strategy.md
  - agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/history/2026-05-31-cargo-build-failure-heuristic-polish.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md
  - agent-comms/tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md
---

# History: 2026-06-01 cycle — **Phase 4 §4 #2 lands** + 3-defect cargo cascade

Combined cycle close for two interleaved cycle-attempts:
- **Run Defect 1 mini-cycle** (single-team): cargo-llvm-cov
  `--ignore-run-fail` swap. Verdict: passed (`5784507` findings).
- **Localization fallback-modes cycle** (4 attempts spanning 5/31 →
  6/1): originally parked at gate failure; landed via 3-commit
  bundle (`804690b` + `3ccfd72` + `05f86bc`) after a cascade of
  cargo-specific defects surfaced.

**Phase 4 §4 #2 DoD bullet** (Mode field populated correctly across
all three fixtures) **CLOSED**. Phase 4 progress: 2/4 → 3/4.

## Slices that landed

| Commit | Author | Subject |
|---|---|---|
| `18fc224` | Run team | fix(run): swap --no-fail-fast for --ignore-run-fail on cargo-llvm-cov path |
| `804690b` | Localization team | feat(localization): close Phase 4 §4 #2 — sbfl_aggregate + failure_proximity modes |
| `3ccfd72` | Localization team | fix(localization-fixture): co-locate failing test_divide with bug in arithmetic.rs |
| `05f86bc` | Localization team | fix(localization): Defect 3 — drop cargo catch-all regex + coverage-scope filter (CEO Option D) |

Plus Main Branch comms: `89c7a80` (Run verification + Defect 3
question), `4b25f14` (Loc verification + Defect 4 question),
`2747fba` (Defect 4 process correction). Manual Test findings:
`5784507` (Run Defect 1 — passed), `6aa26f6` (Loc combined —
passed).

## DoD bullets ticked in `delivery-phasing.md`

**Phase 4 §4 #2** — "Mode field populated correctly across all
three fixtures" — ✅ CLOSED.

Verification (Manual Test 2026-06-01 findings):
- `localization-branch` → `mode: "sbfl_per_test"`, `confidence:
  "high"`, top-1 `divide` Ochiai 1.0 (unchanged from prior cycle —
  regression-pinned)
- `localization-aggregate-only` → `mode: "sbfl_aggregate"`,
  `confidence: "medium"`, top-1 `src/arithmetic.rs` Ochiai 0.5,
  `entries` length 1 (stdlib paths correctly filtered)
- `localization-no-coverage` → `mode: "failure_proximity"`,
  `confidence: "low"`, top-1 `statistics.py`

Phase 4 status: 3/4 ticked (#1, #2, #4). Only #3 (perf NFR-LOC-002,
500 failed × 50k locations < 8s) remains.

## Cargo defect cascade — 3 defects surfaced + fixed across 4 cycle attempts

The Localization fallback-modes slice's `localization-aggregate-only`
fixture was the load-bearing E2E surface for `sbfl_aggregate` mode.
That fixture forces a failing test on cargo — a code path NO prior
cycle had exercised end-to-end on an equipped host. The cascade:

### Attempt 1 (5/31 night) — Defect 1: cargo-llvm-cov bails on failing tests

Gate fail symptom: `cargo llvm-cov did not write coverage.lcov`.
Root cause: `--no-fail-fast` on the cargo-llvm-cov argv tells cargo-
llvm-cov NOT to emit the LCOV report when inner nextest exits
non-zero. Mutually exclusive flag pair: `--ignore-run-fail` is the
cargo-llvm-cov form that internally implies `--no-fail-fast` AND
commits to emitting the report regardless.

Fix: 1-line argv swap in `cargo_adapter.py`'s coverage path
(non-coverage cargo-nextest argv stays `--no-fail-fast`). Run team
`18fc224`. Manual Test verdict `5784507`: passed.

### Attempt 2 (5/31 late night) — Defect 2: fixture panic site ≠ bug site

After Defect 1 fix on main, Loc team rebased + retried. Gate fail
symptom: aggregate-mode e2e ranks `src/lib.rs` top-1 instead of
`src/arithmetic.rs`. Root cause: cargo's panic trace (without
`RUST_BACKTRACE=1`) shows only the `assert_eq!` site, which lived
in `lib.rs::tests::test_divide`. The bug itself was in
`arithmetic.rs::divide`. The algorithm correctly extracted
`("src/lib.rs", 35)` from the panic line; `arithmetic.rs` got
`e_f = 0` and was filtered out.

Fix: **CEO Option A** — move `test_divide` INTO `arithmetic.rs`'s
own `#[cfg(test)] mod tests` block so the assert site IS the bug
site. Loc team `3ccfd72`. Fixture-only change; zero algorithm
modification.

### Attempt 3 (6/1 early morning) — Defect 3: parser catch-all + stdlib pollution

After Defect 2 fix on the rebased Loc branch + FF-merge into main,
gate fail symptom: aggregate-mode e2e ranks
`/rustc/<hash>/library/core/src/ops/function.rs` top-1, with
`src/arithmetic.rs` buried at rank #4 (4-way tie at `e_f = 1`;
lexicographic tie-break sorted `rustc/...` ahead of `src/...`).

Root cause TWO layers:
1. **Parser** (`failure_proximity.py`): `_CARGO_REGEXES` had a third
   "defensive catch-all" regex `\b<file>.rs:N:M` that slurped
   stdlib paths from cargo's default stack backtrace (which is
   emitted without needing `RUST_BACKTRACE=1`).
2. **Algorithm** (`derive.py:438`): `_derive_aggregate`'s candidate
   set was `covered_files | failing_trace_files` (union). Stdlib
   paths from the parser would land in this union even though
   they're never instrumented.

Fix: **CEO Option D** — both layers together:
- Drop the catch-all regex; only `panicked at` + `failed at`
  anchored patterns remain.
- Change `all_files = sorted(covered_files | failing_trace_files)`
  → `all_files = sorted(covered_files)`. Defense in depth.

Loc team `05f86bc`. Source-side change (deviates from Defect 2
brief's "fixture-only" constraint but inevitable given Defect 3's
nature). Main Branch FF-merge attempt 4: green at 759+5 on
equipped host.

### Attempt 4 (6/1) — Defect 1+2+3 all in place → ✅ landed

Manual Test 2026-06-01 findings verdict: **passed**. All 8
scenarios + 5 edges verified. The 4-attempt journey records 3
defects but the final landed state is clean.

## Defect 4 — orthogonal pre-existing bug, carry-forward

During Manual Test E2E, the verb `novetest localization latest`
returned `kind: "unavailable"`, `reason: "run_not_analyzable"`
against the same cargo aggregate run that `novetest localization
<run_id>` ranked correctly.

Root cause: `src/novetest/localization/retrieval.py:99` hardcodes
`return coverage.mapping_granularity == "per-test"`. Pre-this-cycle,
this constraint was correct because `_derive_aggregate` and
`_derive_failure_proximity` were `LocalizationUnavailable`-
returning placeholders. Now they produce real findings, but the
gate hasn't been relaxed.

**Not blocking this cycle's merge.** The explicit `<run_id>` path
works perfectly. The `latest` convenience verb is a separate
discoverability surface.

Queued as `tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md`
(~5-line fix + 1 integration test).

## Process correction — Defect 4 question doc was Main Branch overreach

Main Branch filed Defect 4 as a question doc with full source-line
root-cause analysis (`retrieval.py:99`) and a 5-line suggested fix.
**This was overreach** — Main Branch's charter scopes its
"after-merge" probing to envelope-path capture for verification doc
scenarios. Running `novetest localization latest` and investigating
the failure mode down to the source line is exploratory testing
territory, which belongs to Manual Test.

CEO directed a process correction (commit `2747fba`):
- Question doc retained for data value, but prepended with a
  prominent "Process correction" blockquote flagging the overreach
- Verification doc extended with Scenario 1b prompting Manual Test
  to independently reproduce + add their perspective
- Manual Test's findings (commit `6aa26f6`) ARE the canonical
  signal; the filed question is supplementary context

**Future cycles**: Main Branch and Manual Test boundaries are
binding. Main Branch may NOTICE surprising behavior post-merge
(envelope path mismatch, gate fail, etc.) but should ESCALATE to
PM via question rather than self-investigating source code. PM
routes to Manual Test for exploratory probing. The process
correction is now permanent record; future Main Branch sessions
should respect this boundary.

## Process learning — proactive fix-without-task-brief acceptable

Loc team implemented CEO's Option D for Defect 3 without a formal
PM task brief. Routing signal: the question doc's explicit Option D
recommendation + CEO's "확인하고 업무 진행" directive. Loc team
flagged this in their handoff Open Q #1 asking PM whether to
retroactively file a task brief.

PM disposition (this close): **retroactive task brief NOT filed**.
The proactive fix was correct per the routing signal; the gate
caught any defects (it did — gate green at 759+5); and per CEO's
"Process: charter 유지" posture confirmation, the equipped-host
gate is the mandatory safety net regardless of whether a task brief
was filed. The history entry above documents the routing chain for
audit.

**Future cycles**: a team picking up a fix path explicitly
recommended in a question doc that CEO has answered may implement
proactively. PM retroactively narrates in history rather than
filing post-hoc task briefs. Charter discipline preserved by the
gate.

## Process learning — equipped-host gate is now 3x production-validated

The 5/29 polyglot-host-parity decision's 3-trigger closure
machinery has now caught **3 distinct ship-blocker defects** that
unit + integration tests on Rust-less hosts missed:

| Date | Cycle | Defect | What the gate caught |
|---|---|---|---|
| 5/31 | cargo trigger-b | `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` missing | every cargo run on equipped host exited 4 |
| 5/31 night | Loc 1A original | `--no-fail-fast` blocks LCOV on failing runs (Defect 1) | aggregate e2e couldn't produce CoverageFactSet |
| 6/1 | Loc 1A retry #2 | Parser catch-all + stdlib pollution (Defect 3) | arithmetic.rs ranked #4 instead of #1 |

**Pattern**: every cargo-specific equipped-host defect this past
week has been **invisible to all pre-merge layers** (unit tests
stub `run_subprocess`; integration tests skip-guard on toolchain
absence; team development happens on Rust-less hosts). The
equipped-host gate is the ONLY safety net that fires on these.

**Implications for future adapters (JUnit, dotnet)**:
- The same cascade pattern is likely. JUnit's `Launcher.execute()`
  behavior with assert-vs-bug-site, dotnet's Coverlet `PerTestCoverage`
  config nuances, etc., will only manifest on equipped hosts.
- The equipped-host gate is **NOT a nice-to-have** — it's the
  spine of polyglot host parity. Charter discipline is binding.
- PM should include "equipped-host pre-flight evidence" as a
  mandatory section in every adapter task brief at handoff time
  (already mandated since 5/31 hotfix cycle; reinforced here).

## Process learning — verification-doc nit pattern broken

The recurring "predicted-output typos in Main Branch's verification
doc" pattern from prior 3 cycles (Obs 1+2 in cargo-LCOV cycle,
Obs 1+2+3 in cargo-build-failure-polish cycle) did **NOT** recur
this cycle. Manual Test's findings: "verification doc was
byte-accurate" — particularly noting the Ochiai score arithmetic
(`1/√((1+0)·(1+3)) = 0.5`) matched verbatim along with all 3
alternate scores.

Suggested cause: the prior cycle's history entry's recommendation
("Main Branch should dry-run the verification doc's exact command
snippets against the freshly-merged tip before filing") may have
informally taken hold even without a formal template update.
**Pattern carried forward as informal best practice**.

## Envelope freeze v1 — failure_proximity deviation narrated, not formally amended

The 2026-05-30 `localization-outcome-envelope-shape` freeze pinned
the 12/9/6/3-key shape for the `localization_outcome.kind:
"fact-set"` block. The new `failure_proximity` mode introduces
**legitimate mode-specific exceptions**:
- `finding.alternate_scores_available: []` (empty list — not the
  pinned 3-element list, because failure_proximity is not SBFL
  and doesn't compute per-formula scores)
- `entries[*].alternate_scores: {}` (empty dict — same reason)
- `formula: "ochiai"` field is a placeholder so the closed-enum
  `__post_init__` validator passes; consumers gate on `mode` not
  `formula`

PM disposition: **narrate in history (this entry); do NOT formally
amend the 2026-05-30 freeze decision**. Rationale:
- The deviation is mode-specific and INTENTIONAL (per the slice's
  algorithm). Not a violation of the original spec; an extension
  the original spec didn't enumerate.
- The original freeze pinned shapes for `sbfl_per_test` mode (the
  only mode implemented at freeze time). `failure_proximity`'s
  emptier shapes are the appropriate spec for a non-SBFL mode.
- Formal v2 amendment can come later if/when an external consumer
  needs the spec pinned more explicitly. Until then, history +
  source comments are sufficient documentation.
- Manual Test verified the deviation works correctly in production
  (Scenario 4 of their findings).

**Carry-forward**: if a future Localization slice touches envelope
shape OR if an external AI agent consumer encounters the deviation
unexpectedly, PM revisits with a formal v2 amendment decision doc.

## What the next cycle is

**Defect 4 fix-up** queued as
`tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md`.
Single-team, ~5-line source change + 1 integration test, single-day
slice. Brief inlines the empirical reproduction + root cause from
Manual Test findings + the question doc.

After Defect 4 lands, candidates for the next cycles (CEO picks):
- **Phase 4 §4 #3** (perf NFR-LOC-002 — eventually MVP exit criterion)
- **Phase 3 JUnit** (gated on Open Q #5 — launcher: vendor vs download)
- **Phase 3 dotnet** (gated on Open Q #4 — Coverlet PerTestCoverage key)
- **Memory `delete` polish** (long-standing carry-forward)
- **Envelope freeze v2 amendment** for failure_proximity deviation
  (low priority; do it when next touching Localization envelope)

## Other deferred items (visible to future PM)

1. **Defect 4** (Loc `latest` rejects aggregate runs) — queued as
   task brief; ~5-line fix + 1 integration test.
2. **Phase 4 §4 #3** (perf NFR-LOC-002) — only remaining Phase 4
   bullet; MVP-gate eventually.
3. **Open Q #4 (.NET) + Q #5 (JUnit)** — both still gating Phase 3
   5/6 and 6/6.
4. **Memory `delete` polish** — carry-forward from 2026-05-27.
5. **Envelope freeze v2 amendment** for failure_proximity — low
   priority informal.
6. **Verification-doc self-test pattern** — informal best practice
   for Main Branch, no formal template change.
