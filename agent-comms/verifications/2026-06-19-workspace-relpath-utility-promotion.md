---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready-for-verification
created: 2026-06-19
slug: workspace-relpath-utility-promotion
merged_commit: 9c5abbf
merged_tip: d5b4242
source_handoffs:
  - agent-comms/handoffs/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md
related:
  - agent-comms/tasks/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
host: equipped (per `decisions/2026-06-08-equip-and-exercise §1` SHOULD tier; equipped Linux host for the §4 CI-matrix-verdict-deferred cross-OS verification)
---

# Verification — workspace-relpath utility promotion (Coverage + Localization cross-over)

## TL;DR

**Merged commit**: `9c5abbf` (single bundled commit — Coverage refactor + WORKLOG + handoff + 9-file diff). **Merged tip**: `d5b4242` (post-Wave-1 cohort: this slice + Release `f4523da` + Run `d5b4242`).

9-file refactor lifts the workspace-relpath helpers from Coverage-private (`src/novetest/coverage/_paths.py`) to a project-wide utility surface (`src/novetest/utils/path_utils.py`). Localization's `_normalize_to_workspace_relative` inside-workspace branch now delegates to the shared utility. Byte-equivalent refactor — envelope diff 1406 bytes identical modulo volatile `run_id` + `created_at` + `derived_at` timestamps per Coverage's pre-merge probe.

Your job (Manual Test): verify the **utility surface is structurally sound** at the merged tip + **byte-equivalence is preserved** in the end-to-end Localization envelope + **CI matrix verdict ⊃ cross-OS path-handling** lands green on the post-push ci.yml run.

## Source handoff consumed

- `agent-comms/handoffs/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md` (committed in `9c5abbf` alongside the code refactor)

## Pre-merge empirical anchors (re-verified at merged tip `d5b4242`)

### Anchor A — Public import surface

```bash
$ .venv/bin/python -c "from novetest.utils.path_utils import workspace_relpath, to_workspace_relative_posix, relpath_or_drive_stripped; print('OK 3 exports importable from novetest.utils.path_utils')"
OK 3 exports importable from novetest.utils.path_utils

$ .venv/bin/python -c "from novetest.utils import workspace_relpath, to_workspace_relative_posix, relpath_or_drive_stripped; print('OK 3 exports re-exported from novetest.utils')"
OK 3 exports re-exported from novetest.utils
```

Both import paths green. `utils/__init__.py` re-exports the 3 names (was empty pre-slice; now +19 lines per handoff).

### Anchor B — DoD #2 strict grep (zero internal `_paths` imports remain)

```bash
$ grep -rn "from novetest.coverage._paths\|from novetest.coverage import _paths" src/ tests/
(exit=1, no matches)
```

Zero hits — DELETE-not-shim disposition (Coverage handoff §"`coverage/_paths.py` disposition (DoD #7)") empirically holds at merged tip.

### Anchor C — `coverage/_paths.py` actually deleted

```bash
$ ls src/novetest/coverage/_paths.py
ls: cannot access 'src/novetest/coverage/_paths.py': No such file or directory
```

