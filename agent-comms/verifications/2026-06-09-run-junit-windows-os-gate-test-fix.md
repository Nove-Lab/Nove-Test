---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-09
slug: run-junit-windows-os-gate-test-fix
related:
  - agent-comms/handoffs/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
---

# Verification — Run JUnit Windows OS-gate test fix (3/3 of Windows-CI-fix triple)

## Merged commit

- **HEAD on main after this slice**: `a6ebd91 test(run): skip JUnit tests on Windows per decision §R5 OS gate`
- **Source handoff**: `agent-comms/handoffs/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`
- **Worktree base**: `230420c` → rebased onto `c5c85de` (Coverage + Localization landed first per alphabetic order) → FF-merged as 3/3 in the chain.

## What landed

- **0 src changes** (test-only fix; production JUnit adapter is correctly OS-gated per `decisions/2026-06-03-junit-console-launcher-vendor.md` §R5).
- **5 test files modified** (+94 LOC):
  - `tests/unit/run/test_junit_readiness.py`: `_SKIP_IF_WINDOWS = pytest.mark.skipif(sys.platform.startswith("win"), reason=...)` at line 39; applied as `@_SKIP_IF_WINDOWS` decorator to 7 specific tests (lines 71, 88, 101, 114, 134, 159, 182). `test_windows_os_gate` at line ~176 deliberately UNMARKED — it's the gate-firing regression detector via `monkeypatch.setattr("novetest.run.readiness.sys.platform", "win32")`.
  - `tests/unit/run/adapters/test_junit_adapter.py`: `@pytest.mark.skipif(sys.platform.startswith("win"), ...)` at line 1134 on the `TestGradleCoverageArgv` class (line 1154). Class-level mark covers both `test_init_script_present_with_coverage_and_jacoco` (the failing one) AND `test_init_script_absent_without_coverage` (currently passing sibling) — symmetric coverage across the OS-gated `run_junit` Gradle path.
  - `tests/integration/run/test_junit_gradle.py`: `pytestmark = [Windows-OS-gate-skipif, existing-JDK+Gradle-skipif]` at line 36. List-of-marks pattern — each reason surfaces independently in CI logs.
  - `tests/integration/run/test_junit_maven.py`: same list-of-marks pattern at line 39.
  - `tests/integration/run/test_junit_warnings.py`: single module-level `pytestmark` at line 53 (no list — the existing skip mechanism here is per-test `_require_junit_toolchain()` function-call, not a module-level mark; composing naturally).
- **WORKLOG**: top entry preserved through rebase chain.
- **Net delta**: 5 test files + handoff + WORKLOG = +324 / -8 lines.

## Post-merge test gate (full chain at `a6ebd91`)

```
uv run mypy --strict src/novetest      → Success: no issues found in 93 source files
uv run pytest -q tests/unit tests/integration → 1229 passed + 23 skipped + 1 failed in 32.43s
```

The 1 failed test = `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` (`dotnet not on PATH`) — pre-existing host-equipment dependency, NOT a regression. This slice's handoff §"Pre-existing failure analysis" + the parallel Coverage handoff Gotcha #3 + every recent cycle's WORKLOG all document this identically.

Note: pytest `skipped` count is unchanged at **23** on Linux because the new `skipif` decorators only fire on `sys.platform == "win32"`. On Windows CI the same suite will show 12-17 additional skips (the 12 originally-RED tests + 5 already-passing siblings that share the OS-gated code path), turning 12 RED → 12 SKIPPED.

## Verification scenarios for Manual Test

### Scenario A — Audit the 5 modified test files (charter-mandated audit)

```bash
# 1) test_junit_readiness.py — verify _SKIP_IF_WINDOWS pattern
grep -n '_SKIP_IF_WINDOWS' tests/unit/run/test_junit_readiness.py

# 2) test_junit_adapter.py — verify class-level skipif on TestGradleCoverageArgv
grep -nB1 -A6 'class TestGradleCoverageArgv' tests/unit/run/adapters/test_junit_adapter.py

# 3) test_junit_gradle.py + test_junit_maven.py — verify list-of-marks pattern
grep -nA4 '^pytestmark = \[' tests/integration/run/test_junit_gradle.py tests/integration/run/test_junit_maven.py

# 4) test_junit_warnings.py — verify single module-level skipif
grep -nA3 '^pytestmark' tests/integration/run/test_junit_warnings.py
```

