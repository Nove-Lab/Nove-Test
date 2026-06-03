---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
created: 2026-06-04
slug: phase2.5-junit-adapter
verdict: failed
related:
  - agent-comms/verifications/2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/handoffs/run-team-2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - scripts/dev-host-setup.md
merged_tip_verified: b2bd10f
host_equipping_summary: "JDK 17.0.19 (openjdk-17-jdk via apt) + Maven 3.8.7 (apt) + Gradle 8.5 (gradle.org official zip, user-level at $HOME/.local/gradle-8.5)"
---

# Findings — Phase 2.5 JUnit 5 (Jupiter) adapter — **FAILED**

## TL;DR — verdict and headline

**Verdict: `failed`.** The slice **cannot ship as-is**. End-to-end CLI invocation of `novetest run` on any JUnit project (Maven OR Gradle, with OR without `--coverage`) hard-fails with a structured `cli-error` due to an orchestration-vs-adapter contract mismatch on `artifact_paths` (Defect 4 below). `novetest test` (Phase 6 integrated flow) is broken on JUnit via the same root cause. The Phase 5 ↔ Phase 2.5 cross-interaction (`novetest replay` on a JUnit run, Scenario J) is therefore unverifiable until the hotfix lands.

What works: `_vendor/` asset (SHA-256, wheel inclusion, importlib.resources resolution, `java -jar --version`) ✓; readiness probe negative paths (JUnit 4 reject, TestNG reject) ✓; `novetest init` on Maven AND Gradle fixtures ✓; mypy strict (90 source files) ✓.

What's broken: every execution path that produces a Run Record (Scenarios A, B, C, D, G, I, J at the CLI level) + 3 integration tests that were skip-gated on a JDK-less host but **fail when actually executed against a real Maven/Gradle toolchain** (which is the polyglot-host-parity contract this slice was supposed to honor).

The skip-gating masked all three defects from both Run team's local gate AND Main Branch's pre-merge gate. **Process gap, not just a code defect.**

| # | Defect | Severity | Surface |
|---|---|---|---|
| 1 | `artifact_paths["reports_dir"]` set to native Maven/Gradle output (`<workspace>/target/surefire-reports/` or `<workspace>/build/test-results/test/`) violates orchestration's `.relative_to(store.path)` invariant → `cli-error` on every `novetest run`/`novetest test` execution path | **P0 (blocker)** | wire-surface |
| 2 | `artifact_paths["coverage_xml"]` is **never set** by the JUnit adapter even when `collect_coverage=True` (no glob in `_run_maven`/`_run_gradle` for `jacoco.xml`) → integration tests fail when actually run | P1 | wire-surface |
| 3 | Gradle's JUnit XML reporter produces `<testcase name="testSubtract()">` (with parens); Maven's Surefire strips them. Adapter normalizer surfaces the parens as-is in `payload["tests"][*].identity` AND in `failure_logs` keys. Cross-build-tool `test_id` divergence | P1 | normalization |
| 4 | Team's integration tests call `run_junit()` directly, bypassing the CLI envelope layer that enforces the subpath invariant — defects 1+2+3 were structurally invisible to the unit/integration gate | Process | testing discipline |

These are 3 separate code defects and 1 process gap. Run team hotfix scope estimate: 1 short cycle.

---

## Host equipping (the equipping path the CEO authorized)

Per "equipped host로 준비해서 진행해" (CEO 2026-06-04), the JDK-less verification host was equipped before testing:

```sh
# 1. Refresh apt lists (sudo, password CEO-provided)
sudo apt-get update                                            # OK

# 2. JDK + Maven (system-wide via apt — dev-host-setup.md §5 canonical path)
sudo apt-get install -y openjdk-17-jdk maven gradle            # OK
java -version → openjdk version "17.0.19" 2026-04-21 ✓
mvn -version  → Apache Maven 3.8.7                             ⚠ (matrix says 3.9+; see §"Matrix deviation note")
gradle -v     → Gradle 4.4.1                                   ❌ (matrix floor is 7.6 — Ubuntu noble ships 4.4.1)

# 3. Gradle 8.5 via gradle.org official zip (user-level, no sudo)
curl -fsSL https://services.gradle.org/distributions/gradle-8.5-bin.zip -o /tmp/gradle-8.5-bin.zip
unzip -q /tmp/gradle-8.5-bin.zip -d $HOME/.local/
echo 'export PATH=$HOME/.local/gradle-8.5/bin:$PATH' >> ~/.bashrc
gradle -v     → Gradle 8.5                                     ✓
```

