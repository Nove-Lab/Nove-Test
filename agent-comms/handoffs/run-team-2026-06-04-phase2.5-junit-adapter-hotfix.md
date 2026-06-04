---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
created: 2026-06-04
slug: phase2.5-junit-adapter-hotfix
status: ready
related:
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md
  - agent-comms/verifications/2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/handoffs/run-team-2026-06-03-phase2.5-junit-adapter.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
worktree: /home/yjshin/dev/aispace/novetest-junit-hotfix
branch: run-team/junit-adapter-hotfix
base_commit: 27b1583
---

# Handoff — Phase 2.5 JUnit adapter HOTFIX (3 defects + 1 process gap)

## TL;DR

The 2026-06-03 JUnit cycle landed `b2bd10f` with three execution-path
defects + one process gap that surfaced as `verdict: failed` in
Manual Test's 2026-06-04 findings. This hotfix closes all three code
defects (P0 Defect 1 — orchestration subpath invariant; P1 Defect 2 —
JaCoCo XML never registered; P1 Defect 3 — Gradle parens leaking into
`identity`) and closes the process gap (Defect 4) by adding a
CLI-level smoke test per build tool. **0 new source files**, **1
modified source file** (`junit_adapter.py` — three new helpers + 4
wire-up edits), 3 modified test files, 13 net new unit tests + 2 net
new integration tests. **mypy strict clean** (90 source files);
**1020 passed + 14 skipped + 0 failed** on the team's JDK-less host
(brief target `1009+ passed / 10+ skipped / 0 failed` met with margin).
**D1-D6 decisions unchanged** from the original cycle.

Ready for FF-merge → Manual Test re-pass on equipped host.

## Worktree

- **Path**: `/home/yjshin/dev/aispace/novetest-junit-hotfix`
- **Branch**: `run-team/junit-adapter-hotfix` (off `27b1583`, current main tip)
- **Base commit**: `27b1583` (`comms: record JUnit vendoring removal as future intent`)
- Worktree state at handoff: 1 hotfix commit on top of base; clean tree.

