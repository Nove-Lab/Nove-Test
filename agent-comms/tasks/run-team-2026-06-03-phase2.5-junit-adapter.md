---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-03
slug: phase2.5-junit-adapter
status: pending
related:
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/engine-adapters.md
  - design/interace-contract/run.md
  - design/interace-contract/coverage.md
  - design/workflows/run.md
  - design/requirements-analysis/requirements-specification/groups/run.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - scripts/dev-host-setup.md
---

# Phase 2.5 — Java + JUnit 5 adapter (`junit_adapter.py`)

## TL;DR

Add the fifth Run engine adapter to bring `novetest run` from
**4 ecosystems (pytest / jest / gotest / cargo) to 5** by implementing
the Java + JUnit 5 path:

- `src/novetest/run/adapters/junit_adapter.py` — `run_junit()` async
  invocation function, parallel to the four existing adapters.
- `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
  — vendored Console Launcher (the **first vendored asset** in the
  project; establishes the pattern for any future vendored adapter
  helpers per
  [`decisions/2026-06-03-junit-console-launcher-vendor.md`](../decisions/2026-06-03-junit-console-launcher-vendor.md)).
- `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` — EPL 2.0
  attribution for the vendored jar.
- `pyproject.toml` package-data inclusion of the `_vendor/` tree.
- `src/novetest/run/engine.py` dispatch branch for `engine_name == "junit"`.
- `src/novetest/run/readiness.py` JUnit detection (Maven `pom.xml` /
  Gradle `build.gradle{,.kts}` markers + `java` / `mvn` / `gradle` PATH
  probes).
- `src/novetest/coverage/derive.py` new dispatch branch + JaCoCo XML
  parser (`_derive_junit_jacoco()`) emitting CoverageFacts with
  `mapping_granularity: aggregate` (default) or `per-test-class` (opt-in
  via `--per-test-class`; see §6 D1).
- `tests/fixtures/projects/junit-maven-basic/` + `junit-gradle-basic/`
  — controlled SuT projects (deterministic, no novetest imports).
- `tests/unit/run/adapters/test_junit_adapter.py` + `tests/integration/
  run/test_junit_*.py` — adapter unit tests + real-CLI integration
  tests that probe Maven Surefire AND Gradle paths with `shutil.which`
  skip gates.
- `tests/integration/run/test_junit_vendored_launcher.py` — **load-bearing
  R4 mitigation**: validates that `importlib.resources` can resolve the
  vendored jar AND that `java -jar <resolved_jar> --version` succeeds in
  the test environment (the precursor to PyApp binary blob extraction
  verification — full PyApp verification is its own DoD bullet covered
  by the Release team smoke at handoff).
- `scripts/dev-host-setup.md` §5 was filled in the 2026-06-03 cleanup
  commit (`0c72a68`); this slice equips the host per that section.

**Closes 1 DoD bullet at `delivery-phasing.md`** Phase 2.5 (the JUnit
adapter bullet — see §11). After this slice, **MVP scope reduces to**:
.NET adapter (1 cycle, Open Q #4 already closed) + B1/B2 polish work +
Phase 7 MCP (post-MVP, out of MVP scope per CEO 2026-06-03 decision).

## Product framing

Before this slice:

```
$ cd <user's Maven project with pytest-free codebase>
$ novetest run
[ JSON envelope: kind=engine-missing, message="no supported native engine detected" ]
```

After this slice:

```
$ cd <Maven project: pom.xml with JUnit Jupiter + maven-surefire-plugin>
$ novetest run
[ JSON envelope: kind=run-record, engine_name=junit, summary={passed: N, failed: M, ...},
  failed_tests: ["com.example.FooTest#testBar", ...] ]

$ cd <Gradle project: build.gradle.kts with useJUnitPlatform()>
$ novetest run --coverage
[ JSON envelope: kind=run-record, coverage_fact={mapping_granularity: aggregate, ...} ]

$ cd <project with neither JDK nor Maven/Gradle installed>
$ novetest run
[ JSON envelope: kind=engine-misconfigured, warnings:[{kind:"missing-jdk"}, {kind:"missing-build-tool"}] ]
```

The `novetest test` integrated workflow (Phase 6 entry) automatically
gains the JUnit path because it calls `select_native_engine` →
`execute_with_engine_context`; no additional wiring needed in this
slice. Same for `novetest replay` (Phase 5) and `novetest regression`
(Phase 3).

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md` — **binding contract for the vendored asset pattern**
4. `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` — JDK + JUnit Platform + Maven/Gradle + JaCoCo rows added 2026-06-03
5. `agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` — polyglot-host-parity contract; Manual Test E2E required before MVP
6. `design/implementation-plan/engine-adapters.md` §3 (Java) — your primary spec
7. `design/interace-contract/run.md` §2.3 (Java – JUnit via Maven Surefire / Gradle)
8. `design/workflows/run.md` — top-level workflow shapes
9. `design/requirements-analysis/requirements-specification/groups/run.md` REQ-RUN-001 through REQ-RUN-008 — JUnit is in REQ-RUN-006
10. `src/novetest/run/adapters/gotest_adapter.py` — **closest sibling** (no on-the-fly config; external tool subprocess; per-test failure logs)
11. `src/novetest/run/adapters/cargo_adapter.py` — **structural sibling** for the dual-coverage-path discipline (Maven and Gradle here, parallel to nextest / nextest+llvm-cov there)
12. `src/novetest/run/engine.py` lines 106-147 — explicit if/elif dispatch where you add the `engine_name == "junit"` branch
13. `src/novetest/run/readiness.py` — where Java/Maven/Gradle PATH + manifest probes land
14. `src/novetest/run/types.py` lines 21-27 — `NativeResult` dataclass shape (binding)
15. `src/novetest/coverage/derive.py` — `_derive_*` dispatch table you extend with `_derive_junit_jacoco()`
16. `src/novetest/coverage/parsers/` — the existing parser modules; the JaCoCo parser is a new sibling
17. `scripts/dev-host-setup.md` §5 (Java) — equip your host before unit tests run
18. `tests/fixtures/projects/gotest-basic/` and `tests/fixtures/projects/cargo-basic/` — fixture shape reference (manifest + minimal SuT; no novetest imports)

