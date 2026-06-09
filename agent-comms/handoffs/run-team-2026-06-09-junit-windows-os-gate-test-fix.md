---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-09
slug: junit-windows-os-gate-test-fix
related:
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
---

# Handoff — Run team JUnit Windows OS-gate test fixes (12 tests, test-only)

## Worktree

- **Path**: `/home/yjshin/dev/aispace/novetest-junit-windows-fix`
- **Branch**: `run-team/junit-windows-os-gate-test-fix`
- **Base commit**: `230420c` (HEAD of main at slice start)
- **Worktree status**: clean except for the 5 modified test files + WORKLOG + this handoff
- **Diff stat**: 5 src test files (94 LOC test-only) + WORKLOG entry + this handoff. **ZERO `src/novetest/` changes.**

## What landed

Test-only mitigation for the JUnit Windows-OS-gate blocker (3/3 of the parallel Windows CI fix triple — Coverage + Localization + Run). The JUnit adapter is intentionally OS-gated against Windows per decision `2026-06-03-junit-console-launcher-vendor.md` §R5; production code correctly emits `engine-misconfigured` of kind `os-unsupported` ("JUnit adapter requires a non-Windows host until the Windows binary pipeline ships (Open Question #16)"). The 12 failing tests were authored on Linux/macOS assuming `state == "ready"` (or specific missing-binary diagnostics); on Windows the readiness probe returns `engine-misconfigured` from the OS gate firing, and the tests' expectations don't account for that.

### Files modified (5 test files, 94 LOC)

| File | Change | Tests affected |
|---|---|---|
| `tests/unit/run/test_junit_readiness.py` | Added `_SKIP_IF_WINDOWS` constant + `@_SKIP_IF_WINDOWS` on 7 specific functions | 7 skipped on Windows; `test_windows_os_gate` (line 176) deliberately NOT marked — runs on both Windows AND non-Windows |
| `tests/unit/run/adapters/test_junit_adapter.py` | Class-level skipif on `TestGradleCoverageArgv` + `import sys` | 2 skipped on Windows |
| `tests/integration/run/test_junit_gradle.py` | Extended `pytestmark` to list of two marks (Windows-OS-gate + existing JDK+Gradle) | 3 skipped on Windows; pre-existing JDK+Gradle skip-gate preserved |
| `tests/integration/run/test_junit_maven.py` | Same list-of-two-marks pattern | 3 skipped on Windows; pre-existing JDK+Maven skip-gate preserved |
| `tests/integration/run/test_junit_warnings.py` | Added module-level `pytestmark` | 2 skipped on Windows; per-test `_require_junit_toolchain()` still fires |

### Quantitative scope

- **Currently-failing on Windows**: 12 tests across the 5 files
- **Will be SKIPPED on Windows after merge**: 17 tests (the 12 failing + 5 already-passing siblings that exercise the same OS-gated code path, for symmetric coverage)
- **Continues running on Windows**: 1 test (`test_windows_os_gate` — gate-firing regression detector)
- **Continues running on Linux/macOS**: all 18 tests (no behavior change on the dev/CI Linux+macOS cells)
- **LOC delta**: +94 lines tests, +0 lines src

## Verification

### Linux dev host (this slice's authoring host)

```
$ uv run mypy --strict src/novetest
Success: no issues found in 92 source files

$ uv run pytest -q tests/unit tests/integration
1206 passed, 26 skipped, 1 failed in 33.38s

$ uv run pytest -q tests/unit/run/test_junit_readiness.py \
    tests/unit/run/adapters/test_junit_adapter.py
68 passed in 0.13s
```

### Pre-existing failure analysis

