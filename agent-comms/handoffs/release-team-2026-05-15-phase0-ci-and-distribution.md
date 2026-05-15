---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-15
slug: phase0-ci-and-distribution
related: [release-team-2026-05-14-phase0-ci-and-distribution.md]
---

# Handoff: Phase 0 CI matrix + PyApp release-test pipeline + install.sh

All three slices (A, B, C) from the task land together in this worktree.
Slice A is the must-have; Slices B and C exercise each other end-to-end via
the `install-script-e2e` job inside `release-test.yml`, so it was cleaner to
ship them as one slice than to split.

## Worktree

- **Path:** `../Nove-Test-release-phase0/`
- **Branch:** `worktree-phase0-release-ci-and-distribution`
- **Base commit:** `fe28479` (`docs: resolve OQ#15 — install script hosting URL`)
- **Working state:** clean except for the new files listed below; `main` worktree at
  `/home/yjshin/dev/aispace/Nove-Test/` is untouched (no rebase needed).

## Files written / modified

New files only — no edits to `src/`, no edits to existing tests, no edits to
`pyproject.toml`:

- `.github/workflows/ci.yml` — 9-cell matrix (Linux/macOS/Windows × Python
  3.11/3.12/3.13). Steps: `astral-sh/setup-uv@v3` → `uv sync --dev --frozen`
  → `uv run pytest -q` → `uv run mypy` → (Linux/macOS only) `uv run pytest -q
  tests/release`. windows-arm64 gap documented in a top-of-file comment per
  the Phase 0 risk note.
- `.github/workflows/release-test.yml` — tag-`v*` and `workflow_dispatch`
  triggers. Per-target build matrix (`linux-x86_64` on `ubuntu-latest`,
  `linux-aarch64` on `ubuntu-22.04-arm`, `macos-x86_64` on `macos-13`,
  `macos-arm64` on `macos-latest`). Each cell does `uv build --wheel` →
  download PyApp v0.22.0 source → `cargo build --release` with PyApp env
  vars → emit `<bin>` + `<bin>.sha256`. A follow-on `install-script-e2e`
  job downloads the linux-x86_64 artifact, serves it on localhost, and
  runs `scripts/install.sh` twice (clean install + idempotent re-run). On
  tag push only, a draft GitHub Release is created via
  `softprops/action-gh-release@v2`.
- `scripts/install.sh` — POSIX sh (verified under `dash`). OS+arch detect
  → URL compose → curl/wget download → SHA-256 verify via
  `sha256sum`/`shasum -a 256`/`openssl dgst` fallback → loud abort on
  mismatch (writes nothing under `$PREFIX`) → atomic `cp + rename(2)`
  install → PATH hint. Overridable via `NOVETEST_INSTALL_{REPO,VERSION,BASE_URL,PREFIX}`.
- `tests/release/__init__.py` (empty, matches existing test-subdir convention).
- `tests/release/test_install_script.py` — 3 tests using a localhost
  `http.server` fixture: happy path; idempotent re-run; tampered-binary
  loud abort. Skipped on Windows (POSIX sh required).
- `WORKLOG.md` — new top entry `## 2026-05-15 — phase0 / release-ci-and-distribution`.
- `agent-comms/handoffs/release-team-2026-05-15-phase0-ci-and-distribution.md`
  (this file).
- `agent-comms/INDEX.md` — regenerated.

## Verification result

Local (in the worktree, on this Linux x86_64 host):

| Command | Result |
| --- | --- |
| `uv run pytest -q` | **185 passed** in 5.91s (baseline preserved — release tests are out of default `testpaths`) |
| `uv run mypy` | **clean** (41 source files, `--strict`) |
| `uv run pytest -q tests/release` | **3 passed** in 1.63s |
| `python3 -c 'import yaml; yaml.safe_load(...)'` on both workflow YAMLs | parse OK |
| Manual smoke under `/usr/bin/dash` against a localhost `python3 -m http.server` fixture | download → SHA verify → install → executable runs ("stub novetest 0.0.0") + PATH hint emitted |

**NOT verified locally** (requires real GitHub Actions; a 1M-context sandbox
cannot push and observe live workflow runs):

