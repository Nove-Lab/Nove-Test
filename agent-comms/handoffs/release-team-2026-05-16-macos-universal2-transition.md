---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready
verdict: pre-merge-pending-gha-observation
created: 2026-05-16
slug: macos-universal2-transition
related:
  - tasks/release-team-2026-05-16-macos-universal2-transition.md
  - history/2026-05-16-phase0-closure-partial.md
---

# Handoff: macOS universal2 transition — code ready, awaiting merge + GHA re-observation

## TL;DR

- Workflow matrix collapsed 4 cells → 3: dropped `macos-x86_64 / macos-13`
  entirely, renamed `macos-arm64 / macos-latest` to `macos-universal2 /
  macos-latest`. The lipo-fuse approach is the ONLY viable path with PyApp
  v0.22.0 (diagnostic-first finding: PyApp does NOT natively support
  universal2 because `astral-sh/python-build-standalone` publishes per-arch
  tarballs only — verified against `ofek/pyapp@v0.22.0/docs/config/distribution.md`
  + live API listing of the latest python-build-standalone release).
- `install.sh::detect_target` collapsed: any `Darwin` host →
  `novetest-macos-universal2`. Linux still per-arch. `tests/release/...::_detect_target`
  mirrored.
- Local sanity checks all green; live GHA verification (the only valid
  validation for cross-compile + lipo fuse + install-script-e2e
  round-trip) follows the merge + push.
- **Status: `ready` for Main Branch to merge + push.** Once on origin/main,
  I (Release) self-trigger `release-test.yml --ref main`, observe, and
  write a follow-up addendum / supersede this handoff with the
  comprehensive post-observation version.

## Worktree

- Path: `/home/yjshin/dev/novetest-macos-universal2-transition`
- Branch: `worktree-macos-universal2-transition`
- Base commit: `3df9ec2` (main at task pickup)
- Single commit: `b9d05ae ci(release): transition macOS to universal2 (drop macos-13)`
- 4 files changed, +65 / -20 lines.

## Files written / modified

Modified:
- `.github/workflows/release-test.yml` — matrix collapsed 4→3; dropped
  `macos-x86_64 / macos-13` and `macos-arm64`; added single
  `macos-universal2 / macos-latest` cell. `Install Rust toolchain (host)`
  step's `targets:` input now uses an inline matrix conditional —
  `aarch64-apple-darwin,x86_64-apple-darwin` for the macos-universal2 cell,
  empty for every other cell. `Wrap wheel with PyApp` step grew an in-shell
  branch on `${{ matrix.target }}`: linux cells stay at `cargo build
  --release`, the macos cell does two cross-target cargo builds plus
  `lipo -create` plus `lipo -archs` sanity check (expected output:
  `x86_64 arm64`). All inline comments record the rationale so the next
  agent doesn't simplify the fuse away.
- `scripts/install.sh` — `detect_target` collapsed the macOS arch logic.
  Any `Darwin` host (Apple Silicon or Intel) now resolves to
  `_arch_id="universal2"`. Linux case unchanged. Error message for
  unsupported Linux arch updated to mention macOS universal2.
- `tests/release/test_install_script.py` — `_detect_target` mirrors the
  same macOS-universal2 collapse so the 3 happy-path / idempotent /
  tampered-binary tests keep working on macOS dev hosts. Linux path
  unchanged.

Created:
- `WORKLOG.md` entry — `2026-05-16 — phase0 / macos-universal2-transition`
  with the Landed / Verified / Left open / Gotcha / Next sections.

No other files touched: `src/**`, `tests/unit/**`, `tests/integration/**`,
`tests/fixtures/**`, `pyproject.toml`, `ci.yml`,
`design/implementation-plan/**`, `agent-comms/decisions/**`, `history/**`
all untouched per task out-of-scope contract.

## Diagnostic-first finding (informs the lipo-fuse choice)

Task spec called for a PyApp universal2 feasibility check BEFORE coding.
Two probes:

1. **PyApp `PYAPP_DISTRIBUTION_SOURCE` semantics** (via
   `https://api.github.com/repos/ofek/pyapp/contents/docs/config/distribution.md?ref=v0.22.0`):
   the option overrides `PYAPP_PYTHON_VERSION` with a *single tarball
   URL*. PyApp does not fuse multi-arch sources internally.
2. **python-build-standalone upstream artifacts** (via
   `https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest`):
   the latest release publishes per-arch tarballs only —
   `cpython-3.X.Y+...-aarch64-apple-darwin-install_only.tar.gz` and
   `cpython-3.X.Y+...-x86_64-apple-darwin-install_only.tar.gz`. No
   `universal2-apple-darwin` variant exists.

Conclusion: the task spec's "Option 1 (direct env-var)" is **not viable**
with PyApp v0.22.0. lipo-fuse fallback is the only path forward and is
implemented as such. No `agent-comms/questions/` written because the
fallback path was explicitly authorized in the task spec.

## Verification (local, pre-merge)

