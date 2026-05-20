---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-20
slug: ci-node-cell
---

# Task: add a Node.js setup step to CI so the jest integration tests run

## Scope / Mission

`tests/integration/run/test_jest_basic.py` currently skips on **every**
CI runner because the CI matrix has no Node.js. Add Node.js to the CI
job so the jest integration tests actually execute in CI instead of
silently skipping. This also covers the new jest-coverage integration
test landing in parallel slices this cycle.

Small slice. Release team is briefly reactivated from standby for it;
after this you revert to standby (Phase 0 is fully closed).

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-release-team.md`
2. `.github/workflows/ci.yml` — the current 3-OS x 3-Python matrix and
   its job steps (`Install uv` -> `Sync dependencies` -> `pytest` ->
   `mypy` -> `pytest (release smoke)`)
3. `tests/integration/run/test_jest_basic.py` — the skip guard
   `_require_node_and_local_jest()`: it needs `node` + `npx` on PATH AND
   the fixture's `node_modules` installed
4. `tests/fixtures/projects/jest-basic/` — the existing jest fixture

## Files to write / modify

- `.github/workflows/ci.yml` — add Node.js setup + jest fixture
  dependency install.

## Files NOT to touch

- `src/**`, `tests/**` — do not modify test code or fixtures. The skip
  guards already do the right thing; your job is to make the guards
  pass in CI by providing Node + `node_modules`.
- `.github/workflows/release-test.yml` and any other workflow.
- `pyproject.toml`, `agent-comms/decisions/**`.

## Implementation contract

1. **Add `actions/setup-node@v4`** to the `test` job, after checkout.
   Pin a Node.js LTS version (>= 18, consistent with the jest adapter's
   "install Node.js >=18" hint). Recommended: apply to all matrix cells
   — `setup-node` is fast and cached, and running the jest tests across
   all three OSes is valuable (the jest adapter's `--watchman=false`
   exists specifically for Windows predictability). If cross-OS jest
   proves flaky, restricting to `ubuntu-latest` is an acceptable
   fallback — document the choice in the handoff either way.
2. **Install the jest fixtures' dependencies.** Add a step that installs
   `node_modules` for the jest fixtures so `_require_node_and_local_jest()`
   finds the local jest install. **Iterate over every
   `tests/fixtures/projects/*/package.json`** rather than hardcoding
   fixture names — a parallel slice this cycle adds a second jest fixture
   (`jest-basic-coverage/`), and the loop makes this step robust to
   fixtures added before or after your branch is cut. Sketch:
   ```sh
   for d in tests/fixtures/projects/*/; do
     if [ -f "$d/package.json" ]; then
       (cd "$d" && npm install --no-audit --no-fund)
     fi
   done
   ```
   Make it work cross-OS (the matrix includes `windows-latest`; a plain
   `run:` shell step defaults to `pwsh` there — either use a portable
   approach or set `shell: bash`).
3. Order the steps so Node + `node_modules` are ready **before** the
   `pytest` step.
4. Do not change the existing uv / pytest / mypy / release-smoke steps.

## Verification commands (must pass before handoff)

- The change is a CI-config change; validate by reasoning through the
  YAML and, if possible, `act` or a push to a branch. The real signal is
  the CI run going green with the jest tests no longer reporting as
  skipped.
- Confirm `.github/workflows/ci.yml` is valid YAML.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
editing the workflow (CI config counts as code).

## Reporting

Write `agent-comms/handoffs/release-team-2026-05-20-ci-node-cell.md`.

This slice touches only `.github/workflows/` — NOT `src/` or `tests/` —
so **no `WORKLOG.md` entry is required** (the WORKLOG hook keys on
`src/`+`tests/`). Still: run `python3 tools/regen_comms_index.py` and
stage the new comms files + `INDEX.md` with the workflow change.

**DoD bullets believed closed:** none — Phase 0 is already fully closed
and this is not a `delivery-phasing.md` DoD bullet. State "none"
explicitly.

In the handoff, note which matrix cells got Node and whether you observed
the jest integration tests running (not skipping) on the branch CI run.
