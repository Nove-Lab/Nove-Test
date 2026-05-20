---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-21
slug: restore-windows-jest-ci
task: release-team-2026-05-21-restore-windows-jest-ci
verdict: restore-succeeded-ci-red-on-run-team-unit-test
---

# Handoff: restore jest to all 9 CI cells (lift the Windows guard)

## POST-MERGE OBSERVATION — verdict: restore succeeded; CI red on a separate Run-team unit-test bug

Merged to `origin/main` (`bd7612d` + comms). CI run **26172964986** on
headSha `3f30aae`:

| Cells | Conclusion | Detail |
|---|---|---|
| 3x ubuntu-latest | success | `337 passed` |
| 3x macos-latest  | success | `337 passed` |
| 3x windows-latest | **failure** | `1 failed, 339 passed` |

### The restore itself SUCCEEDED — this is the key result

Windows pytest summary moved from `334 passed, 3 skipped` (under the old
guard) to **`1 failed, 339 passed` — no skips**. The 3 jest integration
tests now **run and pass on `windows-latest`** via the `cmd /c npx`
adapter path. The Run npx fix (`0e9ab71`) is verified end-to-end on a
real Windows runner. jest is a genuine CI gate on all 9 cells; that part
of the task is fully achieved.

### The lone red — a stale Run-team unit test, NOT this slice and NOT a CI-config bug

```
FAILED tests/unit/run/adapters/test_jest_adapter.py::test_argv_includes_target_expression
  - AssertionError: assert 'cmd' == '/usr/bin/npx'
```

The Run npx fix made `run_jest` build argv as `["cmd", "/c", "npx", ...]`
on Windows, but the unit test `test_argv_includes_target_expression`
still asserts `argv[0] == '/usr/bin/npx'` unconditionally (POSIX-only).
The fix updated the adapter but not its companion unit test. This unit
test is OS-agnostic in execution — it would have failed on `windows-latest`
even with the old guard still in place (the guard only gated jest
*integration* tests; the *unit* test never needed Node). Confirmed:
the prior run `26172567747` on `75ba64f` (guard still present) already
showed this exact `1 failed` on all 3 Windows cells.

`tests/unit/run/adapters/test_jest_adapter.py` is Run-team territory —
Release team cannot touch `tests/**`. Raised to PM in question
`release-team-2026-05-21-jest-adapter-unit-test-windows.md` for routing
to Run team.

### Release-team decision: guard NOT re-added

Per the task contract, Release did NOT unilaterally re-add the
`runner.os != 'Windows'` guard. Re-adding it would mask a now-passing
jest integration suite on Windows just to hide an unrelated unit-test
defect — a regression in coverage. The restore slice stays as merged.
Once Run team makes the unit test OS-aware, CI goes 9/9 green with no
further Release action.

### Secondary observation (flagged to Run team, non-blocking)

The Windows job log carries a non-fatal warning —
`UnicodeDecodeError: 'charmap' codec can't decode byte 0x90` in a
subprocess reader thread. jest still passed; included in the question
file as a suggestion for Run team to pin `encoding="utf-8"` on the
adapter's Windows stream reading.

### Release-owned follow-up noted (not actioned — out of this task's scope)

The CI log shows `astral-sh/setup-uv@v3` emitting
`Unexpected input(s) 'python-version'` — the action moved that input to
`version`/other keys. It is currently only a warning (uv still resolves
the interpreter) and predates all three of this cycle's Release slices.
Not fixed here (this task's scope was strictly the guard removal); noted
as a small future Release housekeeping item, alongside the GHA
`Node.js 20 actions are deprecated` notice (forced to Node 24 on
2026-06-02).

---

_Pre-merge content below (retained for record)._

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
  the Windows-skip recorded as lifted history (+9 / -16). No other step
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
