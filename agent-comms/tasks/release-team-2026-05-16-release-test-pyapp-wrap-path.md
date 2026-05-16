---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-16
slug: release-test-pyapp-wrap-path
related:
  - history/2026-05-16-phase0-gha-attempt-red.md
---

# Task: Fix `release-test.yml` Wrap-wheel path bug + re-observe

## Scope / Mission

The "Wrap wheel with PyApp" step in `.github/workflows/release-test.yml`
captures the wheel path as **relative to `${{ github.workspace }}/dist`**,
then `cd pyapp-src` invalidates that relative path before `cargo build`
runs PyApp's `build.rs`. PyApp panics with
`Project path is not a file: dist/novetest-0.0.0-py3-none-any.whl`.
All 4 PyApp build matrix jobs (linux-x86_64, linux-aarch64, macos-x86_64,
macos-arm64) fail at this step in run `25954755663`;
`install-script-e2e` auto-SKIPS via `needs: build`.

Two-part task:

1. **Fix the YAML** — capture the wheel path as absolute *before* the
   `cd`, so PyApp's `build.rs` resolves it regardless of cwd.
2. **Re-trigger and observe** — after the fix merges, `gh workflow run
   release-test.yml --ref main`, watch all 4 PyApp build jobs green +
   `install-script-e2e` job green, report URLs and conclusions.

Closes Phase 0 DoD #2 (signed binary builds on release-test) and #3
(curl-pipe-sh end-to-end) in one task. DoD #1 (CI matrix) is handled
in parallel by the Run team task in this same cycle.

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/history/2026-05-16-phase0-gha-attempt-red.md` —
   full RED diagnosis including the exact lines that fail and a
   suggested fix
4. `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` —
   binding install URL principle (unchanged by this task)
5. `agent-comms/tasks/release-team-2026-05-16-release-test-pyapp-wrap-path.md`
   (this file)
6. `WORKLOG.md` top 3 entries — Phase 0 release slice (`74a6ce4`)
   landed this workflow
7. `design/implementation-plan/delivery-phasing.md` Phase 0 DoD #2, #3
8. `.github/workflows/release-test.yml` — your single source of edit;
   pay particular attention to lines ~109-127, the "Wrap wheel with
   PyApp" step

## Diagnosed failure (verbatim from history)

```yaml
# .github/workflows/release-test.yml lines 109-127
- name: Wrap wheel with PyApp
  env:
    PYAPP_PROJECT_PATH: ${{ github.workspace }}/dist   # points at a *directory*
    ...
  run: |
    set -eu
    wheel="$(ls dist/novetest-*-py3-none-any.whl | head -n1)"   # ← RELATIVE
    export PYAPP_PROJECT_PATH="$wheel"
    cd pyapp-src                                                # ← breaks the relative path
    cargo build --release                                       # ← sees `dist/novetest-...` from inside `pyapp-src/`
```

Error from run `25954755663` (all 4 matrix children):

```
error: failed to run custom build command for `pyapp v0.22.0`
Caused by:
  thread 'main' panicked at build.rs:434:13:
  Project path is not a file: dist/novetest-0.0.0-py3-none-any.whl
