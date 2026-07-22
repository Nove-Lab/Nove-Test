# Per-Language Notes (Human)

The canonical happy path in [quick-start.md](./quick-start.md) is
language-agnostic — same `init` → `test` flow, same text-mode output
shape. This page documents only **what differs** per language: the
toolchain you need on PATH, the detection marker, the external command
the adapter invokes (shown simplified — coverage runs add a few extra
flags), and whether coverage is available.

`novetest init` detects which engine your project uses from workspace
markers and **pins** it into `.novetest/store.json`. From then on every
verb runs the pinned engine — nothing is re-detected at run time. In
the common single-engine project you never pass an `--engine` flag;
it exists for two specific situations (ambiguous roots and one-off
overrides — see below).

## The six supported engines

`novetest` ships six fully-wired native engine adapters. Each is an
`(ecosystem, engine)` pair — the `engine` string is exactly what
appears as `engine_name` in your Run Record:

| Ecosystem | Engine | Marker(s) | Coverage |
|---|---|---|---|
| `python` | `pytest` | `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini` | yes |
| `javascript-typescript` | `jest` | `package.json` | yes |
| `java` | `junit` (JUnit 5 Jupiter **only**) | `pom.xml`, `build.gradle`, `build.gradle.kts` | yes |
| `go` | `go-test` | `go.mod` | **no** (see below) |
| `rust` | `cargo-test` (nextest **required**) | `Cargo.toml` | yes |
| `dotnet` | `xunit` (xUnit v2 **only**) | `*.csproj` (root + 1-level glob), `*.sln` | yes |

Note the exact engine names: `go-test`, `cargo-test`, and `xunit`
(the .NET engine is named `xunit`, not `dotnet`). Java is **JUnit 5
Jupiter only** — JUnit 4 and TestNG are explicitly rejected. .NET is
**xUnit v2 only** — MSTest and NUnit are explicitly rejected. Rust
**requires `cargo-nextest`** — there is no plain `cargo test`
fallback. **`go test` runs, but its coverage is not consumed** — see
the gotest section.

## One `novetest test` call = exactly one engine — the pin

`novetest test` (and every other verb) runs **one engine at a time**:
the one pinned at `init`. How the pin is chosen:

- **Exactly one viable engine** at the init directory → pinned
  silently. This is the common case; nothing changes in your flow.
- **Two or more viable engines** (e.g. `pyproject.toml` AND
  `Cargo.toml` at the same root, both toolchains installed) → `init`
  **refuses** (exit 2, error `engine-ambiguous`), creates nothing, and
  asks you to choose explicitly:

  ```bash
  novetest init --engine pytest      # or cargo-test, jest, …
  ```

  There is no silent priority-win: novetest never guesses which suite
  you meant.
- **"Viable" = marker present AND the toolchain is actually ready.**
  A root with `pyproject.toml` + a tooling-only `package.json` (no
  jest installed) pins pytest without asking. Consequence: the same
  repo can init silently on one machine and demand `--engine` on
  another, depending on which toolchains are installed there.

Three more things the pin gives you:

- **Verbs work from any subdirectory.** Every verb walks **up** from
  where you run it to the nearest `.novetest/` (like git). Running
  `novetest test` from `src/deep/nested/` behaves exactly as from the
  project root — a bare invocation is always workspace-scoped; your
  cwd never silently narrows what runs.
- **One-off override without re-pinning**: `novetest test --engine
  cargo-test` runs that engine once; the pin is untouched. To change
  the pin permanently, re-run `novetest init --engine <name>` — same
  store, run history retained.
- **Old stores upgrade themselves.** A `.novetest/` created before
  pinning existed gets its pin backfilled silently on the next verb
  (or, if the root is ambiguous, you're asked to re-init with
  `--engine`).

### Working with a polyglot repository

The supported pattern is **one `.novetest/` per ecosystem subdirectory**:

```
polyglot-repo/
├── backend/
│   ├── pyproject.toml
│   ├── my_module/
│   ├── tests/
│   └── .novetest/        ← created by `cd backend && novetest init`
└── frontend/
    ├── package.json
    ├── src/
    ├── __tests__/
    └── .novetest/        ← created by `cd frontend && novetest init`
```

Then:

```bash
( cd backend  && novetest test )   # runs pytest only
( cd frontend && novetest test )   # runs jest only
```

