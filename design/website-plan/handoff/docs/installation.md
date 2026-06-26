# Installation

This page covers:

1. The one-line install command for Linux / macOS / Windows.
2. Direct binary download and a Python-tooling alternative.
3. Where the binary lands.
4. Two sanity checks — `novetest --version` and `novetest --help`.
5. Environment overrides, re-install, and uninstall.

Nove Test ships as a single self-contained binary — a PyApp bundle that
embeds CPython 3.11 plus the `novetest` wheel — so the binary path needs
**no Python toolchain** on your machine. Current version: **0.1.2**.

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

Both scripts are **idempotent** (re-running upgrades in place via atomic
rename), **sudo-free** (write to `~/.local/bin/`), and **abort loudly on a
SHA-256 mismatch** rather than write a partial binary.

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

### What the install script does, step by step

1. Detects OS + arch.
2. Resolves the GitHub Release asset name:
   - Linux × x86_64 -> `novetest-linux-x86_64`
   - Linux × aarch64 -> `novetest-linux-aarch64`
   - macOS (any arch) -> `novetest-macos-universal2` (one fat binary covering Intel + Apple Silicon)
   - Windows × x86_64 -> `novetest-windows-x86_64.exe`
3. Downloads the binary **and** its `.sha256` sidecar.
4. Computes SHA-256 locally (`sha256sum` / `shasum` / `openssl` / `Get-FileHash`).
5. Compares to the sidecar. **Mismatch -> loud abort**; nothing is written under the install prefix.
6. Atomically renames the verified binary into `~/.local/bin/novetest`.
7. Tests whether the install prefix is on `PATH`; if not, prints a one-line hint.

The script needs a downloader (`curl` or `wget`) and a SHA-256 tool.

### Supported platforms

| OS | Arch | Asset |
|---|---|---|
| Linux | x86_64 | `novetest-linux-x86_64` |
| Linux | aarch64 | `novetest-linux-aarch64` |
| macOS | universal2 (Intel + Apple Silicon) | `novetest-macos-universal2` |
| Windows | x86_64 | `novetest-windows-x86_64.exe` |

Linux i686 / armv7l and Windows arm64 are **not** built.

### Where the binary lives

| OS | Default path |
|---|---|
| Linux | `~/.local/bin/novetest` |
| macOS | `~/.local/bin/novetest` |
| Windows | `%USERPROFILE%\.local\bin\novetest.exe` |

Override with `NOVETEST_INSTALL_PREFIX=...` if you need elsewhere.

### If `~/.local/bin` is not on your PATH

```bash
# Linux / macOS (~/.bashrc, ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"
```

```powershell
# Windows (PowerShell profile)
$env:PATH = "$HOME\.local\bin;$env:PATH"
```

Then `source` the profile (or open a new shell) and re-check.

### Pinning a specific version

```bash
NOVETEST_INSTALL_VERSION=v0.1.2 \
  curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

The default (`latest`) resolves the most recent GitHub Release at install
time. Pinning a tag gives deterministic, reproducible installs — recommended
for CI pipelines and agent-managed hosts.

---

## 2. Other ways to install

### Direct binary download (no script)

```bash
base=https://github.com/Nove-Lab/Nove-Test/releases/latest/download
target=novetest-linux-x86_64   # or linux-aarch64 / macos-universal2 / windows-x86_64
curl -fsSLO "$base/$target"
curl -fsSLO "$base/$target.sha256"
sha256sum -c "$target.sha256"          # must say: OK
chmod +x "$target" && mv "$target" ~/.local/bin/novetest
```

### For Python-tooling users (secondary)

If you already manage CLIs with `uv` or `pipx` and have Python **>= 3.11**:

```bash
uv tool install novetest
# or
pipx install novetest
```

The curl/PowerShell binary install is the primary, supported path; the
`uv` / `pipx` route is a convenience for Python-tooling users. There is no
Homebrew, Docker, `npm`, or `cargo` distribution.

---

## 3. Sanity check #1 — `novetest --version`

The shortest round-trip to confirm the binary works. It reports the CLI
identity envelope; on a TTY the same values render as text.

::: tabs
@tab For human

```bash
novetest --version
```

The reported identity (JSON shown for clarity):

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
| `installedVersion` | CLI version. Should be `0.1.2`. |
| `commandName` | Always `novetest`. |
| `installLocation` | Path on disk. On a binary install this is your installed `novetest`; the capture above was run from a source checkout, so it shows that interpreter. |
| `pythonVersion` | The bundled CPython 3.11.x — you did not install it. |
| `platform` | `{system}-{machine}`, lowercased. |
| `verifiedAt` | ISO-8601 UTC timestamp of when this identity envelope was generated (i.e. when you ran `--version`) — not a build time; it changes every invocation. |

Exit code: `0`. If you see a stack trace or nothing at all, see
[Troubleshooting](./troubleshooting.md#install-issues).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest --version
```

Real captured envelope:

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

Top-level keys are exactly `{schema, command, ok, data, errors, warnings}`
(emitted sorted) — there is no top-level `version`, `verb`, or `exit_code`.
Gate version-dependent behavior on `data.installedVersion`; confirm identity
with `data.commandName == "novetest"`. Route platform assumptions on
`data.platform`.