Expected:
- 1 constant definition + 7 `@_SKIP_IF_WINDOWS` decorations on culprit tests; `test_windows_os_gate` UNMARKED
- `@pytest.mark.skipif(sys.platform.startswith("win")...)` immediately above `class TestGradleCoverageArgv:`
- `pytestmark = [mark, mark]` list pattern in gradle + maven
- single `pytestmark = pytest.mark.skipif(...)` in warnings file

### Scenario B — Confirm `test_windows_os_gate` is the gate-firing regression detector

The whole design hinges on this one test running on BOTH Linux/macOS AND Windows. On Linux it uses `monkeypatch.setattr("novetest.run.readiness.sys.platform", "win32")` to simulate Windows; on Windows the monkey-patch is a no-op but the assertion still fires identically.

```bash
# Verify it is NOT marked with @_SKIP_IF_WINDOWS
grep -B5 'def test_windows_os_gate' tests/unit/run/test_junit_readiness.py | head -6

# Run it on Linux (this host) — should pass via monkey-patch
uv run pytest -v tests/unit/run/test_junit_readiness.py::test_windows_os_gate
```

Expected: no `@_SKIP_IF_WINDOWS` decorator immediately above the function; test passes on Linux.

### Scenario C — Run all 5 modified test files on Linux

```bash
uv run pytest -v \
  tests/unit/run/test_junit_readiness.py \
  tests/unit/run/adapters/test_junit_adapter.py
```

