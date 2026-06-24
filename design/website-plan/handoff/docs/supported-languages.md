# Supported Languages

The canonical happy path in [Quick Start](./quick-start.md) is
language-agnostic. This page documents only **what differs per
language**: detection markers, the toolchain you need on PATH, the
minimal project skeleton, per-test identity convention, the coverage
format, and the per-engine quirks the adapter team has pinned over
development.

`novetest` auto-detects which engine your project uses from workspace
markers (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`,
`pom.xml` / `build.gradle`, `*.csproj` / `*.sln`). **You do not pass
an `--engine` flag.**

---

## Detection priority — one engine at a time

`novetest test` (and every other non-`init` verb) runs **one engine
at a time**. Detection walks a fixed priority list and **returns on
the first marker match**:

| # | `engine` | `ecosystem` | Workspace markers |
|---|---|---|---|
| 1 | `pytest` | `python` | `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini` |
| 2 | `jest` | `javascript-typescript` | `package.json` |
| 3 | `junit` | `java` | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| 4 | `go-test` | `go` | `go.mod` |
| 5 | `cargo-nextest` | `rust` | `Cargo.toml` |
| 6 | `xunit` | `dotnet` | `*.csproj` (1-depth glob), `*.sln` |

::: tabs
@tab For human

If your workspace root has both `pyproject.toml` AND `package.json`,
`novetest test` from that root will only run **pytest** — the
JavaScript suite is silently ignored. This is by design at MVP (the
single-engine assumption is baked into the Run Record schema and
every downstream engine).

@tab For agent

Polyglot workspaces with multiple markers at the same root → only
the first match is selected; the others are silently ignored at
this invocation. Polyglot orchestration in a single envelope is
post-MVP (future verb: `novetest workspaces test`).

The detection result is exposed on the `init` envelope as
`data.engine_readiness.engine` + `data.engine_readiness.ecosystem`
— the canonical machine-readable identifier pair.

:::

### Working with a polyglot repository

The supported pattern is **one `.novetest/` per ecosystem
subdirectory**:

```
polyglot-repo/
├── backend/
│   ├── pyproject.toml
│   ├── my_module/
│   ├── tests/
│   └── .novetest/        ← `cd backend && novetest init`
└── frontend/
    ├── package.json
    ├── src/
    ├── __tests__/
    └── .novetest/        ← `cd frontend && novetest init`
```

Then:

```bash
( cd backend  && novetest test )   # runs pytest only
( cd frontend && novetest test )   # runs jest only
```

Each subdirectory's `.novetest/` carries its own run history,
coverage facts, regression baselines, and SBFL findings — completely
isolated. The walk-up rule from
[Quick Start -> Where do I run `novetest test` from?](./quick-start.md#where-do-i-run-novetest-test-from)
guarantees that `novetest test` from `backend/tests/` finds
`backend/.novetest/`, not the frontend one.

---

## Quick toolchain matrix

| Engine | What must be on PATH | Coverage tool |
|---|---|---|
| pytest | `python` ≥ 3.11 (your project's, not the bundled one) + `pytest` | `pytest-cov` |
| jest | Node.js ≥ 18 (`node`, `npx`) + `jest` in the project's `node_modules` | jest built-in (Istanbul) |
| gotest | Go ≥ 1.21 | built-in `go test -cover` |
| cargo | Rust toolchain + `cargo-nextest` ≥ 0.9.50 + `cargo-llvm-cov` (for coverage) | `cargo-llvm-cov` (LCOV output) |
| junit | JDK ≥ 17 + Maven ≥ 3.9 OR Gradle ≥ 7.6; JUnit 5 in project deps | JaCoCo plugin (auto-injected for Gradle) |
| xunit | .NET SDK ≥ 8.0; xUnit v2 ≥ 2.4 in test project | `coverlet.collector` ≥ 6.0.2 |

::: tabs
@tab For human

If a toolchain piece is missing, `novetest init` will tell you
exactly what to install. The hint is on the line right after
`engine readiness: engine-missing`.

@tab For agent

Missing toolchain -> `init` reports
`engine_readiness.state = "engine-missing"` (with actionable hints
in `engine_readiness.issues[]`) but does **not** fail. Subsequent
`novetest test` exits **4** with
`errors[0].code = "engine-missing"` or `"engine-not-ready"` until
you fix the host. The hint `details.install_hint` is a one-line
shell command.

:::

---

## pytest (Python)

This is the **baseline** used in [Quick Start](./quick-start.md);
treat that page as the canonical pytest walkthrough.

### Project skeleton

```
my-project/
├── pyproject.toml
├── my_module/
│   ├── __init__.py
│   └── math_utils.py
└── tests/
    └── test_math_utils.py
```

Markers `novetest` looks for: `pyproject.toml`, `setup.py`,
`setup.cfg`, `pytest.ini`. Default test path is `tests/` (or
whatever your `[tool.pytest.ini_options].testpaths` says).

### Toolchain

```bash
# In a venv or globally:
pip install pytest
# For coverage:
pip install pytest-cov
```

### Per-test identity

pytest's `nodeid`: `tests/test_x.py::test_y`. Outcomes:
`passed` / `failed` / `skipped`. Duration: seconds, float.

Coverage is JSON via `pytest-cov` (`coverage.json`).

### Quirks

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is forced internally so that
  venv-local plugins do not leak into the run. If you rely on a
  pytest plugin, add it to `pyproject.toml` and load it explicitly
  via `addopts = "-p my_plugin"`.
- pytest coverage is collected with `--cov-context=test`, which
  enables per-test coverage facts (required for SBFL per-test
  mode). Without it the localization stage degrades to aggregate
  mode.
- Target expressions are passed verbatim to pytest. You can pass a
  nodeid (`tests/test_math.py::test_add_positive`), a directory
  (`tests/`), or a single file.

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

`package.json`:

```json
{
  "name": "my-js-project",
  "version": "0.0.0",
  "private": true,
  "scripts": { "test": "jest" },
  "devDependencies": { "jest": "^29.7.0" }
}
```

Marker: any `package.json` with `jest` in dependencies or
devDependencies. Test discovery defaults to `**/__tests__/**` or
`**/*.{test,spec}.{js,jsx,ts,tsx}`.

### Toolchain

```bash
# In the project root:
npm install --save-dev jest
# (Optional, for TS:) npm install --save-dev ts-jest typescript
```

`jest` is invoked via `npx jest`. Node ≥ 18 must be on PATH.

### Per-test identity

jest's `testResults[].assertionResults[]` shape — each assertion
carries `title`, `status` (`passed` / `failed` / `pending` /
`skipped`), `duration` (ms, integer), and `location.line`. The
per-file rollup is one `testResults[]` entry per test file.

Coverage is **Istanbul JSON** (`coverage/coverage-final.json`).

### Quirks

- The adapter passes `--testLocationInResults` so jest emits
  file:line of each test (required for SBFL line-level
  localization).
- `--watchman=false` is forced for determinism on Windows.
- On Windows hosts the adapter wraps `npx` with `cmd /c` to handle
  the batch-shim. On Linux/macOS the invocation is direct.
- A workspace-local `jest.config.js` (or `jest.config.ts`) is
  honored as-is. You do not need to pass `--config`.

---

## gotest (Go / `go test`)

### Project skeleton

```
my-go-module/
├── go.mod
├── math.go
└── math_test.go
```

`go.mod`:

```
module example.com/math

go 1.21
```

Marker: `go.mod`. Default target is `./...` (all packages in the
module).

### Toolchain

Install Go ≥ 1.21 from <https://go.dev/dl/>. No separate coverage
tool — coverage is built into `go test -cover`.

### Per-test identity

`<Package>::<TestName>`. Sub-tests use the `/` separator:
`example.com/math::TestAdd/subtable_case_1`.

Coverage is Go's native **`.out` profile** (text-based, per-line
hit counts).

### Quirks

- `-count=1` is forced so Go's test-result cache does not return a
  stale pass.
- `-coverpkg=./...` is forced so coverage measures the whole
  module, not just the test package.
- `GOTOOLCHAIN=local` is forced so Go does not auto-download a
  different toolchain mid-run.
- Build failures (compile errors before any test runs) are
  detected by "no `run` action AND non-zero exit" and surfaced as a
  typed error envelope, not as a silent "no tests".

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

`Cargo.toml`:

```toml
[package]
name = "my_rust_crate"
version = "0.0.0"
edition = "2021"

[lib]
path = "src/lib.rs"
```

Marker: `Cargo.toml`. Default target is the workspace
(`--workspace` is forwarded).

### Toolchain

```bash
# Install rustup from https://rustup.rs
rustup install stable
cargo install cargo-nextest --locked    # MANDATORY — no fallback
cargo install cargo-llvm-cov            # required for coverage
```

The adapter **requires** `cargo nextest`; there is no fallback to
`cargo test`. Floor is `cargo-nextest` ≥ 0.9.50.

### Per-test identity

`cargo nextest`'s libtest-JSON NDJSON
(`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` is set internally). Test
identity carries the binary path prefix:
`my_rust_crate::tests::test_add`.

Coverage is **LCOV** (`coverage.lcov`) produced by
`cargo llvm-cov nextest --lcov`.

### Quirks

- Coverage and non-coverage runs use **different** cargo
  invocations (`cargo llvm-cov nextest` vs `cargo nextest run`);
  they are mutually exclusive at the cargo level. The Run engine
  picks based on whether the orchestrator asked for coverage.
- `--ignore-run-fail` is forced for coverage so the LCOV is written
  even when tests fail.
- Directory-type targets (`novetest test .`) deliberately do NOT
  append `.` to the nextest filter, since nextest treats an empty
  filter as "all".
- A filter that matches no tests exits non-zero from cargo, but
  the adapter distinguishes "filter matched nothing" (exit 4 with
  a clear error) from "build failed" (exit 101 with a separate
  error code).

---

## junit (Java / JUnit 5)

### Project skeleton (Maven)

```
my-java-project/
├── pom.xml
└── src/
    ├── main/java/com/example/Math.java
    └── test/java/com/example/MathTest.java
```

`pom.xml` (excerpt):

```xml
<dependencies>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.0</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

### Project skeleton (Gradle)

```
my-gradle-project/
├── build.gradle
└── src/
    ├── main/java/com/example/Math.java
    └── test/java/com/example/MathTest.java
```

`build.gradle` (excerpt):

```groovy
plugins { id 'java' }
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'
}
test { useJUnitPlatform() }
```

Markers: `pom.xml` OR `build.gradle{,.kts}`. When both are present
in the same directory, the adapter picks Maven and emits a warning
in `envelope.warnings[]` (code: `junit-multiple-build-systems`).

### Toolchain

- JDK ≥ 17 (`java` on PATH)
- Maven ≥ 3.9 (`mvn` on PATH) OR Gradle ≥ 7.6 (`gradle` on PATH;
  the wrapper `./gradlew` in the workspace is also honored)

The adapter ships a vendored
`junit-platform-console-standalone-1.11.4.jar` (EPL 2.0,
attribution in the wheel's `*.dist-info/licenses/NOTICES.md`). The
vendored jar is reserved for future "list tests without running"
discovery; it is not used during normal `novetest test` invocation.

### Per-test identity

JUnit's classname#method form: `com.example.MathTest#testAdd`.
Status values: `passed`, `failed`, `skipped`, `errored`. Failure
details include `message`, `type`, `stack`.

Coverage is **JaCoCo XML** (`target/site/jacoco/jacoco.xml` for
Maven, `build/reports/jacoco/test/jacocoTestReport.xml` for Gradle).

### Quirks

- For Maven coverage, the adapter passes
  `-Dmaven.test.failure.ignore=true` so the JaCoCo report runs even
  when tests fail.
- For Gradle coverage, the adapter injects an init-script globally
  that auto-applies the JaCoCo plugin if missing, so you do not
  need to wire it into `build.gradle` yourself.
- Multi-module Maven projects: per-module `target/surefire-reports/`
  directories are globbed and each test result carries its `module`
  field for attribution.
- JUnit 4 / TestNG are detected and rejected with a clear
  diagnostic; only JUnit 5 (Jupiter) is supported at MVP.

---

## xunit (.NET / xUnit v2)

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

`MathLib.Tests.csproj` (excerpt):

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
    <PackageReference Include="xunit" Version="2.6.6" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.6" />
    <PackageReference Include="coverlet.collector" Version="6.0.2" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="..\MathLib\MathLib.csproj" />
  </ItemGroup>
</Project>
```

Marker: any `*.csproj` or `*.sln` in the workspace. When multiple
test projects are found, the alphabetically first one named
`*Test*` / `*Tests*` is chosen and a warning is emitted in
`envelope.warnings[]`.

### Toolchain

- .NET SDK ≥ 8.0 (`dotnet` on PATH).
- xUnit v2 ≥ 2.4 declared in the test project's `PackageReference`s.
- `coverlet.collector` ≥ 6.0.2 declared in the test project's
  `PackageReference`s (for `--coverage`).

xUnit v3 is detected and emits a warning that coverage is not yet
supported in v3 (it is forced to no-op); the test run itself still
works.

### Per-test identity

`namespace.class#method`: `MyNamespace.MathTests#TestAdd`. The
adapter parses the **TRX** (Test Result XML, Microsoft format)
emitted by `dotnet test --logger trx`. Status values: `passed`,
`failed`, `skipped`, `errored`.

Coverage is **Cobertura XML** produced by Coverlet
(`TestResults/coverage.cobertura.xml`). The adapter generates a
hermetic `coverlet.runsettings` per run; it never modifies any
runsettings you have in your repo.

### Quirks

- `dotnet restore <csproj>` is run before the coverage probe so the
  version detection has the restored `project.assets.json`
  available.
- `<SingleHit>false</SingleHit>` is forced in the generated
  runsettings, otherwise Coverlet reports zero-hit lines as
  misleading no-hits.
- Per-test coverage via Coverlet's XPlat collector is empirically
  inert on Coverlet 6.0.x / SDK 8.0 (the generated runsettings
  still include the per-test template for forward compatibility,
  but per-test coverage facts fall back to aggregate granularity).
- Multiple `*.csproj` at workspace root with a sibling `*.sln` ->
  the adapter picks the alphabetically first matching csproj and
  warns; specify the csproj as your target if you want a specific
  one.

---

## After language setup, return to the canonical flow

Once your engine's toolchain is installed and your project skeleton
is in place, **the rest of the workflow is identical** to
[Quick Start](./quick-start.md):

```bash
cd my-project
novetest init
novetest test
```

::: tabs
@tab For human

The text-mode output shape
(`<glyph> [<category>] <sentence>\n  ↳ <citation>`) is the same
across all six engines. Only the values inside the per-test
identity strings and the coverage representation differ; the
orchestration layer normalizes those so the recommendation output
stays language-agnostic.

@tab For agent

The envelope shape `novetest test` returns is the same across all
six engines. Only the values inside
`run_record.test_results[].test_id` and the coverage representation
differ; the orchestration layer normalizes those so your downstream
recommendation routing is language-agnostic.

Specifically, your agent can rely on:

- `data.run_reference.run_id` is a ULID, format-stable across
  engines.
- `data.stage_eligibility.*` ∈ `{"available", "unavailable", "not_run"}`.
- `data.recommendations[].category` comes from a closed taxonomy
  shared by all engines.

The engine-specific values only matter when you walk a citation —
e.g., `evidence_citations[0].selector.test_id` will look different
per engine (`tests/test_x.py::test_y` for pytest vs
`example.com/math::TestAdd` for go vs
`com.example.MathTest#testAdd` for junit), and your agent should
treat `test_id` as an opaque string keyed off the engine identifier.

:::

---

## What to read next

- **[Quick Start](./quick-start.md)** — re-read with your language's
  toolchain in mind.
- **[Understanding Results](./understanding-results.md)** — the
  same recommendation taxonomy applies regardless of engine.
- **[Troubleshooting](./troubleshooting.md)** — per-engine errors
  and their one-line fixes.
