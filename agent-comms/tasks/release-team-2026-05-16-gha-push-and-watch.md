---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-16
slug: gha-push-and-watch
---

# Task: GHA observation pass — close Phase 0 DoD #1, #2, #3

## Scope / Mission

The Phase 0 release-tooling slice (commit `3704527 release: ship Phase 0 CI
matrix, PyApp release pipeline, and install.sh`, already on `main`) landed
two GitHub Actions workflows that have not yet been observed green on real
GHA hardware. Your job this cycle is to **observe** those workflows, not to
edit them.

Specifically:

1. Confirm `.github/workflows/ci.yml` (9-cell matrix: Linux/macOS/Windows ×
   Python 3.11/3.12/3.13) is green on the current `origin/main` tip
   (`017eb04` as of task creation, or whatever has landed by the time you
   pick this up).
2. Trigger `.github/workflows/release-test.yml` via `workflow_dispatch` (or
   ask CEO to push a `v0.0.1-rc0` tag — see "Trigger choice" below) and
   confirm green across all four PyApp targets (linux-x86_64, linux-aarch64,
   macos-x86_64, macos-arm64) AND the in-workflow `install-script-e2e` job.
3. Write a handoff that names the three Phase 0 DoD bullets this observation
   pass satisfies — PM will tick them during cycle cleanup.

