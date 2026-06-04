---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
created: 2026-06-05
slug: phase2.5-junit-adapter-hotfix-3
related:
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-3.md
  - agent-comms/questions/main-branch-team-2026-06-04-junit-hotfix-2-gate-failed.md
  - agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
worktree: /home/yjshin/dev/aispace/novetest-junit-hotfix-3
branch: run-team/junit-adapter-hotfix-3
base_commit: caf3dd4 (origin/main)
tip_commit: (set after final commit; see §9)
---

# Handoff — Phase 2.5 JUnit adapter hotfix #3

Closes brief
`agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-3.md`.
Both Main Branch gate failures (F1 envelope path + F2 Gradle
coverage_xml) closed on the new dev host (JDK 17.0.19 + Maven 3.8.7 +
Gradle 8.5). Foundation: hotfix-2 (`41d58ab`, rebased clean onto
`origin/main`).

## 1. DoD bullets believed closed (PM verifies + ticks)

All 11 bullets from brief §7:

| # | Bullet | Evidence |
|---|---|---|
| 1 | F1 Maven envelope path | `tests/integration/run/test_junit_maven.py:231-245` — `envelope["data"]["memory_entry"]["run_record"]["engine_name"]` with inline comment citing `workflows/run.py:32-46` + `cli/app.py:269-281` |
| 2 | F1 Gradle envelope path | `tests/integration/run/test_junit_gradle.py:188-201` — same edit shape |
| 3 | F2 hypothesis confirmed in handoff with diag-log | §3 below — H1 confirmed; transcripts at `/tmp/gradle-diag.log` + `/tmp/gradle-ignore-fail.log` |
| 4 | F2 fix shape + unit test | §4 below — Fix-D (init-script `Test.ignoreFailures = true`); pinned by `tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco` |
| 5 | `test_junit_gradle.py::test_coverage_run_emits_jacoco_xml` PASSES on equipped host (JDK 17 + Gradle ≥7.6) | `uv run pytest -v tests/integration/run/test_junit_gradle.py` → 3 passed, including `test_coverage_run_emits_jacoco_xml` |
| 6 | Both `test_cli_smoke_run_emits_envelope` PASS on equipped host | Maven 3/3 + Gradle 3/3 — see §5 |
| 7 | Pre-handoff gate ran on equipped host per §2.5 | §5 below — JDK 17.0.19 + Maven 3.8.7 + Gradle 8.5 detected; JUnit skip count 0; JUnit failure count 0 |
| 8 | `uv run pytest -q tests/unit tests/integration` ≥1033 passed + 0 failed | **1034 passed + 5 skipped + 0 failed in 86.19s** — see §5 |
| 9 | `uv run mypy --strict` clean | `Success: no issues found in 90 source files` |
| 10 | Hotfix-1 Defect 1 (reports_dir under store.path) + Defect 3 (identity parens strip) canaries PASS | §6 — TestStripTrailingParens (6) + TestStageReportsDir (3) + TestStageCoverageXml (2) + TestNormalizeTestCase::test_gradle_failure_log_key_uses_stripped_identity all green |
| 11 | Hotfix-2 Maven `-Dmaven.test.failure.ignore=true` preserved | §6 — TestMavenCoverageArgv (3 cases) + integration `test_junit_maven.py::test_coverage_run_emits_jacoco_xml` (real Maven + JaCoCo end-to-end) all green |

## 2. F1 envelope path before/after

Both smoke files had:

```python
if envelope["ok"]:
    assert envelope["data"]["run_record"]["engine_name"] == "junit"
```

Now:

```python
if envelope["ok"]:
    # Envelope shape: ``data`` carries a ``MemoryEntry`` (per
    # ``src/novetest/orchestration/workflows/run.py:32-46`` ``RunOutcome.
    # memory_entry`` and ``src/novetest/cli/app.py:269-281`` which
    # projects ``data = {"memory_entry": entry.to_dict()}``). The
    # ``RunRecord`` lives under ``data.memory_entry.run_record`` — NOT
    # ``data.run_record``. Hotfix #2 shipped a wrong dereference here;
    # Main Branch's equip-and-exercise pre-merge gate caught it on
    # 2026-06-04 (``KeyError: 'run_record'``) and aborted the merge.
    # See ``agent-comms/questions/main-branch-team-2026-06-04-junit-
    # hotfix-2-gate-failed.md`` for the gate transcript.
    assert (
        envelope["data"]["memory_entry"]["run_record"]["engine_name"]
        == "junit"
    )
```

(Gradle file has a shorter comment pointing at the Maven sibling for full rationale.)

