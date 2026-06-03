---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix
status: pending
related:
  - agent-comms/tasks/run-team-2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/handoffs/run-team-2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/verifications/2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
---

# Phase 2.5 — JUnit adapter HOTFIX (3 defects + 1 process gap)

## TL;DR

The 2026-06-03 JUnit cycle landed at `b2bd10f` and was **verdict-failed**
by Manual Test on 2026-06-04 (see `findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md`).
Skip-gated integration tests on the team's JDK-less host masked three
adapter defects that surface immediately when the adapter is actually
invoked end-to-end via the CLI on an equipped host.

| # | Defect | Severity | Path |
|---|---|---|---|
| 1 | `artifact_paths["reports_dir"]` set to Maven/Gradle native output dir → violates orchestration's `.relative_to(store.path)` invariant → every `novetest run`/`novetest test` on JUnit hard-fails as `cli-error` | **P0 (blocker)** | `src/novetest/run/adapters/junit_adapter.py:363,560` |
| 2 | `artifact_paths["coverage_xml"]` never populated even with `collect_coverage=True` (no glob in `_run_maven`/`_run_gradle` for `jacoco.xml`) → coverage path silently degrades to `unavailable` | P1 | `src/novetest/run/adapters/junit_adapter.py` `_run_maven` / `_run_gradle` |
| 3 | Gradle XML reports `<testcase name="testFoo()">` (parens), Maven Surefire reports `<testcase name="testFoo">` (no parens). Adapter normalizes both as-is → cross-build-tool `identity` divergence | P1 | `src/novetest/run/normalizer.py` JUnit-XML path |
| 4 | Integration tests call `run_junit()` directly, bypassing CLI envelope layer where the `.relative_to` enforcement lives → defects 1+2+3 invisible to the team's local gate AND Main Branch pre-merge gate | Process | `tests/integration/run/test_junit_*.py` |

This brief scopes a tight hotfix: fix 1+2+3 in code; add a CLI-level
smoke per build tool to close the process gap (4). After this slice
the cycle re-enters Main Branch → Manual Test → close protocol with
the same task / handoff / verification / findings transient file
quartet (the original quartet stays put — hotfix appends a second
verification + findings).

