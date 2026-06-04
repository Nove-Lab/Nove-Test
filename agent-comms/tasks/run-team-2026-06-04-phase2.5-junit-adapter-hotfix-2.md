---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix-2
status: pending
related:
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/verifications/2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
---

# Phase 2.5 — JUnit adapter HOTFIX #2 (Defect 2 reopen + Defect 4 assertion bug + Gradle 9 fixture compat)

## TL;DR

The 2026-06-04 JUnit hotfix #1 (`e28e63e`) closed Defects 1 + 3
cleanly but Manual Test re-pass on the equipped host
(`findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`)
verdict-failed because:

| # | Issue | Severity | Fix shape |
|---|---|---|---|
| 1 | **Defect 2 reopens** — `coverage_xml` still absent on canonical fixture. Hotfix #1's added `jacoco:report` goal never runs because Maven aborts at the failing-test phase before the report goal. Same shape on Gradle: `:test` fails → `:jacocoTestReport` never runs. | P1 | Maven: append `-Dmaven.test.failure.ignore=true`. Gradle: append `--continue`. Both one-line. |
| 2 | **Defect 4 assertion** — both `test_cli_smoke_run_emits_envelope` cases assert `returncode in (0, 1)`. Canonical fixture has a failing test → CLI exits **3** per `EXIT_USER_TESTS_FAILED`; assertion rejects 3 → smokes false-fail. **The §1 "must not skip-gate" mandate WORKED** — smokes ran rather than skipped and the bug was caught. | P0 (process: bug shipped at `e28e63e`) | One tuple edit per file: `(0, 1)` → `(0, 3)`. |
| 3 | **Gradle 9.x fixture incompatibility** — Gradle 9 dropped implicit injection of `junit-platform-launcher` into `testRuntimeClasspath`. The fixture's `build.gradle.kts` does not declare it explicitly. Manual Test rolled back to Gradle 8.14.5 to proceed. | P2 (forward-compat) | Add `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` to `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts`. Forward-compatible across 7.6 / 8.x / 9.x. |

The hotfix #1's correct work on Defects 1 and 3 stays in place — do
NOT unwind it. This slice is additive.