## 3. F2 hypothesis + diagnostic evidence

**H1 CONFIRMED**: `:jacocoTestReport` is transitively dependent on
`:test`. Gradle's `--continue` only continues tasks INDEPENDENT of the
failure, so when `:test` fails, `:jacocoTestReport` is skipped
regardless of `--continue`.

**Diagnostic transcript** — `/tmp/gradle-diag.log` from
`gradle test jacocoTestReport --no-daemon --continue --info` on the
fixture, key lines:

```
Tasks to be executed: [task ':compileJava', task ':processResources',
  task ':classes', task ':compileTestJava', task ':processTestResources',
  task ':testClasses', task ':test', task ':jacocoTestReport']

> Task :test FAILED
CalculatorTest > testSubtract() FAILED
6 tests completed, 1 failed, 1 skipped

BUILD FAILED in 13s
3 actionable tasks: 3 executed
```

The planner included `:jacocoTestReport` in the graph (4 actionable
items at plan time), but after `:test FAILED` only `3 actionable
tasks: 3 executed` ran. No `> Task :jacocoTestReport` line anywhere in
the log — the task was silently dropped. `build/jacoco/test.exec` IS on
disk (the JaCoCo agent's `dumponexit=true` flag survives test
failures), but the XML report task never ran to read it.

**Probed alternatives that ALSO failed:**

- **Fix-A (brief's recommendation, two-pass)** — `gradle test
  --continue` then `gradle jacocoTestReport --no-daemon` (or even
  `--continue` on the second pass): the second pass observes that the
  prior `:test` failure is not UP-TO-DATE and re-runs `:test`, which
  re-fails, and `:jacocoTestReport` is again skipped. Verified at
  `/tmp/gradle-second-pass.log` + `/tmp/gradle-second-continue.log`.
- **Fix-B (init-script `finalizedBy`)** — wires `:test finalizedBy
  :jacocoTestReport` lazily. The wiring confirmed via println trace
  (`[init] wired test finalizedBy jacocoTestReport`), but Gradle still
  skipped `:jacocoTestReport` (`3 actionable tasks: 3 executed`)
  because `:jacocoTestReport.dependsOn(:test)` is unfulfillable when
  `:test` fails. Verified at `/tmp/gradle-init-script.log` +
  `/tmp/gradle-init-v2.log` + `/tmp/gradle-init-v3.log`.

**The working fix (call it Fix-D)** — make `:test` itself tolerate
test failures, mirroring Maven's `-Dmaven.test.failure.ignore=true`.
Achieved via init-script setting `Test.ignoreFailures = true` on all
`tasks.withType(Test)`. With this, `:test` reports failures via JUnit
XML but task-level result is success; the graph proceeds to
`:jacocoTestReport`; XML written. Diagnostic transcript at
`/tmp/gradle-ignore-fail.log`:

```
> Task :test
CalculatorTest > testSubtract() FAILED
6 tests completed, 1 failed, 1 skipped
There were failing tests. See the report at: file:///.../index.html
> Task :jacocoTestReport
BUILD SUCCESSFUL in 7s
4 actionable tasks: 4 executed

(XML at: build/reports/jacoco/test/jacocoTestReport.xml)
```

**Why the exit-code-becomes-0 is safe**: `_aggregate_junit_status` in
`src/novetest/run/normalizer.py:736-757` derives Run Record status
from parsed XML (`test_results`), not from returncode. Any test in
`(failed, errored)` → status = "failed" → EXIT_USER_TESTS_FAILED=3 at
the CLI layer. The returncode is only the tiebreaker for build-step
crashes after compile but before any test ran (no test_results entries
AND returncode != 0 → status = "errored"). Same invariant that makes
hotfix-2's Maven `-Dmaven.test.failure.ignore=true` safe.

**H2 REJECTED**: After Fix-D made the task actually run, the XML
landed at `build/reports/jacoco/test/jacocoTestReport.xml` — exactly
where `_run_gradle`'s `candidate` Path computation expects it
(`workspace / "build" / "reports" / "jacoco" / "test" /
"jacocoTestReport.xml"` at `junit_adapter.py:560-568`). No glob
mismatch.

**H3 REJECTED**: `_stage_coverage_xml` worked correctly once the XML
was actually produced; staging path computation is fine. Not a staging
bug.

## 4. F2 fix shape + unit test

**Mechanism**: Adapter writes a generated init-script at
`<artifact_dir>/native/init-ignore-test-failures.gradle` whenever
`collect_coverage and has_jacoco` is true, then passes
`--init-script <path>` to the Gradle invocation. Content (module-level
constant `_GRADLE_IGNORE_FAILURES_INIT_SCRIPT` in `junit_adapter.py`):

```groovy
// Auto-generated by novetest JUnit adapter (hotfix #3, 2026-06-04).
// Makes Test tasks report failures via JUnit XML without failing the
// build, so :jacocoTestReport can run after :test. Safe to delete after
// the run — recreated per run under <artifact_dir>/native/.
allprojects {
    afterEvaluate { project ->
        project.tasks.withType(Test).configureEach {
            ignoreFailures = true
        }
    }
}
```

**Why init-script, not fixture edit**: brief §2 explicitly rejects
Fix-C (fixture-side `finalizedBy`) on user-project-assumption grounds
("real user builds will not be edited by us"). The init-script
mechanism is fixture-cooperation-free — works on any user project
without modifying their `build.gradle` or `build.gradle.kts`.

**Why ONLY in coverage runs**: non-coverage runs keep the natural
exit-1 channel from `:test FAILED` for orchestration callers that
observe the raw adapter returncode. The fix is opt-in via the same
gate as the previous (broken) `--continue` flag was.

**Why under artifact_dir, not /tmp**: keeps the init-script
postmortem-discoverable (alongside the rest of the run's artifacts)
and keeps runs hermetic (no /tmp pollution that could collide between
concurrent runs).

**Unit test**:
`tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco`
asserts:

1. No `--continue` in argv (regression canary against hotfix-2's broken pattern)
2. `--init-script` flag present
3. Path argument ends in `init-ignore-test-failures.gradle`
4. The file exists on disk at that captured path (the contract with Gradle)
5. File contains `ignoreFailures = true` (load-bearing semantic)
6. File contains `withType(Test)` (must target Test tasks, not arbitrary)
7. Path lives under `artifact_dir/native/` not `/tmp` (hermetic)

Sibling negative test
`test_init_script_absent_without_coverage` asserts `--continue` AND
`--init-script` AND `jacocoTestReport` are ALL absent when
`collect_coverage=False`.

## 5. Pre-handoff gate report (equipped-host)

**Host equipment** (per
`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5):

