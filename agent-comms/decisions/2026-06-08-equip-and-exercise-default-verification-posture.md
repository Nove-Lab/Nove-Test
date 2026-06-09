---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-08
slug: equip-and-exercise-default-verification-posture
related:
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md
  - agent-comms/history/2026-06-05-cargo-cli-orchestration-defect-and-second-equip-exercise-validation.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
  - agent-comms/history/2026-06-08-b1-polish-parallel-pair-defect7-and-fixed-tests-spec.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
  - agent-comms/tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md
---

# Decision: Equip-and-exercise is the default verification posture for ALL `src/` + `tests/` slices

CEO-approval pending. Builds on `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
without modifying its §2.5 file-glob heuristic or any of its §1-§5
adapter-specific bindings. This is a **scope-extension meta-decision**,
not a re-derivation.

## Context — 6 consecutive cycles of empirical validation

Since 2026-06-04 (the equip-and-exercise decision's effective date),
**every** cycle that has merged `src/` or `tests/` changes has gone
through the same verification posture: Manual Test validates on an
equipped host (`~/.local/share/novetest-toolchains.sh` sources +
verified toolchain banner) before declaring a verdict. The posture
has now been the verification default for six consecutive cycles
without exception:

| # | Date | Cycle | Adapter touched? | §2.5 fired? | Manual Test host | Verdict |
|---|---|---|---|---|---|---|
| 1 | 2026-06-04 | JUnit hotfix #1 | YES (junit) | YES | equipped | PASSED (after hotfix-1) |
| 2 | 2026-06-05 | Cargo CLI orchestration defect | YES (cargo) | YES | equipped | PASSED |
| 3 | 2026-06-06 | .NET adapter + hotfix #1 | YES (dotnet) | YES | equipped | PASSED (after hotfix-1) |
| 4 | 2026-06-07 | envelope-warnings + cobertura-derive parallel pair | YES (run/types + coverage) | YES (envelope-warnings touches adapter integration tests) | equipped | PASSED |
| 5 | 2026-06-08 | B1 polish — defect7 + fixed-tests-spec parallel pair | NO | NO | equipped | PASSED |
| 6 | 2026-06-08 | B2 UX-normalize — coverage + localization + run hardening parallel triple | NO (Run slice unit-tests only) | NO | equipped | PASSED |

Cycles #5 and #6 are the load-bearing observations. Both were
non-adapter polish cycles where the §2.5 file-glob heuristic did NOT
fire (no `src/novetest/run/adapters/*_adapter.py` change + no
`tests/integration/run/test_*_<engine>_*.py` change). Despite that,
Manual Test still ran the verification on the equipped host. The
posture was *de facto* default across the entire `src/` + `tests/`
surface, not just adapter cycles.

The next cycle (Release readiness assessment,
`tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md`)
will be the **7th consecutive validation** — release readiness itself
exercises CI matrix + binary build + install.sh smoke on an equipped
host. This decision codifies the posture before the 7th observation
turns the pattern into operational dogma without explicit ratification.

## What this decision pins

### 1. Manual Test verification host = equipped, by default

For every cycle that merges `src/` or `tests/` changes, the Manual Test
verification step SHOULD run on an equipped host (`scripts/dev-host-setup.md`
or equivalent local installation). The verification host is equipped
unless a specific cycle's verification request explicitly states
otherwise + provides a reason.

**Scope**: ALL `src/` + `tests/` slices, not only adapter cycles. The
2026-06-04 decision's §1 ("verdict-blocking gate for every new Native
Engine adapter cycle") remains in force unchanged; this decision
*extends* the default posture to non-adapter cycles, but at SHOULD-strength
(non-adapter cycles MAY ship on general host if Manual Test documents
the choice).

The two strength tiers:

| Cycle shape | Verification host | Strength |
|---|---|---|
| **Adapter cycle** (matches §2.5 file-glob: `adapters/<engine>_adapter.py` + `tests/integration/run/test_<engine>_*.py`) | Equipped | **MUST** (per 2026-06-04 §1) |
| **Non-adapter cycle** (touches `src/` or `tests/` but does NOT match §2.5 file-glob) | Equipped | **SHOULD** (this decision) |

The MUST tier inherits its verdict-blocking semantics from the
2026-06-04 decision unchanged. The SHOULD tier is a soft default:
Manual Test's verification template defaults to "Host: equipped"; a
deliberate exception requires a one-line rationale in the verification
doc.

### 2. Originating team's §2.5 pre-handoff gate scope is UNCHANGED

The 2026-06-04 decision §2.5 file-glob heuristic remains the only
trigger for the **originating team's** pre-handoff equipped-host gate:

- `src/novetest/run/adapters/<engine>_adapter.py`
- `tests/integration/run/test_<engine>_*.py`

Non-adapter cycles (Localization, Coverage, Regression, Replay,
Orchestration, etc.) do NOT require the originating team to equip
their pre-handoff gate host. Manual Test's verification host (§1
above) is where the equipped-host invariant lives for those cycles.

This split is intentional. The §2.5 pre-handoff gate exists to catch
the specific failure mode where an adapter's CLI-execution path
silently skips on a toolchain-less host — a mode unique to adapter
code. Other engines (Coverage, Localization, etc.) are pure-Python
and do not have an analogous failure mode. Pushing the §2.5
requirement onto every team would add ceremony without value.

### 3. Verification doc template — "Host: equipped" as the default banner

`agent-comms/README.md` §"Standard body sections (per type) →
verifications/" SHOULD be amended in the same commit as this
decision to recommend a "Host" line in the verification doc front-
matter or top section, with "equipped" as the default value and an
explicit rationale required if "general host" is chosen.

(This README amendment is a polish item; it is NOT a verdict-
blocker. The defacto practice is already in place — every recent
verification doc opens with an "Environment" or "Host" line; this
just standardizes the location.)

## What this decision does NOT change

- **§2.5 file-glob heuristic** (2026-06-04 §2.5): unchanged. Only
  adapter slices trigger the originating team's pre-handoff equipped-
  host gate.
- **2026-06-04 §1, §2, §3, §4** (Manual Test verdict-blocking gate for
  adapter cycles): unchanged. Adapter-cycle Manual Test passes remain
  MUST-equipped, with verdict-blocking semantics.
- **2026-06-04 §5** (cargo v1 exception): unchanged. The cargo Manual
  Test E2E gap continues to govern per `2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  §3 closure triggers.
- **2026-06-04 §2.5.1** (what does NOT count as compliance for §2.5):
  unchanged. Argv-only unit stubs, internal-call integration tests,
  and unreachable-envelope smokes still don't satisfy §2.5.

## Why now (vs after the 7th observation)

Two reasons:

1. **Avoid ratifying-by-accumulation**: codifying the posture before
   the 7th observation prevents the pattern from solidifying as
   tribal knowledge without explicit ratification. Future PMs (or
   future cycle teams) who see "6 cycles followed this; the 7th did
   too" without a decision doc would have a harder time interpreting
   the boundary between MUST and SHOULD strength.
2. **Release-readiness narrative coherence**: the Release readiness
   cycle's sign-off statement ("MVP release-ready as of `<commit>`")
   carries more weight when the verification posture under which it
   was reached is explicitly named. Without this decision, the
   sign-off implicitly relies on a 6-cycle pattern that has no
   binding name.

## Effective date

Effective immediately upon CEO approval + commit merge. The Release
readiness cycle currently pending dispatch
(`tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md`)
will be the first explicit application of this decision's SHOULD
tier — its verification will run on an equipped host per §1.

## Supersedes / amends

- **Builds on**: `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
  (unchanged; this decision extends scope without modifying the
  original's bindings).
- **Composes with**: `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  (cargo v1 exception path unchanged).
- **No prior decision is superseded.**

## Affected teams / files

- **Manual Test team**: applies the SHOULD-equipped default to
  non-adapter cycles starting with the Release readiness verification.
  No charter change required.
- **PM**: includes "Host: equipped" banner in verification request
  templates (Main Branch authors verification requests; PM curates
  the README template if §3 amendment is taken).
- **All originating teams**: §2 unchanged — Run team continues to
  apply §2.5 to adapter slices; other teams continue to ship on
  general host.
- **Main Branch**: verification doc template adds "Host:" line per
  §3 (optional polish, not blocking).

## Implementation notes

This decision is an **anti-fragility move**, not a behavior change.
The 6-cycle observation pattern is reified into a binding default so
that:

1. The next time a non-adapter cycle runs (post-release polish,
   Phase 7 MCP, etc.), Manual Test does not have to re-derive "should
   we equip the host?" from first principles.
2. The Release readiness cycle's sign-off carries explicit reference
   to the verification posture under which it was reached.
3. Future PMs reading the audit trail see "the posture was ratified
   on 2026-06-08 after 6 consecutive empirical validations" rather
   than "the posture emerged as tribal knowledge."

If a future cycle finds the SHOULD tier causes friction (e.g., a
non-adapter slice whose verification genuinely benefits from a
general-host probe), Manual Test files the exception via a one-line
rationale in the verification doc, and the cycle proceeds. The
decision is permissive of well-reasoned deviation; it just prevents
silent drift.