---

## 1. Binding contracts (frozen — verbatim wire shape)

These are the surfaces the rest of the system has already agreed on.
Treat each as a contract; if implementation discovers a contradiction,
**stop and write a `questions/` entry** before changing the contract.

### 1.1 Vendored asset location and resolution

```
src/novetest/run/adapters/_vendor/
├── junit-platform-console-standalone-1.11.4.jar
└── THIRD_PARTY_NOTICES.txt
```

`pyproject.toml` MUST contain (additive — do NOT remove other entries):

```toml
[tool.setuptools.package-data]
"novetest.run.adapters._vendor" = ["*.jar", "THIRD_PARTY_NOTICES.txt"]
```

Runtime resolution MUST use `importlib.resources.files()` (Python 3.11+
API; matches our `requires-python`):

```python
import importlib.resources

def _launcher_jar_path() -> Path:
    _vendor = importlib.resources.files("novetest.run.adapters._vendor")
    jar_resource = _vendor.joinpath("junit-platform-console-standalone-1.11.4.jar")
    # importlib.resources may return a MultiplexedPath inside zipapp / PyApp;
    # use .as_file() to get a concrete filesystem Path that survives the
    # `java -jar` subprocess invocation.
    with importlib.resources.as_file(jar_resource) as p:
        return p
```

**DO NOT** use `Path(__file__).parent / "_vendor" / ...` — that breaks
under PyApp single-binary extraction. The R4 mitigation integration test
(§8) validates this resolution path.

### 1.2 SHA-256 pin

Capture the SHA-256 of the downloaded jar at slice-execution time from
Maven Central's `.sha256` sidecar:

```
https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.11.4/junit-platform-console-standalone-1.11.4.jar.sha256
```

Pin it in `THIRD_PARTY_NOTICES.txt` AND in a module constant
`src/novetest/run/adapters/_vendor/__init__.py`:

```python
LAUNCHER_JAR_FILENAME = "junit-platform-console-standalone-1.11.4.jar"
LAUNCHER_JAR_SHA256 = "<captured at slice time>"
LAUNCHER_VERSION = "1.11.4"
```

The adapter MAY (not MUST in this slice) re-verify the SHA-256 at
startup with a `hashlib.sha256` over the resolved file — this is a
defense-in-depth check against on-disk corruption, not a security
boundary. Acceptable to defer to a future hardening cycle.

### 1.3 `THIRD_PARTY_NOTICES.txt` content (binding shape)

```
Nove Test Third-Party Notices

This file lists third-party software distributed inside the Nove Test
binary. Each entry includes the artifact identification, license, source
URL, and pinned SHA-256.

------------------------------------------------------------------------

JUnit Platform Console Launcher (Standalone)
  Artifact:  org.junit.platform:junit-platform-console-standalone
  Version:   1.11.4
  Source:    https://github.com/junit-team/junit5
  License:   Eclipse Public License 2.0 (EPL-2.0)
  License URL: https://www.eclipse.org/legal/epl-2.0/
  SHA-256:   <pinned at slice time>

The Console Launcher is distributed unmodified per EPL 2.0 §3.3 (Larger
Work allowance). Nove Test makes no modifications to the jar. Source
code is available at the URL above under the same license.

------------------------------------------------------------------------
```

### 1.4 `NativeResult` payload shape for JUnit

