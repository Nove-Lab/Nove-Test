# Implementation Plan - Engine Adapters

**Scope:** Per-ecosystem implementation strategy for the native engine adapters under `src/novetest/run/adapters/`. Discovery, structured execution output, failure detail capture, coverage emission, per-test attribution feasibility, plugin requirements, and known edge cases for each of the six target ecosystems.

**Upstream**
- Foundations: [`foundations.md`](./foundations.md)
- Run interface contract: [`design/interace-contract/run.md`](../interace-contract/run.md)
- Coverage interface contract: [`design/interace-contract/coverage.md`](../interace-contract/coverage.md)
- Run product plan: [`design/product-plans/subproducts/nove-test-run.md`](../product-plans/subproducts/nove-test-run.md)
- Coverage product plan: [`design/product-plans/subproducts/nove-test-coverage.md`](../product-plans/subproducts/nove-test-coverage.md)

---

## Cross-Cutting: Per-Test Coverage Attribution

This is the load-bearing constraint for our Coverage and Localization engines. The Coverage interface advertises "test-to-code mapping"; we have to deliver that with varying fidelity per ecosystem.

| Ecosystem | Per-test attribution | Mechanism | Default mode |
| --- | --- | --- | --- |
| Python (pytest + coverage.py) | **Yes - first class** | `--cov-context=test` dynamic contexts; JSON report `contexts` map per line | `per-test` |
| .NET (xUnit + Coverlet) | **Yes** | Coverlet collector `PerTestCoverage` (Coverlet 6+); `Microsoft.CodeCoverage` per-test mode | `per-test` |
| Java (JUnit 5 + JaCoCo) | No (aggregate) | Workaround: `forkMode=perTestClass` with merged sessions - **class-level only** | `per-test-class` |
| JavaScript / TypeScript (Jest + Istanbul) | No (aggregate) | Workaround: per-file isolated runs with merged Istanbul JSON - **file-level only** | `per-test-file` |
| Go (`go test`) | No (aggregate) | Workaround: per-test invocation with N coverprofiles - slow | `aggregate` (opt-in `--per-test-coverage`) |
| Rust (`cargo-llvm-cov`) | No (aggregate) | Workaround: per-test invocation - slow | `aggregate` (opt-in `--per-test-coverage`) |

### Implication for Coverage Fact schema

