# Install + First Sanity Checks

This page covers the single-command install, the directory the
binary lands in, the two sanity checks an AI agent should run
immediately, and the literal envelope shapes those checks return.

---

## 1. The install command (Linux + macOS)

```bash
curl -fsSL https://ailovestesting.com/novetest/install.sh | sh
```

That is the one command you run. It is idempotent (re-running
upgrades in place via POSIX `rename(2)`), it is sudo-free (it
writes to `~/.local/bin`, never `/usr/local/bin`), and it aborts
loudly on a SHA-256 mismatch rather than writing a partial binary.

### What the script does, step by step

1. Detects OS + arch via `uname`. Supports:
   - `Linux` × `x86_64` → asset `novetest-linux-x86_64`
   - `Linux` × `aarch64`/`arm64` → asset `novetest-linux-aarch64`
   - `Darwin` × any arch → asset `novetest-macos-universal2`
     (single fat binary, the right Mach-O slice is picked at
     `exec` time)
   - Anything else: exits non-zero with a clear message.
     Windows is the only intentional gap; an `install.ps1` ships
     post-MVP.
2. Downloads the binary AND its `.sha256` sidecar from the
   resolved URL (default: the public hosting URL above; release
   testing can override via env vars — see §5).
3. Computes the binary's SHA-256 locally using whichever of
   `sha256sum`, `shasum -a 256`, or `openssl dgst -sha256` is
   available.
4. Compares to the sidecar. **Mismatch → loud abort**; nothing
   is written under `~/.local/bin`.
5. Atomically stages the binary as `~/.local/bin/novetest.tmp`,
   `chmod 0755`s it, then `mv`s to `~/.local/bin/novetest`. On
   the same filesystem this is a single `rename(2)` syscall, so
   concurrent readers either see the old binary or the new one,
   never a partial.
6. Tests whether `~/.local/bin` is already on your `PATH`. If
   not, the script prints a one-line hint asking you to add it
   to your shell profile.
7. Prints a final "Run `novetest --version` to verify."

### Where the binary lives

By default: **`~/.local/bin/novetest`**.

That follows the XDG convention and is on PATH by default on
most modern Linux distros and on macOS via Homebrew profiles.
Override with `NOVETEST_INSTALL_PREFIX=...` (see §5) if you
need it elsewhere.

### If `~/.local/bin` is not on your PATH

Add this to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then `source` the profile or open a new shell and re-check with
`novetest --version`.

---

## 2. Sanity check #1 — `novetest --version`

```bash
novetest --version
```

`--version` and `-v` are identical. The CLI emits the standard
`novetest/v1` envelope; on a TTY you see the human-readable form,
when piped (or under `NOVETEST_OUTPUT=json`) you see the JSON:

```json
{
  "schema": "novetest/v1",
  "command": "version",
  "ok": true,
  "data": {
    "installedVersion": "0.1.0",
    "commandName": "novetest",
    "installLocation": "/home/you/.local/bin/novetest",
    "pythonVersion": "3.11.5",
    "platform": "linux-x86_64",
    "verifiedAt": "2026-06-09T14:22:33Z"
  },
  "errors": [],
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `installedVersion` | The semver of the bundled `novetest` package. At MVP this is `"0.0.0"` for development builds; published releases will carry their tag (`"0.1.0"`, etc.). |
| `commandName` | Always `"novetest"`. Pin against this if you want to verify you are looking at the right CLI. |
| `installLocation` | The Python interpreter PyApp resolved for itself. NOT the path of your binary on disk — that is `which novetest`. |
| `pythonVersion` | The bundled CPython. You do not need to install Python yourself; the binary brings its own. |
| `platform` | `{system}-{machine}`, lowercased. Useful for routing platform-specific assumptions. |
| `verifiedAt` | UTC ISO 8601 (`Z` suffix), captured at envelope-build time. |

Exit code: **0** if the envelope rendered. There is no other
expected exit code for `--version`.

---

## 3. Sanity check #2 — `novetest --help`

```bash
novetest --help
```

`--help` / `-h` (or simply running `novetest` with no args) emits
the **command surface envelope** — a machine-readable
self-description of every verb the CLI exposes, grouped by
intent and labelled with the implementation phase it landed in.
This is the canonical way for an AI agent to discover what verbs
exist without grepping documentation.

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
        "name": "novetest status",
        "summary": "Summarize the latest run and which sub-reports are available.",
        "group": "memory",
        "availableInPhase": 1
      },
      {
        "name": "novetest inspect",
        "summary": "Aggregate run summary plus all derived facts for a single run.",
        "group": "memory",
        "availableInPhase": 1
      }
      // ... (more verbs, including coverage.*, regression.*, localization.*, replay, compare, memory.*)
    ]
  },
  "errors": [],
  "warnings": []
}
```

Two arrays:

- `data.onboarding[]` — verbs you typically run **once** to come
  online. `--version`, `--help`, `init`.
- `data.operating[]` — verbs you run during normal use.

Each item carries `name`, `summary`, `group`, and
`availableInPhase`. `availableInPhase` lets you reason about
maturity: at MVP, every operating verb has landed (phases 0–6 are
all `[x]`). The pair `(group, name)` is stable; rely on it for
programmatic dispatch.

Exit code: **0** for a successful help render.

---

## 4. After install + sanity, you are ready

At this point:

- `which novetest` resolves to `~/.local/bin/novetest`.
- `novetest --version` round-trips a valid envelope.
- `novetest --help` enumerates the verb tree.

Next: head to [quick-start.md](./quick-start.md) for the
canonical happy path. If your project is not Python, glance at
[languages.md](./languages.md) for the one-line setup difference
your engine needs before you `novetest init`.

---

## 5. Environment overrides (advanced)

You almost never need these for the happy path. They exist
mainly for release testing, mirror operators, and CI pinning.

| Variable | Default | What it does |
|---|---|---|
| `NOVETEST_INSTALL_PREFIX` | `~/.local/bin` | Where the binary is placed. |
| `NOVETEST_INSTALL_VERSION` | `latest` | A tag like `v0.1.0` to pin to. |
| `NOVETEST_INSTALL_REPO` | `nove/novetest` | GitHub `owner/repo` for URL composition. |
| `NOVETEST_INSTALL_BASE_URL` | (derived) | Full base URL override. Used by the integration tests that serve fixtures on `localhost`. |
| `NOVETEST_OUTPUT` | (auto: text on TTY, json when piped) | Force `json` / `text` / `ndjson` envelope rendering. |

---

## 6. Re-install and uninstall

- **Re-install / upgrade**: re-run the same `curl | sh`. It
  always overwrites with the downloaded binary via atomic rename.
- **Uninstall**: `rm ~/.local/bin/novetest`. The CLI keeps no
  state outside of per-project `.novetest/` directories (see
  [quick-start.md §2](./quick-start.md)). Removing the binary
  removes the CLI entirely.

---

## 7. Caveats pinned by the MVP

- **Windows install** is not in scope for MVP. The binary itself
  is built but `install.ps1` is post-MVP work. If you are on
  Windows and have the binary on PATH some other way, the CLI
  still works.
- **macOS `arm64`** uses the `universal2` fat binary, picked
  automatically at exec time.
- **Linux `i686` / `armv7l`** are not in scope. Linux ships
  `x86_64` and `aarch64`/`arm64` only.
- **First-run cold start** is on the order of 5–15 seconds (the
  PyApp self-extracting bundle expands its bundled Python on
  first invocation; subsequent invocations are warm and fast).
  This is a one-time cost per binary version per user.
