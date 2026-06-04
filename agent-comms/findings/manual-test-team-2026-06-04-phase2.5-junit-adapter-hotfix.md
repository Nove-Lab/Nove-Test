---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: failed
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix
related:
  - agent-comms/verifications/2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - scripts/dev-host-setup.md
---

# Findings — Phase 2.5 JUnit adapter HOTFIX re-pass

**Verdict: failed.**

The hotfix at merged tip `e28e63e` closes **Defect 1** (`reports_dir`
subpath invariant) and **Defect 3** (Gradle/Maven identity
normalization) cleanly. It does NOT close **Defect 2** (`coverage_xml`
population) — the bug reappears in the same shape (`coverage_outcome.kind == "unavailable"`,
`reason == "missing-native-payload"`) for both Maven and Gradle on
the canonical failing-test fixture. It only **structurally** closes
**Defect 4** (CLI smoke present): the smoke test exists and runs
rather than skips, satisfying the decision §1 "must not skip-gate"
clause, but its `returncode in (0, 1)` assertion is wrong by the
project's own exit-code constants (`EXIT_USER_TESTS_FAILED = 3` per
`src/novetest/cli/output.py:15`) and **fires false-positive on the
canonical fixture**.

Two additional discoveries surfaced during equip-and-exercise:

1. **Gradle 9.x incompatible with the fixture's `build.gradle.kts`** —
   matrix ceiling needs pinning ≤ 8.x.
2. **Verification doc and test source drifted from the CLI's own
   exit-code constants** — the doc says "exit=1" for user-tests-failed
   and the smoke's assertion treats exit 1 as the user-tests-failed
   code; both contradict `EXIT_USER_TESTS_FAILED = 3`.

Per the equip-and-exercise decision §1 the verdict cannot be `passed`
while the CLI-level smoke fires false on the canonical happy-path
fixture, even though the smoke itself executes (does not skip).
**Manual Test recommends a second hotfix cycle** scoped narrowly to
Defect 2 + the Defect 4 assertion + matrix/fixture Gradle ceiling.

## Host equipping summary

This is the first verification run on the host fully equipped per
`scripts/dev-host-setup.md`. Versions detected:

| Tool | Detected | Floor (matrix) | Notes |
|---|---|---|---|
| JDK | 17.0.19 (Temurin) | 17 | tarball install, `~/.local/opt/jdk17/` |
| Maven CLI | 3.9.16 | 3.8 | tarball install, `~/.local/opt/maven/` |
| `maven-surefire-plugin` (in fixture pom) | 3.2.5 | 3.0 | declared in `junit-maven-basic/pom.xml` |
| Gradle CLI | **8.14.5** | 7.6 | tarball install, `~/.local/opt/gradle/`; see "Gradle 9 incompatibility" below for why 9.5.1 was rolled back to 8.14.5 |
| `junit-jupiter` (in fixture build.gradle.kts) | 5.10.2 | 5.10 | declared via `junit-bom:5.10.2` |
| `jacoco-maven-plugin` (in fixture pom) | 0.8.11 | 0.8.11 | declared in `junit-maven-basic/pom.xml` |

Gate A (5/5 floors satisfied) passed on the equipped host. The
verification proceeded.

## Per-step PASS/FAIL summary

