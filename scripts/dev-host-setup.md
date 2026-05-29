# Dev host setup — reproducible Native engine toolchain

Canonical record of how to equip a developer host so that **every
`tests/integration/run/test_<engine>_*.py` case runs rather than skips**.
This is the operational counterpart of
`agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
("polyglot host parity"): when a host is set up per this file, the
host qualifies as a Manual Test E2E box for all six adapters.

**Why this file exists.** The project's dev environment moves between
multiple desktops (per CEO's 2026-05-29 closing note). Without a single
checked-in record, each host re-discovery costs time and drifts. Each
section below is a re-executable recipe verified on a clean host.

**Scope.** Only what `novetest` itself needs to run its test gate + the
native test engines used by the adapter suite. NOT user-application
deps (those live in each fixture / SuT project's own manifest).

**Verification convention.** Each section ends with a "Verify" block.
Run it in a fresh shell after install — every command MUST succeed
and print a sensible version string. If any fails, the toolchain is
not yet operational and the adjacent integration tests will still
skip.

**Maintenance protocol.** PM owns this file. Each new Native engine
adapter task brief MUST add a section here at handoff time. Each
floor-version bump in
`agent-comms/decisions/2026-05-25-supported-engine-matrix.md`
MUST be mirrored here in the same commit.

---

## Target platform support

| OS | Status | Notes |
|---|---|---|
| Linux (Ubuntu 22.04+ / WSL2 Ubuntu) | ✅ supported | primary dev target |
| macOS (12+, Apple Silicon or Intel) | ✅ supported | install commands provided where they differ |
| Windows native (non-WSL) | ⚠️ untested | dev workflow assumes WSL2; CI matrix covers Windows runners |

WSL2 callout: on Windows hosts, install everything **inside** the
WSL2 Linux distribution, NOT in Windows itself. The `shutil.which()`
guards check Linux `PATH`; Windows-side binaries (e.g. Windows
Node.js visible as `/mnt/c/Program Files/nodejs/`) do not satisfy
them and will leave integration tests skipping.

---

## 1. Python + uv (always required)

**Floor:** Python 3.11 per `pyproject.toml requires-python`.
Tested ceiling: 3.13.

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md` row "Python".

### Linux / WSL2

```sh
# Python 3.11 via system package manager
sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip

# uv (https://docs.astral.sh/uv/) — manages our venv + dev deps
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL   # reload PATH so ~/.local/bin/uv is visible
```

### macOS

```sh
# Python 3.11 via Homebrew
brew install python@3.11

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL
```

### After install

```sh
cd <repo-root>
uv sync                  # installs runtime + dev deps into .venv/
uv run pytest -q tests/unit tests/integration   # gate green = setup OK
uv run mypy              # strict-clean = setup OK
```

### Verify

```sh
uv --version             # uv 0.4+ or newer
uv run python --version  # Python 3.11.x or newer
uv run pytest --version  # pytest 8.x
```

---

## 2. Node.js + npm + npx (for jest adapter)

**Floor:** Node 18 LTS per matrix row "Node.js".
Tested ceiling: 22 LTS.

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md` row "Node.js".

**Why:** the jest adapter's integration tests probe a real `npx jest`
invocation. They skip via `shutil.which("node") is None or
shutil.which("npx") is None`.

### Linux / WSL2 (recommended: nvm)

```sh
# nvm install
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
exec $SHELL              # reload PATH