Exit code: **0**. There is no other expected exit code for `--version`.

:::

---

## 4. Sanity check #2 — `novetest --help`

The list of every verb the CLI exposes. `novetest --help` and bare
`novetest` (no args) are equivalent — bare `novetest` prints help, it does
not run tests.

::: tabs
@tab For human

```bash
novetest --help
```

Real output, grouped into two sections:

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

- **Onboarding** — verbs you run once to come online: `--version`, `--help`, `init`, and `reset`.
- **Operating** — the verbs you use during normal work. `novetest test` is the headline; everything else is either a deeper view (`inspect`, `status`) or a power-user surface (`coverage`, `regression`, `localization`, `replay`, `memory`).

Exit code: `0`.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest --help
```

Emits the **command surface envelope** — the canonical way for an agent to
discover verbs without grepping docs. Real output (`data.operating`
truncated; elided items are real, not invented):

```json
{
  "command": "help",
  "data": {
    "onboarding": [
      { "availableInPhase": 0, "group": "onboarding", "name": "novetest --version", "summary": "Print CLI identity envelope." },
      { "availableInPhase": 0, "group": "onboarding", "name": "novetest --help",    "summary": "Print command surface envelope." },
      { "availableInPhase": 1, "group": "onboarding", "name": "novetest init",      "summary": "Initialize a Project Store under .novetest/ in the current workspace." },
      { "availableInPhase": 7, "group": "onboarding", "name": "novetest reset",     "summary": "Wipe the active Project Store and re-initialize (requires --confirm)." }
    ],
    "operating": [
      { "availableInPhase": 6, "group": "orchestration", "name": "novetest test", "summary": "Run tests with integrated orchestration and synthesize a recommendation." },
      { "availableInPhase": 1, "group": "run",           "name": "novetest run",  "summary": "Execute a Test Target via the native engine and persist a Run Record." }
      /* ... also: memory list/show/delete, inspect, status, coverage show/diff,
         regression compare/latest, compare, localization, replay, licenses */
    ],
    "schemaVersion": 1
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Two arrays under `data`: `onboarding[]` (`--version`, `--help`, `init`,
`reset`) and `operating[]` (the 15 work verbs). Each item carries `name`,
`summary`, `group`, and `availableInPhase`; the pair `(group, name)` is
stable — rely on it for dispatch. Discover verbs from
`data.operating[*].name` instead of hard-coding them; do **not** gate on
`availableInPhase` (informational, not a capability flag).

Exit code: **0**.

:::

---

## 5. Environment overrides

Install-script variables (script-only; they do not affect the CLI at runtime):

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Where the binary is placed during install. |
| `NOVETEST_INSTALL_VERSION` | `latest` | A tag like `v0.1.2` to pin to during install. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | GitHub `owner/repo` for URL composition. |
| `NOVETEST_INSTALL_BASE_URL` | (GitHub Releases) | Override the download base URL. |

Runtime output mode:

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_OUTPUT` | auto (`text` on TTY, `json` when piped) | Force `text` / `json` / `ndjson` output. |

Precedence rule:

```
explicit --output flag  >  NOVETEST_OUTPUT env  >  TTY auto-detect
```

---

## 6. Verifying a clean install

::: tabs
@tab For human

The two sanity checks above are enough. If `novetest --version` and
`novetest --help` both print clean output and exit 0, move on to the
[Quick Start](./quick-start.md). If something looks off, jump to
[Troubleshooting -> Install issues](./troubleshooting.md#install-issues).

@tab For agent

A minimal pre-flight probe — copy into your agent's startup:

```bash
# 1) Binary on PATH
command -v novetest || { echo "novetest missing"; exit 1; }

# 2) Version envelope round-trips
NOVETEST_OUTPUT=json novetest --version \
  | jq -e '.ok == true and .schema == "novetest/v1" and .data.installedVersion == "0.1.2"' \
  || { echo "version envelope malformed"; exit 1; }

# 3) Help envelope enumerates the operating surface
NOVETEST_OUTPUT=json novetest --help | jq -e '.data.operating | length >= 15' \
  || { echo "help envelope shrunk unexpectedly"; exit 1; }
```

If all three pass, you can drive novetest.

:::

---

## 7. Re-install and uninstall

- **Re-install / upgrade**: re-run the same install command. The script always overwrites with the verified binary via atomic rename.
- **Uninstall**: `rm ~/.local/bin/novetest` (Linux/macOS) or `Remove-Item $HOME\.local\bin\novetest.exe` (Windows). The CLI keeps no state outside per-project `.novetest/` directories, so removing the binary removes the CLI entirely.

To delete a specific project's history (without touching its source or tests):

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

## What to read next

- **[Quick Start](./quick-start.md)** — the 4-step canonical happy path: `init` -> `test` -> read the recommendation -> (optional) `inspect`.
- **[Supported Languages](./supported-languages.md)** — if your project is not Python, the one-line toolchain difference your engine needs before you `novetest init`.
- **[Troubleshooting](./troubleshooting.md)** — if a sanity check didn't return clean output.
