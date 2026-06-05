---
from: novetest-pm-team
to: all
type: history
created: 2026-06-05
slug: cargo-cli-orchestration-defect-and-second-equip-exercise-validation
status: archived
related:
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md
  - design/implementation-plan/engine-adapters.md
---

# Cargo CLI orchestration defect — closure + second equip-and-exercise validation (2026-06-04 surfaced → 2026-06-05 closed)

## TL;DR

The defect Manual Test surfaced on 2026-06-04 during the polyglot
host-equipping pass — `novetest run .` against the canonical Rust
fixture returning `adapter-unparseable-output` — closed in **one short
cycle, no hotfixes**. Run team's slice on `176e593` lands:

- **Fix A** (P1 — adapter-local directory-type carve-out)
- **Fix B** (P2 — no-tests-match heuristic separating filter mismatch
  from compile failure)
- **2 new CLI smokes** (Process — dot case + bare control)

| Cycle | Commits | Manual Test verdict | What broke |
|---|---|---|---|
| Single (2026-06-04 brief → 2026-06-05 close) | `176e593` + `93068c5` | **passed** | All 3 defects closed; native_exit_code 4 → 100 flip is the smoking-gun signal |

This is the **second adapter cycle** where the
`equip-and-exercise §2.5` binding heuristic (added in JUnit hotfix-3,
2026-06-04) gated the originating team's pre-handoff exercise on the
equipped host. As in the JUnit hotfix-3 → re-pass cycle, all three
gate layers (Run team's pre-handoff, Main Branch's pre-merge, Manual
Test's re-pass) agreed: zero defects leaked.

## Load-bearing lessons (the parts future agents must internalize)

### 1. Native exit code as smoking-gun forensics

Pre-fix: cargo-nextest exited **4** (no tests matched filter — wrong
but plausible). Post-fix: cargo-nextest exits **100** (one test failed
by design, the canonical fixture's `test_subtract_intentionally_fails`).

This isn't redundant signal — it's the objective evidence that Fix A
redirected the filter-DSL append away from `.` at the **argv
construction layer**, rather than papering over the symptom at
parse-time or status-derivation downstream. Pattern future cycles
should reuse: **when a fix involves "stop sending the wrong argv to
the native tool", verify by checking the native tool's exit code
shifted to the correct semantic class.** Memory engine surfaces
`metadata.native_exit_code` per
`decisions/2026-05-30-native-result-metadata-slot.md` precisely so
adapter cycles have this forensic surface.

Pin: Manual Test verification §"Critical edge cases worth probing"
item 1; finding §"What was tested (CEO-readable narrative)" smoking-
gun paragraph.

### 2. §2.5 paid off on the second adapter cycle in a row

`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`
(added during JUnit hotfix-3 dispatch, commit `d46152e`) binds Run
team's pre-handoff gate to an equipped host when the diff modifies
both `src/novetest/run/adapters/<engine>_adapter.py` AND
`tests/integration/run/test_<engine>_*.py`.

The cargo slice's diff matched the binding heuristic. Run team
detected toolchain versions ≥ matrix floors, ran the engine-specific
integration cases with **0 skips + 0 fails**, captured before/after
envelopes in the handoff. Two cycles after the policy landed, two
clean validations. The amendment's empirical track record is now
strong enough that **§2.5 is the default expectation for all
remaining adapter cycles** (.NET + xUnit + Coverlet next).

### 3. Audit-trail preservation under adapter-local normalization

Fix A is adapter-local: it suppresses the nextest filter-DSL append
when `target_type == "directory"`. But the `RunRecord` still carries
the user's original input verbatim:

```
target_expression = "."         # user typed `.`
target_type       = "directory" # classifier saw a directory
```

This is the canonical pattern for **adapter normalizes invocation
↔ Memory carries user intent verbatim**. Replay / Regression /
Localization downstream can reconstruct what the user actually
requested, even though the native tool received a different argv.
Sub-crate selection (`novetest run crates/foo/`) is documented as
deferred in `engine-adapters.md §5` precisely because audit-trail
honesty is non-negotiable; any future per-sub-crate solution must
preserve the same `target_expression` + `target_type` audit shape.

Counter-example to avoid: silently promoting `target_type` from
`directory` to `workspace` would have "fixed" the symptom faster
but corrupted the audit trail. Scenario B's control case (bare
`novetest run` → `target_type: workspace`) confirms the carve-out
respects the type distinction.

### 4. `adapter-unparseable-output` umbrella overload — fourth sub-kind

`AdapterInvocationError.kind = "unparseable-output"` now disambiguates
four distinct conditions via message text (no new `kind` value):

1. **compile-failure** ("cargo nextest exited 4 ... likely build failure")
2. **env-var missing** (post-2026-05-31 hotfix wording)
3. **llvm-cov missing** (cargo coverage path)
4. **filter matched zero tests** (this cycle's addition: "filter
   matched zero tests, target_expression=..., target_type=...")

The umbrella split (introducing typed `kind` values per sub-kind) was
explicitly deferred in the cargo brief §10 — requires a `questions/`
entry before the structural change. New wording is **keyword-stable
enough** for downstream AI consumers to disambiguate at the message
level, but a formal split is the eventual refactor. **Likely trigger**:
the .NET adapter cycle, which will bring xunit/coverlet-specific
signals likely warranting the same disambiguation pattern → at that
point the umbrella refactor is justified.

### 5. Worktree-isolated node_modules gotcha (and the §2.5 scope interpretation)

`git worktree add` materializes only tracked files. The jest fixtures'
`tests/fixtures/projects/jest-basic{,-coverage}/node_modules/` is
`.gitignore`d, so it lives only in the main checkout. A worktree
created from a freshly equipped host sees the jest cases skip at
`shutil.which("npm")` or fixture-availability gates.

The cargo slice's `§2.5` mandate — "skip count for the engine's
integration cases MUST be 0" — was interpreted **narrowly**: the
binding applies to the engine **in the diff** (cargo here), not to
every engine the equipped host can reach. The slice took this
interpretation by design and the gate stayed green. PM may want to
either:

- **Amend §2.5 wording** to make the narrow scope explicit ("the
  engine the diff modifies"), or
- **Amend `scripts/dev-host-setup.md`** with a "post-worktree-create:
  `cd tests/fixtures/projects/jest-basic && npm install`" step, or
- **Move shared fixture state out of `.gitignore`** (smallest change
  but inflates repo size).

**This is open backlog**, not a blocker. The current interpretation
is operationally sound. Decision deferred until next cycle to learn
whether multi-ecosystem diffs (e.g. a refactor touching pytest +
jest + gotest at once) actually hit this case.

### 6. Cargo v1-exception trigger (a) materially closed at the CLI level

`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md §3` listed
three v1-exception closure triggers. Trigger (a) — "CI matrix gains a
Rust cell" — is formally Release-team territory (PyApp matrix-cell
work).

After this cycle, **operationally the cargo CLI orchestration path
is no longer structurally unverifiable**: the equipped-host gate
runs cargo nextest end-to-end on every adapter slice touching cargo,
and the §2.5 binding makes the gate mandatory. The formal trigger
remains Release-team's call, but the original concern (the path
being verifiable only in production) is materially closed at the
team-level gating layer.

**No action taken** this cycle — formal exception status remains
open until Release-team coordinates. Recorded so a future Release-
team brief can cite this as evidence when the cargo CI cell ships.

### 7. The "PM lists hypotheses, Run team confirms or surfaces alternates" pattern, applied

The cargo brief listed three fix variants (Fix A adapter-local /
Fix B target_resolver-side / Fix C nextest expression DSL) and
recommended A. Run team's handoff §"Fix shape declaration" walks
through why A is right (single source file, no cross-engine coupling,
correct semantic alignment) and explains why B + C are wrong (B
alters cross-adapter contract; C requires per-crate-path expression
construction). Same pattern as JUnit hotfix-3 (where Run team took
Fix-D outside the brief's enumeration after diagnostic on equipped
host).

**Principle reinforced**: brief proposes hypotheses; Run team
diagnoses on equipped host and may select within or outside the
enumeration. The brief's job is to constrain the solution space and
explain the trade-offs, not to dictate.

## Cycle artifacts archived

Four transient files deleted in this close commit:

- **Task (1)**: `tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md`
- **Handoff (1)**: `handoffs/run-team-2026-06-05-cargo-cli-orchestration-defect.md`
- **Verification (1)**: `verifications/2026-06-05-cargo-cli-orchestration-defect.md`
- **Finding (1)**: `findings/manual-test-team-2026-06-05-cargo-cli-orchestration-defect.md`

The `findings/manual-test-team-2026-06-04-host-equip.md` file is
**still retained** — it's standalone institutional context (the event
of Manual Test's host being equipped polyglot-fully) and is
referenced from the equip-and-exercise decision, not a per-cycle
transient. This cycle's close does not change its retention status.

## DoD bullets in delivery-phasing.md

None to tick. Cargo lands in Phase 3's "all six adapters finalized by
end of Phase 3" narrative but does not have a specific DoD checkbox
for "CLI orchestration defect closure" — this is a Phase 2.5/3
maintenance cycle, not a new-deliverable cycle.

The cargo brief's own 8 DoD bullets (handoff §"DoD bullets believed
closed") are evidence-pinned in the handoff and re-verified in the
verification doc. All 8 ticked at cycle close.

## Future-cycle backlog surfaced (NOT auto-queued)

1. **Jest node_modules / worktree heuristic** — amend §2.5 wording OR
   `scripts/dev-host-setup.md` post-worktree-create step (low priority,
   cosmetic, defer until multi-ecosystem diff cycle actually hits it).
2. **`adapter-unparseable-output` umbrella split** — formal
   `engine-adapters.md §4.B` revision introducing typed `kind` values
   per sub-kind. Defer until .NET adapter cycle brings new sub-kinds
   warranting the split.
3. **Cargo v1-exception formal closure** — Release-team coordination
   on whether `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
   §3 trigger (a) can be formally closed now that the operational gap
   is closed. Reactivates when Release team works the CI matrix cell.
4. **Sub-crate directory selection** (`novetest run crates/foo/`) —
   `engine-adapters.md §5` carries the deferral note. Reopen when a
   user requests; would translate to `cargo -p crate` or nextest's
   `-E 'package(crate)'` selector.
5. **JUnit cycle's deferred backlog** (carried forward from the
   2026-06-04 history entry §"Future-cycle backlog surfaced") still
   open: Gradle 9.x verification, multi-module JUnit fixture,
   `.gradle/` `.gitignore` entry, `origin/run-team/junit-adapter-hotfix-2`
   remote branch cleanup, verification-doc identifier drift, JDK 11
   readiness probe hard-reject.

## Counter-history (what we DIDN'T do, and why)

- **DID NOT** modify `src/novetest/run/target_resolver.py`. Fix A is
  adapter-local; the cross-adapter directory-classification contract
  stays intact for pytest/jest/gotest which already consume
  `target_type="directory"` correctly through their own native
  conventions.
- **DID NOT** add per-sub-crate `-p`/`--package` selector logic.
  Deferred per brief §4 until a user requests sub-crate execution.
  The deferral note lives in `engine-adapters.md §5`.
- **DID NOT** introduce a new `AdapterInvocationError.kind` value
  for the no-tests-match case. Stayed on `unparseable-output` per
  brief §2; the umbrella split is queued as backlog item #2 above.
- **DID NOT** retroactively backfill CLI smokes for
  pytest/jest/gotest. Equip-and-exercise §2 binds NEW adapters from
  the policy's effective date; retroactive backfill is optional and
  was not in scope for this cycle.
- **DID NOT** amend `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`.
  The operational closure of trigger (a) is recorded in this history
  entry; formal exception status remains open until Release team
  coordinates.

## Process metrics

- **Cycles**: 1 (no hotfixes; closed on first attempt)
- **Defects caught at Manual Test (0 verdicts failed)**: 0
- **Defects caught at pre-merge gate (0 aborts)**: 0
- **Wall-clock elapsed**: ~1 day (brief queued 2026-06-04 evening,
  closed 2026-06-05 morning Korea time)
- **Slice diff**: +630 / -1 across 5 files (1 modified src + 2 modified
  tests + 1 modified design doc + WORKLOG)
- **Equipped-host gate parity**: 1042 passed + 3 skipped + 0 failed
  on default suite; 4 passed + 0 skipped + 0 failed on cargo focus;
  3 skips are non-cargo (jest×2 + localization×1)

## Effective date

Cycle archived 2026-06-05. The §2.5 binding (added 2026-06-04, now
validated across two distinct adapter cycles) carries forward to the
next adapter cycle (.NET / xUnit v2 + Coverlet) — equipped-host
pre-handoff gate is the default expectation.
