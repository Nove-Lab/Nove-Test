---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-09
slug: localization-windows-path-normalization-fix
related:
  - agent-comms/handoffs/localization-team-2026-06-09-windows-path-normalization-fix.md
  - agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
---

# Verification — Localization Windows path normalization fix (2/3 of Windows-CI-fix triple)

## Merged commit

- **HEAD on main after this slice**: `c5c85de comms: handoff for Localization Windows path normalization fix (2/3 of Windows CI fix triple)` (2 commits: `edb78f8 feat(localization): Windows path normalization fix (regex drive-prefix capture + as_posix separator)` + handoff)
- **Final tip after all 3 slices**: `a6ebd91` (Coverage + this slice + Run merged in alphabetic order)
- **Source handoff**: `agent-comms/handoffs/localization-team-2026-06-09-windows-path-normalization-fix.md`
- **Worktree base**: `230420c` → rebased onto `4110645` (Coverage just landed) → FF-merged as 2/3 in the alphabetic chain.

## What landed

- **1 src module modified**: `src/novetest/localization/failure_proximity.py` (+108 net LOC). Three changes:
  1. **Regex amendment** at line 104: `_FILE_PATH_CHARS = r"(?:[A-Za-z]:[\\/])?[A-Za-z_./\\][\w\-./\\]*"` — optional Windows drive-prefix group + `\\` added to first-char class. Inert on POSIX (the optional group matches empty); load-bearing on Windows.
  2. **New helper** `_is_outside_workspace(file_path, workspace_root) -> bool` at line 516. Carries cross-drive `ValueError` safety net as the explicit "inside vs outside" classifier.
  3. **`_normalize_to_workspace_relative` restructured** at line 549: `is_absolute()` → `_is_outside_workspace()` → `relative_to()` (with defensive `os.path.relpath` fallback) → `.as_posix()`. Inside-workspace emits POSIX; outside-workspace returns verbatim (operator affordance for "not your code" cue); relative input passes through with `as_posix()` normalization.
- **1 test module extended**: `tests/unit/localization/test_derive_failure_proximity.py` (+250 LOC, 8 new tests under §"Windows path normalization fix (2026-06-09)" header).
- **WORKLOG**: top entry preserved through rebase chain.
- **Net delta**: 1 src + 1 test file, +368 / -21 lines.

## Post-merge test gate (full chain at `a6ebd91`)

```
uv run mypy --strict src/novetest      → Success: no issues found in 93 source files
uv run pytest -q tests/unit tests/integration → 1229 passed + 23 skipped + 1 failed in 32.43s
```

The 1 failed test = `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` (`dotnet not on PATH`) — pre-existing host-equipment dependency, not a regression. Documented identically in all 3 handoffs of the triple.

## Verification scenarios for Manual Test

### Scenario A — 4 originally-failing Windows tests are now green on Linux

```bash
uv run pytest -v \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_workspace_internal_path_normalized_to_relative \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_path_outside_workspace_kept_absolute \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_and_relative_for_same_file_collapse_to_relative \
  tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top
```

Expected: **4 passed**. These were the 4 RED-on-Windows tests targeted by the slice; the production fix lives entirely in `src/` so the test assertions remain stable.

### Scenario B — 8 new Windows-pinning tests

```bash
uv run pytest -v tests/unit/localization/test_derive_failure_proximity.py -k "windows or normalize or outside_workspace"
```

Expected output (selected tests):
- `test_parse_failure_log_captures_windows_drive_prefix_backslash` — regex captures `C:\Users\runner\ws\src\foo.py:5` as the file token
- `test_parse_failure_log_captures_windows_drive_prefix_forward_slash` — same for `C:/Users/runner/ws/src/foo.py:5`
- `test_parse_failure_log_posix_paths_unchanged_post_windows_fix` — Linux paths round-trip unchanged
- `test_is_outside_workspace_classifies_disjoint_paths_as_outside` — `D:\elsewhere` vs `C:\workspace` → outside
- `test_normalize_relative_input_passes_through_as_posix` — already-relative path gets `as_posix()` applied
- `test_normalize_outside_workspace_input_preserved_verbatim` — outside path returned as-is (operator-friendly OS-native form)
- `test_normalize_inside_workspace_input_emits_posix_separators` — `C:\ws\src\foo.py` → `src/foo.py`
- `test_normalize_relpath_fallback_engages_when_relative_to_raises` — defense-in-depth fallback fires when `Path.relative_to` is monkey-patched to raise

All 8 should pass.

### Scenario C — Localization full sweep

```bash
uv run pytest -q tests/unit/localization tests/integration/localization
```

Expected: **171 passed + 2 skipped** (was 163 in B2-2 close; +8 reflects the new tests).

### Scenario D — Asymmetric inside/outside normalization spot-check

```bash
uv run python -c "
from pathlib import Path
from novetest.localization.failure_proximity import (
    _is_outside_workspace, _normalize_to_workspace_relative,
)
ws = Path('/workspace')  # POSIX equivalent of C:/workspace
# Inside: POSIX-emitted
print('inside:', _normalize_to_workspace_relative(Path('/workspace/src/foo.py'), ws))
# Outside: verbatim
print('outside:', _normalize_to_workspace_relative(Path('/elsewhere/file.py'), ws))
# Already-relative: as_posix idempotent
print('relative:', _normalize_to_workspace_relative(Path('src/bar.py'), ws))
"
```

