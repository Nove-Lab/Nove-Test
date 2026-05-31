---
from: novetest-pm-team
to: all
type: history
created: 2026-05-31
slug: cargo-env-var-hotfix-and-trigger-b-closure
related:
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md
---

# History: 2026-05-31 cycle — cargo env-var hotfix + **trigger-(b) CLOSED**

Single-team Run hotfix slice closes Issue 1 from the 2026-05-30
cargo E2E sweep (`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` missing in
`_build_child_env()`). Manual Test verdict: **passed**. The polyglot-
host-parity gap for cargo, opened at 2026-05-29 cargo-slice landing
and re-opened at 2026-05-30 trigger-(b) firing, is **now fully
closed** for the first time.

This is the **first end-to-end traversal of the 3-trigger closure
machinery** defined in
`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3.
Decision → trigger fires (host equipped) → re-verify discovers bug
(closure ≠ firing) → hotfix dispatched (separate cycle) → re-verify
confirms working (this cycle). The pattern is now proven; future
adapters (JUnit, dotnet, Rust slow-mode paths) inherit a tested
mechanism.

## Slices in scope

| Team | Commit(s) | Verdict | Phase touched |
|---|---|---|---|
| Run | `1e736cc` | passed (gate + pre-flight host probe + Manual Test E2E re-verify) | Phase 3 — cargo adapter hotfix |

Merge cycle: handoff (Run team) → `1e736cc` (Main Branch fast-forward
merge) → `1745480` (verification) → `e6bab32` (Manual Test findings).
Cycle-close commit: this one.

## DoD bullets ticked in `delivery-phasing.md` this close

**None.** Per task brief Handoff §3: "No `delivery-phasing.md`
checkbox implications — this is a bug fix to a landed adapter, not
a new DoD-tracked feature." Phase 3 DoD remains all-ticked from
prior cycles; the cargo adapter count stays 4/6 (Python / JS-TS /
Go / Rust, all NOW genuinely E2E-verified).

## Cargo trigger-(b) — CLOSED

`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3
defined three closure triggers. **Trigger-(b) is closed as of
2026-05-31.** Specifically:

- **Trigger (b) precondition** (host equipped): satisfied 2026-05-30
  via `scripts/dev-host-setup.md` §4 install (cargo 1.96.0,
  cargo-nextest 0.9.137, cargo-llvm-cov 0.8.7, llvm-tools rustup
  component).
- **Trigger (b) closure** (adapter works on real toolchain): satisfied
  2026-05-31 via Manual Test's verification of the hotfix
  (`findings/manual-test-team-2026-05-31-cargo-nextest-env-var-hotfix.md`,
  deleted at this close — diagnostics preserved here + in the
  WORKLOG entry for `1e736cc`).

Manual Test's smoking-gun proofs:
- `metadata.native_exit_code: 95 → 100` (libtest's "1+ tests failed",
  NOT the pre-fix "experimental feature not enabled"). The single
  cleanest single-number proof that the env var propagates to the
  child process.
- `events.jsonl: 0 lines → 10 lines` of real libtest-JSON events.
  Pre-fix the file existed but was empty; post-fix it contains a
  well-formed event stream.
- `exit 4 (adapter-unparseable-output) → exit 3 (test-failures-detected)`
  with `ok: true`, full `test_results` populated, failure log
  artifact pointing at a real 1578-byte panic log including
  `RUST_BACKTRACE=1` backtrace.
- LCOV coverage path: 62-line LCOV file with 3 `SF:` records, 25
  `DA:` lines, 3 `end_of_record` markers (was missing entirely
  pre-fix). Coverage propagation through `cargo llvm-cov nextest`
  works.
- **Regression engine composes correctly across 2 consecutive cargo
  runs** (Manual Test "Bonus probe 3"). This is the load-bearing
  E2E signal — cargo run records aren't just CLI-surface; they're
  correctly structured for the rest of the engine stack (Memory,
  Regression, future Localization) to consume.