# Node 22 LTS
nvm install --lts
nvm use --lts
nvm alias default lts/*
```

### macOS

```sh
# Same nvm path works; OR Homebrew
brew install node@22
brew link --force --overwrite node@22
```

### Project-side (NOT this repo — for the jest SuT fixtures)

The jest fixtures under `tests/fixtures/projects/jest-*` carry their
own `package.json`. No global jest install needed — `npx jest` resolves
from each fixture's local `node_modules/`. Just ensure each fixture
runs `npm install` (the integration test does this in its setup; if
you ever run a fixture manually, do `cd <fixture> && npm install`
first).

### Verify

```sh
node --version           # v18.x.x or higher
npm --version            # 9.x or higher
npx --version            # ships with npm
```

---

## 3. Go toolchain (for go-test adapter)

**Floor:** Go 1.21 per matrix row "go (toolchain)".
Tested ceiling: TBD (pending CI Go cell).

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md` row "go (toolchain)".

**Why:** the go-test adapter's integration tests probe a real
`go test -json` invocation. They skip via `shutil.which("go") is None`.

### Linux / WSL2

```sh
# Pick a version >= 1.21. Replace go1.22.3 with the current stable release.
GO_VERSION=1.22.3
wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz
rm go${GO_VERSION}.linux-amd64.tar.gz

# Persist on PATH (add to ~/.profile or ~/.bashrc)
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.profile
source ~/.profile
```

### macOS

```sh
brew install go@1.22       # or `brew install go` for current stable
```

### Pin behavior

The Go fixture's `go.mod` declares `go 1.21`. Setting `GOTOOLCHAIN=local`
prevents `go test` from auto-fetching a newer toolchain when the
installed version is older than the fixture's `go` directive (per
the matrix decision's go row note). Recommended:

```sh
echo 'export GOTOOLCHAIN=local' >> ~/.profile
source ~/.profile
```

### Verify

```sh
go version               # go1.21.x or newer
echo $GOTOOLCHAIN        # local
```

---

## 4. Rust toolchain (for cargo nextest adapter)

**Floor:** cargo 1.74 + cargo-nextest 0.9.50 per matrix rows added
2026-05-29.

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md`
rows "cargo (Rust toolchain)" / "cargo-nextest" /
"llvm-tools-preview"; pinned by
`decisions/2026-05-29-cargo-adapter-nextest-primary.md`.

**Why:** the cargo adapter's integration tests probe a real
`cargo nextest run` (and `cargo llvm-cov nextest`) invocation. They
skip via `shutil.which("cargo") is None or shutil.which("cargo-nextest")
is None` (basic) and additionally `shutil.which("cargo-llvm-cov") is
None` (coverage). **Equipping this section is the canonical
fulfillment of polyglot-host-parity trigger (b)** per
`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3.

### Linux / WSL2 + macOS (same path via rustup)

```sh
# rustup — official Rust installer
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
. "$HOME/.cargo/env"          # one-time PATH load; rustup installer also patches ~/.profile

# cargo-nextest (libtest-json compatible runner)
cargo install cargo-nextest --locked

# cargo-llvm-cov (LCOV coverage producer)
cargo install cargo-llvm-cov

# The rustup component required by cargo-llvm-cov
rustup component add llvm-tools-preview
```

### After install

When this section is freshly applied for the first time on a host, run
the cargo Manual Test E2E sweep that was deferred at the
2026-05-29 cycle close (Steps 2-5 of the deleted verification doc —
reconstruct from
`history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md`
§"Verification-doc drift" and the
`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` Context
section). This closes the cargo E2E gap.

### Verify

```sh
cargo --version          # cargo 1.74 or newer
cargo nextest --version  # 0.9.50 or newer
cargo llvm-cov --version # any
rustup component list --installed | grep llvm-tools-preview
```

---

## 5. Java (JDK) — placeholder, JUnit adapter pending

**Floor:** TBD (set when the JUnit adapter task brief is written).
Likely JDK 17+ (LTS).

**Status:** the JUnit adapter is blocked on
`delivery-phasing.md` Open Question #4. This section will be filled in
with concrete `apt-get` / `brew` commands when the adapter lands.
Until then, no Java is required for the test gate.

When this section is finalized, add:
- JDK install commands (`apt-get install openjdk-17-jdk` /
  `brew install openjdk@17`).
- Maven or Gradle install (depending on Q#4 resolution).
- A floor row to the supported-engine-matrix decision.

---

## 6. .NET SDK — placeholder, dotnet adapter pending

**Floor:** TBD (set when the dotnet adapter task brief is written).
Likely .NET 8 SDK (LTS).

**Status:** the dotnet adapter is blocked on
`delivery-phasing.md` Open Question #5. This section will be filled in
when the adapter lands. Until then, no .NET is required for the test
gate.

When this section is finalized, add:
- Microsoft package install (`apt-get install dotnet-sdk-8.0` /
  `brew install --cask dotnet-sdk`).
- A floor row to the supported-engine-matrix decision.

---

## 7. Smoke after equipping a fresh host

After running every applicable section above (Python is mandatory;
others are per-engine), the project's full integration suite should
run with **fewer skips than before**:

```sh
cd <repo-root>
uv sync
uv run pytest -q tests/unit tests/integration
```

Expected on a fully-equipped host (Python + Node + Go + Rust; JUnit
and dotnet pending):

| Section installed | Expected skip count change |
|---|---|
| Python only | baseline 5 skips |
| + Node (jest fixtures `npm install` done) | -3 skips (3 jest cases run) |
| + Go | -2 skips (2 gotest cases run) |
| + Rust (with cargo-llvm-cov) | -2 skips (2 cargo cases run) |
| All four | **0 skips** (when JUnit + dotnet adapters land, this count grows but should still reach 0 after equipping all six) |

If the skip count does not drop as expected, re-check the relevant
"Verify" block — a `shutil.which()` guard is finding a non-functional
binary (common on WSL when Windows-side `node` leaks into Linux PATH).

---

## 8. Known gotchas (cross-engine)

- **WSL2 PATH leak from Windows.** `which node` may resolve to
  `/mnt/c/Program Files/nodejs/`, which the jest integration tests
  treat as present but which often cannot resolve project fixtures.
  Always install Node *inside* WSL via nvm.
- **Multiple Rust toolchains.** `rustup` defaults to `stable`. If a
  project ever pins a `rust-toolchain.toml`, `rustup` auto-installs
  that channel — disk usage grows. Periodic `rustup toolchain list`
  + `rustup toolchain uninstall <old>` keeps it bounded.
- **`cargo install` is not idempotent across major versions.** Re-running
  `cargo install cargo-nextest --locked` prints "is already installed";
  to upgrade pass `--force`.
- **Go `GOTOOLCHAIN=local` is REQUIRED on dev hosts older than the
  go-test fixture's `go.mod` directive.** Without it, `go test`
  silently downloads a newer toolchain — passes tests but breaks the
  "reproducible install" promise of this file.

---

## Cross-references

- `decisions/2026-05-25-supported-engine-matrix.md` — version floors
  + ceilings for each row.
- `decisions/2026-05-29-cargo-adapter-nextest-primary.md` — cargo /
  nextest / llvm-cov stack rationale.
- `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` —
  polyglot host parity contract; this file is the operational
  fulfillment.
- `agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md`
  — origin of this file's commitment.
- `CLAUDE.md` — project structure, including `tests/integration/`.