### Matrix deviation note (informational, NOT a slice defect)

`decisions/2026-05-25-supported-engine-matrix.md` row "Maven (Surefire) OR Gradle …" lists "Surefire 3.0 / Gradle 7.6" as the floor. The verification doc Gate A asks for `mvn -v` >= 3.9, BUT what actually matters is the **Surefire plugin** version (declared in the user's `pom.xml`, not the Maven CLI version). The Maven 3.8.7 we installed runs Surefire 3.2.5 (declared by the fixture's pom.xml) cleanly — verified by inspecting `mvn -B test` output. PM may want to soften Gate A's `mvn -v >= 3.9` line to `mvn -v >= 3.8 with Surefire 3.0+ in pom.xml` for future verifications; Ubuntu 24.04 noble apt currently ships Maven 3.8.7 only.

### Auto-mode classifier observations (for handoff #7 closure)

Three things were blocked by the auto-mode classifier before CEO authorization:

1. `bash <(curl get.sdkman.io)` — "remotely fetched installer" → blocked. CEO chose apt path instead.
2. `sudo apt-get install openjdk-17-jdk …` (first attempt) — "system-wide install needs explicit per-command authorization" → CEO issued explicit authorization → succeeded.
3. `apt-get update` (passwordless probe) — denied as "credential exploration" → had to be the second probe in the same sentence after CEO password.

Handoff §"Open questions / followups for PM" #7 anticipated this exactly. The pattern: each new agent that needs to equip a fresh host will hit the same three walls. PM may want to either (a) pre-author a `.claude/settings.json` Bash permission rule for the §5 install lines, or (b) maintain a CEO-prefab equipped host snapshot.

---

## Gate results

### Gate A — Pre-flight host equipping ✓ (after the §"Host equipping" steps above)

```sh
$ java -version 2>&1
openjdk version "17.0.19" 2026-04-21
$ mvn -v 2>&1 | head -1
Apache Maven 3.8.7
$ gradle -v 2>&1 | head -10 | grep ^Gradle
Gradle 8.5
```

### Gate B — Test gate parity on equipped host — **FAILED**

```sh
$ uv run mypy
Success: no issues found in 90 source files     ✓

$ uv run pytest -q tests/unit tests/integration
1011 passed, 5 skipped, 3 FAILED in 102.00s     ❌

FAILED tests/integration/run/test_junit_gradle.py::test_basic_run_emits_native_result
FAILED tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml
FAILED tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml
```

The verification doc's "**~1015 passed, ~4 skipped**" target on equipped host **was not met**. Three new integration tests fail when actually executed.

| Suite | Verification doc target | Observed | Delta |
|---|---|---|---|
| `tests/unit/` + `tests/integration/` passed | ~1015 | 1011 | -4 |
| skipped | ~4 | 5 | +1 |
| **failed** | **0** | **3** | **+3** |

(The 5 skipped: 1 long-standing `pytest-json-report` skip + 4 host-specific skips that were unrelated to this slice. Verified by grepping skip reasons.)

The skip-gated tests on the team's JDK-less host masked these failures because `shutil.which("java") is None or shutil.which("mvn") is None` evaluated `True` there. On any equipped host, the skip guards evaluate `False` and the tests actually run and reveal the defects below.

---

## Defect details (P0 → P1 → P1)

### Defect 1 (P0 / blocker) — `cli-error` on every JUnit `novetest run`/`novetest test`

**Reproducer (Maven path):**
```sh
cp -r tests/fixtures/projects/junit-maven-basic /tmp/junit-smoke-maven
cd /tmp/junit-smoke-maven
uv --project <repo> run novetest init      # OK; engine_readiness.state="ready"; engine_version=5.10.2
uv --project <repo> run novetest run       # FAILS, exit 1
```