- The 9-cell CI matrix actually green on real GHA runners (DoD #1).
- The PyApp wrap actually produces a working binary per target (DoD #2).
- The `install-script-e2e` job inside `release-test.yml` actually
  round-trips against the real PyApp-wrapped binary (DoD #3).

These three checks land on Main Branch / CEO post-merge: push to `main`
triggers `ci.yml`; tagging `v0.0.1-rc0` (or running `release-test.yml` via
`workflow_dispatch`) triggers `release-test.yml`. PM should tick the four
Phase 0 DoD bullets only after both runs are observed green.

## DoD bullets believed closed

Mapping to the unchecked Phase 0 bullets in
`design/implementation-plan/delivery-phasing.md`:

1. **`uv run pytest -q` green on all three OSes and three Python versions.**
   Authored by `.github/workflows/ci.yml` (3×3 matrix). *Believed closed
   pending live GHA observation*; the local baseline (185 passed) and the
   parametric matrix shape are sound.
2. **A signed binary builds on the `release-test` workflow.** Authored by
   `.github/workflows/release-test.yml` (PyApp build per target + `.sha256`
   sidecar per artifact). "Signed" interpreted as **SHA-256-checksum-signed**
   per Phase 0 scope; Apple Developer ID / Windows Authenticode is post-MVP.
   *Believed closed pending the first live `release-test` run.*
3. **`curl ... | sh` end-to-end produces a working `novetest --version` on a
   clean Linux container and a clean macOS runner; re-running upgrades in
   place.** Authored by `scripts/install.sh` + the `install-script-e2e` job
   inside `release-test.yml` (which exercises a clean GHA Linux runner →
   download via the script → `novetest --version` → re-run for idempotence).
   *Believed closed pending the first live `release-test` run.* The
   "clean macOS runner" half of the bullet is *not* directly exercised by
   this slice's e2e job (which runs on `ubuntu-latest` only); macOS coverage
   piggybacks on the per-target build matrix's smoke step in `release-test.yml`
   (`./out/novetest-${target} --version --output json`).
4. **The install script verifies SHA-256 and aborts loudly on mismatch;
   covered by an integration test that intentionally serves a tampered
   binary.** Authored by `tests/release/test_install_script.py`
   (`test_install_aborts_loudly_when_sha256_mismatches`); also re-exercised
   by the `install-script-e2e` job's happy half. **Locally verified.**
   *Believed closed.*

## Open items / surprises

- **Real-GHA validation gap.** Items 1–3 above cannot be ticked from local
  observation alone. PM should sequence: merge → CEO observes `ci.yml`
  green on the merge commit → CEO triggers `release-test.yml` via
  `workflow_dispatch` (or pushes a `v0.0.1-rc0` tag) → CEO observes that
  workflow green including the `install-script-e2e` job → PM ticks 1–3.
  Item 4 is locally verified and can be ticked at PM's discretion.
- **PyApp v0.22.0 is a placeholder pin.** I could not verify against the
  current PyApp release feed from this sandbox. If `0.22.0` does not exist
  or has a different source.tar.gz layout, the `Download PyApp source` step
  in `release-test.yml` will fail loudly — bump to the latest PyApp tag and
  reconfirm. The version is centralized in `env.PYAPP_VERSION_DEFAULT` (and
  overridable via the `workflow_dispatch` input) so the bump is one line.
- **`ailovestesting.com/novetest/install.sh` redirect is CEO action.** Per
  `decisions/2026-05-14-install-script-hosting-url.md` rollout note, the
  in-repo script keeps `scripts/install.sh`; the public URL is wired by
  CEO before MVP launch. Today's install command is the raw GitHub URL
  (`https://raw.githubusercontent.com/<org>/novetest/main/scripts/install.sh`)
  per the decision's rollout step 1. README does not yet document either
  URL — that is a follow-up doc task PM can route after the redirect lands.
- **Repo path hard-coded to `nove/novetest`.** `install.sh` defaults
  `NOVETEST_INSTALL_REPO` to `nove/novetest` (matches the example in
  `foundations.md` §7). If the canonical GitHub org/repo name differs at
  release time, override via the env var or update the default. No code
  here references `ailovestesting.com` directly — that domain is purely
  the user-facing redirect host, not a download origin.
- **Windows `install.ps1` parity is OQ#16 / post-MVP** — not in this
  slice. The CI matrix already covers Windows for the unit/integration
  test gate; only the install-script half is non-Windows.
- **Coordination with Run Team's `pytest-coverage-emission` slice.** That
  task adds `pytest-cov` and `coverage[toml]>=7.0` to `[dependency-groups]
  .dev`. This slice does **not** touch `pyproject.toml`, so the merge is a
  clean union — Main Branch should have no conflict to resolve there.
- **No new production deps were added** (per the charter's "No production
  dep additions without PM ack" rule). No dev deps either; `pyproject.toml`
  is byte-identical to `main`.

## Worklog entry text

Pasted verbatim into `WORKLOG.md` top-of-file (already staged in this worktree):

```
## 2026-05-15 — phase0 / release-ci-and-distribution

- Landed: `.github/workflows/ci.yml` (9-cell matrix — Linux/macOS/Windows × Python 3.11/3.12/3.13 — running `uv sync --dev --frozen` + `uv run pytest -q` + `uv run mypy`; Linux/macOS additionally run `uv run pytest -q tests/release`); `.github/workflows/release-test.yml` (tag-`v*` / `workflow_dispatch` trigger, per-target PyApp build matrix linux-x86_64 / linux-aarch64 / macos-x86_64 / macos-arm64 via `uv build --wheel` → PyApp source tarball wrap with `cargo build --release` → `.sha256` sidecar per artifact via `sha256sum`/`shasum -a 256`, in-workflow `install-script-e2e` job that downloads the just-built linux-x86_64 artifact, serves it on localhost, runs `scripts/install.sh` twice for idempotence; draft-Release-on-tag via `softprops/action-gh-release@v2` skipped for `workflow_dispatch`); `scripts/install.sh` (POSIX sh — verified under `dash` — detects OS+arch into `linux-{x86_64,aarch64}` / `macos-{x86_64,arm64}`, downloads binary + `.sha256` sidecar to `mktemp -d`, verifies via `sha256sum` / `shasum -a 256` / `openssl dgst` fallback chain, **loudly aborts on mismatch with both digests and the source URL on stderr and writes nothing under `$PREFIX`**, on match installs via stage-then-`mv` for `rename(2)` atomicity, prints PATH hint, idempotent; overridable via `NOVETEST_INSTALL_{REPO,VERSION,BASE_URL,PREFIX}` for tests and mirror operators); `tests/release/__init__.py` + `tests/release/test_install_script.py` (3 tests using a localhost `http.server` fixture: happy path SHA match → installed + executable + bytes-identical; idempotent re-run; **tampered-binary** path → non-zero exit, `"SHA-256 MISMATCH"` on stderr, expected+actual digests both surfaced, NOTHING written to PREFIX). `tests/release/` kept OUT of `[tool.pytest.ini_options].testpaths` so the default `uv run pytest -q` baseline stays at 185.
- Verified: `uv run pytest -q` → 185 passed (baseline unchanged); `uv run mypy` → clean (41 source files, `--strict`); `uv run pytest -q tests/release` → 3 passed; manual smoke under `/usr/bin/dash` with a localhost `python3 -m http.server` fixture: download → SHA verify → install → executable runs ("stub novetest 0.0.0") + PATH hint emitted. Both workflow YAMLs parse cleanly via `yaml.safe_load`. NOT verified yet (requires real GitHub Actions): the 9-cell CI matrix run, the PyApp wrap per target, the in-workflow install-script-e2e job — these can only be observed on actual GHA after merge.
- Left open: 4 Phase 0 DoD bullets are *believed closed* by this slice but await live CI/release-test runs to be ticked by PM — see the handoff. Open Question #15 is resolved (decision 2026-05-14-install-script-hosting-url) but the `ailovestesting.com/novetest/install.sh` redirect is not yet wired by CEO; the in-repo script lives at `scripts/install.sh` and is reachable from `raw.githubusercontent.com` per the decision's rollout note. Windows `install.ps1` is OQ#16 / post-MVP. PyApp version is pinned to `0.22.0` in `release-test.yml`; bumping requires a fresh end-to-end smoke per target.
- Gotcha: install.sh treats `NOVETEST_INSTALL_BASE_URL` as **explicit override iff the env var is *set***, using POSIX `${var+x}` to distinguish set-but-empty from unset (else the GitHub URL layout `releases/latest/download/...` vs `releases/download/<tag>/...` flips). The PATH hint check uses `case ":${PATH}:" in *":${PREFIX}:"*` (POSIX) — not `[[ $PATH == *":$PREFIX:"* ]]`. PyApp passes the wheel path via `PYAPP_PROJECT_PATH` env var read at `cargo build` time, not as a CLI arg — the workflow resolves the exact wheel filename from `dist/` before exporting it so PyApp consumes a single explicit artifact. `release-test.yml` uses `ubuntu-22.04-arm` for the linux-aarch64 cell (native ARM runner; available on GHA since Jan 2025) — if that label gets retired, swap to whatever the current ARM Linux label is. The `install-script-e2e` job in `release-test.yml` is intentionally redundant with `tests/release/test_install_script.py`: the pytest exercises a *fake* binary against the script's logic; the e2e exercises the *actual* PyApp-wrapped binary against the script's network path. Both gates closed = both halves of the install path are sound.
- Next: Main Branch merges this worktree onto `main`. CEO then either pushes a `v0.0.1-rc0` tag to trigger `release-test.yml` end-to-end, or runs it via `workflow_dispatch` to confirm the PyApp wrap actually produces working binaries per target. PM ticks the four Phase 0 DoD bullets after observing both workflow runs green. Coordinate with the parallel Run Team slice (`run-team-2026-05-14-pytest-coverage-emission`) at merge time — that one adds `pytest-cov` and `coverage[toml]>=7.0` to dev deps; this slice does not touch `pyproject.toml`'s `[dependency-groups]`, so the merge should be a clean union.
```
