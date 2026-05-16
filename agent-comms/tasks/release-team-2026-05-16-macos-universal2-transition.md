---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-16
slug: macos-universal2-transition
related:
  - history/2026-05-16-phase0-closure-partial.md
---

# Task: Transition macOS targets to `macos-universal2` (drop macos-13 dependency)

## Scope / Mission

Phase 0 DoD #3 (`curl-pipe-sh` end-to-end) is deferred because the
`release-test.yml` `macos-x86_64` build cell sits queued for 6+ hours on
GHA's saturated `macos-13` runner pool. Wait is indefinite — GitHub is
deprecating macos-13. This task **eliminates the macos-13 dependency
entirely** by transitioning to a single `macos-universal2` artifact
wrapped on the `macos-arm64` runner (fast, never queues).

Two-part change:

1. **Workflow YAML** — drop `macos-x86_64` matrix entry from
   `release-test.yml`; rename `macos-arm64` to `macos-universal2` and
   make PyApp produce a fat binary covering both architectures.
2. **install.sh** — collapse macOS arch detection so any `Darwin`
   (regardless of `x86_64` / `arm64` uname) downloads
   `novetest-macos-universal2`.

Then merge → self-trigger `release-test.yml` → observe 3 build jobs
(`linux-x86_64`, `linux-aarch64`, `macos-universal2`) + `install-script-e2e`
all green. Closes Phase 0 DoD #3 (and reconfirms DoD #2 under the new
matrix shape).

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/history/2026-05-16-phase0-closure-partial.md` — full
   context for why the universal2 transition is the right answer
4. `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` —
   URL principle (unchanged)
5. `agent-comms/tasks/release-team-2026-05-16-macos-universal2-transition.md`
   (this file)
6. `WORKLOG.md` top 3 entries
7. `design/implementation-plan/foundations.md` §7 (Distribution) — note
   the current Tier-1 target list (linux-x86_64, linux-aarch64,
   macos-x86_64, macos-arm64); this task changes the macOS slice
8. `design/implementation-plan/delivery-phasing.md` Phase 0 DoD #2, #3
9. `.github/workflows/release-test.yml` — your edit target
10. `scripts/install.sh` — your second edit target

## Implementation approach

### PyApp universal2 — verify the path before coding

PyApp v0.22.0 builds via `cargo build --release` against a
python-build-standalone distribution. The standalone project ships
universal2 builds (e.g.
`cpython-3.X.Y+YYYYMMDD-universal2-apple-darwin-install_only.tar.gz`).
PyApp's `PYAPP_DISTRIBUTION_SOURCE` env var lets you pin the exact
URL.

**First diagnostic step (do this before coding):**

1. Check PyApp v0.22.0 docs / release notes for native universal2
   support — does setting `PYAPP_DISTRIBUTION_SOURCE` to a universal2
   tarball + building on `macos-latest` (arm64) produce a working
   universal2 binary directly? (Most likely yes.)
2. If yes: single-step build. Set the env var, drop the macos-13 cell,
   rename macos-arm64 → macos-universal2. Done.
3. If no (PyApp wraps single-arch only): fallback path is `lipo
   -create` to fuse two single-arch binaries. That requires keeping
   both x86_64 and arm64 build cells **on macos-latest** (which can
   cross-compile both via the Apple toolchain) and stitching after
   the fact. Adds 1 extra step + ~30s lipo invocation.

If PyApp does not natively support universal2 even via the env var,
**STOP and write `agent-comms/questions/release-team-2026-05-16-pyapp-universal2-support.md`**
asking PM to decide between (a) `lipo` fusion approach or (b) revert
to wait-on-macos-13. PM will route.

PM recommendation: try (1) first; the env-var route is the simplest
shape and matches how PyApp documents distribution overrides.

### Workflow YAML changes

In `.github/workflows/release-test.yml`:

- Matrix entries:
  - **Remove** `macos-x86_64` cell (and its `runner: macos-13`).
  - **Rename** `macos-arm64` → `macos-universal2`. Keep `runner: macos-latest`.
- Inside the `macos-universal2` cell's "Wrap wheel with PyApp" step
  (or a guarded inner step), set
  `PYAPP_DISTRIBUTION_SOURCE` to the universal2 tarball URL (resolve
  the exact URL via `PYAPP_PYTHON_VERSION` substitution — the
  python-build-standalone release scheme is documented).
- `install-script-e2e` job: still downloads
  `novetest-linux-x86_64`-named artifact for its smoke (unchanged) —
  this job is Linux-only by design.
- Sidecar generation step (`Compute SHA-256 sidecar`): no changes
  needed; it uses `${{ matrix.target }}` which becomes
  `macos-universal2` naturally.

If the `lipo` fallback is required, you'll keep both
`macos-x86_64-stage` and `macos-arm64-stage` cells **on `macos-latest`**
(not macos-13!) and add a third `macos-universal2-fuse` job that
downloads both staged artifacts, runs `lipo -create -output
novetest-macos-universal2 novetest-macos-x86_64-stage
novetest-macos-arm64-stage`, computes its own sidecar, and uploads the
final universal2 artifact. Document the choice in your handoff.

### install.sh changes

In `scripts/install.sh`:

- Current macOS arch branch (around lines 58-71) does:
  - `Darwin` → `_os_id="macos"`
  - `x86_64|amd64` → `_arch_id="x86_64"`
  - `aarch64|arm64` → `_arch_id="aarch64"` then `if macos+aarch64 then arm64`
  - Resulting binary name: `novetest-macos-x86_64` or `novetest-macos-arm64`
- Change to: any `Darwin` (regardless of arch) sets the final binary name
  to `novetest-macos-universal2`. Linux branch stays unchanged.
- Keep the existing arch-detect logic for Linux (`x86_64`, `aarch64`).
- Update the inline comment block that documents the supported arch
  matrix to reflect the new macOS shape (one universal2 binary covers
  both Apple Silicon and Intel Macs).

`tests/release/test_install_script.py` already exercises the script's
logic against a stub binary. If your install.sh change breaks any
existing assertion, fix the test alongside. (Spot-check: the test
uses `NOVETEST_INSTALL_*` env overrides for the binary URL; arch
detection should still work, but verify by running
`uv run pytest -q tests/release` locally.)

## Files to write / modify

- `.github/workflows/release-test.yml` — matrix + wrap step changes
  (or +lipo fuse job if fallback path).
- `scripts/install.sh` — macOS arch detection collapse.
- `tests/release/test_install_script.py` — only if the install.sh
  change breaks the local mock-binary tests.
- `agent-comms/handoffs/release-team-2026-05-16-macos-universal2-transition.md`
  (final output, post-observation).
- `agent-comms/questions/release-team-2026-05-16-pyapp-universal2-support.md`
  (only if PyApp's native universal2 path is unclear and you need
  PM guidance on the lipo fallback).

## Files NOT to touch

- `src/**`, `tests/unit/**`, `tests/integration/**` — out of scope.
- `tests/fixtures/projects/**` — engine teams own.
- `.github/workflows/ci.yml` — handled separately (currently passing
  with the Run team's fix; do not modify).
- `pyproject.toml` — no dep changes.
- `design/implementation-plan/foundations.md` — propose any §7
  wording update via PM after this slice lands; do not edit directly.
- `agent-comms/decisions/**`, `history/**` — PM only.

## Verification commands

### Local (pre-merge)

```sh
# YAML still parses
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml')); print('OK')"

# install.sh executes under dash without errors (POSIX-sh portability)
sh -n scripts/install.sh

# Existing install-script tests pass with the new macOS detection
uv run pytest -q tests/release
```

### Remote (post-merge)

```sh
gh workflow run release-test.yml --ref main --repo Nove-Lab/Nove-Test
# Poll (per history learning #2 — use json status, not gh run watch):
until gh run view <run-id> --json status -q '.status' | grep -q completed; do sleep 30; done
gh run view <run-id> --json conclusion,jobs
```

## Green-pass criteria

| DoD bullet | Observation required |
|---|---|
| #2 (re-confirm) | All build jobs (`linux-x86_64`, `linux-aarch64`, `macos-universal2`) `success`; each produces a `novetest-<target>` artifact + `.sha256` sidecar. |
| #3 (close) | `install-script-e2e` job `success`; log shows `novetest --version` invocation green against the just-built linux-x86_64 binary. |

The macOS universal2 binary should also be smoke-testable: in the
build job, after PyApp wrap, add a `lipo -archs novetest-macos-universal2`
check that prints both `x86_64 arm64` archs. (Optional but cheap, and
proves the universal2 fuse worked end-to-end.)

## If RED

Per task convention (one fix attempt per task): do NOT iterate the YAML
in-flight. Capture the failure, write the handoff with
`status: blocked / verdict: failed`, document the new root cause
hypothesis. PM routes a follow-up.

## DoD bullets to claim closed

In the handoff's "DoD bullets believed closed" list, name:

- **Phase 0, bullet #2** (re-confirmed under new matrix shape — 3-cell
  green all-arch coverage)
- **Phase 0, bullet #3** (closed — install-script-e2e job green)

Together these mark **Phase 0 fully closed** for the first time. Note
that in your handoff.

## Reporting (handoff)

Write `agent-comms/handoffs/release-team-2026-05-16-macos-universal2-transition.md`
with the standard handoff body sections. Capture:

- Worktree path + branch + base commit (workflow YAML edits are normal
  worktree → main merge — coordinate via Main Branch).
- Files written/modified.
- PyApp universal2 approach chosen (direct via env-var vs lipo fuse).
- Local pre-merge checks.
- Workflow run URL + conclusion.
- Per-job conclusions for all build cells + install-script-e2e.
- `lipo -archs` output for the universal2 binary if you added the
  smoke step.
- DoD bullets believed closed (see above).
- Open items / surprises.
- No WORKLOG entry needed (no `src/` or `tests/` impact, except
  conditionally `tests/release/`; if that test was modified, append a
  WORKLOG entry per format).

When the handoff is written, run `python3 tools/regen_comms_index.py`.

## Out of scope (do NOT do these in this task)

- Add Windows support (`install.ps1`, windows-x86_64 PyApp wrap) —
  OQ #16, post-MVP.
- Bump PyApp version.
- Wire `ailovestesting.com/novetest/install.sh` DNS redirect (separate
  CEO task).
- Edit `ci.yml`.
- Touch `src/**`, `pyproject.toml`.
- Pre-emptively add `actions/cache` for cargo — runner cache is warm
  per the prior cycle's observation; do not add unless this iteration
  shows a need.

## Why this task exists

The prior cycle's Release fix verified the YAML wrap-path bug repair
on 3 of 4 PyApp targets (linux-x86_64, linux-aarch64, macos-arm64), all
running the identical step. The 4th (macos-x86_64) is blocked on GHA
infrastructure, not on our code. Waiting is indefinite given macos-13's
deprecation trajectory. Switching to universal2 is the only path that
makes Phase 0 closeable on a predictable timeline and simplifies the
shipping matrix from 4 macOS targets to 1. Phase 0 has been the project's
longest-running open phase; closing it unblocks downstream phases'
attention.
