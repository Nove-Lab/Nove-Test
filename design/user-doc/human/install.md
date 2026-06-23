# Install + First Sanity Checks (Human)

This page covers:

1. The one-line install (Linux, macOS, Windows).
2. Where the binary lands.
3. Two sanity checks — `novetest --version` and `novetest --help` — and the text-mode output you should expect.
4. Environment overrides you almost never need.
5. Re-install and uninstall.

---

## 1. The install command

### Linux + macOS

```bash
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

### Windows (PowerShell 5.1+)

```powershell
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
```

All three scripts are idempotent (re-running upgrades in place via
atomic rename), sudo-free (write to `~/.local/bin/`), and abort loudly
on a SHA-256 mismatch rather than write a partial binary.

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

1. Detects OS + arch via `uname` (POSIX) or `[System.Runtime.InteropServices.RuntimeInformation]` (PowerShell).
2. Resolves the asset name:
   - Linux × x86_64 → `novetest-linux-x86_64`
   - Linux × aarch64 → `novetest-linux-aarch64`
   - macOS (any arch) → `novetest-macos-universal2` (fat binary; Mach-O slice picked at exec)
   - Windows × x86_64 → `novetest-windows-x86_64.exe`
3. Downloads the binary **and** its `.sha256` sidecar from the latest GitHub Release.
4. Computes SHA-256 locally (`sha256sum` / `shasum` / `openssl dgst` / `Get-FileHash`).
5. Compares to the sidecar. **Mismatch → loud abort**; nothing is written under `~/.local/bin/`.
6. Atomically stages the binary as `novetest.tmp`, `chmod 0755`s it, then renames to its final name. On the same filesystem this is one `rename(2)` syscall; concurrent readers see the old binary or the new one, never a partial.
7. Tests whether `~/.local/bin/` is on `PATH`. If not, prints a one-line hint.
8. Prints `Run 'novetest --version' to verify.`

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

## 2. Sanity check #1 — `novetest --version`

```bash
novetest --version
```

`--version` and `-v` are identical. In your terminal you should see
exactly one line:

```
novetest 0.1.2 (Python 3.11.9, linux-x86_64)
```

Three values, separated by spaces and parentheses:

| Position | Meaning |
|---|---|
| `0.1.2` | The semver of the installed CLI. Should match the latest GitHub Release. |
| `Python 3.11.9` | The bundled CPython interpreter. You did NOT install this; PyApp brings it. |
| `linux-x86_64` | `{system}-{machine}`, lowercased. Tells you which asset got chosen. |

Exit code: `0`. If you see anything else (a stack trace, a Python error,
nothing at all), see [troubleshooting.md](./troubleshooting.md).

---

## 3. Sanity check #2 — `novetest --help`

```bash
novetest --help
```

`--help` / `-h` (or simply running `novetest` with no args) prints an
aligned listing of every verb the CLI exposes, grouped by section:

```
novetest — AI-first testing orchestration

Onboarding:
  novetest --version  Print CLI identity envelope.
  novetest --help     Print command surface envelope.
  novetest init       Initialize a Project Store under .novetest/ in the current workspace.

Operating:
  novetest test          Run tests with integrated orchestration and synthesize a recommendation.
  novetest run           Execute a Test Target via the native engine and persist a Run Record.
  novetest status        Summarize the latest run and which sub-reports are available.
  novetest inspect       Aggregate run summary plus all derived facts for a single run.
  novetest compare       Composed regression + coverage delta for a baseline/target pair.
  novetest replay        Re-execute a prior run; classify reproducibility.
  novetest licenses      List third-party components Nove Test redistributes or links to.
  novetest coverage      Coverage engine: show / diff per-run coverage facts.
  novetest regression    Regression engine: compare / resolve latest pair.
  novetest localization  Fault localization (SBFL): rank suspicious code locations.
  novetest memory        Memory store: list / show / delete (tombstone) run history.
```

Two sections, two intents:

- **Onboarding** — verbs you run **once** to come online. After install you read this list, run `novetest init` inside your project, and you're done with this section forever.
- **Operating** — the verbs you use **during normal work**. `novetest test` is the headline; everything else is either a deeper view (`inspect`, `status`) or a power-user surface (`coverage`, `regression`, `localization`, `replay`, `memory`).

Exit code: `0`.

---

## 4. Environment overrides (you almost never need these)

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Where the binary is placed during install. |
| `NOVETEST_INSTALL_VERSION` | `latest` | A tag like `v0.1.2` to pin to during install. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | GitHub `owner/repo` for URL composition. |
| `NOVETEST_OUTPUT` | (auto: `text` on TTY, `json` when piped) | Force `text` / `json` / `ndjson` output. |

If you want to see the JSON envelope (e.g. while sanity-checking your
own script's parser), set `NOVETEST_OUTPUT=json` once at session
start:

```bash
export NOVETEST_OUTPUT=json
novetest --version    # now prints the full envelope, not the one-liner
```

The text-mode one-liner is just a projection of the same envelope.

---

## 5. Re-install and uninstall

- **Re-install / upgrade**: re-run the same install command. The
  script always overwrites with the downloaded binary via atomic
  rename.
- **Uninstall**: `rm ~/.local/bin/novetest` (Linux/macOS) or
  `Remove-Item $HOME\.local\bin\novetest.exe` (Windows). The CLI
  keeps no state outside of per-project `.novetest/` directories,
  so removing the binary removes the CLI entirely.

If you also want to delete a specific project's history:

```bash
cd /path/to/project
rm -rf .novetest/
```

That wipes all stored runs, coverage facts, regression baselines, and
SBFL findings for that project. It does NOT touch your source code or
your tests.

---

## Caveats pinned by the MVP

- **First-run cold start** is on the order of 5–25 seconds (the PyApp
  self-extracting bundle expands its bundled Python on first
  invocation; subsequent invocations are warm and fast). This is a
  one-time cost per binary version per user.
- **Linux i686 / armv7l** are not supported. Linux ships x86_64 and
  aarch64 only.
- **macOS arm64** uses the `universal2` fat binary, picked
  automatically at exec time.

---

## Next

Head to [quick-start.md](./quick-start.md) for the canonical 4-step
happy path. If your project is not Python, glance at
[languages.md](./languages.md) for the one-line toolchain difference
your engine needs before you `novetest init`.