**Note on documentation channel** (continuity with yesterday's
history learning #3): the matrix decision
(`2026-05-25-supported-engine-matrix.md`) and the polyglot-host-
parity decision (`2026-05-29-cargo-adapter-v1-without-rust-e2e.md`)
are NOT amended. Both pin intent/spec; trigger closure is
operational status. Status delta lives here. Future PMs reading
either decision should chain through this history (and yesterday's
`2026-05-30-...-trigger-b-reopened.md`) for the operational
narrative.

Trigger (a) (Release CI Rust cell) and trigger (c) (polyglot host
sweep cycle) remain open but **no longer load-bearing for the cargo
gap** — trigger (b) closure is sufficient. (a) and (c) still serve
as automated / batch-amortized re-verifications in the future;
e.g., when Release adds a Rust cell, it'll act as a regression
gate. They are not blockers.

## Issue 2 follow-up — typed-slot task queued

Per `decisions/2026-05-30-native-result-metadata-slot.md`
§"Dispatch ordering" — the typed-slot slice was binding-gated on
the hotfix merging first (both touch `cargo_adapter.py`). Hotfix
is now landed; PM queues the typed-slot brief in this close commit:

- **Task**: `agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`
- **Scope**: add `NativeResult.metadata: dict[str, str]` field,
  update normalizer overlay with `native_exit_code` reserved-key
  guard, migrate cargo adapter (`payload["nextest_version"]` →
  `metadata["nextest_version"]`), audit pytest / jest / gotest
  adapters for analogous fields and migrate same slice
- **Owner**: Run team (most of the diff is in their territory; PM
  authorizes the cross-territory 1-line addition to
  `src/novetest/models/native_result.py` in the brief)
- **DoD implications**: none on `delivery-phasing.md` directly
  (structural refactor of the contract layer)

## Load-bearing learnings (for future agents)

### 1. Trigger-based gap-closure machinery WORKS end-to-end

The 2026-05-29 polyglot-host-parity decision invented a 3-trigger
closure model under uncertainty. This cycle proved the mechanism
end-to-end for the first time:

```
decision → trigger fires (host equipped)
         → re-verify discovers bug (closure ≠ firing) ← key insight
         → hotfix dispatched (separate cycle)
         → re-verify confirms working
         → trigger CLOSED + history pins status
```

The "closure ≠ firing" insight from yesterday's history learning #3
is what made the mechanism robust — without it, trigger firing
would have been declared as "done" and the bug would have shipped.
Future adapters (JUnit, dotnet) inherit this proven workflow with
high confidence.

**Forward action for PM**: when JUnit / dotnet adapters land,
include the same 3-trigger closure structure in their respective
decisions. The pattern is now production-validated; no need to
re-invent the model.

### 2. The pre-flight host-present probe is now mandatory norm

Yesterday's history learning #1 ("Native engine adapters carry
runtime contracts that pre-shipped tests miss") prescribed: PM
SHOULD include a pre-flight host-present probe step in every
future Native engine adapter brief at handoff time.

The Run team's hotfix brief followed this prescription
(`tasks/run-team-2026-05-30-...-hotfix.md` §"Pre-flight host
check (MANDATORY before opening the handoff)"). The Run team ran
the probe, observed `2 passed in 1.12s`, and shipped with
confidence. Main Branch independently re-ran on the merged tip and
saw the same `2 passed`. Manual Test then ran the SAME probe a
third time post-merge.

Result: **the bug-discovery path is now multi-layered.** Three
independent host-present executions before declaring closure.
The norm should be retained verbatim for JUnit / dotnet.

### 3. Bonus E2E probes from Manual Test are a multiplier

Manual Test went beyond the verification doc's required scenarios
and added 3 bonus probes:
1. Failure log artifact has real content (verified 1578-byte panic
   log with RUST_BACKTRACE backtrace)
2. Consecutive `novetest run` calls accumulate cleanly (ULID
   uniqueness, run record persistence)
3. **Regression engine composes across 2 cargo runs** — proves
   `cargo-test` run records are correctly typed for the engine
   stack to compose, not just for CLI display.

The third probe is particularly valuable — it implicitly verified
that the cargo adapter's normalized output threads cleanly through
Memory → Regression. Future Manual Test sweeps for new adapters
should consider adding analogous "engine stack composition" probes
beyond pure CLI-surface verification.

## What the next cycle is

**Single-team Run typed-slot slice** for Issue 2
(`tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`),
per the dispatch ordering in
`decisions/2026-05-30-native-result-metadata-slot.md`.

After typed-slot lands, the natural follow-ons (no strict
ordering — CEO picks):
- **Phase 3 JUnit adapter** — gated on Open Q #5 (JUnit launcher
  bundling). CEO call would unblock.
- **Phase 3 dotnet adapter** — gated on Open Q #4 (Coverlet
  PerTestCoverage key). CEO call would unblock.
- **Phase 4 §4 #2** — `sbfl_aggregate` / `failure_proximity`
  modes + fixtures (Localization team).
- **Phase 4 §4 #3** — NFR-LOC-002 perf slice (Localization team).
- **Coverage LCOV dispatch on `engine_name == "cargo-test"`**
  (Coverage team, independent of Run typed-slot — no file
  conflict).
- **Build-failure heuristic UX polish** at `cargo_adapter.py:263`
  (Manual Test surfaced as low-priority polish; specific error
  code for `NEXTEST_EXPERIMENTAL_LIBTEST_JSON` literal in stderr).

## Other deferred items (visible to future PM)

1. **Edge 6 (Cyclopts help UX for `None`-sentinel flags)** — still
   deferred-not-queued per 2026-05-30 CEO decision (defer until
   post-MVP user feedback).
2. **`scripts/dev-host-setup.md` §4** — no refinement needed
   beyond commit `a0f6582`. Verified again this cycle on the same
   host, no drift. Setup doc is "paying for itself" per Manual
   Test's verbatim feedback.
3. **Memory `delete` CLI workflow polish** — carry-forward from
   2026-05-27 cycle, still pending.
4. **Open Q #4 (.NET PerTestCoverage key) + Open Q #5 (JUnit
   launcher)** — both still gating Phase 3 JUnit / dotnet adapters.
5. **Coverage LCOV dispatch on `engine_name == "cargo-test"`** —
   the cargo adapter now produces well-formed LCOV
   (`coverage_lcov` artifact verified this cycle); Coverage engine
   doesn't yet parse it. Independent Coverage-team slice.
6. **`nextest_version` payload-stash → typed slot migration** —
   queued in this close commit as Issue 2 follow-up.