```python
NativeResult(
    engine_name="junit",
    engine_version="<jupiter version detected from pom.xml or Gradle dependency report>",
    payload={
        "build_tool": "maven" | "gradle",
        "build_tool_version": "<mvn -v or gradle --version>",
        "jupiter_version": "<5.10.x | 5.11.x | ...>",
        "jdk_version": "<java -version major>",
        "reports": [
            {
                "path": "<absolute path to JUnit XML or OTR report>",
                "format": "junit-xml" | "otr-xml",
                "module": "<for multi-module Maven: module name; for single: project name>",
            },
            ...
        ],
        "tests": [  # normalized cross-format per-test outcomes
            {
                "identity": "<fully-qualified class>#<method>[<param>]",
                "unique_id": "<JUnit Platform uniqueId if available; falls back to identity>",
                "status": "passed" | "failed" | "skipped" | "errored",
                "duration_ms": <int>,
                "failure": {  # only when status in {failed, errored}
                    "message": "<from <failure>/<error> message attr>",
                    "type": "<from <failure>/<error> type attr>",
                    "stack": "<element text>",
                } | None,
                "stdout": "<system-out element text or empty>",
                "stderr": "<system-err element text or empty>",
            },
            ...
        ],
        "summary": {"total": N, "passed": A, "failed": B, "skipped": C, "errored": D},
    },
    artifact_paths={
        "stdout": Path(...),
        "stderr": Path(...),
        "reports_dir": Path(...),  # the directory containing all XML reports
        "coverage_xml": Path(...) | None,  # JaCoCo XML if --coverage; None otherwise
    },
    returncode=<int>,
    started_at_ms=<int>, completed_at_ms=<int>,
    metadata={
        "console_launcher_version": "1.11.4",
        "console_launcher_sha256": "<pin>",
        "build_tool": "maven" | "gradle",
        "surefire_version": "<for maven>" | None,
        "jacoco_version": "<if coverage>" | None,
        "multi_module": "true" | "false",
    },
)
```

The normalizer at `src/novetest/run/engine.py` consumes `payload["tests"]`
to build `Run Record` `Test Result` entries; the per-engine name
`junit` flows through `engine_name` on the Run Record (NativeEngineContext)
unchanged.

### 1.5 Coverage artifact key + dispatch

`NativeResult.artifact_paths["coverage_xml"]` is the JaCoCo XML output
path. Coverage engine dispatch (`derive_coverage_facts`) routes on
`engine_name == "junit"` to a new `_derive_junit_jacoco()` parser in
`src/novetest/coverage/derive.py`. The parser emits a CoverageFact with:

- `mapping_granularity`: `"aggregate"` (default — no per-test attribution)
  OR `"per-test-class"` (when the adapter ran in `forkMode=perTestClass`
  Maven mode; see §6 D1).
- Per-class line / branch / instruction counters from JaCoCo's
  `<counter type="LINE"/>` / `<counter type="BRANCH"/>` /
  `<counter type="INSTRUCTION"/>` elements.
- `source_paths` populated from the user's `src/main/java/` (Maven
  convention) or Gradle source-set convention.

---

## 2. Adapter file shape (matches the existing 4 adapters)

```python
# src/novetest/run/adapters/junit_adapter.py
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Final

from ..types import NativeResult, TestTarget
from ._vendor import LAUNCHER_JAR_FILENAME, LAUNCHER_VERSION, LAUNCHER_JAR_SHA256

ENGINE_NAME: Final[str] = "junit"


async def run_junit(
    test_target: TestTarget,
    artifact_dir: Path,
    timeout: float,
    collect_coverage: bool,
) -> NativeResult:
    """Run JUnit 5 tests via the user's Maven or Gradle build."""
    build_tool = _detect_build_tool(test_target.workspace_path)  # "maven" | "gradle"

    if build_tool == "maven":
        return await _run_maven(test_target, artifact_dir, timeout, collect_coverage)
    elif build_tool == "gradle":
        return await _run_gradle(test_target, artifact_dir, timeout, collect_coverage)
    else:
        raise AdapterInvocationError(
            kind="build-tool-undetermined",
            message="neither pom.xml nor build.gradle{,.kts} found in workspace root",
        )


def _detect_build_tool(workspace_path: Path) -> str | None:
    if (workspace_path / "pom.xml").is_file():
        return "maven"
    if (workspace_path / "build.gradle").is_file() or (workspace_path / "build.gradle.kts").is_file():
        return "gradle"
    return None
```

`_run_maven()` and `_run_gradle()` are the two execution branches.
Inside each:

1. Confirm tooling on PATH (`shutil.which("mvn")` / `shutil.which("gradle")`
   / `shutil.which("java")`).
2. Compose the argv (see §3.1 and §3.2 below).
3. `await asyncio.create_subprocess_exec(...)` with `stdout`/`stderr`
   redirected to artifact files.
4. After completion, glob the report directory, parse each XML, build
   the normalized `payload["tests"]` list.
5. If `collect_coverage=True`, glob and resolve the JaCoCo XML path.
6. Return `NativeResult` per §1.4.

## 3. Native CLI command shape

### 3.1 Maven path

```
mvn -B test \
  -Dsurefire.reportFormat=plain \
  -Dsurefire.useFile=false \
  [-Dtest=<target_filter>]
```

When `--coverage` was requested, prefix with the JaCoCo agent
configuration. If the user's `pom.xml` already declares `jacoco-maven-plugin`
with `prepare-agent` + `report` goals, just add `org.jacoco:jacoco-maven-plugin:report`
to the goal list:

```
mvn -B test org.jacoco:jacoco-maven-plugin:report \
  -Dsurefire.reportFormat=plain \
  -Dsurefire.useFile=false
```

