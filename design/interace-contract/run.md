# Interface Contract - Run

**Scope:** Run sub-product. Resolves Test Target, selects Native Engine, invokes execution, normalizes Native Result into a Run Record, and assigns a stable Run Reference. Run is a wrapper over native test engines; it does not redefine native discovery, assertion, or reporting semantics.

**Upstream references**
- `design/product-plans/subproducts/nove-test-run.md`
- `design/requirements-analysis/requirements-specification/groups/run.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-002, SR-003, SR-004, SR-005, SR-006)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration, Replay) within the tool boundary.
- **Native CLI** (Section 2 only) - External native test engine command surfaces that Run invokes as a subprocess. These are owned by the external Native Test Engine Ecosystem actor, not by Nove Test.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## 1. Run Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest run [target]` | External | Test Target (target expression, optional workspace context) | Run Record (with Run Reference, status, summary counts, failed Test Result references, captured output handle, recorded Native Engine context) |
| `execute(test_target)` | Internal | Test Target | Run Record bound to a fresh Run Reference and a Native Result handle preserved for Memory |
| `execute_with_engine_context(test_target, native_engine_context)` | Internal | Test Target plus a previously recorded Native Engine context (used by Replay to reuse the original engine path) | Run Record bound to a fresh Run Reference, traceable to the supplied Native Engine context |
| `resolve_test_target(target_expression, workspace_context)` | Internal | Raw target expression and current workspace context | Normalized Test Target (target expression, target type, workspace context) |
| `select_native_engine(test_target)` | Internal | Test Target | Native Engine context (engine name, engine version, ecosystem) chosen for this run |
| `normalize_native_result(native_result, native_engine_context)` | Internal | Native Result bundle plus its Native Engine context | Run Record with normalized status, Test Result entries, summary counts, captured-output handles |
| `assign_run_reference(run_record)` | Internal | Run Record without a Run Reference | Run Record bound to a stable Run Reference (`runId`, `createdAt`) |
| `list_supported_engine_pairs()` | Internal | (none) | Set of supported (ecosystem, Native Engine) pairs covering at minimum: Python+pytest, JavaScript/TypeScript+jest, Java+JUnit, Go+`go test`, Rust+`cargo test`, .NET/C#+xUnit (per REQ-RUN-006) |

---

## 2. Native Engine Interfaces Used by Run

The following native CLI surfaces are invoked by Run to produce Native Results. Run does not reimplement their semantics; it captures their outputs and normalizes them into Run Records and supporting Coverage inputs.

### 2.1 Python - pytest

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `pytest <target> --json-report --json-report-file=<path>` | Native CLI (pytest + `pytest-json-report`) | Test Target (test file/dir/nodeid expression) | Structured JSON Native Result containing per-test outcomes, durations, failure references, summary counts |
| `pytest <target> --junitxml=<path>` | Native CLI (pytest built-in) | Test Target | JUnit XML Native Result (alternate normalized form) |
| `pytest --collect-only <target>` | Native CLI (pytest) | Test Target | Native test discovery listing (used to validate the resolved target) |
| `pytest <target> --cov=<scope> --cov-report=xml:<path>` | Native CLI (pytest + `pytest-cov`/`coverage.py`) | Test Target plus coverage scope | Cobertura-style coverage XML Native Result feeding Coverage Fact derivation |

### 2.2 JavaScript / TypeScript - jest

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `jest <target> --json --outputFile=<path>` | Native CLI (jest) | Test Target (test path pattern or test name pattern) | JSON Native Result with `testResults`, per-test status, failure messages, timings |
| `jest --listTests <target>` | Native CLI (jest) | Test Target | Native test discovery listing |
| `jest <target> --coverage --coverageReporters=lcov --coverageReporters=json-summary` | Native CLI (jest) | Test Target plus coverage configuration | LCOV + JSON coverage Native Result feeding Coverage Fact derivation |

### 2.3 Java - JUnit (via Maven Surefire / Gradle)

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `mvn -q test -Dtest=<filter>` | Native CLI (Maven Surefire over JUnit) | Test Target (Surefire `-Dtest` filter) | Surefire XML Native Result under `target/surefire-reports/` |
| `gradle test --tests <filter>` | Native CLI (Gradle Test Kit over JUnit) | Test Target (Gradle test class/method filter) | JUnit XML Native Result under `build/test-results/test/` plus HTML report |
| `mvn -q jacoco:report` / `gradle jacocoTestReport` | Native CLI (JaCoCo) | (depends on prior test execution context) | JaCoCo XML/HTML coverage Native Result feeding Coverage Fact derivation |

### 2.4 Go - `go test`

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `go test -json <package_pattern>` | Native CLI (`go test`) | Test Target (package pattern, optional `-run` filter) | Streamed JSON event Native Result (one event per line) with run, pass, fail, output events |
| `go test -list <regex> <package_pattern>` | Native CLI (`go test`) | Test Target | Native test discovery listing |
| `go test -coverprofile=<path> -covermode=atomic <package_pattern>` | Native CLI (`go test`) | Test Target | Coverage profile Native Result feeding Coverage Fact derivation |

### 2.5 Rust - `cargo test`

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `cargo test <filter> -- --format=json -Z unstable-options` | Native CLI (`cargo test` / libtest, nightly JSON) | Test Target (filter expression) | JSON Native Result with libtest events |
| `cargo test -- --list` | Native CLI (`cargo test`) | Test Target | Native test discovery listing |
| `cargo llvm-cov --json --output-path=<path>` | Native CLI (`cargo-llvm-cov`) | Test Target | JSON coverage Native Result feeding Coverage Fact derivation |

### 2.6 .NET / C# - xUnit (via `dotnet test`)

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `dotnet test <project> --filter <expr> --logger "trx;LogFileName=<path>"` | Native CLI (`dotnet test` over xUnit) | Test Target (project path plus xUnit `--filter` expression) | TRX XML Native Result with per-test outcomes, durations, failure references |
| `dotnet test <project> --list-tests` | Native CLI (`dotnet test`) | Test Target | Native test discovery listing |
| `dotnet test <project> --collect:"XPlat Code Coverage"` | Native CLI (`dotnet test` + Coverlet) | Test Target | Cobertura XML coverage Native Result feeding Coverage Fact derivation |

---

## Notes

- Section 1 interfaces are the only Run surfaces other Nove Test engines depend on; Section 2 lists external Native Engine commands that Run invokes on their behalf.
- Native Engine interfaces preserved here intentionally cover discovery, execution, and tightly-coupled coverage emission so that Run can produce Native Results that downstream sub-products (Memory, Coverage) can consume.
- Run does not own the semantics of any Section 2 interface; the Native Engine remains the source of truth (NFR-RUN-001).
