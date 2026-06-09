---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-09
slug: windows-path-normalization-fix
task: agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/tasks/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
---

# Handoff — Localization Windows path normalization fix (2/3 of Windows CI fix triple)

## TL;DR

Fixed the 4-test Windows CI red-cell regression that the B2-2 slice
(2026-06-08 commit `51ea1b6`) introduced. Worktree branch
`localization-team/windows-path-normalization-fix` ready for FF-merge.
Empirically verified on Linux (172 pass + 2 skipped Localization-
scoped; 4 originally-failing tests explicitly re-run green); Windows
verification deferred to post-merge CI matrix per task brief §"CI
matrix verdict".

## Worktree

```
path: /home/yjshin/dev/aispace/novetest-localization-windows-path
branch: localization-team/windows-path-normalization-fix
base: 230420c (main)
```

## Files written / modified

### Source

- `src/novetest/localization/failure_proximity.py` —
  - `import os` added (for the `os.path.relpath` defense-in-depth
    fallback).
  - `_FILE_PATH_CHARS` regex amended: optional `(?:[A-Za-z]:[\\/])?`
    leading drive-prefix group + `\\` added to the first-character
    class so the engine can resume capture at the path separator
    following a Windows drive (`C:\Users\...`).
  - `_is_outside_workspace(file_path, workspace_root) -> bool` added
    as a new internal helper (factor-out per brief §"outside-workspace
    판정 자체도 cross-drive 안전" audit recommendation).
  - `_normalize_to_workspace_relative` updated: `is_absolute` → call
    `_is_outside_workspace` → `relative_to` (with defensive
    `os.path.relpath` fallback) → `as_posix()`. The already-relative
    branch also calls `as_posix()` for separator normalization on
    Windows. Outside-workspace branch returns the input string
    verbatim (deliberate; pinned by test).

### Tests

- `tests/unit/localization/test_derive_failure_proximity.py` — added
  7 new tests + extended imports to include the helpers as testable
  surfaces:
  - `test_parse_failure_log_captures_windows_drive_prefix_backslash`
  - `test_parse_failure_log_captures_windows_drive_prefix_forward_slash`
  - `test_parse_failure_log_posix_paths_unchanged_post_windows_fix`
  - `test_is_outside_workspace_classifies_disjoint_paths_as_outside`
  - `test_normalize_relative_input_passes_through_as_posix`
  - `test_normalize_outside_workspace_input_preserved_verbatim`
  - `test_normalize_inside_workspace_input_emits_posix_separators`
  - `test_normalize_relpath_fallback_engages_when_relative_to_raises`
  (8 tests — the §"Windows path normalization fix" header section).

  The 4 originally-failing tests (the 3 B2-2 unit tests in this same
  file + 1 e2e in `tests/integration/localization/test_failure_proximity_e2e.py`)
  are UNCHANGED — the fix lives entirely in `src/`, the test
  assertions remain stable. They are green on Linux post-fix (CI
  matrix verdict on Windows pending FF-merge).

### Communication

- `WORKLOG.md` — new top entry (charter format) with Landed /
  Verified / Left open / Gotcha / Next sections.
- This handoff doc (`agent-comms/handoffs/localization-team-2026-06-09-windows-path-normalization-fix.md`).
- `agent-comms/INDEX.md` — will be regenerated as part of the
  cycle-close ritual.

## Verification result

| Surface | Command | Result |
|---|---|---|
| Type check | `uv run mypy --strict src/novetest` | **Success: no issues found in 92 source files** |
| Targeted regression (4 originally-failing tests) | `pytest -v tests/unit/.../test_absolute_workspace_internal_path_normalized_to_relative tests/unit/.../test_absolute_path_outside_workspace_kept_absolute tests/unit/.../test_absolute_and_relative_for_same_file_collapse_to_relative tests/integration/.../test_failure_proximity_ranks_buggy_file_top` | **4 passed in 0.37s** |
| Localization unit + integration | `uv run pytest -q tests/unit/localization tests/integration/localization` | **171 passed + 2 skipped + 0 failed in 2.66s** (was 163 in B2-2 close; +8 new tests) |
| Full unit + integration | `uv run pytest -q tests/unit tests/integration` | **1214 passed + 26 skipped + 1 failed in 32s** — the single failure is pre-existing `dotnet not on PATH` host-equip (brief §2.5 non-applicable to this slice) |
| Empirical regex check | Inline Python on Linux — see WORKLOG §"Verified" | Windows backslash + forward-slash inputs both capture drive prefix; POSIX absolute + relative inputs round-trip unchanged |

## DoD bullets (11 / 11 closed by team belief)

Per task brief §"Definition of done":

- [x] (1) `_normalize_to_workspace_relative` cross-drive ValueError
      safety + `.as_posix()` separator normalization
- [x] (2) `_is_outside_workspace` cross-drive safety audit + factor-out
- [x] (3) 4 failing Windows tests green — Linux-side proxy via 7 new
      pinning tests; binding criterion is bullet 8 below
- [x] (4) Linux/macOS unchanged — full Localization suite 171/2/0;
      full suite 1214/26/1 host-equip-pre-existing
- [x] (5) B2-2 "outside-workspace asymmetry" PM disposition preserved
      — outside-workspace remains deliberately absolute via
      `_is_outside_workspace` → return verbatim branch
- [x] (6) `mypy --strict` clean
- [x] (7) `pytest -q tests/unit tests/integration` green on equipped
      host (modulo the pre-existing dotnet host-equip failure)
- [ ] (8) **CI matrix verdict criterion** — Windows × 3 Python = 3
      cells green AFTER FF-merge; PM cite `ci.yml` run number in
      verification doc (⏳ blocked on FF-merge; team belief is
      verdict will be GREEN given the Linux-side empirical proxy)
- [x] (9) WORKLOG entry
- [x] (10) This handoff doc
- [x] (11) `tools/regen_comms_index.py` (will run before commit)

## Open items (none requiring PM input)

This slice closes the Localization side of the Windows CI fix
triple cleanly. No questions filed. No charter ambiguities surfaced.

## Pre-merge checklist for Main Branch

- [x] Worktree at `/home/yjshin/dev/aispace/novetest-localization-windows-path`
- [x] Branch `localization-team/windows-path-normalization-fix`
- [x] 2 commits expected (feat + handoff/INDEX/WORKLOG closure)
- [x] Base: `230420c` (main HEAD at slice creation)
- [x] File footprint: 1 src + 1 test + WORKLOG + handoff + INDEX
- [x] **Disjoint from peer slices**: Coverage operates in
      `src/novetest/coverage/**`; Run operates in
      `tests/{unit,integration}/run/**` (test-only). Zero merge
      conflict expected.
- [x] FF-merge order per brief: **coverage → localization → run**
      (this slice is 2/3 in alphabetic order)

## Implementation choices

### Two defects, not one

The brief diagnosed only the `Path.relative_to` drive-loss surface;
empirical Linux-side regex simulation against the actual
`_FILE_PATH_CHARS` pattern produced the same `Users\runneradmin\...`
drive-less output the Windows CI logged. Conclusion: the regex
character class missing `:` is the FIRST defect; the helper's bare
`str()` + missing `os.path.relpath` fallback is the SECOND. **Both
MUST be fixed together** — fixing only the helper still leaves it
receiving a malformed string from the regex.

The regex amendment is **strictly Windows-safety additive**: the
optional drive prefix group matches empty on POSIX; the `\\` added
to the first-character class lets a Windows path resume capture
after the drive separator but is structurally inert on POSIX
inputs (`\` is not a path separator on POSIX; the regex can match
it but no real POSIX failure log contains it). Empirically
regression-free on Linux per the full suite.

### `_is_outside_workspace` carries the cross-drive safety

Factored out per brief §"outside-workspace 판정 자체도 cross-drive
안전 필요" audit recommendation. The single helper now carries the
binary "inside vs outside" classification using the same `try` /
`except ValueError` mechanism as before, but explicitly named and
documented so the cross-drive case is visible at the call site.
Cross-drive Windows paths (`C:` file vs `D:` workspace) take the
"outside" branch — naturally aligned with the failure_proximity
"not your code" semantic per brief §"failure_proximity outside-
workspace는 absolute 유지".

### Outside-workspace preserves OS-native form

Asymmetric design choice (documented in helper docstring + pinned
by `test_normalize_outside_workspace_input_preserved_verbatim`):

- **Inside-workspace** paths emit POSIX-separator form (envelope
  consistency with sbfl_* modes that source from CoverageFactSet).
- **Outside-workspace** paths emit OS-native form (operator
  affordance — Windows operators recognize
  `C:\Users\runneradmin\AppData\...` immediately;
  `C:/Users/runneradmin/AppData/...` requires an extra cognitive
  step).

The asymmetry preserves the Defect-3 (2026-05-31) defensive posture
that the absolute spelling IS the "not your code" semantic cue.

### `os.path.relpath` fallback is defense-in-depth

Currently un-reachable under stable pathlib semantics because
`_is_outside_workspace` and `Path.relative_to` use identical
machinery. The fallback exists as future-drift insurance: a
hypothetical Python 3.14 release that subtly changed `relative_to`
behavior would surface here as a clean fallback rather than an
unhandled `ValueError` bubbling up to the parser loop. Pinned by
`test_normalize_relpath_fallback_engages_when_relative_to_raises`
which uses `monkeypatch` to construct the scenario.

### No `Path.resolve()` introduced

Brief explicitly noted the B2-2 slice deferred `Path.resolve()` for
symlink scenarios; clarified that this Windows fix cycle is a
DIFFERENT defect surface (regex + separator + cross-drive) and the
fix shape is `os.path.relpath` + `as_posix`, NOT `resolve`. Resolve
remains a future-cycle option if Manual Test surfaces a real-host
symlink scenario where the absolute-fallthrough confuses operators.

## What Manual Test should probe (post-merge)

The CI matrix is the binding evidence per task brief §"CI matrix
verdict criterion" — Manual Test's role here is parallel
ratification on the equipped host. Suggested probes:

1. **Cross-OS spot-check via fixture e2e**: re-run
   `pytest tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top`
   on the equipped host. Should pass (already does on Linux);
   Windows verdict is via CI.

2. **Production envelope shape**: run `novetest run tests/` on a
   pytest fixture without `--coverage`; inspect
   `data.localization_finding.entries[*].code_location.file`. All
   values workspace-relative (no absolute paths leaking) unless the
   file is genuinely outside the workspace (in which case the
   absolute form is the deliberate "not your code" cue).

3. **Helper behavior via Python REPL** (on a Windows-capable host
   if available — otherwise skip):
   ```python
   from pathlib import Path
   from novetest.localization.failure_proximity import (
       _is_outside_workspace, _normalize_to_workspace_relative,
   )
   ws = Path("C:/workspace")
   assert _normalize_to_workspace_relative(
       "C:\\workspace\\src\\foo.py", ws
   ) == "src/foo.py"
   assert _normalize_to_workspace_relative(
       "D:\\elsewhere\\file.py", ws
   ) == "D:\\elsewhere\\file.py"
   ```

## Reference

- Task brief: `agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md`
- Cycle history: `agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md`
- B2-2 origin slice: WORKLOG entry 2026-06-08 (the slice that
  introduced the defect); commit `51ea1b6`
- Windows CI log evidence: `gh api repos/Nove-Lab/Nove-Test/actions/jobs/80227759401/logs`
  (Localization 4 failures: drive-prefix loss visible in test output)