```

## Suggested fix (from Release team's own diagnosis)

```sh
wheel="$(ls "$GITHUB_WORKSPACE/dist/"novetest-*-py3-none-any.whl | head -n1)"
export PYAPP_PROJECT_PATH="$wheel"
cd pyapp-src
cargo build --release
```

Or equivalently, `realpath dist/novetest-*.whl` before the `cd`. You
own the YAML; pick the form you prefer. The constraint is: the
`PYAPP_PROJECT_PATH` value the cargo build sees must be a single
absolute path to the wheel.

Also consider deleting (or rewriting) the env-block's
`PYAPP_PROJECT_PATH: ${{ github.workspace }}/dist` — it points at a
*directory* and is shadowed by the shell body's `export`, but its
presence is misleading. The cleanest form is: drop the env entry
and `export PYAPP_PROJECT_PATH="$wheel"` in the shell.

## Files to write / modify

- `.github/workflows/release-test.yml` — fix the "Wrap wheel with
  PyApp" step per above. No other workflow changes.

## Files NOT to touch

- `src/**`, `tests/**` — separate Run task handles the CI test bug in
  parallel.
- `scripts/install.sh` — the script logic is sound (validated by
  `tests/release/test_install_script.py` last cycle); this task does
  not touch it.
- `pyproject.toml` — no dep changes.
- `.github/workflows/ci.yml` — Run team's test fix closes DoD #1; you
  do not edit ci.yml.
- `agent-comms/decisions/**`, `history/**` — PM only.

## Verification commands

### Local (before merge)

```sh
# YAML parses cleanly
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"

# Sanity: review the rewritten step
sed -n '/Wrap wheel with PyApp/,/Compute SHA-256 sidecar/p' .github/workflows/release-test.yml
```

You CANNOT exercise PyApp locally in this iteration loop — the
verification IS the post-merge GHA observation.

### Remote (after merge)

```sh
gh auth status
gh workflow run release-test.yml --ref main --repo Nove-Lab/Nove-Test
# wait for the run to be queued, then:
gh run list --workflow=release-test.yml --branch=main --limit 3
# poll the run until conclusion:
gh run view <run-id> --json status,conclusion,jobs
# (use `until` loop with sleep 30 rather than `gh run watch` per
#  history learning #3)
```

## Green-pass criteria

Both required, captured per Run/job in your handoff:

| DoD bullet (Phase 0) | Observation required |
|---|---|
| #2 Signed binary builds on release-test | All 4 PyApp matrix jobs `success`; artifact list includes the wheel-wrap binary + `.sha256` sidecar per target |
| #3 curl-pipe-sh end-to-end | `install-script-e2e` job `success`; log shows `novetest --version` invocation green against the just-built linux-x86_64 binary |

For each bullet, capture:
- The workflow run URL
- The conclusion (`success`)
- A 1-2 line excerpt from the relevant log section (proof)

## If still RED

If the rewritten step still fails, capture:
- New error message (full panic / stderr if cargo, or whatever cuts
  it short)
- The run URL + failing job IDs
- Write the handoff with `status: blocked / verdict: failed` and a
  fresh root-cause hypothesis. PM will route a second-iteration
  follow-up. **Do NOT iterate the workflow YAML inside this task** —
  one fix attempt per task keeps the diagnostic loop tight. Optional
  optimization mentioned in the history: add `actions/cache` for
  `~/.cargo` + `pyapp-src/target/` to shorten cargo-rebuild iteration
  time. Defer unless the first fix attempt also requires another
  iteration.

## DoD bullets you should claim closed

In your handoff's "DoD bullets believed closed" list, name:

- **Phase 0, bullet #2** — "A signed binary builds on the
  `release-test` workflow."
- **Phase 0, bullet #3** — "`curl-pipe-sh` end-to-end produces a
  working `novetest --version` on a clean Linux container and a clean
  macOS runner."

Both contingent on the post-fix re-trigger showing green. If either
job is still RED, claim only the ones that closed.

## Reporting (handoff)

Write `agent-comms/handoffs/release-team-2026-05-16-release-test-pyapp-wrap-path.md`
with the standard handoff body sections:

- Worktree path + branch + base commit (workflow YAML edits are
  normal worktree → main merge — coordinate via Main Branch).
- Files written/modified (final list).
- Local YAML parse confirmation.
- Workflow run URL + conclusion per workflow (post-merge re-trigger).
- Conclusion per matrix job.
- DoD bullets believed closed (see above).
- Open items / surprises (especially anything the cargo cache should
  inherit for the next CI/release iteration).
- No WORKLOG entry needed (this task does not modify `src/` or
  `tests/`).

When the handoff is written, run `python3 tools/regen_comms_index.py`.

## Out of scope (do NOT do these in this task)

- Touch `src/**`, `tests/**`, `pyproject.toml`, `scripts/install.sh`,
  `ci.yml`.
- Bump PyApp version (currently pinned to `0.22.0`).
- Wire `ailovestesting.com/novetest/install.sh` DNS redirect (separate
  CEO task).
- Write `install.ps1` for Windows (OQ #16, post-MVP).
- Iterate the workflow more than once (capture failure → handoff →
  PM routes follow-up).

## Why this task exists

Identical root-cause story to the Run team's parallel task: the Phase
0 release-tooling slice landed without ever observing the PyApp wrap
on real GHA. The Release team's own observation pass in the previous
cycle surfaced both the bug AND the diagnosis. This task closes the
workflow-side fix; combined with the Run team's parallel test fix,
Phase 0 closes for real after both green observations land.
