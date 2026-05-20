---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-20
slug: ci-node-win-fallback
related:
  - handoffs/release-team-2026-05-20-ci-node-win-fallback.md
  - handoffs/release-team-2026-05-20-ci-node-cell.md
  - questions/release-team-2026-05-20-jest-adapter-windows-npx.md
  - verifications/2026-05-20-ci-node-cell.md
---

# Verification: restrict jest CI cells to non-Windows (no Manual Test action)

This records a CI-only follow-up slice merged this cycle. It has **no
Manual Test verification surface** — `.github/workflows/ci.yml` only.
Recorded for PM bookkeeping; Manual Test has nothing to run.

## Merged commits

- `c350e5c` — `ci: restrict jest CI cells to non-Windows (npx.cmd adapter bug)`
- `21c4f74` — `comms: ci-node-win-fallback handoff + jest-adapter-windows-npx question`

main HEAD after merge: `21c4f74`. Fast-forward, base was current main
(`c4cb770`) — no rebase, no conflict.

## Source handoff consumed

- `handoffs/release-team-2026-05-20-ci-node-win-fallback.md`
  (supersedes the pre-merge `handoffs/release-team-2026-05-20-ci-node-cell.md`).

## Why this follow-up exists

The `ci-node-cell` slice (`68a4dcb`) added Node.js to all 9 CI cells.
GHA run **26169544419** on origin/main `c4cb770` then went red:

- 6x Linux + macOS — **green**, jest tests genuinely run (`337 passed`).
- 3x `windows-latest` — **red**, `3 failed`.

Root cause is a **jest-adapter bug, not a CI-config bug**: the adapter's
readiness guard uses `shutil.which("npx")` (honours `PATHEXT` -> finds
`npx.cmd` -> guard passes) but then execs the bare name `npx`, which
Windows `CreateProcess` cannot resolve. Full analysis routed to PM ->
Run team in `questions/release-team-2026-05-20-jest-adapter-windows-npx.md`.

## What changed

`.github/workflows/ci.yml` only (+17/-4): `if: runner.os != 'Windows'`
added to the `Install Node.js` and `Install jest fixture dependencies`
steps. This is the `ci-node-cell` task's pre-authorised fallback. With
Node absent on Windows, the adapter's readiness guard correctly skips the
jest tests there; jest stays a real CI gate on the 6 Linux + macOS cells
(strictly better than the task's documented ubuntu-only fallback —
macOS coverage retained).

## Verification

- Local full gate after merge: `uv run pytest -q tests/unit
  tests/integration` -> **334 passed, 3 skipped**; `uv run mypy` ->
  **clean, 52 source files**. CI-only change — no test surface impact,
  as expected.
- The real verification is **GHA observation, owned by the Release
  team** — this is a pre-merge handoff (`verdict:
  pre-merge-pending-gha-observation`). Expected post-merge CI: **9/9
  green**, jest reported as *passed* on 6 cells, *skipped* on 3 Windows
  cells. Release will supersede their handoff `status: done` with the
  observed run URL.

## Manual Test action

**None.** CI YAML only; no CLI/envelope surface.

## Open follow-up (PM)

`questions/release-team-2026-05-20-jest-adapter-windows-npx.md` asks PM
to route the jest-adapter Windows `npx.cmd` bug to the Run team. Once
`jest_adapter.py` resolves `npx.cmd` on Windows, the
`if: runner.os != 'Windows'` guard can be dropped and jest restored to
all 9 cells. Not urgent (Phase 0 closed; jest is Phase 2.5) but should
be tracked so Windows jest coverage is not silently lost.

## Reporting

No findings file required. If Manual Test wants to acknowledge, a single
line in any of this cycle's findings docs is sufficient.
