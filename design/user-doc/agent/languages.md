# Per-Language Notes (Agent)

The canonical happy path in [quick-start.md](./quick-start.md) is
language-agnostic — same envelope shape, same recommendation taxonomy.
This page documents only **what differs** per language: detection
markers, the `(ecosystem, engine_name)` identifier pair, the external
command each adapter invokes (shown simplified — coverage runs add a few
extra flags), the per-test ID convention, and whether coverage facts are
produced.

`novetest` auto-detects the engine from workspace markers. You **do
not** pass an `--engine` flag. The detected pair appears as
`data.engine_readiness.ecosystem` + `data.engine_readiness.engine` on
the `init` envelope, and as `data.memory_entry.run_record.engine_name`
+ `…ecosystem` on every run. Pin `NOVETEST_OUTPUT=json` for stable
machine output.

## The six supported pairs

`engine_name` is verbatim — note `go-test`, `cargo-test`, and `xunit`
(the .NET engine is named `xunit`, the ecosystem is `dotnet`):

| `ecosystem` | `engine_name` | Markers | Coverage facts |
|---|---|---|---|
| `python` | `pytest` | `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini` | yes |
| `javascript-typescript` | `jest` | `package.json` | yes |
| `java` | `junit` (JUnit 5 Jupiter only) | `pom.xml`, `build.gradle`, `build.gradle.kts` | yes |
| `go` | `go-test` | `go.mod` | **no** |
| `rust` | `cargo-test` (nextest required) | `Cargo.toml` | yes |
| `dotnet` | `xunit` (xUnit v2 only) | `*.csproj` (root + 1-deep glob), `*.sln` | yes |

Do **not** emit `engine_name` values like `go`, `cargo`, `dotnet`,
`cargo-nextest`, or `nunit`/`mstest`/`testng`/`junit4` — they never
occur. Java rejects JUnit 4 and TestNG; .NET rejects MSTest and NUnit;
Rust requires `cargo-nextest` (no plain `cargo test`).

## Detection priority (single-engine at MVP)

`novetest test` runs **one engine at a time**. When several ecosystems
match the same workspace root, readiness disambiguates with a fixed
priority:

```
pytest > jest > go-test > cargo-test > junit > xunit
```

A repo with both `pyproject.toml` and `package.json` always routes to
**pytest**; the other matches are ignored at that invocation. There is
no single-envelope polyglot orchestration at MVP — use one
`.novetest/` per ecosystem subdirectory.

### Polyglot: one `.novetest/` per ecosystem subdirectory

```
polyglot-repo/
├── backend/
│   ├── pyproject.toml
│   └── .novetest/        ← `cd backend && novetest init`
└── frontend/
    ├── package.json
    └── .novetest/        ← `cd frontend && novetest init`
```

