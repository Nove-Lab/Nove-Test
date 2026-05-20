---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-21
slug: phase2-3-inspect-and-jest-coverage
---

# History: Phase 2 DoD #2+#3 closed + jest coverage real + the Windows-jest CI saga

The 2026-05-20 cycle dispatched 5 parallel slices, then grew a 4-slice
tail chasing a Windows defect that only surfaced post-merge. Final state:
**Phase 2 = 3/4 DoD**, jest coverage real on all platforms, CI **9/9
green** with jest a real gate on every cell.

## Cycle summary

| Slice | Commit | Outcome |
|---|---|---|
| Orchestration: `inspect` aggregated view | `8d1db6f` | passed — **Phase 2 DoD #3** |
| Run: jest `--coverage` wiring + Istanbul artifact | `91bfa29` | passed |
| Coverage: Istanbul-JSON parser (jest → CoverageFactSet) | `e01df3c` | passed |
| Memory: `entry_id == run_id` contract note | `5c65665` | doc-only |
| Release: CI Node.js cell | `68a4dcb` | RED on Windows post-merge |
| Release: ci-node-win-fallback (Windows guard) | `c350e5c` | 9/9 green (Windows skips jest) |
| Run: jest adapter Windows `npx` fix (`cmd /c`) | `0e9ab71` | proven on real Windows |
| Release: restore jest to all 9 cells | `bd7612d` | restore OK; 1 unit-test red |
| Run: OS-aware unit test fix | `16e4984` | **CI 9/9 green** (run `26173961489`) |

## What closed

- **Phase 2 DoD #2** (`coverage diff` structured deltas) — the work
  actually landed 2026-05-16 (`50c9170`); the tick was *missed* in that
  cycle's cleanup and is corrected this cycle. See learning #1.
- **Phase 2 DoD #3** (`inspect` Coverage section) — `8d1db6f`,
  Manual Test verdict `passed`.
- Phase 2 is now **3/4**. Only DoD #4 (50k-location perf) remains; its
  scoping draft is a ready-to-dispatch task
  (`tasks/coverage-team-2026-05-20-coverage-compare-perf.md`).

## Load-bearing learnings

### 1. A cleanup commit can *claim* a DoD tick without making it

The 2026-05-16 cleanup commit `00cc47a` said "Phase 2 #2" in its message
AND its history entry — but its `delivery-phasing.md` diff only ticked
Phase 0 bullets. DoD #2 was never actually flipped to `[x]`. Caught this
cycle by cross-checking the history claim against the live file.
**Cleanup rule reinforced: after editing `delivery-phasing.md`, re-read
the diff and confirm every claimed bullet is `[x]` before committing.**

### 2. Windows `CreateProcess` cannot run `.cmd` shims — only `cmd.exe` can

The jest adapter exec'd the bare name `npx`. On Windows two distinct
facts bit us: (a) `CreateProcess` only appends `.exe` to a bare name,
never `.cmd`/`.bat` — so bare `npx` is unresolvable even with Node.js
installed; (b) even the *full path* to `npx.cmd` cannot be exec'd
directly — `CreateProcess` (what `asyncio.create_subprocess_exec` uses)
cannot launch batch files at all (`WinError 193`). Fix: on Windows the
adapter launches `["cmd", "/c", "npx", "jest", ...]` — the bare `npx` is
handed to `cmd` so `cmd`'s `PATHEXT` resolution applies and `cmd /c`'s
leading-quote-strip rule is sidestepped. **Any future adapter that execs
an npm-ecosystem shim (`npm`, `npx`, `tsc`, `eslint`, …) on Windows
inherits this — `node.exe` is fine, the `.cmd` shims are not.**

### 3. The guard/exec consistency trap

The engine-readiness probe resolved `npx` via `shutil.which` (honours
`PATHEXT` → finds `npx.cmd` → "ready"), while the adapter exec'd the bare
name (fails). Result: a "ready but unrunnable" engine. **A readiness
check MUST resolve a binary the same way the runtime invokes it** — the
fix made the adapter reuse the resolved path.

