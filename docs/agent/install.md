# Install + First Sanity Checks (Agent)

This page covers:

1. Scripted / CI install for Linux / macOS / Windows, with version pinning.
2. The two sanity envelopes (`version`, `help`) to round-trip before driving any project.
3. Output-mode env vars and the precedence rule.
4. A copy-paste pre-flight probe.

Nove Test ships as a self-contained PyApp binary (embeds CPython 3.11 + the
`novetest` wheel) — the install host needs no Python toolchain. Current
version: **0.3.0**.

---

## 1. Scripted install

### Linux + macOS

```bash
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
```

The script is idempotent (re-running upgrades in place via atomic rename),
sudo-free (`~/.local/bin/`), and **aborts loudly on a SHA-256 mismatch** —
you can rely on it never writing a non-verified binary to disk.

After it finishes, the binary lives at:

| OS | Path |
|---|---|
| Linux | `~/.local/bin/novetest` |
| macOS | `~/.local/bin/novetest` |
| Windows | `%USERPROFILE%\.local\bin\novetest.exe` |

If the install prefix is not on `PATH`, the script prints a hint and exits
0. Your wrapper should pre-set `PATH` or append the hint line to the host's
shell profile.

### Pin the version for reproducible CI

```bash
NOVETEST_INSTALL_VERSION=v0.1.2 \
  curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

Install-script env vars (script-only; they do not affect the CLI at runtime):

| Variable | Default | Effect |
|---|---|---|
| `NOVETEST_INSTALL_VERSION` | `latest` | Pin to a release tag for deterministic installs. |
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Install location. |
| `NOVETEST_INSTALL_REPO` | `Nove-Lab/Nove-Test` | GitHub `owner/repo`. |
| `NOVETEST_INSTALL_BASE_URL` | (GitHub Releases) | Override the download base URL (mirrors, internal caches). |

### Scriptless install (direct asset fetch + verify)

For hermetic CI that mirrors release assets, fetch the binary and its
sidecar yourself and gate on the SHA-256:

```bash
base=https://github.com/Nove-Lab/Nove-Test/releases/latest/download
target=novetest-linux-x86_64   # linux-aarch64 | macos-universal2 | windows-x86_64
curl -fsSLO "$base/$target"
curl -fsSLO "$base/$target.sha256"
sha256sum -c "$target.sha256" || { echo "checksum mismatch"; exit 1; }
chmod +x "$target" && mv "$target" ~/.local/bin/novetest
```

Targets: `novetest-linux-x86_64`, `novetest-linux-aarch64`,
`novetest-macos-universal2`, `novetest-windows-x86_64` (`.exe`). No Linux
i686/armv7l, no Windows arm64.

### Python-tooling path (secondary)

If the host already has Python **>= 3.11** and manages CLIs with `uv` or
`pipx`: `uv tool install novetest` or `pipx install novetest`. The binary
install is the primary path; treat this as a convenience fallback.

---

## 2. Sanity check #1 — `novetest --version`

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
    "installedVersion": "0.3.0",
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

Note the top-level envelope keys are exactly `{schema, command, ok, data,
errors, warnings}` (emitted sorted). There is **no** top-level `version`,
`verb`, or `exit_code` field.

| Field | Type | Meaning |
|---|---|---|
| `installedVersion` | string (semver) | CLI version. Gate version-dependent behavior on this. |
| `commandName` | string | Always `"novetest"`. Confirm you are looking at the right CLI. |
| `installLocation` | string (path) | Binary/interpreter path on disk (above shows a source checkout's interpreter; a binary install shows the installed `novetest`). |
| `pythonVersion` | string (semver) | Bundled CPython; you do not install Python yourself. |
| `platform` | string | `{system}-{machine}`, lowercased. Route platform assumptions on this. |
| `verifiedAt` | string (ISO-8601 UTC) | Time the `--version` envelope was generated (per-invocation — **not** a build time; it changes every call); `Z` suffix is canonical. |

Exit code: **0**. There is no other expected exit code for `--version`.

---

## 3. Sanity check #2 — `novetest --help`

```bash
NOVETEST_OUTPUT=json novetest --help
```

Emits the **command surface envelope** — a machine-readable self-description
of every verb. This is the canonical way for an agent to discover verbs
without grepping docs. Real output (`data.operating` truncated for length —
the elided items are real, not invented):

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

Two arrays under `data`:

- `onboarding[]` — `--version`, `--help`, `init`, `reset`.
- `operating[]` — the 15 work verbs (`test`, `run`, `memory list/show/delete`, `inspect`, `status`, `coverage show/diff`, `regression compare/latest`, `compare`, `localization`, `replay`, `licenses`).

Each item carries `name`, `summary`, `group`, and `availableInPhase`. The
pair `(group, name)` is stable; rely on it for dispatch. `data.schemaVersion`
is `1`.

Exit code: **0**.

### Why an agent should call `--help` at startup

The verb list is data, not documentation. Discover verbs from
`data.operating[*].name` instead of hard-coding them, so a future release
that adds a verb does not require a code change in your agent. Do **not**
gate on `availableInPhase` — it is informational, not a capability flag.

---

## 4. Output-mode env vars

| Variable | Default | Effect |
|---|---|---|
| `NOVETEST_OUTPUT` | auto (`text` on TTY, `json` when piped) | Force the output mode. **Set to `json` once at session start.** |

Precedence:

```
explicit --output flag  >  NOVETEST_OUTPUT env  >  TTY auto-detect
```

(`--output` is a global flag; it is stripped from anywhere in the argv
before dispatch, so it works in any position — `novetest --output json
status` and `novetest status --output json` are equivalent. Values:
`text` / `json` / `ndjson`. JSON is pretty-printed with sorted keys; NDJSON
is one compact envelope per line.) Setting `NOVETEST_OUTPUT=json` in the
agent's environment is enough — you do not need `--output json` on every
call. The install-script env vars in §1 are separate and do not affect
runtime output.

---

## 5. Pre-flight probe for a clean install

```bash
# 1) Binary on PATH
command -v novetest || { echo "novetest missing"; exit 1; }

# 2) Version envelope round-trips
NOVETEST_OUTPUT=json novetest --version \
  | jq -e '.ok == true and .schema == "novetest/v1"
           and (.data.installedVersion | type == "string" and length > 0)' \
  || { echo "version envelope malformed"; exit 1; }

# 3) Help envelope enumerates the operating surface
NOVETEST_OUTPUT=json novetest --help | jq -e '.data.operating | length >= 15' \
  || { echo "help envelope shrunk unexpectedly"; exit 1; }
```

If all three pass, you can drive Nove Test. The first real invocation pays a
one-time 5–15 second PyApp unpack cost; subsequent calls are warm.

Step 2 asserts the envelope round-trips rather than pinning a version number,
so the probe stays green across upgrades. Compare `.data.installedVersion`
against a literal only in a job that also pins `NOVETEST_INSTALL_VERSION` (§1)
— otherwise the assertion fails on the next release rather than on a real
defect.

---

## Next

[quick-start.md](./quick-start.md) — the 4-step canonical workflow, every
step pinned to its envelope shape.