| Tool | Detected version | Matrix floor | Status |
|---|---|---|---|
| JDK | 17.0.19 (Ubuntu OpenJDK) | 17 | ✅ above floor |
| Maven | 3.8.7 (apt-noble) | 3.9 | ⚠️ BELOW floor; see §7 open question |
| Gradle | 8.5 (user-level zip install) | 7.6 | ✅ above floor |

**Gradle version delta vs hotfix-2 gate host (8.14.5 → 8.5)**: the
`--continue` semantic relevant to H1 has been unchanged across Gradle
7.x / 8.x / 9.x lifecycle. The fix is verified on 8.5; Main Branch's
gate on 8.14.5 will exercise the same code path. Forward-compat with
Gradle 9 was already established by hotfix-2's
`testRuntimeOnly("org.junit.platform:junit-platform-launcher")`
fixture edit (preserved here).

**Gate results**:

```
$ uv run mypy
Success: no issues found in 90 source files

$ uv run pytest -q tests/unit tests/integration
1034 passed, 5 skipped in 86.19s (0:01:26)
```

**Skip distribution** (`uv run pytest -rs` for the 5 skipped cases):

- 1× `tests/integration/coverage/test_jest_coverage.py` — requires Node.js
- 2× `tests/integration/run/test_jest_*.py` — requires Node.js
- 2× `tests/integration/run/test_gotest_*.py` — requires `go` on PATH

All 5 skips are unrelated to JUnit. **JUnit-specific skip count = 0** —
all 6 JUnit integration cases (Maven 3 + Gradle 3) EXECUTE and PASS:

```
$ uv run pytest -v tests/integration/run/test_junit_maven.py
tests/integration/run/test_junit_maven.py::test_basic_run_emits_native_result PASSED
tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml PASSED
tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope PASSED
3 passed in 10.27s

$ uv run pytest -v tests/integration/run/test_junit_gradle.py
tests/integration/run/test_junit_gradle.py::test_basic_run_emits_native_result PASSED
tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml PASSED
tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope PASSED
3 passed in 22.01s
```

**Baseline comparison**:

| Where | Passed | Skipped | Failed |
|---|---|---|---|
| Hotfix-2 Run team gate (JDK-less) | 1025 | 14 | 0 |
| Hotfix-2 Main Branch gate (equipped, 8.14.5) | 1033 | 3 | **3** ← merge ABORTED |
| **Hotfix-3 Run team gate (equipped, 8.5) — THIS** | **1034** | **5** | **0** |

