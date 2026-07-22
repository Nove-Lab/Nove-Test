# Per-Language Notes (Agent)

The canonical happy path in [quick-start.md](./quick-start.md) is
language-agnostic — same envelope shape, same recommendation taxonomy.
This page documents only **what differs** per language: detection
markers, the `(ecosystem, engine_name)` identifier pair, the external
command each adapter invokes (shown simplified — coverage runs add a few
extra flags), the per-test ID convention, and whether coverage facts are
produced.

`novetest init` detects the engine from workspace markers and **pins**
it into the Project Store; every later verb runs the pinned engine —
nothing is re-detected at run time. The pin appears as
`data.pinned_engine` (`{"ecosystem": …, "engine_name": …}`) on the
`init` and `status` envelopes, alongside the existing
`data.engine_readiness.*` fields; each run still carries
`data.memory_entry.run_record.engine_name` + `…ecosystem`. Pin
`NOVETEST_OUTPUT=json` for stable machine output.

`--engine <name>` exists in exactly two places — route on the error
codes below, do not guess:

- `novetest init --engine <name>` — required only when `init` refuses
  with `engine-ambiguous`; also re-pins an existing store in place
  (run history retained).
- `novetest test|run --engine <name>` — one-off override for a single
  invocation; the pin is NOT changed. Invalid value on any verb →
  `invalid-flag`, exit 2.

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

## Engine selection (the anchored pin — no run-time detection)

`novetest test` runs **one engine at a time**: the pinned one. `init`
outcomes to route on:

| `init` situation | Exit | Envelope | Your move |
|---|---|---|---|
| Exactly one viable engine | 0 | `data.pinned_engine` set | proceed |
| No marker at this directory | 4 | `errors[0].code = "no-engine-detected"`; `data.candidates[]` = `[{ecosystem, engine_name, path}]` (bounded scan: depth ≤ 2, vendor dirs skipped; `data.scan_refused: true` at `/` and `$HOME`) | `cd` into each candidate `path` and run `init` there. **Nothing was created.** |
| ≥ 2 viable engines (or ≥ 2 markers with zero toolchains ready) | 2 | `errors[0].code = "engine-ambiguous"`; `data.candidates[]` | re-run `novetest init --engine <name>`. **Nothing was created.** |

"Viable" = marker present AND toolchain-READY. A `pyproject.toml` +
tooling-only `package.json` root (jest not installed) pins `pytest`
silently — the same repo can therefore init cleanly on one host and
return `engine-ambiguous` on another. Never cache init outcomes across
machines.

Legacy pin-less stores: the first **execution** verb (`run` / `test`)
backfills `pinned_engine` silently when unambiguous, or exits 2 with
`engine-ambiguous` (instructing re-init) when not. Read-only verbs
(`status`, `memory ...`, `inspect`, `coverage show`,
`regression compare/latest`, `localization <run_id>/latest`, `compare`)
neither backfill nor
refuse — they proceed engine-less (exit 0) over a legacy store and write
nothing. `reset --confirm` re-inits **at the anchor** and carries the
pin; on an ambiguous pin-less store it refuses with `engine-ambiguous`
and wipes nothing.

There is no single-envelope polyglot orchestration at MVP — use one
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
`errors[0].code = "engine-missing"` (or `"engine-misconfigured"` — the
code is the readiness state verbatim). See the readiness section below
for the exact envelope.

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
  `<resolved python> -m pytest -p pytest_jsonreport --json-report
  --json-report-file=<artifacts>/native/pytest-report.json -q [<target>]`.
  Never a `pytest` on PATH; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- **Interpreter resolution (venv-first, two tiers, no PATH tier):**
  1. `<workspace>/.venv` when its pytest console script exists
     (`.venv/bin/pytest`, or `.venv\Scripts\pytest.exe` on Windows) →
     that venv's `python`;
  2. otherwise `sys.executable` (the interpreter running novetest).
  Readiness probes the **same** resolved interpreter it will run, and
  `engine_version` reports that interpreter's pytest. So `pytest` +
  `pytest-json-report` (+ `pytest-cov` for coverage runs) must be
  importable from the workspace `.venv` if it has one, else from
  novetest's own interpreter. Under the standalone-binary install
  (`curl … | sh`) `sys.executable` is a sealed CPython that cannot be
  installed into — a workspace `.venv` is the only route there.
- **Coverage:** `coverage_json` (+`coverage_xml`), collected with
  `--cov-context=test` (enables per-test SBFL).
- **node_id:** `tests/test_arithmetic.py::test_subtract`.
- **Misconfig messages** (both name the resolved interpreter and the
  `.venv` remediation): pytest not importable → `engine-misconfigured`
  `"pytest is not importable from the resolved interpreter
  (<interpreter>); install pytest, pytest-json-report and pytest-cov into
  <workspace>/.venv (novetest prefers the workspace's own .venv over its
  interpreter; pytest-cov is what the coverage-collecting verbs such as
  \`novetest test\` additionally need) — from <workspace> run: python3 -m
  venv .venv && .venv/bin/python -m pip install pytest pytest-json-report
  pytest-cov"`; plugin missing → the same text with `"pytest-json-report
  plugin is not importable from the resolved interpreter
  (<interpreter>); …"`. Readiness itself gates only on pytest +
  pytest-json-report; a missing `pytest-cov` surfaces later as
  `adapter-missing-plugin` (exit 4) on a coverage-collecting run, so the
  hint installs all three at once.

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
- **node_id:** `<workspace-relative POSIX file>::<ancestors>::<title>`.
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
  `coverlet.collector` ≥ 6.0.2; below floor → degrades with a
  `coverlet-below-floor` warning; absent → `coverlet-absent`, coverage
  not collected). Other warning codes: `ambiguous-project-layout`.

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
      "code": "engine-missing",
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
`state`. The error `code` is the readiness state **verbatim** —
`engine-missing`, or `engine-misconfigured` for a misconfigured engine,
also exit 4 (the code IS the state, with no extra prefix). Engine-level
adapter failures (e.g. an unparseable report) instead exit 4 with
`errors[0].code = "adapter-<kind>"`, where `<kind>` is a stable token
such as `missing-plugin`, `missing-binary`, `missing-engine`,
`unparseable-output`, `misconfigured-environment`, or `timed-out` (the
exact set varies by engine — match the `adapter-` prefix, not a fixed
list). The one exception is `adapter-invalid-target` — a dash-/flag-/
metacharacter-shaped target rejected at the boundary is a caller **usage
error** and exits **2**, not 4.

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
