---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-09
slug: coverage-windows-parser-fixes
related:
  - agent-comms/handoffs/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/tasks/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
---

# Verification — Coverage Windows parser fixes (1/3 of Windows-CI-fix triple)

## Merged commit

- **HEAD on main after this slice**: `4110645 fix(coverage): handle Windows cross-drive ValueError in workspace-relative path resolution (Windows-CI-fix 1/3)`
- **Final tip after all 3 slices**: `a6ebd91` (this slice + Localization + Run merged in alphabetic order)
- **Source handoff**: `agent-comms/handoffs/coverage-team-2026-06-09-windows-parser-fixes.md`
- **Worktree base**: `230420c` → FF-merged into main as the FIRST of the 3-slice alphabetic chain (coverage → localization → run); no rebase needed because main hadn't moved.

## What landed

- **1 new src module**: `src/novetest/coverage/_paths.py` (111 LOC; 2 public functions `to_workspace_relative_posix` + `relpath_or_drive_stripped`; `_WINDOWS_DRIVE_PREFIX_RE` at line 64)
- **3 src parsers edited**: `cobertura_parser.py`, `istanbul_parser.py`, `lcov_parser.py` (all route through new helper; `import os` removed from each)
- **1 new test module**: `tests/unit/coverage/test_paths.py` (9 tests for the helper)
- **3 test files extended**: `test_cobertura_parser.py`, `test_istanbul_parser.py`, `test_lcov_parser.py` (+1-2 tests each pinning cross-drive ValueError simulation via monkey-patched `os.path.relpath`)
- **WORKLOG**: top entry (charter format) — preserved verbatim through rebase chain
- **Net delta**: 4 src + 4 test files, +777 / -21 lines

## Post-merge test gate (full chain)

After all 3 slices merged at `a6ebd91`:

```
uv run mypy --strict src/novetest      → Success: no issues found in 93 source files (+1 vs prior baseline = new _paths.py)
uv run pytest -q tests/unit tests/integration → 1229 passed + 23 skipped + 1 failed in 32.43s
```

The 1 failed test is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` requiring `dotnet` on PATH — same pre-existing host-equipment dependency present on every prior cycle since 2026-05-31 (documented identically in all 3 handoffs of this triple + every recent cycle's WORKLOG). NOT a regression from this slice.

Delta vs prior baseline (1209 passed pre-cycle): **+20 net passing** = 12 Coverage + 8 Localization + 0 Run (Run added skipif markers that only fire on `sys.platform == "win32"`, so on Linux the count is unchanged).

## Verification scenarios for Manual Test

### Scenario A — 3-step fallback chain works on the helper directly

```bash
# Helper directly (Linux host, no Windows needed for structural proof)
uv run pytest -v tests/unit/coverage/test_paths.py
```

Expected: **9 passed**. Tests pin:
- Step 1 (subpath via `relative_to`)
- Step 2 (sibling via `os.path.relpath`)
- Step 3 (cross-drive simulation via monkey-patched `os.path.relpath` raising `ValueError("path is on mount 'D:', start on mount 'C:'")`)
- Drive-prefix regex tolerance (both `C:` and `c:` cases)
- Universal `not Path(result).is_absolute()` parametrized across all inputs

### Scenario B — Cross-drive ValueError simulation per parser

```bash
uv run pytest -v \
  tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_cross_drive_value_error_falls_back_to_drive_stripped \
  tests/unit/coverage/test_istanbul_parser.py::test_cross_drive_value_error_falls_back_to_drive_stripped \
  tests/unit/coverage/test_lcov_parser.py::test_outside_workspace_warning_text_is_posix_separator_agnostic
```

Expected: **3 passed**. These tests use `monkeypatch` to make `os.path.relpath` raise the Windows cross-drive `ValueError`. Each parser must:
- Produce a non-absolute path (B2-3 amendment's universal `not is_absolute()` contract holds)
- For LCOV specifically: warning text MUST carry POSIX `/` separators in the `workspace_root=` segment (no leaking `\\` from `os.fspath` on Windows)

### Scenario C — Coverage suite full sweep

```bash
uv run pytest -q tests/unit/coverage tests/integration/coverage
```

Expected: **156 passed + 3 skipped** (3 skips are toolchain-gated E2E for cargo/jest on unequipped hosts — unchanged behavior).

### Scenario D — Universal `not is_absolute()` contract spot-check

```bash
# Inside-workspace + outside-workspace + cross-drive (simulated) cases
uv run python -c "
from pathlib import Path
from novetest.coverage._paths import to_workspace_relative_posix

