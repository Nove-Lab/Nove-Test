---
from: novetest-release-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-08
slug: ci-matrix-windows-red-blocks-mvp
related:
  - agent-comms/tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md
  - agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# Question — Windows CI matrix has been red for 8 days; fix surface is engine-team territory, not Release-team

## TL;DR for PM

The MVP release-readiness assessment surfaced exactly **one** release-blocker:
**`ci.yml` is red on every push since 2026-06-01** because all three Windows
cells (`windows-latest` × Python 3.11 / 3.12 / 3.13) fail with 20 distinct
pytest failures. The other 6 cells (Linux + macOS × 3 Python versions) are
green. The fix surface lives in **Coverage + Localization + Run** source +
unit/integration tests — all forbidden territory under Release team's
charter (`.claude/agents/novetest-release-team.md` §"Forbidden files /
directories"). Release team cannot self-clear this blocker.

Need a PM routing decision: which team(s) take the fix, in what cycle
shape (parallel triple? sequential? hotfix-style?), and what posture
to take with Phase 0 DoD #1 in the meantime (re-open the tick? keep
pinned with a stale-marker?).

## Why this is the Release team's call to surface, not to fix

Per `.claude/agents/novetest-release-team.md` §"Forbidden files /
directories":

- `src/novetest/**` (all engine code) — forbidden
- `tests/unit/**`, `tests/integration/**` (cannot add or edit)

All 20 failing tests live under those exact paths (see §Failure inventory
below). My charter §"During work" says:

> "If a dep change might affect engine behavior: write
> `agent-comms/questions/release-team-<date>-<slug>.md` for PM to route."

This isn't a dep-change question — it's the **broader pattern**: any
release-blocking gap whose fix lies outside the Release-team writable
surface gets routed to PM. The Phase 1 assessment matrix in my handoff
explicitly classified this as the only blocker; the rest of the
assessment landed clean.

## Failure inventory (20 tests, all on Windows × 3 Python versions)

Source: `gh api repos/Nove-Lab/Nove-Test/actions/jobs/80040568794/logs`
on run `27121828271` (push of commit `bd4d300`, the task-brief commit).
The same 20 failures reproduce identically on all 3 Windows cells
(`80040568794` py3.12 / `80040568831` py3.13 / `80040568845` py3.11).

### Category A — `Path.relative_to` cross-drive ValueError (3 tests, Coverage team)

```
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_fixture_coverlet_basic_yields_one_file_fully_covered
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlMultiClass::test_fixture_partial_coverage_yields_two_files
FAILED tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found
```

