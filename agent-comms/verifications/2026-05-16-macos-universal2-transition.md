---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: macos-universal2-transition
related:
  - handoffs/release-team-2026-05-16-macos-universal2-transition.md
  - tasks/release-team-2026-05-16-macos-universal2-transition.md
  - history/2026-05-16-phase0-closure-partial.md
---

# Verification request: macOS universal2 transition (3-cell matrix + lipo-fuse)

## Merged commit

- **Hash:** `09eda94` (rebased from worktree commit `b9d05ae` onto current main `32c09a0`; ff merge afterwards).
- **Title:** `ci(release): transition macOS to universal2 (drop macos-13)`
- **Scope:** Workflow matrix collapsed 4→3 cells. `macos-x86_64 / macos-13` dropped entirely. `macos-arm64 / macos-latest` renamed `macos-universal2 / macos-latest`. New `macos-universal2` cell does two cross-target `cargo build`s (`aarch64-apple-darwin` + `x86_64-apple-darwin`) plus `lipo -create` plus `lipo -archs` sanity (expected: `x86_64 arm64`). `scripts/install.sh::detect_target` collapsed: any `Darwin` host → `novetest-macos-universal2` (single artifact for both Apple Silicon and Intel; macOS picks the slice at exec time). `tests/release/test_install_script.py::_detect_target` mirrored. Linux paths unchanged. No source/unit/integration files touched.
- **Closes Phase 0 DoD #2 + #3 — PENDING green re-observation** (per task spec; the authoritative gate is Release team's post-merge GHA observation pass, see Critical edge cases below).
- **Diagnostic-first finding informs the design.** Release team probed PyApp v0.22.0 (`PYAPP_DISTRIBUTION_SOURCE` requires a single tarball URL) and `astral-sh/python-build-standalone` (per-arch tarballs only — no `universal2-apple-darwin` variant). Conclusion: PyApp does NOT natively support universal2; lipo-fuse is the only viable path. Recorded verbatim in handoff §"Diagnostic-first finding".

## Source handoffs consumed

- `agent-comms/handoffs/release-team-2026-05-16-macos-universal2-transition.md` — Release wrote this **directly to the main checkout's working tree** (untracked) rather than into their worktree, per their documented `Write`-blocked-by-isolation fallback (GOTCHAS.md). I staged it in the same comms commit as this verification — byte-equivalent to a worktree-resident handoff.

## Merge notes

- **Rebase required (not fast-forward from declared base).** Worktree was branched from `3df9ec2`; main had moved to `32c09a0` (coverage-show-diff + jest-adapter-phase1 plus their comms commits). Rebase of single commit `b9d05ae` onto `32c09a0` produced **one expected conflict in `WORKLOG.md`** — surgical resolution: kept all entries, macos-universal2 on top (newest), jest-adapter and coverage-show-diff below per the WORKLOG "newest on top" convention. No source/test conflicts (file scopes fully disjoint). New rebased hash: `09eda94`.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration tests/release` → **301 passed + 1 skipped** (267 baseline + 12 coverage-show-diff + 21 jest unit/integration + 3 tests/release; 1 skipped = jest integration test without Node.js). `uv run mypy --strict` → **clean** (50 source files). Both `release-test.yml` and `ci.yml` parse cleanly via `yaml.safe_load` on main.
- **Diff scope:** scope-clean — only `.github/workflows/release-test.yml`, `scripts/install.sh`, `tests/release/test_install_script.py`, WORKLOG. No source code, no unit tests, no integration tests, no pyproject.toml.
- **Handoff is `status: ready, verdict: pre-merge-pending-gha-observation`.** Release explicitly designed for post-merge supersede: they will write a follow-up addendum (or a fresh handoff) with the live workflow URLs + job conclusions filled into the `## Verification (remote, post-merge — PENDING)` table after re-trigger.

## What Manual Test can verify (very limited; real gate is GHA-side)

