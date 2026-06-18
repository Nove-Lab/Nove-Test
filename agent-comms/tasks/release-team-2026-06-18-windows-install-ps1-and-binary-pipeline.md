---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-18
slug: windows-install-ps1-and-binary-pipeline
related:
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #4
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md  # canonical URL + interim raw URL policy
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md  # JUnit Windows OS-gate stays
  - design/implementation-plan/foundations.md  # §7 Distribution
---

# Task: Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)

## Mission

Close `delivery-phasing.md` Open Question **#16** ("Windows `install.ps1` parity (post-Phase-0)") by:

1. **Adding a 4th matrix cell** to `.github/workflows/release-test.yml`: `windows-x86_64` on `windows-latest` runner, producing a `novetest-windows-x86_64.exe` + `.sha256` sidecar via PyApp.
2. **Authoring `scripts/install.ps1`** — the PowerShell equivalent of `scripts/install.sh`: detect arch, download, SHA-256 verify, install to a per-user PATH location, idempotent re-install, abort-on-mismatch.
3. **Adding an `install-ps1-e2e` CI job** mirroring the existing `install-script-e2e` job (clean install + idempotent re-install against a localhost-served fixture binary).
4. **Updating `foundations.md §7`** (Distribution) to reflect Windows-x86_64 is now a Tier-1 supported target.
5. **Updating `README.md`** with a Windows install one-liner (`irm ... | iex` pattern).

This closes Future-cycle queue item **#4** from `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`.

## Strategic context

`design/implementation-plan/foundations.md §549` explicitly states:

> Target platforms (Phase 0 scope): `linux-x86_64`, `linux-aarch64`, `macos-arm64`, `macos-x86_64`. **Windows is a follow-up via a parallel `install.ps1`; it is not a Phase 0 blocker.**

This slice IS that follow-up. The pipeline shape mirrors the existing linux/macOS path; the only platform-specific differences are (a) PowerShell syntax for `install.ps1`, (b) `windows-latest` GitHub Actions runner, (c) `.exe` suffix, (d) PATH semantics on Windows.

PyApp + python-build-standalone supports Windows x86_64 natively (the upstream PyApp release matrix ships Windows builds at `ofek/pyapp/releases/.../source.tar.gz` — same tarball this workflow already uses for Linux / macOS, with `cargo build --release` doing the right thing on Windows). No fork, no patch.

**Windows ARM64 is explicitly OUT OF SCOPE** for this cycle — `foundations.md §54`: "PyApp + python-build-standalone availability for `windows-arm64` - currently unsupported; we ship `windows-x86_64` only and document the gap." That gap stays as-is; a future cycle reopens when python-build-standalone publishes Windows-arm64 builds.

## Scope (file footprint)

### New files

- **`scripts/install.ps1`** — PowerShell installer, parallel to `scripts/install.sh`. Target: PowerShell 5.1 (Windows 10/11 default) compatible — no PowerShell 7-only syntax.

### Modified files

- **`.github/workflows/release-test.yml`** — add `target: windows-x86_64` to the build matrix (`runner: windows-latest`, `shell: pwsh`); add `install-ps1-e2e` job depending on the windows-x86_64 build.
- **`scripts/install.sh`** — comment update only: line 14 + canonical URL note may reference the Windows companion script (optional polish, not load-bearing).
- **`design/implementation-plan/foundations.md` §7** — narrative update: Tier 1 list adds `windows-x86_64`; §549 Phase-0-scope sentence updated to acknowledge Windows is now Tier-1 with `install.ps1` as a parallel script (canonical URL: `https://ailovestesting.com/novetest/install.ps1` per existing brand-namespace principle; interim raw GitHub URL per `decisions/2026-05-14-install-script-hosting-url.md` Amendment 2026-06-10).
- **`README.md`** — add Windows install one-liner alongside the existing curl-pipe-sh line.
- **`scripts/dev-host-setup.md`** — add a brief "Windows (PowerShell-native)" section noting that WSL2 is the recommended dev path; PowerShell-native is supported for END USERS but the project's test gate is not validated on PowerShell-native dev hosts. (Per PM's note that CEO does not maintain a Windows-native dev environment.)

