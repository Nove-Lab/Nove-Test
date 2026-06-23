# Install + First Sanity Checks (Agent)

This page covers:

1. The one-line install for Linux / macOS / Windows.
2. The two sanity envelopes (`version`, `help`) you should round-trip before driving any real project.
3. Env vars + the precedence rule.
4. What the install script does step by step (in case you delegate the install to a host script).

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

Idempotent (re-running upgrades in place via atomic rename), sudo-free
(`~/.local/bin/`), aborts loudly on SHA-256 mismatch. SHA-256 verification
is **mandatory** — you can rely on the script never writing a
non-verified binary to disk.

After the script finishes, the binary lives at:

| OS | Path |
|---|---|
| Linux | `~/.local/bin/novetest` |
| macOS | `~/.local/bin/novetest` |
| Windows | `%USERPROFILE%\.local\bin\novetest.exe` |

If `~/.local/bin/` is not on PATH at install time, the script prints a
hint and exits 0. Your wrapper should either pre-set PATH or add the
hint line to the user's shell profile.

### Pinning a specific version

```bash
NOVETEST_INSTALL_VERSION=v0.1.2 \
  curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

The default (`latest`) resolves the most recent GitHub Release at install
time. Pinning a tag gives you deterministic, reproducible installs.

---

## 2. Sanity check #1 — `novetest --version`

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

Exit code: **0**. There is no other expected exit code for `--version`.

---

## 3. Sanity check #2 — `novetest --help`

```bash
NOVETEST_OUTPUT=json novetest --help
```

This emits the **command surface envelope** — a machine-readable
self-description of every verb the CLI exposes. This is the canonical
way for an AI agent to discover what verbs exist without grepping
documentation.

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

- `data.onboarding[]` — verbs you typically run **once** to come online: `--version`, `--help`, `init`.
- `data.operating[]` — verbs you run during normal use.

Each item carries `name`, `summary`, `group`, and `availableInPhase`.
The pair `(group, name)` is stable; rely on it for programmatic
dispatch. `availableInPhase` lets you reason about maturity — at MVP,
every operating verb has landed (phases 0–6 are all complete; phase 7
MCP is post-MVP).

Exit code: **0**.

### Why an agent should call `--help` at startup

Because the verb list is data, not documentation. If your agent ships
with hard-coded knowledge of `["init", "test", "status", ...]` and
the next Nove Test version adds a new verb you would benefit from
(e.g. `novetest workspaces test` post-MVP), your agent can discover
it without a code release — just by re-parsing this envelope.

Pin against `data.operating[*].name`; do NOT pin against
`availableInPhase` (it is informational, not a gate).

---

## 4. Env vars

| Variable | Default | Effect |
|---|---|---|
| `NOVETEST_OUTPUT` | (auto: `text` on TTY, `json` when piped) | Force the output mode. **Set this to `json` once at session start.** |
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Install-script only. |
| `NOVETEST_INSTALL_VERSION` | `latest` | Install-script only. Pin to a tag for deterministic installs. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | Install-script only. |

Precedence rule (canonical Unix):

```
explicit --output flag  >  NOVETEST_OUTPUT env  >  TTY auto-detect
```

Two takeaways:

- Setting `NOVETEST_OUTPUT=json` in the agent's environment is enough.
  You do NOT need to also pass `--output json` on every call.
- If you need a specific verb to override the env (rare), pass
  `--output json` on that invocation. The flag wins.

---

## 5. Verifying a clean install in your agent

A minimal three-step probe:

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

If all three pass, you can drive Nove Test.

---

## What the install script does internally (for reference)

1. Detects OS + arch.
2. Resolves the asset name (`novetest-linux-x86_64` / `novetest-linux-aarch64` / `novetest-macos-universal2` / `novetest-windows-x86_64.exe`).
3. Downloads the binary and its `.sha256` sidecar from the latest GitHub Release (or pinned version via `NOVETEST_INSTALL_VERSION`).
4. Verifies SHA-256 locally. Mismatch → aborts.
5. Atomic rename into `~/.local/bin/novetest{.exe}`.
6. Checks PATH; prints hint if needed.

No network calls happen at CLI invocation time. The first `novetest`
invocation pays a one-time 5–25 second cost (PyApp self-extracts the
bundled Python); subsequent invocations are warm.

---

## Next

[quick-start.md](./quick-start.md) — the 4-step canonical workflow,
every step pinned to its envelope shape.