| Step | Defect | Result | Detail |
|---|---|---|---|
| Gate A | — | ✅ PASS | all five floor checks met (after Gradle downgrade) |
| Step 0 — CLI smoke gate (decision §1) | Defect 4 (process gap) | ⚠️ MIXED | Both smokes RUN (no skip-gate) so the §1 mandate is structurally met. Both smokes FAIL on assertion `returncode in (0, 1)` because the canonical fixture emits `EXIT_USER_TESTS_FAILED = 3`. See "Defect 4 — partially closed". |
| Step 1 — `reports_dir` under store.path | Defect 1 | ✅ **PASS** | Maven: `reports_dir = run/artifacts/run_*/native/reports`, relative, under `.novetest/`. On disk: `TEST-com.example.CalculatorTest.xml` staged. `is_relative_to(store.path)` invariant holds. |
| Step 2 — `coverage_xml` populated | Defect 2 | ❌ **FAIL** | Maven: `coverage_xml` absent from `artifact_paths`; `coverage_outcome.kind == "unavailable"`, `reason == "missing-native-payload"`. The `target/jacoco.exec` is produced (agent runs), but `target/site/jacoco/jacoco.xml` is NEVER written because `jacoco:report` is sequenced after `surefire:test` on the same Maven command line, and Maven aborts at the failing test phase before `report` executes. See "Defect 2 — root cause". |
| Step 3 — Gradle/Maven identity parity | Defect 3 | ✅ **PASS** | After Gradle downgrade. Gradle: 6 tests, 4 passed/1 failed/1 skipped; failed identity = `com.example.CalculatorTest#testSubtract` (no trailing parens). `diff /tmp/id-mvn.txt /tmp/id-gradle.txt` returns empty (byte-identical). |
| Step 4 — Gradle coverage shape | Defect 2 (Gradle path) | ❌ **FAIL** | Gradle: same shape as Step 2. `coverage_xml` absent; `:jacocoTestReport` never runs because `:test` task fails first. |
| Step 5 — Multi-module coverage_xml dichotomy | — | ⊘ SKIPPED | No multi-module fixture available; verification doc explicitly allows skipping. |
| Edge case 1 — `reports_dir` retry idempotency | — | ✅ PASS | Two consecutive `novetest run` invocations on the same Maven workspace: `init=0, run1=3, run2=3`. Both produce valid envelopes. Two `run_*` artifact directories present (one per run). `shutil.copytree(..., dirs_exist_ok=True)` works as designed. |

## Defect-by-defect detail

### Defect 1 — FIXED ✅

Reproducer:

```bash
cp -r tests/fixtures/projects/junit-maven-basic /tmp/junit-mvn-smoke
cd /tmp/junit-mvn-smoke
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run > /tmp/run-maven.json
```

Observed:

```
exit = 3   (= EXIT_USER_TESTS_FAILED; canonical for "tests ran, some failed")
ok = true
data.memory_entry.run_record.engine_name = "junit"
data.memory_entry.run_record.artifact_paths.reports_dir = "run/artifacts/run_01KT8JP5VHEQXQSK2FMCSEP5D8/native/reports"
data.memory_entry.run_record.summary_counts = {passed:4, failed:1, skipped:1, errored:0, total:6}
```

On disk:
`.novetest/run/artifacts/run_01KT8JP5VHEQXQSK2FMCSEP5D8/native/reports/TEST-com.example.CalculatorTest.xml`
exists. Path is fully under `.novetest/` (the Project Store path) and
the `is_relative_to(store.path)` invariant in
`src/novetest/orchestration/workflows/run.py:85-89` holds. No
`cli-error` envelope from `.relative_to` failure — that's the
regression canary the hotfix established, and it does NOT fire.

### Defect 2 — NOT FIXED ❌  (P1 reopens)

Reproducer:

```bash
cd /tmp/junit-mvn-smoke
rm -rf .novetest target
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run --coverage > /tmp/run-maven-cov.json
```

Observed:

```
exit = 3
ok = true
data.memory_entry.run_record.artifact_paths.keys() = ['reports_dir', 'stderr', 'stdout']  ← coverage_xml ABSENT
data.coverage_outcome.kind = "unavailable"
data.coverage_outcome.reason = "missing-native-payload"
```

On disk (after the run):

```
/tmp/junit-mvn-smoke/target/jacoco.exec       ← present (the agent ran)
/tmp/junit-mvn-smoke/target/site/             ← DOES NOT EXIST
/tmp/junit-mvn-smoke/.novetest/run/artifacts/run_*/native/coverage/   ← DOES NOT EXIST
```

