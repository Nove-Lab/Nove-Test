---
from: novetest-pm-team
to: all
type: history
created: 2026-05-31
slug: cargo-build-failure-heuristic-polish
related:
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
---

# History: 2026-05-31 single-slice mini-cycle — cargo build-failure heuristic polish

Small single-team Run polish slice. Shipped within the 2026-05-31
parallel-cycle attempt where the Localization fallback-modes sibling
was kicked back by Main Branch's equipped-host gate. The Run polish
was clean and **merged independently**; this history closes its
mini-cycle. The Localization fix-up is a separate ongoing cycle
(see "Companion cycle" below).

## Slice in scope

| Team | Commit | Verdict |
|---|---|---|
| Run | `8910bf1` (source) + `58bb603` (docs-only correction) | passed |

Cycle: dispatch → handoff → verification (`ee55a52`) → findings
(`2d50e43`) → close (this commit).

## What shipped (product framing)

Diagnostic UX improvement on cargo adapter's two `unparseable-output`
raise sites. When `cargo nextest` or `cargo llvm-cov nextest`
stderr carries the literal `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, the
adapter now raises `AdapterInvocationError(kind="misconfigured-environment")`
with override-diagnosis prose instead of generic `unparseable-output`
(which mis-frames the symptom as a compile failure).

The substantive env-var fix landed earlier
(`1e736cc`, 2026-05-31 hotfix — sets the env var unconditionally
in `_build_child_env()`). This polish is **defense-in-depth
diagnostic** for any edge case where the hotfix is bypassed:
- Parent process / shell pre-unsets the env var (adapter overrides
  it, but the diagnostic helps users understand if they wonder why
  their override didn't take).
- A future nextest version renames or removes the gate (the same
  exit-95-with-zero-events pattern would recur with different
  stderr; substring-only detection on the env-var name remains
  robust).

Single helper `_libtest_json_env_misconfigured_error(*, mode,
returncode, stderr_tail)` is the source of both emissions
(build-failure path + coverage path); the two call sites share a
keyword-only signature so swap-mistakes surface immediately. One
new `AdapterInvocationError.kind` literal (`misconfigured-environment`).
Zero new source modules.

## DoD bullets ticked in `delivery-phasing.md` this close

**None.** Diagnostic UX polish; not a phase-gated feature.

## What didn't ship in this slice (companion cycle)

The parallel-cycle sibling Localization fallback-modes slice (1A)
was kicked back by Main Branch's equipped-host gate
(`questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`).
Two defects surfaced:
- **Defect 1** (Run team territory): `cargo llvm-cov nextest
  --no-fail-fast` doesn't write LCOV on inner nextest non-zero
  exit. Fix queued at
  `tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`.
- **Defect 2** (Localization team territory): aggregate-only
  fixture's panic trace points to assertion site (lib.rs), not bug
  site (arithmetic.rs). CEO chose Option A (move test into
  arithmetic.rs). Fix queued at
  `tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md`.

Both fix-ups are in flight at this close commit's tip. They close
in a separate larger cycle when the Localization re-merge succeeds
+ Manual Test verifies the aggregate mode e2e on the equipped host
(at which point Phase 4 §4 #2 DoD bullet ticks).

## Load-bearing learning (carried forward — process)

Manual Test surfaced **three doc-level observations** in their
findings (none source-level; all in Main Branch's verification doc
predictions):
- Obs 1: Scenario 2 expected `status: "passed"` + `native_exit_code: 0`
  but the `cargo-test-basic` fixture is by-design failing
  (status `"failed"`, exit code 100). Cut-and-paste from
  Scenario 1's all-passing fixture.
- Obs 2: Edge 3 grep count predicted 4 hits, actual is 5
  (detection sites use the constant name, not the literal
  substring).
- Obs 3: `AdapterInvocationError` docstring still lists only 4
  kinds; the 5th (`missing-binary`) was already absent, and this
  slice adds a 6th (`misconfigured-environment`) without amending
  the docstring (deliberate per the WORKLOG entry's first Gotcha;
  defer to a future StrEnum-formalization slice).

**Pattern**: this is the **second cycle in a row** Manual Test has
caught predicted-output typos in Main Branch's verification doc
(prior cycle Obs 1+2 were `glob` path + field-name discrepancies
on Scenario 5). Suggested process improvement: **Main Branch should
dry-run the verification doc's exact command snippets against the
freshly-merged tip before filing**. Catches expected-output
mismatches at the source.

PM defers a verification-doc template change to a future slice;
flagged here so the next Main Branch session that authors a
verification doc sees the pattern. Not blocking; not urgent. The
pattern is small enough that direct doc-template improvement is
better than a process-policy decision.

## Companion cycle (ongoing)

Run Defect 1 + Localization Defect 2 fix-up cycle runs separately.
Tracked via:
- `tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`
- `tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md`
- `tasks/localization-team-2026-05-31-fallback-modes.md` (original
  1A brief; parked Localization worktree `a42ea87` will be
  re-validated through the fix-up cycle)
- `questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
  (CEO response folded in at `345b663`)

That cycle closes when Phase 4 §4 #2 DoD bullet ticks.

## What the next cycle is

Companion Localization fix-up cycle (already in flight). After
that closes, candidates per the 2026-05-31 parallel-cycle close
history §"What the next cycle is":
- Phase 4 §4 #3 (Localization perf NFR — eventually MVP exit
  criterion)
- Phase 3 JUnit (gated on Open Q #5)
- Phase 3 dotnet (gated on Open Q #4)
- Memory `delete` polish (long-standing carry-forward)

CEO picks after the Localization aggregate-mode cycle closes.
