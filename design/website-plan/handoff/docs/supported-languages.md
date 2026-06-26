# Supported Languages

The canonical happy path in [Quick Start](./quick-start.md) is
language-agnostic. This page documents only **what differs per
language**: detection markers, the `(ecosystem, engine)` identifier
pair, the toolchain you need on PATH, the external command the adapter
invokes (shown simplified — coverage runs add a few extra flags), and
whether coverage is available.

`novetest` auto-detects which engine your project uses from workspace
markers. **You do not pass an `--engine` flag.**

---

## The six supported engines

`novetest` ships six fully-wired native engine adapters. The `engine`
string is exactly what appears as `engine_name` on your Run Record —
note `go-test`, `cargo-test`, and `xunit` (the .NET engine is named
`xunit`, not `dotnet`):

| `ecosystem` | `engine` | Marker(s) | Coverage |
|---|---|---|---|
| `python` | `pytest` | `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini` | yes |
| `javascript-typescript` | `jest` | `package.json` | yes |
| `java` | `junit` (JUnit 5 Jupiter **only**) | `pom.xml`, `build.gradle`, `build.gradle.kts` | yes |
| `go` | `go-test` | `go.mod` | **no** |
| `rust` | `cargo-test` (nextest **required**) | `Cargo.toml` | yes |
| `dotnet` | `xunit` (xUnit v2 **only**) | `*.csproj` (root + 1-deep glob), `*.sln` | yes |

Java is **JUnit 5 Jupiter only** — JUnit 4 and TestNG are explicitly
rejected. .NET is **xUnit v2 only** — MSTest and NUnit are explicitly
rejected. Rust **requires `cargo-nextest`** — there is no plain
`cargo test` fallback. **`go test` runs, but its coverage is not
consumed** (see the gotest section).

---

## Detection priority — one engine at a time

`novetest test` (and every other non-`init` verb) runs **one engine at
a time**. When a polyglot repo matches several ecosystems at the same
root, readiness disambiguates with a fixed priority:

```
pytest > jest > go-test > cargo-test > junit > xunit
```

::: tabs
@tab For human

If your workspace root has both `pyproject.toml` AND `package.json`,
`novetest test` from that root will only run **pytest** — the
JavaScript suite is silently ignored. This is by design at MVP (the
single-engine assumption is baked into the Run Record schema and
every downstream engine).

@tab For agent

A repo with both `pyproject.toml` and `package.json` always routes to
**pytest**; the other matches are ignored at that invocation. There is
no single-envelope polyglot orchestration at MVP. The detected pair is
exposed on the `init` envelope as
`data.engine_readiness.ecosystem` + `data.engine_readiness.engine`
(and on each run as `…run_record.engine_name` + `…ecosystem`).

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

```bash
( cd backend  && novetest test )   # runs pytest only
( cd frontend && novetest test )   # runs jest only
```