### 4. OS-specific code branches need OS-aware unit tests

The `npx` fix added a Windows `cmd /c` argv branch but left its unit test
`test_argv_includes_target_expression` asserting `argv[0]` POSIX-only.
That test went red on every `windows-latest` cell from the moment the fix
merged — masked because the win-fallback guard was still on and observers
read "Windows red" as expected jest-skip noise. **When a slice adds an
OS-specific branch, its unit tests must assert OS-invariant parts (or
branch on platform), and Windows-cell CI must be checked per-cell — not
"is the matrix green".**

### 5. Windows defects are invisible until a real `windows-latest` runner

Manual Test's box has no Node; the engine teams' dev boxes are Linux. All
three Windows issues this cycle (`npx` exec, unit-test assertion, a
`charmap` decode warning) were invisible until post-merge GHA on a real
Windows runner. The cycle's entire 4-slice tail was Windows-defect
chasing. There is no substitute for observing the actual `windows-latest`
cell conclusions; treat "matrix green" claims skeptically until per-cell
results are checked. (Manual Test's standing recommendation to provision
Node on its box would have caught the npx bug one stage earlier.)

### 6. jest coverage is real now — `aggregate` granularity

`novetest run --coverage` on a jest workspace now produces a real
`CoverageFactSet` (Istanbul `coverage-final.json` → parser dispatched on
`engine_name == "jest"`). jest's default `--coverage` merges per-run, so
the granularity is `aggregate` (not `per-test` like pytest). Manual Test
confirmed the jest `aggregate` path does not bleed into pytest's
`per-test` path. Verified end-to-end on real Linux/macOS **and** Windows
CI cells.

## inspect aggregated view — notes for Phase 3+

`novetest inspect <run_id>` is now a real aggregated single-run view.
Invariants confirmed by Manual Test (`passed`):
- `data.sub_reports` always carries exactly 4 keys (`coverage`,
  `regression`, `localization`, `replay`); only `coverage` is dynamic
  today — Phase 3/4/5 each just flip their key to `available`.
- The Coverage section reuses the frozen `coverage_outcome` block verbatim.
- A tombstoned run stays inspectable; `run_summary.status` becomes
  `"tombstoned"` while `summary_counts` retains the real test counts —
  i.e. `status` is a lifecycle discriminator, not purely a test verdict.

PM may freeze the `InspectView` container shape as a `decisions/` entry
when Phase 3's `compare` first extends it; not urgent.

## Open follow-ups (PM queue)

1. **Phase 2 DoD #4** — 50k-location `coverage diff` perf (NFR-COV-002).
   Ready-to-dispatch task: `tasks/coverage-team-2026-05-20-coverage-compare-perf.md`
   (scoped by a `performance-engineer` review; `tests/perf/` placement
   avoids a `pyproject.toml` marker edit).
2. **jest adapter `charmap` UnicodeDecodeError** on Windows subprocess
   stream reading — pin `encoding="utf-8"`. Non-blocking warning today;
   future Run robustness slice.
3. **Release CI housekeeping** (two GHA warnings, non-blocking):
   `astral-sh/setup-uv@v3` `python-version` input deprecated; `Node.js 20`
   GHA actions deprecation (forced to Node 24 on 2026-06-02).

## Process notes

- Cycle tail sprawl: 5 → 9 slices. Each tail slice was small and
  necessary; the CEO chose "clean close" over deferring the Windows
  defect — the cycle closes with zero CI-gating defects and jest a real
  gate on 9/9.
- Worktrees were cleaned by Main Branch this cycle — no PM escalation
  needed (an improvement over the prior two cycles).
- No new `decisions/` this cycle; the frozen `coverage_outcome` /
  `coverage_delta` / `coverage-facts-layout` contracts were reused
  exactly as designed by the `inspect` and jest-coverage slices.
