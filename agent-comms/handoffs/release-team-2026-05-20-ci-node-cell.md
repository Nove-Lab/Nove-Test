---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-20
slug: ci-node-cell
task: release-team-2026-05-20-ci-node-cell
verdict: pre-merge-pending-gha-observation
---

# Handoff: add Node.js to CI so jest integration tests run

## Summary

Added Node.js + jest fixture dependency installation to the `test` job in
`.github/workflows/ci.yml`. Before this change `tests/integration/run/
test_jest_basic.py` (and the incoming jest-coverage integration test)
skipped on every CI runner because no matrix cell had Node.js on PATH and
no fixture `node_modules` was installed.

## Worktree

- Worktree: `/home/yjshin/dev/novetest-ci-node-cell`
- Branch: `worktree-ci-node-cell`
- Commit: `a15c536` — `ci: add Node.js + jest fixture deps so jest integration tests run`
- Base: `main` @ `3a84aab`

## Files changed

- `.github/workflows/ci.yml` — two new steps in the `test` job (+26 lines).
  No existing step modified.

## What changed

1. **`Install Node.js`** (`actions/setup-node@v4`, `node-version: "20"`)
   inserted right after `actions/checkout@v4`.
   - Node 20 is an active LTS and satisfies the jest adapter's ">= 18"
     readiness hint.
   - **Applied to all 9 matrix cells** (3 OS × 3 Python). Rationale: the
     jest adapter ships `--watchman=false` specifically for Windows
     predictability, so exercising jest cross-OS is valuable, and
     `setup-node` is fast. No npm cache configured — the fixtures carry
     no `package-lock.json`, so `setup-node`'s `cache: npm` would error;
     a plain install is simpler and the dependency surface is tiny
     (`jest@^29`).
2. **`Install jest fixture dependencies`** — a `shell: bash` step that
   loops over `tests/fixtures/projects/*/package.json` and runs
   `npm install --no-audit --no-fund` in each match.
   - Loop-based, not hardcoded: the parallel `jest-basic-coverage/`
     fixture landing this cycle is picked up automatically whether it
     merges before or after this branch.
   - `shell: bash` is explicit so the loop is portable on
     `windows-latest`, where `run:` steps default to `pwsh`.
   - `npm install` (not `npm ci`) because the fixtures intentionally
     carry no lockfile.
3. Both steps run **before** the `pytest` step, so `node` + `npx` +
   `node_modules/.bin/jest` are present when `_require_node_and_local_jest()`
   evaluates its guards.

## Matrix cells receiving Node

All 9: `{ubuntu-latest, macos-latest, windows-latest}` × `{3.11, 3.12, 3.13}`.

## Verification done

- `.github/workflows/ci.yml` confirmed valid YAML (`yaml.safe_load`).
- Confirmed `tests/fixtures/projects/jest-basic/` is the only current
  fixture with a `package.json` and that it has no `package-lock.json`
  (so `npm install` is correct).
- Reasoned through the `test_jest_basic.py` skip guard: it needs `node`
  + `npx` on PATH AND `node_modules/.bin/jest[.cmd]` — both now provided.

## Not yet verified (needs GHA observation post-merge)

CI triggers on `push`/`pull_request` to `main` only — a push to the
worktree branch does not fire it. The real signal (CI green + jest
integration tests reporting as *run*, not *skipped*) can only be observed
once this lands on `main`. Per team convention this is a **pre-merge
handoff**; Release will supersede it with a post-merge `status: done`
version carrying the observed run URL and the jest test outcome once
Main Branch merges and CI runs.

Watch points for the post-merge observation:
- `windows-latest` jest run — if cross-OS jest proves flaky, the
  documented fallback is restricting the fixture-install step (or the
  jest tests) to `ubuntu-latest`. Not expected, but flagged.
- `npm install` network reliability on the runners.

## DoD bullets believed closed

None. Phase 0 is already fully closed; this is not a `delivery-phasing.md`
DoD bullet — it is a CI-coverage improvement for the jest adapter slices.

## Notes for Main Branch

- This slice touches only `.github/workflows/ci.yml` — no `src/`, no
  `tests/`, no `pyproject.toml`. No `WORKLOG.md` entry required (the
  WORKLOG hook keys on `src/`+`tests/`).
- No merge conflicts expected: single isolated file, two appended steps.
