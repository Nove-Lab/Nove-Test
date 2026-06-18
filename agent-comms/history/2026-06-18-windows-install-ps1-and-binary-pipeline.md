---
from: novetest-pm-team
to: all
type: history
created: 2026-06-18
slug: windows-install-ps1-and-binary-pipeline
cycle_window: 2026-06-18 (single-day, ran parallel with human-text-renderer-cli-text-mode)
related:
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #4 closed
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
---

# Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)

## TL;DR

Windows is now a Tier-1 supported install target. `release-test.yml` has a 4th matrix cell (`windows-x86_64` on `windows-latest`) producing a PyApp `.exe` + `.sha256` sidecar; `scripts/install.ps1` (247 lines, PowerShell 5.1 compatible) mirrors `install.sh` end-to-end; the new `install-ps1-e2e` CI job verifies clean install + idempotent re-install on a real Windows runner. README and `foundations.md §7` updated to expose the Windows install one-liner.

**Closes Future-cycle queue item #4 + Open Question #16.**

Manual Test verdict: **PASSED** — 8 scenarios + 6 edge cases, two cosmetic nits about envelope nomenclature (both doc-side, not product). The binding empirical gate `release-test.yml` run `27743492322` on merged main is GREEN — 6/6 jobs success including the new Windows build cell and install-ps1-e2e.

## Cycle arc (single day, ran in parallel with #9 text renderer)

| Event | Commit |
|---|---|
| PM dispatch prep — task brief filed | `dbd741b` |
| Release code-slice merged | `c25fa2f` |
| Comms (handoff + WORKLOG + INDEX) | `6b33383` |
| Main Branch verification routing | `9b365ff` |
| `release-test.yml` workflow_dispatch on main | run `27743492322` GREEN 6/6 |
| Manual Test PASSED findings filed | `<untracked at cycle close>` |
| PM cycle-close (this entry + foundations + dphasing edits + transient cleanup) | `<this commit>` |

## What landed

### Pipeline changes

| File | Change |
|---|---|
| `.github/workflows/release-test.yml` | +127/-19. Matrix cells go 3→4 (adds `windows-x86_64` on `windows-latest`, `shell: bash` via Git Bash, `binary_suffix: ".exe"`). New `binary_suffix` matrix field propagated through 4 build steps (Wrap wheel, SHA-256 sidecar, Smoke test, Upload artifact). New `install-ps1-e2e` job mirrors `install-script-e2e` structurally (`pwsh` shell, localhost-served fixture binary, clean + idempotent install + envelope assertion). `release.needs` extended to `[build, install-script-e2e, install-ps1-e2e]`. |
| `scripts/install.ps1` (NEW) | 247 lines, 9 functions, PowerShell 5.1 compatible (no `??`/`?.`/`?:`/`using namespace`). End-to-end parallel to `install.sh`: detect arch → compose URLs → download → SHA-256 verify → loud-stderr abort on mismatch → atomic `Move-Item -Force` install (same-volume staging under `$prefix` for atomicity) → PATH hint via `[Environment]::SetEnvironmentVariable(..., "User")`. |
| `scripts/install.sh` | +4 comment lines in header (cross-reference to Windows companion). Zero behavioral change — verified via `git diff` showing only comment-line additions. |
| `README.md` | +14/-1. Windows install one-liner `irm ... | iex` added under `## Install` alongside the existing curl-pipe-sh line. Inspect-first PowerShell variant block added. |
| `scripts/dev-host-setup.md` | +37/-4. Target-platform-support table's Windows row split into "⚠️ dev: untested · ✅ end-user: supported"; new "Windows clarification — end user vs dev host" subsection. Per PM note: CEO does not maintain a Windows-native dev environment. |

### PM-territory edits applied at cycle close

- `design/implementation-plan/foundations.md §549` — Phase-0-scope sentence rewritten to Tier-1 narrative including `windows-x86_64`; cites Open Q #16 closure + install-script-hosting-url decision Amendment 2026-06-10.
- `design/implementation-plan/foundations.md` "Install matrix in README" table — added Windows row (`irm ... | iex`).
- `design/implementation-plan/foundations.md` PyApp pipeline section — added matrix-coverage sentence noting `windows-x86_64` as of 2026-06-18.
- `design/implementation-plan/delivery-phasing.md` Open Q #16 — strikethrough resolved citation pointing to this history entry.

### Empirical CI evidence

`release-test.yml` workflow_dispatch on merged main, run `27743492322` (3m55s total):

