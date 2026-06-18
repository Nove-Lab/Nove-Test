---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-18
slug: windows-install-ps1-and-binary-pipeline
related:
  - agent-comms/handoffs/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md
  - agent-comms/tasks/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
---

# Verification — Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)

## Merge summary

Release slice rebased onto orchestration (alphabetic merge order per Main
Branch charter) and FF-merged into `main` as the **second** of two parallel
cycles. The post-rebase commit SHAs differ from the originals:

| Slice | Original SHA | Post-rebase SHA (on main) | Subject |
|---|---|---|---|
| Code  | `a554df7` | `c25fa2f` | `release: add Windows install.ps1 + PyApp binary pipeline (closes Open Q #16)` |
| Comms | `b8a5c66` | `6b33383` | `comms: Release handoff + WORKLOG for Windows install.ps1 + binary pipeline cycle` |

- **Source handoff**: [release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md](../handoffs/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md)
- **Rebase conflicts**: 1 — `WORKLOG.md` only (both teams prepended a 2026-06-18 entry). Resolved with the standard "newest-in-history on top + `---` divider" convention: Release entry on top, orchestration entry below, `---` between. **Zero source-file conflicts** (Release touches `scripts/` + `.github/` + `README.md` + `scripts/dev-host-setup.md`; orchestration touches `src/novetest/cli/` + `tests/`).
- **Local main HEAD after this slice**: `6b33383`
- **⚠ Push status (CEO action required)**: `git push origin main` **BLOCKED** by HTTP 403 — same READ-only auth Release team flagged in their handoff §"Risks" #1. Local merge + gate are complete; push to origin awaits CEO action.

## Post-merge gate (re-run at `6b33383`)

| Check | Result |
|---|---|
| `uv run mypy --strict src/novetest` | **PASS** — 109 source files, 0 issues (baseline 93 + 16 renderer modules from orchestration; Release slice adds 0 src) |
| `uv run pytest -q tests/unit tests/integration` | **1281 passed + 23 skipped + 1 failed** (39.09s) — **same numbers as orchestration's gate** since Release slice adds 0 test surface |
| Pre-existing failure | `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` (`dotnet` not on PATH; chronic dev-host-equip dependency, **unchanged by this slice**) |
| `.github/workflows/release-test.yml` structural sanity | **GREEN** — 4 jobs (`build`, `install-script-e2e`, `install-ps1-e2e`, `release`); 4 build matrix cells: `linux-x86_64`, `linux-aarch64`, `macos-universal2`, **`windows-x86_64`** (new); `release.needs: [build, install-script-e2e, install-ps1-e2e]` (extended) |
| PowerShell structural sanity | `scripts/install.ps1` 247 lines, 9 functions; balanced braces; no PS7-only syntax (`??`, `?.`, `using namespace`) in code body |
| `scripts/install.sh` byte-identity guard | `git diff dbd741b HEAD -- scripts/install.sh` shows only **+4 comment lines** in header; main(), compose_urls(), sha256_compute/extract, download(), print_path_hint, detect_target — **byte-identical** |

**The binding empirical CI gate is `release-test.yml` on Windows** — DEFERRED
until CEO push (see §"CEO action required" below) because the workflow's
`workflow_dispatch` + `windows-latest` runner exec cannot be triggered from
this READ-only session.

## Files landed (release slice)

### NEW

| File | Lines | Role |
|---|---:|---|
| `scripts/install.ps1` | 247 | PowerShell 5.1 compatible installer; parallel to `install.sh`. 9 functions: `Write-Info`, `Resolve-EnvOrDefault`, `Get-Target`, `Get-DownloadUrls`, `Get-Sha256Hex`, `Get-ExpectedSha256`, `Save-RemoteFile`, `Show-PathHintIfNeeded`, `Invoke-Install`. |

### MODIFIED

| File | Net Δ | Change |
|---|---:|---|
| `.github/workflows/release-test.yml` | +127 / −19 | 4th matrix cell `windows-x86_64` (`binary_suffix: ".exe"`); suffix interpolated in 4 build steps; new `install-ps1-e2e` job (6 steps, `pwsh`, `windows-latest`); `release.needs` extended. |
| `README.md` | +14 / −1 | Windows install one-liner: `irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 \| iex` + parallel inspect-first PowerShell block. |
| `scripts/dev-host-setup.md` | +37 / −4 | Target-platform-support table Windows row split: "dev: untested · end-user: supported"; new "Windows clarification" subsection. |
| `scripts/install.sh` | +4 / −0 | Header-comment polish referencing `install.ps1` companion (zero behavioral change). |

## Verification scenarios for Manual Test

### Scenario A — `release-test.yml` structural audit (pre-CI-dispatch sanity)

```sh
git checkout main && git pull --ff-only       # AFTER CEO push

python3 -c "
import yaml
w = yaml.safe_load(open('.github/workflows/release-test.yml'))
print('jobs:', list(w['jobs'].keys()))
print('build matrix targets:', [c['target'] for c in w['jobs']['build']['strategy']['matrix']['include']])
print('build matrix binary_suffix:', [c.get('binary_suffix', '?') for c in w['jobs']['build']['strategy']['matrix']['include']])
print('release.needs:', w['jobs']['release']['needs'])
"
```