This pass is the gate for declaring **Phase 0 fully closed**.

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` (the
   `ailovestesting.com/novetest/install.sh` URL is not yet wired by CEO;
   `release-test.yml` uses the GHA artifact URL directly for the e2e job)
4. `agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md`
   (the prior cycle's notes on what was "believed closed but not yet
   observed")
5. `WORKLOG.md` top 3 entries (Phase 0 release slice entry for full
   landing inventory)
6. `design/implementation-plan/delivery-phasing.md` Phase 0 DoD —
   specifically bullets #1, #2, #3, #4 (with note: #4 is already ticked
   from last cycle; you are NOT re-verifying #4)
7. `.github/workflows/ci.yml` and `.github/workflows/release-test.yml`
   (your verification inputs; do not modify)

## Trigger choice (CEO-interactive)

Two options for triggering `release-test.yml`. CEO has indicated
"automatable parts by team, human-judgment parts by CEO interactively."

**Default (team-executes):** `gh workflow run release-test.yml --ref main`
from your shell. This runs the workflow without creating a permanent tag.
Faster, no tag pollution. Recommended.

**Alternative (CEO-executes):** Ask CEO to push a `v0.0.1-rc0` annotated
tag. This also creates a draft GitHub Release as a side effect. Use this
only if `workflow_dispatch` is blocked or CEO explicitly wants a tagged
artifact for archival.

**Procedure:**

1. First, **check the team's GHA permissions yourself**: `gh auth status`
   and `gh workflow list --repo Nove-Lab/Nove-Test`. If both succeed, you
   have what you need — proceed with `workflow_dispatch`.
2. If `gh workflow run` fails with a permissions error (or `gh` is not
   authenticated for the team's identity), STOP and write
   `agent-comms/questions/release-team-2026-05-16-gha-trigger-auth.md`
   asking CEO to either (a) authenticate the team's `gh` or (b) trigger
   the dispatch from CEO's account. PM will route. Do not proceed without
   a green trigger path.

## Files to write / modify

- `agent-comms/handoffs/release-team-2026-05-16-gha-push-and-watch.md`
  (the only output)
- `agent-comms/questions/release-team-2026-05-16-*.md` (only if you
  encounter a blocker — see "Trigger choice" and "If RED" below)

## Files NOT to touch

- `.github/workflows/**` — observation-only. If the workflows have a bug
  that prevents a green run, STOP and write a `questions/` file rather
  than fixing in-flight. The fix is a separate slice.
- `scripts/install.sh` — same as above.
- `src/**`, `tests/**` — out of your charter scope and out of this task.
- `pyproject.toml` — no dep changes in this task.

## Green-pass criteria (all required to tick)

| DoD bullet (Phase 0) | Observation required |
|---|---|
| #1 `uv run pytest -q` green across 9-cell matrix | `ci.yml` latest run on `017eb04`-or-later: all 9 cells green, including the `tests/release` job that runs on Linux/macOS |
| #2 A signed binary builds on the `release-test` workflow | `release-test.yml` latest run: all 4 PyApp build jobs green; each produces a `novetest-<target>` artifact + `.sha256` sidecar (verify by inspecting the workflow artifact list with `gh run view --log`) |
| #3 `curl-pipe-sh` end-to-end produces a working `novetest --version` | `release-test.yml` `install-script-e2e` job: green; you can see `novetest --version` was invoked successfully against the just-installed binary in the job's log |

For each bullet, capture in your handoff:
- The workflow run URL (`gh run view <id> --json url`)
- The conclusion (`success`)
- A 1-2 line excerpt from the relevant log section (proof, not exhaustive)

## If RED

If any cell or job fails:

1. **Do not fix.** This task is observation-only.
2. Capture the failing cell/job, the conclusion, and a useful stderr
   excerpt (last ~30 lines of the failing step's log).
3. Write the handoff with `status: blocked` and `verdict: failed`. List
   the failures specifically. PM will route to a follow-up Release task
   to fix the workflow.
4. Do NOT claim any DoD bullet closed.

## Verification commands (use these — do not improvise)

```sh
# 1. Confirm auth + repo access
gh auth status
gh repo view Nove-Lab/Nove-Test --json defaultBranchRef

# 2. Check latest ci.yml run on main
gh run list --workflow=ci.yml --branch=main --limit 5
gh run view <run-id> --json conclusion,headSha,jobs

# 3. Trigger release-test.yml (if --workflow-dispatch is the chosen path)
gh workflow run release-test.yml --ref main
# Then watch:
gh run watch <run-id>     # or
gh run view <run-id> --log-failed   # after completion, only on failure

# 4. Inspect release-test artifacts
gh run view <run-id> --json artifacts
# Sanity-check the artifacts include a .sha256 sidecar per binary
```

`gh run watch` is interactive — fine for your shell. If it blocks longer
than ~30 min, switch to `gh run view --json conclusion` polling.

## Reporting (handoff)

Write `agent-comms/handoffs/release-team-2026-05-16-gha-push-and-watch.md`
with the standard handoff body sections. In addition:

- **Workflow run URLs** (one for `ci.yml`, one for `release-test.yml`).
- **Conclusion per workflow** (`success` / `failure`).
- **DoD bullets believed closed** — list the Phase 0 bullets satisfied.
  Empty list if RED.
- **No worklog entry needed** — this task does not modify `src/` or
  `tests/`, so the `check-worklog-before-commit.sh` hook does not apply.
  This is intentional: PM tracks the GHA-observation outcome through the
  handoff + cycle history, not WORKLOG.

When the handoff is written, run `python3 tools/regen_comms_index.py`.

## Out of scope (do NOT do these in this task)

- Edit `ci.yml` or `release-test.yml`.
- Bump PyApp version (currently pinned to `0.22.0`).
- Wire the `ailovestesting.com/novetest/install.sh` redirect. That is a
  CEO + DNS task, separate from CI/release verification.
- Write `install.ps1` for Windows. OQ #16, post-MVP.
- Add `windows-arm64` cell. Currently unsupported per `foundations.md`.
- Touch `pyproject.toml`.

## Why this task exists

The Release slice landed with 4 Phase 0 DoD bullets believed closed, but 3
of them (#1, #2, #3) require live GHA observation that local testing
cannot substitute for. Last cycle, PM ticked #4 (install-script SHA-256
abort path) because Manual Test independently exercised the tampered-binary
path on the dev machine. The remaining three are intrinsically remote-CI
observations. Closing them now lets Phase 0 be formally declared done and
the project can focus on Phase 2 progression without a dangling Phase 0
DoD chain.