#### Root cause

The hotfix amended `src/novetest/run/adapters/junit_adapter.py:209` to
append `org.jacoco:jacoco-maven-plugin:report` to the Maven argv when
`collect_coverage and has_jacoco`. The resulting Maven invocation
on the equipped host is:

```
mvn -B test org.jacoco:jacoco-maven-plugin:report -Dsurefire.reportFormat=plain -Dsurefire.useFile=false
```

Maven executes goals in the order they appear on the command line.
When `test` (which runs `surefire-plugin:test` via the lifecycle)
encounters the deliberately-failing `testSubtract`, surefire raises
`MojoFailureException`. **Maven aborts the entire reactor at that
point — by design.** The subsequent `org.jacoco:jacoco-maven-plugin:report`
goal NEVER executes. `target/site/jacoco/jacoco.xml` is therefore
never written, and the adapter's downstream "look for jacoco.xml"
step (at `junit_adapter.py:325` per the verification doc citation)
finds nothing → `coverage_outcome` projects as `unavailable`.

The fix is one flag on the same line:

```python
argv: list[str] = [mvn_path, "-B", "test"]
if collect_coverage and has_jacoco:
    argv.append("-Dmaven.test.failure.ignore=true")    # ← THIS
    argv.append("org.jacoco:jacoco-maven-plugin:report")
```

`-Dmaven.test.failure.ignore=true` tells Surefire to report the
failure but NOT raise `MojoFailureException`, so the build continues
and `jacoco:report` runs. The user-tests-failed signal is still
carried in the Surefire XML (which the adapter parses for test
outcomes) and surfaces up to `EXIT_USER_TESTS_FAILED`. Net effect:
build status unchanged from a user-visibility standpoint, but
`jacoco.xml` actually gets produced.

The integration test
`tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml`
encodes the wrong assumption in its docstring comment:

```python
# Failing test still fails; coverage XML still emitted because the
# JaCoCo agent is in the test phase and the report goal runs in the
# test lifecycle.
```

The first half is true (the agent runs in the test phase). The
second half is false (Maven does NOT run subsequent CLI-positional
goals after a phase failure). The agent collects coverage data into
`jacoco.exec`, but `jacoco:report` doesn't run to serialize it as
XML.

The Gradle path has the **same shape** at `junit_adapter.py:484`:

```python
argv.extend(["test", "--no-daemon"])
...
if collect_coverage and has_jacoco:
    argv.append("jacocoTestReport")
```

When `:test` fails, Gradle stops the task graph before
`:jacocoTestReport` can run. Same fix structure: add `--continue` to
the argv (or `test.ignoreFailures = true` per build config, but the
adapter does not edit the build script). Recommended:

```python
argv.extend(["test", "--no-daemon"])
if collect_coverage and has_jacoco:
    argv.append("--continue")     # ← THIS
    argv.append("jacocoTestReport")
```

### Defect 3 — FIXED ✅