Pinned expected output (verified by Main Branch on merged HEAD `6b33383`):

```
jobs: ['build', 'install-script-e2e', 'install-ps1-e2e', 'release']
build matrix targets: ['linux-x86_64', 'linux-aarch64', 'macos-universal2', 'windows-x86_64']
build matrix binary_suffix: ['', '', '', '.exe']
release.needs: ['build', 'install-script-e2e', 'install-ps1-e2e']
```

### Scenario B — `install.ps1` static surface audit

```sh
wc -l scripts/install.ps1                     # expect: 247
grep -c '^function ' scripts/install.ps1      # expect: 9

# PS5.1 compatibility — confirm no PS7-only syntax in CODE (only OK in header comment):
grep -nE '(\?\?|\?\.|using namespace)' scripts/install.ps1
# expect: hits ONLY on lines 9-10 (the header comment block that DOCUMENTS the constraint)
# no hits outside the comment block
```

### Scenario C — `install.ps1` ⇄ `install.sh` semantic parallelism spot-check

Both scripts should follow the same 7-step flow: detect → compose URLs → download → SHA-256 verify → abort-on-mismatch → atomic install → PATH hint. Spot-check the SHA-256 verify + abort step in both:

```sh
grep -nA 10 'compute.*sha256\|Get-Sha256Hex' scripts/install.sh scripts/install.ps1 | head -30
```

Both scripts should print a loud abort banner to **stderr** on mismatch
(install.sh: `printf >&2`; install.ps1: `[Console]::Error.WriteLine`) — then
`exit 1`. Manual Test confirms the abort routes to stderr (so a redirected
stdout pipe like `irm | iex 2>install.log` still surfaces the abort visibly).

### Scenario D — `install.sh` non-regression byte-identity guard

```sh
git diff dbd741b 6b33383 -- scripts/install.sh
```

Expected: **only +4 comment lines** in the header (lines 7-11 area)
referencing the new `install.ps1` companion. Zero changes to `main()`,
`compose_urls()`, `sha256_compute()`, `sha256_extract_expected()`,
`download()`, `print_path_hint_if_needed()`, `detect_target()`. DoD #8
binding.

### Scenario E — README Windows install line

```sh
grep -A 5 'irm .*install.ps1' README.md
```

Expected verbatim (per handoff §"Files in the diff" README row):

```
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
```

Plus the parallel inspect-first PowerShell block. The existing
`curl-pipe-sh` Linux/macOS line MUST be preserved byte-identical (DoD #9 +
non-regression).

### Scenario F — `release-test.yml` empirical CI dispatch (BINDING — CEO post-push)

This is the load-bearing empirical proof of the Windows pipeline. Per
handoff §"Cycle close direction":

```bash
# AFTER CEO push lands main on origin:
gh workflow run release-test.yml --ref main

# Watch:
gh run list --workflow=release-test.yml --limit=1
gh run watch <run-id>
```

Expected outcomes (per handoff §"Verification surface" + §"Cycle close direction"):

| Job | Expected | Notes |
|---|---|---|
| `build (linux-x86_64)`     | success | baseline; no new behavior on existing cells |
| `build (linux-aarch64)`    | success | baseline |
| `build (macos-universal2)` | success | baseline; lipo-fused arm64 + x86_64 unchanged |
| `build (windows-x86_64)`   | **success** | **NEW** — PyApp builds `pyapp.exe` via cargo + dtolnay/rust-toolchain@stable on `windows-latest` |
| `install-script-e2e (linux-x86_64)` | success | unchanged step bodies (binary_suffix expands to "" on linux cell) |
| `install-ps1-e2e (windows-x86_64)` | **success** | **NEW** — pwsh runs install.ps1 against served `windows-x86_64.exe` artifact; clean + idempotent install; envelope `--version --output json` assertion both runs |
| `release` | skipped | `workflow_dispatch` trigger; `if: startsWith(github.ref, 'refs/tags/v')` guard |

Artifact bundle expected from the dispatched run:

```sh
gh run download <run-id>
# expect: 8 files in 4 binary directories — novetest-linux-x86_64{,.sha256},
#         novetest-linux-aarch64{,.sha256}, novetest-macos-universal2{,.sha256},
#         novetest-windows-x86_64.exe{,.sha256}
```

### Scenario G — Empirical envelope from `install-ps1-e2e` job (binding)

Pull the `install-ps1-e2e` job logs and extract the verbatim `novetest/v1`
envelope from the `--version --output json` assertion:

```sh
JOB_ID=$(gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("install.ps1")) | .databaseId')
gh api repos/Nove-Lab/Nove-Test/actions/jobs/$JOB_ID/logs | grep -A 12 '"command": "version"'
```

Expected envelope shape (per orchestration team's parallel pin on merged
HEAD; Windows pipeline serves the same schema):

