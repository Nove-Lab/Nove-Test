---
from: novetest-pm-team
to: all
type: history
created: 2026-06-19
slug: workspace-relpath-utility-promotion
cycle_window: 2026-06-19 (Wave 1 of 3 parallel cycles, FF-merge order Coverage → Release → Run)
related:
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md  # Future-cycle queue #6 closed
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #6 source
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md  # §4 amendment 2026-06-19 first explicit application
---

# workspace_relpath utility promotion (Coverage + Localization cross-over)

## TL;DR

Coverage team lifted `src/novetest/coverage/_paths.py` (Coverage-internal
cross-OS path-relativization helpers introduced 2026-06-09 to fix the
9-day Windows chronic red) to the project-wide
`src/novetest/utils/path_utils.py`, and migrated Localization's
`_normalize_to_workspace_relative` inline duplicate to delegate to the
shared utility. Pure refactor; envelope output byte-equivalent.

**Closes Future-cycle queue item #6.**

**First explicit application of the §4 CI matrix verdict criterion** —
ci.yml run `27831589304` 10/10 GREEN at SHA `167a261` empirically proved
the relocated cross-drive Windows fallback wiring still works on all 3
Windows-cell Python versions.

Manual Test verdict: **PASSED** — 8 scenarios + 6 critical edges, zero
blocking defects.

## Cycle arc (Wave 1, parallel with Release NOTICES+bench bundle and Run v1-metadata-sunset)

| Event | Commit |
|---|---|
| PM dispatch prep (parallel cohort + §7 decision amendment) | `42f6a32` |
| Coverage code+WORKLOG+handoff | `9c5abbf` |
| Main Branch FF-merge + verification routing | `0cdc3dc` |
| Manual Test PASSED findings filed | _(at cycle close)_ |
| PM cycle-close (this entry + transient cleanup) | _(this commit)_ |

## What landed

### Source changes (9 files)

| File | Change | LOC |
|---|---|---|
| `src/novetest/utils/path_utils.py` | NEW | +155 |
| `src/novetest/utils/__init__.py` | re-exports 3 names | +19 |
| `src/novetest/coverage/_paths.py` | DELETED (no re-export shim; 4 callsites < threshold) | −112 |
| `src/novetest/coverage/{lcov,istanbul,cobertura}_parser.py` | import-line rewrite | ±0 |
| `src/novetest/localization/failure_proximity.py` | delegate inside-workspace branch to utility; drop `import os`; B2-2 policy classifier preserved | −16 / +6 |
| `tests/unit/coverage/test_paths.py` | DELETED (relocated) | −137 |
| `tests/unit/utils/test_path_utils.py` | NEW (7 relocated + 3 wrapper + 2 extra) | +170 |

Net production code: **+52 LOC** (relocation + 1 new `workspace_relpath(path, workspace_root) -> Path` Path-typed wrapper over the existing `to_workspace_relative_posix`).

### Public surface (`src/novetest/utils/path_utils.py`)

| Function | Returns | Purpose |
|---|---|---|
| `to_workspace_relative_posix(path, workspace_root)` | `str` | Three-step resolution: `Path.relative_to` → `os.path.relpath` → drive-stripped POSIX fallback for Windows cross-drive |
| `relpath_or_drive_stripped(path, workspace_root)` | `str` | Step 2+3 half (used by callers that pre-discriminated "is the path a clean subpath?") |
| `workspace_relpath(path, workspace_root)` | `Path` | Convenience `Path` wrapper over `to_workspace_relative_posix` for callers preferring Path-typed receivers |

All three re-exported through `novetest.utils` package surface for the canonical import.

### Localization migration