After downgrading Gradle to 8.14.5 (see "New issue: Gradle 9
incompatibility" below), the cross-build-tool identity check:

```
Maven  failed identity: com.example.CalculatorTest#testSubtract
Gradle failed identity: com.example.CalculatorTest#testSubtract
diff /tmp/id-mvn.txt /tmp/id-gradle.txt   → no output (byte-identical)
```

No `test_results[].node_id` value across either run ends in `()`.
The `_strip_trailing_parens` normalization at
`junit_adapter.py:720` is doing what the verification doc claims.

Note: the verification doc reads `.identity` and `.status` from the
projected envelope:

```bash
jq '... | select(.status=="failed") | .identity'
```

The actual projected envelope shape uses `.outcome` and `.node_id`
(per `src/novetest/models/run_record.py` test_results projection).
Both names map to the same underlying field set; the doc-side
identifier drift is documented in "Verification doc shape drift"
below and is **not** a defect — it's a verification-doc-only
correction.

### Defect 4 — STRUCTURALLY CLOSED, ASSERTION WRONG ⚠️

The hotfix added `test_cli_smoke_run_emits_envelope` to both
`test_junit_maven.py` and `test_junit_gradle.py`. The tests RUN
(no `shutil.which("mvn|gradle") is None` skip-gate fires on the
equipped host), so the **decision §1 "must not skip" clause is
structurally met**. That's the process-gap closure.

However, the assertion is:

```python
assert run_result.returncode in (0, 1), (
    f"CLI returned exit {run_result.returncode}; "
    f"expected 0 (pass) or 1 (some test failed). ..."
)
```

The CLI's own exit-code constants are in `src/novetest/cli/output.py`:

```python
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_USAGE = 2
EXIT_USER_TESTS_FAILED = 3   # ← canonical "tests ran, some failed"
EXIT_ENGINE_MISSING = 4
EXIT_STORAGE = 5
```

`EXIT_USER_TESTS_FAILED` is **3**, not 1. The canonical fixture has
one deliberately failing test (`testSubtract`) — so the CLI correctly
exits 3. The smoke's assertion `(0, 1)` rejects this and fails.

Both smokes (Maven AND Gradle, after Gradle downgrade) fire false on
this assertion:

```
FAILED tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope
  - AssertionError: CLI returned exit 3; expected 0 (pass) or 1 (some test failed)
FAILED tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
  - AssertionError: CLI returned exit 3; expected 0 (pass) or 1 (some test failed)
```

The fix is one tuple edit:

```python
assert run_result.returncode in (0, 3), (
    f"CLI returned exit {run_result.returncode}; "
    f"expected 0 (all passed) or 3 (some user tests failed). "
    f"Higher exit codes indicate CLI-error (engine missing, storage, "
    f"contract violation like Defect 1) and MUST not occur on the "
    f"canonical happy-path fixture."
)
```

Alternative: `assert run_result.returncode != 2` (treats only
EXIT_USAGE as the smoke-fail signal). The narrower `(0, 3)` is
preferable because it also catches `EXIT_ENGINE_MISSING = 4` —
which would mean the equipping path itself broke.

Note on the verification-doc claim that **Gradle's smoke passed in
Main Branch's pre-handoff gate** (line 42-44: "1023 passed, 11
skipped"): that gate ran on a JDK-less / `mvn`-less / `gradle`-less
host. The smokes skipped (didn't run), so the {0, 1} assertion was
never evaluated. The hotfix's gate did not exercise the smoke at all.
This is the exact failure mode the equip-and-exercise decision §1 was
written to catch — and it caught it on this verification host.

## New issue: Gradle 9.x incompatibility with the fixture

When Gradle 9.5.1 (the current latest stable) was installed initially,
`gradle test` against `tests/fixtures/projects/junit-gradle-basic`
fails at the JUnit Platform load step:

```
FAILURE: Build failed with an exception.
* What went wrong:
Execution failed for task ':test' (registered by plugin 'org.gradle.jvm-test-suite').
> Test process encountered an unexpected problem.
   > Could not start Gradle Test Executor 1.
      > Failed to load JUnit Platform.  Please ensure that all JUnit Platform
        dependencies are available on the test's runtime classpath, including
        the JUnit Platform launcher.
```

Root cause: Gradle 9.x **dropped the implicit injection** of
`org.junit.platform:junit-platform-launcher` into the
`testRuntimeClasspath` that earlier Gradle versions added when
`useJUnitPlatform()` was declared. The fixture's
`build.gradle.kts` does not declare the launcher explicitly:

```kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    // missing: testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

This is a published Gradle 9 migration note (the launcher must now be
declared by the user). On Gradle 8.14.5 the implicit injection still
happens, and `useJUnitPlatform()` works without the explicit
dependency.

Mitigation options for PM (one OR the other; not both required):

A. **Pin matrix ceiling** to Gradle 8.x in
   `decisions/2026-05-25-supported-engine-matrix.md` row
   "Maven (Surefire) OR Gradle (`useJUnitPlatform()`)" and document
   the launcher migration as a future-cycle task.
B. **Add the launcher dependency to the fixture's
   `build.gradle.kts`**:
   ```kotlin
   testRuntimeOnly("org.junit.platform:junit-platform-launcher")
   ```
   This is forward-compatible (works on 7.6, 8.x, 9.x) and is the
   migration path the JUnit project itself recommends for Gradle
   users.

Option B is the structurally correct fix (the missing dependency was
always present-by-grace; making it explicit removes the dependency on
Gradle's implicit-injection behavior). Recommend B paired with a
matrix ceiling annotation that records 8.14.5 and 9.5.1 as both
tested (with the launcher dep present).

This is independent of the hotfix's scope — the fixture issue existed
before the hotfix and is only visible now because the equipped host
caused it to be reachable.

## Verification doc shape drift (non-defect, doc-correction only)

The verification doc has two surface-level inaccuracies that did not
affect the verdict but should be corrected before next cycle. Neither
is a code defect.

1. **Exit code in Step 1's expected envelope.** Doc line 100:
   > `exit=1` (Calculator test has off-by-one in `testSubtract`; user tests failed = exit 1, NOT exit 2).

   Actual canonical exit code is **3** per `output.py:15`
   `EXIT_USER_TESTS_FAILED = 3`. The "NOT exit 2" half is correct
   (exit 2 is `EXIT_USAGE`, reserved for CLI contract violations
   like the old Defect 1 surface).

2. **Test result field names in Step 3's `jq` queries.** Doc lines
   183, 186, 193, 194:
   > `jq -er '.data.memory_entry.run_record.test_results[] | select(.status=="failed") | .identity'`

   Actual projected envelope field names are `.outcome` (not
   `.status`) and `.node_id` (not `.identity`). The `.failure_logs`
   dict KEY shape mentioned in line 199-205 maps to `.node_id`
   values, post-`_strip_trailing_parens`.

## Edge cases probed (verification doc §"Critical edge cases worth probing")

1. **`reports_dir` retry idempotency** — ✅ PASS. Two consecutive
   `novetest run` on `/tmp/junit-mvn-smoke`: `init=0`, `run1=3`,
   `run2=3`. Both produce valid envelopes; two distinct `run_*` IDs
   in `.novetest/run/artifacts/`. The
   `shutil.copytree(..., dirs_exist_ok=True)` at the staging path
   does not blow up on the pre-existing dest.

2. **`payload["warnings"]` carrying `missing-jacoco`** — not probed.
   `payload["warnings"]` is internal to the adapter and not surfaced
   on the user-facing envelope (`top-level warnings: []` and
   `data.memory_entry.run_record.metadata` does not carry the kind).
   The user-facing surface check is
   `data.coverage_outcome.kind == "unavailable"` with `reason`
   non-empty — which IS what we saw, but with reason
   `"missing-native-payload"` instead of the
   `"missing-jacoco"` shape the doc anticipates. The
   `missing-jacoco` shape applies when the pom itself doesn't declare
   the plugin; here the plugin is declared but the report goal
   doesn't run — different reason path.

3. **Maven multi-module reports staging** — not scaffolded
   (no multi-module fixture); verification doc allows skip.

4. **JDK 11 vs JDK 17 floor** — host runs JDK 17.0.19. No JDK 11
   regression to surface. The hotfix did NOT amend the readiness
   probe to hard-reject < 17 (open item #3 in the run team handoff).
   The vendored Console Launcher 1.11.4 functions on this JDK 17;
   `data.memory_entry.run_record.metadata.console_launcher_version`
   surfaces as `"1.11.4"` and `console_launcher_sha256` matches the
   pinned hash.

5. **Gradle parametrized display name passthrough** — not probed
   (would require fixture edit, out of scope; deferred to next
   cycle).

6. **Defect-1 regression canary** — ✅ PASS. No `cli-error` envelope;
   no `.relative_to(store.path)` ValueError. The exit-3 outcome
   is `EXIT_USER_TESTS_FAILED`, NOT a `EXIT_USAGE = 2` contract
   violation. The Step 0 smokes failed on assertion shape, not on
   contract — exit 3 ∉ {0, 1, 2}.

## Recommendations for PM

### Required for `passed` verdict on next pass

1. **Defect 2 — Maven fix.** Add `-Dmaven.test.failure.ignore=true`
   to `junit_adapter.py:_run_maven` argv when
   `collect_coverage and has_jacoco`. One-line change. Update the
   integration test's misleading docstring comment ("the report goal
   runs in the test lifecycle" — it doesn't unless surefire's
   failure is ignored).

2. **Defect 2 — Gradle fix.** Add `--continue` to
   `junit_adapter.py:_run_gradle` argv when
   `collect_coverage and has_jacoco`. One-line change.

3. **Defect 4 — assertion fix.** Change `returncode in (0, 1)` to
   `returncode in (0, 3)` in both
   `tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope`
   and `tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope`.
   Update the inline comment ("Exit 0 (all passed) or 1 (some test
   failed)" → "Exit 0 (all passed) or 3 (some user tests failed,
   per EXIT_USER_TESTS_FAILED constant)"). One-tuple-edit per file.

### Recommended (matrix / fixture hygiene)

4. **Gradle ceiling pinning.** Update
   `decisions/2026-05-25-supported-engine-matrix.md` row for Gradle
   to record `tested ceiling: 8.14.5` and explicitly note Gradle 9.x
   incompatibility with the fixture as-shipped. PM's call whether to
   open an immediate slice to make the fixture forward-compatible
   (Option B in the "New issue" section above) or to defer.

5. **Verification-doc corrections.** Update
   `verifications/2026-06-04-phase2.5-junit-adapter-hotfix.md` (or
   leave it as historical record and reference this finding) for
   the two doc drifts: (a) `exit=1` → `exit=3` in Step 1; (b) `.status`
   / `.identity` → `.outcome` / `.node_id` in Step 3's `jq` queries.
   These are doc-only — no code change implied.

### Informational

6. **PATH-file maintenance.** `~/.local/share/novetest-toolchains.sh`
   on the equipped host now points `~/.local/opt/gradle` at the
   8.14.5 install (rolled back from the originally-installed 9.5.1).
   The Gradle 9.5.1 install remains under
   `~/.local/opt/gradle-9.5.1/` for re-probing once the fixture is
   forward-compatible. No PM action required.

## Process notes

- Cycle followed `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
  literally: Gate A pre-flight (5/5 floors) → Step 0 CLI smoke
  (executed not skipped — §1 met) → Steps 1-5 + 6 edge cases.
- `Write` tool was blocked at one point by background-session
  worktree isolation (GOTCHAS.md §"Write/Edit blocked"); used
  `cat > … <<'EOF'` heredoc fallback for this findings file. Byte
  count: ~14k.
- Two transient bash classifier outages mid-session resolved on
  retry; no impact on outcomes.
- Scratch fixture copies at `/tmp/junit-mvn-smoke` and
  `/tmp/junit-gradle-smoke` are retained; reproducers above are
  one-command repeatable. Manual workspace's
  `tests/manual-test-workspace/host-equip-2026-06-04/` from the prior
  session is unchanged.

## Effective date

2026-06-04. Verdict-failed; queue a second hotfix narrowly scoped to
Defect 2 (both build tools) + Defect 4 assertion + matrix Gradle
ceiling. The hotfix's correct work on Defects 1 and 3 should NOT be
unwound — the second hotfix should be additive.
