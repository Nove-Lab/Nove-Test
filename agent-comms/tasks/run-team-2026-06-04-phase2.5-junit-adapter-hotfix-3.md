---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix-3
status: pending
related:
  - agent-comms/questions/main-branch-team-2026-06-04-junit-hotfix-2-gate-failed.md
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
---

# Phase 2.5 — JUnit adapter HOTFIX #3 (envelope path + Gradle 8.14.5 coverage staging + pre-handoff gate equipping)

## TL;DR

Hotfix #2 (`41d58ab`, branch `origin/run-team/junit-adapter-hotfix-2`)
closed Defect 2 cleanly **on the Maven path** and corrected the Defect 4
assertion tuple, but Main Branch's pre-merge gate on the equipped host
(JDK 17.0.19 + Maven 3.9.16 + Gradle 8.14.5) caught two unresolved
issues. The merge was aborted — no merge commit, no verification doc.
See `questions/main-branch-team-2026-06-04-junit-hotfix-2-gate-failed.md`
for the full gate transcript.

| # | Issue | Severity | Fix shape |
|---|---|---|---|
| F1 | **CLI-smoke envelope path wrong** — both `test_cli_smoke_run_emits_envelope` cases dereference `envelope["data"]["run_record"]["engine_name"]`. Actual envelope shape is `envelope["data"]["memory_entry"]["run_record"]["engine_name"]` per `src/novetest/orchestration/workflows/run.py:32-46` (the `RunOutcome.memory_entry` field carries the `MemoryEntry`, and the envelope projects that as `data.memory_entry`). Smoke `KeyError: 'run_record'` on the equipped host. Same class of defect as Defect 4: a CLI-smoke assertion shipped without ever being exercised end-to-end against the canonical envelope. | P0 | One-line dict-key edit in 2 test files |
| F2 | **Gradle 8.14.5 `--continue` does NOT restore `coverage_xml`.** Maven path with `-Dmaven.test.failure.ignore=true` works ✅ (confirmed in Main Branch's gate). Gradle path: `coverage_xml` still absent from `artifact_paths`; `returncode=1`. Hotfix #2's argv unit test only proves flag ordering, not runtime task-graph outcome. | P1 | Run team to diagnose on equipped host; 2-3 hypotheses listed below |
| Process | **Pre-handoff gate must run on equipped host when adapter integration tests are in the diff.** Run team's gate has now leaked the same class of defect twice (Defect 4 in hotfix #1 — assertion never evaluated; F1 in hotfix #2 — envelope dereference never evaluated). The `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5 (added in the same commit as this brief) binds Run team's own gate too. | Decision | See §3 below; the decision amendment lands in the same commit as this brief |

The hotfix #2 work on the Maven coverage path (the
`-Dmaven.test.failure.ignore=true` fix), the assertion tuple `(0,1)→(0,3)`,
and the Gradle 9 fixture launcher dep are **all correct and STAY** —
this slice is additive. The branch `run-team/junit-adapter-hotfix-2` on
origin is the foundation; do NOT unwind any of its commits.

**Estimated scope:** Very small if F2 root cause is hypothesis H1
(probable — see §2); medium if H2 or H3. ~30-100 LOC including the
diagnostic walk.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/questions/main-branch-team-2026-06-04-junit-hotfix-2-gate-failed.md`** — the gate transcript with exact failure stacks and the recommendation that led to this brief
4. **`agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`** — the prior cycle's failure detail; preserves what hotfix #2 did correctly on Maven
5. **`agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5** (NEW) — pre-handoff gate equip-and-exercise binding, applies to this slice
6. `agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md` — hotfix #1 evidence to preserve
7. `src/novetest/orchestration/workflows/run.py:32-46` — the `RunOutcome.memory_entry` shape that determines the correct envelope path
8. `tests/integration/run/test_junit_maven.py` ~line 232 and `tests/integration/run/test_junit_gradle.py` ~line 200 (on the hotfix-2 tip) — the smoke envelope dereference sites
9. `src/novetest/run/adapters/junit_adapter.py` `_run_gradle` (line ~484) — F2 fix site
10. The smoke output of `gradle test --no-daemon --continue jacocoTestReport` against `tests/fixtures/projects/junit-gradle-basic/` on the equipped host — necessary for F2 diagnosis