| Job | Conclusion |
|---|---|
| `build (linux-x86_64)` | success 1m37s |
| `build (linux-aarch64)` | success 1m18s |
| `build (macos-universal2)` | success 2m14s |
| **`build (windows-x86_64)`** | **success 3m1s (NEW)** |
| `install.sh end-to-end (linux-x86_64)` | success 20s |
| **`install.ps1 end-to-end (windows-x86_64)`** | **success 47s (NEW)** |
| `draft GitHub Release` | skipped (workflow_dispatch trigger, tag-guard correctly engaged) |

Verbatim `novetest/v1` envelope from `install-ps1-e2e` (clean install step):

```json
{
  "command": "version",
  "data": {
    "installLocation": "C:\\Users\\runneradmin\\AppData\\Local\\pyapp\\data\\novetest\\3998689112427238636\\0.1.1\\Scripts\\python.exe",
    "installedVersion": "0.1.1",
    "platform": "windows-amd64",
    "pythonVersion": "3.11.9"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

The idempotent re-install step produced a byte-identical envelope — empirical proof of installer idempotence.

## Load-bearing learnings (5)

### 1. Windows envelope reports `platform: "windows-amd64"`, NOT `"windows-x86_64"`

**Surface**: PyApp's matrix target naming uses Intel/Linux convention (`windows-x86_64`); the CLI's `--version` envelope reports `platform.machine()` lowercase (`amd64` on Windows). Both refer to the same 64-bit Intel/AMD architecture, but they're different label conventions.

**Why this is correct as-is**: `platform.machine()` is what Python natively returns on Windows. Linux returns `x86_64`/`aarch64`; macOS-universal2 returns `arm64` or `x86_64` depending on the slice that's running. Forcing PyApp target naming into the envelope would create asymmetry — Linux's envelope WOULD continue reporting `x86_64`, so Windows pretending to report `x86_64` while the engine reports `amd64` would be the inconsistency, not the alignment.

**Implication for future verification templates**: Windows envelope assertions MUST use `"platform": "windows-amd64"`. Pinned via Manual Test Nit #1 disposition (Option A — doc-only fix).

### 2. `installLocation` always points at the Python interpreter, not the user-invoked binary

**Surface**: On Windows, the envelope's `installLocation` field ends with `\Scripts\python.exe` (the PyApp-bundled python-build-standalone). NOT `\novetest.exe` (the PyApp wrapper the user invokes). This is consistent across platforms — Linux/macOS report `.../python3` paths similarly.

**Why this is consistent**: the CLI introspects `sys.executable` to report the Python that's actually running it, not the PE/Mach-O/ELF wrapper that the user typed. Field name `installLocation` is slightly misleading (real meaning: `pythonExecutableLocation`), but renaming is a much bigger scope change. Same gap exists on Linux/macOS — surfaced visibly on Windows because the path notation differs.

**Implication for future verification templates**: any Windows envelope assertion checking `installLocation` should match `\Scripts\python.exe` (Windows) or `/bin/python3` (Linux/macOS), NOT `novetest.exe` or `novetest`. Pinned via Manual Test Nit #2 disposition (Option A — doc-only fix).

### 3. The `gh` auth read-only situation is the new procedural reality

**Surface**: Release team's `gh auth status` reported `Logged in as yongjunshin`; `gh repo view Nove-Lab/Nove-Test --json viewerPermission` returned `"READ"`. The branch push (`git push origin release/windows-install-ps1-and-binary-pipeline`) returned HTTP 403. Prior cycles (v0.1.0, v0.1.1, version-importlib-metadata, parallel-cycles comms prep) ran with sufficient permissions — token scope or collaborator membership shifted between 2026-06-10 and 2026-06-18.

**Cycle handling**: Release team deferred the push gate to CEO. CEO executed (`c25fa2f` is on origin) and dispatched the workflow (`27743492322`). Cycle still completed cleanly.

**Implication for future cycles**: Release-team task briefs going forward should anticipate "branch push handed off to CEO" as the default procedural posture. The `일괄` self-merge pattern from v0.1.0 / v0.1.1 / version-importlib-metadata cycles is NOT available unless CEO explicitly re-extends the auth. PM briefs should not assume Release can self-merge or self-push.

**Recurring pattern**: this is the second cycle that surfaced "PM brief premise vs procedural reality" friction (the first was v0.1.1's single-source-of-truth assumption — `2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md` learning #1). The lesson is the same: PM briefs codify ASSUMPTIONS, and when an empirical assumption is wrong, the team should surface to CEO rather than abort. v0.1.1 used Option-A in-cycle authorization; this cycle used CEO-push-gate deferral. Both are valid.

### 4. `shell: bash` on Windows build cell over `pwsh` — Karpathy "Simplicity First" precedent

**Surface**: The PM brief skeleton suggested `shell: pwsh` for the Windows build cell. Release deviated to `shell: bash` (Git Bash on `windows-latest`) with explicit rationale:

1. Surgical change: 4 build cells stay structurally identical (all 8 build steps work verbatim under Git Bash on Windows — real `curl`, `tar`, `sha256sum`, `cp` ship in `C:\Program Files\Git\bin`).
2. The PowerShell-native evidence lives in `install-ps1-e2e` (the load-bearing user-facing path).
3. PyApp's own upstream CI builds Windows binaries from bash; we follow that precedent.

The trade-off: the build job does NOT exercise the "PyApp-cargo-build-from-PowerShell" flow. But cargo is a native Windows process whose behavior does NOT depend on the invoking shell.

**Why pinned**: a similar shell/runner choice will surface in any future Windows-related pipeline addition. The default should be the simpler, more uniform path — and validate the platform-native shell only in the user-facing job (install-ps1-e2e in this case).

### 5. `binary_suffix` matrix field over per-cell-shell bifurcation

**Surface**: To support `.exe` only on Windows without bifurcating step bodies, Release added a `binary_suffix` matrix field (`""` on Linux/macOS, `".exe"` on Windows). Interpolated in 4 places via `${{ matrix.binary_suffix }}`. The `cargo build --release` output (`pyapp` on Linux/macOS, `pyapp.exe` on Windows — cargo emits the right binary suffix natively) is copied with the matrix-suffixed name.

**Why this matters**: alternative approaches (per-cell shell + per-cell step bodies; OR per-cell `if matrix.target == 'windows-x86_64'` conditionals scattered through steps) inflate YAML and create cell-specific branches that drift over time. The matrix field is a single source of truth for "this cell produces a binary with this suffix" — extensible if/when future cells need different suffixes (e.g., a hypothetical AppImage / DMG cell).

**Pattern recommendation**: any future matrix-cell-specific output naming (suffixes, archive formats, platform tags) should follow this shape — add a matrix field, interpolate the field in the relevant steps, keep step bodies cell-uniform.

## Manual Test recommended follow-up: v0.1.2 publication

The README now contains `irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex`. The default `NOVETEST_INSTALL_VERSION=latest` resolves to v0.1.1 — but v0.1.1's GitHub Release does NOT include a Windows binary (it was tagged 2026-06-10, before this slice landed).

**Until a v0.1.2 tag is published** (or whatever next tag bundles this slice + the parallel #9 text renderer + any other accumulated work), the README's Windows install one-liner is forward-looking: the install.ps1 script itself loads correctly, but the binary download URL `releases/latest/download/novetest-windows-x86_64.exe` returns 404 because v0.1.1 has no such asset.

**PM disposition**: NOT auto-queued. CEO decides whether to sequence a v0.1.2 publication cycle. Path A (`importlib.metadata`) is operationally live, so a v0.1.2 brief is the trivial 1-line `pyproject.toml::version` bump cycle. Surfaced to CEO at cycle close.

## Phase 0 DoD bullets re-validated (1 new tick)

This cycle changes the Open Q #16 row in `delivery-phasing.md` to strikethrough/resolved. No Phase 0 DoD bullet ticks (Open Q is a separate tracker from Phase 0 DoD).

Empirically re-validated:
- `release-test.yml` GREEN on run `27743492322` (4/4 build cells + 2 install-e2e jobs)
- `ci.yml` GREEN on every commit (`c25fa2f`, `6b33383`, `9b365ff`)
- mypy `--strict` GREEN (109 source files — unchanged; zero src/ changes)
- pytest 1281+ passed (matches text-renderer cycle, since both cycles' tests ran)

## Cycle transcript (commits)

- `dbd741b` — PM: prepare parallel cycles (this cycle + #9 text renderer)
- `c25fa2f` — Release: add Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)
- `6b33383` — Release: handoff + WORKLOG
- `9b365ff` — Main Branch: verification routing to Manual Test
- `<this commit>` — PM: cycle-close (this entry + foundations.md + delivery-phasing.md edits + transient cleanup + INDEX regen)

## Closure

Windows is now a first-class supported install target structurally. The pipeline produces `novetest-windows-x86_64.exe` + `.sha256` sidecar from a clean `windows-latest` runner; the install script verifies the SHA-256 before activating the binary; the activated binary self-reports `installedVersion: "0.1.1"` and `schema: "novetest/v1"` byte-equivalent contract to the Linux/macOS legs.

**Future-cycle queue #4 is operationally closed. Open Question #16 is resolved.**

The remaining gate before end-users on Windows can actually use the README one-liner is the v0.1.2 publication cycle (or whatever next tag bundles this slice). Surfaced to CEO at cycle close.
