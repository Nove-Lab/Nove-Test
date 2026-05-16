---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: release-test-pyapp-wrap-path
related:
  - tasks/release-team-2026-05-16-release-test-pyapp-wrap-path.md
  - history/2026-05-16-phase0-gha-attempt-red.md
  - handoffs/run-team-2026-05-16-pytest-adapter-bin-false-portable.md
---

# Verification request: release-test.yml PyApp wrap path fix

## Merged commit

- **Hash:** `855f56a` (rebased from worktree commit `4793eab` onto `9771501`, then fast-forward to main; clean linear history).
- **Title:** `ci(release-test): pass absolute wheel path to PyApp wrap step`
- **Scope:** Pure workflow YAML change. `.github/workflows/release-test.yml`'s "Wrap wheel with PyApp" step now captures `wheel` as an absolute path via `"$GITHUB_WORKSPACE/dist/"...whl` so `PYAPP_PROJECT_PATH` survives the subsequent `cd pyapp-src` before PyApp v0.22.0's `build.rs` reads it. Dropped the misleading `PYAPP_PROJECT_PATH: ${{ github.workspace }}/dist` env-block entry (it pointed at a *directory*, was always shadowed by the shell-body `export`, but its presence implied the shell rewrite was optional). Replaced with a comment explaining why the value lives in the shell body.
- **Closes Phase 0 DoD #2 + #3 pending green re-observation** (per task spec — the post-merge `release-test.yml` re-trigger is the authoritative observation, owned by Release team).
- **No production code, test, or dep change.** YAML-only.

## Source / handoff status (special pattern)

**No handoff doc was written before merge** — this is by design per the task spec (`tasks/release-team-2026-05-16-release-test-pyapp-wrap-path.md`):

> "Worktree path + branch + base commit (workflow YAML edits are normal worktree → main merge — **coordinate via Main Branch**)."
> "Workflow run URL + conclusion per workflow (**post-merge re-trigger**)."

The Release team cannot exercise PyApp locally, so the slice's verification IS the post-merge GHA observation. The handoff will be written **after** Release re-triggers `release-test.yml` against the new origin/main and captures the workflow URLs + conclusions per DoD bullet. PM's task spec explicitly authorizes this merge-before-handoff pattern for this slice.

## Merge notes

- **Rebase required (not fast-forward from base).** Release's worktree was branched from `1fddb94`, then I merged Run team's slice (`fc79209`) and a comms commit (`9771501`) onto main while Release was still working. Release's branch was therefore not an ancestor of current main. I rebased their single commit `4793eab` onto `9771501` cleanly (no conflicts — file scopes fully disjoint: Run touched `tests/unit/run/adapters/test_pytest_adapter.py`, Release touched `.github/workflows/release-test.yml`). Rebased commit hash: `855f56a`. Then fast-forwarded main.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration` → **267 passed** (unchanged baseline — slice has no Python impact), `uv run mypy --strict` → **clean** (49 files).
- **YAML parse check on main:** both `release-test.yml` and `ci.yml` parse cleanly via `yaml.safe_load`.
- **Diff inspected before merge.** Confirmed surgical: only the wrap-step shell body + env-block comment swap. No other workflow steps, no other workflows, no source.

## What Manual Test can verify (very limited)

This slice has **zero user-facing impact and zero local-runnable verification** beyond YAML parse + suite-still-green checks. The authoritative gate is Release team's post-merge `gh workflow run release-test.yml` observation (9-cell `ci.yml` + 4 PyApp build jobs + 1 install-script-e2e job, all expected `success`). Manual Test should spend ≤5 minutes here.

### Spot-check 1 — YAML still parses on main

```sh
cd /home/yjshin/dev/Nove-Test
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml')); print('OK')"
```

Assert: prints `OK`.

### Spot-check 2 — Full suite unchanged

```sh
uv run pytest -q tests/unit tests/integration
```

Assert: `267 passed`. (No Python touched in this slice; the count should match the previous verification.)

### Spot-check 3 — Eyeball the YAML change

Open `.github/workflows/release-test.yml`, locate the "Wrap wheel with PyApp" step (around line 109). Confirm:
- The `env:` block has NO `PYAPP_PROJECT_PATH` entry (replaced with a comment).
- The shell body's `wheel="$(ls "$GITHUB_WORKSPACE/dist/"...)"` quoting is intact (the absolute-path expansion only works with the inner double-quotes around `$GITHUB_WORKSPACE/dist/`).
- The subsequent `export PYAPP_PROJECT_PATH="$wheel"` is on its own line, before `cd pyapp-src`.

## Critical edge cases

1. **The real gate is GHA-side and depends on the push.** Release team's task explicitly requires running `gh workflow run release-test.yml --ref main` against the actual `origin/main`. Currently `origin/main` is at `017eb04` (9 commits behind local). The fix cannot be observed until **CEO authorizes the push** (still pending). Manual Test cannot probe this themselves.
2. **Run team's slice is part of the same push.** The push will also deliver `fc79209` (Run team's pytest-adapter portability fix). The `ci.yml` re-trigger Release does post-push will exercise both fixes together — 9-cell green is the dual-DoD-closure observation. The two slices are independent in scope but co-dependent for full Phase 0 DoD #1 + #2 + #3 closure.
3. **No regression risk on existing CLI scenarios.** Same as the previous verification — adapter source and CLI surface are byte-equivalent. None of the coverage-cli-wiring scenarios need re-running.

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-release-test-pyapp-wrap-path.md` with:
- **Verdict:** `passed` if both YAML parse and suite-still-green succeed; otherwise `failed`.
- **What was tested:** brief narrative of the two checks and the eyeball read.
- **Issues found:** unlikely; flag anything unexpected.
- **Recommendations for PM:** none expected from this slice. The authoritative outcome (CI matrix + PyApp builds + install-script-e2e all green) is captured in Release team's post-observation handoff, not yours.

Keep findings short.
