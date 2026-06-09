---
from: novetest-pm-team
to: all
type: history
created: 2026-06-09
slug: windows-ci-fix-triple-coverage-localization-run
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
---

# Windows CI fix triple — Coverage parsers + Localization B2-2 regression + Run JUnit OS-gate (all PASSED + 10/10 ci.yml GREEN)

## Cycle outcome

**Second 3-team parallel cycle** in project history (after 2026-06-08
B2 UX-normalization). All three slices verified PASSED on the
equipped host; **`ci.yml` run `27187459586` returned 10/10 GREEN
matrix** — the first all-green CI matrix on `main` since 2026-05-31,
breaking a 9-day Windows red chronic state.

| Slice | Team | Verdict | Functional commit | Headline |
|---|---|---|---|---|
| Coverage Windows parser fixes (4 tests) | Coverage | PASSED | `4110645` | Scenario A pattern (`os.path.relpath` + `.as_posix()`) extended to cobertura/derive_xunit; cross-drive `Path.relative_to` ValueError safe. LCOV warning text POSIX-separator normalized at emit |
| Localization Windows path normalization fix (4 tests) | Localization | PASSED | `edb78f8` | `_normalize_to_workspace_relative` + outside-workspace check both cross-drive safe; B2-2 outside-workspace asymmetry policy preserved (failure_proximity stdlib frames remain absolute) |
| Run JUnit Windows OS-gate test fix (12 tests, test-only) | Run | PASSED | `a6ebd91` | 5 test files gained `pytestmark = pytest.mark.skipif` per decision `2026-06-03-junit-console-launcher-vendor.md` §R5; 1 subprocess test gained `encoding="utf-8"` |

Cycle commits in chronological order (post `230420c` cycle-close +
dispatch commit from yesterday): `4110645` (Coverage fix) → `edb78f8`
(Localization fix) → `c5c85de` (Localization handoff) → `a6ebd91` (Run
fix) → `c9af08c` (Coverage verification) → `c1424bd` (Localization
verification) → `871a278` (Run verification) → this cycle-close
commit.

## Track-status update — MVP path remaining

| Track | Status | Notes |
|---|---|---|
| C envelope-warnings-projection | ✅ closed 2026-06-07 | |
| D dotnet-cobertura-derive | ✅ closed 2026-06-07 | |
| A — B1 critical polish | ✅ closed 2026-06-08 | |
| B — B2 UX normalization | ✅ closed 2026-06-08 (Linux/macOS) + Windows regression fixed THIS CYCLE | |
| Release readiness assessment | ✅ closed 2026-06-09 (negative sign-off) | |
| **Windows CI matrix fix** | ✅ **CLOSED THIS CYCLE** | 10/10 GREEN; 9-day chronic ended |
| Release team re-dispatch | **QUEUED (next cycle)** | Phase-3-only sign-off pass; expected positive |
| v1 metadata-channel sunset | parked at post-MVP cleanup | |

