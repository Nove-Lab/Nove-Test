---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-21
slug: restore-windows-jest-ci
task: release-team-2026-05-21-restore-windows-jest-ci
verdict: pre-merge-pending-gha-observation
---

# Handoff: restore jest to all 9 CI cells (lift the Windows guard)

## Summary

The jest adapter's Windows `npx` defect is fixed and merged (commit
`0e9ab71` — `run_jest` launches the `npx.cmd` shim through `cmd /c` on
Windows). This slice removes the temporary `runner.os != 'Windows'` guard
that `ci-node-win-fallback` added, so jest runs as a real CI gate on all
9 matrix cells again.

## Worktree

- Worktree: `/home/yjshin/dev/novetest-restore-win-jest`
- Branch: `worktree-restore-windows-jest-ci`
- Commit: `bd7612d` — `ci: restore jest to all 9 cells (lift the Windows guard)`
- Base: `origin/main` @ `75ba64f`

## Files changed

- `.github/workflows/ci.yml` — dropped `if: runner.os != 'Windows'` from
  the `Install Node.js` and `Install jest fixture dependencies` steps;
  rewrote the comment block to describe the restored cross-OS state with
  the Windows-skip recorded as lifted history (+9 / −16). No other step
  touched.

## What changed and what did not

- **Removed:** the `if: runner.os != 'Windows'` condition on both
  jest/Node steps. All 9 cells now install Node 20 + jest fixture
  `node_modules`.
- **Untouched (deliberate):** the `pytest (release smoke)` step keeps its
  own `if: runner.os != 'Windows'` — a separate, legitimate skip
  (`install.sh` is POSIX sh; Windows parity is post-MVP, OQ#16). Only the
  two jest/Node steps lost their guard.
- The `Install jest fixture dependencies` step keeps `shell: bash` —
  `windows-latest` runners ship Git Bash, so the fixture-install loop is
  portable as-is; no shell change needed.

## Verification done

- `.github/workflows/ci.yml` confirmed valid YAML.
- Confirmed exactly one `if: runner.os != 'Windows'` remains in the file —
  the `pytest (release smoke)` step — and that it is intentionally kept.

## Not yet verified (needs GHA observation post-merge)

CI fires only on push/PR to `main`. Per team convention this is a
pre-merge handoff; Release will supersede it `status: done` with the
observed run URL once Main Branch merges and CI runs.

**Expected: 9/9 green, jest tests reported as run + pass on all 9 cells.**
The 3 `windows-latest` cells should move from `334 passed, 3 skipped` to
`337 passed`. This CI run is also the definitive end-to-end verification
of the Run npx fix (`0e9ab71`) on a real `windows-latest` runner — it has
not been exercised there before because the guard skipped it.

If `windows-latest` jest still fails, Release will NOT re-add the guard
unilaterally — it will raise a `questions/` file, since that would mean
the `cmd /c npx` fix is incomplete and Run team must re-engage.

## DoD bullets believed closed

None. This is not a `delivery-phasing.md` DoD bullet — it is the tail
slice restoring cross-OS jest CI coverage after the Run adapter fix.

## Notes for Main Branch

- Touches only `.github/workflows/ci.yml` — no `src/`, no `tests/`, no
  `pyproject.toml`. No `WORKLOG.md` entry required.
- No merge conflicts expected — single isolated file, base is current
  `origin/main` `75ba64f`.
- This reverses `release-team-2026-05-20-ci-node-win-fallback.md`; that
  handoff (`status: done`) stays as historical record.