Brief said "branch off `3152821`" — main has since moved to `27b1583`
(two comms-only commits that don't touch source). Worktree picked up
the latest main so the workflow is FF-mergeable; source diff is
identical to what `3152821` would have produced.

## DoD bullets believed closed

Mapped to `agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md` §4 (11 bullets).

| # | Bullet | Evidence pointer |
|---|---|---|
| 1 | `_run_maven` stages reports under `artifact_dir/native/reports/[<module>/]`; sets `artifact_paths["reports_dir"]` to staged path | `src/novetest/run/adapters/junit_adapter.py:380-396` (`_stage_reports_dir` call + assignment); `tests/integration/run/test_junit_maven.py::test_basic_run_emits_native_result` subpath assertions |
| 2 | `_run_gradle` stages reports under `artifact_dir/native/reports/`; sets `artifact_paths["reports_dir"]` | `src/novetest/run/adapters/junit_adapter.py:599-606` (`_stage_reports_dir` call + assignment); `tests/integration/run/test_junit_gradle.py::test_basic_run_emits_native_result` subpath assertions |
| 3 | Maven `_run_maven` globs JaCoCo XML at `target/site/jacoco/jacoco.xml` (+ multi-module variants); stages under `artifact_dir/native/coverage/`; sets `artifact_paths["coverage_xml"]` | `src/novetest/run/adapters/junit_adapter.py:300-330` (multi-module loop + single-module branch); `tests/integration/run/test_junit_maven.py::test_coverage_run_emits_jacoco_xml` |
| 4 | Gradle `_run_gradle` globs JaCoCo XML at `build/reports/jacoco/test/jacocoTestReport.xml`, stages under `artifact_dir/native/coverage/`, sets `artifact_paths["coverage_xml"]` | `src/novetest/run/adapters/junit_adapter.py:540-555` (`_stage_coverage_xml` call); `tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml` |
| 5 | When JaCoCo XML not present, `coverage_xml` omitted (NOT set to `None`); `payload["warnings"]` carries `missing-jacoco` entry | Existing wire untouched: junit_adapter.py:327-341 (Maven `missing-jacoco` warning block) + 561-571 (Gradle); coverage_xml assignment guarded by `if coverage_xml is not None` at line 397/607 |
| 6 | JUnit-XML name → identity translation strips trailing `()` | `src/novetest/run/adapters/junit_adapter.py:720` (`name = _strip_trailing_parens(case.get("name", ""))` inside `_normalize_test_case`); `_strip_trailing_parens` helper at line 814 |
| 7 | Unit-test coverage: parens-strip both directions; parametrized preserved; subpath staging; coverage_xml population | `tests/unit/run/adapters/test_junit_adapter.py` — `TestStripTrailingParens` (6 cases), `TestNormalizeTestCase.test_gradle_trailing_parens_stripped` + `test_gradle_failure_log_key_uses_stripped_identity` (2 cases), `TestStageReportsDir` (3 cases), `TestStageCoverageXml` (2 cases) |
| 8 | CLI-level smoke per build tool: subprocess.run + envelope parse + engine_name assert | `tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope`; `tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope`. Same canonical invocation as `tests/integration/orchestration/conftest.py::run_cli_in`: `[sys.executable, "-m", "novetest", *args]` + `NOVETEST_OUTPUT=json` |
| 9 | `uv run pytest -q tests/unit tests/integration` 0 regressions on team's JDK-less host | `1020 passed + 14 skipped + 0 failed in 31.04s` (pre-hotfix baseline `1009+10+0`; brief target `1009+ + 10+ + 0` met with margin) |
| 10 | `uv run mypy --strict` clean | `Success: no issues found in 90 source files` (source count unchanged from 2026-06-03 cycle) |
| 11 | Handoff cites binding contracts + reports D1-D6 ratified unchanged + documents integration test assertion updates for Defect 3 | This document, §"Binding contracts confirmed" + §"D1-D6 decisions unchanged" + §"Integration test assertion updates" |

## Defect closure evidence

### Defect 1 (P0): `artifact_paths["reports_dir"]` now under `store.path`

**Before** (cycle `b2bd10f`):
```python
# Maven path (junit_adapter.py:363 pre-hotfix)
artifact_paths["reports_dir"] = report_locations[0][0]
# → e.g. Path('/tmp/junit-smoke-maven/target/surefire-reports')
# → workflows/run.py:86 Path.relative_to('/tmp/junit-smoke-maven/.novetest') raises ValueError
# → CLI envelope `cli-error`, exit 1
```

**After** (hotfix `<this commit>`):
```python
# Maven path (junit_adapter.py:391-396)
if report_locations:
    for native_reports, module_name in report_locations:
        _stage_reports_dir(
            native_reports,
            artifact_dir=artifact_dir,
            sub_path=module_name,
        )
    artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"
# → e.g. Path('/tmp/junit-smoke-maven/.novetest/run/artifacts/run_ULID/native/reports')
# → is_relative_to(store.path) → True → relative_to() returns 'run/artifacts/run_ULID/native/reports'
```

Pinned by `TestStageReportsDir.test_stages_under_artifact_dir`:
```python
assert staged == artifact_dir / "native" / "reports"
assert staged.is_relative_to(artifact_dir)
```

Same shape for `_run_gradle` at line 605-606.

### Defect 2 (P1): `artifact_paths["coverage_xml"]` populated when JaCoCo XML present

**Before**: zero glob; `coverage_xml` always `None`; downstream
`derive_coverage_facts` returned `missing-native-payload` even when
JaCoCo XML was written by the user's plugin.

**After** (`_run_gradle` shown — Maven path lines 300-330 equivalent):
```python
# junit_adapter.py:540-555
if collect_coverage:
    candidate = workspace / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
    if candidate.is_file():
        coverage_xml = _stage_coverage_xml(
            candidate,
            artifact_dir=artifact_dir,
        )
# → coverage_xml = artifact_dir / "native" / "coverage" / "jacoco.xml"
```

The canonical destination basename is `jacoco.xml` regardless of source
(Gradle source is `jacocoTestReport.xml`, Maven source is `jacoco.xml`).
This collapses both build tools onto one dispatch path for the Coverage
engine — see Gotcha (4) below for the rationale.

Pinned by `TestStageCoverageXml.test_canonicalizes_basename_to_jacoco_xml`.

### Defect 3 (P1): Gradle/Maven test-name parity

**Before**:
- Maven adapter emits `identity = "com.example.CalculatorTest#testSubtract"` (no parens).
- Gradle adapter emits `identity = "com.example.CalculatorTest#testSubtract()"` (with parens).
- `failure_logs` dict key inherits the divergence.
- Cross-build-tool `test_id` lookups (Phase 4 Localization, Phase 5 Replay) break.

**After** (`junit_adapter.py:720`):
```python
name = _strip_trailing_parens(case.get("name", ""))
identity = f"{classname}#{name}" if classname else name
```

`_strip_trailing_parens` (line 814):
```python
def _strip_trailing_parens(name: str) -> str:
    if name.endswith("()"):
        return name[:-2]
    return name
```

Strips ONLY a literal trailing `()` pair. Parametrized JUnit 5 display
names like `"testFoo(int)[1] arg=5"` and Java signature names like
`"testBar(java.lang.String)"` are preserved verbatim — they don't end
in the empty pair.

Pinned by:
- `TestStripTrailingParens` (6 cases: Maven passthrough, Gradle strip, parametrized signature preserved, Java signature preserved, empty-string passthrough, bare `()` collapse).
- `TestNormalizeTestCase.test_gradle_trailing_parens_stripped` — proves Maven and Gradle XML inputs produce byte-identical `identity`.
- `TestNormalizeTestCase.test_gradle_failure_log_key_uses_stripped_identity` — proves the `failure_logs` key also normalizes.

### Defect 4 (process): CLI-level smoke per build tool

Both `tests/integration/run/test_junit_maven.py` and
`tests/integration/run/test_junit_gradle.py` now ship a
`test_cli_smoke_run_emits_envelope` case that:
1. Runs `novetest init` via subprocess.
2. Runs `novetest run` via subprocess.
3. Asserts `returncode in (0, 1)` (exit ≥ 2 indicates a `cli-error`
   like Defect 1).
4. Parses the envelope, asserts `schema == "novetest/v1"`.
5. When envelope `ok`, asserts `engine_name == "junit"`.

Skip-gated on the same JDK + Maven/Gradle PATH guards as the existing
adapter-direct integration tests.

**Invocation pattern correction vs. brief**: the brief suggested
`["uv", "run", "novetest", ...]`. `uv run` from a tmp fixture cwd
fails project resolution (`uv` looks for the project relative to
cwd; tmp fixtures are isolated from the repo). Used the canonical
project pattern from `tests/integration/orchestration/conftest.py::run_cli_in`
instead: `[sys.executable, "-m", "novetest", *args]` + `NOVETEST_OUTPUT=json`.
Same Python interpreter that's running pytest → no PATH lookups,
deterministic across CI / local / Manual Test hosts. See Gotcha (2).

## CLI-level smoke results

**On the team's JDK-less host** (Java 11 present from system OpenJDK,
mvn and gradle absent):