File is gone (renamed-move to `utils/path_utils.py` per Coverage's `R` rename detection in `git diff --stat`).

### Anchor D — Pre-merge gate (combined Wave 1 cohort)

```bash
$ source ~/.local/share/novetest-toolchains.sh
[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5

$ uv run mypy
Success: no issues found in 109 source files

$ uv run pytest -q tests/unit tests/integration
1303 passed, 5 skipped in 147.60s (0:02:27)
37 snapshots passed.
```

1303 passed = Coverage pre-slice baseline 1294 + Coverage's 3 new `workspace_relpath` wrapper tests + Run slice's net +5-6 from rename/migration. 5 skipped = jest/Node + Go SDK fixture skips on equipped Linux (orthogonal to this slice). **Zero failures** — the chronic-dotnet failure documented in Coverage's pre-merge non-equipped pytest is suppressed on the equipped host (§2.5 evidence).

## Verification scenarios (5 surface + 3 structural)

### Scenario A — Import surface from both paths

```bash
cd /home/yjshin/dev/Nove-Test
.venv/bin/python -c "from novetest.utils.path_utils import workspace_relpath, to_workspace_relative_posix, relpath_or_drive_stripped"
.venv/bin/python -c "from novetest.utils import workspace_relpath, to_workspace_relative_posix, relpath_or_drive_stripped"
```

Expected: both lines exit 0 with no output. **PASS** if both green; **FAIL** if either ImportError (would signal `__init__.py` re-export breakage).

### Scenario B — DoD #2 grep zero re-confirmation

```bash
grep -rn "from novetest.coverage._paths\|from novetest.coverage import _paths" src/ tests/
```

Expected: zero hits (exit 1). **PASS** if zero; **FAIL** if any hit (would signal lingering internal import the rewrite missed).

### Scenario C — DoD #3 inline-implementation removal

```bash
grep -rn "os.path.relpath\|relative_to(workspace_root)" src/novetest/localization/
```

Expected: 4 hits, ALL benign:
- Line 543 of `failure_proximity.py`: inside `_is_outside_workspace` — `file_path.relative_to(workspace_root)` is the policy classifier (try/except returns `bool`, NOT a relpath fallback). Brief out-of-scope §4 preserves this.
- Lines 579, 583, 630: docstring/comment text only.

ZERO function-body try/except/relpath fallback blocks remain. **PASS** if matches 4 (1 classifier + 3 docstring) with no relpath fallback; **FAIL** if any line introduces a new inline `os.path.relpath` chain.

### Scenario D — Envelope byte-identity (Localization E2E)

Replicate Coverage's DoD #6 probe at merged tip:

```bash
cd /home/yjshin/dev/Nove-Test
# Pre-slice run: check out 42f6a32, run failure_proximity E2E, dump envelope
# Post-slice run: HEAD = d5b4242, same E2E, dump envelope
# Diff should show 3 volatile-field hunks only
```

Coverage's pre-merge probe captured 1406 bytes identical pre + post with diff hunks limited to `run_id` (ULID, varies), `created_at` (RunReference timestamp, varies), `derived_at` (LocalizationFinding timestamp, varies). Re-validate by running the `failure_proximity_e2e` test and confirming the persisted envelope size + structural diff stays in those 3 volatile fields.

Optional alternative: trust the pre-merge probe + the byte-equivalent unit tests (`test_path_utils.py` 10 cases including 7 relocated byte-equivalent from `test_paths.py` + 3 new `workspace_relpath` wrapper tests).

**PASS** if envelope `entries[*].code_location.file` is byte-identical pre vs post; **FAIL** if any file path string differs (would signal the policy preservation slipped).

### Scenario E — Test relocation completeness

```bash
ls tests/unit/coverage/test_paths.py 2>&1     # expected: No such file
ls tests/unit/utils/test_path_utils.py 2>&1   # expected: file exists
.venv/bin/python -m pytest -q tests/unit/utils/test_path_utils.py 2>&1 | tail -5
```

Expected:
- Old test file deleted.
- New test file exists.
- pytest shows 10 tests passed (7 relocated + 3 new `workspace_relpath` wrapper).

**PASS** if all 10 green; **FAIL** if any missing or fewer than 7 relocated cases retained.

### Scenario F — `_is_outside_workspace` policy preserved

```bash
grep -n "_is_outside_workspace" src/novetest/localization/failure_proximity.py
.venv/bin/python -c "
from pathlib import Path
from novetest.localization.failure_proximity import _is_outside_workspace
ws = Path('/tmp/workspace')
print('inside-workspace:', _is_outside_workspace(Path('/tmp/workspace/src/foo.py'), ws))
print('outside-workspace:', _is_outside_workspace(Path('/usr/lib/python3.11/os.py'), ws))
"
```

Expected:
- `_is_outside_workspace` is defined (Coverage preserved per brief out-of-scope §4).
- inside-workspace returns `False`; outside-workspace returns `True` (B2-2 policy preserved).

**PASS** if classifier returns the right Boolean on both sides; **FAIL** if either side flips (would signal Coverage's "policy preserved" claim slipped under refactor).

### Scenario G — Merge diff scope re-confirmation

```bash
git log --oneline 42f6a32..9c5abbf       # Coverage's slice commits
git diff --stat 42f6a32..9c5abbf
git diff --name-only 42f6a32..9c5abbf
```

Expected:
- 1 commit: `9c5abbf refactor(utils): promote coverage/_paths.py to utils/path_utils.py + migrate Localization`
- 9 files changed, +385/−49 (`R067` rename `_paths.py → path_utils.py` + `R063` rename `test_paths.py → test_path_utils.py` + 3 import-line rewrites + 1 utils/__init__.py expand + 1 failure_proximity delegate edit + WORKLOG + handoff)
- Files: under `src/novetest/utils/`, `src/novetest/coverage/`, `src/novetest/localization/`, `tests/unit/utils/`, `WORKLOG.md`, `agent-comms/handoffs/`

**PASS** if all in expected scope; **FAIL** if any unexpected file appears.

### Scenario H — CI matrix verdict (POST-PUSH, §4 amendment 2026-06-19 binding)

This slice qualifies under `decisions/2026-06-08-equip-and-exercise §4` amendment 2026-06-19 #1: touches `pathlib.Path` ops + `os.path` calls + workspace-relative path conversion. The §4 binding is **MUST** cite a 9/9 `ci.yml` matrix-run URL on the merged tip.

```bash
# After the push lands, find the ci.yml run auto-triggered on the merged HEAD
gh run list --workflow ci.yml --branch main --limit 5
# Pick the run for SHA d5b4242 (the merged tip with this verification commit on top)
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected: 9 matrix cells (3 OSes × 3 Pythons) all `success`. The Windows cross-drive `_raising_relpath` fixture-mocked test must remain green at the migrated `utils/path_utils.py` surface.

**PASS** if 9/9 green at merged tip; **FAIL** if any Windows cell RED (would signal the rename broke cross-drive fallback wiring).

## Critical edge probes

1. **The first Coverage worktree commit was `reset --hard HEAD` then re-committed**: Coverage's reflog shows `HEAD@{1}: <empty msg>` → `HEAD@{0}: reset: moving to HEAD` BEFORE the final `9c5abbf` commit landed. Coverage team committed once, reset back, re-committed cleanly. The handoff was untracked at the time Main Branch first inspected the worktree (CEO confirmed Coverage just committed during the merge cycle). Flag if the final committed surface differs from the handoff's claimed 9-file footprint — empirically it does not (diff stat matches the handoff table byte-for-byte).

2. **107 line `__init__.py` re-export count**: handoff claims `+19` LOC for `utils/__init__.py`. Empirically: file went 0 → 19 lines (3 import lines + `__all__` list + module docstring + blank lines). Re-exports `workspace_relpath`, `to_workspace_relative_posix`, `relpath_or_drive_stripped`. Flag if the public name set changes (e.g., a 4th name was promoted) — currently exactly 3.

3. **mypy file count baseline drift**: mypy reports 109 source files post-merge (matches Coverage's pre-merge claim). The +1 new `path_utils.py` − 1 deleted `_paths.py` = net 0 module count, BUT mypy's tracking includes `__init__.py` which was previously empty and now is non-empty. If mypy reports 110 (a +1 drift from the `__init__.py` going from empty-but-tracked to non-empty), it's not a regression — purely a counting nuance. Empirically 109 holds.

4. **Localization `_is_outside_workspace` policy is the ONLY remaining `relative_to(workspace_root)` call**: post-slice, this single classifier is the sole use of the `relative_to` pattern in localization/. If a future cycle promotes the classifier itself to `path_utils.py`, this verification scenario's expected hit count drops to 0. For now (and Coverage Q2 of handoff), the classifier stays Localization-internal.

5. **PEP 639 wheel-license auto-discovery surfaces `path_utils.py` indirectly**: `path_utils.py` has no license header of its own (it's source code, not third-party); the project's NOTICES.md surface (Release slice this cycle) is the canonical attribution. No interaction expected — flag if `uv build --wheel` produces a wheel without `path_utils.py` in `src/novetest/utils/` (would signal `[tool.hatch.build.targets.wheel]` package discovery broke).

6. **§4 CI matrix verdict deferred to post-push**: This verification doc is committed BEFORE the push. The ci.yml run referenced in Scenario H comes into existence only after the push triggers it. Manual Test consumes this verification doc AFTER both the merge push and the ci.yml run completion. The §4 binding therefore lives in PM's cycle-close step, not in this verification request — but the test surface is identical (9/9 matrix). PM (not Manual Test) typically harvests the run ID into the cycle-close history; Manual Test can either wait for PM's harvest or cite the run themselves at verify time.

## Anything that wasn't obvious during merge

1. **Coverage's worktree was uncommitted at first inspection**: The handoff was already drafted with `status: ready` but the team had not yet committed the worktree (reflog showed `HEAD@{1}: <empty msg>` → `HEAD@{0}: reset: moving to HEAD` — one commit was made and then reset away). Main Branch escalated to CEO; CEO reported Coverage committed during the conversation. The final commit `9c5abbf` lands cleanly per the handoff's "Suggested commit message" template; no Main-Branch-authored content on the code/test surface.

2. **WORKLOG conflict at Run rebase (NOT this slice)**: Coverage's WORKLOG entry landed first (FF-merge clean). Run's rebase onto Coverage's new main produced a WORKLOG conflict at the top-of-file new-entry region. Resolved with `incoming-on-top` convention (Run on top, `---` separator, Coverage below). This verification doc lives at merged tip `d5b4242`; the WORKLOG entry for THIS slice (Coverage) is the second entry from the top.

3. **Pre-merge gate ran on equipped host** (`source ~/.local/share/novetest-toolchains.sh` produced dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5 banner). 1303 passed + 5 skipped + 0 failed in 147.60s; mypy 109 files clean. The 5 skips are jest/Node + Go SDK fixture skips (toolchains not equipped) — orthogonal to this slice.

4. **Charter cross-over disposition**: Coverage team's edit to `src/novetest/localization/failure_proximity.py` is the third application of the CEO-approved in-cycle Option-A pattern (PM disposition #3 of 2026-06-09). Byte-equivalent refactor only — Coverage's pre-merge envelope-diff probe (1406 bytes identical modulo volatile timestamps) is the binding empirical justification.