Each subdirectory's `.novetest/` carries its own run history, coverage
facts, regression baselines, and SBFL findings — completely isolated.
And because verbs walk up to the nearest `.novetest/`, you can run
`novetest test` from anywhere **inside** `backend/` and it resolves to
`backend/.novetest` automatically.

Running `novetest init` at a markerless root (e.g. the repo root of
the polyglot layout above) creates **nothing**: it exits with
`no-engine-detected` and lists the sub-projects it can see (bounded
scan, depth ≤ 2, refused outright at `/` and `$HOME`) so you know
where to `cd` and init. novetest never initializes a directory you
are not standing in.

## Quick prerequisites overview

| Engine | What must be on PATH | Coverage tool |
|---|---|---|
| pytest | the `pytest` + `pytest-json-report` plugin importable from novetest's own interpreter | `pytest-cov` |
| jest | Node.js ≥ 18 (`node` **and** `npx`) + jest installed in the project | jest built-in (Istanbul) |
| go-test | Go ≥ 1.21 (`go`) | — (coverage not consumed) |
| cargo-test | Rust toolchain + `cargo-nextest` ≥ 0.9.50 (mandatory) + `cargo-llvm-cov` (for coverage) | `cargo-llvm-cov` (LCOV) |
| junit | JDK ≥ 17 + Maven ≥ 3.9 OR Gradle ≥ 7.6/wrapper; JUnit 5 Jupiter in deps | JaCoCo |
| xunit | .NET SDK ≥ 8.0; xUnit v2 in test project | `coverlet.collector` ≥ 6.0.2 |

---

## pytest (Python)

This is the **baseline** used in [quick-start.md](./quick-start.md);
treat that page as the canonical pytest walkthrough.

### Project skeleton

```
calc-demo/
├── pyproject.toml          # [tool.pytest.ini_options] testpaths=["tests"]
├── calc/
│   ├── __init__.py
│   └── arithmetic.py
└── tests/
    └── test_arithmetic.py
```

Markers `novetest` looks for: `pyproject.toml`, `setup.py`,
`setup.cfg`, `pytest.ini`. Readiness **additionally** requires a
pytest configuration to exist — one of `pytest.ini`, `conftest.py`, a
`tests/` directory, `[tool.pytest.ini_options]` in `pyproject.toml`,
or `[tool:pytest]` in `setup.cfg`. A Python workspace with none of
these reports `engine-missing`.

### Toolchain

`pytest` and the `pytest-json-report` plugin (plus `pytest-cov` for
coverage runs) must be importable from the **interpreter novetest
resolves for your project**, which is chosen venv-first:

1. **`<project>/.venv`** — used when its pytest console script exists
   (`.venv/bin/pytest`, or `.venv\Scripts\pytest.exe` on Windows).
   novetest then runs that venv's `python`, so your project's own pytest
   and plugin versions are what execute.
2. **novetest's own interpreter** (`sys.executable`) — the fallback when
   the project has no such `.venv`.

A `pytest` merely on `PATH` is never used. Readiness checks the same
interpreter it will run, and the reported `engine_version` is that
interpreter's pytest version.

**If you installed novetest as the standalone binary** (`curl … | sh`),
its interpreter is a sealed CPython you cannot install into — give your
project a `.venv` with the test dependencies:

```
cd <project>
python3 -m venv .venv
.venv/bin/python -m pip install pytest pytest-json-report pytest-cov
```

`pytest-cov` is not required for readiness to report `ready`, but
`novetest test` collects coverage by default — without it that run stops
with `adapter-missing-plugin` (exit 4). Installing all three up front is
why the readiness hint lists them together.

With a pip/venv, pipx, or `uv tool` install of novetest you may instead
put these in novetest's own environment; the project `.venv` route works
in every install mode.

### External command

```
<resolved python> -m pytest -p pytest_jsonreport --json-report
  --json-report-file=<artifacts>/native/pytest-report.json -q [<target>]
```