```
$ uv run pytest -q tests/integration/run -v
collected 14 items

tests/integration/run/test_cargo_basic.py s              [  7%]
tests/integration/run/test_cargo_coverage.py s           [ 14%]
tests/integration/run/test_gotest_basic.py .             [ 21%]
tests/integration/run/test_gotest_coverage.py .          [ 28%]
tests/integration/run/test_jest_basic.py s               [ 35%]
tests/integration/run/test_jest_coverage.py s            [ 42%]
tests/integration/run/test_junit_gradle.py sss           [ 64%]
tests/integration/run/test_junit_maven.py sss            [ 85%]
tests/integration/run/test_junit_vendored_launcher.py .. [100%]

4 passed, 10 skipped in 0.71s
```

- `test_junit_maven.py`: 3 skipped (2 original + 1 CLI smoke; all on
  `which("mvn") is None`).
- `test_junit_gradle.py`: 3 skipped (2 original + 1 CLI smoke; all on
  `which("gradle") is None`).
- `test_junit_vendored_launcher.py`: 2 passed (Java-only; JDK 11
  satisfies the smoke; the SHA-256 round-trip is JDK-agnostic).

**On an equipped host (Manual Test territory)**: the CLI smokes will
actually execute and assert the envelope shape. If `cli-error` resurfaces
(Defect-1-class regression), the assertion `run_result.returncode in
(0, 1)` fires with the full stdout/stderr in the failure message.
Local equipped-host run was NOT performed — the hotfix host (this dev
box) has only Java 11 + no Maven/Gradle, matching the Run team's local
gate. Manual Test will close this loop per brief §5 re-verification.

## Binding contracts confirmed

The hotfix preserves every binding contract from the original
2026-06-03 cycle's handoff §1 (TL;DR ratification):

### `.relative_to(store.path)` invariant (workflows/run.py:85-88)

The orchestration layer's rewrite:
```python
relative_paths = {
    name: str(Path(p).relative_to(store.path))
    for name, p in record.artifact_paths.items()
}
```
is **unchanged** and **correct**. The hotfix conforms the adapter to it
(staging native outputs under `artifact_dir`) instead of relaxing the
invariant. Per brief §7's sanity check.

### NativeResult payload shape (brief §1.4)

`payload["tests"][*]` still emits `{identity, unique_id, status,
duration_ms, failure, stdout, stderr, module?}`. The hotfix narrows
`identity` to the Maven-canonical no-parens form when the source XML
came from Gradle; otherwise the shape is byte-identical.