---

## 1. F1 — Envelope path fix (one-line edit × 2 files)

### Site 1: `tests/integration/run/test_junit_maven.py` ~line 232

Current (hotfix-2 tip):

```python
envelope = json.loads(run_result.stdout)
assert envelope["schema"] == "novetest/v1"
assert isinstance(envelope["ok"], bool)
if envelope["ok"]:
    assert envelope["data"]["run_record"]["engine_name"] == "junit"
```

Fix:

```python
envelope = json.loads(run_result.stdout)
assert envelope["schema"] == "novetest/v1"
assert isinstance(envelope["ok"], bool)
if envelope["ok"]:
    # Envelope shape: data carries a MemoryEntry (workflows/run.py:32-46
    # RunOutcome.memory_entry). The RunRecord lives under
    # data.memory_entry.run_record — NOT data.run_record. Hotfix #2
    # shipped a wrong dereference here; Main Branch's equip-and-
    # exercise pre-merge gate caught it on 2026-06-04 (KeyError:
    # 'run_record').
    assert envelope["data"]["memory_entry"]["run_record"]["engine_name"] == "junit"
```

### Site 2: `tests/integration/run/test_junit_gradle.py` ~line 200

Same edit shape (engine_name remains `"junit"` — Gradle and Maven both
route through the same JUnit adapter).

### Why this path was missed

The hotfix #2 task brief specified the smoke pattern but not the
dereference path explicitly; Run team's gate ran on a JDK-less host
where the smoke skip-gated, so the line was never executed against a
real envelope. **Equip-and-exercise §2.5 makes this masking class of
defect non-repeatable** — Run team's pre-handoff gate now runs on the
equipped host whenever adapter integration tests are in the diff.

---

## 2. F2 — Gradle 8.14.5 coverage_xml staging (diagnose-and-fix)

The Maven path is settled: `-Dmaven.test.failure.ignore=true` lets
`jacoco:report` execute after Surefire failure, `target/site/jacoco/
jacoco.xml` is written, adapter glob picks it up, `artifact_paths`
includes `coverage_xml`. Main Branch's gate confirms this end-to-end.

The Gradle path with hotfix #2's `--continue` flag inserted before
`jacocoTestReport` does NOT produce the equivalent outcome on Gradle
8.14.5. Concretely:

```
$ uv run pytest -q tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml
FAILED
> AssertionError: assert 'coverage_xml' in result.artifact_paths
> artifact_paths={'stdout', 'stderr', 'reports_dir'}  # no coverage_xml
> returncode=1
```

The hotfix #2 unit test proves `--continue` appears in argv before
`jacocoTestReport` — that's correct. The runtime semantics are the
unknown.

### Three hypotheses (Run team diagnoses on equipped host)

**H1 (most likely) — `:jacocoTestReport` has an implicit `dependsOn(:test)`.**

Gradle's task-graph semantics for `--continue`: keep running tasks that
do NOT depend on the failed one. The JaCoCo plugin v0.8.x configures
`jacocoTestReport.executionData(test)` (which reads `test.exec`), but
the plugin docs also reference `jacocoTestReport` "being aware of" test
results. If the task itself reports a `dependsOn(:test)` relationship,
`--continue` cannot run it after `:test` fails.

**Diagnostic.** On the equipped host, run:

```sh
cd tests/fixtures/projects/junit-gradle-basic
# Force-execute test+report; observe what Gradle does after the failing testSubtract
~/.local/opt/gradle/bin/gradle test jacocoTestReport --no-daemon --continue --info 2>&1 | tee /tmp/gradle-diag.log

# Then inspect what tasks actually ran:
grep -E '^> Task |UP-TO-DATE|SKIPPED|FAILED' /tmp/gradle-diag.log
```

