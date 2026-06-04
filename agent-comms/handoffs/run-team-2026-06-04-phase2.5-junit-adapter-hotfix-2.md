---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix-2
status: ready
related:
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/verifications/2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
worktree: /home/yjshin/dev/aispace/novetest-junit-hotfix-2
branch: run-team/junit-adapter-hotfix-2
base_commit: 6099841
---

# Handoff — Phase 2.5 JUnit adapter HOTFIX #2

## TL;DR

Tiny additive slice on top of hotfix #1 (`e28e63e`). Closes the 1 P1
reopen (Defect 2 — coverage XML never produced because Maven/Gradle
aborted at the test phase before the report goal/task ran), the 1 P0
process bug shipped at `e28e63e` (Defect 4 assertion bug: `(0, 1)`
rejects the canonical fixture's `EXIT_USER_TESTS_FAILED=3`), and the
1 P2 Gradle 9 forward-compat (fixture missing
`junit-platform-launcher` dep). **0 new source files**, 1 modified
source file (~24 lines added), 3 modified test files (+440 net),
1 modified fixture file (+8 lines), 1 modified WORKLOG entry.
**mypy strict clean** (90 source files unchanged); **1025 passed +
14 skipped + 0 failed** on JDK-less host (hotfix #1 baseline 1020+
14+0; +5 net from new argv composition tests). **D1-D6 unchanged**;
hotfix #1's Defect 1+3 fixes preserved unchanged.

Ready for FF-merge → Manual Test re-pass on equipped host.

## Worktree

- **Path**: `/home/yjshin/dev/aispace/novetest-junit-hotfix-2`
- **Branch**: `run-team/junit-adapter-hotfix-2` (off `6099841`, current main tip)
- **Base commit**: `6099841` (`comms: queue JUnit hotfix-2 + cargo CLI orchestration defect (blocked)`)
- Worktree state at handoff: 1 hotfix-2 commit on top of base; clean tree.

## DoD bullets believed closed

Mapped to `agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md` §7 (8 bullets).

| # | Bullet | Evidence pointer |
|---|---|---|
| 1 | `_run_maven` appends `-Dmaven.test.failure.ignore=true` BEFORE `org.jacoco:jacoco-maven-plugin:report`, ONLY when `collect_coverage and has_jacoco`; unit-tested | `src/novetest/run/adapters/junit_adapter.py:211-228` (conditional argv block); `tests/unit/run/adapters/test_junit_adapter.py::TestMavenCoverageArgv::test_failure_ignore_flag_present_with_coverage_and_jacoco` (positive + ordering); `test_failure_ignore_flag_absent_without_coverage` + `test_failure_ignore_flag_absent_when_jacoco_undeclared` (scope guards) |
| 2 | `_run_gradle` appends `--continue` BEFORE `jacocoTestReport`, ONLY when `collect_coverage and has_jacoco`; unit-tested | `src/novetest/run/adapters/junit_adapter.py:493-503` (conditional argv block); `tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_continue_flag_present_with_coverage_and_jacoco` (positive + ordering); `test_continue_flag_absent_without_coverage` (scope guard) |
| 3 | `test_junit_maven.py::test_cli_smoke_run_emits_envelope` asserts `returncode in (0, 3)` with updated error message | `tests/integration/run/test_junit_maven.py:208-227` |
| 4 | `test_junit_gradle.py::test_cli_smoke_run_emits_envelope` asserts `returncode in (0, 3)` with updated error message | `tests/integration/run/test_junit_gradle.py:174-187` |
| 5 | `test_junit_maven.py::test_coverage_run_emits_jacoco_xml` docstring updated to reflect `failure.ignore` semantics | `tests/integration/run/test_junit_maven.py:143-150` |
| 6 | `junit-gradle-basic/build.gradle.kts` declares `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` | `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts:28-37` |
| 7 | JDK-less pytest gate 0 regressions vs hotfix #1 baseline | `1025 passed + 14 skipped + 0 failed in 31.51s` (was 1020+14+0; +5 from new argv tests; CLI smokes still skip on this JDK-less box) |
| 8 | `uv run mypy --strict` clean | `Success: no issues found in 90 source files` (source count unchanged) |

## Maven coverage before/after

The brief §9.2 asked for `data.coverage_outcome.kind` and
`artifact_paths` key set before/after. The pre-hotfix-2 state was
captured by Manual Test on the equipped host (their findings doc
`manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`); the
post-hotfix-2 state is exercised on the equipped host by Manual Test
re-pass (Run team's local dev box has no Maven, so the end-to-end
verification can only be performed in re-pass).

Adapter-side behavior unit-tested:

**Before** (hotfix #1 `e28e63e`, `_run_maven` argv when `collect_coverage=True` and JaCoCo declared):
```
['/fake/mvn', '-B', 'test',
 'org.jacoco:jacoco-maven-plugin:report',
 '-Dsurefire.reportFormat=plain', '-Dsurefire.useFile=false']
```
Reactor aborts at Surefire when a test fails → `org.jacoco:jacoco-maven-plugin:report` never runs → `target/site/jacoco/jacoco.xml` never written → `artifact_paths["coverage_xml"]` absent → CoverageFactSet kind `"unavailable"`.

**After** (hotfix #2):
```
['/fake/mvn', '-B', 'test',
 '-Dmaven.test.failure.ignore=true',
 'org.jacoco:jacoco-maven-plugin:report',
 '-Dsurefire.reportFormat=plain', '-Dsurefire.useFile=false']
```
Surefire reports failures but does NOT raise → Maven runs the report goal → `target/site/jacoco/jacoco.xml` written → adapter's `_stage_coverage_xml` copies it to `artifact_dir/native/coverage/jacoco.xml` → `artifact_paths["coverage_xml"]` populated → Coverage engine emits CoverageFactSet kind `"fact-set"`.

The `EXIT_USER_TESTS_FAILED=3` signal still propagates (failing-test
status preserved in Surefire XML, parsed by the adapter, propagates
through `aggregate_junit_status → "failed"`).

Pinned by `TestMavenCoverageArgv.test_failure_ignore_flag_present_with_coverage_and_jacoco`:
```python
assert "-Dmaven.test.failure.ignore=true" in argv
assert "org.jacoco:jacoco-maven-plugin:report" in argv
idx_flag = argv.index("-Dmaven.test.failure.ignore=true")
idx_goal = argv.index("org.jacoco:jacoco-maven-plugin:report")
assert idx_flag < idx_goal  # flag MUST precede goal
```

## Gradle coverage before/after

**Before** (hotfix #1, `_run_gradle` argv with coverage):
```
['/fake/gradle', 'test', '--no-daemon', 'jacocoTestReport']
```
`:test` task fails → Gradle stops task graph → `:jacocoTestReport` never runs → `build/reports/jacoco/test/jacocoTestReport.xml` never written → same downstream consequence.

**After** (hotfix #2):
```
['/fake/gradle', 'test', '--no-daemon', '--continue', 'jacocoTestReport']
```
`--continue` lets independent tasks proceed → `:jacocoTestReport` runs against `jacoco.exec` (produced regardless of `:test` outcome) → XML written → staged to `artifact_dir/native/coverage/jacoco.xml`.

Pinned by `TestGradleCoverageArgv.test_continue_flag_present_with_coverage_and_jacoco` with same ordering assertion.

## CLI smoke before/after

**Before** (hotfix #1 `e28e63e`, `_test_cli_smoke_run_emits_envelope` core assertion):
```python
assert run_result.returncode in (0, 1)
```
Canonical fixture has 1 failing test → CLI exits **3** (`EXIT_USER_TESTS_FAILED`) → assertion rejects 3 → smoke false-fails on equipped host. The brief flagged this as "the `(0, 1)` assertion WORKED — smokes ran rather than skipped and the bug was caught"; the equipping mandate from `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §1 made the smoke actually execute on the equipped host, which surfaced the assertion error.

**After** (hotfix #2):
```python
assert run_result.returncode in (0, 3), (
    f"CLI returned exit {run_result.returncode}; "
    f"expected 0 (EXIT_OK, all passed) or 3 (EXIT_USER_TESTS_FAILED, "
    f"some user tests failed). Exit codes 1 (EXIT_GENERIC), "
    f"2 (EXIT_USAGE), 4 (EXIT_ENGINE_MISSING), 5 (EXIT_STORAGE) all "
    f"indicate contract or environment violations and MUST not "
    f"occur on the canonical happy-path fixture. See "
    f"src/novetest/cli/output.py:12-17. ..."
)
```
Exit 0 (all-passed) and 3 (user-tests-failed, canonical fixture's
designed outcome) now both pass; exit 1 (generic), 2 (usage), 4
(engine-missing), 5 (storage) remain rejected with a verbose error
message mapping each code so a future regression message
self-documents.

The matching errata in `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2 (commit `efa0466`) pins this assertion shape in the binding adapter-cycle template.

## Hotfix #1 Defects 1 + 3 regression canary

Per brief §9.5, confirming the prior fixes are preserved unchanged.

**Defect 1 (reports_dir staging under store.path)**:
- `_stage_reports_dir` helper at `junit_adapter.py:1078-1102` untouched.
- `_run_maven` line 391-396 untouched (still calls `_stage_reports_dir` and sets `artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"`).
- `_run_gradle` line 605-606 untouched.
- Unit tests `TestStageReportsDir` (3 cases) all green.
- Integration test assertions `reports_dir.is_relative_to(artifact_dir)` etc. unchanged.

**Defect 3 (identity parens strip)**:
- `_strip_trailing_parens` helper at `junit_adapter.py:814` untouched.
- `_normalize_test_case` line 720 still calls `_strip_trailing_parens(case.get("name", ""))`.
- Unit tests `TestStripTrailingParens` (6 cases) all green; `TestNormalizeTestCase.test_gradle_trailing_parens_stripped` + `test_gradle_failure_log_key_uses_stripped_identity` all green.
- Integration test assertion `"#testSubtract" in failure_logs_raw` (no parens) + `"#testSubtract()" not in failure_logs_raw` unchanged.

## Slice diff summary

```
 WORKLOG.md                                         |  10 +
 src/novetest/run/adapters/junit_adapter.py         |  24 ++
 .../projects/junit-gradle-basic/build.gradle.kts   |   8 +
 tests/integration/run/test_junit_gradle.py         |  12 +-
 tests/integration/run/test_junit_maven.py          |  31 +-
 tests/unit/run/adapters/test_junit_adapter.py      | 397 +++++++++++++++++++++
 6 files changed, 472 insertions(+), 10 deletions(-)
```

+ this handoff file.

The 397-line unit test growth is mostly the `_make_*_argv_capturing_stub`
helpers (~150 lines) + 5 test methods (~200 lines combined) + the
test pom/build.gradle.kts fixtures (~50 lines of multi-line strings).
The actual asserted behavior is small (4 assertions per test).

## Test counts post-fix

| Suite | Hotfix #1 baseline (`e28e63e`) | Post-hotfix-2 |
|---|---|---|
| `tests/unit` + `tests/integration` passed | 1020 | **1025** (+5) |
| skipped | 14 | **14** (unchanged) |
| failed | 0 | **0** |
| Time | ~31 s | ~31 s |
| mypy `--strict` | 90 source files clean | 90 source files clean (unchanged) |

The +5 passed comes from the 5 new argv composition tests (3 Maven + 2 Gradle). Brief §7 required `1020+ + 10+ + 0`; we hit `1025+14+0` with margin.

## D1-D6 ratification

All six decisions unchanged from the 2026-06-03 cycle. No
re-ratification needed. Hotfix #2's three code fixes are
argv-composition / fixture-dependency / test-assertion edits —
orthogonal to the D1-D6 policy decisions (default coverage
granularity, multi-module emission shape, build-tool tiebreaker,
Surefire-XML format preference, JUnit-4-and-TestNG reject behavior,
Gradle DSL parity).

## Open items / suggestions for PM

1. **Gradle 9 support floor** (Manual Test rec #4) — the fixture
   change makes the canonical fixture forward-compatible with Gradle
   9.x. Whether to bump
   `decisions/2026-05-25-supported-engine-matrix.md`'s Gradle row
   from "tested 7.6 / 8.x" to include 9.x is PM's call; the fixture
   side is closed regardless.

2. **Argv ordering as binding contract** — the hotfix's added
   inline comments document that the flag MUST precede the
   goal/task in the argv. If Run team ever refactors the argv
   composition into a more declarative style (e.g. a list of
   `Flag | Goal` records), the ordering invariant must survive.
   The unit tests' `idx_flag < idx_task` assertion is the load-bearing
   guard.

3. **Hotfix #1 Defect 2 docstring drift** — `test_coverage_run_emits_jacoco_xml`'s
   docstring at hotfix #1 time claimed "the JaCoCo agent is in the
   test phase and the report goal runs in the test lifecycle". That
   was speculative — the actual mechanism is the failure-ignore
   flag. The new docstring corrects it and pins the citation. If
   any other docs in the repo carry the same misconception, they'd
   need a separate pass (none found in this hotfix's scope).

4. **Forward CLI-smoke backfill** — equip-and-exercise §2 binds new
   adapters, not retroactive backfills (per brief §6 explicit out-
   of-scope). PM may want to schedule a hardening cycle that adds
   CLI smokes to pytest / jest / gotest / cargo for parity. Tracked
   under "optional" in the brief.

5. **Local equipped-host smoke not performed** — same as hotfix #1:
   Run team's dev box has only Java 11 + no Maven/Gradle. Manual
   Test will re-pass on their equipped host (JDK 17 + Maven 3.8.7 +
   Gradle 8.5 or 9.x with launcher dep declared per the fixture).
   If Manual Test re-pass fails, Run team picks up immediately.

## Pre-merge checklist for Main Branch

- [x] mypy `--strict` clean (90 source files)
- [x] pytest unit+integration 0 regressions (1025+14+0 ≥ 1020+14+0)
- [x] Worktree clean on `run-team/junit-adapter-hotfix-2`
- [x] D1-D6 unchanged from original cycle's handoff
- [x] Hotfix #1's Defect 1 + Defect 3 fixes preserved unchanged
- [x] Original 2026-06-03 handoff + hotfix #1 handoff stay put as historical record
- [x] WORKLOG entry written at the top
- [x] Index regen ready (PM to run `tools/regen_comms_index.py` post-merge)

## What PM should do next

Per brief §9:
1. Verify the DoD bullets in §"DoD bullets believed closed" against the file pointers.
2. Dispatch Main Branch for FF-merge of `run-team/junit-adapter-hotfix-2`.
3. Dispatch Manual Test for re-pass of the hotfix #1 verification
   scenarios on the equipped host (see brief §8 for the exact
   commands). The CLI smokes should now PASS rather than skip on
   the equipped host.
4. When Manual Test files PASSED findings, close the JUnit cycle:
   delete ALL eight transient files (original 4 + hotfix #1 4 +
   hotfix #2 4), tick the Phase 2.5 JUnit DoD bullet in
   `delivery-phasing.md`, write a single combined history entry
   covering all 3 attempts' lessons.
5. History should pin two load-bearing process lessons: (a) "always
   add CLI-level smoke for new adapters" (hotfix #1 Defect 4, now
   binding per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`);
   (b) "the CLI smoke assertion MUST use `(0, 3)`, NOT `(0, 1)` —
   `EXIT_USER_TESTS_FAILED=3` is the dedicated channel for the
   canonical happy-path fixture's intentional failure" (hotfix #2
   Defect 4, codified in errata commit `efa0466`).