If the user's `pom.xml` does NOT declare JaCoCo, emit
`engine-misconfigured` of kind `missing-jacoco` with the install hint
("add `jacoco-maven-plugin` 0.8.11+ to `pom.xml` <build><plugins>
section") and degrade to `mapping_granularity: aggregate` with
`coverage_xml=None` on the NativeResult. **Do NOT auto-modify pom.xml.**

Reports land at `target/surefire-reports/TEST-*.xml`. Coverage at
`target/site/jacoco/jacoco.xml`. Glob both directories.

For multi-module Maven projects (workspace has child `<module>` entries
in pom.xml), reports appear under `<module>/target/surefire-reports/`
for each module. The adapter MUST walk all modules and aggregate
reports into `payload["tests"]` with the `module` field populated per
test. See §9 for the aggregation scope.

### 3.2 Gradle path

```
./gradlew test --no-daemon [--tests <target_filter>]
```

(Use `./gradlew` wrapper when present, else `gradle`.) The
`--no-daemon` flag is mandatory — daemon caches break the
`-Dcount=1`-equivalent contract (cargo cycle learned this for nextest;
Gradle has the same trap). Reports land at
`build/test-results/test/*.xml`.

For coverage:

```
./gradlew test jacocoTestReport --no-daemon
```

Requires the user's `build.gradle{,.kts}` to apply the `jacoco` plugin.
If absent, same `missing-jacoco` engine-misconfigured warning + aggregate
degrade as Maven.

Coverage XML lands at `build/reports/jacoco/test/jacocoTestReport.xml`.

### 3.3 Console Launcher: discovery ONLY

The vendored Console Launcher is used **only** for the `discover`
subcommand (test enumeration without execution), invoked when
`novetest test --list` or `novetest run --list` requires a pre-execution
test count. The actual test execution always flows through Maven
Surefire or Gradle (we do NOT replace the user's build).

```
java -jar <_vendor/junit-platform-console-standalone-1.11.4.jar> discover \
  --details=tree --details-theme=ascii \
  --reports-dir=<artifact_dir>/discovery \
  -cp <test-classpath>
```

`<test-classpath>` is built from `mvn dependency:build-classpath` (Maven)
or `./gradlew printTestClasspath` (Gradle helper task that the adapter
generates on the fly if the user has not declared it; the helper task
is added to a temp `build.gradle` overlay, NOT to the user's file).

The `discover` subcommand emits an enumeration without execution. For
Phase 2.5 we only need it for the optional `--list` flag; **for the
in-scope `novetest run` path, discovery is implicit in the Surefire /
Gradle execution** and the Console Launcher is not invoked. The
vendored asset still ships and is exercised by the §8 R4 integration
test even if the runtime path does not use it for every invocation.

---

## 4. Coverage parser — JaCoCo XML

New file: `src/novetest/coverage/parsers/jacoco_xml.py`.

Parse JaCoCo's `jacoco.xml` (and per-module variants when aggregating).
JaCoCo XML structure:

```xml
<report name="...">
  <sessioninfo .../>
  <package name="com/example">
    <class name="com/example/Foo" sourcefilename="Foo.java">
      <method name="bar" desc="()V" line="12">
        <counter type="INSTRUCTION" missed="0" covered="5"/>
        <counter type="LINE" missed="0" covered="1"/>
        <counter type="COMPLEXITY" missed="0" covered="1"/>
        <counter type="METHOD" missed="0" covered="1"/>
      </method>
      <sourcefile name="Foo.java">
        <line nr="12" mi="0" ci="5" mb="0" cb="0"/>
        ...
      </sourcefile>
      <counter type="LINE" missed="0" covered="3"/>
      <counter type="BRANCH" missed="0" covered="0"/>
      <counter type="INSTRUCTION" missed="0" covered="15"/>
    </class>
  </package>
  <counter type="LINE" missed="X" covered="Y"/>
  ...
</report>
```

Parser MUST:

- Iterate `<package>/<class>/<sourcefile>/<line>` elements.
- Build a per-source-file `LineCoverage` list mapping `line nr` →
  `covered = (ci > 0)`. Branch coverage from `mb`/`cb`.
- Resolve `sourcefile name` against the user's source roots
  (Maven `src/main/java/` + Gradle source-set conventions; package
  path = `<package name>` with `/` → directory).
- Emit the resulting `CoverageFact` with `mapping_granularity` per §5
  decision (D1).
- Handle multi-module aggregation: if the adapter passed multiple
  JaCoCo XML paths (one per module), parse all and merge into a single
  CoverageFact, OR (decision D2) emit one CoverageFact per module.

Use stdlib `xml.etree.ElementTree.iterparse` for memory efficiency on
large JaCoCo files (>50MB reported in some enterprise projects); a
single-pass streaming parser is preferred over loading the whole tree.

### 4.1 No per-test-method JaCoCo

JaCoCo cannot natively produce per-test-method coverage without a fresh
JVM per test method (`forkMode=pertest` in Surefire), which is
prohibitive at scale (10s of minutes for medium suites). The default
is `mapping_granularity: aggregate`. The opt-in
`forkMode=perTestClass` mode gives **per-test-class** granularity at
~2-5x runtime cost. See §6 D1 for the default-vs-opt-in decision.

## 5. Engine readiness probe extension

`src/novetest/run/readiness.py` MUST add a JUnit branch to
`assess_engine_readiness(project_workspace)`:

```python
def _assess_junit_readiness(workspace_path: Path) -> ReadinessFact | None:
    # 1. Detect build tool from manifest files.
    has_maven = (workspace_path / "pom.xml").is_file()
    has_gradle = (
        (workspace_path / "build.gradle").is_file()
        or (workspace_path / "build.gradle.kts").is_file()
    )
    if not (has_maven or has_gradle):
        return None  # not a JUnit project — let other engines try

    # 2. Detect JDK on PATH.
    if shutil.which("java") is None:
        return ReadinessFact(
            engine_name="junit",
            state="engine-misconfigured",
            warnings=[{"kind": "missing-jdk", "message": "install JDK 17+ (see scripts/dev-host-setup.md §5)"}],
        )

    # 3. Detect build tool on PATH (must match the manifest).
    build_tool = "maven" if has_maven else "gradle"
    tool_binary = "mvn" if has_maven else "gradle"
    if shutil.which(tool_binary) is None:
        # Gradle: also check for ./gradlew wrapper
        if build_tool == "gradle" and (workspace_path / "gradlew").is_file():
            pass  # wrapper present, OK
        else:
            return ReadinessFact(
                engine_name="junit",
                state="engine-misconfigured",
                warnings=[{
                    "kind": "missing-build-tool",
                    "message": f"install {build_tool} (see scripts/dev-host-setup.md §5)",
                }],
            )

    # 4. Detect JUnit Jupiter in the user's dependency graph.
    #    Maven: parse pom.xml for <artifactId>junit-jupiter*</artifactId>.
    #    Gradle: parse build.gradle for `junit-jupiter` / `junit.jupiter` literals.
    #    (Robust dependency resolution would shell out to `mvn dependency:tree`
    #    or `gradle dependencies` — DEFER to a hardening cycle; manifest parse
    #    is acceptable for v1.)
    if not _detects_jupiter_in_manifest(workspace_path, build_tool):
        return ReadinessFact(
            engine_name="junit",
            state="engine-misconfigured",
            warnings=[{
                "kind": "missing-jupiter",
                "message": "JUnit Jupiter (junit-jupiter) is not declared in the project's dependencies",
            }],
        )

    # 5. Windows OS gate (PyApp matrix does not include Windows yet per Open Q #16).
    import sys
    if sys.platform.startswith("win"):
        return ReadinessFact(
            engine_name="junit",
            state="engine-misconfigured",
            warnings=[{
                "kind": "os-unsupported",
                "message": "JUnit adapter requires a non-Windows host until the Windows binary pipeline ships (Open Question #16)",
            }],
        )

    return ReadinessFact(engine_name="junit", state="ready", ...)
```

The probe runs in declared order with the other engines (pytest first,
then jest, then gotest, cargo, then JUnit; .NET joins at the next
cycle). Order does not matter for correctness but affects which warning
the user sees first if multiple engines are misconfigured.

---

## 6. Pre-design delegated decisions

These are the small but load-bearing choices PM does not pre-decide.
You (Run team) make the call, document it in your handoff, and PM
ratifies it in the cycle-close decision file. **If you are unsure, file
a `questions/` entry before committing.**

### D1. Default coverage granularity — aggregate or per-test-class?

JaCoCo with default `forkMode=once` (Surefire) gives aggregate coverage
only. Switching to `forkMode=perTestClass` gives per-test-class
attribution at ~2-5x runtime cost. The trade-off:

- **PM recommendation**: default to **aggregate**. Opt-in flag
  `--per-test-class` (mirrors cargo's per-test-coverage opt-in).
  Localization engine handles `mapping_granularity: aggregate`
  gracefully (degrades to `sbfl_aggregate` mode); per-test-class is a
  fidelity upgrade not a correctness requirement.
- Alternative: default to per-test-class for small suites (<100 tests).
  Discouraged — runtime estimation is brittle and the heuristic adds
  complexity.

### D2. Multi-module Maven aggregation — single CoverageFact or per-module?

For a multi-module Maven project, JaCoCo emits one XML per module.

- **PM recommendation**: emit **one CoverageFact per module** (one
  RunRecord covers the whole `mvn test` invocation but the
  `CoverageFactSet` contains multiple CoverageFacts each with a
  `module` annotation). This matches Cargo workspace handling and
  preserves module-boundary information for downstream analysis.
- Alternative: merge into a single project-wide CoverageFact. Loses
  module attribution; the downstream Localization engine cannot then
  cite module-level evidence.

### D3. Tool tiebreaker when both pom.xml AND build.gradle present

Some projects vendor both files (legacy Maven + new Gradle migration in
progress). Default tiebreaker?

- **PM recommendation**: Maven wins (`pom.xml` is older and more
  common in the JUnit-using enterprise market). Surface a `warnings`
  entry of kind `ambiguous-build-tool` with a CLI flag hint
  (`--build-tool=gradle`) so the user can override.
- Alternative: Gradle wins / no tiebreaker (require explicit
  `--build-tool`). The flag-required path is a worse first-run UX.

### D4. SHA-256 pin capture timing

The `THIRD_PARTY_NOTICES.txt` SHA-256 must come from the actual
downloaded jar (not transcribed from a third-party blog).

- **PM recommendation**: at slice start, `curl` the Maven Central
  `.sha256` sidecar, verify it matches `sha256sum <downloaded.jar>`,
  paste both values into `THIRD_PARTY_NOTICES.txt` AND
  `_vendor/__init__.py`. Commit both the jar and the pin in the same
  commit. Capture the command sequence in a code comment for posterity.

### D5. JUnit 4 detection — silent reject or warning?

A non-trivial number of legacy projects still use JUnit 4 (the
`<dependency><artifactId>junit</artifactId><version>4.x</version>`
pattern). Our adapter targets JUnit 5 (Jupiter) only.

- **PM recommendation**: detect JUnit 4 in the manifest (artifactId
  `junit` with version starting `4.`) and emit
  `engine-misconfigured` of kind `junit-4-not-supported` with the
  message "Nove Test supports JUnit 5 (Jupiter); migrate via JUnit
  Vintage Engine or upgrade tests to Jupiter". Do NOT silently fall
  back to running tests anyway — JUnit 4 reports through a different
  Surefire format that our parser is not tested against, and the
  resulting `payload["tests"]` would be lossy.

### D6. Gradle Kotlin DSL vs Groovy DSL detection

Both `build.gradle` (Groovy) and `build.gradle.kts` (Kotlin) are valid.

- **PM recommendation**: treat both identically — both are passed to
  the same `./gradlew test` invocation; the DSL is irrelevant to test
  execution. Manifest-parse handling for D5 / Jupiter detection MUST
  read both (regex over both file contents).

---

## 7. Tests required

### 7.1 Unit tests (`tests/unit/run/adapters/test_junit_adapter.py`)

Mirror the gotest adapter's unit-test layout. Cover:

- `_detect_build_tool()` for all 4 manifest combinations (maven only,
  gradle-groovy only, gradle-kotlin only, neither).
- `_detects_jupiter_in_manifest()` for Maven pom.xml + both Gradle
  DSLs. Include positive cases (jupiter declared) + negative (JUnit 4
  declared, no test framework declared).
- Manifest detection robustness: comments, multiple `<dependencies>`
  blocks, transitive declarations via `<dependencyManagement>`.
- `payload["tests"]` normalization from synthetic JUnit XML fixtures
  (small XML strings inlined in the test file, not full fixture
  projects). Cover: passed / failed / skipped / errored / parametrized
  / nested classes / Kotlin synthetic names.
- JaCoCo XML parser: per-file line coverage, branch coverage,
  multi-class single-package, multi-module aggregation merge logic.
- D1 / D2 / D3 / D5 / D6 outcomes match the decision document.
- Windows OS gate emits the right warning.

Target: ~400-600 LOC test (similar to jest's 647 LOC test file).

### 7.2 Integration tests (`tests/integration/run/test_junit_*.py`)

Three files:

- `test_junit_maven.py` — runs against `tests/fixtures/projects/
  junit-maven-basic/`. Probes a real `mvn -B test` invocation, parses
  the actual Surefire output, asserts the resulting NativeResult shape.
  Skip via `shutil.which("java") is None or shutil.which("mvn") is
  None`. ~5-8 test methods covering: passing tests, failing tests,
  skipped tests, parametrized tests, coverage path (JaCoCo XML
  presence + sample line coverage assertion), engine-misconfigured
  paths.
- `test_junit_gradle.py` — same shape, Gradle path, runs against
  `tests/fixtures/projects/junit-gradle-basic/`. Uses `./gradlew`
  wrapper. Skip via `shutil.which("java") is None or
  (shutil.which("gradle") is None and not (workspace /
  "gradlew").is_file())`.
- `test_junit_vendored_launcher.py` — §8 below.

### 7.3 Fixture projects

`tests/fixtures/projects/junit-maven-basic/`:

```
junit-maven-basic/
├── pom.xml               # JUnit Jupiter 5.10 + Surefire 3.0 + JaCoCo 0.8.11
├── src/
│   └── main/
│       └── java/
│           └── com/example/
│               └── Calculator.java    # SuT: 3-4 small methods
└── src/
    └── test/
        └── java/
            └── com/example/
                └── CalculatorTest.java # 5-7 tests: pass/fail/skip/parametrized
```

`tests/fixtures/projects/junit-gradle-basic/`:

```
junit-gradle-basic/
├── build.gradle.kts      # useJUnitPlatform() + jacoco
├── settings.gradle.kts
├── gradlew, gradle/wrapper/, gradlew.bat
└── src/main/java/com/example/Calculator.java
└── src/test/java/com/example/CalculatorTest.java
```

The fixture projects MUST be deterministic, isolated, and free of
`novetest` imports (per project structure rule for `tests/fixtures/
projects/`). Use a minimal Calculator + arithmetic-tests-with-a-known-bug
shape so localization downstream can demonstrate suspect ranking.

## 8. PyApp binary blob extraction integration test (R4 mitigation)

`tests/integration/run/test_junit_vendored_launcher.py` — load-bearing
DoD bullet. Two test methods:

### 8.1 `test_importlib_resources_resolves_vendored_jar`

```python
def test_importlib_resources_resolves_vendored_jar():
    import importlib.resources
    _vendor = importlib.resources.files("novetest.run.adapters._vendor")
    jar_resource = _vendor.joinpath("junit-platform-console-standalone-1.11.4.jar")
    with importlib.resources.as_file(jar_resource) as p:
        assert p.is_file()
        assert p.stat().st_size > 1_000_000  # >1 MB sanity check
        # SHA-256 round-trip
        import hashlib
        from novetest.run.adapters._vendor import LAUNCHER_JAR_SHA256
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert digest == LAUNCHER_JAR_SHA256
```

### 8.2 `test_java_can_execute_vendored_jar`

```python
def test_java_can_execute_vendored_jar():
    java_path = shutil.which("java")
    if java_path is None:
        pytest.skip("no java on PATH; install JDK 17+ per scripts/dev-host-setup.md §5")
    import importlib.resources
    _vendor = importlib.resources.files("novetest.run.adapters._vendor")
    jar_resource = _vendor.joinpath("junit-platform-console-standalone-1.11.4.jar")
    with importlib.resources.as_file(jar_resource) as p:
        result = subprocess.run(
            [java_path, "-jar", str(p), "--version"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "JUnit Platform" in result.stdout or "JUnit Platform" in result.stderr
```

### 8.3 PyApp-side verification (Release team smoke at handoff)

The full PyApp binary blob extraction verification (R4 across all three
target platforms: Linux x86_64, Linux aarch64, macOS universal2) is a
**Release team smoke at handoff time** — NOT in this slice's source
tests, because PyApp binary production is the Release team's
territory. Your handoff MUST include:

- A note to Manual Test team to run `pip install dist/novetest-*.whl`
  AND `pyapp <novetest-binary> run` against a junit-maven-basic
  fixture; report which platforms passed.
- If any platform fails the extraction step, the fallback strategy is:
  detect the extraction failure at adapter startup, manually extract
  the jar to a process-local tempdir, point `LAUNCHER_JAR` constant at
  the extracted copy. Document the fallback in your handoff if R4 fires.

---

## 9. Out of scope (explicit)

Do **not** implement these in this slice. Each is either a separate
cycle or a deferred enhancement:

- **TestNG adapter** — only JUnit 5 (Jupiter) in this slice. TestNG is
  a separate ecosystem decision; route TestNG users to
  `engine-misconfigured` of kind `testng-not-supported` with the
  message "Nove Test currently supports JUnit 5; TestNG support is
  deferred to a future cycle".
- **JUnit 4 adapter** — explicit reject per §6 D5.
- **xUnit v3 / Microsoft.Testing.Platform .NET coverage path** — that
  is the .NET cycle's concern, not JUnit's. Mentioned only because
  these two cycles are paired in the Phase 2.5 closure.
- **Cross-module CoverageFact merging** (a single project-wide
  CoverageFact for multi-module Maven) — D2 records per-module
  CoverageFacts; the cross-module aggregation verb is a future
  cross-run cycle item.
- **Maven `dependency:tree` / Gradle `dependencies` shell-out for
  robust Jupiter detection** — manifest-regex parsing is acceptable
  for v1; hardening cycle later.
- **JaCoCo HTML report parsing** — only XML is consumed by the
  Coverage engine.
- **OTR (open-test-reporting) XML preference over Surefire XML** —
  `engine-adapters.md` §3 mentions OTR as preferable when present; for
  v1, parse Surefire XML only (more universal). OTR is a fidelity
  upgrade for a future hardening cycle.
- **Windows host** — gated as `os-unsupported` per Open Q #16.
- **Multi-JDK projects** (Toolchains, `--release` per source set) — assume
  single-JDK invocation in v1.
- **Kotlin/Scala-specific synthetic-display-name normalization** —
  use `uniqueId` when present; surface the synthetic display name
  as-is otherwise (per engine-adapters.md §3 Edge cases).
- **`novetest --licenses` CLI verb that surfaces `THIRD_PARTY_NOTICES`** —
  ship the NOTICE file in this slice; the CLI surface is a Phase 2.5
  cleanup cycle item.

## 10. Doctor probe shape

The Run team's doctor surface for JUnit (called as part of
`assess_engine_readiness`):

| Check | Pass criterion | Fail kind | Hint |
|---|---|---|---|
| JDK present | `shutil.which("java")` | `missing-jdk` | install per dev-host-setup.md §5 |
| JDK version >= 17 | `java -version` major >= 17 | `jdk-below-floor` | upgrade to JDK 17+ |
| Build tool present | `pom.xml` OR `build.gradle{,.kts}` exists | `not-a-junit-project` | (silent — let other engines try) |
| Maven on PATH (if pom.xml) | `shutil.which("mvn")` | `missing-build-tool` | install per dev-host-setup.md §5 |
| Gradle on PATH OR wrapper (if Gradle) | `shutil.which("gradle")` OR `gradlew` file exists | `missing-build-tool` | install per dev-host-setup.md §5 |
| Jupiter declared in manifest | regex `junit-jupiter` match | `missing-jupiter` | add JUnit Jupiter 5.10+ to dependencies |
| JUnit 4 NOT present | no `junit:junit:4.*` artifact | `junit-4-not-supported` | migrate via Vintage Engine or to Jupiter |
| TestNG NOT present | no `testng` artifact | `testng-not-supported` | TestNG support deferred |
| Coverage requested → JaCoCo declared | jacoco plugin present in build config | `missing-jacoco` (warning, not blocker) | add jacoco plugin; degrades to aggregate |
| OS supported | `not sys.platform.startswith("win")` | `os-unsupported` | Windows pipeline deferred per Q#16 |
| Vendored launcher resolvable | importlib.resources resolves jar | `vendored-launcher-extraction-failed` | (file a bug — R4 fired) |

## 11. Definition of Done bullets

Tick when ALL of these are true:

- [ ] `src/novetest/run/adapters/junit_adapter.py` ships and matches
      the §1.4 `NativeResult` payload shape exactly.
- [ ] `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
      committed; `_vendor/__init__.py` declares `LAUNCHER_JAR_SHA256`;
      `_vendor/THIRD_PARTY_NOTICES.txt` ships with §1.3 content.
- [ ] `pyproject.toml` `[tool.setuptools.package-data]` includes
      `"novetest.run.adapters._vendor" = ["*.jar", "THIRD_PARTY_NOTICES.txt"]`.
- [ ] `importlib.resources.files()` resolves the jar in §8.1; SHA-256
      round-trip matches.
- [ ] `java -jar <resolved_jar> --version` exits 0 with "JUnit Platform"
      in output (§8.2).
- [ ] `src/novetest/run/engine.py` dispatch branch for `engine_name ==
      "junit"` routes to `run_junit()`.
- [ ] `src/novetest/run/readiness.py` JUnit branch detects Maven /
      Gradle / wrapper / Jupiter / JUnit 4 / TestNG / OS gate per §5
      and §10.
- [ ] `src/novetest/coverage/derive.py` dispatch + new
      `_derive_junit_jacoco()` in `src/novetest/coverage/parsers/
      jacoco_xml.py`.
- [ ] `tests/fixtures/projects/junit-maven-basic/` + `junit-gradle-basic/`
      ship; deterministic; no novetest imports.
- [ ] `tests/unit/run/adapters/test_junit_adapter.py` covers §7.1
      scope; passes in the project's unit gate.
- [ ] `tests/integration/run/test_junit_maven.py` +
      `test_junit_gradle.py` + `test_junit_vendored_launcher.py` ship;
      pass when the host is equipped per `scripts/dev-host-setup.md §5`;
      skip via `shutil.which()` guards when not.
- [ ] D1 / D2 / D3 / D5 / D6 decisions are documented in the handoff
      (one or two sentences each citing this brief's §6).
- [ ] `mypy --strict` clean across new files.
- [ ] Manual Test E2E equipping: handoff includes the dev-host setup
      §5 reference + an E2E command sequence to validate `novetest run`
      against each fixture (per the 2026-05-29 polyglot-host-parity
      contract).
- [ ] `delivery-phasing.md` Phase 2.5 DoD bullet for JUnit ticked by
      PM at cycle close (Phase 2.5 has one bullet per ecosystem).

## 12. Handoff expectations

When you're ready to merge, write
`agent-comms/handoffs/run-team-2026-06-XX-phase2.5-junit-adapter.md`
with:

1. **DoD bullets believed closed** — list each from §11 with a one-line
   evidence pointer (file path + line range or test name).
2. **D1-D6 decisions made** — one or two sentences each.
3. **R4 result** — did `importlib.resources` resolve cleanly under
   regular `pytest tests/`? Any PyApp-side extraction concerns to
   flag to Release team?
4. **Manual Test E2E checklist** — pasted command sequence + expected
   envelope shapes for Maven + Gradle paths.
5. **Slice diff summary** — `git diff --stat` output.
6. **Open questions / followups** — anything you bumped into that
   needs a `questions/` entry or future cycle scope.

PM picks up the handoff, dispatches Main Branch team for FF-merge +
verification request, then Manual Test team for E2E sweep against an
equipped host. If E2E fires a regression you didn't catch, the
findings doc goes back to PM and the cycle close is delayed until
addressed.

## 13. Dev host setup amendment

`scripts/dev-host-setup.md` §5 (Java) was filled in commit `0c72a68`
as part of the Open Q closure. Confirm your dev host is equipped per
that section BEFORE you start coding — the unit gate runs but the
integration gate will skip half the new tests otherwise, masking real
regressions.

If during your slice you discover a host-setup gap (e.g., a required
Maven plugin version not mentioned), append the fix to §5 in your
slice commit. The dev-host-setup is PM-owned, but slice-driven
amendments are welcome and merged with the slice — this matches the
2026-05-30 cargo trigger-b refinement pattern.

---

## Final sanity check before starting

If, on reading this brief, you find yourself wanting to:

- Modify the user's `pom.xml` / `build.gradle*` → STOP. We never
  modify user manifests. Generate temp overlays in `artifact_dir`
  instead.
- Implement TestNG / JUnit 4 / Vitest / Kotlin-specific paths → STOP.
  §9 excludes these.
- Download something from Maven Central at runtime → STOP. §1.1 + the
  vendor decision forbids it.
- Add a `~/.cache/novetest/` directory → STOP. No runtime caches.
- Add SQLite anything → STOP. Deferred per
  `decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`.
- Modify the .NET adapter, MCP, JUnit 4 vintage path → STOP. Out of
  scope.

If you stop, file a `questions/` entry with the proposed change and
PM resumes after CEO review.

Otherwise: equip your host per `scripts/dev-host-setup.md §5`, branch
a worktree, start with the `_vendor/` directory and the §8 R4
mitigation test first (smallest atomic checkpoint), then build outward
to the adapter + readiness + parser + fixtures + integration tests.