**Verification doc / fixture doc drift items** (Manual Test rec #5) are
PM-picked up separately and out of scope for Run team here.

**Estimated scope:** very small slice (~150 LOC change total, mostly
tests). The fixes are precisely prescribed below; the bulk of effort is
re-verifying on the equipped host (which is now available — see
`findings/manual-test-team-2026-06-04-host-equip.md`).

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`** — primary spec; defect 2 + defect 4 + Gradle 9 explanations include exact file:line refs
4. `agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md` §"Defect closure evidence" — the prior cycle's evidence; preserve unchanged
5. `agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2 (and its same-day errata) — the corrected CLI smoke template (assertion `(0, 3)`)
6. `src/novetest/cli/output.py:12-17` — exit-code constants (`EXIT_USER_TESTS_FAILED = 3`)
7. `src/novetest/run/adapters/junit_adapter.py:209` (Maven argv block) and `:484` (Gradle argv block) — fix sites
8. `tests/integration/run/test_junit_maven.py:211` and `tests/integration/run/test_junit_gradle.py:175` — assertion fix sites
9. `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts` — launcher dep add site

---

## 1. Defect 2 — Maven argv fix (one line)

`src/novetest/run/adapters/junit_adapter.py` Maven argv composition.
Current shape (hotfix #1, line ~209):

```python
argv: list[str] = [mvn_path, "-B", "test"]
if collect_coverage and has_jacoco:
    argv.append("org.jacoco:jacoco-maven-plugin:report")
```

The `jacoco:report` goal is positional-after-`test`. Maven runs goals
in the order they appear on the command line. When `surefire:test`
encounters a failing test, surefire raises `MojoFailureException` and
**Maven aborts the entire reactor**. The subsequent `jacoco:report`
goal never executes. `target/site/jacoco/jacoco.xml` is therefore
never written.

Fix:

```python
argv: list[str] = [mvn_path, "-B", "test"]
if collect_coverage and has_jacoco:
    argv.append("-Dmaven.test.failure.ignore=true")
    argv.append("org.jacoco:jacoco-maven-plugin:report")
```

`-Dmaven.test.failure.ignore=true` tells Surefire to **report**
test failures but NOT raise `MojoFailureException`, so the build
continues and `jacoco:report` runs. The user-tests-failed signal is
still carried in the Surefire XML the adapter parses for test
outcomes, which propagates up to `EXIT_USER_TESTS_FAILED` correctly.
Net effect: build status unchanged from user-visibility standpoint;
`jacoco.xml` actually gets produced.

**Important — only apply when `collect_coverage and has_jacoco`.** Do
NOT toggle `failure.ignore` in non-coverage runs; the existing exit
behavior must stay the same when JaCoCo isn't requested.

Also: update the misleading docstring at
`tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml`:

```python
# OLD (misleading):
# Failing test still fails; coverage XML still emitted because the
# JaCoCo agent is in the test phase and the report goal runs in the
# test lifecycle.

# NEW (accurate):
# Failing test still surfaces as exit 3 (EXIT_USER_TESTS_FAILED); the
# `-Dmaven.test.failure.ignore=true` flag lets Maven continue past the
# Surefire failure so the subsequent `jacoco:report` goal actually
# runs and writes target/site/jacoco/jacoco.xml. Without that flag,
# Maven aborts at the test phase and JaCoCo XML is never serialized.
```

## 2. Defect 2 — Gradle argv fix (one line)

`src/novetest/run/adapters/junit_adapter.py` Gradle argv composition,
line ~484:

```python
argv.extend(["test", "--no-daemon"])
...
if collect_coverage and has_jacoco:
    argv.append("jacocoTestReport")
```

Same root cause shape. When `:test` task fails, Gradle stops the task
graph before `:jacocoTestReport` can run.

Fix:

```python
argv.extend(["test", "--no-daemon"])
...
if collect_coverage and has_jacoco:
    argv.append("--continue")
    argv.append("jacocoTestReport")
```

`--continue` tells Gradle to keep running independent tasks even when
some fail. The `:jacocoTestReport` task is independent of
`:test`'s outcome (it depends on the JaCoCo agent's `jacoco.exec`
file, which is produced when `:test` runs the JaCoCo-instrumented
JVM regardless of pass/fail).

**Same scope rule as Maven:** apply ONLY when `collect_coverage and has_jacoco`.

## 3. Defect 4 — assertion tuple edit (two files)

`tests/integration/run/test_junit_maven.py:211`:

```python
# OLD (bug):
assert run_result.returncode in (0, 1), (
    f"CLI returned exit {run_result.returncode}; "
    f"expected 0 (pass) or 1 (some test failed). "
    f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
)

# NEW (correct):
assert run_result.returncode in (0, 3), (
    f"CLI returned exit {run_result.returncode}; "
    f"expected 0 (EXIT_OK, all passed) or 3 (EXIT_USER_TESTS_FAILED, "
    f"some user tests failed). Exit codes 1 (EXIT_GENERIC), 2 (EXIT_USAGE), "
    f"4 (EXIT_ENGINE_MISSING), 5 (EXIT_STORAGE) all indicate "
    f"contract or environment violations and MUST not occur on the "
    f"canonical happy-path fixture. See src/novetest/cli/output.py:12-17."
)
```

Same edit at `tests/integration/run/test_junit_gradle.py:175`.

The exit-code constants are in `src/novetest/cli/output.py:12-17` —
do NOT inline numeric literals beyond `(0, 3)`; the assertion is the
narrow gate. The error message documents the broader code map for
future readers.

## 4. Gradle 9.x fixture compat (forward-compatible fix)

`tests/fixtures/projects/junit-gradle-basic/build.gradle.kts`,
`dependencies { ... }` block:

```kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")  // ← ADD THIS
}
```

Why: Gradle 9 dropped the implicit injection of
`junit-platform-launcher` into `testRuntimeClasspath` that earlier
Gradle versions added when `useJUnitPlatform()` was declared. The
fixture's reliance on that implicit injection breaks on Gradle 9.x.
Adding the dependency explicitly works on Gradle 7.6, 8.x, AND 9.x —
the JUnit project itself recommends this for Gradle users post-9.

After this addition the fixture is forward-compatible. PM will
separately consider whether to bump
`decisions/2026-05-25-supported-engine-matrix.md` Gradle tested-ceiling
to 9.x (Manual Test rec #4) — that decision-doc amendment is PM
territory, not yours. You just make the fixture forward-compatible.

## 5. Files touched (estimated)

| File | Change |
|---|---|
| `src/novetest/run/adapters/junit_adapter.py` | +2 lines (one per build tool, conditional on `collect_coverage and has_jacoco`) |
| `tests/integration/run/test_junit_maven.py` | Assertion tuple `(0, 1)` → `(0, 3)`; docstring update on `test_coverage_run_emits_jacoco_xml`; CLI smoke message text |
| `tests/integration/run/test_junit_gradle.py` | Assertion tuple `(0, 1)` → `(0, 3)`; CLI smoke message text |
| `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts` | +1 line: `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` |
| `tests/unit/run/adapters/test_junit_adapter.py` (or wherever appropriate) | Add a unit test asserting the Maven argv contains `-Dmaven.test.failure.ignore=true` when `collect_coverage=True and has_jacoco=True`, AND verifying it does NOT contain that flag when `collect_coverage=False`. Symmetric Gradle test for `--continue`. |
| `WORKLOG.md` | New entry per protocol. |

Likely diff scope: ~30 LOC src + ~50 LOC tests + 1 line fixture +
docstring touch-ups. Smallest cycle in recent memory.

## 6. Out of scope (explicit)

These are surfaced by Manual Test but NOT part of this hotfix:

- **Verification-doc shape drift corrections** (rec #5 from
  hotfix #1 findings) — `exit=1` → `exit=3` in Step 1's envelope spec;
  `.status`/`.identity` → `.outcome`/`.node_id` in Step 3 `jq` queries.
  Both are verification-doc-only; Main Branch picks up when it writes
  the next verification doc.
- **Matrix Gradle tested-ceiling bump** (rec #4) — PM decision-doc
  amendment in `2026-05-25-supported-engine-matrix.md`. PM picks up
  separately.
- **JDK 11 readiness probe hard-reject** (handoff #1 open item #3) —
  unchanged by this slice; Run team handoff #1 had it as deferred
  follow-up.
- **Maven multi-module coverage_xml dichotomy** (verification doc
  Step 5) — no multi-module fixture; deferred (handoff #1 followup #6).
- **`adapter-unparseable-output` overload audit** — separate cargo
  cycle scope concern; see `tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md`.
- **Backfilling CLI smokes to pytest / jest / go-test** — equip-and-
  exercise §2 binds new adapters, not retroactive backfills. Optional.

Do **not** introduce these in this slice. File a `questions/` entry
if you find yourself wanting to.

## 7. Definition of Done bullets

Tick when ALL are true:

- [ ] `junit_adapter.py` `_run_maven` appends `-Dmaven.test.failure.ignore=true`
      *before* `org.jacoco:jacoco-maven-plugin:report` in the argv, ONLY
      when `collect_coverage and has_jacoco`. Unit-tested.
- [ ] `junit_adapter.py` `_run_gradle` appends `--continue` *before*
      `jacocoTestReport` in the argv, ONLY when `collect_coverage and
      has_jacoco`. Unit-tested.
- [ ] `tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope`
      asserts `returncode in (0, 3)` with updated error message.
- [ ] `tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope`
      asserts `returncode in (0, 3)` with updated error message.
- [ ] `tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml`
      docstring updated to reflect actual semantics (`failure.ignore` flag
      lets Maven continue past surefire failure).
- [ ] `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts` declares
      `testRuntimeOnly("org.junit.platform:junit-platform-launcher")`.
- [ ] `uv run pytest -q tests/unit tests/integration` on JDK-less host:
      no regressions vs hotfix #1 baseline (`1020 passed + 14 skipped + 0
      failed`). CLI smokes still skip-gate without toolchain.
- [ ] `uv run mypy --strict` clean.
- [ ] Handoff cites the §1, §2, §3, §4 fix shapes and confirms hotfix #1's
      Defect 1 + Defect 3 fixes are preserved unchanged.

## 8. Re-verification (Manual Test re-pass on equipped host)

After Main Branch FF-merges and the slice is on `main`, Manual Test
re-runs the hotfix #1 verification scenarios on the equipped host:

```sh
# Reproduce Step 0 (CLI smokes — should now PASS):
uv run pytest -q tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope \
                tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
# Expected: 2 passed, 0 failed (or 2 skipped if reverting to JDK-less host;
# but on Manual Test's equipped host, both must pass)

# Reproduce Step 2 (Maven coverage):
cd /tmp/junit-mvn-smoke
rm -rf .novetest target
uv run --project <repo> novetest init
uv run --project <repo> novetest run --coverage > /tmp/run-maven-cov.json
jq '.data.coverage_outcome.kind' /tmp/run-maven-cov.json
# Expected: "fact-set" (was "unavailable" pre-fix)
jq '.data.memory_entry.run_record.artifact_paths | keys' /tmp/run-maven-cov.json
# Expected: includes "coverage_xml" (was absent pre-fix)

# Reproduce Step 4 (Gradle coverage):
# Same shape as Step 2 against /tmp/junit-gradle-smoke with --coverage

# Spot-check Step 1 (Defect 1 regression canary):
cd /tmp/junit-mvn-smoke; uv run --project <repo> novetest run
# Expected: exit 3 (unchanged); reports_dir under .novetest/

# Spot-check Step 3 (Defect 3 regression canary):
# Same as hotfix #1 — identity strings byte-identical between Maven and Gradle.
```

All Step-1 (Defect 1) and Step-3 (Defect 3) scenarios from hotfix #1
must remain ✅ — they're additive guardrails this slice doesn't touch.

## 9. Handoff expectations

When ready to merge, write
`agent-comms/handoffs/run-team-2026-XX-XX-phase2.5-junit-adapter-hotfix-2.md`
with:

1. **DoD bullets believed closed** — list each from §7 with a one-line
   evidence pointer.
2. **Maven coverage before/after** — paste the
   `data.coverage_outcome.kind` value (was `"unavailable"` →
   should be `"fact-set"`) and the `artifact_paths` key set (must
   include `"coverage_xml"`).
3. **Gradle coverage before/after** — same shape.
4. **CLI smoke before/after** — paste the assertion's evaluation
   on the canonical fixture: exit 3 (canonical) now passes the
   `(0, 3)` set; previously failed `(0, 1)`.
5. **Hotfix #1 Defects 1 + 3 regression canary** — confirm `reports_dir`
   still under `store.path` and identity strings still byte-identical
   between Maven and Gradle.
6. **Slice diff summary** — `git diff --stat`.
7. **Test counts post-fix** — match or exceed hotfix #1's
   `1020 passed + 14 skipped + 0 failed` baseline on JDK-less.

PM picks up the handoff, dispatches Main Branch for FF-merge, then
Manual Test for re-pass. When Manual Test files PASSED findings, PM
closes the JUnit cycle: deletes ALL eight transient files (original
4: task / handoff / verification / failed findings; hotfix #1 4:
task / handoff / verification / failed findings; hotfix #2 4:
this task / handoff / verification / passing findings), ticks the
Phase 2.5 JUnit DoD bullet in `delivery-phasing.md`, writes a single
combined history entry covering all 3 attempts' lessons.

## 10. Sanity check before starting

If you find yourself wanting to:

- Touch the JDK 11 readiness probe → STOP. Out of scope; handoff #1
  followup #3 captures it.
- Add a `--per-test-class` opt-in → STOP. Out of scope.
- Modify the `EXIT_USER_TESTS_FAILED` constant → STOP. The constant is
  correct; the assertion was wrong. Fix the assertion.
- Amend `decisions/2026-05-25-supported-engine-matrix.md` Gradle row
  yourself → STOP. PM owns decisions; raise as a `questions/` entry if
  you think a new entry is needed.
- Refactor the staging helpers from hotfix #1 → STOP. They work.
  Hotfix #2 is additive — preserve.

Otherwise: branch a worktree off current main tip (post-hotfix-#1
verification + failed-findings commits — likely `b3fa515` or wherever
main is when this brief dispatches), apply Defect 2 Maven fix first
(it's the load-bearing user-visible defect), then Defect 2 Gradle fix,
then Defect 4 assertion fix in both test files, then the Gradle
fixture launcher dep. CLI-level smokes should now pass on the
equipped host without further intervention.