```sh
$ python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"
# → YAML parse OK

$ sh -n scripts/install.sh
# → OK (POSIX baseline)

$ dash -n scripts/install.sh
# → OK (Debian /bin/sh — the install script's strictest dependency)

$ uv run pytest -q tests/release
# → 3 passed in 1.67s
#   (Linux host: _detect_target() returns "linux-x86_64"; the macOS-universal2
#    code path is exercised only on a Darwin host or by the post-merge
#    install-script-e2e GHA job.)
```

NOT verified locally (intentionally — these require macOS runners):
- `cargo build --release --target x86_64-apple-darwin` from an arm64 host
  (needs Apple's universal toolchain; macos-latest ships it).
- `lipo -create` correctly fusing two PyApp wraps.
- `install-script-e2e` round-trip on actual artifact.

Live GHA observation is the only valid validation; it runs after merge.

## Verification (remote, post-merge — PENDING)

This section will be filled in by Release team after Main Branch merges
+ pushes and the `release-test.yml --ref main` re-trigger completes.
Expected shape:

| Job | Conclusion | Notes |
|---|---|---|
| `build (linux-x86_64)` | TBD | Should be unchanged from prior cycle (single cargo build, sidecar, smoke) |
| `build (linux-aarch64)` | TBD | Same |
| `build (macos-universal2)` | TBD | NEW: two cross-target cargo builds + `lipo -create` + `lipo -archs` (expect `x86_64 arm64`) |
| `install-script-e2e` | TBD | First time this job will actually run end-to-end (prior cycles blocked by stuck macos-13 cell) |

Workflow URL: TBD (will be `https://github.com/Nove-Lab/Nove-Test/actions/runs/<id>`)

## DoD bullets believed closed

**Pre-merge: none.** Code is ready but live GHA observation has not yet
run. The post-merge addendum will name:

- Phase 0, bullet #2 (re-confirmed under the new 3-cell matrix shape)
- Phase 0, bullet #3 (`install-script-e2e` job green end-to-end —
  **first observation since Phase 0 inception**)

Together these mark Phase 0 fully closed for the first time — but only
after the live observation confirms.

## Worklog

`WORKLOG.md` entry written and staged in this commit per
`check-worklog-before-commit.sh` hook requirement (this slice touches
`tests/release/test_install_script.py`).

## Coordination notes for Main Branch

- **Other in-flight worktrees this cycle**: `worktree-coverage-show-diff`
  (Orchestration) and `worktree-run-team-jest-adapter-phase1` (Run).
  Both touch disjoint file scopes (`src/novetest/orchestration/`,
  `src/novetest/run/adapters/`, `tests/unit/**`) from this slice
  (`.github/workflows/release-test.yml`, `scripts/install.sh`,
  `tests/release/`). Merge order is flexible; no conflicts anticipated.
- **Push to origin is required before Release can self-trigger**
  `release-test.yml --ref main` — the workflow reads the YAML from
  origin/main, not local. The prior cycle's experience: Main Branch's
  merge step landed on local main but did not push by default; CEO had
  to instruct an explicit push. Flagging in case the dispatch
  convention has been clarified since then.
- After push, ping CEO so Release proceeds with the re-trigger +
  observation phase.

## Release-pipeline surprises

1. **PyApp's lack of native universal2 support is the load-bearing
   pivot.** If a future PyApp release ships native universal2 (e.g.
   via a synthetic `PYAPP_DISTRIBUTION_VARIANT=universal2` or a
   meta-tarball convention), the workflow `Wrap wheel with PyApp` step
   could simplify back to a single `cargo build --release`. Keep the
   lipo-fuse comment as a historical pointer if/when that happens.
2. **`dtolnay/rust-toolchain@stable`'s `targets:` input accepts an
   empty string and skips the add.** That's what makes the inline
   matrix conditional `${{ matrix.target == 'macos-universal2' && '...'
   || '' }}` work without an extra `if:` step. Documented because the
   pattern isn't obvious from the action's README.
3. **macOS picks Mach-O slices at exec time, not at download time.**
   This is why a single `novetest-macos-universal2` artifact is correct
   for both Apple Silicon and Intel users — install.sh doesn't need to
   know the host arch, it just hands the file to `/usr/local/bin` and
   macOS takes care of the slice selection on the first `novetest`
   invocation. The slice-specific PyApp wrap then fetches the matching
   python-build-standalone tarball on first run.
4. **The prior stuck run (`25955972426`) is now permanently moot.** Its
   `macos-x86_64` cell will never complete because the matrix no longer
   exists post-merge. PM may cancel it (`gh run cancel 25955972426`) to
   keep the runs list tidy.

## Fallback note

`Write` tool was blocked by the documented worktree-isolation handshake
issue (see `GOTCHAS.md` → "Write / Edit blocked by worktree isolation
handshake"). Used the sanctioned `cat > ... <<EOF` heredoc fallback via
`Bash`. Byte-identical output. No deliverable impact.