**Estimated scope:** 1 short cycle (~½ day). Most of the change shape
is already pinned by the Manual Test findings doc (file:line refs +
recommended fix patterns); your job is to implement + add the missing
CLI-level smoke tests.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md`** — the primary spec; defect descriptions include file:line refs and recommended fix shapes
4. `agent-comms/verifications/2026-06-03-phase2.5-junit-adapter.md` — the equipped-host verification scenarios you must re-pass after hotfix
5. `agent-comms/handoffs/run-team-2026-06-03-phase2.5-junit-adapter.md` — D1-D6 decisions you must preserve unchanged
6. `agent-comms/tasks/run-team-2026-06-03-phase2.5-junit-adapter.md` §1.4 — `NativeResult` payload contract (binding; defects don't relax it, they enforce it)
7. `src/novetest/orchestration/workflows/run.py` lines 85-88 — the `.relative_to(store.path)` invariant that Defect 1 violates
8. `src/novetest/orchestration/workflows/test.py` line ~155 — identical pattern; both code paths hit Defect 1
9. `src/novetest/run/adapters/pytest_adapter.py` — **canonical pattern** for how to stage native artifacts under `artifact_dir`
10. `src/novetest/run/adapters/gotest_adapter.py` — same pattern (per-test failure logs precedent)
11. `src/novetest/run/adapters/cargo_adapter.py` — same pattern (the dual-coverage-path discipline mirror)
12. `src/novetest/run/adapters/junit_adapter.py` lines 363 (Maven) + 560 (Gradle) — exact mutation points

---

## 1. Binding contracts (frozen)

### 1.1 The `.relative_to(store.path)` invariant — what's broken

`src/novetest/orchestration/workflows/run.py:85-88`:

```python
relative_paths = {
    name: str(Path(p).relative_to(store.path))
    for name, p in record.artifact_paths.items()
}
persisted_record = replace(record, artifact_paths=relative_paths)
```

This rewrites all artifact paths as **relative to** `store.path`
(typically `<workspace>/.novetest/`). The contract — implicit but
load-bearing across all adapters — is:

> Every entry in `NativeResult.artifact_paths` MUST be a filesystem
> path located somewhere under `store.path`. Adapters that produce
> native artifacts outside `store.path` (Maven's `target/`, Gradle's
> `build/`, `~/.m2/`, `~/.gradle/caches/`) MUST stage those artifacts
> by copying or moving them under `artifact_dir` before populating
> `artifact_paths`.

`pytest_adapter`, `jest_adapter`, `gotest_adapter`, `cargo_adapter`
all honor this — their `artifact_dir` argument is computed as
`store.path / "run" / "artifacts" / f"run_{run_id}"`, and they write
native outputs directly into that directory tree.

`junit_adapter.py` violates the contract by setting:
- Line 363 (Maven): `artifact_paths["reports_dir"] = workspace / "target" / "surefire-reports"` ← OUTSIDE `store.path`
- Line 560 (Gradle): `artifact_paths["reports_dir"] = workspace / "build" / "test-results" / "test"` ← OUTSIDE `store.path`

### 1.2 Defect 1 fix — staging strategy (Fix #1 per findings)

After Maven/Gradle complete, **copy** (`shutil.copytree`) the native
reports directory into `artifact_dir / "native" / "reports/"`, then
set:

```python
artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"
```

Do NOT move (`shutil.move`) — moving could clobber the user's source
tree on retry. Copy is cheap; reports dirs are typically <10 MB.

`payload["reports"][*].path` already point at the native locations and
do NOT go through `.relative_to`; keep those native paths untouched
(they're informational; downstream readers correlate via the
identity/uniqueId fields, not these paths). If a reader needs the
report files, they MUST read via `artifact_paths["reports_dir"]`.

The Maven multi-module case (D2 contract) stages every module's
`<module>/target/surefire-reports/` under
`artifact_dir / "native" / "reports" / <module>/`. The walk that
already exists for multi-module detection feeds the stage step.

### 1.3 Defect 2 fix — JaCoCo XML glob + stage

Add to both `_run_maven` and `_run_gradle`, ONLY when
`collect_coverage=True`:

```python
# Maven:
jacoco_xml = workspace / "target" / "site" / "jacoco" / "jacoco.xml"
# Multi-module Maven:
jacoco_xml_paths = list(workspace.glob("*/target/site/jacoco/jacoco.xml"))

# Gradle:
jacoco_xml = workspace / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
```

If the file exists, **copy** it under
`artifact_dir / "native" / "coverage" / "jacoco.xml"` (single-module)
or `artifact_dir / "native" / "coverage" / <module>/jacoco.xml`
(multi-module — preserve the per-module D2 contract via the prefix).
Then:

```python
artifact_paths["coverage_xml"] = artifact_dir / "native" / "coverage" / "jacoco.xml"
```

(For multi-module, set `coverage_xml` to the parent
`artifact_dir / "native" / "coverage"` directory; the parser already
globs `*/jacoco.xml` per D2.)

If the file does NOT exist (JaCoCo not configured by the user), emit
`engine-misconfigured` of kind `missing-jacoco` on `payload["warnings"]`
(already documented in the original brief §3.1) and leave
`artifact_paths["coverage_xml"]` unset.

### 1.4 Defect 3 fix — normalizer strips trailing `()` from JUnit XML test names

In `src/novetest/run/normalizer.py` (or wherever the JUnit-XML test
case name → identity translation lives — findings did not pin the
exact line, file the question if you can't locate it):

```python
def _normalize_junit_test_name(name: str) -> str:
    # Gradle 8+ JUnit XML reports include trailing "()" for parameterless
    # methods; Maven Surefire strips them. Normalize to the Maven-canonical
    # no-parens form so identity is stable across build tools.
    # Parametrized tests have name="testFoo(int) [1] arg=5" — strip ONLY the
    # literal trailing "()" pair, not signature parens.
    if name.endswith("()"):
        return name[:-2]
    return name