This slice has **zero user-facing impact** on the CLI. The authoritative verification is Release team's post-merge `gh workflow run release-test.yml --ref main` observation. Manual Test scope should be ≤10 minutes of local sanity checks.

### Spot-check 1 — Workflow YAMLs still parse on main

```sh
cd /home/yjshin/dev/Nove-Test
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml')); print('OK')"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"
```

Assert: both print `OK`.

### Spot-check 2 — `install.sh` is POSIX-clean

```sh
sh -n /home/yjshin/dev/Nove-Test/scripts/install.sh
dash -n /home/yjshin/dev/Nove-Test/scripts/install.sh 2>&1 || echo "dash not installed locally; sh -n is sufficient"
```

Assert: both exit 0 (or dash unavailable note). Confirms the install script's POSIX `/bin/sh` baseline holds.

### Spot-check 3 — `tests/release` still passes

```sh
cd /home/yjshin/dev/Nove-Test
uv run pytest -q tests/release
```

Assert: `3 passed`. Confirms `_detect_target` mirror didn't regress the existing release tests on Linux.

### Spot-check 4 — Eyeball the matrix collapse

Open `.github/workflows/release-test.yml`. Confirm:
- Matrix has exactly **3** `target` entries: `linux-x86_64`, `linux-aarch64`, `macos-universal2`.
- The `macos-13` runner is gone everywhere.
- The "Wrap wheel with PyApp" step has a shell-body conditional on `${{ matrix.target }}` — linux cells: single `cargo build --release`; macos cell: two cross-target builds + `lipo -create` + `lipo -archs` sanity.
- The "Install Rust toolchain (host)" step's `targets:` uses `${{ matrix.target == 'macos-universal2' && 'aarch64-apple-darwin,x86_64-apple-darwin' || '' }}`.

Open `scripts/install.sh`. Confirm:
- `detect_target` has any-Darwin → `_arch_id="universal2"` collapse (single binary name `novetest-macos-universal2`).
- Linux branch unchanged (still per-arch).

### Spot-check 5 — Full suite still passes (cross-cycle regression)

```sh
uv run pytest -q tests/unit tests/integration
```

Assert: `298 passed + 1 skipped`. (No Python change in this slice; should match jest-adapter-phase1 verification numbers exactly.)

## Critical edge cases

1. **Real gate is GHA-side. Manual Test cannot probe.** The lipo-fuse and `install-script-e2e` round-trip ONLY exercise on actual macOS runners. Push to origin/main is required before Release can re-trigger `release-test.yml` against the new YAML. Currently `origin/main` is **6 commits behind** local; CEO push authorization is the prerequisite.
2. **Phase 0 DoD #2 + #3 closure is pending observation.** This slice's claim is "code ready" — the actual DoD tick depends on:
   - 3 `build` jobs (`linux-x86_64`, `linux-aarch64`, `macos-universal2`) all `success`.
   - `install-script-e2e` `success` (FIRST time this job will run end-to-end; prior cycles were blocked by the stuck `macos-13` cell).
3. **Stuck prior workflow run.** Release flagged that the prior run `25955972426` has a `macos-x86_64` cell that will never complete (matrix entry no longer exists post-merge). PM may `gh run cancel 25955972426` to keep the runs list tidy. Not blocking.
4. **lipo-fuse complexity is load-bearing.** If a future PyApp release ships native universal2, the wrap step could simplify back to a single cargo build. The handoff §"Release-pipeline surprises" #1 explicitly asks not to delete the lipo-fuse comment when that day comes — keep the historical pointer.
5. **Cross-cycle envelope shape regression.** No CLI envelope change in this slice (it's CI-only). All prior verifications' assertions should still hold; Spot-check 5 confirms via the full suite.

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-macos-universal2-transition.md` with the standard format. The verdict applies ONLY to the local sanity checks; the authoritative DoD-closing observation belongs to Release team's post-observation addendum.

**Last of three slices merged this cycle** (coverage-show-diff, jest-adapter-phase1, macos-universal2-transition).