If you see `> Task :jacocoTestReport SKIPPED` (and not `:jacocoTestReport`
without a status, indicating successful execution), H1 is confirmed.

**Fix candidates for H1 (Run team's call; recommend Fix-A):**

- **Fix-A — two-pass adapter invocation.** Split into two subprocess
  calls:
  1. `gradle test --no-daemon --continue` (lets `:test` write
     `build/jacoco/test.exec` even on failure)
  2. `gradle jacocoTestReport --no-daemon` (reads existing `test.exec`,
     writes XML — does NOT re-run `:test`)

  Both invocations share the same Gradle build cache, so the second is
  fast. The non-zero exit of the first is preserved as the user-tests-
  failed signal; the second's exit is suppressed for the purpose of
  coverage staging (best-effort).

- **Fix-B — `--init-script` finalizedBy injection.** Write a temporary
  `init.gradle` file that does:
  ```groovy
  allprojects {
      afterEvaluate {
          if (tasks.findByName('test') && tasks.findByName('jacocoTestReport')) {
              tasks.named('test').configure { finalizedBy('jacocoTestReport') }
          }
      }
  }
  ```
  Then invoke `gradle test --no-daemon --init-script <tmpfile>`. The
  `finalizedBy` semantic runs the finalizer even after the task fails.
  No fixture edit required.

- **Fix-C — fixture-side `finalizedBy`.** Edit
  `tests/fixtures/projects/junit-gradle-basic/build.gradle.kts` to add:
  ```kotlin
  tasks.test {
      finalizedBy(tasks.jacocoTestReport)
  }
  ```
  Simplest, but tying coverage behavior to fixture cooperation breaks
  the user-project assumption: real user builds will not be edited by
  us, so the adapter must work without fixture cooperation.

**PM recommendation: Fix-A (two-pass)** — it's adapter-local, no fixture
edit, deterministic across Gradle 7.6 / 8.x / 9.x without depending on
behavior of any single Gradle version. Fix-B is the second choice if
Fix-A turns out to have a perf or ergonomic issue.

**H2 — output path mismatch (less likely).**

JaCoCo plugin's default XML report location for the `jacocoTestReport`
task on Gradle 8.14.5 may differ from what the adapter's
`_stage_coverage_xml` glob expects. The standard pattern is
`build/reports/jacoco/test/jacocoTestReport.xml`, but some
configurations produce `build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml`.
If H1 confirms `:jacocoTestReport` ran (status displayed without
SKIPPED/FAILED tag), inspect:

```sh
find tests/fixtures/projects/junit-gradle-basic/build -name "*.xml" -path "*jacoco*"
```

Compare the actual path against the adapter glob; fix the glob if a
mismatch exists.

**H3 — adapter staging path bug (least likely).**

If both H1 and H2 are negative (the XML exists on disk under the
expected glob, but `coverage_xml` is still missing from
`artifact_paths`), trace into `_stage_coverage_xml` and verify the
relative-path computation matches the `.relative_to(store.path)`
invariant.

### Mandatory diagnostic preserve

Whichever fix you take, the handoff MUST include:

1. The `/tmp/gradle-diag.log` snippet showing what tasks Gradle reported
   after `--continue` + the failing test
2. The actual on-disk path of the XML (find result, even if absent)
3. The hypothesis confirmed (H1/H2/H3) and the rejected ones with
   one-sentence reason each

This is the institutional learning that → Gradle JaCoCo behavior is now
documented for the next time someone touches this code.

---

## 3. Pre-handoff gate equipping (equip-and-exercise §2.5)

**`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5 is
amended in the same commit as this brief** to add a binding requirement:

> When a Run-team slice modifies `src/novetest/run/adapters/<engine>_adapter.py`
> OR `tests/integration/run/test_<engine>_*.py`, the team's pre-handoff
> gate MUST run on a host with the engine's toolchain installed per
> `scripts/dev-host-setup.md`. If the team's local environment cannot
> be equipped (e.g. license restriction, container limitation), the
> work pauses and the team files a `questions/` entry to PM rather than
> handing off an un-exercised diff.

Concrete checklist Run team applies to this hotfix:

- [ ] JDK 17 + Maven 3.9+ + Gradle 8.14.5 installed on Run team's gate
      host per `scripts/dev-host-setup.md` §5
- [ ] `uv run pytest -q tests/integration/run/test_junit_maven.py
      tests/integration/run/test_junit_gradle.py` shows tests EXECUTE
      (not skip); pre-merge gate count is `(N passed, 0 skipped JUnit
      lines)`
- [ ] Both `test_cli_smoke_run_emits_envelope` cases PASS (this proves
      F1 fix is correct)
- [ ] `test_coverage_run_emits_jacoco_xml` PASSES for both Maven and
      Gradle (this proves F2 fix is correct on Gradle 8.14.5)

If any of these four cannot be true at handoff time, do NOT write the
handoff — file a `questions/` entry to PM.

---

## 4. Worktree continuity

This is a new computer; the original hotfix-2 worktree was on a different
machine and is not present here. The branch `run-team/junit-adapter-hotfix-2`
at tip `41d58ab` IS on origin (pushed by Main Branch in the prior session).

Run team's start sequence:

```sh
# From the main checkout:
git fetch origin

# Create the hotfix-3 worktree based on hotfix-2's tip:
git worktree add /home/yjshin/dev/aispace/novetest-junit-hotfix-3 \
    -b run-team/junit-adapter-hotfix-3 origin/run-team/junit-adapter-hotfix-2

cd /home/yjshin/dev/aispace/novetest-junit-hotfix-3

# Rebase the abort-commit (42b3961, comms-only) onto your branch so the
# eventual FF-merge is clean:
git rebase origin/main
# Expect: clean fast-forward (42b3961 only touches agent-comms/, no
# conflict with src/ or tests/). If a conflict surfaces, stop and file
# a questions/ entry.

# Verify the rebase landed clean:
git log --oneline origin/main..HEAD
# Expect: a single commit (hotfix-2's `41d58ab` content reapplied onto
# the new base), no extras yet.
```

After applying F1 + F2 commits on top, the branch will contain:
hotfix-2 content + your 1-2 new commits.

---

## 5. Files touched (estimated)

| File | Change |
|---|---|
| `tests/integration/run/test_junit_maven.py` | F1: envelope path `data["run_record"]` → `data["memory_entry"]["run_record"]` (~line 232 on hotfix-2 tip) |
| `tests/integration/run/test_junit_gradle.py` | F1: same edit (~line 200 on hotfix-2 tip) |
| `src/novetest/run/adapters/junit_adapter.py` | F2: depending on hypothesis confirmed — Fix-A two-pass restructure in `_run_gradle`, OR Fix-B init-script injection, OR Fix-C (NOT recommended). Adapter-local. |
| `tests/unit/run/adapters/test_junit_adapter.py` | F2: unit test for whichever Gradle fix shape lands — Fix-A: assert the adapter issues 2 subprocess calls in correct order; Fix-B: assert init-script content matches expected `finalizedBy` snippet. |
| `WORKLOG.md` | New entry per protocol. |

Likely diff scope: ~20 LOC tests + ~30-60 LOC adapter + ~30-50 LOC unit
tests = ~100 LOC total. F1 is trivial; F2 is the bulk.

## 6. Out of scope (explicit)

Do NOT introduce these in this slice:

- **Backfilling CLI smokes to pytest / jest / go-test / cargo.** The
  equip-and-exercise §2 binds new adapters; retroactive backfills are
  optional (cargo brief covers it separately when unblocked).
- **JDK 11 readiness probe hard-reject.** Hotfix #1 open item; still
  deferred.
- **Matrix Gradle tested-ceiling bump to 9.x.** PM decision-doc
  amendment; out of Run team scope. The hotfix #2 Gradle 9 launcher
  dep fixture-side fix is forward-compatible and lands as part of this
  cycle's foundation — but the matrix amendment itself is PM territory.
- **Verification-doc shape-drift corrections** (hotfix #1 findings rec
  #5). Main Branch picks up.
- **Refactor of staging helpers from hotfix #1 / #2.** They work where
  they work. Hotfix #3 is additive.
- **A new `AdapterInvocationError.kind` value** if F2 fix-A produces an
  edge case where the second subprocess call fails — keep it `silently
  best-effort`; record a `payload["warnings"]` entry with kind
  `"gradle-jacoco-report-skipped"` if you want to surface it, but do
  NOT introduce a new error kind without filing a `questions/` entry.

## 7. Definition of Done bullets

Tick when ALL are true:

- [ ] `tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope`
      dereferences `envelope["data"]["memory_entry"]["run_record"]["engine_name"]`
      with an inline comment citing `workflows/run.py:32-46`.
- [ ] Same fix at `tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope`.
- [ ] F2 hypothesis confirmed in the handoff (H1 / H2 / H3) with the
      `/tmp/gradle-diag.log` evidence snippet.
- [ ] F2 fix (Fix-A two-pass / Fix-B init-script / Fix-C fixture —
      Fix-A recommended) lands in `junit_adapter.py:_run_gradle`. Unit
      test pins the chosen mechanism.
- [ ] `uv run pytest -q tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml`
      PASSES on equipped host (JDK 17 + Gradle 8.14.5).
- [ ] `uv run pytest -q tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope`
      and the Gradle sibling BOTH PASS on equipped host.
- [ ] Run team's pre-handoff gate ran on equipped host per
      `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
      §2.5. Handoff cites JDK + Maven + Gradle versions detected on the
      gate host (must be ≥ matrix floors).
- [ ] `uv run pytest -q tests/unit tests/integration` on equipped host:
      `>=1033 passed + 3 skipped + 0 failed`. (Hotfix #2's baseline on
      JDK-less was `1025 passed + 14 skipped + 0 failed`; equipping
      moves ~11 cases from skipped to passed and adds the new F2 unit
      tests; numbers can deviate slightly but skipped count must DROP
      and failed count MUST be 0.)
- [ ] `uv run mypy --strict` clean.
- [ ] Hotfix #1 Defect 1 (reports_dir under store.path) and Defect 3
      (identity parens strip) regression canaries PASS — confirm
      explicitly in the handoff.
- [ ] Hotfix #2's Maven `-Dmaven.test.failure.ignore=true` fix
      preserved; Maven `coverage_xml` still populated on canonical
      fixture.

## 8. Re-verification (Manual Test re-pass on equipped host)

After Main Branch FF-merges and the slice lands on `main`, Manual Test
re-runs the same verification scenarios as hotfix #2:

```sh
source ~/.local/share/novetest-toolchains.sh  # PATH for JDK + Maven + Gradle

# Step 0 — CLI smokes must PASS:
uv run pytest -q tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope \
                tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
# Expected: 2 passed, 0 failed.

# Step 2 — Maven coverage (regression canary; hotfix-2 closed this on Maven):
cd /tmp/junit-mvn-smoke
rm -rf .novetest target
uv run --project <repo> novetest init
uv run --project <repo> novetest run --coverage > /tmp/run-maven-cov.json
jq '.data.coverage_outcome.kind' /tmp/run-maven-cov.json
# Expected: "fact-set"
jq '.data.memory_entry.run_record.artifact_paths | keys' /tmp/run-maven-cov.json
# Expected: includes "coverage_xml"

# Step 4 — Gradle coverage (THIS hotfix's primary scope):
cd /tmp/junit-gradle-smoke
rm -rf .novetest build
uv run --project <repo> novetest init
uv run --project <repo> novetest run --coverage > /tmp/run-gradle-cov.json
jq '.data.coverage_outcome.kind' /tmp/run-gradle-cov.json
# Expected: "fact-set" (was "unavailable" pre-fix)
jq '.data.memory_entry.run_record.artifact_paths | keys' /tmp/run-gradle-cov.json
# Expected: includes "coverage_xml" (was absent pre-fix)

# Regression canaries:
cd /tmp/junit-mvn-smoke; uv run --project <repo> novetest run
# Expected: exit 3; reports_dir under .novetest/
cd /tmp/junit-gradle-smoke; uv run --project <repo> novetest run
# Expected: exit 3; identity strings byte-identical to Maven case
```

All Step-1 (Defect 1) and Step-3 (Defect 3) scenarios from hotfix #1
must remain ✅ — they're additive guardrails this slice doesn't touch.

## 9. Handoff expectations

When ready to merge, write
`agent-comms/handoffs/run-team-2026-06-XX-phase2.5-junit-adapter-hotfix-3.md`
with:

1. **DoD bullets believed closed** — list each from §7 with a one-line
   evidence pointer.
2. **F1 envelope path before/after** — paste the line diff for both
   smoke files.
3. **F2 hypothesis + evidence** — H1 / H2 / H3 confirmed; paste the
   `/tmp/gradle-diag.log` snippet showing what tasks Gradle reported.
4. **F2 fix shape + unit test pointer** — Fix-A / B / C declared; unit
   test name + assertion shape.
5. **Pre-handoff gate report** — equipped-host tool versions detected;
   skip count for `test_junit_*` cases (must be 0); failure count
   (must be 0).
6. **Hotfix #1 Defects 1 + 3 regression canary** — `reports_dir`
   under `store.path`; Maven/Gradle identity byte-identical.
7. **Hotfix #2 Maven coverage_xml regression canary** — `coverage_xml`
   still in `artifact_paths` on Maven canonical fixture.
8. **Slice diff summary** — `git diff origin/main --stat`.
9. **Worktree path** — `/home/yjshin/dev/aispace/novetest-junit-hotfix-3`;
   branch `run-team/junit-adapter-hotfix-3`; tip commit SHA.

PM picks up the handoff, dispatches Main Branch for the pre-merge gate
(which MUST run on equipped host per §2.5 — Main Branch was the one
that caught hotfix-2's leak; that posture continues), then Manual Test
for re-pass. When Manual Test files PASSED findings, PM closes the
JUnit cycle: deletes ALL twelve transient files (original 4 + hotfix-1
4 + hotfix-2 4), ticks the Phase 2.5 JUnit DoD bullet in
`delivery-phasing.md`, writes a single combined history entry covering
all 3 attempts' lessons.

## 10. Sanity check before starting

If you find yourself wanting to:

- Touch the JDK 11 readiness probe → STOP. Out of scope.
- Modify the `EXIT_USER_TESTS_FAILED` constant or any cli/output.py
  constant → STOP. Those are correct.
- Refactor hotfix #1 or hotfix #2's staging helpers → STOP. They work
  where they work; hotfix #3 is additive only.
- Modify `target_resolver.py` or any cross-engine module → STOP. This
  is a JUnit-only slice.
- Amend `decisions/2026-05-25-supported-engine-matrix.md` yourself →
  STOP. PM owns decisions; raise a `questions/` entry if you want a
  new matrix row.
- Ship without running pytest on the equipped host because "the unit
  test passes" → STOP. The §2.5 mandate exists because that pattern
  has now leaked the same class of defect twice.
- Take Fix-C (fixture-side `finalizedBy`) without exhausting Fix-A
  and Fix-B → STOP. Adapter-local fixes only; the user-project
  assumption is binding.

Otherwise: branch the worktree (§4), diagnose F2 on equipped host (§2
H1/H2/H3 walk), apply F1 first (trivial), then F2 (Fix-A recommended),
then unit test + run the gate on equipped host (§3 checklist). Handoff
once §7 DoD bullets are all ticked.