**Observed envelope (verbatim from `/tmp/A-run-maven.json`):**
```json
{
  "command": "cli",
  "data": {},
  "errors": [
    {
      "code": "cli-error",
      "details": {},
      "message": "'/tmp/junit-smoke-maven/target/surefire-reports' is not in the subpath of '/tmp/junit-smoke-maven/.novetest' OR one path is relative and the other is absolute."
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit code: **1**, top-level `command` is `"cli"` (not `"run"` — the error fires before envelope composition).

**Gradle path** (`/tmp/B-run-gradle.json`): same `cli-error` with `'/tmp/junit-smoke-gradle/build/test-results/test' is not in the subpath of '/tmp/junit-smoke-gradle/.novetest'`.

**With `--coverage`** (Maven, `/tmp/C-run-coverage.json`): same `cli-error`. Coverage path never reached.

**Integrated `novetest test`** (Maven, `/tmp/I-test-maven.json`): same `cli-error`. Phase 6 cross-interaction broken.

**D3 ambiguous build tool** (`/tmp/G-run-ambig.json`): D3 tiebreaker fires (Maven wins per handoff §D3), then execution path hits the same `cli-error`. The D3 decision is correctly wired, but its happy-path is unreachable.

**Root cause (load-bearing source pointer):**

`src/novetest/orchestration/workflows/run.py:85-88`:
```python
relative_paths = {
    name: str(Path(p).relative_to(store.path))
    for name, p in record.artifact_paths.items()
}
persisted_record = replace(record, artifact_paths=relative_paths)
```

`src/novetest/orchestration/workflows/test.py:155` (identical pattern in integrated `novetest test` flow).

`Path.relative_to()` raises `ValueError` with the exact message above when the path is not a subpath. Sibling adapters (`pytest_adapter.py`, `gotest_adapter.py`, etc.) place every artifact under `artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"` (which IS under `store.path`), so the invariant holds for them.

`src/novetest/run/adapters/junit_adapter.py` violates this in two places:

- Line **363** (Maven path): `artifact_paths["reports_dir"] = report_locations[0][0]` where `report_locations[0][0]` is `workspace / "target" / "surefire-reports"` (Maven Surefire's native output directory; OUTSIDE `store.path`).
- Line **560** (Gradle path): `artifact_paths["reports_dir"] = reports_dir` where `reports_dir = workspace / "build" / "test-results" / "test"` (Gradle's native; OUTSIDE `store.path`).

**Three viable fixes (Run team's call):**

1. **Copy/move** reports XML into `artifact_dir / "native" / "reports/"` before returning the `NativeResult`, then set `artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"`. Matches the pytest/gotest/cargo pattern. Cost: 1 directory copy per run; preserves the `payload["reports"][*].path` references (which already point to the native location — those don't go through `.relative_to`).
2. **Drop `reports_dir` from `artifact_paths`** entirely and rely on `payload["reports"][i].path` (which is not subjected to the `.relative_to` rewrite). The team's tests would need to update to read the path from `payload["reports"]` instead. Smallest code change but breaks the documented contract (handoff §1.4 lists `reports_dir` as a key in `artifact_paths`).
3. **Relax the orchestration subpath check** to skip `.relative_to` for paths that aren't subpaths (just preserve them as absolute strings). Most invasive — affects the JSON wire shape for every engine; would need a decision doc.

PM and Run team should pick. Fix #1 is the lowest-risk and matches sibling adapters.

### Defect 2 (P1) — `--coverage` never populates `artifact_paths["coverage_xml"]`

**Reproducer** (Maven; same Gradle): observed in `tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml` and `test_junit_gradle.py::test_coverage_run_emits_jacoco_xml`. With `collect_coverage=True`, the resulting `NativeResult.artifact_paths` contains only `{stdout, stderr, reports_dir}` — never `coverage_xml`.

**Observed full `artifact_paths` (Maven, from pytest output):**
```python
{
  'reports_dir': PosixPath('.../junit-maven-basic/target/surefire-reports'),
  'stderr': PosixPath('.../art/native/stderr.log'),
  'stdout': PosixPath('.../art/native/stdout.log'),
}
```

`payload["tests"]` correctly contains all 6 test cases with the expected pass/fail/skip pattern (`{passed: 4, failed: 1, skipped: 1, errored: 0}` exactly as the verification doc predicts for Scenario C). So the Maven `mvn -B test` invocation runs cleanly; coverage emission is the only failure.

**Root cause:**

`src/novetest/run/adapters/junit_adapter.py:559-560` (Gradle branch shown — Maven branch lines 356-365 has same pattern):
```python
if reports_dir.is_dir():
    artifact_paths["reports_dir"] = reports_dir
```

No corresponding block for `target/site/jacoco/jacoco.xml` (Maven) or `build/reports/jacoco/test/jacocoTestReport.xml` (Gradle). The adapter's `NativeResult` contract (handoff §1.4) declares `artifact_paths["coverage_xml"]: Path | None` — but `_run_maven` and `_run_gradle` simply never set it.

This is a real functional gap (not just a key-name mismatch): even when JaCoCo IS configured in the user's pom.xml/build.gradle (the fixtures both ship it), the adapter doesn't probe for the JaCoCo output. Coverage-engine downstream `_derive_junit_jacoco` therefore has nothing to derive from.

Note: this defect compounds Defect 1 — even if Defect 1 were fixed, `novetest run --coverage` would still emit `coverage_outcome.kind == "unavailable"` (the empty-cache branch) instead of `kind == "fact-set"`. Verification doc Scenario C's pin (`coverage_outcome.kind == "fact-set"` + `metadata.branch_arc_semantics == "jacoco-line-counter-index"`) cannot be hit until both Defects 1 and 2 are fixed.

**Fix scope:** add a `_glob_jacoco_xml(workspace, build_tool)` helper that returns `target/site/jacoco/jacoco.xml` (Maven) or `build/reports/jacoco/test/jacocoTestReport.xml` (Gradle), and set `artifact_paths["coverage_xml"] = <found_path>` when present (None otherwise). Then route through the same staging logic as Defect 1's Fix #1.

### Defect 3 (P1) — Gradle path produces test_id with trailing `()`, Maven path strips them

**Reproducer:** `tests/integration/run/test_junit_gradle.py::test_basic_run_emits_native_result`:
```
AssertionError: assert 'com.example.CalculatorTest#testSubtract' in 
  {'com.example.CalculatorTest#testSubtract()': 'native/failures/com.example.CalculatorTest_testSubtract__.log'}
```

**Observed (Gradle) `payload["tests"][*].identity` values:**
```python
['com.example.CalculatorTest#testDivideByZero()',
 'com.example.CalculatorTest#testAdd()',
 'com.example.CalculatorTest#testSubtract()',
 'com.example.CalculatorTest#testSkip()',   # if present
 'com.example.CalculatorTest#testMultiply()']
```

**Observed (Maven) `payload["tests"][*].identity` values:**
```python
['com.example.CalculatorTest#testDivideByZero',
 'com.example.CalculatorTest#testAdd',
 'com.example.CalculatorTest#testSubtract',
 'com.example.CalculatorTest#testMultiply']
```

The verification doc's Scenario A pin (which only covers the Maven side) says `failed_tests` contains exactly `"com.example.CalculatorTest#testSubtract"` (no parens). Gradle's `failed_tests` would emit `"com.example.CalculatorTest#testSubtract()"` (with parens), which:

1. Diverges from Maven (cross-build-tool inconsistency — the SAME source code produces TWO different test IDs depending on which build tool ran it).
2. Diverges from the verification doc pin (it would not match a substring assert for the no-parens variant).
3. Breaks downstream Phase 5 (Replay) `test_id`-based filter and Phase 4 (Localization) per-test attribution if any of those layers use the Maven literal as a key.

**Root cause:** Gradle 8.5 (and JUnit Platform 1.10+) emits JUnit XML where `<testcase name="testSubtract()">` includes the parentheses (matches Java method signature). Maven Surefire 3.x strips them in its XML reporter. The team's normalizer at `src/novetest/run/normalizer.py` (lines exact-grep needed but `tests/integration/run/test_junit_gradle.py:78` confirms the surface) reads the `name` attribute as-is into `identity` without stripping parens. Maven's `name` arrives without parens — coincidentally consistent with the expected format.

**Fix scope:** in the JUnit-XML normalizer path, strip trailing `()` from the `name` attribute when constructing `identity`. (Parametrized JUnit tests have `name="testFoo(int) [1] arg=5"` — care needed; strip only the literal trailing `()`.) Add unit-test coverage for both Maven (no parens) and Gradle (with parens) input XML.

### Defect-adjacent (process gap, not a code bug) — Integration tests bypass the CLI envelope layer

The team's three integration tests (`test_junit_maven.py`, `test_junit_gradle.py`) call `run_junit(...)` directly:

```python
# tests/integration/run/test_junit_maven.py
result = await run_junit(target, artifact_dir=..., timeout=300.0, collect_coverage=True)
assert "coverage_xml" in result.artifact_paths
```

This skips `src/novetest/orchestration/workflows/run.py` (where `.relative_to` is enforced) AND skips `src/novetest/cli/app.py` (where envelope projection happens). So the integration tests can pass even when the CLI is broken (as long as the adapter returns *some* `NativeResult`).

The cargo cycle had the same risk and resolved it by ALSO running a CLI-level smoke. The JUnit cycle's integration tests don't include a CLI-level case (zero `subprocess.run(["novetest", "run"])` calls under `tests/integration/run/test_junit_*.py`). 

PM should consider:
1. A short follow-up brief asking Run team to add a CLI-level integration test per ecosystem (or factor it into a shared harness so it's automatic for each new adapter).
2. The verification doc could (post-fix) include a "Gate B+" that asserts `subprocess.run(["uv", "run", "novetest", "run"], …).returncode == <expected>` for each fixture so this class of bug is caught at pre-merge.

---

## Scenario-by-scenario results

| Scenario | Verdict | Notes |
|---|---|---|
| **Gate A** Host equipping | ✓ | JDK17, Maven 3.8.7 + Gradle 8.5 installed per §"Host equipping" |
| **Gate B** Test gate parity | ❌ | 1011 passed, 5 skipped, **3 FAILED** (vs target ~1015 + ~4 skipped + 0 failed) |
| **Cap-1** SHA-256 round-trip | ✓ | `pin_matches_observed: true`, 2,809,597 bytes; byte-identical to verification doc |
| **Cap-2** Wheel inspection | ✓ | All three `_vendor/` entries ship at the canonical wheel paths |
| **Cap-3** `engine_selector` pairs | ✓ | 6 pairs including `["java", "junit"]`; byte-identical to verification doc |
| **Cap-4/5/6** init/run on misconfigured host | ✓ (Main-Branch-side, not re-pinned) | I'm on an equipped host now; re-pinning would require uninstalling the JDK. Verification doc allows skip. |
| **A** Maven happy path via CLI | ❌ | `cli-error` (Defect 1) |
| **B** Gradle happy path via CLI | ❌ | `cli-error` (Defect 1) |
| **C** `--coverage` via CLI (Maven) | ❌ | `cli-error` (Defect 1); if D1 fixed, would then expose Defect 2 (no coverage_xml in artifact_paths) |
| **D** Multi-module Maven | n/a | No fixture committed; verification doc marks OPTIONAL |
| **E** JUnit 4 reject | ✓ | Exit 4, `issues[0]` literal exact-matches verification doc (`"JUnit 4 detected (artifactId=junit, version=4.x); Nove Test supports JUnit 5 (Jupiter) only — migrate via the JUnit Vintage Engine or upgrade tests to Jupiter"`) |
| **F** TestNG reject | ✓ | Exit 4, `issues[0]` exact-matches (`"TestNG detected (artifactId=testng); Nove Test currently supports JUnit 5 only — TestNG support is deferred to a future cycle"`) |
| **G** D3 ambiguous (pom.xml + build.gradle.kts) | ❌ | D3 tiebreaker fires correctly (Maven wins); then execution path hits Defect 1's `cli-error`. The D3 decision logic IS wired; its happy-path is unreachable. |
| **H** Engine-misconfigured negatives | ✓ (Main-Branch Cap-6) | Re-pin would require uninstalling JDK |
| **I** `novetest test` integrated flow | ❌ | `cli-error` (Defect 1 via `test.py:155` — same root cause as `run.py:86`) |
| **J** `novetest replay <run_id>` after JUnit run | ⏸ blocked | Cannot produce a successful `run_id` due to Defect 1; Phase 5 ↔ Phase 2.5 cross-interaction is unverifiable |
| **K** Console Launcher discovery | ✓ | `tests/integration/run/test_junit_vendored_launcher.py` — 2/2 passed in 0.24s (importlib.resources resolution + `java -jar --version`) |

### Critical edges (verification doc §"Critical edge cases worth probing")

| Edge | Verdict | Notes |
|---|---|---|
| **1** Hatchling deviation from brief §1.1 | ✓ (informational) | `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` ships all three `_vendor/` entries (Cap-2 confirmed) |
| **2** PyApp binary blob extraction (R4 closure) | n/a | Release team's smoke at handoff; not in scope here |
| **3** Gradle wrapper absent from fixture | ✓ (informational) | Confirmed: `tests/fixtures/projects/junit-gradle-basic/gradlew` not present; system `gradle 8.5` was used. Handoff followup #6 captures the slice-future commit. |
| **4** Multi-JDK projects | n/a | Out of scope per handoff |
| **5** OTR (open-test-reporting) XML preference | n/a | Out of scope per handoff |
| **6** `--per-test-class` opt-in absent | ✓ (informational) | Aggregate-only per D1; confirmed by inspecting `_derive_junit_jacoco` dispatch |
| **7** SHA-256 pin update flow | ✓ (informational) | `_vendor/__init__.py` exports `LAUNCHER_JAR_SHA256` and `LAUNCHER_VERSION` consistently with the NOTICE file and the actual jar bytes (Cap-1 round-trip) |
| **8** `_SUBCOMMAND_TOKENS` extension | n/a | Out of scope (no new CLI verb added) |

---

## Commands run + observed-output capture inventory

Verbatim envelopes for each scenario captured under `/tmp/`:

```
/tmp/A-run-maven.json         Scenario A — Maven happy path; cli-error (Defect 1)
/tmp/B-run-gradle.json        Scenario B — Gradle happy path; cli-error (Defect 1)
/tmp/C-run-coverage.json      Scenario C — Maven --coverage; cli-error (Defect 1)
/tmp/E-init-junit4.json       Scenario E — JUnit 4 init OK
/tmp/E-run-junit4.json        Scenario E — JUnit 4 run rejected, exit 4 ✓
/tmp/F-init-testng.json       Scenario F — TestNG init OK
/tmp/F-run-testng.json        Scenario F — TestNG run rejected, exit 4 ✓
/tmp/G-init-ambig.json        Scenario G — D3 ambiguous init OK
/tmp/G-run-ambig.json         Scenario G — D3 execution hit cli-error
/tmp/I-test-maven.json        Scenario I — novetest test integrated; cli-error
```

Workspaces preserved on disk: `/tmp/junit-smoke-maven`, `/tmp/junit-smoke-gradle`, `/tmp/junit-smoke-junit4`, `/tmp/junit-smoke-testng`, `/tmp/junit-smoke-ambig`. PM or Run team can re-run any of the above by replaying the same `uv --project <repo> run novetest run` against any of those workspaces.

Built wheel preserved at `/tmp/nove-wheel-probe-mt/novetest-0.0.0-py3-none-any.whl` (Cap-2 evidence).

---

## Recommendations for PM

1. **Do NOT tick Phase 2.5 JUnit DoD in `delivery-phasing.md` yet.** Three of the 13 brief §11 bullets are not satisfied as written:
   - "feat works end-to-end against a real Maven project" — broken at the CLI (D1).
   - "feat works end-to-end against a real Gradle project" — broken at the CLI (D1); also test_id divergence (D3).
   - "Coverage path works" — `coverage_xml` never populated (D2).
   The remaining 10 bullets (vendored asset, mypy, fixtures, R4 mitigation, readiness probe negative paths, etc.) ARE satisfied.

2. **Open a hotfix cycle for Run team** with the following scope:
   - Defect 1 (P0): stage reports_dir under `artifact_dir/native/reports/` — copy or `shutil.move`. PM picks fix shape (Fix #1 recommended). This unblocks Scenarios A/B/C/G/I/J at the CLI.
   - Defect 2 (P1): add a `_glob_jacoco_xml` step and set `artifact_paths["coverage_xml"]`.
   - Defect 3 (P1): strip trailing `()` from `<testcase name>` during normalization; add explicit unit-test coverage for both Maven-style (no parens) and Gradle-style (with parens) inputs.
   - Add a CLI-level smoke (one per build tool: `subprocess.run([... "novetest", "run"])`) to `tests/integration/run/test_junit_*.py` so this class of defect is caught at the team's local gate.
   - Estimated 1 short cycle.

3. **Do not push to `origin/main`** until the hotfix lands. The current `main` ships a slice whose primary advertised feature (`novetest run` on JUnit Maven/Gradle) hard-fails at the CLI. The pre-merge gate green numbers (1009 + 10 skip) were JDK-less skip-counts, not actual execution.

4. **Process gap — verification harness extension.** Consider amending the verification request template to require Manual Test to run a CLI-level smoke for every newly-added engine (`subprocess.run([... "novetest", "run"])` on the canonical happy-path fixture) AND assert `exit code in {0, 1}` (not 2-or-higher CLI-error). This would have caught Defect 1 at the verification stage automatically. Cargo team's similar slice survived this risk by luck; future adapters should be insured against it.

5. **Process gap — polyglot-host-parity contract.** Handoff §"Manual Test E2E checklist" said the equipped-host gate "cannot self-verify" — true at the team level. But the verification doc Gate B said "Re-run on your host AFTER you uninstall the JDK" for Scenario H, which gives Manual Test an out from re-pinning the engine-misconfigured side. There's no symmetric "out" on the equipping side: an equipped Manual Test is the ONLY layer that catches the JUnit-execution defects. The 2026-05-29 polyglot-host-parity decision should be amended (or a corollary added) to say: "for any adapter cycle, Manual Test MUST equip and exercise the CLI-level smoke before verdict; the merge is not 'shippable' until that step lands."

6. **Verification doc Gate A** line `mvn -v # expect 3.9+` should be relaxed to `mvn -v # expect 3.8+ AND fixture pom.xml pins Surefire 3.0+` (Ubuntu 24.04 noble ships Maven 3.8.7 only; the Surefire pin in the fixture is what actually matters). Minor doc edit.

7. **Auto-mode classifier amendment** — handoff #7 anticipated this. PM may want to either:
   - Add a `.claude/settings.json` Bash permission rule pre-authorizing `sudo apt-get install -y openjdk-17-jdk maven gradle` (the exact dev-host-setup.md §5 line) so future agents can equip without three rounds of CEO authorization, OR
   - Pre-build a CEO-maintained equipped-host snapshot (e.g. a Docker image) that future verification runs reuse.

8. **Console Launcher discovery (Scenario K) IS verified** even though the runtime path doesn't invoke it for `novetest run`. The vendored-asset infrastructure (SHA-256 pin, importlib.resources, `java -jar`, EPL-2.0 NOTICE, wheel inclusion) is the load-bearing piece of this slice and it's solid. The execution-path defects above are independent of the vendored-asset work.

---

## What's salvageable from this slice (if PM wants to land a partial)

If hotfix latency matters and PM wants to ship a slice with caveats, the following sub-components are independently solid and could ship under a "preview" gate:

- The `_vendor/` directory + `THIRD_PARTY_NOTICES.txt` + `LAUNCHER_JAR_SHA256` constant + Hatchling force-include (Cap-1, Cap-2). This establishes the vendored-asset pattern for future adapters (.NET cycle next).
- The readiness probe (`_assess_junit_readiness`) including JDK17 / Maven / Gradle / wrapper / Jupiter / JUnit 4 / TestNG / OS-Windows gating (Scenarios E + F + Cap-4/5/6). The doctor-shape table (handoff §10) is wired correctly.
- The `engine_selector` registering `["java", "junit"]` (Cap-3).
- The mypy strict clean across 90 source files (Gate B.1).

PM may want to surface a `--engine=preview-junit` flag or similar, but my read is **don't ship partial** — the user-facing wire surface is `novetest run`, and if it doesn't work for JUnit, the slice's product-framing claim ("Bring `novetest run` from 4 to 5 ecosystems") is false. Cleanest path: hotfix, re-verify, ship.

---

## Closing pointer

Verdict: **`failed`**. Hotfix scope is 3 small code changes + 2 new integration tests + 1 process amendment. Estimated 1 short Run-team cycle. After hotfix:

- Re-run Gate B on equipped host → expect 1014 passed + 4 skipped + 0 failed.
- Re-run Scenarios A, B, C, G, I, J → expect all PASS.
- Tick Phase 2.5 JUnit DoD bullet.
- Push to origin/main.

I will preserve workspaces under `/tmp/junit-smoke-*` and capture files under `/tmp/{A,B,C,E,F,G,I}-*.json` until Run team picks up the hotfix or PM signals safe-to-clean.