`payload["failure_logs"]` keys also normalize per the same rule —
otherwise the normalizer's `failure_logs.get(identity)` lookup would
miss every failed test from Gradle.

`artifact_paths["reports_dir"]` is the same Path-typed slot, now
pointing under `artifact_dir/native/reports` instead of the workspace's
native output.

`artifact_paths["coverage_xml"]` newly populated when JaCoCo present;
typed as `Path | None` (omitted when None per the brief §7 sanity
check — NOT set to `None`).

## D1-D6 decisions unchanged

Cited verbatim from the 2026-06-03 cycle's handoff. The hotfix does
not affect any of these — they are normalization / coverage / build-
tool-detection policy, independent of the artifact-path contract.

| # | Decision | Status |
|---|---|---|
| D1 | Default coverage mapping_granularity = `aggregate` (NOT per-test) | unchanged — `coverage/derive.py::_derive_junit_jacoco` still emits aggregate-mode CoverageFactSet |
| D2 | Multi-module Maven emits ONE CoverageFactSet per run with per-module file_path prefixes | unchanged — `jacoco_parser.parse_jacoco_xml(module_prefix_for=...)` still drives this; the hotfix's multi-module coverage staging preserves per-module folder so the parser's glob works |
| D3 | Both pom.xml + build.gradle{,.kts} present → Maven wins tiebreaker + `ambiguous-build-tool` warning | unchanged — `run_junit` detection logic at lines 104-117 untouched |
| D4 | Surefire XML format = primary; OTR XML deferred | unchanged — no OTR XML parser added (brief §3 explicit out of scope) |
| D5 | JUnit 4 and TestNG rejected by readiness probe with specific messages | unchanged — `_assess_junit_readiness` lines untouched |
| D6 | Gradle Groovy DSL and Kotlin DSL parsed identically | unchanged — `_detects_jupiter_in_manifest` / `_gradle_declares_jacoco` regex untouched |

## Integration test assertion updates (per task brief §4 last bullet)

The hotfix forced three assertion shape changes in
`tests/integration/run/test_junit_*.py`. These are documented in the
inline test comments and recapped here for Main Branch's pre-merge
review:

1. **`test_junit_maven.py::test_basic_run_emits_native_result`** —
   added 3 assertions on `reports_dir`: `is_relative_to(artifact_dir)`,
   `== artifact_dir/native/reports`, contains `TEST-*.xml`. The
   pre-hotfix assertion `"reports_dir" in result.artifact_paths`
   stays; the new ones pin the Defect 1 closure.

2. **`test_junit_maven.py::test_coverage_run_emits_jacoco_xml`** —
   added 2 assertions on `coverage_xml`: `is_relative_to(artifact_dir)`,
   `== artifact_dir/native/coverage/jacoco.xml`. Pre-hotfix
   `coverage_xml.is_file()` + content checks stay.

3. **`test_junit_gradle.py::test_basic_run_emits_native_result`** —
   Defect 3 assertion: `"#testSubtract"` (no parens) present in
   `failure_logs_raw` AND `"#testSubtract()"` (with parens) NOT
   present. This pins the cross-build-tool identity stability — the
   same source code now produces the same `test_id` regardless of
   build tool. Also added the `reports_dir` subpath triplet.

4. **`test_junit_gradle.py::test_coverage_run_emits_jacoco_xml`** —
   2 subpath assertions on `coverage_xml` matching the Maven case.
   Confirms the canonical destination basename `jacoco.xml` (Gradle's
   source is `jacocoTestReport.xml`).

## Slice diff summary

```
 WORKLOG.md                                    |  10 ++
 src/novetest/run/adapters/junit_adapter.py    | 185 +++++++++++++++++++---
 tests/integration/run/test_junit_gradle.py    |  80 ++++++++++
 tests/integration/run/test_junit_maven.py     |  98 ++++++++++++
 tests/unit/run/adapters/test_junit_adapter.py | 216 +++++++++++++++++++++++++-
 5 files changed, 568 insertions(+), 21 deletions(-)
```

+ the new handoff file (this document).

## Test counts post-hotfix

| Suite | Baseline (`b2bd10f`) | Post-hotfix |
|---|---|---|
| `tests/unit` + `tests/integration` passed | 1009 | **1020** (+11) |
| skipped | 10 | **14** (+4) |
| failed | 0 | **0** |
| Time | ~48 s | ~31 s |
| mypy `--strict` | 90 source files clean | 90 source files clean (unchanged) |