`_normalize_to_workspace_relative` (inside-workspace branch) now delegates to
`to_workspace_relative_posix`. The `_is_outside_workspace` policy classifier
(which decides "this file lives outside the workspace — keep absolute path
for stdlib frames per B2-2 policy") is **preserved unchanged** — that's
Localization-specific policy ON TOP of the path utility, not part of the
utility.

## Load-bearing learnings (3)

### 1. The §4 amendment 2026-06-19 CI matrix verdict criterion's first qualifier

This was the first slice to qualify under the new §4 MUST clause of
`decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
(amended this cycle). The verification doc cited `ci.yml` run `27831589304`
10/10 GREEN at SHA `167a261` (= merged tip `d5b4242` + 3 comms-only
verification request commits on top). The Windows cross-drive
`_raising_relpath` fixture-mocked test passed on all 3 Windows-cell Python
versions — empirically proving the rename did NOT break cross-drive
fallback wiring.

**Why pinned**: future slices that touch path-handling / OS-gating /
Python-version-sensitive code MUST follow the same citation pattern.
The criterion is now reified and operationally green.

### 2. Charter cross-over "Option-A in-cycle" pattern is mature

This was the **third application** of the in-cycle charter exception pattern
(after v0.1.1 wheel version-bump 2026-06-10 and 2026-06-18 Windows-pipeline
CEO-push-gate deferral). Coverage team authored Localization migration under
PM authorization with the scoping discipline:

- Pure refactor (byte-equivalent envelope output verified via Coverage's
  pre-merge probe — 1406 bytes byte-identical pre vs post modulo timestamps)
- Zero new logic (only the inline implementation moves; semantics unchanged)
- B2-2 outside-workspace policy preserved unchanged (it's policy, not utility)

**Pattern recommendation**: future briefs may use the same shape when a
refactor naturally crosses team boundaries AND the migration is provably
behavior-preserving. The pre-authorization scoping (3 bullets above) is
the load-bearing discipline.

### 3. Delete + rewrite > re-export shim for low-callsite refactors

Coverage chose DELETE + rewrite-3-import-lines over the re-export shim path
because only 4 Coverage-internal callsites referenced `_paths.py`. The
threshold (< 5 callsites = delete; > 5 = shim) from the brief's "Coverage
team chooses" disposition held — keeps the new public surface (`utils.path_utils`)
as the single source of truth, no backward-compat liability on the deleted
internal module.

**Why pinned**: future utility-promotion cycles can reuse the same threshold
heuristic — call-site count drives shim-vs-rewrite decision.

## Phase 0 DoD bullets re-validated (no new ticks)

This cycle adds zero new Phase 0 DoD ticks (Future-cycle queue item, not
Phase 0 binding). Empirically re-validated:

- `ci.yml` 10/10 GREEN on `27831589304` (= merged tip + comms commits)
- mypy `--strict` GREEN (109 source files — unchanged)
- pytest 1303 passed / 5 skipped / 0 failed at equipped-host pre-merge gate

## Future-cycle queue impact

- **#6 `workspace_relpath` utility** ← CLOSED by this cycle (canonical
  promotion path queued in 2026-06-09 MVP sign-off history)
- **#7 CI verdict meta-decision amendment** ← CLOSED by `42f6a32` (PM
  internal amendment merged in cycle dispatch commit)

## Cycle transcript (commits)

- `42f6a32` — PM: Wave 1 parallel dispatch (this cycle + #2a/#5/#8 Release + #3 Run + #7 PM internal amendment)
- `9c5abbf` — Coverage: workspace_relpath utility promotion + Localization migration
- `0cdc3dc` — Main Branch: verification routing to Manual Test
- _(this commit)_ — PM: cycle-close (3-history bundle + transient cleanup + INDEX regen)

## Closure

The workspace-relpath utility is now project-wide canonical. The "scenario
A pattern" (`os.path.relpath` + drive-stripped POSIX fallback) lives in one
place; future engines that need workspace-relative paths import from
`novetest.utils.path_utils`. Future-cycle queue #6 is operationally closed.

**Companion entries**: `2026-06-19-notices-pip-deps-and-perf-bench-bundle.md`
(closes #2a / #5 / #8) and `2026-06-19-v1-metadata-channel-sunset.md`
(closes #3) close the Wave 1 cohort.
