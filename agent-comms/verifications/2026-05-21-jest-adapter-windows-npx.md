---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-21
slug: jest-adapter-windows-npx
related:
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
  - questions/release-team-2026-05-20-jest-adapter-windows-npx.md
  - verifications/2026-05-20-ci-node-win-fallback.md
---

# Verification: jest adapter `npx` resolution on Windows

## Merged commit

- `0e9ab71` — `fix(run): resolve npx via cmd /c on Windows in jest adapter`

main HEAD after merge: `0e9ab71`. Fast-forward, base was current main
(`ab1ef44`) — no rebase, no conflict.

## Source handoff consumed

- `handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md`

Closes the defect raised in
`questions/release-team-2026-05-20-jest-adapter-windows-npx.md` (jest
tests red on all 3 `windows-latest` CI cells in GHA run 26169544419).

## What changed

`src/novetest/run/adapters/jest_adapter.py` (+ its unit test file).
`run_jest` previously exec'd the bare name `"npx"`; Windows
`CreateProcess` only appends `.exe` to a bare name, never `.cmd`, so
`npx` (which exists only as `npx.cmd`) was unresolvable even with Node.js
installed. The fix:

- `npx` is resolved up front via `shutil.which("npx")`; `None` -> a typed
  `missing-binary` error (was a less specific `FileNotFoundError` path).
- New pure helper `_npx_launcher(npx_path, *, windows)`:
  - **POSIX**: launcher = `[<resolved abs path to npx>]`, exec'd directly.
    Functionally identical to the old bare-name behaviour (`execvp`
    resolved the bare name to the same file).
  - **Windows**: launcher = `["cmd", "/c", "npx"]` — the `.cmd` batch
    shim is run *through* `cmd.exe` (CreateProcess cannot launch batch
    files directly). The bare `npx` is handed to `cmd` so `cmd`'s
    `PATHEXT` resolution applies.

Confirmed against merged source (`_npx_launcher` lines 223-246).

## Verification

- Post-merge full gate on the combined tree: `uv run pytest -q
  tests/unit tests/integration` -> **337 passed, 3 skipped**;
  `uv run mypy` -> **clean, 52 source files**. The 3 skips are the
  Node-dependent jest integration tests. This slice adds +3 net unit
  tests (`_npx_launcher` POSIX/Windows + the split missing-binary cases).

## IMPORTANT — what Manual Test can and cannot verify

This is a **Windows-specific defect fix**. The definitive signal is a
real `windows-latest` CI run — which is currently still **skipped** by
the `ci-node-win-fallback` guard (`if: runner.os != 'Windows'` in
`ci.yml`). The companion Release follow-up task will drop that guard now
that this adapter fix is on `main`; that CI run is the true verification.

So:

- **Linux/macOS POSIX path** — unchanged by design. Confirm no regression:
  if Manual Test has Node.js, a plain `novetest run` against the
  `jest-basic` fixture must behave exactly as before. If no Node.js (as
  on the merge-team box), the jest exec path short-circuits at the
  engine-readiness probe — report as skipped, matching prior cycles.
- **Windows `cmd /c npx` path** — **cannot be verified locally** on a
  Linux/macOS box. Defer to the Release guard-removal CI run.

A `partial` verdict (POSIX confirmed / Windows deferred to CI) is the
expected and acceptable outcome here, same shape as the jest-coverage
verification.

## Critical edge cases worth probing

- **Unresolvable `npx`** — in an environment with no `npx` on PATH,
  `novetest run` against a jest workspace must fail with a typed
  `missing-binary` error (structured envelope, no traceback), NOT a raw
  `FileNotFoundError`.
- **POSIX behaviour byte-identical** — the resolved-abs-path launcher
  must produce the same jest invocation as before; confirm via the
  unit suite (`test_npx_launcher_posix_uses_resolved_path`) if a real
  run is not possible.

## Reporting

Write findings to `agent-comms/findings/manual-test-team-2026-05-21-jest-adapter-windows-npx.md`.