```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "<windows-temp-path>\\novetest-install\\novetest.exe",
    "installedVersion": "0.1.1",
    "platform": "windows-x86_64",
    "pythonVersion": "<python-build-standalone resolved>",
    "verifiedAt": "<ISO-UTC>"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Manual Test confirms:
- `data.platform == "windows-x86_64"` ✓
- `data.installedVersion == "0.1.1"` ← importlib.metadata path live (closes the prior `"0.0.0"` stub)
- `data.installLocation` ends with `\novetest.exe` (Windows path separators, `.exe` suffix)
- `schema == "novetest/v1"`, `ok == true`, `errors == []`, `warnings == []`

### Scenario H — `install.ps1` local smoke on a real Windows host (OPTIONAL)

Per handoff §"Manual Test team action" #2. Use case for Manual Test with
access to a Windows host / VM / Codespace:

```powershell
# AFTER CEO push + AFTER a v0.1.2 (or whatever tag bundles this slice) is published
# with Windows binary artifacts attached:
$env:NOVETEST_INSTALL_VERSION = "v0.1.2"
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
& "$env:USERPROFILE\.novetest\bin\novetest.exe" --version --output json
```

**Pre-tag-publication caveat**: until PM sequences a v0.1.2 publication cycle
(or whichever tag bundles this slice's Windows binary), the README's
`irm ... | iex` line will **404 against `novetest-windows-x86_64.exe`** —
v0.1.1 was tagged before this slice landed. Substitute by downloading the
`workflow_dispatch` artifact bundle from Scenario F and running install.ps1
locally with `NOVETEST_INSTALL_BASE_URL` overrides. Handoff §"Risks" #7
documents this temporal window.

## Critical edge cases worth probing

1. **README temporal window** (handoff §"Risks" #7). The Windows install line is forward-looking until a v0.1.2 tag is published with Windows binaries. PM should sequence v0.1.2 promptly.
2. **PyApp Windows MSVC build flakiness** (handoff §"Risks" #2). Not encountered locally; CI will gate. If `cargo build --release` fails first run, check Visual Studio Build Tools version drift on the `windows-latest` runner image.
3. **PowerShell `$PID` shadowing** (handoff §"Risks" #3 — RESOLVED). Cleanup step uses `$pidValue`, not `$pid`.
4. **`Move-Item -Force` cross-volume** (handoff §"Risks" #4). `.tmp` staging is UNDER `$prefix` (not `$env:TEMP`) to guarantee same-volume atomic rename.
5. **Live-binary lock on re-install** (handoff §"Risks" #5 — documented constraint). User must close any running `novetest.exe` before re-install. Same limitation as `gh`/`git`/`node` Windows installers; not a defect.
6. **Empty `$env:NOVETEST_INSTALL_BASE_URL` semantic divergence from install.sh** (handoff §"Risks" #6). install.sh distinguishes "unset" from "set-to-empty" via POSIX `${var+x}`; install.ps1's `[Environment]::GetEnvironmentVariable` returns `$null` for unset and `""` for empty, both falling through to the default GitHub URL. Brief §"Failure modes" #10 accepts this; empty-but-set is not in any user contract.

## Notes for PM (per handoff DoD ledger)

- **DoD #6 + #7 CI matrix GREEN** ← BINDING gate is `release-test.yml` workflow_dispatch on merged main; deferred to CEO post-push (Scenario F). Once green, mark closed.
- **DoD #11 `foundations.md` + `delivery-phasing.md` updates** ← drafted in handoff §"Out of scope deferred to PM"; PM applies at cycle close. Three locations: foundations.md §549 Phase-0-scope sentence, §603-608 install matrix table, delivery-phasing.md line 303 Open Q #16 strikethrough.
- **Future-cycle queue #4 + #16** ← marked closed by this slice; PM updates queue at cycle close.
- **`ailovestesting.com` DNS routing** ← still gated by CEO ops (Gap 2 of alpha-full; handoff §"Out of scope" #2). install.ps1 references `raw.githubusercontent.com` URL in README as interim; PM may rotate to `ailovestesting.com/novetest/install.ps1` once DNS lands.

## Cleanup

- Release worktree `/home/yjshin/dev/aispace/novetest-windows-install-ps1` — **removed** ✓
- Release branch `release/windows-install-ps1-and-binary-pipeline` — **deleted** ✓
- Single main worktree remains: `/home/yjshin/dev/aispace/Nove-Test` ✓
- Local `tmp-main` ref used during release-branch rebase — **deleted** ✓
- **`origin/main` push BLOCKED**: HTTP 403, READ-only token. CEO push required.

## CEO push procedure (READ-only auth blocker)

```bash
cd /home/yjshin/dev/aispace/Nove-Test
git log --oneline origin/main..HEAD
# expect ~10 commits pending: dbd741b PM prep + 397fe00 + c76dbbb orchestration
#                              + c25fa2f + 6b33383 release + 2 verification commits

git push origin main
# requires write token on Nove-Lab/Nove-Test (yongjunshin currently READ)

# Then dispatch release-test.yml against the merged main HEAD:
gh workflow run release-test.yml --ref main
gh run list --workflow=release-test.yml --limit=1
gh run watch <run-id>
```

The 4 build cells + 2 install-e2e jobs are the binding empirical proof for
DoD #6 + #7.