Plugin autoload is disabled (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`) so
the venv's other plugins do not leak; the json-report (and, on
coverage runs, `pytest-cov`) plugins are loaded explicitly via `-p`.

### Per-test identity & coverage

Node-id form: `tests/test_arithmetic.py::test_subtract`. Coverage is
JSON via `pytest-cov`, collected with `--cov-context=test` so per-test
coverage facts are available (this is what enables SBFL per-test mode).

### Real output

```
✓ Initialized .novetest/ at /abs/path/to/calc-demo/.novetest
  engine readiness: ready — python/pytest 9.0.3
```

(The pytest version shown is *your* project's pytest, not a
novetest-controlled constant. novetest's own version is `0.1.2`.)

---

## jest (JavaScript / TypeScript)

### Project skeleton

```
my-js-project/
├── package.json
├── src/
│   └── math.js
└── __tests__/
    └── math.test.js
```

Marker: `package.json`. Readiness requires that jest is declared in
`dependencies`/`devDependencies` **or** installed at
`node_modules/.bin/jest`.

### Toolchain

Node.js ≥ 18 — **both** `node` and `npx` must be on PATH — plus a
workspace-local jest install. If `node`/`npx` are missing readiness is
`engine-missing`; if jest is absent it is `engine-misconfigured`.

### External command

```
npx jest --ci --json --testLocationInResults
  --outputFile=<artifacts>/native/jest-results.json
  --reporters=default --watchman=false [<target>]
```

On Windows the launcher is `cmd /c npx …`. Unlike pytest, jest has no
plugin-autoload isolation — your workspace `jest.config.js` is honored
as written.

### Per-test identity & coverage

Node-id form: `<file>::<ancestors>::<title>`. Coverage is Istanbul
JSON (`--coverage --coverageReporters=json`).

---

## gotest (Go / `go test`)

### Project skeleton

```
my-go-module/
├── go.mod
├── math.go
└── math_test.go
```

Marker: `go.mod`. Default target is `./...` (every package in the
module). Readiness needs `go` on PATH and a working `go version`.

### Toolchain

Go ≥ 1.21 (`go` on PATH). Nothing else.

### External command

```
go test -json -count=1 -timeout=<seconds>s [coverage flags] <target>
```

`-count=1` disables Go's result cache so a stale pass is never
returned.

### Coverage is NOT consumed

This is the one real gap. `go test` *runs* fine, but **`novetest run
--coverage` on a Go project produces no coverage facts**. The adapter
writes a Go `cover.out` profile, but the coverage engine reads a
different artifact key, so the run reports coverage as unavailable
("this run was executed without coverage collection"). Test execution
works; coverage facts do not. Node-id form: `<package>::<test>`.

---

## cargo (Rust / `cargo nextest`)

### Project skeleton

```
my-rust-crate/
├── Cargo.toml
├── src/
│   └── lib.rs
└── tests/
    └── integration_test.rs
```

Marker: `Cargo.toml`. The default target is the workspace.

### Toolchain

```bash
# Install rustup from https://rustup.rs
rustup install stable
cargo install cargo-nextest --locked    # MANDATORY — no fallback
cargo install cargo-llvm-cov            # required for coverage
```

The adapter **requires** `cargo nextest` — a successful
`cargo nextest --version` is a load-bearing readiness gate. Missing
nextest → `engine-misconfigured`. There is **no** fallback to plain
`cargo test`. Coverage additionally needs `cargo-llvm-cov`.

### External command

Non-coverage and coverage runs use **different, mutually-exclusive**
invocations:

```
# non-coverage:
cargo nextest run --message-format=libtest-json --no-fail-fast --workspace [<filter>]
# coverage:
cargo llvm-cov nextest --lcov --output-path <artifacts>/native/coverage.lcov
  --ignore-run-fail --workspace --message-format=libtest-json
```

`--ignore-run-fail` is load-bearing on coverage runs: it emits the
LCOV even when tests fail. A *directory* target (`novetest test .`)
does NOT append `.` as a filter, because nextest treats positionals as
filter expressions, not paths.

### Per-test identity & coverage

Node-id is nextest's test name directly. Coverage is LCOV via
`cargo llvm-cov`.

---

## junit (Java / JUnit 5 Jupiter)

JUnit 5 Jupiter is the **only** supported framework. **JUnit 4 and
TestNG are detected and rejected** as `engine-misconfigured`. Windows
hosts are not supported for JUnit (rejected as `engine-misconfigured`).

### Project skeleton (Maven)

```
my-java-project/
├── pom.xml
└── src/
    ├── main/java/com/example/Math.java
    └── test/java/com/example/MathTest.java
```

`pom.xml` must declare `org.junit.jupiter:junit-jupiter` (test scope).

### Project skeleton (Gradle)

```
my-gradle-project/
├── build.gradle
└── src/
    ├── main/java/com/example/Math.java
    └── test/java/com/example/MathTest.java
```

`build.gradle` must declare `org.junit.jupiter:junit-jupiter` and use
`useJUnitPlatform()`.

Markers: `pom.xml` (→ Maven) or `build.gradle{,.kts}` (→ Gradle). When
**both** are present, Maven wins and an `ambiguous-build-tool` warning
is emitted in `envelope.warnings[]`.

### Toolchain

- JDK ≥ 17 (`java` on PATH; missing → "`java` not found on PATH;
  install JDK 17+")
- Maven ≥ 3.9 (`mvn`) **or** Gradle ≥ 7.6 (`gradle` on PATH, or the
  `./gradlew` wrapper in the workspace)

### External command

```
# Maven:
mvn -B test [jacoco:report] -Dsurefire.reportFormat=plain
  -Dsurefire.useFile=false [-Dtest=<filter>]
# Gradle:
./gradlew test --no-daemon [--tests <filter>] [jacocoTestReport]
```

### Coverage & quirks

Coverage is JaCoCo XML. If you request `--coverage` but JaCoCo is not
wired in, a `missing-jacoco` warning is emitted and coverage degrades.
Note: on the **Gradle** path the reported `engine_version` is often
`null` (the Jupiter-version regex frequently can't extract it); Maven
reports it fine (e.g. `5.10.2`).

---

## xunit (.NET / xUnit v2)

xUnit v2 is the **only** supported framework. **MSTest and NUnit are
detected and rejected** as `engine-misconfigured` ("…supports xUnit v2
only"). xUnit **v3** runs, but coverage is deferred with a warning.

### Project skeleton

```
my-dotnet-project/
├── MathLib/
│   ├── MathLib.csproj
│   └── Math.cs
└── MathLib.Tests/
    ├── MathLib.Tests.csproj
    └── MathTests.cs
```

The test project's `.csproj` must declare
`<PackageReference Include="xunit" …>`.

Detection is by **glob**: `*.csproj` at the root or one directory
deep, or `*.sln` at the root (this is what lets the canonical
`MyLib` + `MyLib.Tests` split be found). novetest picks the first
csproj whose name contains "test".

### Toolchain

- .NET SDK ≥ 8.0 (`dotnet` on PATH).
- For coverage only: `coverlet.collector` ≥ 6.0.2 in the test
  project. **Coverlet is not a readiness gate** — bare `novetest run`
  works without it; only `--coverage` needs it.

### External command

```
dotnet test <csproj> --logger "trx;LogFileName=results.trx"
  --results-directory <results> [--collect:"XPlat Code Coverage" --settings <runsettings>]
  [--filter "FullyQualifiedName~<target>"]
```

On coverage runs the adapter first runs `dotnet restore <csproj>`.

### Coverage

Coverage is Cobertura XML via Coverlet (using a per-run hermetic
runsettings; your own runsettings are never modified). If Coverlet is
absent or below 6.0.2, coverage degrades with a warning.

---

## Readiness states & the engine-missing error

Every `init` reports an `engine readiness` line; the readiness state is
exactly one of three:

- `ready` — the adapter applies and the tooling resolves.
- `engine-missing` — no supported engine matches, **or** the engine
  binary itself is absent (node/npx, go, cargo, dotnet not on PATH),
  **or** a Python workspace has no pytest configuration.
- `engine-misconfigured` — the engine applies but required tooling or
  config is missing (plugin missing, nextest missing, wrong test
  framework, JDK missing, etc.).

Once an engine is pinned, `novetest init` never fails on a *bad*
engine — it records the readiness state and moves on. (The two cases
where `init` does refuse — no marker at all, or several viable
engines — are about *which* engine, not its health; see "the pin"
above.) But the next `novetest run`/`novetest test` exits **4** with
error code `engine-missing` (the readiness state verbatim — the code IS
the state) or `engine-misconfigured`. Real run against a Python
workspace that has no pytest config:

```
✗ run
  engine-missing: engine readiness state: engine-missing (engine=(none detected))
```

(exit 4)

---

## After language setup, return to the canonical flow

Once your engine's toolchain is installed and your project skeleton
is in place, **the rest of the workflow is identical** to
[quick-start.md](./quick-start.md):

```bash
cd my-project
novetest init
novetest test
```

The text-mode output shape is the same across all six engines. Only
the per-test identity strings and the coverage format differ; the
orchestration layer normalizes those so the recommendation output
stays language-agnostic. The one capability difference to remember:
**coverage is available for pytest, jest, junit, xunit, and
cargo-test — but not for go-test.**
