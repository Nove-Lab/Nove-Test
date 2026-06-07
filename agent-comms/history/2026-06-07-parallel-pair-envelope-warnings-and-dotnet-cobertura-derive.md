---
from: novetest-pm-team
to: all
type: history
created: 2026-06-07
slug: parallel-pair-envelope-warnings-and-dotnet-cobertura-derive
status: archived
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/findings/manual-test-team-2026-06-06-host-equip.md
  - design/implementation-plan/delivery-phasing.md
---

# Parallel pair — envelope-warnings-projection + dotnet-cobertura-derive (both passed; MVP-blocking gap-pair closes)

## TL;DR

The two MVP-blocking parallel briefs PM queued on `130a5eb` (2026-06-06)
both landed clean in a single equipped-host validation pass on 2026-06-07.

| Slice | Feat commit | Verification tip | Manual Test verdict |
|---|---|---|---|
| `envelope-warnings-projection` (Run+Orch+CLI cross-team) | `c2340e8` | `d735a6a` | **passed** (all 8 scenarios, 8 critical edges green) |
| `dotnet-cobertura-derive` (Coverage single-team) | `c1ee2a4` | `113fa2b` | **passed** (all 8 scenarios, 8 critical edges green) |

These two slices close the two product gaps PM identified at the
2026-06-06 .NET adapter Phase 2.5 cycle-close history file under "Track
C" + "Track D":

- **Track C** — adapter warnings now reach the JSON envelope's
  top-level `warnings[]` field across all 6 engines, with v1 metadata-
  channel kept as a backward-compat bridge per the
  `2026-06-06-adapter-warning-surface-v1-metadata-channel` decision.
- **Track D** — .NET coverage now produces a real `CoverageFactSet`
  (not `CoverageUnavailable`), making `coverage show / diff / inspect`
  light up identically across all 6 native engines.

Combined narrative: **all six adapters are production-ready AND all
six are first-class Coverage citizens AND adapter warnings have a
uniform top-level envelope surface across all six.** This is the
moment the "polyglot test orchestration tool" promise is fully
internally consistent across every native engine.

## Why both slices landed cleanly in one host pass

PM's parallel-dispatch decision (file-disjoint, team-disjoint, both
small) was vindicated by Manual Test's ability to verify both
empirically against the same equipped host (`YJ-LAPTOP`) within a
single session. The two findings cite the **same Manual Test tip
commit `113fa2b`** and the **same merged tip** — no separate
verification host bring-up, no toolchain drift between the two.

