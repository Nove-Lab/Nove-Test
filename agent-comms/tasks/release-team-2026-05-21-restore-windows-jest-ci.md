---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-21
slug: restore-windows-jest-ci
related:
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
  - questions/release-team-2026-05-20-jest-adapter-windows-npx.md
---

# Task: restore jest to all 9 CI cells (drop the Windows guard)

## Scope / Mission

The jest adapter's Windows `npx` defect is **fixed and merged** — commit
`0e9ab71` (`fix(run): resolve npx via cmd /c on Windows in jest adapter`).
Drop the temporary `runner.os != 'Windows'` guard your `ci-node-win-fallback`
slice added so jest runs as a real CI gate on **all 9 cells** again.

This is the final tail slice of the 2026-05-20 cycle. The post-merge GHA
run for this change is **also the definitive verification of the Run npx
fix** (`0e9ab71`) — which has not yet been exercised on a real
`windows-latest` runner because the guard still skips it.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-release-team.md`
2. `.github/workflows/ci.yml` — the current `test` job; the two guarded
   steps `Install Node.js` (line ~60-64) and `Install jest fixture
   dependencies` (line ~72-81), each carrying `if: runner.os != 'Windows'`
3. `agent-comms/handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md`
   — the fix: Windows now launches jest as `cmd /c npx jest ...`
4. Your own `agent-comms/handoffs/release-team-2026-05-20-ci-node-win-fallback.md`
   — the slice this one reverses

## What the Run fix did (context — no action needed from you)

`run_jest` resolves `npx` via `shutil.which` up front; on Windows the
`.cmd` batch shim is launched **through `cmd.exe`** (`["cmd", "/c",
"npx"]`) because `CreateProcess` cannot execute `.cmd`/`.bat` directly.
POSIX behaviour is unchanged. So jest is now runnable on `windows-latest`.

## Files to write / modify

- `.github/workflows/ci.yml` — remove the `if: runner.os != 'Windows'`
  condition from BOTH the `Install Node.js` step and the `Install jest
  fixture dependencies` step. Rewrite the explanatory comment block above
  those steps so it reflects the restored state: all 9 cells get Node.js +
  jest fixture deps; jest is a real gate cross-OS; note that the earlier
  Windows-skip was a temporary fallback lifted once the adapter's
  `cmd /c npx` fix landed (commit `0e9ab71`). Do NOT leave stale text
  describing the Windows omission as current.

## Files NOT to touch

- The `pytest (release smoke)` step's `if: runner.os != 'Windows'`
  (line ~112) — **LEAVE IT.** That is a separate, legitimate Windows skip
  (`install.sh` is POSIX sh; Windows parity is post-MVP, OQ#16). Only the
  two jest/Node steps lose their guard.
- `src/**`, `tests/**`, `pyproject.toml`, any other workflow,
  `agent-comms/decisions/**`.

## Expected effect

- All 9 cells install Node.js 20 + jest fixture `node_modules`.
- `windows-latest` cells: jest integration tests now **run** (via the
  fixed `cmd /c npx` adapter path) instead of skipping — expect the 3
  Windows cells to go from `334 passed, 3 skipped` to `337 passed`.
- Linux + macOS cells: unchanged (`337 passed`).
- The `Install jest fixture dependencies` step already uses `shell: bash`
  — `windows-latest` runners ship Git Bash, so the loop is portable as-is;
  no shell change needed.

## Verification

- Confirm `.github/workflows/ci.yml` is valid YAML.
- The real signal is **GHA observation post-merge** — CI fires only on
  push/PR to `main`. Per your team convention, hand off pre-merge
  (`verdict: pre-merge-pending-gha-observation`), then supersede
  `status: done` once Main Branch merges and CI runs. **Expected: 9/9
  green, jest tests reported as run + pass on all 9 cells** (Windows
  included). If `windows-latest` jest still fails, do NOT re-add the
  guard unilaterally — raise a `questions/` file; that would mean the
  `cmd /c npx` fix is incomplete and Run team must re-engage.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
editing the workflow.

## Reporting

Write `agent-comms/handoffs/release-team-2026-05-21-restore-windows-jest-ci.md`.

Touches only `.github/workflows/ci.yml` — no `src/`/`tests/` — so **no
`WORKLOG.md` entry required**. Run `python3 tools/regen_comms_index.py`
and stage the comms files + `INDEX.md` with the workflow change.

**DoD bullets believed closed:** none — not a `delivery-phasing.md` DoD
bullet. State "none" explicitly.

In the post-merge supersession, report the CI run URL and the observed
jest outcome on the 3 `windows-latest` cells — that confirms the Run npx
fix end-to-end and lets PM close the 2026-05-20 cycle.
