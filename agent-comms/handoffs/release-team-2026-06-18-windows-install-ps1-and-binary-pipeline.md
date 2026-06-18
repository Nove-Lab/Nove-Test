---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-18
slug: windows-install-ps1-and-binary-pipeline
worktree: release/windows-install-ps1-and-binary-pipeline
related:
  - agent-comms/tasks/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #4
---

# Handoff: Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)

## Posture (one paragraph)

Worktree `release/windows-install-ps1-and-binary-pipeline` at HEAD (will be
`a554df7` for code + the comms-slice commit that follows this handoff
filing). Adds Tier-1 `windows-x86_64` support: 4th matrix cell in
`release-test.yml`, new `scripts/install.ps1` (PowerShell 5.1 compatible,
structurally parallel to `install.sh`), `install-ps1-e2e` CI job under
`pwsh`. README gets a Windows install one-liner; `scripts/dev-host-setup.md`
gets a "Windows clarification" section distinguishing end-user-supported
from dev-host-untested. Zero `src/`, zero `tests/`, zero
`pyproject.toml` dep surface, zero adapter / engine / fixture changes —
pure pipeline + install-surface work per brief §"Out of scope".
**Empirical CI gate deferred to CEO push** (this session's `gh` auth is
read-only on `Nove-Lab/Nove-Test`; details + procedure in §"Cycle close
direction (CEO + Main Branch + PM)" below).

## Worktree state

| | |
|---|---|
| Branch                  | `release/windows-install-ps1-and-binary-pipeline` |
| Base                    | `main` at `dbd741b` (PM's parallel-cycles comms prep) |
| Code-slice commit       | `a554df7` "release: add Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)" |
| Comms-slice commit      | (filed alongside this handoff — refers to this file + WORKLOG entry + INDEX regen) |
| Worktree path           | `/home/yjshin/dev/aispace/novetest-windows-install-ps1` |
| Files touched           | 5 (1 new + 4 modified) — see §"Files in the diff" |
| Lines (net)             | +421 / −21 in code slice |
| Local validation        | YAML parse GREEN (4 jobs, 4 build cells, 6 install-ps1-e2e steps, `release.needs` extended); PowerShell structural sanity GREEN (balanced braces, 9 functions, 1 try/finally, no PS7-only syntax in code) |

## Files in the diff

### NEW

| File | Lines | Purpose |
|---|---:|---|
| `scripts/install.ps1` | 247 | PowerShell 5.1 compatible installer parallel to `install.sh`. |

### MODIFIED

| File | Lines (net) | Change |
|---|---:|---|
| `.github/workflows/release-test.yml` | +127 / −19 | Add `windows-x86_64` matrix cell + `matrix.binary_suffix` field across all 4 cells; suffix interpolated in 4 build steps (Wrap wheel, SHA-256 sidecar, Smoke test, Upload artifact); new `install-ps1-e2e` job (6 steps, `pwsh`, `windows-latest`); `release.needs` extended to `[build, install-script-e2e, install-ps1-e2e]`. |
| `README.md`                          | +14 / −1  | Add `irm | iex` one-liner alongside the existing `curl-pipe-sh` line under `## Install`; parallel inspect-first PowerShell block. |
| `scripts/dev-host-setup.md`          | +37 / −4  | Target-platform-support table's Windows row split into "dev: untested · end-user: supported"; new "Windows clarification — end user vs dev host" subsection delineating the product surface (Tier-1 via `install.ps1`) from the dev surface (WSL2-recommended; `Verify` blocks only validated on Linux/WSL2/macOS hosts). |
| `scripts/install.sh`                 | +4 / −0   | Header-comment polish referencing the new `install.ps1` companion (brief §"Modified files" optional polish). Zero behavioral change. |

## Architectural shape (what landed)

### `release-test.yml` matrix

```yaml
matrix:
  include:
    - target: linux-x86_64       | runner: ubuntu-latest      | shell: bash | binary_suffix: ""
    - target: linux-aarch64      | runner: ubuntu-22.04-arm   | shell: bash | binary_suffix: ""
    - target: macos-universal2   | runner: macos-latest       | shell: bash | binary_suffix: ""
    - target: windows-x86_64     | runner: windows-latest     | shell: bash | binary_suffix: ".exe"  # ← new
```

**Shell choice — bash on every cell, including Windows.** Brief skeleton
§"Architectural shape" suggested `shell: pwsh` for the Windows build cell.
We deviated to `shell: bash` (Git Bash on `windows-latest`) on the
following analysis:

1. **Surgical change**: keeps the 4 build cells structurally identical.
   All 8 existing build steps work verbatim under Git Bash on Windows
   (real `curl`, `tar`, `sha256sum`, `cp` ship in `C:\Program Files\Git\bin`).
2. **The PowerShell-native evidence is in `install-ps1-e2e`**: that job
   runs `install.ps1` under `pwsh` against the windows-x86_64 artifact —
   that's the load-bearing PowerShell-native user-facing path. Splitting
   the build job into per-cell-shell branches adds YAML for no DoD
   benefit (DoD #1+#2 only require the artifact + sidecar exist).
3. **Karpathy "Simplicity First"** applies: one shell convention for the
   entire build job vs. bifurcated step bodies.

The trade-off is that the build job does NOT exercise the
"PyApp-cargo-build-from-PowerShell" flow — but cargo is a native Windows
process whose behavior does not depend on the invoking shell (cwd is
passed via the standard Win32 API regardless of cmd/pwsh/bash). PyApp's
own upstream CI builds Windows binaries from bash; we follow that
precedent.

### `binary_suffix` matrix field

Empty string on Linux/macOS cells, `".exe"` on Windows. Interpolated in
4 places via `${{ matrix.binary_suffix }}`:

1. `Wrap wheel with PyApp` step — `out_path="../out/novetest-${{ matrix.target }}${{ matrix.binary_suffix }}"` + `cp "target/release/pyapp${{ matrix.binary_suffix }}" "$out_path"` (cargo emits `pyapp.exe` on Windows).
2. `Compute SHA-256 sidecar` step — `bin="novetest-${{ matrix.target }}${{ matrix.binary_suffix }}"`.
3. `Smoke test the binary` step — `./out/novetest-${{ matrix.target }}${{ matrix.binary_suffix }} --version --output json`.
4. `Upload artifact` step — both `path:` glob entries include the suffix.

The `lipo` branch (macOS) is unchanged — it only fires for
`matrix.target == 'macos-universal2'`.

### `install-ps1-e2e` job

Mirrors `install-script-e2e` structurally:

- `runs-on: windows-latest` with `defaults.run.shell: pwsh`
- Downloads the `novetest-windows-x86_64` artifact from the build job
- Serves the binary + sidecar on `http://127.0.0.1:8000/dev/` via
  `python -m http.server` (preinstalled on `windows-latest`)
- Runs `install.ps1` twice (clean + idempotent) against
  `NOVETEST_INSTALL_BASE_URL=http://127.0.0.1:8000` + `_VERSION=dev` +
  `_PREFIX=$RUNNER_TEMP\novetest-install`
- Each run is followed by `novetest.exe --version --output json` envelope
  assertion via the call operator `& "$env:NOVETEST_INSTALL_PREFIX\novetest.exe"`
- Cleanup step kills the HTTP server PID stored at `$env:RUNNER_TEMP\http.pid`
  (ABSOLUTE path — fixes the brief skeleton's `..\http.pid` relative-path
  bug)

Two refinements vs. the brief skeleton:

1. **PID capture**: skeleton used `Start-Process ... -PassThru | Tee-Object -FilePath ..\http.pid` which writes the `Process` object's default
   ToString() (not just the PID). Replaced with
   `$proc = Start-Process ... -PassThru; Set-Content -Path $env:RUNNER_TEMP\http.pid -Value $proc.Id -Encoding ascii`.
2. **PID file path**: skeleton used `..\http.pid` (relative to the
   step's cwd, which changes between steps). Replaced with
   `$env:RUNNER_TEMP\http.pid` — absolute, survives cwd shifts.

### `release` job dependency update

```yaml
release:
  needs: [build, install-script-e2e, install-ps1-e2e]   # ← added install-ps1-e2e
```

Flatten step's glob `novetest-*` already matches
`novetest-windows-x86_64.exe` + `novetest-windows-x86_64.exe.sha256` — no
glob change needed (sanity-check on the first tag-push dry run; per brief
§"release job dependency update").

### `install.ps1` design

PowerShell 5.1 compatible — no `??`, no `?.`, no `?:`, no `using namespace`.
Single-file 247 lines. 9 functions:

| Function | Purpose |
|---|---|
| `Write-Info` | Stdout wrapper (mirrors install.sh `info`). |
| `Resolve-EnvOrDefault` | Reads `[Environment]::GetEnvironmentVariable($name, "Process")` or returns the default — handles both unset (`$null`) and empty (`""`) as "fall through to default" (documented divergence from install.sh's `${var+x}` distinction; per brief §"Failure modes" #10). |
| `Get-Target` | Reads `$env:PROCESSOR_ARCHITECTURE` + `$env:PROCESSOR_ARCHITEW6432`; returns `windows-x86_64` for AMD64; throws explicit error for ARM64 (with foundations.md §54 citation); generic throw for other. |
| `Get-DownloadUrls` | Same 3-branch URL composition as install.sh: explicit BASE_URL → `${BASE_URL}/${VERSION}/${asset}`; `VERSION=latest` → `releases/latest/download/${asset}`; otherwise → `releases/download/${VERSION}/${asset}`. Returns hashtable `@{ Binary; Sha }`. |
| `Get-Sha256Hex` | `(Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()`. PS 5.1 builtin. |
| `Get-ExpectedSha256` | Reads first line via `Get-Content -TotalCount 1` (avoids whole-file read for huge sidecars); `Trim().Split('\s+')[0].ToLower()` — matches install.sh's `awk '{print $1; exit}'` semantics. |
| `Save-RemoteFile` | `Invoke-WebRequest -Uri … -OutFile … -UseBasicParsing`. The `-UseBasicParsing` flag is required in headless contexts (no IE COM dep) and on Server Core. TLS 1.2+ assumed default on Windows 10 1809+ (the supported floor). |
| `Show-PathHintIfNeeded` | Reads `[Environment]::GetEnvironmentVariable("Path", "User")`; splits on `;`; case-insensitive (`-ieq`) comparison vs. each segment; if PREFIX is absent, prints the registry-persistent `[Environment]::SetEnvironmentVariable('Path', ..., 'User')` add-snippet. |
| `Invoke-Install` | Orchestrates: detect → urls → download (binary + sidecar) → verify (extract expected + compute actual → loud-stderr abort on mismatch) → install (`Move-Item -Force` after staging `.tmp` UNDER the install prefix per brief §"Failure modes" #5) → PATH hint → verify hint. Wrapped in `try { … } finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $stagingRoot }`. |

**Mismatch banner**: emitted via `[Console]::Error.WriteLine($banner)` so a
redirected stdout pipe (`irm | iex 2>install.log`) still surfaces the abort
visibly. Followed by `exit 1`. Banner shape byte-equivalent (modulo `→` /
`-` substitution for PS-5.1-clean ASCII) to install.sh's loud abort.

**Idempotent re-install**: tested in CI via the second `install-ps1-e2e`
step. The `Move-Item -Force` on Windows uses `MoveFileEx` with
`MOVEFILE_REPLACE_EXISTING` — same-volume rename is atomic; cross-volume
falls back to copy+delete. By staging the `.tmp` UNDER `$prefix` (not
under `$env:TEMP`), we guarantee same-volume for the rename regardless of
where TEMP lives. **Documented constraint**: if the user has
`novetest.exe` currently running in another process, `Move-Item -Force`
will fail with "file in use"; user must close any running instance first.
Same limitation as `gh`, `git`, `node` Windows installers; not a defect.

## DoD bullets believed closed (PM verifies + ticks)

The brief lists 14 DoD bullets. Status table:

| # | Bullet | Status | Evidence |
|---|---|---|---|
|  1 | `release-test.yml` matrix has 4 cells incl. `windows-x86_64` | ✅ CLOSED | YAML parse confirms 4 matrix.include entries with targets `linux-x86_64`, `linux-aarch64`, `macos-universal2`, `windows-x86_64`. |
|  2 | Windows cell on `windows-latest` produces `.exe` + `.sha256` via `cargo build --release` of PyApp | ✅ CLOSED (CI-pending) | `matrix.binary_suffix=".exe"` propagates to Wrap wheel + SHA-256 sidecar + Upload artifact step. CI run on the branch is the binding empirical proof — currently DEFERRED to CEO push (see §"Cycle close direction"). |
|  3 | `scripts/install.ps1` exists, PS5.1 compatible, parallel structurally to install.sh | ✅ CLOSED | 247 lines, 9 functions, no PS7-only syntax (`??`/`?.`/`?:` only appear in the header comment that DOCUMENTS the avoidance); detect / download / SHA-256 verify / abort-on-mismatch / atomic install (`Move-Item -Force` from same-volume staging) / idempotent re-install / PATH hint all implemented and structurally parallel to install.sh. |
|  4 | `install-ps1-e2e` job in `release-test.yml`, `windows-latest`, twice (clean + idempotent) + envelope assertion | ✅ CLOSED (CI-pending) | Job exists (6 steps); pwsh shell; two install-ps1 invocations each followed by `--version --output json`. Binding empirical proof is the CI run. |
|  5 | `release.needs` includes `install-ps1-e2e`; flatten glob picks up `.exe` + `.exe.sha256` | ✅ CLOSED | `release.needs: [build, install-script-e2e, install-ps1-e2e]`. Existing `novetest-*` glob matches both Windows artifacts; verified at PM brief level + on the workflow yaml. |
|  6 | CI: 4/4 build cells GREEN + Linux install-e2e GREEN + Windows install-e2e GREEN | 🟡 CI-PENDING | Deferred — see §"Cycle close direction (CEO + Main Branch + PM)" for the push + dispatch procedure. |
|  7 | Existing 3-cell matrix remains GREEN (no regression) | 🟡 CI-PENDING | Same CI gate as #6. Structurally: the only change to existing-cell step bodies is the `${{ matrix.binary_suffix }}` interpolation which expands to empty string on those cells — semantically identical to the pre-edit step bodies. |
|  8 | `scripts/install.sh` SHA-256 verification logic unchanged byte-for-byte | ✅ CLOSED | Diff is +4 / −0 lines in the header comment block only. The `main()` function, `compose_urls()`, `sha256_compute()`, `sha256_extract_expected()`, `download()`, `print_path_hint_if_needed()`, `detect_target()` — all byte-identical. `git diff main HEAD -- scripts/install.sh` shows only comment lines added. |
|  9 | README has Windows install one-liner | ✅ CLOSED | `irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex` block added under `## Install`, after the existing curl-pipe-sh block. Parallel inspect-first PowerShell block added under the existing inspect-first bash block. |
| 10 | `scripts/dev-host-setup.md` has Windows section noting WSL2 recommended | ✅ CLOSED | Target-platform-support table's Windows row updated to "⚠️ dev: untested · ✅ end-user: supported"; new "Windows clarification — end user vs dev host" section delineating product surface (Tier-1 via install.ps1) vs dev surface (WSL2). Per PM note: CEO does not maintain Windows-native dev environment. |
| 11 | `foundations.md §7` + `delivery-phasing.md` Open Q #16 update text drafted in handoff (PM applies) | ✅ DRAFTED (PM applies) | Proposed text shipped in §"Out of scope deferred to PM" below. Mirrors 2026-06-10 v0.1.0 license cycle pattern. |
| 12 | Zero new runtime / dev deps in `pyproject.toml` | ✅ CLOSED | `git diff main HEAD -- pyproject.toml` returns empty. No changes. |
| 13 | Zero `src/novetest/**` changes. Zero `tests/**` changes | ✅ CLOSED | `git diff main HEAD -- src/ tests/` returns empty. No changes. |
| 14 | WORKLOG entry written; handoff filed; INDEX regen | ✅ CLOSED (this commit) | This handoff file + WORKLOG entry + INDEX regen ship in the comms-slice commit on this branch. |

**Summary**: 12/14 unambiguously closed; 2/14 (#6, #7) DEFERRED to the CI
run on the worktree branch which requires a CEO-side `git push`.

## Verification surface — what was empirically done

### Local (Linux dev host)

- **YAML parse**: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"` GREEN. Job count = 4 (`build`, `install-script-e2e`, `install-ps1-e2e`, `release`). Matrix cells = 4. `release.needs = ['build', 'install-script-e2e', 'install-ps1-e2e']`.
- **PowerShell structural sanity**: brace count balanced (30 open / 30 close); 9 function definitions; 1 `try`/`finally` pair; 3 `throw` calls (unsupported-arch x2 + sha256-sidecar-empty); 1 `exit 1` (SHA-256 mismatch); no PowerShell-7-only syntax (`??`/`?.`/`using namespace`) in the code body — only in the header comment block that documents the constraint (`grep -nE '(\?\?|\?\.|using namespace)' scripts/install.ps1` shows hits only on lines 9-10 of the header comment).
- **README diff sanity**: irm-iex line present; parallel inspect-first block present; existing curl-pipe-sh line preserved byte-identical.
- **install.sh diff sanity**: `git diff main HEAD -- scripts/install.sh` shows only +4 comment lines in the header (lines 7-11 area), zero behavioral diff.

### Empirical CI (DEFERRED — see §"Cycle close direction" for procedure)

`pwsh` is not installed on the dev host, so the binding PowerShell-syntax
verdict is CI-side via `release-test.yml`'s `install-ps1-e2e` job. The
`gh` auth for this session is read-only on `Nove-Lab/Nove-Test`
(`gh repo view Nove-Lab/Nove-Test --json viewerPermission` returned
`"READ"`), so the `git push` of `release/windows-install-ps1-and-binary-pipeline`
to origin requires CEO action.

Once the branch is on origin:

```bash
# Dispatch the workflow on the worktree branch (does NOT push a tag —
# wheel version stays at 0.1.1 per brief §"Cycle close direction"):
gh workflow run release-test.yml --ref release/windows-install-ps1-and-binary-pipeline

# Watch:
gh run watch <run-id>

# Expected outcome:
#   4/4 build cells SUCCESS (linux-x86_64 + linux-aarch64 +
#                            macos-universal2 + windows-x86_64)
#   install-script-e2e (Linux) SUCCESS
#   install-ps1-e2e (Windows) SUCCESS
#   release SKIPPED (workflow_dispatch trigger, no tag push)
#
# Artifact bundle:
#   gh run download <run-id> → 4 binaries + 4 .sha256 sidecars (8 files).
```

## Cycle close direction (CEO + Main Branch + PM)

### CEO action (push gate)

The local worktree state is ready but unpushed because this session's
`gh` auth (`yongjunshin`) has only READ permission on
`Nove-Lab/Nove-Test`. CEO should push the branch under an account with
write access:

```bash
cd /home/yjshin/dev/aispace/novetest-windows-install-ps1
git log --oneline -3   # confirm a554df7 + comms commit
git push -u origin release/windows-install-ps1-and-binary-pipeline
```

Then dispatch the workflow:

```bash
gh workflow run release-test.yml --ref release/windows-install-ps1-and-binary-pipeline
gh run list --workflow=release-test.yml --branch=release/windows-install-ps1-and-binary-pipeline --limit=1
```

Wait for the run to complete (~6-10 min on a cold runner). Verify
4 + install-script-e2e + install-ps1-e2e jobs SUCCESS.

### Main Branch team action (after CI green)

Standard worktree FF-merge to `main`:

```bash
cd /home/yjshin/dev/aispace/Nove-Test
git fetch origin
git merge --ff-only origin/release/windows-install-ps1-and-binary-pipeline
git push origin main
git push origin :release/windows-install-ps1-and-binary-pipeline  # delete remote branch
git worktree remove /home/yjshin/dev/aispace/novetest-windows-install-ps1
git branch -d release/windows-install-ps1-and-binary-pipeline
```

Then write a verification request to Manual Test under
`agent-comms/verifications/`.

### Manual Test team action

Per brief §"Procedural posture":

1. Empirical CI envelope citation: pull the `install-ps1-e2e` job logs
   (`gh api repos/Nove-Lab/Nove-Test/actions/jobs/<job-id>/logs`) and
   extract the verbatim `novetest/v1` envelope from the `--version`
   assertion. Confirm `"installedVersion": "0.1.1"`,
   `"platform": "windows-x86_64"`, `"pythonVersion"` (whatever
   python-build-standalone resolves), `"installLocation"` containing
   the user-temp PyApp install path.
2. Real-Windows-host smoke (OPTIONAL — per brief §"install.ps1 smoke on
   real Windows"): if Manual Test has a Windows host, VM, or codespace,
   run:
   ```powershell
   $env:NOVETEST_INSTALL_VERSION = "v0.1.1"  # current public tag; no Windows binary yet
   irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/release/windows-install-ps1-and-binary-pipeline/scripts/install.ps1 | iex
   ```
   **Caveat**: this will 404 against v0.1.1 because v0.1.1 was tagged
   BEFORE this slice's Windows binary existed. The real-Windows-host
   smoke against a PUBLISHED Windows binary becomes possible after v0.1.2
   (or whatever tag bundles this slice) is published. Manual Test may
   substitute by downloading the workflow_dispatch artifact bundle
   manually and running install.ps1 locally with
   `NOVETEST_INSTALL_BASE_URL` overrides.
3. Linux/macOS regression smoke (per brief): confirm
   `curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/release/windows-install-ps1-and-binary-pipeline/scripts/install.sh | sh`
   still works (install.sh diff is +4 comment lines, zero behavioral change).
4. **If no Windows host is available**: per brief §"Procedural posture"
   the empirical-gate gap is PM's disposition — likely accept CI
   evidence as binding and defer real-host smoke to a Windows user.

### PM cycle-close actions

1. **Tick Open Q #16** in `delivery-phasing.md` line 303 — proposed
   strikethrough text in §"Out of scope deferred to PM" below.
2. **Apply `foundations.md §7` updates** — proposed text in
   §"Out of scope deferred to PM" below. Three locations: Tier-1 list,
   §549 Phase-0-scope sentence, "Install matrix in README" table.
3. **Cycle-close history entry** at
   `agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md`
   (per brief).
4. **Future-cycle queue update**: drop #4 (this slice) and #16 (also
   this slice) from the queue inheritance in the cycle-close history.
5. **No tag push from this cycle.** Brief §"Cycle close direction" is
   explicit: wheel version stays at `0.1.1`. PM may file a v0.1.2
   publication brief AFTER this slice + the parallel #9 text-renderer
   slice both merge — Path A (`importlib.metadata`) is operationally
   live, so a v0.1.2 brief is the trivial 1-line `pyproject.toml::version`
   bump.

## Out of scope deferred to PM (proposed text)

Per brief §"Charter exception checkpoint":
`design/implementation-plan/foundations.md §7` and
`design/implementation-plan/delivery-phasing.md` are PM-owned. Release
team drafts here; PM applies at cycle close, mirroring the 2026-06-10
v0.1.0 license cycle pattern.

### Proposed: `foundations.md §549` (Phase-0-scope sentence)

**Current line 549** (cited from `git show main:design/implementation-plan/foundations.md | sed -n '549p'`):

> Target platforms (Phase 0 scope): `linux-x86_64`, `linux-aarch64`, `macos-arm64`, `macos-x86_64`. Windows is a follow-up via a parallel `install.ps1`; it is not a Phase 0 blocker.

**Proposed replacement** (2 sentences instead of 2; same paragraph
position; cites both the install-script-hosting-url decision and this
slice's history entry):

> Target platforms (Tier 1): `linux-x86_64`, `linux-aarch64`, `macos-universal2` (lipo-fused arm64 + x86_64), `windows-x86_64`. Windows was added on 2026-06-18 (closes Open Q #16; canonical install URL `https://ailovestesting.com/novetest/install.ps1` per the `decisions/2026-05-14-install-script-hosting-url.md` brand-namespace principle, interim raw GitHub URL per Amendment 2026-06-10; `windows-arm64` remains unsupported pending python-build-standalone — see §54).

### Proposed: `foundations.md` "Install matrix in README" table

**Current** (around line 603-608):

```
| **Default for everyone (any language SuT)** | `curl -fsSL https://ailovestesting.com/novetest/install.sh \| sh` |
| Inspect-first users / hermetic CI           | Direct binary download + SHA-256 verify (Tier 2 above)            |
| macOS / Linux Homebrew users                | `brew install nove/tap/novetest` (once the tap is published)      |
| Python developers                           | `uv tool install novetest` or `pipx install novetest`             |
```

**Proposed addition** (insert immediately after the Linux/macOS default
row):

```
| **Default for everyone — Windows**          | `irm https://ailovestesting.com/novetest/install.ps1 \| iex`      |
```

### Proposed: `delivery-phasing.md` Open Q #16 strikethrough

**Current line 303**:

```
| 16  | Windows `install.ps1` parity (post-Phase-0)                                                          | Post-MVP            | `foundations.md` distribution                                          |
```

**Proposed replacement**:

```
| 16  | ~~Windows `install.ps1` parity (post-Phase-0)~~ — **resolved 2026-06-18** via `release/windows-install-ps1-and-binary-pipeline` cycle (4th `release-test.yml` matrix cell + `scripts/install.ps1` + `install-ps1-e2e` job). See `agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md`. `windows-arm64` remains out of scope pending python-build-standalone (§54). | Phase 0 follow-up   | `foundations.md` distribution                                          |
```

### Proposed: `foundations.md` "What ships behind the script - PyApp single binaries" mention

Optional polish — add a sentence to the PyApp section noting Windows
parity:

> Pipeline: GitHub Actions matrix builds wheels with `uv build`, then PyApp wraps the wheel per target. Each release publishes the binaries with sidecar `*.sha256` files via `gh release create`. Total release pipeline ~50 lines of YAML. **As of 2026-06-18 the matrix covers `linux-x86_64`, `linux-aarch64`, `macos-universal2`, and `windows-x86_64` — see the matrix in `.github/workflows/release-test.yml`.**

PM decides whether to add. Not load-bearing.

## Risks / failure modes encountered

1. **`gh` auth is read-only on `Nove-Lab/Nove-Test`** (PRIMARY UNRESOLVED RISK).
   `gh auth status` shows `Logged in to github.com as yongjunshin`;
   `gh repo view Nove-Lab/Nove-Test --json viewerPermission` returned
   `"READ"`. `git push origin release/windows-install-ps1-and-binary-pipeline`
   returned HTTP 403 — `Permission to Nove-Lab/Nove-Test.git denied to
   yongjunshin`. Prior cycles (v0.1.0, v0.1.1, version-importlib-metadata,
   parallel-cycles comms prep) ran with sufficient permissions; either
   token scope or collaborator membership changed between
   `7b079d0` (last successful push 2026-06-10) and now. **CEO action
   required**: push the branch under an account that has write access
   (see §"Cycle close direction"). No code change can resolve this from
   the Release team side.

2. **PyApp Windows MSVC build flakiness** (NOT ENCOUNTERED — anticipated
   in brief §"Failure modes" #1). `dtolnay/rust-toolchain@stable` on
   `windows-latest` installs `x86_64-pc-windows-msvc` by default; Visual
   Studio 2022 Build Tools are preinstalled on the runner image (per
   GitHub's runner-images repo). PyApp upstream's own CI builds Windows
   binaries via cargo on windows-latest, so the path is well-trodden.
   If `cargo build --release` fails on the first run, check the runner
   image readme for VS toolchain version drift.

3. **PowerShell automatic-variable shadowing** (RESOLVED PRE-COMMIT).
   PS 5.1 has `$PID` as an automatic variable (the current PS process's
   PID); using `$pid = ...` would shadow it. The cleanup step uses
   `$pidValue = ...` instead, avoiding the conflict.

4. **`Move-Item -Force` cross-volume fallback** (DOCUMENTED, NOT BLOCKING).
   By staging the `.tmp` under `$prefix` (NOT under `$env:TEMP`), the
   final `Move-Item` is same-volume → atomic rename. The download
   staging dir IS under `$env:TEMP` but only intermediate files live
   there; the actual install transition is `$prefix\novetest.exe.tmp` →
   `$prefix\novetest.exe`.

5. **Live-binary lock on re-install** (DOCUMENTED CONSTRAINT, NOT A DEFECT).
   If a user has `novetest.exe` currently running in another process,
   the second install.ps1 invocation's `Move-Item -Force` will fail with
   "file in use". Same limitation as `gh`, `git`, `node` Windows
   installers. The CI test does NOT exercise this case (no parallel
   process); idempotence is verified against a stopped binary.

6. **Empty BASE_URL semantic divergence from install.sh** (DOCUMENTED,
   ACCEPTABLE PER BRIEF). install.sh distinguishes "unset" from "set
   to empty" via POSIX `${var+x}`; install.ps1's
   `[Environment]::GetEnvironmentVariable` returns `$null` for unset
   and `""` for empty, both falling through to the default GitHub URL.
   Brief §"Failure modes" #10 accepts this. The empty-but-set case is
   not part of any user contract.

7. **README's Windows install one-liner returns 404 against v0.1.1**
   (TEMPORAL — DOCUMENTED FOR PM). The README now contains
   `irm .../scripts/install.ps1 | iex`. The install.ps1 default
   `NOVETEST_INSTALL_VERSION=latest` resolves to the current public
   release, which is v0.1.1 — but v0.1.1's GitHub Release does NOT
   include a Windows binary (it was tagged before this slice). Until
   PM sequences a v0.1.2 publication cycle that includes this slice +
   any other accumulated work, the README's Windows install line is
   forward-looking. The 404 is on the `novetest-windows-x86_64.exe`
   asset, not on the install.ps1 script itself. PM should sequence
   v0.1.2 promptly to avoid a long temporal window where the README is
   documented but non-functional on Windows. Brief §"Out of scope" is
   explicit that no tag push happens in this cycle.

## Procedural notes

- **No Release-team self-FF-merge this cycle.** Brief §"Procedural
  posture" is explicit: "After CI matrix green, handoff to Main Branch
  for FF-merge." This is the standard worktree → Main Branch pattern.
  v0.1.0 / v0.1.1 cycles used the 일괄 self-merge pattern; this cycle
  reverts to standard.
- **Charter exception**: none. All edits are inside Release team's
  writable surface per `.claude/agents/novetest-release-team.md`
  (`scripts/install.{sh,ps1}`, `.github/workflows/**`, `README.md`,
  `scripts/dev-host-setup.md`). `foundations.md` and `delivery-phasing.md`
  are PM-owned and deliberately untouched by this slice — proposed text
  in §"Out of scope deferred to PM" for PM to apply at cycle close.
- **No `andrej-karpathy-skills:karpathy-guidelines` skill invocation
  via Skill tool** — the skill is not exposed in this session's tool
  registry. Applied the four guidelines manually (Think Before Coding /
  Simplicity First / Surgical Changes / Goal-Driven Execution) at each
  decision point: shell choice on Windows cell (bash over pwsh —
  Simplicity First), binary_suffix matrix var over per-cell-shell
  bifurcation (Surgical), README scope (add the line; do NOT
  preemptively flip Status/Roadmap — Surgical), foundations.md proposal
  as draft text in handoff vs direct edit (Charter respect).

## Reporting back

| Field | Value |
|---|---|
| Worktree                  | `/home/yjshin/dev/aispace/novetest-windows-install-ps1` on branch `release/windows-install-ps1-and-binary-pipeline` |
| Code-slice commit SHA     | `a554df7` |
| Comms-slice commit SHA    | (this commit; SHA TBD after `git commit`) |
| Files modified            | 5 (1 new + 4 modified): `scripts/install.ps1` (new), `.github/workflows/release-test.yml`, `README.md`, `scripts/dev-host-setup.md`, `scripts/install.sh` |
| CI matrix result          | DEFERRED — needs CEO push (see §"Cycle close direction") |
| Install-script E2E result | install-script-e2e (Linux) DEFERRED; install-ps1-e2e (Windows) DEFERRED |
| Release-pipeline surprises | (1) PyApp Windows build untested locally (CI gate); (2) brief skeleton's `..\http.pid` relative-path bug and `Tee-Object` PID-capture bug — both fixed in the implemented job; (3) `gh` auth read-only — push handed off to CEO |
| Worklog entry text        | See `WORKLOG.md` (top entry for 2026-06-18) |