Expected: **all green or skipped-by-existing-toolchain-gate** (NOT skipped by the new Windows mark, since we're on Linux). The 7 + 2 marked tests should all pass on Linux.

```bash
uv run pytest -v tests/integration/run/test_junit_gradle.py tests/integration/run/test_junit_maven.py tests/integration/run/test_junit_warnings.py
```

Expected: skipped on hosts without JDK + Maven/Gradle; passed on equipped hosts. The Windows-OS-gate skipif fires only on Windows; on Linux the existing toolchain skipifs surface their reasons.

### Scenario D — list-of-marks composition check

```bash
uv run python -c "
import importlib
m = importlib.import_module('tests.integration.run.test_junit_gradle')
print('pytestmark type:', type(m.pytestmark).__name__)
print('pytestmark len:', len(m.pytestmark))
m2 = importlib.import_module('tests.integration.run.test_junit_maven')
print('maven pytestmark type:', type(m2.pytestmark).__name__)
print('maven pytestmark len:', len(m2.pytestmark))
m3 = importlib.import_module('tests.integration.run.test_junit_warnings')
print('warnings pytestmark type:', type(m3.pytestmark).__name__)
"
```

Expected:
```
pytestmark type: list
pytestmark len: 2
maven pytestmark type: list
maven pytestmark len: 2
warnings pytestmark type: MarkDecorator
```

(`warnings` uses single-mark since per-test `_require_junit_toolchain()` composes naturally.)

### Scenario E — Windows CI matrix verdict (binding criterion)

The 12 RED-on-Windows tests should turn SKIPPED (not RED, not PASSED):

```
tests/unit/run/test_junit_readiness.py::test_ready_when_java_and_mvn_present
tests/unit/run/test_junit_readiness.py::test_missing_jdk
tests/unit/run/test_junit_readiness.py::test_missing_mvn
tests/unit/run/test_junit_readiness.py::test_missing_jupiter
tests/unit/run/test_junit_readiness.py::test_junit4_specific_diagnostic
tests/unit/run/test_junit_readiness.py::test_testng_specific_diagnostic
tests/unit/run/test_junit_readiness.py::test_gradle_wrapper_path
tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco
tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope
tests/integration/run/test_junit_warnings.py::test_cli_smoke_missing_jacoco_emits_envelope_warning
tests/integration/run/test_junit_warnings.py::test_cli_smoke_ambiguous_build_tool_emits_envelope_warning
```

(Note: `test_xunit_v3_deferral_emits_envelope_warning_via_adapter` was in the original 20-failure inventory but it's the `dotnet` one — separate Run-team concern; not part of this JUnit slice.)

```bash
gh run list --workflow ci.yml --branch main --limit 1
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

Expected on Windows × 3 Py = 3 cells: `conclusion: success` AND the 12 tests above show `SKIPPED` in the verbose output. Reason strings should mention "decision 2026-06-03-junit-console-launcher-vendor.md §R5" and/or "Open Question #16".

## Critical edge cases worth probing

1. **The production adapter is correct; the OS gate fires by design** (`decisions/2026-06-03-junit-console-launcher-vendor.md` §R5). This slice does NOT amend the gate; it makes 12 tests honor the gate's existence. Manual Test should NOT propose lifting the gate or skipping `test_windows_os_gate` — the gate is the production contract until Open Question #16 lands a Windows binary pipeline.

2. **A real production-code bug at `src/novetest/run/adapters/junit_adapter.py:590` is DEFERRED to Open Q #16** (handoff Choice 2). `init_script_path.write_text(_GRADLE_IGNORE_FAILURES_INIT_SCRIPT)` lacks `encoding="utf-8"`; on Windows `Path.write_text()` defaults to cp1252 which can't encode the em-dash (U+2014) in `_GRADLE_IGNORE_FAILURES_INIT_SCRIPT` comment text → 0x97 byte → test reads back with `encoding="utf-8"` → `UnicodeDecodeError`. **Invisible in production** because the readiness OS gate intercepts requests BEFORE the adapter runs on Windows. When Open Q #16 lifts the gate, the implementer MUST fix this together (un-skip + add `encoding="utf-8"` in the same slice).

3. **`test_windows_os_gate` is the only Windows-runtime regression detector for the JUnit gate.** If a future Open Q #16 slice lifts the gate without amending or removing this test, the test will fail on Windows — which IS the intended regression signal (the gate is no longer firing). Manual Test should not propose adding `@_SKIP_IF_WINDOWS` to it.

4. **List-of-marks vs OR-composition rationale** (handoff Choice 3). `pytestmark = [Windows-mark, JDK-mark]` is OR-composed at skip-evaluation time AND each reason surfaces independently in CI logs (vs concatenated). Future cleanup PRs proposing "combine into one skipif for brevity" would lose the granular reason surfacing — Manual Test should flag any such PRs.

5. **Brief's Category-D mechanism diagnosis was slightly off** (handoff Open Item #1). Brief assumed `subprocess.run(text=True)` cp1252 issue; actual mechanism is `Path.write_text` defaulting to cp1252 in production code. Same fix shape (skipif) still works. The skip docstring captures the actual mechanism for the future Open-Q#16 implementer.

6. **§2.5 equip-and-exercise gate does NOT fire on this slice.** The 2026-06-04 decision binds adapter cycles (`src/novetest/run/adapters/**` + `tests/integration/run/**` PAIR condition); this slice touches integration tests only, ZERO src. The file-glob heuristic explicitly requires both halves. The 2026-06-08 default-posture meta-decision tier-2 SHOULD applies; the team's "verification on equipped Windows CI matrix" posture (deferred to post-merge CI) satisfies that as the binding evidence per task brief §"CI matrix verdict criterion".

## Rebase / merge notes for the audit trail

- **Worktree branch**: `run-team/junit-windows-os-gate-test-fix`, based on `230420c`.
- **Rebase**: required — main moved by `4110645` (Coverage) + `c5c85de` (Localization) ahead per alphabetic order.
- **Conflict count**: 1 (WORKLOG.md only — three slices all added 2026-06-09 top entries).
- **Resolution**: run on top (newest-in-history), `---`, localization, `---`, coverage — preserving the alphabetic-order chain in reverse-chronological narrative order per "newest entry on top" convention. Source files: zero conflict (test-only slice; disjoint file footprints from peers).
- **FF-merge**: `c5c85de..a6ebd91` clean after rebase.
- **Test gate post-conflict-resolution** (mandate): mypy clean, pytest 1229 passed + 23 skipped + 1 environmental fail. Run at end-of-chain per charter (single gate covers the 3-slice integrated state).
- **Worktree cleanup**: deferred to after this verification doc lands.
