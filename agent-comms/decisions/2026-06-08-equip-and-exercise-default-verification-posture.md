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

---

## Amendment 2026-06-19 — CI matrix verdict criterion (path/OS/Python-sensitive slices)

**Status**: CEO-approved. Folds in the disposition #2 surfaced by
`agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
§"PM dispositions this cycle" #2. Closes Future-cycle queue item #7
from `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`.

### Context

The 2026-06-09 Windows-CI fix triple cycle (Coverage `4110645` +
Localization `edb78f8` + Run `a6ebd91`) established a new verdict
criterion empirically: each slice's verification doc cited a specific
`ci.yml` run on the post-fix HEAD with all matrix cells green
(`27187459586` on `871a278` 10/10 GREEN). This criterion broke the
9-day chronic Windows red that had drifted since 2026-05-31 — the
prior 14 days of cycle-close commits had carried Linux-only
`pytest -q` green statements without cross-OS evidence, and that
missing check is precisely what let the regression drift.

PM disposition #2 from the fix-triple history queued an amendment
to this decision when the next path/OS/Python-sensitive slice
arrived, or sooner if a standalone decision was warranted. With the
2026-06-18 parallel cycles closing without any path/OS regressions
(Windows install.ps1 cycle exercised cross-OS verification; text
renderer cycle was path-independent), the criterion has been
ambient practice for ~10 days. Codifying now before the next
ambiguity surfaces.

### §4. CI matrix verdict criterion (new clause)

For any slice whose surface intersects **path-handling**, **OS-gating**,
or **Python-version sensitivity**, the verification doc MUST cite a
specific `ci.yml` workflow run on the merged HEAD (or the post-fix
HEAD if the cycle is itself a fix slice) with the following structure:

- **Anchor**: a `ci.yml` run number + commit SHA the run was triggered on.
- **Verdict**: all 9 matrix cells (3 OS × 3 Python) MUST report
  `conclusion: success`. The non-blocking `perf` lane is informational
  only; its conclusion does NOT gate the verdict.
- **Strength**: **MUST** — verdict-blocking.

The criterion composes with §1's equipped-host tier:

| Slice shape | Equipped host? | CI matrix run citation? |
|---|---|---|
| Adapter cycle (matches §2.5 file-glob) | MUST | MUST if path/OS/Python-sensitive (per §4); otherwise SHOULD |
| Non-adapter cycle, path/OS/Python-sensitive surface | SHOULD (per §1) | **MUST** (this amendment) |
| Non-adapter cycle, path/OS/Python-insensitive surface | SHOULD (per §1) | SHOULD (default; cite Linux green only if a deliberate exception) |

### §4.1. What counts as path/OS/Python-sensitive

A slice's surface is path/OS/Python-sensitive if ANY of the following
apply:

1. **Path-handling**: touches `pathlib.Path` operations beyond simple
   concatenation, OR introduces `os.path` calls, OR modifies any code
   that converts between absolute and workspace-relative paths.
2. **OS-gating**: introduces or modifies `pytest.mark.skipif` based on
   `sys.platform`, `os.name`, or runner environment, OR introduces
   subprocess invocations whose argv differs by OS (e.g., `cmd /c npx`
   vs bare `npx`), OR touches `scripts/install.{sh,ps1}` or
   `.github/workflows/`.
3. **Python-version sensitivity**: uses Python 3.11/3.12/3.13-specific
   syntax (e.g., `StrEnum`, PEP 695 generics, `typing.Self`), OR
   modifies any `if sys.version_info >= ...` branch, OR adds a new
   stdlib import that landed in a specific Python version.

When in doubt, the originating team SHOULD treat the surface as
sensitive and cite the CI matrix run. The cost of a redundant citation
is low; the cost of a missed cross-OS regression is the 9-day chronic
red that triggered this amendment.

### §4.2. Citation shape

The verification doc's "Environment" or "CI evidence" section MUST
contain a row of the shape:

```
ci.yml run <run_id> on commit <sha> — <conclusion>: <n>/<n> jobs
  - test (ubuntu-latest / py3.11): <conclusion>
  - test (ubuntu-latest / py3.12): <conclusion>
  - ...
```

The conclusion summary is sufficient; per-job enumeration is
recommended but not required. The `perf` lane row, if cited, MUST be
annotated `(non-blocking)`.

### §4.3. Pre-merge variant (optional polish)

The amendment intentionally does NOT require pre-merge CI matrix
green. The Main Branch FF-merge orchestration is the natural
serialization point; teams continue to develop in worktrees against
the equipped-host pytest gate (§1), and the CI matrix runs on every
push to `main`. The verification doc cites the post-merge run.

For higher-risk slices (e.g., new adapter cycles, install-script
changes), Main Branch MAY trigger a pre-merge `gh workflow run
ci.yml --ref <branch>` and route the dispatch's run number into the
verification doc instead of waiting for the post-merge run. This is
optional polish, not binding.

### What this amendment does NOT change

- **§1, §2, §3**: unchanged. Equipped-host SHOULD/MUST tiers and
  pre-handoff gate scope continue to apply as written.
- **2026-06-04 decision §1-§5**: unchanged. Adapter-cycle verdict-
  blocking gates remain intact.
- **§2.5 file-glob heuristic**: unchanged. The CI matrix criterion
  is orthogonal to the originating-team pre-handoff gate.

### Why §4 alongside §1, not instead of

§1 (equipped-host tier) and §4 (CI matrix criterion) measure
**different defect classes**:

- Equipped-host: catches "adapter execution path silently skips on
  toolchain-less host" — the defect class the 2026-06-04 decision
  originally addressed.
- CI matrix: catches "Linux-authored slice silently breaks Windows /
  cross-Python" — the defect class the 2026-06-09 fix triple
  empirically named.

Both layers are required for path/OS/Python-sensitive slices because
the failure modes do not overlap: an equipped Linux host with full
toolchain CAN still author code that breaks `Path.relative_to` on
cross-drive Windows. The amendment codifies what the empirical
record has shown for ~10 days.

### Effective date

Effective immediately upon merge of the commit landing this
amendment. The next slice to qualify under §4 — the
`workspace_relpath` utility promotion cycle dispatched 2026-06-19
(touches `pathlib.Path`/`os.path` plumbing across Coverage and
Localization) — MUST cite a `ci.yml` matrix run per §4.2 in its
verification doc.

### Supersedes / amends

- **Amends**: this decision (adds §4 / §4.1 / §4.2 / §4.3).
- **Closes**: Future-cycle queue item #7 from
  `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`.
- **Empirical grounding**: §"Load-bearing lessons" #1 of
  `agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`.