### Charter exception checkpoint

`.github/workflows/**` and `scripts/install.{sh,ps1}` are Release-team territory per `.claude/agents/novetest-release-team.md`. `foundations.md §7` is **PM-owned** (`design/implementation-plan/foundations.md` is in PM's owned files) — Release team should write the proposed text edit in the handoff §"Out of scope deferred to PM" section; PM applies the edit at cycle-close. This is the same pattern the 2026-06-10 v0.1.0 license cycle used for `foundations.md §7 License`.

## Architectural shape

### `release-test.yml` matrix addition

Add to the existing `matrix.include` list (after `macos-universal2`):

```yaml
- target: windows-x86_64
  runner: windows-latest
  shell: pwsh
```

The existing `defaults.run.shell: ${{ matrix.shell }}` already supports per-cell shell selection; `pwsh` is preinstalled on `windows-latest`.

Inside the build job:

- **Wheel build step**: `uv build --wheel --out-dir dist` — works on Windows out of the box; `uv` is cross-platform.
- **PyApp wrap step**: identical cargo build flow. The output binary is named `novetest-windows-x86_64.exe` (note the `.exe` suffix — pin via PowerShell `$out_path = "..\out\novetest-${{ matrix.target }}.exe"`). The wheel resolution glob (`$GITHUB_WORKSPACE/dist/novetest-*-py3-none-any.whl`) works on PowerShell with quoting.
- **SHA-256 sidecar step**: PowerShell has `Get-FileHash -Algorithm SHA256`; emit the `<hash>  <filename>` format that matches `sha256sum -c`. Reference helper:

  ```powershell
  $bin = "novetest-windows-x86_64.exe"
  $hash = (Get-FileHash -Algorithm SHA256 ".\out\$bin").Hash.ToLower()
  "$hash  $bin" | Out-File -FilePath ".\out\$bin.sha256" -Encoding ascii
  ```

- **Smoke test step**: `.\out\novetest-windows-x86_64.exe --version --output json` — same envelope assertion shape as the other cells.
- **Upload artifact step**: identical `actions/upload-artifact@v7` with the .exe + .sha256 paths.

### `install.ps1` shape

POSIX-sh structural parallel to `install.sh`; idiomatic PowerShell. PowerShell 5.1 compatible (no `??` null-coalescing, no `?.` safe-nav, no PowerShell 7 ternary).

Skeleton:

```powershell
# install.ps1 — Windows companion to scripts/install.sh
# Canonical user invocation (per decisions/2026-05-14-install-script-hosting-url.md):
#   irm https://ailovestesting.com/novetest/install.ps1 | iex
# Interim per Amendment 2026-06-10:
#   irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex

$ErrorActionPreference = "Stop"

# Override env vars (parallel to install.sh):
#   NOVETEST_INSTALL_REPO     default: Nove-Lab/Nove-Test
#   NOVETEST_INSTALL_VERSION  default: latest
#   NOVETEST_INSTALL_BASE_URL default: derived from REPO+VERSION
#   NOVETEST_INSTALL_PREFIX   default: $env:USERPROFILE\.local\bin

$REPO    = if ($env:NOVETEST_INSTALL_REPO)    { $env:NOVETEST_INSTALL_REPO }    else { "Nove-Lab/Nove-Test" }
$VERSION = if ($env:NOVETEST_INSTALL_VERSION) { $env:NOVETEST_INSTALL_VERSION } else { "latest" }
$PREFIX  = if ($env:NOVETEST_INSTALL_PREFIX)  { $env:NOVETEST_INSTALL_PREFIX }  else { Join-Path $env:USERPROFILE ".local\bin" }

# Detect target (Windows + arch)
$arch = (Get-CimInstance Win32_Processor).Architecture
# 0 = x86, 9 = AMD64 (x86_64); we only support 9 today (Windows ARM64 is OOS)
if ($arch -ne 9) { throw "unsupported Windows architecture; this cycle ships windows-x86_64 only" }
$target = "windows-x86_64"
$asset  = "novetest-$target.exe"

# Compose URL
if ($env:NOVETEST_INSTALL_BASE_URL) {
    $binary_url = "$($env:NOVETEST_INSTALL_BASE_URL)/$VERSION/$asset"
} elseif ($VERSION -eq "latest") {
    $binary_url = "https://github.com/$REPO/releases/latest/download/$asset"
} else {
    $binary_url = "https://github.com/$REPO/releases/download/$VERSION/$asset"
}
$sha_url = "$binary_url.sha256"

Write-Host "Installing novetest ($target, $VERSION) into $PREFIX"
Write-Host "  binary: $binary_url"
Write-Host "  sha256: $sha_url"

# Download (Invoke-WebRequest is PS 5.1 builtin; works without curl)
$tmpdir = New-Item -ItemType Directory -Path (Join-Path $env:TEMP "novetest-install-$([guid]::NewGuid())")
try {
    $binary_path = Join-Path $tmpdir $asset
    $sha_path    = "$binary_path.sha256"
    Invoke-WebRequest -Uri $binary_url -OutFile $binary_path -UseBasicParsing
    Invoke-WebRequest -Uri $sha_url    -OutFile $sha_path    -UseBasicParsing

    # Verify SHA-256
    $expected = (Get-Content $sha_path -Raw).Split()[0].ToLower()
    $actual   = (Get-FileHash -Algorithm SHA256 $binary_path).Hash.ToLower()
    if ($expected -ne $actual) {
        Write-Error @"

=================================================================
  SHA-256 MISMATCH — refusing to install $asset.
-----------------------------------------------------------------
  expected:  $expected
  actual:    $actual
  source:    $binary_url
  sidecar:   $sha_url

  This means the binary you would have installed does NOT match
  the published checksum. Possible causes: a corrupted download,
  a man-in-the-middle, or a tampered mirror. Nothing has been
  written to $PREFIX.
=================================================================
"@
        exit 1
    }
    Write-Host "SHA-256 verified ($actual)."

    # Install: copy to PREFIX\novetest.exe, atomic rename
    New-Item -ItemType Directory -Path $PREFIX -Force | Out-Null
    $install_path = Join-Path $PREFIX "novetest.exe"
    $stage_path   = "$install_path.tmp"
    Copy-Item -Path $binary_path -Destination $stage_path -Force
    # Move-Item is atomic on the same volume.
    Move-Item -Path $stage_path -Destination $install_path -Force
    Write-Host "Installed: $install_path"

    # PATH hint
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not ($userPath -split ';' | Where-Object { $_ -ieq $PREFIX })) {
        Write-Host ""
        Write-Host "Note: $PREFIX is not on your user PATH."
        Write-Host "      To add it permanently, run this once in PowerShell:"
        Write-Host ""
        Write-Host "        [Environment]::SetEnvironmentVariable('Path', `$env:Path + ';$PREFIX', 'User')"
        Write-Host ""
        Write-Host "      Then open a fresh PowerShell session and run: novetest --version"
    } else {
        Write-Host "Run 'novetest --version' to verify."
    }
} finally {
    Remove-Item -Path $tmpdir -Recurse -Force -ErrorAction SilentlyContinue
}
```

### `install-ps1-e2e` CI job

Parallel to `install-script-e2e`. Sketch:

```yaml
install-ps1-e2e:
  name: install.ps1 end-to-end (windows-x86_64)
  needs: build
  runs-on: windows-latest
  defaults:
    run:
      shell: pwsh
  steps:
    - uses: actions/checkout@v6

    - name: Download built binary
      uses: actions/download-artifact@v8
      with:
        name: novetest-windows-x86_64
        path: srv

    - name: Serve binary on localhost
      run: |
        New-Item -ItemType Directory -Path "www\dev" -Force
        Copy-Item "srv\novetest-windows-x86_64.exe" "www\dev\"
        Copy-Item "srv\novetest-windows-x86_64.exe.sha256" "www\dev\"
        Push-Location www
        Start-Process -FilePath "python" -ArgumentList "-m","http.server","8000" -WindowStyle Hidden -PassThru | Tee-Object -FilePath ..\http.pid
        # Wait for the server
        for ($i=0; $i -lt 20; $i++) {
          try { Invoke-WebRequest "http://127.0.0.1:8000/dev/novetest-windows-x86_64.exe.sha256" -UseBasicParsing | Out-Null; break } catch { Start-Sleep -Milliseconds 250 }
        }
        Pop-Location

    - name: Run install.ps1 (clean install)
      env:
        NOVETEST_INSTALL_BASE_URL: "http://127.0.0.1:8000"
        NOVETEST_INSTALL_VERSION: "dev"
        NOVETEST_INSTALL_PREFIX: ${{ runner.temp }}\novetest-install
      run: |
        & scripts\install.ps1
        & "$env:NOVETEST_INSTALL_PREFIX\novetest.exe" --version --output json

    - name: Run install.ps1 again (idempotent upgrade)
      env:
        NOVETEST_INSTALL_BASE_URL: "http://127.0.0.1:8000"
        NOVETEST_INSTALL_VERSION: "dev"
        NOVETEST_INSTALL_PREFIX: ${{ runner.temp }}\novetest-install
      run: |
        & scripts\install.ps1
        & "$env:NOVETEST_INSTALL_PREFIX\novetest.exe" --version --output json

    - name: Stop HTTP server
      if: always()
      run: |
        if (Test-Path ..\http.pid) { Get-Content ..\http.pid | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
```

The `release` job at the bottom of `release-test.yml` (the draft GitHub Release creation) needs the `install-ps1-e2e` added to its `needs` list, so the draft is not created if Windows install-script-e2e fails.

### `release` job dependency update

```yaml
release:
  needs: [build, install-script-e2e, install-ps1-e2e]   # added install-ps1-e2e
```

The flatten step also needs to glob the .exe + .exe.sha256:

```yaml
find artifacts -type f \( -name 'novetest-*' -o -name '*.sha256' \) -exec cp {} release/ \;
```

The existing glob `novetest-*` already matches `novetest-windows-x86_64.exe` and `novetest-windows-x86_64.exe.sha256` — no change needed. Sanity-check this on the first dry run.

## Out of scope — DO NOT do in this cycle

- **JUnit / dotnet Windows OS-gate removal**: decision `2026-06-03-junit-console-launcher-vendor.md §R5` keeps the JUnit Windows OS gate in place; dotnet adapter has its own Windows constraints (Coverlet XPlat issues; see decision `2026-06-03-coverlet-pertestcoverage-key.md`). The 12 JUnit Windows tests that this slice's CI matrix will see remain skipped via the existing `@_SKIP_IF_WINDOWS` decorators in `tests/unit/run/` and `tests/integration/run/`. **Adapter Windows enablement is a separate post-MVP cycle.**
- **Windows ARM64**: `windows-arm64` is OUT — python-build-standalone gap (`foundations.md §54`). Future cycle reopens when upstream supports it.
- **PowerShell 7 syntax**: write PowerShell 5.1 compatible (Windows 10/11 default). No `??`, `?.`, `?:`, no `using namespace`. The CI runner has both PS 5.1 and PS 7 available but users may only have PS 5.1.
- **Code-signing / Authenticode**: foundations.md §3-§11 frame "signed" as SHA-256 sidecar (Phase 0 sense). Authenticode signing is a post-MVP concern requiring a cert. Stay with SHA-256 only.
- **MSI installer / chocolatey / winget / scoop**: future polish per Open Q #13 (Homebrew tap publishing — Windows equivalents would be analogous). NOT this cycle.
- **DNS routing for `ailovestesting.com/novetest/install.ps1`**: parallel to install.sh per Amendment 2026-06-10 — interim raw URL works; canonical brand URL pending Cloudflare Page Rules. Document the interim path in README's Windows one-liner; do NOT block on DNS.
- **Wheel changes / dependency changes**: `pyproject.toml` is dev-deps territory only for Release; `dependencies = ["cyclopts>=3.0", "numpy>=1.26"]` is correct as-is. The wheel built in this cycle is the SAME wheel as v0.1.1 — only the PyApp wrap target changes.
- **`tests/**` modifications**: this slice adds zero unit/integration tests. The verification surface is the CI matrix itself (binary builds + install-ps1-e2e job).
- **`src/**` modifications**: zero. The product source is target-agnostic.

## Verification surface

### Pre-merge local sanity (Linux dev host)

These run on the Release team's Linux dev host before pushing:

- **YAML lint**: `cat .github/workflows/release-test.yml | yamllint -` (or just `yq` to parse).
- **PowerShell syntax check** (if pwsh available — `apt install powershell` or skip): `pwsh -c "Get-Command -Syntax (Get-Content scripts/install.ps1 -Raw)"` — empirically optional, the CI run will catch syntax errors definitively.
- **Existing `release-test.yml` workflow_dispatch run on `main`**: confirm the 3-cell matrix still works (no regression introduced by adding the 4th cell).

### Empirical CI smoke on the worktree branch

- Push branch `release/windows-install-ps1-and-binary-pipeline` to origin.
- `gh workflow run release-test.yml --ref release/windows-install-ps1-and-binary-pipeline` to dispatch.
- Wait for completion. Expected: 4/4 build cells GREEN (linux-x86_64 + linux-aarch64 + macos-universal2 + **windows-x86_64**), `install-script-e2e` GREEN (Linux), `install-ps1-e2e` GREEN (Windows), `draft GitHub Release` SKIPPED (workflow_dispatch trigger, not tag push).
- Capture the artifact bundle: `gh run download <run_id>` should yield 4 binaries + 4 .sha256 sidecars (8 files).

### Empirical CI on tag push (deferred to cycle close)

A v0.1.2 tag push would trigger the full release-test.yml including the `release` job, producing 4 binaries + 4 sidecars + a draft GitHub Release. **This cycle does NOT push a tag** — wheel version is unchanged from v0.1.1, no release-worthy product code change. PM may sequence a tag bump cycle (v0.1.2) AFTER this slice + the parallel #9 text-renderer slice both merge.

### Binary integrity proof

Verify the .exe artifact has the right shape:
- `file novetest-windows-x86_64.exe` → "PE32+ executable (console) x86-64, for MS Windows"
- SHA-256 cross-check: `(Get-FileHash novetest-windows-x86_64.exe).Hash` matches the sidecar content
- Expected byte-size: ~6-8 MB (parallel to linux/macOS); if dramatically larger or smaller, investigate

### install.ps1 smoke on real Windows

If the Release team has access to a Windows host (or Windows VM, or a fresh Windows runner via `gh codespace`), running the canonical install one-liner against the workflow's released binary IS the load-bearing user smoke:

```powershell
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/release/windows-install-ps1-and-binary-pipeline/scripts/install.ps1 | iex
```

This is OPTIONAL — the `install-ps1-e2e` CI job is the binding evidence. The real-Windows smoke is bonus.

## Definition of Done (claim closed in handoff §"DoD bullets believed closed")

1. `.github/workflows/release-test.yml` matrix has 4 cells: `linux-x86_64`, `linux-aarch64`, `macos-universal2`, **`windows-x86_64`**.
2. The Windows cell on `windows-latest` runner produces `novetest-windows-x86_64.exe` + `.sha256` sidecar via `cargo build --release` of PyApp.
3. `scripts/install.ps1` exists, PowerShell 5.1 compatible, parallel structurally to `scripts/install.sh` (detect / download / SHA-256 verify / abort-on-mismatch / atomic install / idempotent re-install / PATH hint).
4. `install-ps1-e2e` job exists in `release-test.yml`, runs on `windows-latest`, executes `install.ps1` against a localhost-served fixture, twice (clean + idempotent), each followed by `novetest.exe --version --output json` envelope assertion.
5. `release` job's `needs:` list includes `install-ps1-e2e`; flatten step picks up `.exe` + `.exe.sha256` (existing glob should work).
6. CI run on the branch: 4/4 build cells GREEN + Linux install-e2e GREEN + Windows install-e2e GREEN.
7. Existing 3-cell matrix (linux + macOS) remains GREEN — no regression in the existing pipeline.
8. `scripts/install.sh` SHA-256 verification logic unchanged byte-for-byte (this slice does not touch the POSIX path's semantics).
9. README has a Windows install one-liner (`irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex`) alongside the existing curl-pipe-sh line.
10. `scripts/dev-host-setup.md` has a "Windows" section noting WSL2 is the recommended dev path.
11. `foundations.md §7` and `delivery-phasing.md` Open Q #16 update text drafted in handoff §"Out of scope deferred to PM" (Release does NOT edit these files directly — PM applies at cycle close, mirroring 2026-06-10 v0.1.0 cycle pattern).
12. Zero new runtime / dev deps in `pyproject.toml`.
13. Zero `src/novetest/**` changes. Zero `tests/**` changes (this is pure pipeline + install-surface work).
14. WORKLOG entry written; handoff filed at `agent-comms/handoffs/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md`; `tools/regen_comms_index.py` run before commit.

## Failure modes (PM-anticipated; mitigation in your hands)

1. **PyApp Windows build flakiness**: PyApp's Cargo build on Windows depends on a working Rust toolchain (MSVC ABI). The `dtolnay/rust-toolchain@stable` action handles this on `windows-latest`. If `cargo build --release` fails, check the Rust target — Windows defaults to `x86_64-pc-windows-msvc`; you should NOT need to specify `--target` (single-arch host build).
2. **PowerShell file path escaping**: PowerShell paths use `\` (backslash) which is NOT a string escape character in single-quoted strings, but IS in double-quoted with `$()` interpolation. Use single quotes for literal paths; use `Join-Path` for compositional paths.
3. **`Invoke-WebRequest` vs `curl`**: PowerShell 5.1 ships `Invoke-WebRequest` (aka `iwr`); use `-UseBasicParsing` for headless contexts. Avoid `curl` (alias to `Invoke-WebRequest` on Windows, NOT the real curl tool) — confusing for inspect-first users.
4. **`Get-FileHash` output format**: returns a PSObject with `.Hash` property as uppercase hex. Normalize to lowercase to match `sha256sum` output convention.
5. **Atomic install via `Move-Item`**: works on the same volume only. On Windows, `$env:USERPROFILE` and `$env:TEMP` may be on different volumes (rare but possible). If the staging temp dir is on a different volume from the install prefix, `Move-Item` falls back to copy+delete (still works, just not atomic). For defense in depth: stage under the install prefix itself (not `$env:TEMP`).
6. **Default install prefix `$env:USERPROFILE\.local\bin`**: parallels Linux's `~/.local/bin` for naming consistency. NOT the Windows-conventional `$env:LOCALAPPDATA\Programs\novetest`. PM recommendation: stay with `\.local\bin` for cross-platform symmetry with the install.sh path — users following AI-agent install hints get the same shape on every OS. If you have a reason to prefer `$env:LOCALAPPDATA\Programs\novetest`, surface the question in the handoff and PM will route. Either is defensible; symmetry argues for `\.local\bin`.
7. **PATH-add hint that survives PowerShell session**: `[Environment]::SetEnvironmentVariable("Path", $env:Path + ';C:\...', "User")` writes to the user registry — survives sessions. Document this in the PATH hint output. Inline `$env:Path += "..."` is per-session only; not enough for "run novetest tomorrow".
8. **Unicode glyph compatibility in PowerShell**: stdout from `install.ps1` is just install logs (ASCII). No glyph issue. (The `novetest --version` envelope JSON has no glyphs either.) For the parallel #9 text-renderer cycle, see that brief's §"Failure modes" #2.
9. **`gh release create` upload**: the existing `softprops/action-gh-release@v3` step in the `release` job uses a glob `release/novetest-*` — the Windows .exe + .exe.sha256 will be picked up automatically. Sanity-check on the first tag-push dry-run.
10. **Empty BASE_URL edge case in install.ps1**: install.sh distinguishes "BASE_URL unset" from "BASE_URL set to empty" via `${var+x}`. PowerShell equivalent: `if ($env:NOVETEST_INSTALL_BASE_URL) { ... }` — falsy for both unset and empty, so the install.ps1 will fall through to the default GitHub URL composition in either case. This is a minor semantic deviation from install.sh; acceptable.

## Procedural posture

- **Karpathy skill**: invoke `andrej-karpathy-skills:karpathy-guidelines` before any code edit (YAML, PowerShell, foundations.md proposal text). Goal-driven, surgical, simplicity-first. Resist adding chocolatey/winget/MSI/code-signing scope — those are separate cycles.
- **Charter scope**: `.github/workflows/`, `scripts/`, `pyproject.toml` (dev-deps surface — though this slice adds zero) are Release-team territory. `foundations.md` and `delivery-phasing.md` are PM-owned — write proposed text in the handoff for PM to apply at cycle close.
- **Worktree**: branch `release/windows-install-ps1-and-binary-pipeline` off `main`. After CI matrix green (4/4 + 2 install-e2e jobs), handoff to Main Branch for FF-merge.
- **Manual Test**: required. Manual Test verifies (i) the published Windows binary actually works on a real Windows host, (ii) the install.ps1 one-liner produces a working `novetest --version` envelope, (iii) existing Linux/macOS install path still works (no regression). If no Windows host is available to Manual Test, that's an empirical-gate gap — PM dispositions in cycle-close (likely outcome: accept CI evidence as binding for v1; ask CEO whether to defer real-Windows-host smoke to a Windows user once one surfaces).

## Cycle close direction (PM perspective)

- **Manual Test**: as above. Real-Windows-host availability is the key question.
- **PM cycle-close actions**:
  - Tick Open Q #16 in `delivery-phasing.md` line 303 as resolved (with citation to this cycle's history entry).
  - Apply the proposed `foundations.md §7` text from the handoff.
  - Cycle-close history entry under `agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md`.
  - Update the Future-cycle queue (in the next history entry's queue inheritance): #4 dropped, #16 ditto.
- **No tag push from this cycle.** Wheel version stays at `0.1.1`; product source is byte-identical. If CEO wants a v0.1.2 publication cycle that bundles this + the text-renderer slice + any other accumulated work, PM files a separate brief at that time. The v0.1.2 brief would be the trivial 1-line `pyproject.toml::version` bump (Path A is now operationally live — `src/novetest/__init__.py` reads via `importlib.metadata`).

## Coordination with parallel cycle (Orchestration team, A안)

The Orchestration team is dispatched simultaneously with `agent-comms/tasks/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md` (Future-cycle queue #9). **Zero file-footprint overlap** — Orchestration touches `src/novetest/cli/`, `tests/`; Release touches `scripts/`, `.github/workflows/`, `foundations.md` (proposal text), `README.md` (Windows install line), `scripts/dev-host-setup.md`. Either may FF-merge first; no merge conflict expected.

**One Windows-specific consideration**: when the Windows CI cell first runs, Orchestration's existing CLI unit + integration tests will execute on `windows-latest` if those tests are already in `ci.yml`'s matrix (which they are per `foundations.md §511`). Confirm: the existing `ci.yml` Windows × 3 Python matrix runs the full unit + integration suite on `windows-latest` BEFORE this slice lands, so any Windows test failure surfaced by this slice's pipeline addition is unrelated to your work. The 12 JUnit Windows tests already skipped via `@_SKIP_IF_WINDOWS` — those stay skipped.

If Orchestration's text-renderer slice lands BEFORE yours, the Windows CI cell will run the new text-renderer tests too. They should pass (Unicode glyphs work on Windows Terminal); if they don't, that's Orchestration's signal to add an ASCII fallback (see #9 brief §"Failure modes" #2) — unrelated to your binary pipeline work.
