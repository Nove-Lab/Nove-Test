# Installation

This page covers:

1. The one-line install command for Linux / macOS / Windows.
2. Where the binary lands.
3. Two sanity checks — `novetest --version` and `novetest --help` —
   with sample output for both audiences.
4. Environment variables you almost never need.
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

All three scripts are **idempotent** (re-running upgrades in place
via atomic rename), **sudo-free** (write to `~/.local/bin/`), and
**abort loudly on a SHA-256 mismatch** rather than write a partial
binary.

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

1. Detects OS + arch via `uname` (POSIX) or
   `[System.Runtime.InteropServices.RuntimeInformation]` (PowerShell).
2. Resolves the asset name:
   - Linux × x86_64 -> `novetest-linux-x86_64`
   - Linux × aarch64 -> `novetest-linux-aarch64`
   - macOS (any arch) -> `novetest-macos-universal2` (fat binary;
     Mach-O slice picked at exec)
   - Windows × x86_64 -> `novetest-windows-x86_64.exe`
3. Downloads the binary **and** its `.sha256` sidecar from the
   latest GitHub Release.
4. Computes SHA-256 locally
   (`sha256sum` / `shasum` / `openssl dgst` / `Get-FileHash`).
5. Compares to the sidecar. **Mismatch -> loud abort**; nothing is
   written under `~/.local/bin/`.
6. Atomically stages the binary as `novetest.tmp`, `chmod 0755`s
   it, then renames to its final name. On the same filesystem this
   is one `rename(2)` syscall; concurrent readers see the old
   binary or the new one, never a partial.
7. Tests whether `~/.local/bin/` is on `PATH`. If not, prints a
   one-line hint.
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

Then `source` the profile (or open a new shell) and re-check.

### Pinning a specific version

```bash
NOVETEST_INSTALL_VERSION=v0.1.2 \
  curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

The default (`latest`) resolves the most recent GitHub Release at
install time. Pinning a tag gives you deterministic, reproducible
installs — recommended for CI pipelines and agent-managed hosts.

---

## 2. Sanity check #1 — `novetest --version`

The shortest possible round-trip to confirm the binary works.

::: tabs
@tab For human

```bash
novetest --version
```

You should see exactly one line:

```
novetest 0.1.2 (Python 3.11.9, linux-x86_64)
```

Three values, separated by spaces and parentheses:

| Position | Meaning |
|---|---|
| `0.1.2` | The semver of the installed CLI. Should match the latest GitHub Release. |
| `Python 3.11.9` | The bundled CPython interpreter. You did NOT install this; PyApp brings it. |
| `linux-x86_64` | `{system}-{machine}`, lowercased. Tells you which asset got chosen. |

Exit code: `0`. If you see anything else (a stack trace, a Python
error, nothing at all), see
[Troubleshooting](./troubleshooting.md#install-issues).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest --version
```

Round-trip envelope:

```json
{
  "schema": "novetest/v1",
  "command": "version",
  "ok": true,
  "data": {
    "installedVersion": "0.1.2",
    "commandName": "novetest",
    "installLocation": "/home/you/.local/bin/novetest",
    "pythonVersion": "3.11.9",
    "platform": "linux-x86_64",
    "verifiedAt": "2026-06-22T07:17:07Z"
  },
  "errors": [],
  "warnings": []
}
```

| Field | Type | Meaning |
|---|---|---|
| `installedVersion` | string (semver) | The semver of the installed CLI. Use this to gate version-dependent behavior in your agent (`if version >= "0.1.2": ...`). |
| `commandName` | string | Always `"novetest"`. Pin against this if you want to verify you are looking at the right CLI. |
| `installLocation` | string (absolute path) | Path of the binary on disk. |
| `pythonVersion` | string (semver) | The bundled CPython. You do not need to install Python yourself; the binary brings its own. |
| `platform` | string | `{system}-{machine}`, lowercased. Useful for routing platform-specific assumptions in your agent. |
| `verifiedAt` | string (ISO-8601 UTC) | Captured at envelope-build time. `Z` suffix is canonical. |

Exit code: **0**. There is no other expected exit code for
`--version`.

:::

---

## 3. Sanity check #2 — `novetest --help`

The list of every verb the CLI exposes. `--help` / `-h` and bare
`novetest` (no args) are equivalent.

::: tabs
@tab For human

```bash
novetest --help
```

You should see an aligned listing of every verb, grouped into two
sections:

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

Two intents:

- **Onboarding** — verbs you run **once** to come online. After
  install you read this list, run `novetest init` inside your
  project, and you're done with this section forever.
- **Operating** — the verbs you use **during normal work**.
  `novetest test` is the headline; everything else is either a
  deeper view (`inspect`, `status`) or a power-user surface
  (`coverage`, `regression`, `localization`, `replay`, `memory`).

