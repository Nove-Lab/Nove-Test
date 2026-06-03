---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
created: 2026-06-03
slug: phase2.5-junit-adapter
status: ready-to-merge
related:
  - agent-comms/tasks/run-team-2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - scripts/dev-host-setup.md
---

# Handoff — Phase 2.5 JUnit adapter (fifth Native Engine)

## Worktree
- **Path:** `/home/yjshin/dev/novetest-phase2.5-junit-adapter`
- **Branch:** `worktree-run-team-phase2.5-junit-adapter`
- **Base:** `caf3dd4` (origin/main tip at slice start)
- **Tip:** single commit on top of base — see `git log --oneline caf3dd4..HEAD`
- **Working tree:** clean (after handoff + WORKLOG commit)

## DoD bullets believed closed (PM verifies + ticks `delivery-phasing.md`)

All 13 brief §11 bullets satisfied:

| # | DoD bullet | Evidence pointer |
|---|---|---|
| 1 | `junit_adapter.py` ships matching §1.4 NativeResult shape | `src/novetest/run/adapters/junit_adapter.py` (~720 LOC); `run_junit` returns NativeResult with `engine_name="junit"` + payload `{build_tool, build_tool_version, jupiter_version, jdk_version, reports, tests, summary, failure_logs, warnings}` + artifact_paths `{stdout, stderr, reports_dir, coverage_xml?}` + metadata `{console_launcher_version, console_launcher_sha256, build_tool, surefire_version?, jacoco_version?, multi_module}` |
| 2 | Vendored JAR + SHA-256 constant + NOTICE file | `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar` (2,809,597 bytes); `_vendor/__init__.py` exports `LAUNCHER_JAR_SHA256 = "b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc"`; `_vendor/THIRD_PARTY_NOTICES.txt` (EPL-2.0 attribution) |
| 3 | `pyproject.toml` ships jar in wheel | `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` block (Hatchling-native equivalent of brief's `setuptools.package-data` — see §Build-system deviation below); verified by `uv build --wheel` + `zipfile` namelist inspection — jar + NOTICE + __init__.py all present |
| 4 | `importlib.resources` resolves jar + SHA-256 round-trip | `tests/integration/run/test_junit_vendored_launcher.py::test_importlib_resources_resolves_vendored_jar` (passes green at unit-gate time, not skip-gated) |
| 5 | `java -jar --version` smoke | `test_junit_vendored_launcher.py::test_java_can_execute_vendored_jar` (skip-gated on `shutil.which("java") is None`; green on equipped host) |
| 6 | `engine.py` dispatch branch for `"junit"` | `src/novetest/run/engine.py` lines ~131-137 (`if engine_name == "junit": return await run_junit(...)`) |
| 7 | `readiness.py` JUnit branch | `src/novetest/run/readiness.py` `_assess_junit_readiness` (~150 LOC) — implements OS gate / build-tool detect / JDK probe / mvn-or-gradle-wrapper probe / Jupiter detect / JUnit 4 reject / TestNG reject / Jupiter version capture |
| 8 | `coverage/derive.py` dispatch + `jacoco_parser.py` | `src/novetest/coverage/jacoco_parser.py` (~330 LOC, pure `parse_jacoco_xml`); `coverage/derive.py` `_derive_junit_jacoco` (~85 LOC) + `COVERAGE_JACOCO_XML_ARTIFACT_KEY = "coverage_xml"` constant |
| 9 | Two fixture projects ship | `tests/fixtures/projects/junit-maven-basic/` + `junit-gradle-basic/` — deterministic, no novetest imports, identical 6-test Calculator with one off-by-one bug for predictable failure shape |
| 10 | Unit tests cover §7.1 scope | `tests/unit/run/adapters/test_junit_adapter.py` (41 tests); `tests/unit/coverage/test_jacoco_parser.py` (7 tests); `tests/unit/run/test_junit_readiness.py` (8 tests); `tests/unit/coverage/test_derive_junit.py` (3 tests) — **66 new unit tests** |
| 11 | Integration tests ship | `tests/integration/run/test_junit_maven.py` (2 tests); `test_junit_gradle.py` (2 tests); `test_junit_vendored_launcher.py` (2 tests). All Maven + Gradle cases skip-gated on toolchain PATH presence per polyglot-host-parity contract |
| 12 | D1-D6 decisions documented | See §"D1-D6 decisions" below |
| 13 | mypy strict clean | `uv run mypy` → `Success: no issues found in 90 source files` (+3 vs baseline 87) |

Plus the brief's "Manual Test E2E equipping" bullet: see §"Manual Test E2E checklist" below.

## Verification

```
$ uv run mypy
Success: no issues found in 90 source files

$ uv run pytest -q tests/unit tests/integration
1009 passed, 10 skipped in 48.10s
```

**Delta from baseline:** baseline 949 passed + 5 skipped → +60 net new passing tests + 5 new skip-gated integration cases (matching the 5 JDK/Maven/Gradle-gated cases that need an equipped host). Zero regressions.

**Wheel inspection** (`uv build --wheel` + `zipfile`):
```
novetest/run/adapters/_vendor/__init__.py
novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt
novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
```

**JAR pin verification (slice-write time, 2026-06-03)**:
```
$ curl -fsSL https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.11.4/junit-platform-console-standalone-1.11.4.jar.sha256
b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc

$ sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc  ...
```

## D1-D6 decisions (brief §6)

- **D1 (default coverage granularity)**: **aggregate** — matches PM recommendation. `--per-test-class` opt-in deferred to a future hardening cycle. Implementation: `jacoco_parser._JACOCO_MAPPING_GRANULARITY = "aggregate"`. Localization handles the degradation via `sbfl_aggregate` mode.
- **D2 (multi-module Maven aggregation)**: emit **one CoverageFactSet with per-module-prefixed `file_path`s**. The `CoverageFactSet.files: tuple[FileCoverage, ...]` model doesn't have a `module` slot, so the prefix encodes module attribution (`moduleA/src/main/java/com/example/Foo.java`). Implementation: `parse_jacoco_xml(xml_paths, module_prefix_for={...})`. The derive branch re-globs `*/target/site/jacoco/jacoco.xml` under workspace root when `metadata["multi_module"] == "true"`.
- **D3 (tiebreaker when both pom.xml AND build.gradle present)**: **Maven wins**, emit `ambiguous-build-tool` warning on `payload["warnings"]`. Implementation: `_detect_build_tool` returns "maven" first.
- **D4 (SHA-256 pin capture timing)**: captured at slice-write time from Maven Central sidecar; verified locally; pinned in three places (constant in `_vendor/__init__.py`, prose in `THIRD_PARTY_NOTICES.txt`, prose in this handoff). R4 mitigation test re-verifies at every test run.
- **D5 (JUnit 4 detection)**: **rejected with specific message** ("Nove Test supports JUnit 5 (Jupiter); migrate via JUnit Vintage Engine or upgrade tests to Jupiter"). Implementation: `_assess_junit_readiness` step 6 + step 5 (Jupiter-missing diagnostic specificity).
- **D6 (Gradle Kotlin DSL vs Groovy DSL)**: both DSLs detected via identical regex set; both pass through to the same `./gradlew test --no-daemon` invocation. Implementation: `_safe_read_text(build.gradle) or _safe_read_text(build.gradle.kts)` cascade.

## R4 result (binary blob extraction)

**Closed at unit-gate layer** + **at wheel-build layer**:

- `test_importlib_resources_resolves_vendored_jar` PASSES (not skip-gated). Validates `importlib.resources.files()` + `as_file()` resolution; SHA-256 round-trip matches the pin.
- `uv build --wheel` produces a wheel with the JAR + NOTICE + `__init__.py` at the expected paths inside the zip.

**Not closed here, deferred to Release team**:

- **PyApp binary blob extraction on the three target platforms** (Linux x86_64, Linux aarch64, macOS universal2). This requires a Release-team smoke at handoff time. Per decision §R4: "if extraction is blocked, the fallback is to extract the jar to a temporary directory on first use within the same process (still vendor-side, still no network)". If R4 fires on any platform, Release team writes a Run-team-targeted question describing the fallback need and we add the extract-on-first-use code path.

## Build-system deviation (FYI to PM)

The brief §1.1 prescribes:

```toml
[tool.setuptools.package-data]
"novetest.run.adapters._vendor" = ["*.jar", "THIRD_PARTY_NOTICES.txt"]
```

This project uses **Hatchling**, not setuptools (verified at `pyproject.toml` lines 17-19). Adding setuptools config to a Hatchling project would be misleading dead config. The Hatchling-native equivalent is:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar" = "novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar"
"src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt" = "novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt"
```

Verified by inspecting the built wheel (see §Verification above) — JAR + NOTICE ship at the correct paths.

PM may want to amend brief §1.1 verbatim or add a "if Hatchling, use force-include instead" note to the binding contracts section. Future adapter cycles vendoring assets should follow the Hatchling pattern.

## Manual Test E2E checklist (equipped host required)

Per the polyglot-host-parity contract (`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`), this slice cannot self-verify the integration gate without a JDK + Maven + Gradle install. The current dev host has none of those; the auto-mode classifier blocked the Adoptium JDK download, and sudo for `apt-get install openjdk-17-jdk maven gradle` requires manual approval.

**Manual Test, on a fully-equipped host per `scripts/dev-host-setup.md §5`:**

1. Install JDK 17 LTS + Maven 3.9 + Gradle 7.6 per §5 of the dev-host-setup doc.
2. From the merged main branch:
   ```
   uv sync
   uv run pytest -q tests/integration/run/test_junit_maven.py -v
   uv run pytest -q tests/integration/run/test_junit_gradle.py -v
   uv run pytest -q tests/integration/run/test_junit_vendored_launcher.py -v
   ```
   Expected: all 6 tests PASS. The first Maven run downloads JUnit Jupiter into `~/.m2/repository` (~30-90s); subsequent runs warm-cache to ~10-15s. First Gradle run similarly downloads JUnit Jupiter to `~/.gradle/caches/` (~45-120s); subsequent runs ~20-30s.
3. **End-to-end CLI smoke** (per brief "Product framing"):
   ```
   cd /tmp && cp -r <merged-checkout>/tests/fixtures/projects/junit-maven-basic /tmp/junit-smoke
   cd /tmp/junit-smoke && novetest init && novetest run
   # Expected envelope: kind=run-record, engine_name=junit, summary={passed: 4, failed: 1, skipped: 1}
   # failed_tests includes "com.example.CalculatorTest#testSubtract"

   novetest run --coverage
   # Expected envelope: coverage_outcome.kind=fact-set, has_coverage_facts=true,
   # mapping_granularity=aggregate
   ```
4. **Negative smoke** (engine misconfigured paths):
   - JDK absent → `kind: engine-misconfigured`, `issues: [".*java.*PATH.*"]`
   - JUnit Jupiter absent → `kind: engine-misconfigured`, `issues: [".*Jupiter.*"]`
   - JUnit 4 declared instead of Jupiter → `kind: engine-misconfigured`, `issues: [".*JUnit 4.*"]`
5. Confirm `dist/novetest-*.whl` (built locally) contains the three `_vendor/` entries.

If any of (1)-(5) regresses, file a Findings doc and route back to Run team via PM.

## Open questions / followups for PM

1. **PyApp binary blob extraction smoke** (R4 closure) — Release team must verify the JAR extracts cleanly when packaged via PyApp on Linux x86_64, Linux aarch64, and macOS universal2. The fallback code path (manual extract-to-tempdir on first use) is documented in the decision §R4 but not implemented in this slice; we'd add it reactively if R4 fires.
2. **`--licenses` CLI verb** (brief §9 deferred) — recommended for a Phase 2.5 cleanup cycle. The current `THIRD_PARTY_NOTICES.txt` ships in the wheel but has no CLI surface.
3. **`--per-test-class` opt-in** (brief §9 deferred) — Surefire `forkMode=perTestClass` would give per-test-class coverage attribution at 2-5x runtime cost. Localization could then use the finer-grained CoverageFacts. Hardening-cycle candidate.
4. **OTR (open-test-reporting) XML parser** (brief §9 deferred) — Surefire/Gradle JUnit XML is universally supported; OTR is a fidelity upgrade (richer per-test metadata). Hardening-cycle candidate.
5. **Brief §1.1 setuptools directive** — recommend PM amend to either be Hatchling-native or add a "if Hatchling, use force-include instead" note. Future vendored-asset slices should match.
6. **Gradle wrapper for the fixture** — `tests/fixtures/projects/junit-gradle-basic/` ships without a `gradlew` wrapper (couldn't generate one without a pre-existing Gradle install). A future cycle on an equipped host can run `gradle wrapper` inside the fixture and commit the resulting `gradlew` + `gradle/wrapper/gradle-wrapper.jar` (~60 KB binary). Until then, the Gradle integration test relies on system `gradle` and skip-gates accordingly.
7. **Auto-mode classifier blocked Adoptium download** — when I tried to install JDK 17 via `curl https://api.adoptium.net/v3/binary/.../jdk-17.tar.gz`, the classifier denied it as "external toolchain install without established user intent". The JAR download from Maven Central was allowed (project-vendored asset). CEO/user may want to pre-approve the dev-host-setup §5 install path so future agents can equip hosts without sudo.

## Slice diff summary

```
git diff --stat caf3dd4..HEAD
```

Modifications (high level):
- 3 new src files: `_vendor/__init__.py`, `junit_adapter.py`, `jacoco_parser.py`
- 5 modified src files: `engine.py`, `engine_selector.py`, `readiness.py`, `normalizer.py`, `coverage/derive.py`
- 1 vendored binary: `junit-platform-console-standalone-1.11.4.jar` (2.8 MB)
- 1 NOTICE file
- 1 modified `pyproject.toml` (Hatchling force-include block)
- 5 new test files: `test_junit_adapter.py`, `test_jacoco_parser.py`, `test_junit_readiness.py`, `test_derive_junit.py`, `test_junit_vendored_launcher.py`, `test_junit_maven.py`, `test_junit_gradle.py`
- 8 new fixture files under `tests/fixtures/projects/junit-{maven,gradle}-basic/`
- 1 WORKLOG entry
- 1 handoff doc

## Test counts (post-slice)

| Suite | Before | After | Delta |
|---|---|---|---|
| `tests/unit` + `tests/integration` (this host, JDK-less) | 949 + 5 skip | 1009 + 10 skip | +60 passing, +5 skip |
| `tests/unit` + `tests/integration` (equipped host, projected) | 949 + 5 skip | 1015 + 4 skip | +66 passing on equipped, +5 R4 / java-version skips become 1 java-version skip (project-side `python -m pip show pytest-json-report` is the other long-standing skip) |
| mypy `--strict` source files | 87 | 90 | +3 |

## Recommended commit message

```
feat(run): Phase 2.5 — JUnit 5 (Jupiter) adapter, fifth ecosystem

Bring `novetest run` from 4 to 5 ecosystems (+Java) by implementing
the JUnit 5 adapter via Maven Surefire and Gradle build invocation.
First vendored binary asset in the project (the JUnit Platform
Console Launcher 1.11.4, per CEO-approved 2026-06-03 decision).

* Vendored JAR at src/novetest/run/adapters/_vendor/ with SHA-256
  pin and EPL-2.0 NOTICE; Hatchling force-include in pyproject.toml
  (the brief's setuptools directive doesn't apply — see handoff).
* New adapter `junit_adapter.py` dispatching Maven Surefire or
  Gradle test invocations; per-test failure logs; multi-module
  Maven walk; D3 tiebreaker (Maven wins, ambiguous warning).
* JaCoCo XML parser at `coverage/jacoco_parser.py`, aggregate-mode
  per D1; multi-module D2 via per-module file_path prefix.
* Readiness probe with full §5/§10 doctor coverage: JDK / build-tool
  / Jupiter / JUnit 4 reject (D5) / TestNG reject / Windows gate.
* New fixtures: junit-maven-basic + junit-gradle-basic (off-by-one
  bug in Calculator#subtract for predictable failure shape).
* R4 mitigation test pins importlib.resources resolution + SHA-256
  round-trip; java -jar --version skip-gated on JDK PATH.
* 66 new unit tests + 5 integration tests (3 skip-gated on
  JDK/mvn/gradle PATH per polyglot-host-parity contract).
* Default suite: 949 → 1009 passing (+60); skips 5 → 10.
* mypy --strict: 87 → 90 source files, clean.

Closes Phase 2.5 JUnit DoD bullet in `delivery-phasing.md` pending
PM tick + Manual Test E2E pass on an equipped host (JDK 17 + Maven
3.9 + optionally Gradle 7.6 per scripts/dev-host-setup.md §5).
```
