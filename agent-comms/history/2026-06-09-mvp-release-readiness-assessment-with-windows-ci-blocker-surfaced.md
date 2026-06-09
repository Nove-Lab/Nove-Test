---
from: novetest-pm-team
to: all
type: history
created: 2026-06-09
slug: mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced
related:
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
---

# MVP Release-Readiness Assessment — negative sign-off is the deliverable; Windows CI red 9-day chronic surfaced; 3-team parallel triple dispatched

## Cycle outcome

**Comms-only assessment cycle** (zero `src/` or `tests/` touched).
Release team's negative sign-off is the cycle's deliverable; Manual
Test verified the integrity of the negative judgment, not a positive
release-ready statement. Verdict: **PASSED** (the framing-aware
verdict — the sign-off is well-grounded, internally consistent, and
empirically substantiated).

| Slice | Team | Verdict | Functional commit | Headline |
|---|---|---|---|---|
| MVP release-readiness assessment | Release | PASSED (negative sign-off) | `91ef953` | Comms-only: Phase 1 assessment matrix (6 surfaces) + Phase 2 routed-out (blocker outside writable scope) + Phase 3 empirical sign-off "NOT release-ready as of `bd4d300`" — single blocker (Windows CI red 9-day chronic since `53f7920` 2026-06-01) routed to PM via question; release pipeline (PyApp binary 3-cell + install.sh E2E + SHA-256 verify) empirically GREEN at HEAD via `release-test.yml` run `27176266868`. |

Cycle commits in chronological order: `388f0f0` (meta-decision —
equip-and-exercise default posture) → `bd4d300` (PM brief — was
already in main from previous session) → `91ef953` (Main Branch FF-
merge of Release worktree: handoff + question + WORKLOG + INDEX) →
`486c1df` (Main Branch verification doc) → this cycle-close commit.

## Track-status update — MVP path remaining

| Track | Status | Notes |
|---|---|---|
| C envelope-warnings-projection | ✅ closed 2026-06-07 | |
| D dotnet-cobertura-derive | ✅ closed 2026-06-07 | |
| A — B1 critical polish | ✅ closed 2026-06-08 | |
| B — B2 UX normalization | ✅ closed 2026-06-08 | (Linux/macOS verified; **Windows regression surfaced this cycle** — see §"Load-bearing lessons" #2) |
| **Release readiness assessment** | ✅ **CLOSED THIS CYCLE** | Negative sign-off; single blocker routed |
| **Windows CI matrix fix** | 🔴 **NEW BLOCKER — 3-team parallel triple dispatched** | Coverage + Localization + Run; ~3-5h aggregate effort |
| Release team re-dispatch | parked | Re-activates after Windows fix triple lands + CI matrix all-green |
| v1 metadata-channel sunset | parked at post-MVP cleanup | |

**MVP completion path**: Windows fix triple (NEW) → Release team re-
dispatch (positive sign-off) → MVP release. The v1 metadata sunset
remains post-MVP cleanup territory.

## Load-bearing lessons

### 1. Negative sign-off as a valid cycle deliverable

The Release team's task brief explicitly allowed Phase 2 (critical-
path fix) to be **routed out** when the fix surface falls outside
the team's writable scope. The team executed exactly that: their
charter forbids `src/novetest/**` and `tests/{unit,integration}/**`
(where all 20 failures live), so they filed an open question rather
than attempting a charter-violating fix.

The handoff's TL;DR captures the pattern:

> "Phase 2 thus completed by **routing rather than fixing** — which
> is the charter-compliant action for this surface."

Manual Test's verdict framing was the load-bearing complement: the
slice's deliverable IS the negative sign-off plus the routing, not
a fixed product. **PASSED ≠ "MVP release-ready"**; PASSED means
"the negative judgment is well-grounded."

Pattern for future cycles: when a task brief is assessment-shaped
(diagnose + classify + route), the verdict criterion is sign-off
integrity, not the underlying product state. Briefs that explicitly
authorize routing as a Phase-2 path produce cleanly-resolvable
cycles even when the underlying state is negative.

### 2. **B2 cycle's "PASSED" was Linux/macOS only — Windows regression silently added**