This is the fourth consecutive equipped-host validation cycle on
`YJ-LAPTOP` (JUnit hotfix #3 → cargo CLI orch → .NET hotfix #1 →
this parallel pair). The §2.5 binding gate from
`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
continues to pay dividends.

## Load-bearing lessons (for future agents)

### 1. Cross-team scope expansion via narrow PM authorization works in practice

`envelope-warnings-projection` was the first slice where PM pre-
authorized cross-team file touches in the brief (Run team allowed to
edit `orchestration/workflows/run.py` + `cli/app.py` for specifically
named changes). The Run team **stayed within the granted scope plus
one mechanical adjustment** (`replay/engine.py` 1-line tuple unpack
forced by the authorized `execute()` signature change), and filed
that mechanical touch transparently in the handoff §"Cross-team
scope footprint" for PM retroactive ratification.

**The pattern:**

- Brief explicitly names cross-team files + the specific changes
  allowed in each.
- Receiving team adheres to the named files.
- If a mechanical consequence forces touching an additional file
  (e.g. signature-change ripple), the team flags it in the handoff
  rather than silently expanding scope.
- PM ratifies retroactively in the cycle-close history (this is the
  ratification: the `replay/engine.py` 1-line `record, _ = await
  execute_with_engine_context(...)` adjustment is acceptable and
  sets precedent for future mechanical-ripple cases).

**Why this beats "file a question and pause"**: the mechanical
adjustment was unambiguous (any non-trivial signature change forces
all callers to adapt), the behavior change was nil (warnings
discarded at this call-site because replay's envelope is the Replay
Result block, not a RunRecord envelope), and pausing to question
would have delayed the slice for zero design-decision benefit. The
"flag in handoff for retro ratification" pattern is the right shape
when:

1. The mechanical adjustment is forced (i.e. the unauthorized file
   MUST change for the slice to compile/pass tests), AND
2. The behavior change at the unauthorized file is null or trivially
   verifiable (regression tests still green), AND
3. The handoff calls out the touch explicitly with rationale.

Future cycles can cite this precedent.

### 2. Architecture deviations under "Run team may refine" should be documented in the handoff, not silently buried

The brief's §2.5 literally typed `RunOutcome.warnings: tuple[
EnvelopeWarning, ...] = ()`. Implementing that literally would have
forced `orchestration/workflows/run.py` to import `EnvelopeWarning`
from `cli/output.py`, inverting the existing `cli → orchestration →
run` dependency direction and creating a module-load cycle.

Run team's correct response: **shipped `AdapterWarning` at the
orchestration layer, projected to `EnvelopeWarning` at envelope-
construction time in the CLI handler**. The two dataclasses are
field-by-field identical per decision criterion #3; the conversion
is a one-liner per warning. Run team **documented the deviation
explicitly in the handoff** under "Architectural deviation" with the
dependency-direction rationale.

This is the right shape: when a brief's literal type collides with
project-internal architecture, the receiving team refines to a
field-equivalent shape that respects the architecture, and surfaces
the deviation in the handoff so PM can confirm the equivalence.

### 3. The "open product question" channel for verification doc → finding is the right surface

Manual Test's `dotnet-cobertura-derive` finding raised Critical Edge
#4 (`coverage show` aggregate-only envelope vs handoff DoD bullet 6's
"structured per-file coverage" language) as an **open product
question for PM disposition**, not a defect. The finding offered two
interpretations + an explicit "PM judgment needed" line.

PM disposition (this cycle): **ratify Interpretation 1 — aggregate-
only at the verb level is the v1 contract**. Rationale:

- The persisted `CoverageFactSet` at `.novetest/coverage/facts/
  run_<ULID>/coverage_facts.json` IS the canonical per-file surface
  (AI consumers wanting per-file detail read this file directly).
- `coverage show` as an aggregate-summary verb is the user-friendly
  default and matches the verb's name semantics.
- A future `--detail` flag (or new verb) is a clean extension path
  if MVP feedback shows demand for verb-level per-file detail.
- Bubbling per-file to the verb envelope is a v2 expansion, NOT a
  v1 gap.

DoD bullet 6 of the Coverage handoff is interpreted as referring to
the **persistence path** (the fact-set is structured per-file) — not
the **verb-level envelope**. The wording remains accurate at the
persistence layer; future verification docs should be more precise
when claiming "verb returns X" vs "fact-set carries X".

No decision file needed — this is a v1 surface ratification recorded
in the history file as cycle-close disposition.

### 4. The Cap-X format and the byte-equivalent reproduction discipline are now thoroughly proven

Main Branch's verification docs for both slices used the Cap-X
format (Cap-1 through Cap-N discrete envelope captures). Manual
Test reproduced each Cap-X byte-equivalently modulo per-run ULIDs +
timestamps. The format is now the standard for adapter + coverage
verification work going forward.

**Subtle observation:** in the `envelope-warnings-projection`
verification doc, two minor documentation-precision issues
surfaced (Manual Test minor observations §1 + §2):

1. The doc cited the probe path `.data.memory_entry.run_record.
   payload.warnings` — but `RunRecord` has no `payload` field
   (normalizer drops `NativeResult.payload` at the engine→record
   boundary). The decision's "Forensic `NativeResult.payload[
   'warnings']` retained" language refers to the **in-memory
   adapter-internal payload**, not the user-visible envelope path.
2. The doc cited the test class `TestAdapterWarningStructuralContract`
   but the actual class on the merged tip is named
   `TestAdapterWarningShape`. Drift between brief intent and the
   refined test-class name during implementation.

**Process improvement for Main Branch:** when authoring verification
docs, run `pytest --collect-only` against the merged tip to obtain
verbatim test paths; spot-check probe paths against the actual
post-merge code (e.g. `jq '.data.memory_entry.run_record | keys'`
on a real run's envelope). These checks would have caught both
issues pre-verification-doc-publish. Not blocking; recorded as
post-MVP process polish.

### 5. The two-channel backward-compat pattern (v1 metadata + v2 envelope) shipped cleanly

The `envelope-warnings-projection` slice implements the decision's
criterion #2 ("dual-write the v1 metadata channel alongside the new
envelope channel for one release cycle"). On the dotnet/coverage-
absent path:

- New v2 surface: `envelope.warnings[0] = {code: "engine-misconfigured",
  details: {...}, message: "..."}`
- Retained v1 bridge: `data.memory_entry.run_record.metadata.
  coverage_unavailable_kind = "coverlet-absent-or-stale"` +
  `.coverage_unavailable_message = "..."`

Both channels carry the same information. The deprecation of the v1
metadata channel is queued for a post-MVP cleanup cycle per the
decision's "Effective dates" timeline. No CI/integration test
asserts the v2-only future — by design, the v1 channel must remain
functional for one release cycle to give external AI consumers time
to migrate.

**Lesson for future deprecation cycles:** the dual-write window is
explicit, time-bound, and decision-documented. When the cleanup
cycle eventually runs, the decision file's "Effective dates" section
is the authority for what the v1 surface looked like and when it
was retired.

## Two minor verification-doc precision items (for future Main Branch process)

These are NOT defects; they're documentation-quality items recorded
here so PM can reference them next time a verification doc is
authored:

1. **Probe-path accuracy** — verify the path against an actual
   merged-tip run's envelope (via `jq | keys`) before citing it. The
   `payload.warnings` path cited in the envelope-warnings verification
   doc is structurally absent from `RunRecord`.

2. **Test-path accuracy** — verify class/method names against
   `pytest --collect-only` output on the merged tip. The class name
   `TestAdapterWarningStructuralContract` in the verification doc is
   `TestAdapterWarningShape` on disk.

Both items were transparently flagged in the Manual Test finding's
"minor observations" section, demonstrating that the cycle's QA
loop catches these without blocking the verdict. They become
defects only if Main Branch repeats them; today they're caught.

## Future-cycle backlog (recorded; NOT auto-queued)

These observations from the parallel pair will be surfaced to CEO at
the right time, but are NOT auto-dispatchable:

1. **Multi-warning ordering contract test** — today no fixture emits
   more than one warning per run, so the array ordering across
   multiple emit sites is not pinned by a test. The .NET adapter has
   both `engine-misconfigured` (coverlet-absent) and `xunit-v3-
   coverage-deferred` code paths — a future fixture that triggers
   both in one run would establish the ordering contract. Cheap to
   add; not blocking. Manual Test recommendation #5 of the
   envelope-warnings finding.

2. **v1 metadata-channel cleanup (post-MVP cycle)** — remove
   `coverage_unavailable_kind` + `coverage_unavailable_message`
   from `RunRecord.metadata` per the
   `2026-06-06-adapter-warning-surface-v1-metadata-channel` decision's
   "Effective dates" timeline. Touch points: dotnet adapter (drop the
   metadata writes) + tests asserting both channels (drop the
   metadata-side assertions) + any documentation pinning these
   keys. Slice scope: ~30-50 LOC src + ~20-40 LOC test deletions.
   NOT MVP-blocking.

3. **`coverage show --detail` flag (or `coverage detail` verb)** —
   IF MVP feedback shows demand for per-file detail at the verb
   level, file a slice to extend the envelope. Touch points:
   `cli/handlers/coverage.py` + envelope builder for `coverage.show`;
   6 engines × per-file pass-through. Optional; not MVP-blocking.
   Coverage finding recommendation #3 Interpretation 2.

4. **Cobertura branch coverage parity with JaCoCo** — JaCoCo emits
   synthesized branch indices via `cb`/`mb` counters; Cobertura v1
   emits zero with `branch_arc_semantics = "branches-omitted"`. Post-
   MVP polish slice to align the two paths. Coverage finding
   recommendation #5. Cheap to scope when the cycle pipeline opens up.

5. **`CoverageUnavailable.reason_kind` / `reason_detail` split** —
   today the discriminator (`cobertura-sources-not-found`) is free-
   form text in the `detail` field, matching the JaCoCo / LCOV
   precedent. A future structured `reason_kind` enum + `reason_detail`
   free-form would parallel the v2 adapter-warning surface (code +
   details + message). Coverage finding recommendation #4. NOT MVP-
   blocking.

6. **Release-team CI matrix .NET cell** — `test_dotnet_cobertura_
   derive.py` and `test_dotnet_warnings.py` require `dotnet` on PATH;
   CI lanes don't include .NET, so both tests skip in CI today. The
   equipped-host §2.5 gate covers .NET coverage end-to-end before
   each merge, so this is not blocking. Release-team backlog item.
   Coverage finding recommendation #6.

7. **Verification-doc authoring practice updates** — Main Branch
   should run `pytest --collect-only` against the merged tip when
   citing test paths, and spot-check envelope probe paths with `jq |
   keys`. See §"Two minor verification-doc precision items" above
   for context.

## PM dispositions made this cycle (cycle-close ratifications)

These dispositions are recorded here, not in separate decision files
(they are surface ratifications, not cross-team structural rulings):

1. **Critical Edge #4 (`coverage show` aggregate-only)** — ratified
   Interpretation 1: aggregate-only at the verb level is the v1
   contract. Per-file detail lives in the persisted fact-set on
   disk. DoD bullet 6 of the Coverage handoff refers to the
   persistence layer's per-file shape, not the verb envelope. See
   §"Load-bearing lessons" #3 above for rationale.

2. **`replay/engine.py` mechanical 1-line touch (Run handoff
   recommendation #4)** — ratified retroactively. The `record, _ =
   await execute_with_engine_context(...)` adjustment was a forced
   mechanical consequence of the authorized `execute()` signature
   change; behavior unchanged (verified: 69/69 replay tests green
   in Scenario G). Sets precedent for "mechanical-ripple touch with
   handoff disclosure" as an acceptable cross-team scope footprint
   pattern. See §"Load-bearing lessons" #1 above for the rule shape.

3. **`AdapterWarning` at orchestration + projection-at-CLI shape
   (Run handoff "Architectural deviation")** — ratified. The brief's
   literal type collided with project module dependency direction;
   Run team's refinement is field-equivalent (criterion #3 verified)
   and respects the architecture. Future briefs that pin types
   crossing module boundaries should anticipate this and pre-clear
   the dependency direction.

4. **Brief §1.1 JUnit / `engine-misconfigured` row was a misattribution
   (Run handoff "Brief §1.1 catalog deviation")** — acknowledged.
   The kind `engine-misconfigured` is .NET-adapter-only as a warning;
   JUnit's misconfig surface raises `EngineNotReadyError` on the
   readiness probe path (envelope.errors[]), not a warning. The
   integration test for the misattributed row was correctly omitted.
   PM brief-authoring item: catalog rows should be grep-validated
   against adapter source pre-publish.

## Phase 2/3 Coverage promise — final scorecard

| Engine | Coverage derive path | `coverage_outcome.kind` | Status |
|---|---|---|---|
| pytest | `coverage.py` JSON | `fact-set` | ✅ |
| jest | Istanbul JSON | `fact-set` | ✅ |
| gotest | LCOV | `fact-set` | ✅ |
| cargo | LCOV | `fact-set` | ✅ |
| junit (Maven + Gradle) | JaCoCo XML | `fact-set` | ✅ |
| **xunit (.NET / Coverlet)** | **Cobertura XML** | **`fact-set`** | **✅ NEW THIS CYCLE** |

Phase 3's narrative promise ("all six engines in coverage") is
empirically met. The polyglot Coverage surface is now uniform
across every supported ecosystem.

## Adapter-warning surface — final v1 scorecard

| Engine | Warning emit sites today | Envelope projection |
|---|---|---|
| pytest | 0 | `warnings: []` (plumbing wired) |
| jest | 0 | `warnings: []` (plumbing wired) |
| gotest | 0 | `warnings: []` (plumbing wired) |
| cargo | 0 | `warnings: []` (plumbing wired) |
| junit | `missing-jacoco`, `ambiguous-build-tool` | full v2 envelope projection ✅ |
| xunit | `engine-misconfigured`, `xunit-v3-coverage-deferred` | full v2 envelope projection + v1 metadata bridge ✅ |

All 6 engines unconditionally carry the `envelope.warnings` field
(wire-shape contract: "field present always, sometimes empty"). The
two engines with warning-emit sites today (junit + xunit) populate
the array; the other four carry `[]`. Future warning emit sites in
the four currently-empty engines slot into the same dual-channel
pattern without plumbing changes.

## Track-status update — MVP path remaining

| Track | Status | Notes |
|---|---|---|
| **C** envelope-warnings-projection | ✅ **CLOSED THIS CYCLE** | Option C MVP-blocker satisfied; v1 metadata bridge retained for one release cycle |
| **D** dotnet-cobertura-derive | ✅ **CLOSED THIS CYCLE** | 6th-engine Coverage promise satisfied; polyglot Coverage uniform |
| **A** B1 critical polish | NOT YET SCOPED | Category, not a slice — PM scopes into concrete briefs on CEO request |
| **B** B2 UX normalization | NOT YET SCOPED | Category, not a slice — PM scopes into concrete briefs on CEO request |

**MVP completion path:** with Tracks C + D closed, the remaining MVP
work is concentrated in the "polish" track (Tracks A + B from the
prior history). Estimated 1-2 more dispatch cycles to scope-and-ship
each, depending on how the categories decompose.

## Cycle-close bookkeeping summary

Transient files retired in this cycle's close commit:

- `tasks/coverage-team-2026-06-06-dotnet-cobertura-derive.md`
- `tasks/run-team-2026-06-06-envelope-warnings-projection.md`
- `handoffs/coverage-team-2026-06-07-dotnet-cobertura-derive.md`
- `handoffs/run-team-2026-06-07-envelope-warnings-projection.md`
- `verifications/2026-06-07-dotnet-cobertura-derive.md`
- `verifications/2026-06-07-envelope-warnings-projection.md`
- `findings/manual-test-team-2026-06-07-dotnet-cobertura-derive.md`
- `findings/manual-test-team-2026-06-07-envelope-warnings-projection.md`

Retained:

- `findings/manual-test-team-2026-06-04-host-equip.md` (institutional;
  equipped host #1 — other dev box)
- `findings/manual-test-team-2026-06-06-host-equip.md` (institutional;
  equipped host #2 — `YJ-LAPTOP`)
- The in-force decisions (`2026-05-25-supported-engine-matrix`,
  `2026-06-02-phase5-sqlite-deferred-until-cross-run-verb`,
  `2026-06-03-coverlet-pertestcoverage-key`,
  `2026-06-03-junit-console-launcher-vendor`,
  `2026-06-04-equip-and-exercise-for-adapter-cycles`,
  `2026-06-06-adapter-warning-surface-v1-metadata-channel`)
- This history file

No new decision files needed this cycle — the dispositions are v1
surface ratifications recorded above, not cross-team structural
rulings.

No DoD bullet ticks needed — `delivery-phasing.md`'s Phase 2/3
bullets are already fully ticked; the two slices closed this cycle
satisfy narrative promises (Phase 2/3's "all six engines in coverage"
and the implicit "uniform adapter warning surface") that were not
literally encoded as separate unchecked DoD bullets.
