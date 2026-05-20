---
from: novetest-release-team
to: novetest-pm-team
type: question
status: open
created: 2026-05-20
slug: jest-adapter-windows-npx
---

# jest adapter fails on Windows — `npx` exec name not resolved to `npx.cmd`

## Context

The `ci-node-cell` slice added Node.js to the CI matrix so the jest
integration tests run instead of skip. CI run **26169544419** (origin/main
`c4cb770`) result:

- 6/6 Linux + macOS cells **green** — jest tests now genuinely run
  (`337 passed`, i.e. the 3 jest tests are no longer skipped).
- 3/3 `windows-latest` cells **red** — jest tests fail.

## Root cause (Run-team territory — not a CI-config bug)

On Windows the failure is deterministic:

```
novetest.run.errors.AdapterInvocationError:
  `npx` not found on PATH; install Node.js >=18 and ensure
  `node`/`npx` are on PATH
```

Yet Node.js *was* installed (the `Install Node.js` CI step succeeded) and
`npx.cmd` *was* on PATH. The mismatch:

- The jest adapter's readiness guard uses `shutil.which("npx")`, which
  honours `PATHEXT` and therefore finds `npx.cmd` → the skip guard
  **passes** (does not skip).
- The adapter then execs the subprocess with the **bare name** `npx`
  (`('npx', 'jest', ...)` via `create_subprocess_exec`). Windows
  `CreateProcess` does **not** apply `PATHEXT` to the executable target,
  so `npx` (no extension) is not found and the exec fails — the adapter
  re-raises it as `AdapterInvocationError`.

Affected file (Release team cannot touch `src/**`):
`src/novetest/run/adapters/jest_adapter.py` — the `npx` invocation.

Same applies to any future `node`-name exec on Windows; `node.exe`
resolves fine but `npx`/`npm` are `.cmd` shims.

## Suggested fix (for Run team to evaluate)

On Windows, exec `npx.cmd` instead of `npx` (e.g. resolve the actual path
via `shutil.which("npx")` — which already returns the `.cmd` — and pass
that resolved path to the subprocess, instead of the bare name). The
readiness guard already computes `shutil.which("npx")`; reusing that
resolved path for the exec would fix both the guard/exec inconsistency
and the Windows failure in one change.

## What Release team did in the meantime

Applied the `ci-node-cell` task's pre-authorised fallback: gated the CI
Node-setup steps on `runner.os != 'Windows'`, so Windows skips jest again
(the guard correctly skips when `npx` is absent) and CI is green on all 9
cells. jest remains a real CI gate on the 6 Linux + macOS cells.
See handoff `release-team-2026-05-20-ci-node-win-fallback.md`.

## Ask for PM

Route the adapter bug to Run team. Once `jest_adapter.py` resolves
`npx.cmd` on Windows, Release team can drop the `runner.os != 'Windows'`
guard and restore jest to all 9 cells — a small follow-up. No urgency
(Phase 0 closed; jest is Phase 2.5), but it should be tracked so Windows
jest coverage is not silently lost forever.