Each subdirectory's `.novetest/` carries its own run history, coverage
facts, regression baselines, and SBFL findings — completely isolated.
The walk-up rule from
[Quick Start -> Where do I run `novetest test` from?](./quick-start.md#where-do-i-run-novetest-test-from)
guarantees that `novetest test` from `backend/tests/` finds
`backend/.novetest/`, not the frontend one.

---

## Quick toolchain matrix

| Engine | What must be on PATH | Coverage tool |
|---|---|---|
| `pytest` | `pytest` + `pytest-json-report` importable from novetest's interpreter | `pytest-cov` |
| `jest` | Node.js ≥ 18 (`node` **and** `npx`) + workspace-local jest | jest built-in (Istanbul) |
| `go-test` | Go ≥ 1.21 (`go`) | — (not consumed) |
| `cargo-test` | Rust toolchain + `cargo-nextest` ≥ 0.9.50 (mandatory) + `cargo-llvm-cov` (coverage) | `cargo-llvm-cov` (LCOV) |
| `junit` | JDK ≥ 17 + Maven ≥ 3.9 OR Gradle ≥ 7.6/wrapper; JUnit 5 Jupiter in deps | JaCoCo (XML) |
| `xunit` | .NET SDK ≥ 8.0; xUnit v2 in test project | `coverlet.collector` ≥ 6.0.2 |

`novetest init` never fails on a bad engine — it records the readiness
state and moves on.

::: tabs
@tab For human

If a toolchain piece is missing, `novetest init` reports it on the
`engine readiness:` line. The next `novetest test`/`novetest run`
exits **4** until you fix the host. For example, a Python workspace
with no pytest config:

```
✗ run
  engine-engine-missing: engine readiness state: engine-missing (engine=(none detected))
```

(exit 4)

@tab For agent

Missing toolchain → `init` records
`data.engine_readiness.state` ∈ {`"engine-missing"`,
`"engine-misconfigured"`} (hints in `engine_readiness.issues[]`) but
`init` still exits 0. A subsequent run verb exits **4** with
`errors[0].code = "engine-engine-missing"` (or
`"engine-engine-misconfigured"`). Real `novetest run` against a Python
workspace with no pytest config:

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

(exit 4). The error `code` is the doubled-prefix
`engine-engine-missing` (`engine-` + the state `engine-missing`).
There is **no** `engine-not-ready` readiness state.

:::

---

## pytest (Python)

This is the **baseline** used in [Quick Start](./quick-start.md).

Markers: `pyproject.toml`, `setup.py`, `setup.cfg`, `pytest.ini`.
Readiness **additionally** requires a pytest config — one of
`pytest.ini`, `conftest.py`, a `tests/` dir,
`[tool.pytest.ini_options]` in `pyproject.toml`, or `[tool:pytest]` in
`setup.cfg`. A Python workspace with none reports `engine-missing`.

The external command uses **novetest's own interpreter**, not a
`pytest` on PATH, and disables plugin autoload:

```
<python> -m pytest -p pytest_jsonreport --json-report
  --json-report-file=<artifacts>/native/pytest-report.json -q [<target>]
```

Coverage is JSON via `pytest-cov`, collected with `--cov-context=test`
(enabling per-test SBFL). Node-id form:
`tests/test_arithmetic.py::test_subtract`.

::: tabs
@tab For human

Project skeleton (the canonical `calc` example):

```
calc-demo/
├── pyproject.toml          # [tool.pytest.ini_options] testpaths=["tests"]
├── calc/
│   ├── __init__.py
│   └── arithmetic.py
└── tests/
    └── test_arithmetic.py
```

```bash
cd calc-demo
novetest init
```
```
✓ Initialized .novetest/ at /abs/path/to/calc-demo/.novetest
  engine readiness: ready — python/pytest 9.0.3
```

(The pytest version is *your* project's pytest, not a
novetest-controlled constant. novetest's own version is `0.1.2`.)

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest init
```

`data.engine_readiness` for a ready calc project:

```json
{
  "ecosystem": "python",
  "engine": "pytest",
  "engine_version": "9.0.3",
  "evidence": [
    "pyproject.toml"
  ],
  "issues": [],
  "state": "ready"
}
```

Misconfig messages: pytest not importable → `engine-misconfigured`
`"pytest is not importable from the resolved interpreter; install
with: pip install pytest"`; plugin missing →
`"pytest-json-report plugin is not importable; install with:
pip install pytest-json-report"`.

:::

---

## jest (JavaScript / TypeScript)

Marker: `package.json`. Readiness requires `node` **and** `npx` on
PATH, plus jest declared in `dependencies`/`devDependencies` or
installed at `node_modules/.bin/jest`. Node.js ≥ 18.

External command (Windows launcher is `cmd /c npx …`):

```
npx jest --ci --json --testLocationInResults
  --outputFile=<artifacts>/native/jest-results.json
  --reporters=default --watchman=false [<target>]
```

Unlike pytest, jest has no plugin isolation — your workspace
`jest.config.js` is honored as written. Coverage is Istanbul JSON
(`--coverage --coverageReporters=json`). Node-id form:
`<file>::<ancestors>::<title>`.

::: tabs
@tab For human

```
my-js-project/
├── package.json            # jest in devDependencies
├── src/
│   └── math.js
└── __tests__/
    └── math.test.js
```

If `node`/`npx` are missing readiness is `engine-missing`; if jest is
absent it is `engine-misconfigured` with a `npm install --save-dev
jest` hint.

@tab For agent

Readiness messages: no node/npx → `engine-missing`
`"Node.js (\`node\`/\`npx\`) not found on PATH; install Node.js >=18
…"`; jest absent → `engine-misconfigured`
`"jest not found in package.json … install with: npm install
--save-dev jest"`; declared-but-not-installed →
`"jest is declared in package.json but not installed; run: npm
install"`.

:::

---

## gotest (Go / `go test`)

Marker: `go.mod`. Readiness needs `go` on PATH and a working
`go version`. Default target `./...` (every package in the module).

External command (`-count=1` disables Go's result cache):

```
go test -json -count=1 -timeout=<seconds>s [coverage flags] <target>
```

**Coverage is NOT consumed.** `go test` runs fine, but `novetest run
--coverage` on a Go project produces no coverage facts: the adapter
writes a Go `cover.out` profile under a different artifact key than the
coverage engine reads. Node-id form: `<package>::<test>`.

::: tabs
@tab For human

Coverage runs complete, but the coverage line reports unavailable
("this run was executed without coverage collection"). Test execution
works; coverage facts do not.

@tab For agent

`novetest run --coverage` returns `data.coverage_outcome` with
`kind="unavailable"` and detail
`"RunRecord.artifact_paths has no 'coverage_json' entry; this run was
executed without coverage collection"`. Route coverage-dependent logic
around `engine_name == "go-test"`.

:::

---

## cargo (Rust / `cargo nextest`)

Marker: `Cargo.toml`. The default target is the workspace.

The adapter **requires** `cargo nextest` — a successful
`cargo nextest --version` is a load-bearing readiness gate; missing it
→ `engine-misconfigured`. There is **no** fallback to plain
`cargo test`. Coverage additionally needs `cargo-llvm-cov`.

```bash
rustup install stable
cargo install cargo-nextest --locked    # MANDATORY — no fallback
cargo install cargo-llvm-cov            # required for coverage
```

Non-coverage and coverage runs use **different, mutually-exclusive**
invocations:

```
# non-coverage:
cargo nextest run --message-format=libtest-json --no-fail-fast --workspace [<filter>]
# coverage:
cargo llvm-cov nextest --lcov --output-path <artifacts>/native/coverage.lcov
  --ignore-run-fail --workspace --message-format=libtest-json
```

`--ignore-run-fail` emits the LCOV even when tests fail. A *directory*
target (`novetest test .`) does NOT append a filter token (nextest
treats positionals as filter expressions, not paths). Coverage is
LCOV. Node-id is the nextest test name directly.

---

## junit (Java / JUnit 5 Jupiter)

JUnit 5 Jupiter is the **only** supported framework — **JUnit 4 and
TestNG are detected and rejected** as `engine-misconfigured`. Windows
hosts are unsupported for JUnit (rejected as `engine-misconfigured`).

Markers: `pom.xml` (→ Maven) or `build.gradle{,.kts}` (→ Gradle). When
**both** are present, Maven wins and an `ambiguous-build-tool` warning
is emitted in `envelope.warnings[]`.

Readiness gates, in order: Windows → reject; build tool resolvable;
`java` on PATH (else `"\`java\` not found on PATH; install JDK 17+"`);
`mvn`/`gradle`/`./gradlew`; JUnit Jupiter declared; JUnit 4 → reject;
TestNG → reject.

External command:

```
# Maven:
mvn -B test [jacoco:report] -Dsurefire.reportFormat=plain
  -Dsurefire.useFile=false [-Dtest=<filter>]
# Gradle:
./gradlew test --no-daemon [--tests <filter>] [jacocoTestReport]
```

Coverage is JaCoCo XML; requesting `--coverage` without JaCoCo wired in
emits a `missing-jacoco` warning and coverage degrades.

::: tabs
@tab For human

Project skeleton (Maven): `pom.xml` declaring
`org.junit.jupiter:junit-jupiter` (test scope) +
`src/{main,test}/java/…`. Gradle is the same with `build.gradle`
declaring the Jupiter dependency and `useJUnitPlatform()`. Toolchain:
JDK ≥ 17 plus Maven ≥ 3.9 or Gradle ≥ 7.6 (the `./gradlew` wrapper is
honored).

@tab For agent

On the **Maven** path `engine_version` is extracted (e.g.
`"5.10.2"`); on the **Gradle** path it is commonly `null` (the
Jupiter-version regex frequently can't extract it). Don't rely on a
non-null Java `engine_version`.

:::

---

## xunit (.NET / xUnit v2)

xUnit v2 is the **only** supported framework — **MSTest and NUnit are
detected and rejected** as `engine-misconfigured` ("…supports xUnit v2
only"). xUnit **v3** runs, but coverage is deferred with a warning
(`xunit-v3-coverage-deferred`).

Detection is by **glob**: `*.csproj` at the root or one directory
deep, or `*.sln` at the root. novetest picks the first csproj whose
name contains "test"; it must declare
`<PackageReference Include="xunit">`.

Toolchain: .NET SDK ≥ 8.0 (`dotnet` on PATH). For coverage only:
`coverlet.collector` ≥ 6.0.2 — **Coverlet is not a readiness gate**, so
bare `novetest run` works without it.

External command (coverage runs `dotnet restore <csproj>` first):

```
dotnet test <csproj> --logger "trx;LogFileName=results.trx"
  --results-directory <results>
  [--collect:"XPlat Code Coverage" --settings <runsettings>]
  [--filter "FullyQualifiedName~<target>"]
```

Coverage is Cobertura XML via Coverlet, using a per-run hermetic
runsettings (your own runsettings are never modified). If Coverlet is
absent or below 6.0.2, coverage degrades with a warning.

::: tabs
@tab For human

Project skeleton:

```
my-dotnet-project/
├── MathLib/
│   ├── MathLib.csproj
│   └── Math.cs
└── MathLib.Tests/
    ├── MathLib.Tests.csproj    # PackageReference Include="xunit"
    └── MathTests.cs
```

@tab For agent

Warning codes: `xunit-v3-coverage-deferred`,
`ambiguous-project-layout`, and Coverlet absent/below-floor warnings
whose `code` is the literal `engine-misconfigured` (a string that
collides with the readiness state name — don't assume warning codes
are disjoint from state names).

:::

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

The output shape is the same across all six engines. Only the per-test
identity strings and the coverage format differ; the orchestration
layer normalizes those so results stay language-agnostic. The one
capability difference: **coverage is available for pytest, jest,
junit, xunit, and cargo-test — but not for go-test.**

::: tabs
@tab For human

The text-mode output shape
(`<glyph> [<category>] <sentence>\n  ↳ <citation>`) is identical across
engines.

@tab For agent

Your agent can rely on:

- `data.run_reference.run_id` is a ULID, format-stable across engines.
- `data.recommendations[].category` comes from a closed taxonomy
  shared by all engines.
- `data.stage_eligibility.localization` is the SBFL mode string when
  available; `data.stage_eligibility.replay` is always `not_run`.

Treat `run_record.test_results[].node_id` as an opaque string keyed
off `engine_name` — its format differs per engine (e.g.
`tests/test_arithmetic.py::test_subtract` for pytest vs
`<package>::<test>` for go-test). Do not parse it cross-engine.

:::

---

## What to read next

- **[Quick Start](./quick-start.md)** — re-read with your language's
  toolchain in mind.
- **[Understanding Results](./understanding-results.md)** — the
  same recommendation taxonomy applies regardless of engine.
- **[Troubleshooting](./troubleshooting.md)** — per-engine errors
  and their one-line fixes.
