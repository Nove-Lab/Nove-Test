# Install + First Sanity Checks (Human)

This page covers:

1. The one-line install (Linux, macOS, Windows).
2. Direct binary download (no script) and a Python-tooling alternative.
3. Where the binary lands and how to get it on `PATH`.
4. The sanity checks — `novetest --version` and `novetest --help`.
5. Install-script environment overrides, re-install, and uninstall.

Nove Test ships as a single self-contained binary (a PyApp bundle that
embeds CPython 3.11 + the `novetest` wheel), so the binary path needs **no
Python toolchain on your machine**. Current version: **0.1.2**.

---

## 1. The install command

### Linux + macOS

```bash
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
```

Both scripts are idempotent (re-running upgrades in place via atomic
rename), sudo-free (write to `~/.local/bin/`), and abort loudly on a
SHA-256 mismatch rather than write a partial binary.

### Inspect-first (recommended for first-time users)

```bash
# Linux / macOS
curl -fsSL -o install.sh \
  https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh
less install.sh   # read it
sh install.sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 -OutFile install.ps1
Get-Content install.ps1   # read it
.\install.ps1
```

### What the script does, step by step

1. Detects OS + arch.
2. Resolves the GitHub Release asset name:
   - Linux × x86_64 → `novetest-linux-x86_64`
   - Linux × aarch64 → `novetest-linux-aarch64`
   - macOS (any arch) → `novetest-macos-universal2` (one fat binary covering Intel + Apple Silicon)
   - Windows × x86_64 → `novetest-windows-x86_64` (`.exe`)
3. Downloads the binary **and** its `.sha256` sidecar.
4. Computes SHA-256 locally (`sha256sum` / `shasum` / `openssl` / `Get-FileHash`).
5. Compares to the sidecar. **Mismatch → loud abort**; nothing is written under the install prefix.
6. Atomically renames the verified binary into `~/.local/bin/novetest`.
7. Tests whether the install prefix is on `PATH`; if not, prints a one-line hint.

The script needs a downloader (`curl` or `wget`) and a SHA-256 tool
(`sha256sum`, `shasum`, or `openssl`).

### Supported platforms

| OS | Arch | Asset |
|---|---|---|
| Linux | x86_64 | `novetest-linux-x86_64` |
| Linux | aarch64 | `novetest-linux-aarch64` |
| macOS | universal2 (Intel + Apple Silicon) | `novetest-macos-universal2` |
| Windows | x86_64 | `novetest-windows-x86_64.exe` |

Linux i686 / armv7l and Windows arm64 are **not** built. macOS is a single
universal2 binary — there is no per-arch split.

### Where the binary lives

| OS | Default path |
|---|---|
| Linux | `~/.local/bin/novetest` |
| macOS | `~/.local/bin/novetest` |
| Windows | `%USERPROFILE%\.local\bin\novetest.exe` |

Override with `NOVETEST_INSTALL_PREFIX=...` if you need elsewhere.

### If `~/.local/bin` is not on your PATH

Add this to your shell profile:

```bash
# Linux / macOS (~/.bashrc, ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"
```

```powershell
# Windows (PowerShell profile)
$env:PATH = "$HOME\.local\bin;$env:PATH"
```

Then `source` the profile or open a new shell and re-check.

---

## 2. Other ways to install

### Direct binary download (no script)

Grab the asset for your platform from the latest GitHub Release, verify it,
and put it on your `PATH`:

```bash
curl -fsSLO https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64
curl -fsSLO https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64.sha256
sha256sum -c novetest-linux-x86_64.sha256        # must say: OK
chmod +x novetest-linux-x86_64
mv novetest-linux-x86_64 ~/.local/bin/novetest
```

Swap `novetest-linux-x86_64` for your target from the table above.

### For Python-tooling users (secondary)

If you already manage CLIs with `uv` or `pipx`, you can install the wheel
(requires Python **>= 3.11**):

```bash
uv tool install novetest
# or
pipx install novetest
```

The curl/PowerShell binary install is the primary, supported path; the
`uv` / `pipx` route is offered as a convenience for Python-tooling users.

There is no Homebrew, Docker, `npm`, or `cargo` distribution.

---

## 3. Sanity check #1 — `novetest --version`

```bash
novetest --version
```

`--version` reports the CLI identity envelope. Quoting a real run (JSON
mode shown):