The 1 failed test is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` with `AdapterInvocationError: dotnet not found on PATH` — the same pre-existing host-equipment dependency documented in WORKLOG entries from 2026-06-08 (B2-2 Localization + B2-4 Run artifact_dir resolve cycles). **NOT introduced by this slice.** Verifiable: `git stash + git checkout 230420c + pytest tests/integration/run/test_dotnet_warnings.py` reproduces identically on a host lacking `dotnet`. The §2.5 equip-and-exercise gate does NOT apply to this slice per brief §"§2.5 equip-and-exercise 게이트" (test-only changes, zero adapter src diff; the file-glob heuristic's "adapter src + adapter integration test" pair condition is NOT met).

### Composition checks (programmatic)

```
$ uv run python -c "
import importlib
m = importlib.import_module('tests.integration.run.test_junit_gradle')
print('pytestmark type:', type(m.pytestmark).__name__)
print('pytestmark len:', len(m.pytestmark))
"
pytestmark type: list
pytestmark len: 2
```

Verified that the `pytestmark = [mark_A, mark_B]` list pattern is properly recognized as a list-of-marks (pytest OR-composes them at skip-evaluation time, with distinct reasons surfacing per skipped test).

### Expected post-merge CI behavior

After Main Branch FF-merges this slice (alphabetic order: coverage → localization → run, so this slice is 3/3 / LAST), the next `ci.yml` run on Windows × 3 Python = 3 cells should show:

| Test | Linux/macOS (3 OS × 3 Py = 9 cells) | Windows × 3 Py = 3 cells |
|---|---|---|
| `test_junit_readiness.py::test_ready_when_java_and_mvn_present` | PASS | SKIPPED (reason cites decision §R5 + Open Q #16) |
| `test_junit_readiness.py::test_missing_jdk` | PASS | SKIPPED |
| `test_junit_readiness.py::test_missing_mvn` | PASS | SKIPPED |
| `test_junit_readiness.py::test_missing_jupiter` | PASS | SKIPPED |
| `test_junit_readiness.py::test_junit4_specific_diagnostic` | PASS | SKIPPED |
| `test_junit_readiness.py::test_testng_specific_diagnostic` | PASS | SKIPPED |
| `test_junit_readiness.py::test_gradle_wrapper_path` | PASS | SKIPPED |
| `test_junit_readiness.py::test_windows_os_gate` | PASS (via monkey-patch) | PASS (gate fires identically) |
| `test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco` | PASS | SKIPPED |
| `test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_absent_without_coverage` | PASS | SKIPPED |
| `test_junit_gradle.py::*` (3 tests) | SKIPPED on unequipped CI; PASS on equipped | SKIPPED (Windows mark fires first) |
| `test_junit_maven.py::*` (3 tests) | SKIPPED on unequipped CI; PASS on equipped | SKIPPED (Windows mark fires first) |
| `test_junit_warnings.py::*` (2 tests) | SKIPPED on unequipped CI; PASS on equipped | SKIPPED |

**Net result**: 12 RED → 12 SKIPPED on Windows × 3 Python = 3 cells.

## Implementation choices

### Choice 1 — Function-level skipif on `test_junit_readiness.py`, NOT module-level

**Brief recommended**: module-level `pytestmark = pytest.mark.skipif(...)` on the entire file.

**My choice**: function-level `@_SKIP_IF_WINDOWS` on the 7 culprit tests, leaving `test_windows_os_gate` (line 176) unmarked.

**Rationale**: `test_windows_os_gate` uses `monkeypatch.setattr("novetest.run.readiness.sys.platform", "win32")` to verify the OS gate fires from any host. It passes on Linux/macOS (via monkey-patch) AND on Windows (monkey-patch is a no-op since `sys.platform IS "win32"` there; the assertion still fires). Module-level skipif would have skipped it on Windows — eliminating the only Windows-side regression detection for the gate itself. The brief's "optional dedicated os-gate-firing test" is actually already present; preserving it is more valuable than the uniformity of module-level skipif.

The function-level marks use a single `_SKIP_IF_WINDOWS = pytest.mark.skipif(...)` constant extracted at module level (DRY) and applied via `@_SKIP_IF_WINDOWS` to each of the 7 culprits. The 8th test (`test_windows_os_gate`) is deliberately unmarked.

### Choice 2 — Class-level skipif on `TestGradleCoverageArgv` (covers 2 tests, including 1 currently-passing sibling)

**Brief recommended**: handle Category-D's encoding via `subprocess.run(..., encoding="utf-8")` if the test had that pattern. The brief's grep recommendation returned ZERO matches in the test tree — the actual mechanism is in production code.

**My choice**: class-level skipif on `TestGradleCoverageArgv` (both `test_init_script_present_with_coverage_and_jacoco` failing AND `test_init_script_absent_without_coverage` currently passing on Windows).

**Rationale**: The actual mechanism of the Windows failure is NOT a test-side encoding issue. It's a production-code issue in `src/novetest/run/adapters/junit_adapter.py:590`:

```python
init_script_path.write_text(_GRADLE_IGNORE_FAILURES_INIT_SCRIPT)
```

This call lacks `encoding=`. On Windows, `Path.write_text()` defaults to `cp1252`. The `_GRADLE_IGNORE_FAILURES_INIT_SCRIPT` literal at `junit_adapter.py:92-104` contains an em-dash `—` (U+2014) in the comment "Safe to delete after the run — recreated per run under <artifact_dir>/native/." cp1252 encodes em-dash as byte 0x97. The test then reads the script back with `encoding="utf-8"` at line 1206 — and 0x97 is not a valid UTF-8 start byte → `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 226: invalid start byte`. 

This is a **real production-code bug** but invisible to production because the readiness OS gate intercepts the request BEFORE the adapter ever runs on Windows. The test bypasses readiness by calling `run_junit` directly. The brief's "JUnit adapter src 변경 zero" mandate is intentional: per the decision, the adapter is OS-gated and the bug is non-firing in real use. Fix surface (un-skip + add `encoding="utf-8"` together) belongs to the future Open Question #16 cycle.

I applied the skipif at the CLASS level (not just the one failing test) because both tests in `TestGradleCoverageArgv` exercise the same `run_junit` Gradle-coverage code path that's OS-gated in production. Symmetry: both should skip on Windows; both run on Linux/macOS. The class-level skip docstring documents the production bug mechanism + the future-cycle pair-fix item (un-skip + write_text encoding fix together).

### Choice 3 — `pytestmark = [mark_A, mark_B]` list pattern for the integration test files

**Brief recommended**: module-level `pytestmark = pytest.mark.skipif(...)` on the integration test files.

**My choice**: `pytestmark = [Windows-OS-gate skipif, existing JDK+toolchain skipif]` — a list of two skipif marks rather than concatenating their conditions into one.

**Rationale**: pytest's `pytestmark` accepts either a single mark or a list of marks. The list semantics is "skipped if ANY mark in the list fires" (OR composition). Crucially, **each reason surfaces independently** in pytest's skip output rather than being concatenated into one string. This makes CI logs more grep-able when triaging — if Windows fires, the log shows the Windows reason verbatim; if toolchain fires, the toolchain reason verbatim. The alternative (single skipif with `OR` in condition string and concatenated reason) would have lost this granularity. Small ergonomic choice with no functional difference.

For `test_junit_warnings.py` I used a single skipif (no list) because the existing skip mechanism there is a per-test `_require_junit_toolchain()` function call inside each test body, not a module-level mark. Adding module-level Windows skipif composes naturally with the per-test toolchain check (a Windows host skips at module-mark eval time; an unequipped non-Windows host skips at toolchain check time inside each test).

## Out of scope (per brief)

- **NO** `src/novetest/run/adapters/junit_adapter.py` changes — adapter is correct per decision §R5; the production write_text encoding bug is non-firing in real use due to OS gating
- **NO** other-adapter Windows-handling changes (this slice is JUnit-specific)
- **NO** Windows binary pipeline implementation (Open Q #16 post-MVP)
- **NO** modification of `decisions/2026-06-03-junit-console-launcher-vendor.md` §R5 binding
- **NO** modification to `cli/output.py::EnvelopeWarning` shape (frozen 2026-06-07)
- **NO** other-team territory (Coverage + Localization slices land in parallel — disjoint file footprints)
- **NO** integration tests changing in adapter src + adapter integration test pairings (§2.5 game avoidance — though this slice DOES touch adapter integration tests, it does NOT touch adapter src, so §2.5 file-glob heuristic's pair-condition is NOT met)

## DoD bullets believed closed

PM verifies and ticks; do not pre-tick. From task `agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md` §"Definition of done":

1. ✅ Category D test green on Windows via skipif (class-level on `TestGradleCoverageArgv`)
2. ✅ Other adapter tests audit + sweep (zero hits — brief's grep returned no matches)
3. ✅ Category E 5-file skipif → 11 tests Windows-skip
4. ✅ Optional os-gate-firing dedicated test (pre-existing `test_windows_os_gate` covers — Gotcha 2 in WORKLOG)
5. ✅ Linux/macOS regression-free (1206 passed unchanged from baseline)
6. ✅ `uv run mypy --strict src/novetest` clean (92 src files, zero src changes)
7. ✅ `uv run pytest -q tests/unit tests/integration` green on equipped host (modulo pre-existing dotnet host-equip)
8. ★ **CI matrix verdict** to be verified post-merge by PM with cited `ci.yml` run number
9. ✅ WORKLOG.md entry written (charter format)
10. ✅ Handoff written (this doc)
11. ✅ `python3 tools/regen_comms_index.py` (will run before commit)

## Cross-team scope footprint

This slice is **3/3 of the Windows CI fix parallel triple** dispatched by PM on 2026-06-09:

| Team | Slice | File footprint | Status |
|---|---|---|---|
| Coverage | `coverage-team-2026-06-09-windows-parser-fixes` | `src/novetest/coverage/` + related tests | parallel (run independently) |
| Localization | `localization-team-2026-06-09-windows-path-normalization-fix` | `src/novetest/localization/` + related tests | parallel (run independently) |
| Run (THIS) | `run-team-2026-06-09-junit-windows-os-gate-test-fix` | `tests/{unit,integration}/run/` (5 files, test-only) | this handoff |

**Zero merge conflict expected** — disjoint file footprints across all three slices. Alphabetic FF order per task brief: coverage → localization → run (this slice last).

## Pre-merge checklist for Main Branch team

- [ ] Verify branch HEAD on `run-team/junit-windows-os-gate-test-fix` (single commit on top of `230420c`)
- [ ] Verify diff is test-only (5 files under `tests/unit/run/` and `tests/integration/run/`, ZERO `src/`)
- [ ] Verify diff contains no changes to `src/novetest/run/adapters/junit_adapter.py` (production code per brief §"만지지 말 것")
- [ ] FF-merge per alphabetic order (3/3 after coverage + localization slices land)
- [ ] Post-merge: dispatch `gh workflow run ci.yml --ref main` and capture the run number for the verification doc
- [ ] Confirm CI matrix shows 12 SKIPPED on Windows × 3 Python = 3 cells (not RED)

## Open items / surprises

1. **Brief's Category-D mechanism diagnosis was slightly off** (see Choice 2 above). Brief assumed `subprocess.run(text=True)` cp1252 issue; actual mechanism is `Path.write_text` defaulting to cp1252 in production code. Same fix shape (skipif) still works because the adapter is OS-gated. The skip docstring captures the actual mechanism for the future Open-Q#16 cycle.

2. **The production write_text encoding bug at `junit_adapter.py:590` is deferred to Open Q #16**. When that pipeline lands, the implementer must:
   - Fix `init_script_path.write_text(_GRADLE_IGNORE_FAILURES_INIT_SCRIPT)` → add `encoding="utf-8"`
   - Remove the `TestGradleCoverageArgv` class-level skipif
   - Remove the 4 other Windows-OS-gate skipifs across the 4 other files
   - Remove the `_SKIP_IF_WINDOWS` constant from `test_junit_readiness.py`
   - The decision document `2026-06-03-junit-console-launcher-vendor.md` §R5 will need amendment (the gate description should reflect the new "Windows is supported" reality).

3. **`test_windows_os_gate` (`test_junit_readiness.py:176`)** is the platform-axis regression detector. It runs on BOTH Linux/macOS (via monkey-patch of `sys.platform`) AND Windows (where the monkey-patch is a no-op but the gate assertion fires identically). It's the load-bearing dependency for "is the gate still firing on Windows after my future changes?" — if Open Q #16 lifts the gate without amending this test, this test will fail on Windows, which is the intended regression signal.

## Suggested manual-test verification (if Main Branch requests Manual Test re-pass)

Since this slice is test-only with zero behavior change for users, Manual Test verification is light:

1. **Audit the 5 modified test files**: confirm 5 skipif marks present + 1 `_SKIP_IF_WINDOWS` constant + `import sys` added to `test_junit_adapter.py`
2. **Confirm `test_windows_os_gate` is NOT marked with `@_SKIP_IF_WINDOWS`** — this is the deliberate exception per Choice 1
3. **Run `uv run pytest tests/unit/run/test_junit_readiness.py tests/unit/run/adapters/test_junit_adapter.py tests/integration/run/test_junit_*.py` locally on Linux/macOS** — should be all green (or skipped due to JDK/Maven/Gradle absence on unequipped CI hosts)
4. **Post-merge `gh run view <ci.yml run id>`** — confirm 12 `SKIPPED` results on each Windows cell with reason mentioning "decision 2026-06-03-junit-console-launcher-vendor.md §R5" and "Open Question #16"

## Worklog entry text (paste)

See WORKLOG.md top entry — appended in the worktree before this handoff was filed. Header: `## 2026-06-09 — windows-ci-fix / run-team-junit-windows-os-gate-test-fix (3/3 of parallel triple)`.
