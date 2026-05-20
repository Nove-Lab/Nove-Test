---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-20
slug: ci-node-win-fallback
task: release-team-2026-05-20-ci-node-cell
verdict: green
---

# Handoff: restrict jest CI cells to non-Windows (follow-up to ci-node-cell)

## POST-MERGE OBSERVATION — verdict: green

Merged to `origin/main` (`c350e5c` + comms). CI run **26170660489** on
headSha `f23c07d` — **conclusion: success, 9/9 cells green**:

| Cells | Result | jest tests |
|---|---|---|
| 3x ubuntu-latest | green | run + pass — `337 passed` (334 + 3 jest) |
| 3x macos-latest  | green | run + pass — `337 passed` (334 + 3 jest) |
| 3x windows-latest | green | correctly **skipped** — `334 passed, 3 skipped` |

Log evidence:
- macos-latest/py3.11: `337 passed in 31.41s`; the npm-install loop
  processed both `jest-basic-coverage/` and `jest-basic/`.
- windows-latest/py3.11: `334 passed, 3 skipped` — the adapter's
  `_require_node_and_local_jest()` guard skips jest when Node is absent,
  exactly as designed by this fallback.

Outcome matches the prediction in the pre-merge section below: jest is a
real CI gate on the 6 Linux + macOS cells; Windows is green via correct
skip. The `ci-node-cell` task is complete. Release team returns to standby.

Follow-up tracked in question
`release-team-2026-05-20-jest-adapter-windows-npx.md` (PM -> Run team):
once the jest adapter resolves `npx.cmd` on Windows, the
`runner.os != 'Windows'` guard can be dropped to restore jest to all 9.

---

_Pre-merge content below (retained for record)._

## Why this follow-up exists

The `ci-node-cell` slice (commit `68a4dcb`, merged) added Node.js to all 9
CI cells. CI run **26169544419** on origin/main `c4cb770` then went red:

| Cells | Result |
|---|---|
| 6x Linux + macOS | **green** — jest tests genuinely run (`337 passed`; the 3 jest tests no longer skip) |
| 3x `windows-latest` | **red** — `3 failed, 334 passed` |

The Windows failure is **not a CI-config bug** — it is a jest-adapter bug.
This handoff applies the `ci-node-cell` task's pre-authorised fallback to
restore a green matrix.

## Root cause of the Windows red

`AdapterInvocationError: npx not found on PATH` — despite Node.js being
installed and `npx.cmd` on PATH. The jest adapter's readiness guard uses
`shutil.which("npx")` (honours `PATHEXT` → finds `npx.cmd` → does not
skip), but the adapter then execs the **bare name** `npx`, which Windows
`CreateProcess` cannot resolve (no `PATHEXT` on the exec target). Full
analysis + suggested fix in question
`release-team-2026-05-20-jest-adapter-windows-npx.md` (routed to PM →
Run team; `src/novetest/run/adapters/jest_adapter.py`, outside Release
team's file ownership).

## Worktree

- Worktree: `/home/yjshin/dev/novetest-ci-node-win-fallback`
- Branch: `worktree-ci-node-win-fallback`
- Commit: `c350e5c` — `ci: restrict jest CI cells to non-Windows (npx.cmd adapter bug)`
- Base: `origin/main` @ `c4cb770`

## Files changed

- `.github/workflows/ci.yml` — added `if: runner.os != 'Windows'` to the
  `Install Node.js` and `Install jest fixture dependencies` steps; expanded
  the comment to explain the Windows omission (+17 / −4). No other step
  touched.

## Effect

- Windows cells: Node.js not installed → `shutil.which("npx")` returns
  `None` → the adapter's skip guard `_require_node_and_local_jest()`
  correctly **skips** the jest tests → all 3 Windows cells green again.
- Linux + macOS cells: unchanged — jest stays a **real CI gate** on all 6.
  This is strictly better than the task's documented ubuntu-only fallback
  (macOS coverage retained).
- Expected post-merge CI: **9/9 green**, jest tests reported as *passed*
  on 6 cells, *skipped* on 3 Windows cells.

## Verification done

- `.github/workflows/ci.yml` confirmed valid YAML.
- `if: runner.os != 'Windows'` matches the pattern already used by the
  existing `pytest (release smoke)` step in this same file — consistent.
- Confirmed from run 26169544419 logs: the `Install Node.js` /
  `Install jest fixture dependencies` steps themselves *succeeded* on
  Windows; only the in-`pytest` jest exec failed. So removing Node from
  Windows is sufficient and correct — there is no CI-step-level defect.
- Confirmed on ubuntu py3.11: `337 passed` and the npm-install loop
  processed both `jest-basic/` and `jest-basic-coverage/` (loop picks up
  the parallel fixture automatically, as designed).

## Not yet verified (needs GHA observation post-merge)

CI fires only on push/PR to `main`. Per team convention this is a
pre-merge handoff; Release will supersede it `status: done` with the
observed run URL once Main Branch merges and CI runs. Expected: 9/9 green.

## DoD bullets believed closed

None. Phase 0 is already fully closed; this is CI-coverage maintenance for
the jest adapter slices, not a `delivery-phasing.md` DoD bullet.

## Notes for Main Branch

- Touches only `.github/workflows/ci.yml` — no `src/`, no `tests/`, no
  `pyproject.toml`. No `WORKLOG.md` entry required.
- Also lands one question file (`questions/release-team-2026-05-20-jest-
  adapter-windows-npx.md`) for PM to route to Run team.
- No merge conflicts expected — single isolated file, base is current
  `origin/main`.
- The earlier pre-merge handoff `release-team-2026-05-20-ci-node-cell.md`
  is now superseded by this follow-up; its slice merged but needed this
  Windows correction.