```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/yjshin/dev/aispace/Nove-Test/.venv/bin/python3",
    "installedVersion": "0.1.2",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.15",
    "verifiedAt": "2026-06-25T06:20:42.645279Z"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `installedVersion` | The CLI version. Should be `0.1.2`. |
| `commandName` | Always `novetest`. |
| `installLocation` | Path on disk. On a binary install this points at your installed `novetest`; the example above was captured running from a source checkout, so it shows that interpreter. |
| `pythonVersion` | The interpreter behind the CLI. The binary brings its own CPython 3.11.x — you did not install it. |
| `platform` | `{system}-{machine}`, lowercased — which asset you are running. |
| `verifiedAt` | ISO-8601 UTC timestamp of when you ran `--version`; it changes every invocation (it is **not** a build time). |

Exit code: `0`. On a TTY the same identity renders in text form; the values
are identical. If you see a stack trace or nothing at all, see
[troubleshooting.md](./troubleshooting.md).

---

## 4. Sanity check #2 — `novetest --help`

```bash
novetest --help
```

`novetest --help` (or simply running `novetest` with no args) prints every
verb the CLI exposes, grouped into two sections. Real output:

```
novetest — AI-first testing orchestration

Onboarding:
  novetest --version           Print CLI identity envelope.
  novetest --help              Print command surface envelope.
  novetest init                Initialize a Project Store under .novetest/ in the current workspace.
  novetest reset               Wipe the active Project Store and re-initialize (requires --confirm).

Operating:
  novetest test                Run tests with integrated orchestration and synthesize a recommendation.
  novetest run                 Execute a Test Target via the native engine and persist a Run Record.
  novetest memory list         List Memory Entries in Run History.
  novetest memory show         Show a Memory Entry by Run Reference.
  novetest memory delete       Tombstone a Memory Entry; Run Reference remains resolvable.
  novetest inspect             Aggregate run view across Memory and derived facts.
  novetest status              Latest run plus per-sub-report availability summary.
  novetest coverage show       Show Coverage Facts for a run.
  novetest coverage diff       Diff Coverage Facts between two runs.
  novetest regression compare  Compare two runs into a Regression Fact set.
  novetest regression latest   Compute Regression Facts versus the latest baseline.
  novetest compare             Composed Regression and Coverage delta between two runs.
  novetest localization        Ranked suspicious code locations for a run.
  novetest replay              Re-execute a stored run and classify reproducibility.
  novetest licenses            List third-party components Nove Test redistributes or links to.
```

- **Onboarding** — verbs you run once to come online: `--version`, `--help`, `init`, and `reset` (the wipe-and-re-init escape hatch).
- **Operating** — the verbs you use during normal work. `novetest test` is the headline; everything else is either a deeper view (`inspect`, `status`) or a power-user surface (`coverage`, `regression`, `localization`, `replay`, `memory`).

Exit code: `0`.

---

## 5. Install-script environment overrides

You almost never need these; they tune the install script, not the CLI.

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Where the binary is placed. |
| `NOVETEST_INSTALL_VERSION` | `latest` | A tag like `v0.1.2` to pin to during install. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | GitHub `owner/repo` for URL composition. |
| `NOVETEST_INSTALL_BASE_URL` | (GitHub Releases) | Override the download base URL. |

To pin a version for a reproducible install:

```bash
NOVETEST_INSTALL_VERSION=v0.1.2 \
  curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

Separately, `NOVETEST_OUTPUT=text|json|ndjson` controls the CLI's output
mode at runtime (auto-detects: text on a TTY, JSON when piped).

---

## 6. Re-install and uninstall

- **Re-install / upgrade**: re-run the same install command. The script always overwrites with the verified binary via atomic rename.
- **Uninstall**: `rm ~/.local/bin/novetest` (Linux/macOS) or `Remove-Item $HOME\.local\bin\novetest.exe` (Windows). The CLI keeps no state outside per-project `.novetest/` directories, so removing the binary removes the CLI entirely.

To delete a specific project's history without touching its source or tests:

```bash
cd /path/to/project
novetest reset --confirm   # wipe + re-initialize the Project Store
# or remove it outright:
rm -rf .novetest/
```

---

## Caveats pinned by the MVP

- **First-run cold start** is on the order of 5–15 seconds (PyApp unpacks its embedded Python once per binary version). Subsequent invocations are warm and fast.
- The SHA-256 check is a real integrity gate: a mismatch aborts and writes nothing.
- The binary bundles CPython 3.11; the `>= 3.11` Python requirement only applies to the secondary `uv` / `pipx` path.

---

## Next

Head to [quick-start.md](./quick-start.md) for the canonical 4-step happy
path. If your project is not Python, glance at
[languages.md](./languages.md) for the one-line toolchain difference your
engine needs before you `novetest init`.