Expected:
```
inside: src/foo.py
outside: /elsewhere/file.py
relative: src/bar.py
```

The asymmetry (inside → POSIX-normalized, outside → verbatim) is the deliberate "not your code" operator-affordance cue — pinned by `test_normalize_outside_workspace_input_preserved_verbatim`.

### Scenario E — Failure-proximity wire-level envelope spot-check (optional, requires fixture)

```bash
# If a no-coverage fixture run record exists in .novetest/run/:
LATEST=$(ls -1t .novetest/run/runs/ 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
  uv run novetest localization $LATEST 2>&1 | python3 -c "
import sys, json
env = json.loads(sys.stdin.read())
finding = env.get('data', {}).get('localization_finding', {})
entries = finding.get('entries', [])
print(f'mode={finding.get(\"mode\")} entries={len(entries)}')
for e in entries[:3]:
    f = e.get('code_location', {}).get('file', '')
    print(f'  file={f!r} abs?={f.startswith(\"/\") or (len(f) >= 2 and f[1] == \":\")}')
"
fi
```

Expected: file paths workspace-relative (no `/abs/path/leak` and no `C:\...` leak) for entries from within the workspace; outside-workspace entries (stdlib frames, cargo `/rustc/...` frames) absolute. Skip if no fixture exists.

### Scenario F — Windows CI matrix verdict (binding criterion)

```bash
gh run list --workflow ci.yml --branch main --limit 1
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

Expected: 3 Windows jobs (py3.11 / py3.12 / py3.13) all `conclusion: success`. The 4 originally-failing tests in §Scenario A should turn GREEN on the Windows × 3 Py = 3 cells.

## Critical edge cases worth probing

1. **Two defects, one symptom** (handoff Gotcha #1). The brief diagnosed only `Path.relative_to` drive-loss; empirical Linux-side regex simulation showed `_FILE_PATH_CHARS` was the SILENT culprit (capture started AFTER the `:` because the class lacked `:`). Both fixes had to land together. Manual Test should NOT propose "rollback the regex change but keep the helper change" — they're a load-bearing pair.

2. **Outside-workspace verbatim preservation is DELIBERATE asymmetry** (handoff §"Outside-workspace preserves OS-native form" + Gotcha #2). Inside-workspace paths get `as_posix()` normalized; outside-workspace paths return verbatim (Windows operator sees `C:\Users\runneradmin\AppData\...`; not `C:/Users/...`). The asymmetry is the "not your code" semantic cue from Defect-3 (2026-05-31). If a future cleanup PR proposes "let's normalize everything for consistency," it would break the diagnostic affordance.

3. **`os.path.relpath` defense-in-depth fallback is currently un-reachable** under stable `pathlib` semantics — `_is_outside_workspace` and `Path.relative_to` use identical machinery. The fallback is pure future-drift insurance (hypothetical Python 3.14 changing `relative_to` behavior). Pinned by `test_normalize_relpath_fallback_engages_when_relative_to_raises` which uses `monkeypatch.setattr(Path, "relative_to", fake_raise)`. Without that test the fallback would be dead code and a future cleanup PR could drop it.

4. **B2-2 design intent preserved** (handoff DoD #5). The 2026-06-08 B2-2 slice's "outside-workspace deliberately absolute" + "mode-invariant metadata" decisions remain intact. This slice fixes the implementation bug, not the design contract. Spot-check via running the prior B2-2 verification scenarios — those should still pass.

5. **No `Path.resolve()` introduced** (handoff §"No Path.resolve() introduced"). The B2-2 cycle's "deferred future cycle for symlinks" was a DIFFERENT defect class than this Windows fix surface (regex + separator + cross-drive). The fix shape is `os.path.relpath` + `as_posix`, NOT `resolve`. `Path.resolve()` remains a future-cycle option if Manual Test surfaces a real-host symlink scenario.

6. **The `dotnet not on PATH` pre-existing failure** is documented identically in this slice's handoff (§"Pre-existing failure analysis"), the parallel Coverage + Run handoffs, and every recent cycle's WORKLOG. NOT a regression.

## Rebase / merge notes for the audit trail

- **Worktree branch**: `localization-team/windows-path-normalization-fix`, based on `230420c`.
- **Rebase**: required — main moved by `4110645` (Coverage merged 1/3 first per alphabetic order).
- **Conflict count**: 1 (WORKLOG.md only — both slices added 2026-06-09 top entries).
- **Resolution**: localization on top (newer-in-history), `---` divider, coverage below — per project "newest entry on top + same-day-divider" convention. Source files: zero conflict (file footprints fully disjoint).
- **FF-merge**: `4110645..c5c85de` clean after rebase.
- **Test gate**: deferred to end-of-chain — see §"Post-merge test gate" above. `c5c85de` standalone gate would have been redundant since localization src changes don't interact with coverage src changes.
- **Worktree cleanup**: deferred to after this verification doc lands.