Two independent stores; two independent invocations. The walk-up rule
from
[quick-start.md](./quick-start.md#where-to-run-subsequent-verbs-from)
guarantees `novetest test` from `backend/tests/` finds
`backend/.novetest/`, not the frontend one.

## Toolchain prerequisites

| `engine_name` | PATH requirements | Coverage tool |
|---|---|---|
| `pytest` | `pytest` + `pytest-json-report` importable from novetest's interpreter | `pytest-cov` |
| `jest` | Node.js ≥ 18 (`node` **and** `npx`) + workspace-local jest | jest built-in (Istanbul) |
| `go-test` | Go ≥ 1.21 (`go`) | — (not consumed) |
| `cargo-test` | `cargo` + `cargo-nextest` ≥ 0.9.50 (mandatory) + `cargo-llvm-cov` | `cargo-llvm-cov` (LCOV) |
| `junit` | JDK ≥ 17 + Maven ≥ 3.9 OR Gradle ≥ 7.6/wrapper + JUnit 5 Jupiter | JaCoCo (XML) |
| `xunit` | .NET SDK ≥ 8.0 + xUnit v2 + `coverlet.collector` ≥ 6.0.2 (coverage only) | Coverlet (Cobertura XML) |

Missing toolchain → `init` records
`data.engine_readiness.state` ∈ {`"engine-missing"`,
`"engine-misconfigured"`} (with hints in
`engine_readiness.issues[]`) but `init` still exits 0. A subsequent
`novetest run`/`novetest test` then exits **4** with
`errors[0].code = "engine-engine-missing"` (or
`"engine-engine-misconfigured"`). See the readiness section below for
the exact envelope.

---

## pytest (`python` / `pytest`)

The **baseline**; see [quick-start.md](./quick-start.md).

- **Markers:** `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini`.
  Readiness *additionally* requires a pytest config: `pytest.ini`,
  `conftest.py`, a `tests/` dir, `[tool.pytest.ini_options]` in
  `pyproject.toml`, or `[tool:pytest]` in `setup.cfg`. None → state
  `engine-missing`, issue `"Python workspace detected but no pytest
  configuration (pytest.ini, [tool.pytest.ini_options], conftest.py,
  or tests/ dir) found"`.
- **External command:**
  `<sys.executable> -m pytest -p pytest_jsonreport --json-report
  --json-report-file=<artifacts>/native/pytest-report.json -q [<target>]`.
  Uses novetest's own interpreter, not a `pytest` on PATH;
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- **Coverage:** `coverage_json` (+`coverage_xml`), collected with
  `--cov-context=test` (enables per-test SBFL).
- **node_id:** `tests/test_arithmetic.py::test_subtract`.
- **Misconfig messages:** pytest not importable →
  `engine-misconfigured` `"pytest is not importable from the resolved
  interpreter; install with: pip install pytest"`; plugin missing →
  `"pytest-json-report plugin is not importable; install with:
  pip install pytest-json-report"`.

---

## jest (`javascript-typescript` / `jest`)

- **Marker:** `package.json`. Readiness: `node` **and** `npx` on PATH;
  jest declared in `dependencies`/`devDependencies` or installed at
  `node_modules/.bin/jest`.
- **External command:**
  `npx jest --ci --json --testLocationInResults
  --outputFile=<artifacts>/native/jest-results.json --reporters=default
  --watchman=false [<target>]` (Windows launcher: `cmd /c npx …`).
  No plugin isolation; workspace `jest.config.js` honored as written.
- **Coverage:** Istanbul `coverage_json`
  (`--coverage --coverageReporters=json`).
- **node_id:** `<file>::<ancestors>::<title>`.
- **Misconfig messages:** no node/npx → `engine-missing`
  `"Node.js (\`node\`/\`npx\`) not found on PATH; install Node.js >=18
  …"`; jest absent → `engine-misconfigured`
  `"jest not found in package.json … install with: npm install
  --save-dev jest"`; declared-but-not-installed →
  `"jest is declared in package.json but not installed; run:
  npm install"`.

---

## go-test (`go` / `go-test`)

- **Marker:** `go.mod`. Readiness: `go` on PATH and `go version`
  exits 0. Default target `./...`.
- **External command:**
  `go test -json -count=1 -timeout=<seconds>s [coverage flags] <target>`.
- **Coverage facts: NONE.** The adapter writes a `cover.out` profile
  under artifact key `coverage_profile`, but the coverage engine reads
  `coverage_json`, so `novetest run --coverage` on Go yields
  `data.coverage_outcome` with `kind="unavailable"` and detail
  `"RunRecord.artifact_paths has no 'coverage_json' entry; this run was
  executed without coverage collection"`. Treat go-test as
  **execution-only** for coverage routing.
- **node_id:** `<package>::<test>`.

---

## cargo-test (`rust` / `cargo-test`)

- **Marker:** `Cargo.toml`. Readiness: `cargo` on PATH **and**
  `cargo nextest --version` succeeds (load-bearing gate — absence →
  `engine-misconfigured` `"\`cargo nextest\` is not installed …
  Install with: cargo install cargo-nextest --locked"`). No plain
  `cargo test` fallback. Coverage additionally needs `cargo-llvm-cov`.
- **External command** (mutually exclusive):
  non-coverage `cargo nextest run --message-format=libtest-json
  --no-fail-fast --workspace [<filter>]`; coverage
  `cargo llvm-cov nextest --lcov --output-path … --ignore-run-fail
  --workspace --message-format=libtest-json`. A directory target does
  NOT append a filter token. `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` is
  set in the child env.
- **Coverage:** `coverage_lcov`. `metadata.nextest_version` is on the
  Run Record (e.g. `0.9.137`); `engine_version` is cargo itself.
- **node_id:** the nextest test name directly.

---

## junit (`java` / `junit`) — JUnit 5 Jupiter only

- **Markers / build tool:** `pom.xml` → Maven; `build.gradle{,.kts}` →
  Gradle; **both present → Maven wins** with an `ambiguous-build-tool`
  warning.
- **Readiness gates (in order):** Windows host → `engine-misconfigured`
  (unsupported); build tool resolvable; `java` on PATH (else
  `engine-misconfigured` `"\`java\` not found on PATH; install JDK
  17+"`); `mvn`/`gradle`/`./gradlew`; JUnit Jupiter declared; **JUnit 4
  detected → `engine-misconfigured`; TestNG detected →
  `engine-misconfigured`** (JUnit 5 only).
- **External command:** Maven `mvn -B test [jacoco:report]
  -Dsurefire.reportFormat=plain -Dsurefire.useFile=false
  [-Dtest=<filter>]`; Gradle `./gradlew test --no-daemon
  [--tests <filter>] [jacocoTestReport]`.
- **Coverage:** JaCoCo `coverage_xml`. Warning codes:
  `ambiguous-build-tool`, `missing-jacoco` (coverage requested but
  JaCoCo not declared → coverage degrades).
- **engine_version caveat:** Maven extracts it (`"5.10.2"`); the
  **Gradle path commonly reports `engine_version: null`**. Don't rely
  on a non-null Java engine_version.

---

## xunit (`dotnet` / `xunit`) — xUnit v2 only

- **Detection:** GLOB — `*.csproj` at root or one directory deep, or
  `*.sln` at root. The first csproj whose name contains "test" is the
  test project; it must declare `<PackageReference Include="xunit">`.
- **Readiness:** `dotnet` on PATH (else `engine-missing`); a `*.csproj`
  must exist; **MSTest detected → `engine-misconfigured` "…supports
  xUnit v2 only"; NUnit detected → `engine-misconfigured`.** xUnit
  **v3** → state stays `ready` but a runtime warning
  (`xunit-v3-coverage-deferred`) defers coverage. Coverlet is **not** a
  readiness gate.
- **External command:** `dotnet test <csproj>
  --logger "trx;LogFileName=results.trx" --results-directory <dir>
  [--collect:"XPlat Code Coverage" --settings <runsettings>]
  [--filter "FullyQualifiedName~<target>"]`; coverage runs do
  `dotnet restore <csproj>` first.
- **Coverage:** Coverlet Cobertura `coverage_xml` (requires
  `coverlet.collector` ≥ 6.0.2; below floor → degrades with a warning
  whose `code` is the literal `engine-misconfigured`). Other warning
  codes: `ambiguous-project-layout`.

---

## Readiness states & the engine-missing envelope

`data.engine_readiness.state` ∈ {`"ready"`, `"engine-missing"`,
`"engine-misconfigured"`} (there is **no** `engine-not-ready`
readiness state). `init` always exits 0 regardless of state. The run
verbs gate on readiness and exit **4** if it is not `ready`. Real
`novetest run` against a Python workspace with no pytest config:

```json
{
  "command": "run",
  "data": {
    "engine_readiness": {
      "ecosystem": null,
      "engine": null,
      "engine_version": null,
      "evidence": [
        "pyproject.toml"
      ],
      "issues": [
        "Python workspace detected but no pytest configuration (pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found"
      ],
      "state": "engine-missing"
    }
  },
  "errors": [
    {
      "code": "engine-engine-missing",
      "details": {},
      "message": "engine readiness state: engine-missing (engine=(none detected))"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

(exit 4)

`engine_readiness` keys: `ecosystem`, `engine`, `engine_version`,
`evidence` (array of detected marker filenames), `issues` (array),
`state`. The error `code` is the doubled-prefix
`engine-engine-missing` (`engine-` + the state `engine-missing`); a
misconfigured engine produces `engine-engine-misconfigured`, also exit
4. Adapter-level failures (e.g. an unparseable report) instead exit 4
with `errors[0].code = "adapter-<kind>"`, where `<kind>` is a stable
token such as `missing-plugin`, `missing-binary`, `missing-engine`,
`unparseable-output`, `misconfigured-environment`, or `timed-out` (the
exact set varies by engine — match the `adapter-` prefix, not a fixed
list).

### Agent routing

- `data.engine_readiness.state != "ready"` on a run verb → exit 4,
  `ok:false`. Read `engine_readiness.issues[]` /
  `errors[0].details.install_hint` for the fix.
- `engine_name == "go-test"` → do **not** expect coverage; route
  coverage-dependent logic around it.
- Treat `run_record.test_results[].node_id` as an opaque string keyed
  off `engine_name` — its format differs per engine (e.g.
  `tests/test_arithmetic.py::test_subtract` for pytest vs
  `<package>::<test>` for go-test). Do not parse it cross-engine.
- `data.recommendations[].category` and `data.stage_eligibility.*`
  come from closed taxonomies shared by all engines
  (`stage_eligibility.localization` is the SBFL mode string when
  available; `stage_eligibility.replay` is always `not_run`).