```

This is invoked when building `payload["tests"][*].identity` AND when
constructing the `failure_logs` dict key (Defect 3 evidence shows the
parens leaking into both surfaces).

**Unit-test requirement:** add explicit cases for both Maven-style
input (no parens, e.g. `testSubtract`) and Gradle-style input (with
parens, e.g. `testSubtract()`) → both must produce the same `identity`
literal `"com.example.CalculatorTest#testSubtract"`. Also test the
parametrized signature case (e.g. `testFoo(int) [1] arg=5` → unchanged).

### 1.5 Defect 4 fix — CLI-level smoke test per build tool

Add to `tests/integration/run/test_junit_maven.py` AND
`tests/integration/run/test_junit_gradle.py`:

```python
import subprocess

def test_cli_smoke_run_emits_envelope(maven_workspace: Path):
    """End-to-end CLI smoke — catches Defect-1-class regressions.

    Calls `novetest run` via subprocess (not run_junit directly), so the
    orchestration layer's .relative_to() invariant is exercised.
    """
    if shutil.which("java") is None or shutil.which("mvn") is None:
        pytest.skip("JDK + Maven required; install per scripts/dev-host-setup.md §5")

    # First run novetest init to set up the store
    init_result = subprocess.run(
        ["uv", "run", "novetest", "init"],
        cwd=maven_workspace, capture_output=True, text=True, timeout=60,
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = subprocess.run(
        ["uv", "run", "novetest", "run"],
        cwd=maven_workspace, capture_output=True, text=True, timeout=300,
    )
    # Exit 0 (all pass) or 1 (some failed) are both acceptable; exit 2+
    # is a CLI-error and indicates a contract violation like Defect 1.
    assert run_result.returncode in (0, 1), (
        f"CLI returned exit {run_result.returncode}; "
        f"expected 0 (pass) or 1 (some test failed). "
        f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
    )
    # Verify envelope shape
    import json
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert envelope["ok"] is True or envelope["ok"] is False  # either is fine
    if envelope["ok"]:
        assert envelope["data"]["run_record"]["engine_name"] == "junit"
```

Same shape for Gradle (`mvn` → `gradle`-or-`gradlew`). Skip-gate on
toolchain PATH presence (matching cargo/gotest precedent).

This is the load-bearing process change. Without it, Defect-1-class
regressions remain invisible to your team's local gate. **PM is also
considering a verification-template amendment** (Manual Test
recommendation #4) but that's separate process work — the per-adapter
CLI smoke lives here.

---

## 2. Files touched (estimated)

| File | Change |
|---|---|
| `src/novetest/run/adapters/junit_adapter.py` | Add staging logic in `_run_maven` + `_run_gradle`; set `artifact_paths["reports_dir"]` to staged path; set `artifact_paths["coverage_xml"]` when JaCoCo XML found |
| `src/novetest/run/normalizer.py` | Strip trailing `()` from JUnit XML `<testcase name>` when building `identity` + `failure_logs` keys |
| `tests/integration/run/test_junit_maven.py` | Add CLI-level subprocess smoke test |
| `tests/integration/run/test_junit_gradle.py` | Add CLI-level subprocess smoke test |
| `tests/unit/run/adapters/test_junit_adapter.py` | New unit tests: (a) `_run_maven` returns `coverage_xml` populated when JaCoCo XML staged, None otherwise; (b) `_run_maven`/`_run_gradle` return `reports_dir` under `artifact_dir`, not under workspace |
| `tests/unit/run/test_normalizer.py` (or `test_junit_normalizer.py`) | Trailing `()` strip cases: Maven-style, Gradle-style, parametrized |
| `WORKLOG.md` | New entry per protocol |

Likely diff scope: ~150-250 LOC added, mostly in tests. Adapter
changes are surgical (~30-50 LOC for staging + glob).

## 3. Out of scope (explicit)

These were surfaced by Manual Test as worth doing but are NOT part of
this hotfix cycle — they're process work that PM picks up separately:

- **Verification-template amendment** (Manual Test rec #4) — adding a
  CLI-level smoke requirement to every future adapter verification
  request. PM amends `agent-comms/README.md` separately.
- **`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  corollary** (Manual Test rec #5) — formalizing the "Manual Test MUST
  equip and exercise the CLI-level smoke" rule. PM writes the
  amendment decision in a separate commit.
- **Verification doc Gate A relaxation** (Manual Test rec #6) — `mvn -v
  >= 3.9` → `>= 3.8 with Surefire 3.0+ in pom.xml`. Doc edit; PM
  picks this up.
- **`.claude/settings.json` Bash permission pre-auth** (Manual Test
  rec #7) — CEO-side configuration. PM raises it as a question.
- **Multi-module Maven fixture** (Verification doc Scenario D
  "OPTIONAL"). Defer; not blocking.
- **Gradle wrapper for the fixture** (handoff followup #6). Defer; not
  blocking — adapter still works via system `gradle`.
- **`--per-test-class` opt-in** (handoff followup #3). Defer; D1
  stays at `aggregate` default.
- **OTR XML preference** (handoff followup #4). Defer.
- **`--licenses` CLI verb** (original brief §9 deferred). Defer.

Do **not** introduce these in this slice. If you find yourself wanting
to, stop and file a `questions/` entry.

## 4. Definition of Done bullets

Tick when ALL are true:

- [ ] `src/novetest/run/adapters/junit_adapter.py` `_run_maven` stages
      `target/surefire-reports/` (and multi-module variants) under
      `artifact_dir / "native" / "reports" / [<module>/]`; sets
      `artifact_paths["reports_dir"]` to the staged path.
- [ ] `_run_gradle` stages `build/test-results/test/` under
      `artifact_dir / "native" / "reports/"`; sets `artifact_paths["reports_dir"]`
      to the staged path.
- [ ] When `collect_coverage=True`, `_run_maven` globs JaCoCo XML at
      `target/site/jacoco/jacoco.xml` (+ multi-module variants), stages
      under `artifact_dir / "native" / "coverage/"`, and sets
      `artifact_paths["coverage_xml"]` to the staged location.
- [ ] When `collect_coverage=True`, `_run_gradle` globs JaCoCo XML at
      `build/reports/jacoco/test/jacocoTestReport.xml`, stages under
      `artifact_dir / "native" / "coverage/"`, and sets
      `artifact_paths["coverage_xml"]`.
- [ ] When JaCoCo XML is not present (user has no JaCoCo plugin),
      `artifact_paths["coverage_xml"]` is omitted (NOT set to `None`),
      and `payload["warnings"]` carries a `missing-jacoco`
      `engine-misconfigured` entry.
- [ ] `src/novetest/run/normalizer.py` (or equivalent JUnit-XML name →
      identity translation site) strips trailing `()` from test names.
- [ ] Unit-test coverage added for: trailing-paren strip on both
      Maven-style and Gradle-style inputs; parametrized signature
      preserved; `_run_maven`/`_run_gradle` artifact_paths are
      subpaths of `artifact_dir`; coverage_xml population when JaCoCo
      present.
- [ ] CLI-level smoke test added to `test_junit_maven.py` AND
      `test_junit_gradle.py`; both invoke `subprocess.run(["uv", "run",
      "novetest", "run"], ...)`, assert `returncode in (0, 1)`,
      parse the envelope, and assert `engine_name == "junit"`.
- [ ] `uv run pytest -q tests/unit tests/integration` on the team's
      JDK-less host: **0 regressions** (5 skip-gated cases remain
      skip-gated). Pre-hotfix baseline was 1009+10 skips on JDK-less;
      hotfix target is 1009-or-higher + 10-or-higher skips + 0 failures.
- [ ] `uv run mypy --strict` clean.
- [ ] Handoff doc cites this brief's binding contracts and reports
      D1-D6 ratified unchanged from the original cycle's handoff
      (since none of those decisions are affected by the hotfix).
- [ ] Handoff also documents which integration tests' assertions
      were updated for Defect 3 (e.g. the substring match for
      `failed_tests` now matches both Maven and Gradle output).

## 5. Re-verification (Manual Test will re-pass on equipped host)

After your handoff + Main Branch FF-merge, Manual Test will re-pass
the original verification doc on the same equipped host:

```sh
# Re-Gate-B on equipped host:
uv run pytest -q tests/unit tests/integration
# Expected: 1014+ passed, 4-or-fewer skipped, 0 failed
# (5 previously skip-gated cases become 3-5 passes; existing
# pytest-json-report skip remains).

# Re-Scenario-A (Maven happy path):
cd /tmp/junit-smoke-maven && novetest run
# Expected: kind=run-record, engine_name=junit, summary.{passed:4,failed:1,skipped:1},
# failed_tests=["com.example.CalculatorTest#testSubtract"], exit code 1

# Re-Scenario-B (Gradle happy path):
cd /tmp/junit-smoke-gradle && novetest run
# Expected: same shape as Scenario A, failed_tests pin literal also no parens

# Re-Scenario-C (coverage):
cd /tmp/junit-smoke-maven && novetest run --coverage
# Expected: coverage_outcome.kind="fact-set", metadata.mapping_granularity="aggregate",
# metadata.branch_arc_semantics="jacoco-line-counter-index"

# Re-Scenario-G (D3 ambiguous):
cd /tmp/junit-ambig && novetest run
# Expected: same shape as Scenario A + warning ambiguous-build-tool

# Re-Scenario-I (integrated test):
cd /tmp/junit-smoke-maven && novetest test
# Expected: sub_reports.run.engine_name="junit"; recommendations populated

# Re-Scenario-J (replay):
RID=$(novetest run --json | jq -r .data.run_record.run_reference.run_id)
novetest replay $RID
# Expected: replay_outcome.replay_result.classification in {reproducible,inconsistent,unable_to_replay}
```

Scenarios E (JUnit 4 reject) + F (TestNG reject) + K (vendored
launcher) ALREADY PASS and stay green; no re-verification needed.

## 6. Handoff expectations

When you're ready to merge, write
`agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`
with:

1. **DoD bullets believed closed** — list each from §4 with a one-line
   evidence pointer (file path + line range or test name).
2. **Defect closure evidence** — for each of Defect 1/2/3, paste the
   before/after `artifact_paths` shape (or normalized `identity` value
   for D3) showing the contract now holds.
3. **CLI-level smoke results** — paste the `subprocess.run` output
   from the two new tests, both on the team's JDK-less host (should
   skip with the right skip reason) AND, if possible, on a transient
   container with JDK + Maven installed (should pass).
4. **D1-D6 decisions** — confirm all 6 unchanged from the original
   cycle's handoff. No re-ratification needed unless something forced
   a change (in which case file a `questions/` entry first).
5. **Slice diff summary** — `git diff --stat`.
6. **Test counts post-hotfix** — pre-hotfix baseline 1009+10 (JDK-less)
   → post-hotfix expected 1009-or-higher + 10-or-higher + 0 failed on
   the team's host (the new CLI-smoke tests skip-gate the same as the
   existing test_junit_*.py cases).

PM picks up the handoff, dispatches Main Branch for FF-merge, then
Manual Test for re-pass on the equipped host. When Manual Test files
PASSED findings, PM closes the cycle: deletes ALL six transient files
(the original four: task / handoff / verification / findings;
plus the two hotfix files: this task + the hotfix handoff;
plus the new verification + new findings from the re-pass), ticks the
Phase 2.5 JUnit DoD bullet in `delivery-phasing.md`, writes a single
combined history entry covering BOTH the original cycle's lessons
(skip-gate masking) AND the hotfix scope. The history entry is
load-bearing — it pins the "always add CLI-level smoke for new
adapters" lesson so future ecosystems don't repeat it.

## 7. Sanity check before starting

If you find yourself wanting to:

- Modify the orchestration `.relative_to` check at
  `workflows/run.py:85-88` → STOP. The check is correct; the adapter
  must conform.
- Add a `coverage_xml = None` default to `artifact_paths` instead of
  conditionally omitting → STOP. The contract is "omit when absent"
  per all sibling adapters; setting `None` would break the relative-
  path rewrite (it'd try `Path(None).relative_to(...)`).
- Skip writing the CLI-level smoke test — "it's process work, not a
  defect" → STOP. It IS the defect closure — without the CLI smoke,
  this class of bug remains invisible.
- Patch the original handoff to claim DoD bullets you didn't actually
  close → STOP. Original handoff stays as historical record; your new
  handoff lists what THIS cycle closed.
- Touch the .NET adapter / MCP / Replay engine → STOP. Out of scope.

Otherwise: branch a worktree off `3152821` (current main tip), equip
the host per `scripts/dev-host-setup.md §5` (the auto-mode classifier
may require CEO authorization for `sudo apt-get` lines — file a
`questions/` entry if you hit the wall), and start with the CLI-level
smoke test FIRST (red-test first, then fix to green — TDD on the
defect). Then Defect 1 (P0), then Defect 2, then Defect 3.