The cycle that closed 2026-06-08 ("B2 UX-normalize parallel triple")
reported PASSED across all three slices on the equipped host
(`1233 passed / 0 failed / 0 skipped in 76.63s`). That host was
Linux. CI matrix had been red on Windows for 7 days at the time of
that cycle's close commit, and the Localization B2-2 slice's
`_normalize_to_workspace_relative` helper used `Path.relative_to`
in a Windows-incompatible way — adding **4 new Windows failures**
to the existing 16 red-cell count.

The B2 cycle's history (`2026-06-08-b2-ux-normalize-parallel-triple-
coverage-localization-run.md` §"Load-bearing lessons" #4) noted
"outside-workspace deliberately absolute" as an intentional policy
asymmetry. The same slice's WORKLOG entry §"Gotcha #2" pinned
"`Path.resolve()` deliberately NOT called on either side" as a
cross-platform reasoning, but the reasoning was missing the
Windows-drive case entirely.

**The cycle-close history was substantively correct for Linux and
macOS. It was incorrect for Windows.** No host in the verification
flow ran Windows; no automated gate caught the regression at merge
time (it was already a chronic red state, so the new failures
blended in).

This is the **recurring defect class** the Release team called out:

> "Slices authored on Linux without Windows pre-flight are the
> recurring defect class; addressable by either equip-and-exercise
> extending to Windows OR by pre-merge `gh workflow run ci.yml` on
> the worktree branch."

The meta-decision committed earlier this cycle (`388f0f0`
"equip-and-exercise as default verification posture") does NOT
mandate Windows verification. Its "equipped host" semantics
inherits the Linux-or-macOS scope from `scripts/dev-host-setup.md`.
This gap is now load-bearing for future cycles — a follow-up
amendment to either the meta-decision OR `scripts/dev-host-setup.md`
should pin "Windows pre-merge CI check" as an explicit verification
gate for any slice that touches path-handling code.

PM disposition (see §"PM dispositions" #2): the immediate Windows
fix triple cycle will include "Windows CI cell GREEN" as a verdict
criterion in the verification docs, treating the CI matrix turn-
green as the binding evidence. A formal meta-decision amendment is
deferred until the triple lands + we have one cycle of empirical
data on the new gate semantics.

### 3. CI matrix as the cross-OS verification surface (vs equipped host)

The 2026-06-08 meta-decision's "equipped host" tier explicitly
operationalizes Linux/macOS toolchain installation. Windows is
structurally outside that tier because:

- `scripts/dev-host-setup.md` ships POSIX-shell recipes only
- The CEO's two equipped hosts (per institutional findings
  `manual-test-team-2026-06-04-host-equip.md` + `2026-06-06-host-
  equip.md`) are both Linux
- Manual Test runs verification on those hosts

CI matrix (`ci.yml`, 3 OS × 3 Python = 9 cells) is therefore the
**de facto** cross-OS verification surface, and it's been
asymmetrically broken for 9 days without anyone treating it as a
blocker. The Release readiness cycle made it explicit: CI matrix
green is the binding contract for Phase 0 DoD #1, and the contract
has been silently violated.

**Pattern for the Windows fix triple**: each slice's verification
doc MUST cite a specific `ci.yml` run on the post-fix HEAD with
all 9 cells green. The CI matrix becomes a verdict-blocking gate
for these cycles, mirroring how `release-test.yml` is a verdict-
blocking gate for adapter cycles per `2026-06-04-equip-and-exercise-
for-adapter-cycles.md` §1.

### 4. Pre-existing release pipeline survived the codebase-doubling

5月 16일 closure → 2026-06-09 head (`bd4d300`): the codebase grew
from 1 adapter (pytest) to 6 (pytest + jest + junit + gotest +
cargo + dotnet); 5 Coverage parsers; full Phase 3 + 4 + 5 + 6
engines; vendored JUnit Console Launcher JAR (+2.7 MB); production
dep `numpy` added 2026-05-28. The 5/16 release pipeline
(`release-test.yml`) is unchanged structurally and **still green
at HEAD on first invocation** — `release-test.yml` run
`27176266868` on `bd4d300`:

- `linux-x86_64` 1m42s (5/16 was 3m4s total for 3 cells — actually
  faster now, likely from action-version major bumps + caching
  improvements)
- `linux-aarch64` 1m22s
- `macos-universal2` 2m51s (lipo-fused, both `aarch64-apple-darwin`
  + `x86_64-apple-darwin` slices)
- All 3 with `.sha256` sidecars
- `install-script-e2e` job 15s: clean install + idempotent re-
  install both returned valid `novetest/v1` envelope; SHA-256
  verified live = `d226d9dc0ba18d1aa7a80934f37023668089767291547f7083265e65c1b80c29`

This is the **load-bearing positive** from the assessment: the
release pipeline was built defensively enough in Phase 0 that 4
weeks of engine work + a vendored JAR + a new production dep + 5
action-version major bumps didn't break it. The negative sign-off
is about test-content drift, not pipeline rot.

### 5. THIRD_PARTY_NOTICES.txt is partial-but-blocker-clear

Decision `2026-06-03-junit-console-launcher-vendor.md` §3 mandate:
ship NOTICES file with EPL 2.0 attribution at the vendored-dir
location. **Verified empirically met**:
`src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`
exists, ships in wheel via `[tool.hatch.build.targets.wheel.force-
include]`, covers JUnit Console Launcher with artifact coords +
license URL + source URL + pinned SHA-256
`b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`
(byte-identical to the JAR per `sha256sum` verification).

**What's missing (deferred as non-blocker)**: `cyclopts` (Apache
2.0) + `numpy` (BSD-3-Clause) attribution. Both are pip-fetched at
first-run, not byte-bundled. Strict legal interpretation says
binary-embedded blobs require attribution; pip-fetched deps don't
(user's pip-cache surfaces them). For extra-careful v1, fold into
a Tier-2 NOTICES surface in a post-MVP polish cycle.

**Also not done (Orchestration territory)**: `novetest --licenses`
CLI surface mandated by decision §3 ("MUST surface this notice
file's contents") is not yet wired. Not enforced by any current
test; polish for v1.

These are the non-blocker NOTICES items in §"Future-cycle backlog"
below.

### 6. Equip-and-exercise meta-decision did its job — narrative coherence

The meta-decision `388f0f0` (committed early this cycle, before
Manual Test ran) immediately landed its first explicit application:
the Release readiness Manual Test verification ran on the equipped
host (the 7th consecutive validation pinned in the decision's
context). The Release team handoff §"Follow-up cycle candidates"
references the meta-decision by name when discussing §2.5
interaction with the upcoming Windows fix cycles:

> "PM's brand-new (untracked-in-this-worktree) decision
> `2026-06-08-equip-and-exercise-default-verification-posture.md`
> likely interacts with §2.5 equip-and-exercise gating for these
> cycles — fold in when shaping the briefs."

The PM dispositions §"#2" below folds in that interaction by
elevating the CI matrix green-state to a verdict criterion for the
Windows fix triple — the meta-decision's SHOULD tier composes
naturally with the new gate.

## PM dispositions this cycle (cycle-close ratifications)

### 1. Phase 0 DoD #1 — Option 2 (stale-marker) chosen

Of the three options Release team routed in the question file:
- (1) Un-tick the bullet — cleanest but disrespects the 2026-05-16
  closure work
- (2) **Stale-marker** — preserves 2026-05-16 closure history while
  flagging the regression
- (3) Re-scope DoD #1 to Linux+macOS only — weakens the contract +
  requires foundations §7 amendment

**Chosen**: Option 2. `delivery-phasing.md` Phase 0 DoD #1 now
carries an inline stale-marker block referencing this history file
+ the empirical re-validation evidence + the post-fix re-tick
criterion. The 2026-05-16 closure narrative is preserved as
"closed against 2026-05-16 head; now empirically stale."

### 2. Question routing — parallel triple dispatched this cycle-close

Release team's question proposed a parallel triple matching the
2026-06-08 B2 cycle shape. PM ratifies that shape — the three fix
surfaces are mutually disjoint (`src/novetest/coverage/**` ↔
`src/novetest/localization/**` ↔ `tests/{unit,integration}/run/**`).

**Three briefs dispatched in this cycle-close commit family**:
- `tasks/coverage-team-2026-06-09-windows-parser-fixes.md`
- `tasks/localization-team-2026-06-09-windows-path-normalization-fix.md`
- `tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`

**New verdict criterion**: each slice's verification doc MUST cite
a `ci.yml` run on the post-fix HEAD with all 9 cells green. This
operationalizes §"Load-bearing lessons" #3 (CI matrix as cross-OS
verification surface) for the immediate cycle. A formal meta-
decision amendment is deferred until we have empirical data on the
new gate.

### 3. THIRD_PARTY_NOTICES.txt — decision §3 mandate empirically met; pip-dep attribution + `novetest --licenses` CLI deferred

The vendored JUnit Console Launcher EPL 2.0 attribution at
`src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` meets
the decision §3 binding. Pip-dep attribution (`cyclopts`, `numpy`)
is non-mandatory under strict legal reading of "byte-bundled"; PM
ratifies the current state as sufficient for MVP. `novetest
--licenses` CLI surface is a post-MVP polish cycle item.

### 4. `numpy` first-run latency observation — non-blocker measurement

`numpy` was added 2026-05-28 as a production dep for SBFL hot-path
vectorization (Phase 4 entry). PyApp pulls it at first-run; the
foundations §7 figure ("5-15s while CPython downloads") may now
skew higher. **Not release-blocking** — no functional regression;
just UX. PM defers measurement to a non-blocker polish cycle (post-
MVP) unless user feedback signals it's a real problem.

### 5. Release team re-dispatch sequence pinned

After the Windows fix triple lands + CI matrix all-green is
verified, **Release team re-activates** for a Phase-3-only sign-off
pass:
- Re-run `release-test.yml` on the post-fix HEAD
- Verify CI matrix all-green on the post-fix HEAD via fresh `gh
  run` query
- Update the (now-deleted by this cycle) handoff's sign-off
  statement to "**MVP release-ready as of `<post-fix-commit>`**"
- Re-tick Phase 0 DoD #1 (stale-marker → clean check) in the same
  Release team handoff that issues the positive sign-off

The PM brief for that re-dispatch will be filed when the Windows
fix triple closes; not pre-emptively queued.

## Cycle-close bookkeeping summary

Transient files retired in this cycle's close commit:
- `tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md`
- `handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`
- `verifications/2026-06-09-mvp-release-readiness-assessment.md`
- `findings/manual-test-team-2026-06-09-mvp-release-readiness-assessment.md`
- `questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md`
  (PM disposition recorded in §"PM dispositions" #2; routed via three
  new task briefs in same commit family)

Retained:
- `findings/manual-test-team-2026-06-04-host-equip.md` (institutional)
- `findings/manual-test-team-2026-06-06-host-equip.md` (institutional)
- This history file
- Three new task briefs (Windows fix triple — dispatched in companion
  commit immediately after this cycle-close)

`design/implementation-plan/delivery-phasing.md` Phase 0 DoD #1 was
amended in this cycle-close commit (stale-marker per PM disposition
#1). All other Phase DoD remains 100% checked; only Phase 7 (post-
MVP MCP) carries the original 2 unchecked bullets.

## Future-cycle backlog (recorded; NOT auto-queued)

### Blocker-clearing (dispatched immediately)

1. **Coverage Windows parser fixes** — 3 src + 3 tests, ~1-2h
2. **Localization Windows path normalization fix** — 1 src + 2 tests, ~1h
3. **Run JUnit Windows OS-gate test fix** — 0 src + 4 tests (test-only), ~1-2h

### Post-Windows-fix (queued)

4. **Release team re-dispatch** — Phase 3 sign-off pass after CI
   matrix turns green. ~30min to 1h.

### Non-blocker polish (post-MVP acceptable)

5. **Equip-and-exercise meta-decision Windows amendment** — formalize
   "Windows CI cell green" as a verdict criterion for path-handling
   slices. Defer until empirical data from this cycle's Windows fix
   triple validates the gate semantics.
6. **THIRD_PARTY_NOTICES expansion for pip-deps** (`cyclopts`,
   `numpy`) — Tier-2 NOTICES surface or sibling file. Release team.
7. **`novetest --licenses` CLI surface** — decision
   `2026-06-03-junit-console-launcher-vendor.md` §3 mandate.
   Orchestration team.
8. **First-run latency bench post-`numpy`** — measure cold-start
   `novetest --version` time, document in foundations §7 or amend
   the 5-15s figure. Release team.
9. **Windows install.ps1 + binary pipeline** (Open Q #16) — deferred
   per `foundations.md` §7. Release team, post-MVP per existing
   roadmap.
10. **v1 metadata-channel sunset** — still parked at post-MVP cleanup
    per `2026-06-06-adapter-warning-surface-v1-metadata-channel.md`.
