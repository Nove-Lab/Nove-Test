---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-21
slug: restore-windows-jest-ci
related:
  - handoffs/release-team-2026-05-21-restore-windows-jest-ci.md
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
  - verifications/2026-05-21-jest-adapter-windows-npx.md
  - verifications/2026-05-20-ci-node-win-fallback.md
---

# Verification: restore jest to all 9 CI cells (no Manual Test action)

CI-only follow-up slice. **No Manual Test verification surface** —
`.github/workflows/ci.yml` only. Recorded for PM bookkeeping.

## Merged commits

- `bd7612d` — `ci: restore jest to all 9 cells (lift the Windows guard)`
- `0f9cac9` — `comms: stage restore-windows-jest-ci handoff`

main HEAD after merge: `0f9cac9`. Fast-forward, base was current main
(`75ba64f`) — no rebase, no conflict.

## Source handoff consumed

- `handoffs/release-team-2026-05-21-restore-windows-jest-ci.md`
  (reverses `handoffs/release-team-2026-05-20-ci-node-win-fallback.md`,
  which stays as historical record).

## What changed

`.github/workflows/ci.yml` only (+9/-16): dropped the
`if: runner.os != 'Windows'` condition from the `Install Node.js` and
`Install jest fixture dependencies` steps. All 9 matrix cells now install
Node 20 + jest fixture `node_modules`, so jest is a real CI gate
cross-OS again. The temporary Windows guard was only needed while the
jest-adapter `npx` defect was open; that defect is fixed (`0e9ab71` —
Windows launches jest via `cmd /c npx`).

Deliberately untouched: the `pytest (release smoke)` step keeps its own
separate `if: runner.os != 'Windows'` (install.sh is POSIX sh — a
distinct, legitimate skip).

## Verification

- Post-merge local full gate: `uv run pytest -q tests/unit
  tests/integration` -> **337 passed, 3 skipped**; `uv run mypy` ->
  **clean, 52 source files**. CI-only change — no local test surface
  impact, as expected.
- The real verification is **GHA observation, owned by the Release
  team** — this is a pre-merge handoff (`verdict:
  pre-merge-pending-gha-observation`). Expected post-merge CI: **9/9
  green**, the 3 `windows-latest` cells moving from `334 passed,
  3 skipped` to `337 passed`.
- This CI run is also the **definitive end-to-end verification of the
  Run npx fix `0e9ab71`** on a real `windows-latest` runner — it has
  never been exercised there (the guard skipped it). It closes the
  `partial` verdict left by
  `findings/manual-test-team-2026-05-21-jest-adapter-windows-npx.md`.
- Release stated: if `windows-latest` jest still fails, they will NOT
  re-add the guard unilaterally — they will raise a `questions/` file,
  meaning the `cmd /c npx` fix is incomplete and Run team must re-engage.

## Manual Test action

**None.** CI YAML only; no CLI/envelope surface.

## Reporting

No findings file required.