Exit code: `0`.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest --help
```

This emits the **command surface envelope** — a machine-readable
self-description of every verb the CLI exposes. This is the
canonical way for an AI agent to discover what verbs exist without
grepping documentation.

Shape:

```json
{
  "schema": "novetest/v1",
  "command": "help",
  "ok": true,
  "data": {
    "schemaVersion": 1,
    "onboarding": [
      {
        "name": "novetest --version",
        "summary": "Print CLI identity envelope.",
        "group": "onboarding",
        "availableInPhase": 0
      },
      {
        "name": "novetest --help",
        "summary": "Print command surface envelope.",
        "group": "onboarding",
        "availableInPhase": 0
      },
      {
        "name": "novetest init",
        "summary": "Initialize a Project Store under .novetest/ in the current workspace.",
        "group": "onboarding",
        "availableInPhase": 1
      }
    ],
    "operating": [
      {
        "name": "novetest test",
        "summary": "Run tests with integrated orchestration and synthesize a recommendation.",
        "group": "orchestration",
        "availableInPhase": 6
      },
      {
        "name": "novetest run",
        "summary": "Execute a Test Target via the native engine and persist a Run Record.",
        "group": "run",
        "availableInPhase": 1
      },
      {
        "name": "novetest licenses",
        "summary": "List third-party components Nove Test redistributes or links to.",
        "group": "orchestration",
        "availableInPhase": 0
      }
      /* ... full list includes: status, inspect, compare, replay,
         coverage.show, coverage.diff, regression.compare,
         regression.latest, localization, localization.latest,
         memory.list, memory.show, memory.delete */
    ]
  },
  "errors": [],
  "warnings": []
}
```

Two arrays:

- `data.onboarding[]` — verbs typically run **once** to come online:
  `--version`, `--help`, `init`.
- `data.operating[]` — verbs run during normal use.

Each item carries `name`, `summary`, `group`, and
`availableInPhase`. The pair `(group, name)` is stable; rely on it
for programmatic dispatch. `availableInPhase` lets you reason about
maturity — at MVP, every operating verb has landed.

Exit code: **0**.

#### Why an agent should call `--help` at startup

Because the verb list is data, not documentation. If your agent
ships with hard-coded knowledge of `["init", "test", "status", ...]`
and the next novetest version adds a new verb you would benefit
from, your agent can discover it without a code release — just by
re-parsing this envelope.

Pin against `data.operating[*].name`; do NOT pin against
`availableInPhase` (it is informational, not a gate).

:::

---

## 4. Environment overrides (you almost never need these)

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Where the binary is placed during install. |
| `NOVETEST_INSTALL_VERSION` | `latest` | A tag like `v0.1.2` to pin to during install. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | GitHub `owner/repo` for URL composition. |
| `NOVETEST_OUTPUT` | (auto: `text` on TTY, `json` when piped) | Force `text` / `json` / `ndjson` output. |
| `NOVETEST_HOME` | (parent-directory walk-up to find `.novetest/`) | Pin a specific Project Store path. Skip the walk-up. Use only for hermetic harnesses. |

Precedence rule (canonical Unix):

```
explicit --output flag  >  NOVETEST_OUTPUT env  >  TTY auto-detect
```

---

## 5. Verifying a clean install

::: tabs
@tab For human

The three sanity checks from above are enough. If
`novetest --version` and `novetest --help` both print clean output
and exit 0, you can move on to the
[Quick Start](./quick-start.md).

If something looks off, jump to
[Troubleshooting -> Install issues](./troubleshooting.md#install-issues).

@tab For agent

A minimal three-step probe — copy this into your agent's pre-flight:

```bash
# 1) Binary on PATH
command -v novetest || { echo "novetest missing"; exit 1; }

# 2) Version envelope round-trips
NOVETEST_OUTPUT=json novetest --version | jq -e '.ok == true and .schema == "novetest/v1"' \
  || { echo "version envelope malformed"; exit 1; }

# 3) Help envelope enumerates the operating surface
NOVETEST_OUTPUT=json novetest --help | jq -e '.data.operating | length > 10' \
  || { echo "help envelope shrunk unexpectedly"; exit 1; }
```

If all three pass, you can drive novetest.

:::

---

## 6. Re-install and uninstall

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

That wipes all stored runs, coverage facts, regression baselines,
and SBFL findings for that project. It does **not** touch your
source code or your tests.

---

## Caveats pinned by the MVP

- **First-run cold start** is on the order of 5–25 seconds (PyApp
  self-extracts its bundled Python on first invocation per binary
  version per user). Subsequent invocations are warm and fast.
- **Linux i686 / armv7l** are not supported. Linux ships x86_64 and
  aarch64 only.
- **macOS arm64** uses the `universal2` fat binary, picked
  automatically at exec time.

---

## What to read next

- **[Quick Start](./quick-start.md)** — the 4-step canonical happy
  path: `init` -> `test` -> read the recommendation ->
  (optional) `inspect`.
- **[Supported Languages](./supported-languages.md)** — if your
  project is not Python, the one-line toolchain difference your
  engine needs before you `novetest init`.
- **[Troubleshooting](./troubleshooting.md)** — if a sanity check
  didn't return clean output.