ws = Path('/ws/cargo-project')
print('subpath:', to_workspace_relative_posix(ws / 'src/foo.rs', ws))
print('sibling:', to_workspace_relative_posix(Path('/ws/other/bar.rs'), ws))
import os, unittest.mock as m
with m.patch('novetest.coverage._paths.os.path.relpath', side_effect=ValueError(\"path is on mount 'D:', start on mount 'C:'\")):
    print('crossdrive:', to_workspace_relative_posix(Path('D:/elsewhere/baz.rs'), ws))
"
```

Expected output:
```
subpath: src/foo.rs
sibling: ../other/bar.rs
crossdrive: elsewhere/baz.rs
```

All three values pass `not Path(...).is_absolute()`. The third (cross-drive) demonstrates the Step-3 drive-stripped POSIX fallback firing.

### Scenario E — Windows CI matrix verdict (binding criterion per task brief)

The 4 originally-RED Windows tests should turn GREEN after this slice + Localization merges:

```
tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_fixture_coverlet_basic_yields_one_file_fully_covered
tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlMultiClass::test_fixture_partial_coverage_yields_two_files
tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found
tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning
```

To capture the post-push CI run number:

```bash
gh run list --workflow ci.yml --branch main --limit 1
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

Expected: 3 Windows jobs (py3.11 / py3.12 / py3.13) all `conclusion: success`. Cite the run URL in the cycle-close history per task brief §"CI matrix verdict".

## Critical edge cases worth probing

1. **B2-3 amendment contract is STRENGTHENED, not amended.** Decision `2026-05-15-coverage-facts-json-layout.md` constraint #6 + Amendment 2026-06-08 said "outside-workspace files MUST be expressed as `../`-prefixed POSIX relpath." This slice does NOT amend the wording — it makes the invariant actually-enforced on Windows by closing the cross-drive escape hatch where previously `os.path.relpath` raised `ValueError` (the invariant held vacuously by non-emission, not by enforcement). Manual Test does not need to re-read the decision; spot-check that the helper docstring at `src/novetest/coverage/_paths.py:1-50` cites the amendment.

2. **The `_paths` helper module is private (`_paths.py` underscore prefix).** External consumers MUST go through the parser surface, not call the helper directly. Manual Test should NOT introduce production calls to `_paths` from outside `src/novetest/coverage/**`; that's a charter-forbidden cross-team coupling. The helper is a Coverage-team internal implementation detail.

3. **`derive_xunit.py` does NOT exist as a source module** (handoff Gotcha #2). The brief's named-but-nonexistent module was a brief-side glitch; the actual derive flow lives in `src/novetest/coverage/derive.py::_derive_xunit_cobertura` which routes through `parse_cobertura_xml`. The cobertura Step-3 fix transitively addresses the `test_derive_xunit_*` failures. Manual Test should verify no production code calls a `derive_xunit` symbol expecting it to live in its own module:

```bash
grep -rn 'from novetest.coverage.derive_xunit\|from .derive_xunit' src/novetest/ tests/
# Expected: zero matches
```

4. **LCOV warning text format change is operator-facing.** Pre-this-slice the `lcov_warnings[*]` entry's `workspace_root=` segment carried `os.fspath(workspace_root)` (Windows `\\` separators leaked); post-this-slice it carries `Path(workspace_root).as_posix()` (`/` only). Any external tooling/AI agent that grepped the warning text for backslash patterns would need updating. Spot-check: no test in the tree asserts a backslash form (the `test_outside_workspace_warning_text_is_posix_separator_agnostic` pins POSIX-only).

5. **The `_dotnet not on PATH` test failure is well-known and EXPECTED on hosts without .NET SDK** (handoff Gotcha #3 + every prior cycle's WORKLOG). Not a regression from this slice. Run team is expected to add a `pytest.importorskip`-style guard in a future cycle (out of Coverage scope; Coverage charter forbids editing `tests/integration/run/**`).

## Rebase / merge notes for the audit trail

- **Worktree branch**: `coverage/windows-parser-fixes`, based on `230420c` (main tip at slice start).
- **Rebase**: NOT needed — main hadn't moved between slice creation and merge dispatch.
- **FF-merge**: `230420c..4110645` clean.
- **WORKLOG conflicts**: 0 (this slice merged first in the chain; subsequent localization + run rebases conflicted on WORKLOG as expected — preserved this slice's entry verbatim per "newest entry on top + `---` between same-day entries" convention).
- **Test gate**: deferred to end-of-chain — see §"Post-merge test gate" above.
- **Worktree cleanup**: deferred to after this verification doc lands (charter convention: clean up after verification doc written, before Manual Test runs).