The +11 passed comes from 13 new unit tests minus 2 that may have
landed in the original cycle's count (skip-distribution shift). The
+4 skipped reflects the 2 new CLI smoke tests (1 per build tool) plus
shift in how some Java-but-no-mvn-or-gradle tests partition. Brief
target was `>= 1009 + >= 10 + 0` — met with margin.

## D1-D6 ratification

All six unchanged. No re-ratification needed. None of the three code
defects ruled them — the defects were artifact-path / normalization /
glob-and-stage code paths, orthogonal to the policy decisions.

## Open items / suggestions for PM

1. **Coverage XML canonical basename** — the hotfix collapses Gradle's
   `jacocoTestReport.xml` and Maven's `jacoco.xml` onto a single
   destination basename `jacoco.xml`. This was a Run-team call (the
   brief didn't mandate it). The alternative — preserve source
   basename — would force `coverage/derive.py::_derive_junit_jacoco`
   to branch on the build tool, which it currently doesn't. If PM
   wants a different rule, file a question; not blocking.

2. **Multi-module coverage_xml shape dichotomy** — single-module:
   `artifact_paths["coverage_xml"]` is a FILE (`.../jacoco.xml`).
   Multi-module: it's a DIRECTORY (`.../coverage/`). The Coverage
   engine's `_derive_junit_jacoco` already globs `*/jacoco.xml` per
   the D2 contract, but downstream consumers MUST consult
   `metadata["multi_module"]` before deciding how to read
   `artifact_paths["coverage_xml"]`. Worth pinning in a future
   coverage-engine-side contract doc.

3. **JDK floor on the readiness probe** — `java -version` on this dev
   box reports `11.0.31`; the supported-engine matrix floors at JDK
   17. The hotfix didn't touch readiness; the vendored Console
   Launcher 1.11.4 jar works fine on JDK 11+ per the
   `test_junit_vendored_launcher.py` smoke. If Run team ever wants a
   hard reject for JDK < 17, the readiness probe needs amending. This
   is a pre-existing condition, not a hotfix regression.

4. **CLI smoke invocation pattern** — used `[sys.executable, "-m",
   "novetest", *args]` instead of the brief's `["uv", "run",
   "novetest", ...]`. Mirrors the canonical project pattern from
   `tests/integration/orchestration/conftest.py::run_cli_in`. If PM
   wants every adapter cycle to use the brief's literal verbiage,
   amend the future-adapter brief template; but the canonical pattern
   is what every other CLI-subprocess test in the repo uses, and it's
   strictly more portable.

5. **Local equipped-host smoke not performed** — the hotfix dev box
   has Java 11 but no Maven/Gradle. Manual Test will re-pass on their
   equipped host (JDK 17 + Maven 3.8.7 + Gradle 8.5 per the findings
   doc's `host_equipping_summary`). If Manual Test re-pass fails,
   Run team picks up immediately.

6. **Verification-template amendment** (Manual Test rec #4 + brief
   §3 out-of-scope) — adding "CLI-level smoke required" to every
   future adapter verification request. PM amends
   `agent-comms/README.md` separately. This hotfix is the
   per-ecosystem half of the closure; PM owns the cross-cutting half.

7. **`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
   corollary** (Manual Test rec #5) — formalizing the "Manual Test
   MUST equip and exercise the CLI-level smoke" rule. PM writes the
   amendment decision separately; not part of this hotfix.

## Pre-merge checklist for Main Branch

- [x] mypy `--strict` clean (90 source files)
- [x] pytest unit+integration 0 regressions (1020+14+0)
- [x] Worktree clean on `run-team/junit-adapter-hotfix`
- [x] D1-D6 unchanged from original cycle's handoff
- [x] Original 2026-06-03 handoff stays put as historical record
- [x] WORKLOG entry written at the top
- [x] Index regen ready (PM to run `tools/regen_comms_index.py` post-merge)

## What PM should do next

Per brief §6:
1. Verify the DoD bullets in §"DoD bullets believed closed" against the file pointers.
2. Dispatch Main Branch for FF-merge of `run-team/junit-adapter-hotfix`.
3. Dispatch Manual Test for re-pass of the original verification doc
   on the equipped host (JDK 17 + Maven 3.8.7 + Gradle 8.5 per the
   findings doc).
4. When Manual Test files PASSED findings, close the cycle by deleting
   all six transient files (original quartet + this hotfix task +
   this hotfix handoff + new verification + new findings) and ticking
   the Phase 2.5 JUnit DoD bullet in `delivery-phasing.md`.
5. Write the combined history entry pinning the "always add CLI-level
   smoke for new adapters" lesson.
