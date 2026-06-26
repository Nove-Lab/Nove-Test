# Per-Language Notes (Human)

The canonical happy path in [quick-start.md](./quick-start.md) is
language-agnostic — same `init` → `test` flow, same text-mode output
shape. This page documents only **what differs** per language: the
toolchain you need on PATH, the detection marker, the external command
the adapter invokes (shown simplified — coverage runs add a few extra
flags), and whether coverage is available.

`novetest` auto-detects which engine your project uses from workspace
markers. You **do not** pass an `--engine` flag.

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

## One `novetest test` call = exactly one engine

`novetest test` (and every other non-`init` verb) runs **one engine
at a time**. When a polyglot repo matches several ecosystems at the
same root, readiness disambiguates with a fixed priority:

```
pytest > jest > go-test > cargo-test > junit > xunit
```

So a workspace root with both `pyproject.toml` AND `package.json`
routes to **pytest** — the JavaScript suite is silently ignored at
that invocation. This is by design at MVP (the single-engine
assumption is baked into the Run Record schema and every downstream
engine).

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

`pytest` and the `pytest-json-report` plugin must be importable from
the **interpreter that runs novetest** (the external command is
`<sys.executable> -m pytest …`, not a `pytest` on PATH). Add
`pytest-cov` for coverage.

### External command

```
<python> -m pytest -p pytest_jsonreport --json-report
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

`novetest init` never fails on a bad engine — it records the state and
moves on. But the next `novetest run`/`novetest test` exits **4** with
error code `engine-engine-missing` (the literal string — note the
doubled "engine") or `engine-engine-misconfigured`. Real run against a
Python workspace that has no pytest config:

```
✗ run
  engine-engine-missing: engine readiness state: engine-missing (engine=(none detected))
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