Skipped count DROPPED from 14 → 5 (per brief §7 expectation: "skipped
count must DROP"). Failed count = 0 (per brief §7 mandate: "failed
count MUST be 0"). Passed count 1034 ≥ 1033 brief floor.

## 6. Regression canaries

**Hotfix-1 Defect 1 (reports_dir under store.path)** — staging
helpers unchanged; passes via:

```
TestStageReportsDir::test_subpath_under_artifact_dir PASSED
TestStageReportsDir::test_multi_module_per_module_folders PASSED
TestStageReportsDir::test_idempotent_on_retry PASSED
TestStageCoverageXml::test_canonicalizes_basename_to_jacoco_xml PASSED
TestStageCoverageXml::test_multi_module_sub_path PASSED
```

Plus end-to-end: `test_junit_maven.py::test_basic_run_emits_native_result`
(real Maven; asserts `reports_dir` under `artifact_dir/native/reports`)
and Gradle sibling — both PASS.

**Hotfix-1 Defect 3 (identity parens strip)** — unchanged:

```
TestStripTrailingParens (6 cases: Maven passthrough, Gradle strip,
  parametrized signature preserved, Java signature preserved,
  empty-string passthrough, bare () collapse) — all PASS
TestNormalizeTestCase::test_gradle_failure_log_key_uses_stripped_identity PASSED
```

Plus end-to-end: `test_junit_gradle.py::test_basic_run_emits_native_result`
asserts `"#testSubtract"` (no parens) in `failure_logs_raw` — PASS.

**Hotfix-2 Maven `-Dmaven.test.failure.ignore=true`** — preserved
unchanged at `junit_adapter.py:225`; passes via:

```
TestMavenCoverageArgv::test_failure_ignore_flag_present_with_coverage_and_jacoco PASSED
TestMavenCoverageArgv::test_failure_ignore_flag_absent_without_coverage PASSED
TestMavenCoverageArgv::test_failure_ignore_flag_absent_when_jacoco_undeclared PASSED
```

Plus end-to-end: `test_junit_maven.py::test_coverage_run_emits_jacoco_xml`
(real Maven + JaCoCo; asserts `coverage_xml` in `artifact_paths`) — PASS.
Maven `coverage_xml` confirmed at
`artifact_dir/native/coverage/jacoco.xml` on the equipped host.

**Hotfix-2 Gradle 9 launcher dep** —
`testRuntimeOnly("org.junit.platform:junit-platform-launcher")` at
`build.gradle.kts:36` preserved unchanged. Not directly exercised on
this Gradle 8.5 host but backwards-compatible across 7.6/8.x/9.x.

## 7. Open items for PM (not blocking the merge)

1. **Maven 3.8 vs 3.9 floor mismatch.** This host's Maven is 3.8.7
   (apt-noble default — the only version available via the
   pre-authorized `apt-get install maven` path in `.claude/settings.json`
   line 7). The matrix floor in
   `decisions/2026-05-25-supported-engine-matrix.md` is **3.9**.
   `scripts/dev-host-setup.md §5` says `apt-get install maven` which on
   Ubuntu noble yields 3.8.7. **Recommendation**: bump the matrix
   floor to 3.8 (3.8.7 supports every Maven feature the adapter uses
   — `-B`, `-Dmaven.test.failure.ignore=true`, Surefire 3.x goals; no
   Maven-3.9-specific syntax). Alternative: keep 3.9 floor and amend
   `dev-host-setup.md §5` to install Maven 3.9 via Apache binary
   tarball (currently blocked by auto-mode classifier — would need
   user authorization). Less moving parts → floor-bump preferred.

2. **F2 fix shape declared "Fix-D" outside brief's enumerated A/B/C
   options.** The brief listed Fix-A (two-pass), Fix-B (init-script
   `finalizedBy`), and Fix-C (fixture edit). Empirically: Fix-A and
   Fix-B both fail on Gradle 8.5 (and on 7.6/8.x/9.x in general,
   because the underlying task-graph semantic is unchanged); Fix-C is
   rejected by brief on user-project-assumption grounds. The actual
   working mechanism is **init-script `Test.ignoreFailures = true`**
   — a Fix-D variant that's adapter-local, fixture-cooperation-free,
   and behaves identically to Maven hotfix-2's
   `-Dmaven.test.failure.ignore=true` (same exit-code-becomes-0 +
   normalizer-derives-status-from-XML invariant pair). PM may want to
   update the brief retrospectively or just note it in the cycle
   history entry.

3. **`.gradle/` cache directory polluted fixture during diagnostic
   walk.** Was cleaned up before commit (`rm -rf
   tests/fixtures/projects/junit-gradle-basic/.gradle`). The repo's
   `.gitignore` covers `build/` but not `.gradle/`. Not adding to
   `.gitignore` in this hotfix (additive-only scope per brief §6), but
   PM may want a future housekeeping cycle to add it (1-line edit).

4. **`scripts/dev-host-setup.md §5` documentation gap re: dev-host
   `~/.local/share/novetest-toolchains.sh` shim.** That shim doesn't
   exist on this host. Not blocking the gate (toolchains were
   already on PATH), but Manual Test's prior cycle's findings doc
   referenced it. May want a future cycle to either ship that shim or
   remove the reference.

## 8. Slice diff summary

```
$ git diff --stat origin/main HEAD
 WORKLOG.md                                         |  10 +
 ...m-2026-06-04-phase2.5-junit-adapter-hotfix-2.md | 274 +++++++++++++ (hotfix-2 handoff carried over from origin/run-team/junit-adapter-hotfix-2)
 src/novetest/run/adapters/junit_adapter.py         |  24 ++
 .../projects/junit-gradle-basic/build.gradle.kts   |   8 +
 tests/integration/run/test_junit_gradle.py         |  12 +-
 tests/integration/run/test_junit_maven.py          |  31 +-
 tests/unit/run/adapters/test_junit_adapter.py      | 397 ++++++++++++++++
 7 files changed, 746 insertions(+), 10 deletions(-)
```

**Hotfix-3 commit-only diff (this slice's actual contribution)**:

```
 WORKLOG.md                                    |  10 ++++
 src/novetest/run/adapters/junit_adapter.py    |  73 +++++++++++++++++++++++----
 tests/integration/run/test_junit_gradle.py    |  10 +++-
 tests/integration/run/test_junit_maven.py     |  15 +++++-
 tests/unit/run/adapters/test_junit_adapter.py |  70 ++++++++++++++++++++-----
 5 files changed, 153 insertions(+), 25 deletions(-)
```

## 9. Worktree path + branch + commit metadata

- **Worktree**: `/home/yjshin/dev/aispace/novetest-junit-hotfix-3`
- **Branch**: `run-team/junit-adapter-hotfix-3`
- **Base commit**: `caf3dd4` (origin/main; rebased clean from hotfix-2's `41d58ab`)
- **Tip commit before this handoff is committed**: hotfix-2 reapplied + hotfix-3 working tree
- **Tip commit AFTER commit**: set during the commit; will appear in git log as the hotfix-3 atomic commit on top of hotfix-2's reapplied work

## 10. Next steps

1. **Main Branch team**: pre-merge gate on equipped host per
   `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
   §2.5. Expected:
   - `uv run mypy --strict` → clean
   - `uv run pytest -q tests/unit tests/integration` →
     **>=1033 passed, JUnit skip count 0, failure count 0**
   - All 6 JUnit integration tests EXECUTE and PASS (Maven 3 +
     Gradle 3)
   Once green: FF-merge into `origin/main`, push, write verification.

2. **Manual Test team** (after Main Branch merges): re-pass per brief
   §8 scenarios on equipped host:
   - Step 0: CLI smokes — 2 passed
   - Step 2: Maven coverage regression canary —
     `coverage_outcome.kind == "fact-set"` + `coverage_xml` in
     `artifact_paths`
   - Step 4: Gradle coverage (THIS hotfix's primary scope) — same
     assertions
   - Regression canaries: exit 3 + reports_dir under `.novetest/` +
     identity strings byte-identical Maven/Gradle

3. **PM** (after Manual Test PASSED findings):
   - Tick the Phase 2.5 JUnit DoD row in `delivery-phasing.md`
   - Delete the 12 transient files: original 4 (task / handoff /
     verification / findings) + hotfix-1 4 + hotfix-2 4 + hotfix-3 4
   - Write a single combined history entry covering all 3 hotfix
     attempts' lessons. Load-bearing process lesson to pin:
     **adapter-integration changes MUST be gated on an equipped host**
     (both Run team's pre-handoff gate AND Main Branch's pre-merge
     gate). Unit-test-argv-ordering is necessary but not sufficient;
     the runtime task graph semantics are the truth, and only
     exercise on the real toolchain proves the contract. Hotfix-3
     specifically: `--continue` is misleadingly named for dependent
     tasks (Gotcha #1 in WORKLOG); the Gradle equivalent of Maven's
     `failure.ignore` is `Test.ignoreFailures = true` injected via
     init-script.
   - Optional: reconcile the Maven 3.8 vs 3.9 floor/setup mismatch
     (open question #1 above).
