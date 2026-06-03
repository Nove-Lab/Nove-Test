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
rustup component list --installed | grep llvm-tools
```

The `add` command accepts the historical alias `llvm-tools-preview`,
but `rustup component list --installed` reports the component as
`llvm-tools-<host-triple>` (e.g. `llvm-tools-x86_64-unknown-linux-gnu`)
— the `-preview` suffix was dropped upstream. Grep the unsuffixed
prefix `llvm-tools` so the check survives both naming forms.

Refined 2026-05-30 on first trigger-(b) firing (Linux/WSL2 host).
Observed install versions: cargo 1.96.0, cargo-nextest 0.9.137,
cargo-llvm-cov 0.8.7. Floors held with comfortable headroom; no
floor bump warranted at this firing.

---

## 5. Java (JDK + Maven) — for JUnit 5 adapter

**Floor:** JDK 17 (LTS) + Maven 3.9 (or Gradle 7.6) per matrix rows added
2026-06-03.

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md` rows
"JDK" / "Maven (Surefire) OR Gradle (`useJUnitPlatform()`)"; pinned by
`decisions/2026-06-03-junit-console-launcher-vendor.md`.

**Why:** the JUnit adapter's integration tests probe a real `mvn -B test`
(or `./gradlew test --no-daemon`) invocation. They skip via
`shutil.which("java") is None or (shutil.which("mvn") is None and
shutil.which("gradle") is None)`. The JUnit Platform Console Launcher
itself is **vendored** inside our distribution at
`src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
— the user does NOT install it. Only the JDK + build tool are required.

### Linux / WSL2

```sh
# JDK 17 (LTS) — Adoptium Temurin via apt
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk maven

# Optional alternative: Gradle (use one or the other; both is fine)
sudo apt-get install -y gradle
```

### macOS

```sh
brew install openjdk@17 maven

# Symlink the JDK so /usr/libexec/java_home finds it
sudo ln -sfn $(brew --prefix)/opt/openjdk@17/libexec/openjdk.jdk \
  /Library/Java/JavaVirtualMachines/openjdk-17.jdk

# Optional alternative: Gradle
brew install gradle
```

### Smoke probe

After install, validate that the bundled Console Launcher extracts and
runs cleanly (this is the load-bearing check that PyApp binary blob
extraction works on the host):

```sh
# From a clean tmp directory
cd /tmp && mvn archetype:generate -B \
  -DgroupId=test -DartifactId=junit-smoke \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DarchetypeVersion=1.4 -DinteractiveMode=false
cd junit-smoke && mvn -B test
```

The archetype generates a project with JUnit 4; for JUnit 5 you must edit
the generated `pom.xml` to depend on `junit-jupiter` and add
`maven-surefire-plugin` 3.0+. Detailed migration steps live in the JUnit
adapter task brief at handoff time.

### Verify

```sh
java -version            # openjdk version "17" or newer
mvn -version             # Apache Maven 3.9.x or newer (or gradle -version)
```

### Per-floor-bump maintenance

If JUnit 5.12 ships and we move the JUnit Platform floor to 1.12, mirror
that bump here AND in `decisions/2026-05-25-supported-engine-matrix.md` in
the same commit (per the maintenance protocol at the top of this file).



---

## 6. .NET SDK + Coverlet — for `dotnet test` adapter

**Floor:** .NET SDK 8.0 (LTS) + `coverlet.collector` 6.0.2 per matrix rows
added 2026-06-03.

**Floor source:** `decisions/2026-05-25-supported-engine-matrix.md` rows
".NET SDK" / "coverlet.collector"; pinned by
`decisions/2026-06-03-coverlet-pertestcoverage-key.md`.

**Why:** the .NET adapter's integration tests probe a real `dotnet test`
invocation against an xUnit v2 project. They skip via `shutil.which("dotnet")
is None`. The Coverlet 6.0.2+ floor is enforced at adapter runtime via
`dotnet list <project> package --include-transitive` parsing; if the user's
project resolves a lower version, the adapter degrades to aggregate
coverage with an `engine-misconfigured` warning.

xUnit v3 / Microsoft.Testing.Platform coverage is **deferred from MVP** —
the adapter detects v3 and emits `xunit-v3-coverage-deferred` warning,
running tests without coverage collection.

### Linux / WSL2

```sh
# Microsoft package feed for Ubuntu 22.04 (adjust for other distros)
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O /tmp/ms.deb
sudo dpkg -i /tmp/ms.deb && rm /tmp/ms.deb
sudo apt-get update
sudo apt-get install -y dotnet-sdk-8.0
```

### macOS

```sh
brew install --cask dotnet-sdk          # latest stable (currently .NET 8)
```

### Smoke probe (validates Coverlet floor)

After install, validate that `coverlet.collector >= 6.0.2` is resolvable
from NuGet and that `dotnet test` emits per-test Cobertura under the
expected glob:

```sh
cd /tmp
dotnet new xunit -n dotnet-smoke -o dotnet-smoke && cd dotnet-smoke
dotnet add package coverlet.collector --version 6.0.2

# Generate a probe runsettings (mirrors what the adapter will generate)
cat > coverlet.runsettings <<RUNSETTINGS
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat code coverage">
        <Configuration>
          <Format>cobertura</Format>
          <PerTestCoverage>true</PerTestCoverage>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
RUNSETTINGS

dotnet test --collect:"XPlat Code Coverage" --settings coverlet.runsettings \
  --results-directory ./TestResults

# Expect per-test files (NOT a single coverage.cobertura.xml):
ls TestResults/**/coverage.*.cobertura.xml
```

If the `ls` returns the per-test glob, the host is correctly equipped for
the .NET adapter's per-test mode. If only `coverage.cobertura.xml` (no
slug) appears, the user's resolved Coverlet version is below 6.0.2 or the
runsettings was not picked up — re-check both.

### Verify

```sh
dotnet --version         # 8.0.x or newer
dotnet --list-sdks       # 8.0.x present
```

### Per-floor-bump maintenance

If Coverlet 7.x ships with a stable `PerTestCoverage` form, mirror the
ceiling bump here AND in `decisions/2026-05-25-supported-engine-matrix.md`
in the same commit. The xUnit v3 / MTP coverage deferred decision reopens
when a separate v3 coverage adapter slice is scoped.



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
| + Java (JDK + Maven) | -N skips (count established at JUnit adapter cycle) |
| + .NET (SDK + Coverlet) | -N skips (count established at .NET adapter cycle) |
| All six | **0 skips** target |

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