**Single remaining cycle to MVP release-ready**: Release team re-
dispatch for the positive sign-off pass. The cycle's brief is filed
when PM is dispatched next; the work itself is constrained (re-run
`release-test.yml` + verify ci.yml all-green at HEAD + update the
handoff's sign-off to "MVP release-ready as of `<commit>`").

## Load-bearing lessons

### 1. CI matrix as verdict-blocking gate — first explicit empirical validation

The yesterday-dispatched briefs (this cycle's three slices) introduced
a **new verdict criterion**: each slice's verification doc MUST cite
a specific `ci.yml` run on the post-fix HEAD with all matrix cells
green. This was an extension of the meta-decision `2026-06-08-equip-
and-exercise-default-verification-posture.md` §1 SHOULD tier into
**cross-OS empirical evidence** territory.

Today the gate proved its value: all three Manual Test findings cite
the same `ci.yml` run `27187459586` (on `871a278`) as the binding
evidence that Windows × 3 Python = 3 cells turned green. The previous
14 days of `main` cycle-close commits each carried `pytest -q` Linux
green statements without the corresponding CI matrix check — and that
missing check is precisely what let the Windows red drift for 9 days
without any cycle treating it as a blocker.

**Pattern for future cycles that touch path-handling, OS-gated, or
cross-platform code**: verification docs MUST cite a `ci.yml` run
on the merged HEAD. Linux green is necessary but no longer
sufficient. The pattern composes cleanly with the meta-decision's
"equipped host" tier — Linux/macOS = equipped host evidence + Windows
+ cross-Python = CI matrix evidence. Future PM briefs should consider
adding "Canonical CI matrix run citation" as a standard subsection
when the slice's surface intersects path / OS / Python-version
sensitivity.

### 2. 3-team parallel cycle pattern matured into routine

This was the second 3-team parallel cycle (after 2026-06-08 B2). All
three slices closed cleanly with zero file-ownership conflict;
alphabetical FF-merge order (Coverage → Localization → Run) held;
all three Manual Test findings cite the same equipped-host pytest
gate (`mypy clean 92 files`; `1247 passed / 0 failed / 0 skipped`)
and the same `ci.yml` run number. The pattern is now load-bearing
operational dogma.

**Operational note** for future PM: 3-team parallel is no longer
"first attempt" territory; it is the default shape when three or
more disjoint surfaces need work and ownership is provably non-
overlapping. Smaller cycles (2 teams, 1 team) remain valid; the
upper bound (4+ teams) is still untested and warrants caution.

### 3. B2-2 Localization regression repair — the "Linux-authored slice silently breaks Windows" defect class is now empirically named

Yesterday's Release readiness assessment surfaced the broader pattern
in §"Load-bearing lessons" #2 of `2026-06-09-mvp-release-readiness-
assessment-with-windows-ci-blocker-surfaced.md`:

> "Slices authored on Linux without Windows pre-flight are the
> recurring defect class."

Today's Localization slice (`edb78f8`) is the *first explicit repair*
of that class. The B2-2 helper `_normalize_to_workspace_relative`
landed 2026-06-08 with the comment (per WORKLOG §"Gotcha #2"):

> "Path.resolve() deliberately NOT called on either side ... a future
> cycle adds resolve() if Manual Test surfaces a real-host symlink
> scenario where the absolute-fallthrough confuses operators."

The "future cycle" turned out to be 23 hours later, not via Manual
Test but via Windows CI; and the root cause was not `.resolve()` but
`Path.relative_to`'s cross-drive ValueError + drive-prefix loss. The
fix shape (`os.path.relpath` + `.as_posix()`) matches Coverage's
scenario A pattern verbatim — establishing a **single canonical
cross-OS path-handling idiom** across both engines.

**Pattern to internalize**: when a Linux-authored slice's WORKLOG
flags "future cycle if Manual Test surfaces X", read that as "future
cycle when CI surfaces X (likely from Windows)" instead. The
operator surfacing path defects is the CI matrix, not the human
operator on the equipped Linux host.

### 4. Scenario A pattern is now the cross-OS path-handling idiom

`decisions/2026-05-15-coverage-facts-json-layout.md` "Amendment
2026-06-08" formally pinned scenario A for Coverage:

```python
relpath = Path(os.path.relpath(file_path, workspace_root)).as_posix()
```

Today's Localization slice adopts the same exact shape (via
`os.path.relpath` fallback after a `Path.relative_to` try/except),
producing functionally identical envelope output. This makes the
scenario A idiom the project-wide canonical pattern for path-to-
workspace-relative normalization.

**Operational implication**: any future slice that needs to express
a file path relative to workspace root MUST use this pattern (or
explicitly justify a deviation in the slice's handoff). Future code
review SHOULD reject `Path.relative_to(workspace_root)` calls that
do not have a `try/except ValueError → os.path.relpath` fallback +
`.as_posix()` normalization — cross-OS safety is non-negotiable.

A future formalization candidate: add a `path_utils.workspace_relpath(
file_path, workspace_root) -> Path` utility under `src/novetest/utils/`
that centralizes the scenario A pattern, so individual engines call
the utility rather than duplicating the try/except idiom. Not
required for MVP; queued as a post-MVP polish item.

### 5. Test-only fix is a charter-compliant fix shape

The Run slice (`a6ebd91`) modified `tests/` only (zero `src/`).
JUnit adapter's Windows OS gate per decision `2026-06-03-junit-
console-launcher-vendor.md` §R5 was already correct; the 12 failing
tests reckoned with that gate incorrectly. Fix shape: 5 test files
gained module-level `pytestmark = pytest.mark.skipif`, 1 subprocess
test gained `encoding="utf-8"`. Zero adapter src touched.

**Pattern**: when CI surfaces failures that production code handles
correctly (per a pinned decision) but tests do not reckon with, the
fix surface is `tests/` only. This composes cleanly with §2.5
equip-and-exercise — test-only changes do not trigger the file-glob
heuristic since they do not modify `<engine>_adapter.py`. The Run
slice ran on a general host per §2.5 non-activation; the cycle's
new CI matrix verdict criterion provided the cross-OS evidence that
the equip-and-exercise tier did not.

### 6. CEO flow correction

CEO sequenced this cycle's dispatches in the prior format (three
teams → straight back to PM, skipping Main Branch + Manual Test).
PM caught the gap mid-cycle ("표준 흐름은 그게 아니야") and
re-routed through Main Branch first, then Manual Test, then PM.
Result: no rework, no fragmented merge, no missing verification —
the cycle closed cleanly within the standard 4-stage flow.

**Operational note**: the parallel-pair-and-triple flow's "team
worktree → Main Branch FF-merge → Manual Test → PM" sequence is a
constant across all cycle shapes (1 team, 2 teams, 3 teams). Future
sessions should not skip Main Branch + Manual Test when multiple
worktrees are involved — the FF-merge orchestration + matrix
verification are load-bearing for cycle integrity, especially when
the new CI matrix verdict criterion is in effect.

## PM dispositions this cycle (cycle-close ratifications)

### 1. Phase 0 DoD #1 — re-closed via inline marker

The yesterday-introduced stale-marker on `delivery-phasing.md` Phase
0 DoD #1 is **replaced with a re-closed marker** in this commit:

> "*(re-opened 2026-06-09 via Release readiness assessment — Windows
> × 3 Python cells chronic red since 2026-06-01 (20 failures: 5
> Coverage + 4 Localization B2-2 regression + 11 Run/JUnit); re-
> closed 2026-06-09 via Windows-CI fix triple `871a278` (Coverage +
> Localization + Run parallel slices) — `ci.yml` run `27187459586`
> 10/10 GREEN, first all-green matrix on `main` since 2026-05-31.)*"

The bullet's `[x]` mark is restored to its 2026-05-16 closure state;
the inline marker preserves the full audit trail (re-open reason +
re-close evidence + both history file references). This is the
**third application of the in-place amendment pattern** (after
`2026-05-15-coverage-facts-json-layout.md` §"Amendment 2026-06-08"
and yesterday's stale-marker insertion) — the pattern is now mature.

### 2. CI matrix verdict criterion ratified as default for path/OS/Python-sensitive slices

The verdict criterion introduced in yesterday's briefs has empirical
validation today. PM ratifies the criterion as the **default
verification expectation** for any future slice whose surface
intersects path-handling, OS-gating, or Python-version sensitivity.
The meta-decision `2026-06-08-equip-and-exercise-default-verification-
posture.md` will receive a follow-up amendment when the next path/OS
slice arrives — or sooner if PM decides a standalone decision is
warranted. Not blocking; queued as a load-bearing-but-deferred polish
item.

### 3. Scenario A pattern as cross-OS path-handling idiom

PM ratifies the scenario A pattern (`os.path.relpath` fallback +
`.as_posix()`) as the project-wide canonical idiom for workspace-
relative path normalization. Both Coverage (per
`2026-05-15-coverage-facts-json-layout.md` "Amendment 2026-06-08")
and Localization (per today's `edb78f8`) implement this shape;
future engines must do the same. A future `src/novetest/utils/path_
utils.py` consolidation is queued as post-MVP polish.

### 4. Linux-authored-silently-breaks-Windows defect class is empirically named

§"Load-bearing lessons" #3 above names the defect class explicitly.
PM ratifies the naming. The CI matrix verdict criterion (PM
disposition #2 above) is the operational counter-measure; no
separate decision is needed since the criterion already addresses
the class structurally.

### 5. Release team re-dispatch brief deferred to next session

Per the load-bearing-lessons sequencing (cycle-close → next session
PM brief drafting), PM declines to pre-write the Release team re-
dispatch brief inside this cycle-close commit. The brief is filed
when CEO opens the next session and confirms scope. Estimated cycle
shape: ~30min wall time; single-team; scope = (a) re-run release-
test.yml on the post-Windows-fix HEAD, (b) verify ci.yml all-green at
HEAD via fresh gh run query, (c) update handoff's sign-off statement
to "MVP release-ready as of `<commit>`", (d) re-validate the
THIRD_PARTY_NOTICES.txt vendored JAR SHA-256 and decision §3 mandate.
No new policy decisions in that cycle — pure empirical re-validation.

## Cycle-close bookkeeping summary

Transient files retired in this cycle's close commit:
- `tasks/coverage-team-2026-06-09-windows-parser-fixes.md`
- `tasks/localization-team-2026-06-09-windows-path-normalization-fix.md`
- `tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`
- `handoffs/coverage-team-2026-06-09-windows-parser-fixes.md`
- `handoffs/localization-team-2026-06-09-windows-path-normalization-fix.md`
- `handoffs/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`
- `verifications/2026-06-09-coverage-windows-parser-fixes.md`
- `verifications/2026-06-09-localization-windows-path-normalization-fix.md`
- `verifications/2026-06-09-run-junit-windows-os-gate-test-fix.md`
- `findings/manual-test-team-2026-06-09-coverage-windows-parser-fixes.md`
- `findings/manual-test-team-2026-06-09-localization-windows-path-normalization-fix.md`
- `findings/manual-test-team-2026-06-09-run-junit-windows-os-gate-test-fix.md`

Retained:
- `findings/manual-test-team-2026-06-04-host-equip.md` (institutional)
- `findings/manual-test-team-2026-06-06-host-equip.md` (institutional)
- This history file
- Yesterday's release-readiness history file (foundational context for
  this cycle's narrative)

`design/implementation-plan/delivery-phasing.md` Phase 0 DoD #1 was
amended in this cycle-close commit (re-closed marker per PM
disposition #1). All other Phase DoD remains 100% checked; only
Phase 7 (post-MVP MCP) carries the original 2 unchecked bullets.

## Future-cycle backlog (recorded; NOT auto-queued)

### Immediate (single cycle to MVP release-ready)

1. **Release team re-dispatch** — Phase-3-only sign-off pass. ~30
   min. PM brief filed when next session opens.

### Post-MVP polish (queued)

2. **`src/novetest/utils/path_utils.py::workspace_relpath` utility** —
   centralize scenario A pattern (see §"Load-bearing lessons" #4 +
   PM disposition #3). Cross-team cleanup; ~1-2h scope.
3. **Meta-decision amendment for CI matrix verdict criterion** — when
   the next path/OS/Python-sensitive slice arrives, fold the criterion
   into the equip-and-exercise meta-decision as an explicit clause
   alongside the SHOULD/MUST tiers (see PM disposition #2).
4. **THIRD_PARTY_NOTICES expansion for pip-deps** (`cyclopts`,
   `numpy`) — Tier-2 NOTICES surface. Release team. From yesterday's
   release-readiness history.
5. **`novetest --licenses` CLI surface** — decision
   `2026-06-03-junit-console-launcher-vendor.md` §3 mandate.
   Orchestration team.
6. **First-run latency bench post-`numpy`** — UX measurement. Release
   team.
7. **Windows install.ps1 + binary pipeline** (Open Q #16) — post-MVP
   per `foundations.md` §7.
8. **v1 metadata-channel sunset** — post-MVP cleanup per
   `2026-06-06-adapter-warning-surface-v1-metadata-channel.md`.
9. **CI workflow polish — pre-merge `gh workflow run ci.yml` for
   Linux-authored slices** — as a procedural counter-measure to the
   "Linux-authored silently breaks Windows" defect class beyond just
   the verification-time CI matrix verdict. Optional process polish;
   not required since the verdict criterion already structurally
   addresses the class.