Failure mode: `ValueError: path is on mount 'D:', start on mount 'C:'`.
Windows `Path.relative_to` (the production code presumably uses it) raises
when the source path and workspace root sit on different drive letters.
On the runner, `runner.temp` lives on `C:\...` (`AppData\Local\Temp`)
but `GITHUB_WORKSPACE` is `D:\a\Nove-Test\Nove-Test\` (Actions hosts the
checkout on the D: drive). This is a real cross-platform bug that would
hit any real Windows user with a multi-drive setup.

**Fix shape (Coverage team — `src/novetest/coverage/cobertura_parser.py`,
`src/novetest/coverage/derive_xunit.py` + parser modules)**:
catch `ValueError` and fall back to `os.path.relpath`, matching the same
"scenario A" pattern already used in `lcov_parser.py` and `istanbul_parser.py`
per `decisions/2026-05-15-coverage-facts-json-layout.md` §"Amendment
2026-06-08" (the constraint #6 binding rule). Surfaces in tests by
asserting `.startswith('..')` or `not Path(...).is_absolute()` and using
`Path(...).as_posix()` for separator-agnostic comparisons.

### Category B — LCOV Windows path-separator assertion (1 test, Coverage team)

```
FAILED tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning
```

The test asserts `'/ws/cargo-project' in warning_text` but the actual
warning text on Windows is `'\\ws\\cargo-project'`. The production
code's relpath fallback IS firing (the `..` form is present), but the
test pinned a POSIX separator literal that doesn't survive on Windows.

**Fix shape (Coverage team — `tests/unit/coverage/test_lcov_parser.py`)**:
either assert against `Path(...).as_posix()`-normalized warning text, or
have the production warning emitter normalize separators before writing
the warning string (more user-friendly — the warning text is consumed
by humans + AI agents reading the JSON envelope, both of which expect
POSIX-style paths per the v1 envelope convention).

### Category C — Localization B2-2 path-normalization Windows breakage (4 tests, Localization team)

```
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_workspace_internal_path_normalized_to_relative
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_path_outside_workspace_kept_absolute
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_and_relative_for_same_file_collapse_to_relative
FAILED tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top
```

These are the brand-new B2-2 path-normalization tests that landed
TODAY (2026-06-08 in commit `51ea1b6` per the localization slice's
WORKLOG entry). The `_normalize_to_workspace_relative` helper in
`src/novetest/localization/failure_proximity.py` uses `Path.relative_to`
which loses the drive prefix on Windows and produces a path like
`'Users\\runneradmin\\...\\src\\foo.py'` (no `C:`) instead of the
expected `'src/foo.py'`.

Notable: the WORKLOG entry's §"Gotcha #2" pinned the decision to NOT
call `.resolve()` for cross-platform reasons. That decision interacts
badly with Windows path semantics — the brief lacks Windows coverage
because the local dev host on which the slice was authored is Linux.

**Fix shape (Localization team — `src/novetest/localization/failure_proximity.py`
+ corresponding tests)**: switch the helper from `Path.relative_to` to
`os.path.relpath(file_path, workspace_root)` (the same scenario-A pattern
the Coverage parsers use); normalize the result with `.replace(os.sep, '/')`
or `Path(...).as_posix()` before emission so the envelope carries
stable POSIX-style relative paths cross-OS. The
`test_absolute_and_relative_for_same_file_collapse_to_relative`
test's "1.0 vs 2.0 evidence aggregation" assertion will pass once
the absolute side normalizes correctly and both sides collide at the
same dict key.

### Category D — JUnit subprocess UnicodeDecodeError (1 test, Run team)

```
FAILED tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 226: invalid start byte
```

Same "jest-charmap" class pattern Release team already hardened against
in `tests/release/test_install_script.py::_run_install_script` on 5/21
(commit `12cf04d`): the test calls `subprocess.run(..., text=True)` and
on Windows that decodes pipes with the host's cp1252 locale codec
instead of UTF-8. Byte `0x97` (U+0097, END OF GUARDED AREA) is not a
valid UTF-8 start byte; it IS valid cp1252 (Latin small letter u with
acute, near `ó`). The subprocess output evidently contains a
Windows-1252-encoded character that the test pipes through.

**Fix shape (Run team — `tests/unit/run/adapters/test_junit_adapter.py`)**:
add `encoding="utf-8"` to the failing `subprocess.run` invocation (same
edit shape as Release team's 5/21 install-script test hardening).
Consider sweeping the other adapter tests too — this is a class bug
that may hide in `tests/unit/run/adapters/test_*_adapter.py` more broadly.

### Category E — JUnit Windows OS gate not handled by tests (11 tests, Run team)

```
FAILED tests/unit/run/test_junit_readiness.py::test_ready_when_java_and_mvn_present
FAILED tests/unit/run/test_junit_readiness.py::test_missing_jdk
FAILED tests/unit/run/test_junit_readiness.py::test_missing_mvn
FAILED tests/unit/run/test_junit_readiness.py::test_missing_jupiter
FAILED tests/unit/run/test_junit_readiness.py::test_junit4_specific_diagnostic
FAILED tests/unit/run/test_junit_readiness.py::test_testng_specific_diagnostic
FAILED tests/unit/run/test_junit_readiness.py::test_gradle_wrapper_path
FAILED tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
FAILED tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope
FAILED tests/integration/run/test_junit_warnings.py::test_cli_smoke_missing_jacoco_emits_envelope_warning
FAILED tests/integration/run/test_junit_warnings.py::test_cli_smoke_ambiguous_build_tool_emits_envelope_warning
FAILED tests/integration/run/test_junit_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter
```

These tests expect JUnit readiness `state == "ready"` (or other "engine
detected" cases) but on Windows the adapter unconditionally returns
`state == "engine-misconfigured"` with the issue:

> "JUnit adapter requires a non-Windows host until the Windows binary
> pipeline ships (Open Question #16)"

This is the **deliberate** Windows OS gate from
`decisions/2026-06-03-junit-console-launcher-vendor.md` §"Risks (carried
into the JUnit adapter cycle cycle brief)" §Windows:

> "The JUnit adapter MUST gate on OS support and emit
> `engine-misconfigured` of kind `os-unsupported` with the message ...
> until that gap closes."

The adapter IS doing the right thing; the tests don't know it. They were
written on a Linux host and never reckoned with the OS gate.

**Fix shape (Run team — `tests/unit/run/test_junit_readiness.py`,
`tests/unit/run/adapters/test_junit_adapter.py`,
`tests/integration/run/test_junit_*.py`)**: add module-level
`pytestmark = pytest.mark.skipif(sys.platform.startswith("win"),
reason="JUnit adapter gates Windows per decision
2026-06-03-junit-console-launcher-vendor.md §R5")` to each affected
file. Alternative: add a single `os-gate-aware` branch in the test
that asserts the engine-misconfigured response shape on Windows
(less code-duplication; surfaces a real regression check that the
gate is still firing).

## Suggested follow-up cycle shape

The three fix surfaces are mutually disjoint (different teams' source
territories + test files). A parallel triple cycle matching the B2
UX-normalization shape from 6/8 fits cleanly. Wall-time estimate per
cycle:

| Cycle | Team | Surface | Effort | Files touched |
|---|---|---|---|---|
| Coverage Windows fix | Coverage | `cobertura_parser.py`, `derive_xunit.py`, `lcov_parser.py` (+ tests) | ~1-2 h | 3 src + 3 unit tests |
| Localization Windows path fix | Localization | `failure_proximity.py` (+ tests) | ~1 h | 1 src + 1 unit + 1 integration |
| Run JUnit Windows test gate | Run | `test_junit_readiness.py`, `test_junit_adapter.py`, `test_junit_*.py` integration | ~1-2 h | 0 src + ~4 test files (test-only) |

Suggested parallel-triple-cycle layout if PM agrees the surfaces are
disjoint. Sequential is also fine; the order doesn't matter because
the failures are independent.

Of note: the Run JUnit cycle is **test-only** (the production adapter
is doing the right thing — the OS gate fires correctly per the
decision). The Coverage + Localization cycles are mixed (src + tests).
This may affect §2.5 equip-and-exercise gate triggering:

- Coverage cycle: touches `src/novetest/coverage/**` + tests — coverage
  adapter integration tests need a verified-equipped host? PM
  judgment.
- Localization cycle: touches `src/novetest/localization/**` + tests —
  same question.
- Run JUnit cycle: tests-only on existing JUnit adapter behavior — §2.5
  gate explicitly fires for Run-team source changes but this cycle is
  test-only. PM ruling per the 2026-06-04 decision needed.

PM's brand-new `2026-06-08-equip-and-exercise-default-verification-posture`
decision (pending-CEO-approval, untracked in this worktree per the local
fs check) likely interacts with the §2.5 question here. Worth folding
into PM's cycle-shaping when scoping these fixes.

## Phase 0 DoD #1 posture question

`design/implementation-plan/delivery-phasing.md` Phase 0 DoD bullet #1
is checked `[x]`:

> "[x] `uv run pytest -q` green on all three OSes and three Python versions."

This was checked on 2026-05-16 against the 5/16 head commit. Empirically
**stale at today's head**: Windows has been red on every push since
2026-06-01 (8 days, 30+ consecutive red runs). First red CI commit was
`53f7920` (cargo LCOV dispatch) or `4cb5d48` (typed metadata slot on
NativeResult), per the bisect-by-gh-run-list narrative in my handoff.

PM owns the DoD checklist. Three options I see:

1. **Un-tick the bullet** until the 3 follow-up cycles land. Cleanest
   audit-trail; signals correctly that MVP is not release-ready.
2. **Leave ticked but add a stale-marker** like
   `[x] *(re-opened 2026-06-08; see release-team handoff for blocking
   gap and follow-up cycles)*`. Preserves the 2026-05-16 closure history
   while flagging the regression.
3. **Re-scope DoD #1** to Linux+macOS only (matching foundations §7's
   Phase 0 binary scope), document Windows as Phase-N follow-up. Most
   permissive; requires foundations §7 amendment + a new Phase 0 risk
   acknowledgment.

I recommend option 1 (un-tick) or option 2 (stale-marker); option 3
weakens the contract too much for what's almost certainly an artifact
of "tests written on Linux that never ran on Windows during dev."
PM call.

## What this question does NOT ask

- Specific test-skip patterns (Run team owns that)
- Whether `_normalize_to_workspace_relative` should use `os.path.relpath`
  or `Path.relative_to`+try/except (Localization team owns that)
- Whether Coverage parsers should normalize to `.as_posix()` at parse
  time or at envelope time (Coverage team owns that)

Just routing: who picks up the work, in what shape, and on what
timeline relative to MVP.

## Asks of PM

1. **Routing decision**: which team(s) take the 3 fix cycles; sequential
   vs parallel; cycle shapes.
2. **DoD bookkeeping**: how to mark Phase 0 DoD #1 (un-tick / stale /
   re-scope).
3. **Acknowledge**: the MVP release-readiness sign-off in my handoff
   reads "NOT release-ready as of `<commit>`; blocker: CI matrix red
   on Windows." This is the empirical state — PM owns whether to brief
   CEO with that framing.

Tagged `status: open` until PM responds with routing.