Every Coverage Fact carries a `mapping_granularity` field with values `per-test`, `per-test-class`, `per-test-file`, or `aggregate`. The Localization engine reads this field to pick its `mode` (see [`localization-strategy.md`](./localization-strategy.md#2-degradation-when-per-test-coverage-is-unavailable)). Regression and Replay tolerate the coarser granularity gracefully.

This tiering is product-visible. Surface it in the JSON envelope so AI agents can reason about evidence strength.

---

## 1. Python + pytest

### Required user-project plugins

| Package | Purpose | Min version |
| --- | --- | --- |
| `pytest-json-report` | Stable structured run output | `>= 1.5` |
| `pytest-cov` | Coverage collection wrapper around `coverage.py` | latest |
| `coverage[toml]` | Coverage backend with `contexts` support | `>= 7.0` |

The adapter's `detect()` checks `pyproject.toml` / `setup.cfg` / `pytest.ini` for pytest config; its first user-facing failure mode is a clear "missing required plugin" message with install instructions, exit code 4.

### Discovery

```
pytest --collect-only --json-report --json-report-file=collect.json -p no:cacheprovider
```

Parse the `collectors` and `tests` arrays from `collect.json`. Each test entry includes `nodeid`, file, line number. Collection errors land in `collectors[*]` with non-OK status - surface as discovery failures.

Plain-text fallback (`--collect-only -q`) only if `pytest-json-report` is not installed; we degrade with a warning rather than fail outright.

### Execution with structured output

```
pytest <target> \
  --json-report \
  --json-report-file=$RUN_DIR/native/pytest-report.json \
  --json-report-omit=warnings,keywords \
  -p no:cacheprovider \
  -vv --tb=long \
  -o truncation_limit_lines=0 -o truncation_limit_chars=0
```

The JSON report's stable schema includes per-test `nodeid`, `outcome` (passed/failed/skipped/xfailed/xpassed/error), `setup`/`call`/`teardown` phase outcomes and durations, `crash` block (path/lineno/message), `traceback` array, `stdout`/`stderr`/`log`. The `--tb=long` plus disabled truncation gives us full assertion diffs.

JUnit XML is emitted in parallel (`--junitxml=$RUN_DIR/native/junit.xml`) only as a portability safety net for downstream tooling. Internal parsing always uses the JSON report.

### Failure detail capture

From the JSON report:
- Assertion message: `tests[*].call.crash.message`
- Long repr (pytest's pretty-printed diff): `tests[*].call.longrepr`
- Frames: `tests[*].call.traceback[]`
- Captured streams: `tests[*].call.stdout` / `call.stderr`

### Coverage emission

```
pytest <target> \
  --cov=<scope> \
  --cov-report=xml:$RUN_DIR/native/coverage.xml \
  --cov-report=json:$RUN_DIR/native/coverage.json \
  --cov-context=test \
  --cov-branch
```

Parse `coverage.json` (stable since coverage.py 5.0). It gives per-file line hits, branch arcs, and crucially the `contexts` map per line listing the test nodeids that hit it. **This is the cleanest test-to-code map of any ecosystem we support.** Emit Cobertura XML in parallel for downstream interop.

### Edge cases

- `pytest-xdist` parallelism breaks `pytest-json-report` unless we add `--json-report-merge` (plugin 1.5+). Detect xdist usage and add the flag.
- Doctest collection adds nodeids without source-file line numbers; tolerate missing `lineno`.
- `conftest.py` collection errors land in `collectors[*]`, not `tests[*]` - they are discovery failures, not test failures.
- Windows: nodeids use forward slashes but file paths use backslashes - normalize at the parser boundary.
- Pin `pytest-cov` and `coverage` minor versions; they skew often.

### Implementation note

Plugin presence check: parse `pytest --version --version` (which lists active plugins) or call `python -m pip show pytest-json-report` against the resolved interpreter. Cache the check per `(interpreter, target)` so the doctor pass runs once per session.

---

## 2. JavaScript / TypeScript + Jest

**Decision: Jest as the primary; Vitest as an opt-in alternate.** Jest's `--json` has been stable since Jest 20; Vitest's reporter schema has shifted across 1.x → 2.x and is still maturing.

### Discovery

Jest's discovery is file-level by design. Best we can do without executing test bodies:

```
jest --listTests --json
```

This returns a JSON array of absolute test file paths. To enumerate individual `test()`/`it()` blocks, we accept that Jest does not support that without invoking setup. Either statically parse with a TS/JS parser (later), or rely on file-level discovery and post-hoc test listing from the run JSON.

### Execution with structured output

```
jest <target> \
  --ci \
  --json \
  --testLocationInResults \
  --outputFile=$RUN_DIR/native/jest-results.json \
  --reporters=default \
  --watchman=false
```

`--testLocationInResults` is mandatory - without it we cannot map test → file:line. The schema is documented and stable. `--watchman=false` makes Windows behavior predictable (watchman is often absent there).

Each `assertionResult` includes:
- `failureMessages: string[]` - already rendered with stack frames
- `failureDetails: object[]` - raw matcher info (`matcherName`, `expected`, `actual`, `pass`)
- `location: { line, column }` per `--testLocationInResults`

Suite-level errors (e.g., import failures) come through as `testExecError` on the suite object - surface separately from test failures.

### Failure detail capture

- Assertion message: `assertionResult.failureMessages` joined.
- Structured matcher info: `assertionResult.failureDetails`.
- Per-test console output: configure `silent: false` and parse `testResults[].console: [{ type, message, origin }]`.

### Coverage emission

Configure for the run:

```
jest <target> \
  --coverage \
  --coverageDirectory=$RUN_DIR/native/coverage \
  --coverageReporters=json --coverageReporters=cobertura --coverageReporters=lcov
```

Parse `coverage/coverage-final.json` (Istanbul's raw format) - statement, branch, and function maps with source positions. Cobertura XML is the portable fallback for our internal Coverage engine when the raw Istanbul JSON is missing.

### Test-to-code mapping

**Aggregate by default; degraded per-file when opt-in.** Istanbul does not natively tag coverage by test. Per-test attribution requires running each test file (or each test) in isolation with separate coverage outputs and merging. We expose this as an opt-in slow mode and document it as `mapping_granularity: per-test-file`.

### Edge cases

- `coverage-final.json` paths are absolute; normalize to repo-relative.
- ESM projects need `--experimental-vm-modules`; coverage in ESM was buggy in Jest 28-29, better in Jest 30 - flag the version in the doctor pass.
- Monorepos: prefer running Jest from each workspace package root with a workspace-aware adapter rather than one root invocation.

### Vitest

Available as an alternate adapter (`vitest.py` parallel to `jest.py`). Force `--coverage.provider=istanbul` for parity with Jest's coverage shape. Schema differences across Vitest versions are absorbed by the parser. Document Vitest as a Phase 2+ addition; do not ship it in Phase 1.

---

## 3. Java + JUnit 5 (Maven Surefire / Gradle, JaCoCo)

### Required project setup

The user must already use Maven or Gradle with JUnit 5 (Jupiter). Our adapter does not modify the build file; it expects:
- Surefire (Maven) or `useJUnitPlatform()` (Gradle)
- JaCoCo plugin if coverage is requested

The JUnit Platform Console Launcher is **vendored inside our distribution**
at `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
(the only supported strategy — no download-on-first-use, no network at
runtime). The user does NOT install it. See
[`decisions/2026-06-03-junit-console-launcher-vendor.md`](../../agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md)
(closes Open Question #5) for the EPL 2.0 attribution + binary-blob extraction
contract.

### Discovery

The robust path is the JUnit Platform Console Launcher 1.10+:

```
java -jar junit-platform-console-launcher.jar discover \
  --details=tree --details-theme=ascii \
  --reports-dir=$RUN_DIR/native/discovery \
  -cp <test-classpath>
```

The Console Launcher's `discover` subcommand emits an enumeration without execution. **Vendor a pinned copy of the Console Launcher with the Java adapter** so users without it still get discovery.

For execution we defer to Surefire / Gradle so users keep their build config.

### Execution with structured output

**Maven:**

```
mvn -B test \
  -Dsurefire.reportFormat=plain \
  -Dsurefire.useFile=false
```

Surefire writes JUnit-XML reports to `target/surefire-reports/TEST-*.xml` regardless. Configure stable filenames in the project's `pom.xml` if necessary; we do not auto-modify.

**Gradle:**

```
./gradlew test --no-daemon
```

with the project configured for `useJUnitPlatform()` and JUnit XML reports enabled. Reports land at `build/test-results/test/*.xml`.

**Modern (lossless) format:** the JUnit Platform Console Launcher additionally writes "open-test-reporting" event streams - schema at `https://schemas.opentest4j.org/`. Prefer OTR XML when the project has it; fall back to the Surefire/Gradle JUnit XML otherwise.

### Failure detail capture

JUnit XML `<failure>` / `<error>` elements carry `message`, `type`, and the full stack trace as element text. Per-test stdout/stderr live in `<system-out>` / `<system-err>` if the user has `redirectTestOutputToFile=true` (Maven) or `testLogging.showStandardStreams=true` (Gradle).

OTR additionally has structured `reportEntry` events with key/value metadata - richer when present.

### Coverage emission

JaCoCo. Maven adds `jacoco-maven-plugin` with `prepare-agent` and `report` goals; output is `target/site/jacoco/jacoco.xml`. Gradle applies the `jacoco` plugin with `test { finalizedBy jacocoTestReport }`; output is `build/reports/jacoco/test/jacocoTestReport.xml`.

Parse JaCoCo XML directly: line, branch, instruction, and method counters per class.

### Test-to-code mapping

**Aggregate by default; per-test-class with `forkMode=perTestClass` opt-in.** JaCoCo supports execution-data sessions but per-test-method attribution requires a fresh JVM per test method, which is prohibitive at scale. Document `mapping_granularity: aggregate` or `per-test-class`.

### Edge cases

- Surefire's XML report path/filename varies by version; parse the directory rather than guessing names.
- Gradle daemon caches test results; require `--rerun-tasks` for clean reruns.
- Parametrized tests have non-deterministic display names; use `uniqueId` from OTR as stable identity, not display name.
- Multi-module Maven: one report per module - walk modules and aggregate.
- Kotlin/Scala tests work via JUnit Platform but produce synthetic display names; same advice - prefer `uniqueId`.

---

## 4. Go + `go test`

### Discovery

```
go test -list '.*' ./...
go list -f '{{.Dir}} {{.TestGoFiles}} {{.XTestGoFiles}}' ./...
```

The first lists test names per package (plain text, one per line, with package transitions). The second enumerates test files per package. There is no JSON variant of `-list`; parse plain text.

### Execution with structured output

```
go test -json -count=1 -timeout=10m ./...
```

`-json` has been stable since Go 1.10 (documented under `go doc cmd/test2json`). It emits newline-delimited JSON events `{Time, Action, Package, Test, Output, Elapsed}` with actions `run`, `pause`, `cont`, `pass`, `bench`, `fail`, `output`, `skip`. **Stream-parse stdout** - do not buffer the whole output before parsing.

### Failure detail capture

`Output` events carry the test's stdout/stderr lines as the test produces them, including `t.Logf` and panic stack traces. There is no separate "stack trace" field; the trace is interleaved in `Output` events between `run` and `fail` for the same `(Package, Test)` key. Reassemble per-test by buffering `Output` events keyed on `(Package, Test)` until a terminal action arrives.

Subtests appear with `Test: "Parent/Child"`; track parent/child relationships from the `/`-delimited name.

### Coverage emission

```
go test -cover -coverprofile=$RUN_DIR/native/cover.out -covermode=atomic ./...
```

Native cover-profile format: `mode: atomic` first line, then `<file>:<startLine>.<startCol>,<endLine>.<endCol> <numStmts> <count>` per region. Parse directly. For LCOV/Cobertura interop, optionally call `gocover-cobertura` (third-party) - we do not require it.

For Go 1.20+ binary integration coverage:

```
go build -cover -o ./bin/myapp ./cmd/myapp
GOCOVERDIR=$RUN_DIR/native/integration-cov ./bin/myapp ...
go tool covdata textfmt -i=$GOCOVERDIR -o=$RUN_DIR/native/cover.out
```

### Test-to-code mapping

**Aggregate only by default.** Go's coverage instruments source blocks but has no notion of which test executed which block. Per-test mapping = N invocations with separate `-coverprofile`s, prohibitive at scale. Opt-in `--per-test-coverage` slow mode for users who genuinely need it.

### Edge cases

- Build failures appear as `Action: output` events with `Test: ""`; detect and surface as discovery/build errors.
- `go test` caches; pass `-count=1` to force re-run.
- Subtests with slashes need URL-style escaping when used as filenames.
- `-coverpkg=./...` is required to measure packages other than the test's own package - easy to miss.
- Race detector (`-race`) doubles runtime and changes scheduling; expose as a separate Nove Test mode, not the default.
- On Windows, `go test ./...` walks vendored directories unless `GOFLAGS=-mod=readonly`.

---

## 5. Rust + `cargo nextest`

**Decision (CEO-approved 2026-05-29, `decisions/2026-05-29-cargo-adapter-nextest-primary.md`): `cargo-nextest` is the ONLY execution path. No plain-text `cargo test` fallback. No nightly `-Z unstable-options` JSON path.**

`cargo-nextest`'s `libtest-json` message format is stable on stable Rust at nextest **0.9.50+** (2024). That replaces both:
- the plain-text `cargo test` fallback this section originally sketched (lossy, locale-dependent, no per-test duration / failure detail), and
- the nightly `cargo test --format=json -Z unstable-options` path (regresses Rust support to "nightly required").

Users without nextest get an `engine-misconfigured` readiness state with a clear install hint (`cargo install cargo-nextest --locked` or `cargo binstall cargo-nextest`). Nove Test does not silently degrade.

### Discovery

```
cargo nextest list --message-format=json
```

Stable output since nextest 0.9. (Discovery is currently out-of-scope for the adapter — the v1 slice ships execution + coverage only.)

### Execution with structured output

```
cargo nextest run \
  --message-format=libtest-json \
  --no-fail-fast \
  --workspace \
  [<target_expression>]
```

The adapter does **NOT** write `.config/nextest.toml` (the "we never modify the build file" rule applies across all six ecosystems). `--message-format=libtest-json` is stable on nextest >= 0.9.50.

Each NDJSON line shapes roughly:

- Suite-level: `{"type":"suite", "event":"started"|"ok"|"failed", ...}`
- Test-level: `{"type":"test", "event":"started"|"ok"|"failed"|"ignored", "name":"<crate>::<path>", "stdout":"...", "stderr":"...", "exec_time": <seconds>}`

The `name` field already carries the binary path prefix in nextest mode (e.g. `crate--integration_test::test_x` for an integration-test binary), so it is used directly as the Run Record's `node_id`.

### Failure detail capture

The `test` event with `event: "failed"` carries `stdout` and `stderr` strings — the captured panic message and (with `RUST_BACKTRACE=1`) the backtrace. The adapter concatenates both into a single failure log file under `<artifact_dir>/native/failures/<safe_name>.log` and stores the relative path as the TestResult's `failure_reference`. Same coupling pattern as the gotest adapter.

### Coverage emission

```
cargo llvm-cov nextest \
  --lcov --output-path <artifact_dir>/native/coverage.lcov \
  --no-fail-fast --workspace \
  --message-format=libtest-json \
  [<target_expression>]
```

The underlying engine is LLVM source-based coverage (`-C instrument-coverage`); precise (region-level) and stable. The adapter emits LCOV only in v1 — Cobertura / LLVM JSON are deferred until Coverage team needs them. Coverage mode and execution mode are mutually exclusive per invocation (cargo-llvm-cov wraps nextest internally).

Artifact key: **`coverage_lcov`** (distinct from pytest/jest `coverage_json` and go-test `coverage_profile`). The Coverage engine dispatches on `engine_name == "cargo-test"` to parse LCOV.

### Test-to-code mapping

**Aggregate only on stable.** LLVM source-based coverage supports per-function counters but `cargo-llvm-cov` does not expose per-test tagging. Per-test mode = per-test invocations, opt-in slow mode — out-of-scope for v1 (deferred to a post-MVP slice).

### Required user-side tools

| Tool | Purpose | Min version | Readiness state on absence |
| --- | --- | --- | --- |
| `cargo` (Rust toolchain) | Build / spawn nextest | 1.74 | `engine-missing` (rustup hint) |
| `cargo-nextest` | Test runner with libtest-json output | 0.9.50 | `engine-misconfigured` (`cargo install` hint) |
| `cargo-llvm-cov` | Coverage (only when `--coverage` requested) | latest | `engine-misconfigured` (when coverage requested) |
| `llvm-tools-preview` rustup component | Required by `cargo-llvm-cov` | — | `engine-misconfigured` |

`cargo binstall` produces faster installs than `cargo install`. The adapter never invokes installs on the user's behalf — install hints are text only.

### Child subprocess env

```
CARGO_TERM_COLOR=never
RUST_BACKTRACE=1
NO_COLOR=1
```

NO `RUSTFLAGS` override (would invalidate the build cache). NO `CARGO_INCREMENTAL=0` (leave the user's incremental cache alone).

### Edge cases

- Workspaces: `--workspace` is always passed so all members run by default. Users can scope to one crate via a nextest filter expression (e.g. `package(foo)`) plumbed through `target_expression`.
- Directory-typed targets: `target_resolver` classifies `novetest run .` and `novetest run <subdir>/` as `target_type="directory"`. The adapter suppresses the positional-filter append for directory targets (Fix A, 2026-06-05 cargo CLI orchestration defect closure — see `tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md`) because `cargo nextest` interprets positional args as filter DSL tokens, not filesystem paths. v1 treats all directory-typed targets as workspace-equivalent (`--workspace` covers the workspace root, matching the `novetest run .` ↔ `novetest run` bare equivalence). Sub-crate directory selection (e.g. `novetest run crates/foo/`) would require translation to nextest's `-E 'package(crate)'` expression or cargo's `-p crate` selector — deferred until a user requests it.
- Doctests: `cargo test --doc` is a separate path; nextest does not run doctests. Out of scope for v1; future slice.
- Integration tests in `tests/` get one binary per file — they appear as separate suite blocks in the libtest-json stream and the `name` field disambiguates them.
- Build cache: ensure same `--features` set across discovery, execution, and coverage runs or the cache invalidates.
- Windows: LLVM coverage works but path normalization is tricky; lowercase drive letters when joining.
- Race detector / thread sanitizer: separate Run mode, future work.
- JUnit-XML fallback for pre-0.9.50 nextest: explicitly deferred per the Q3 decision (additive extension; does not require a v2 decision).

---

## 6. .NET / C# + `dotnet test` over xUnit (Coverlet)

### Required project setup

```xml
<PackageReference Include="Microsoft.NET.Test.Sdk" />
<PackageReference Include="xunit" />
<PackageReference Include="xunit.runner.visualstudio" />
<PackageReference Include="coverlet.collector" />
```

Optionally `JunitXml.TestLogger` for JUnit XML output if downstream tooling wants it.

### Discovery

```
dotnet test --list-tests --verbosity:quiet
```

Plain text output. For xUnit v3 projects (released 2024+), the Microsoft.Testing.Platform native discovery supports JSON:

```
dotnet test --list-tests --output json
```

The adapter detects xUnit version from the `.csproj` and picks the path.

### Execution with structured output

```
dotnet test <project> \
  --logger:"trx;LogFileName=results.trx" \
  --results-directory $RUN_DIR/native/TestResults
```

TRX is .NET's native machine format (XML), stable for 15+ years, and the most fidelity-preserving - test outcomes, durations, error info, captured output, computer/run metadata. JUnit XML via `JunitXml.TestLogger` is the portable alternative; we emit both.

For xUnit v3 (Microsoft.Testing.Platform native, bypasses VSTest) the discovery and execution flags differ; the adapter detects v2 vs v3 and routes accordingly.

### Failure detail capture

TRX `<UnitTestResult>` elements include `<Output><ErrorInfo><Message/><StackTrace/></ErrorInfo><StdOut/><StdErr/></Output>` - full capture of message, stack, and per-test stdout/stderr. xUnit's assertion messages include expected/actual values inline.

For richer assertion structure, configure `xunit.runner.json` with `"diagnosticMessages": true`.

### Coverage emission

Use the **Coverlet collector** (composes cleanly with `dotnet test`'s parallelism):

```
dotnet test <project> \
  --collect:"XPlat Code Coverage" \
  --settings $RUN_DIR/native/coverlet.runsettings \
  --results-directory $RUN_DIR/native/TestResults
```

`coverlet.runsettings` (we generate this on the fly):

```xml
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat code coverage">
        <Configuration>
          <Format>cobertura,opencover,json,lcov</Format>
          <PerTestCoverage>true</PerTestCoverage>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
```

For per-test attribution we pin `coverlet.collector >= 6.0.2, < 7.0.0`
(6.0.0/6.0.1 had a non-Windows GUID-subdirectory path bug that prevented
per-test files from being surfaced to the VSTest data collector pipe). The
`<PerTestCoverage>` element is a direct child of `<Configuration>`, PascalCase,
and the sibling `<SingleHit>false</SingleHit>` is **mandatory** — without it,
Coverlet's `SingleHit=true` default records only the first hit per line and
produces misleading zero-hit lines in per-test output when tests share
coverage paths. The element name has been stable throughout the shipped 6.x
line; the early `EnablePerTestCoverage` form was a pre-release name that did
not ship. See [`decisions/2026-06-03-coverlet-pertestcoverage-key.md`](../../agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md)
(closes Open Question #4).

**Output filename pattern depends on mode:**
- Aggregate mode (no `<PerTestCoverage>`): single file at
  `TestResults/<guid>/coverage.cobertura.xml`. Glob `TestResults/**/coverage.cobertura.xml`.
- Per-test mode (with `<PerTestCoverage>true</PerTestCoverage>`): one file
  per test method at `TestResults/<guid>/coverage.<test-slug>.cobertura.xml`
  where `<test-slug>` is a slugified form of the test's display name. Glob
  `TestResults/**/coverage.*.cobertura.xml`. The adapter MUST correlate slugified
  filenames back to test identities — parametrized xUnit test names contain
  `[`, `]`, `(`, `)`, `,`, and Unicode which Coverlet slugifies inconsistently
  across OS path-safety rules; the correlation logic is load-bearing and
  warrants a fixture probe before commit.

> **Amendment 2026-06-05**: Per [`decisions/2026-06-03-coverlet-pertestcoverage-key.md`](../../agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md) §3 (amended 2026-06-05): `<PerTestCoverage>true</PerTestCoverage>` is **empirically inert** on the Coverlet XPlat data collector path (verified on Coverlet 6.0.2 + 6.0.4, dotnet SDK 8.0.421, Linux x86_64). Only the aggregate `coverage.cobertura.xml` is produced. **The adapter ships aggregate-effective-default for v1** with a glob-first/aggregate-fallback strategy. Per-test mode on .NET is achievable only via `coverlet.msbuild` (user csproj modification — violates the non-modification contract) and is deferred. Phase 4 Localization SBFL on .NET projects operates at aggregate granularity and routes to `failure_proximity` mode (per decision §R4).

### Test-to-code mapping

**Per-test attribution is supported.** With Coverlet collector + `PerTestCoverage`, we get per-test Cobertura files. Alternatively, Microsoft's first-party `dotnet-coverage` tool's static instrumentation has a per-test mode used by Visual Studio's "Live Unit Testing." `mapping_granularity: per-test`.

### Edge cases

- Multiple TFMs: `dotnet test` runs once per target framework; aggregate per-TFM TRX files.
- Coverlet collector writes to a randomly-named GUID directory; glob `TestResults/**/coverage.cobertura.xml` (aggregate) or `TestResults/**/coverage.*.cobertura.xml` (per-test).
- TRX paths use backslash on Windows even from cross-platform builds; normalize.
- Solution files with multiple test projects parallelize per project; merge coverage with `dotnet-coverage merge` rather than concatenating XML.
- xUnit v2 vs v3: detect from project file (`<PackageReference Include="xunit" Version="3.*" />` indicates v3). v3 runs on Microsoft.Testing.Platform, which does NOT use VSTest data collectors — `coverlet.collector` is inert on the v3 path. v3 coverage support is **deferred from MVP**; the v3 adapter path emits `xunit-v3-coverage-deferred` warning and runs tests without coverage. See [`decisions/2026-06-03-coverlet-pertestcoverage-key.md`](../../agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md) §6.
- `--blame` mode (crash diagnostics) writes additional artifacts; capture but don't conflate with normal failures.
- Per-test mode performance: writes one Cobertura XML per test method, so a 10k-test suite produces 10k files. `NFR-COV-002` (50k locations <5s) was measured against single aggregate files; per-test mode against large suites needs separate validation. If the adapter fails NFR, expose `--coverage-granularity=aggregate` opt-down and default large suites to aggregate.
- User's resolved Coverlet version is detected via `dotnet list <project> package --include-transitive` (use `--format json` when SDK >= 7.0; tabular parse otherwise). Resolved version below 6.0.2 → `engine-misconfigured` warning + aggregate fallback.

---

## Adapter Implementation Pattern

Each adapter file under `src/novetest/run/adapters/` follows the same shape:

```python
# run/adapters/pytest_.py
from .base import NativeAdapter
from ..adapters import register

@register
class PytestAdapter:
    name = "pytest"
    ecosystem = "python"

    def detect(self, target: Path) -> bool:
        # Check for pyproject.toml [tool.pytest.ini_options], pytest.ini,
        # setup.cfg [tool:pytest], or conftest.py near target.
        ...

    def doctor(self) -> list[DoctorIssue]:
        # Verify pytest, pytest-json-report, pytest-cov, coverage[toml] presence.
        # Return structured issues with install hints.
        ...

    def build_argv(self, spec: RunSpec) -> list[str]:
        # Compose pytest command line from spec (target, coverage flag,
        # parallel flag, etc.) and the canonical flags from above.
        ...

    async def parse_artifacts(self, run_dir: Path) -> NormalizedResult:
        # Parse pytest-report.json, junit.xml fallback, build NormalizedResult.
        ...

    def coverage_artifact_paths(self, run_dir: Path) -> list[Path]:
        # Return list of native coverage artifact paths for the Coverage parsers.
        ...
```

### Doctor pass / engine readiness

Each adapter exposes a `doctor()` method that backs the engine-readiness pipeline. `run/readiness.assess_engine_readiness` (see [`design/interace-contract/run.md`](../interace-contract/run.md) §1) calls `detect_engine_candidates` to pick which adapters apply to the workspace, then invokes their `doctor()` calls. The combined result maps to the contract's three states:

| Adapter `doctor()` outcome | Readiness state | CLI consequence |
| --- | --- | --- |
| Adapter detected, all required tooling resolvable | `ready` | Run / test execution proceeds. |
| No adapter's `detect()` matches the workspace | `engine-missing` | Operating commands exit 4 with structured guidance listing the supported (ecosystem, engine) pairs. `novetest init` still succeeds; readiness is informational. |
| Adapter detected but required tooling unresolvable (missing plugin, missing binary, version too old) | `engine-misconfigured` | Operating commands exit 4 with the structured `DoctorIssue` records below; init still succeeds. |

`DoctorIssue` carries `severity`, `message`, `install_hint`. The install hint is text only - **Nove Test never executes it on the user's behalf**. AI agents can reason directly from the structured readiness payload; humans see the same hint in the text envelope.

The `novetest run --doctor` surface remains as an explicit way to invoke this without running tests; it is the same code path as `assess_engine_readiness`.

### Failure budget for parsers

Parsers must tolerate partial / corrupt input. A truncated JSON report from a killed pytest process should produce a Run Record with `status: errored` plus the partial `Test Result`s that were parseable, not a hard parser exception. Structure parsers as resilient stream consumers where the format permits (Go's `-json`, Jest's `--json` is whole-file but small).

---

## Open Items for Phase 2+

The following are deferred to the relevant implementation phase but recorded here so they are not lost:

1. **Vitest adapter** - alternate JS/TS engine. Not Phase 1.
2. **`cargo nextest libtest-json` stabilization** - check at Phase 2 implementation whether Rust nightly's `libtest-json` has graduated.
3. **Coverlet `PerTestCoverage` config key drift** - lock the exact key name when Phase 2 implementation begins.
4. **JUnit Platform Console Launcher vendoring** - decide license-compatible bundling vs download-on-first-use during Phase 1.
5. **Discovery for individual `it()` blocks in Jest** - statically parse with a TS/JS AST library if static enumeration becomes a hard requirement; not Phase 1.
6. **Open Test Reporting (OTR) parser for Java** - Phase 2 luxury; Phase 1 ships JUnit XML.

These map to the Open Questions list in [`delivery-phasing.md`](./delivery-phasing.md#open-questions).
