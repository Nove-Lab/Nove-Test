---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-06-09
slug: windows-parser-fixes
related:
  - agent-comms/tasks/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
---

# Handoff — Coverage parsers Windows cross-platform fixes (B2-3 amendment enforcement on Windows)

## TL;DR

The 3 coverage parsers that handle absolute native paths (istanbul,
LCOV, cobertura) all carried a 2-step relativization chain
(`try relative_to → except: os.path.relpath`) that BOTH raise
`ValueError` on Windows when the source and workspace are on
different drives. The GH Actions Windows runner is naturally cross-
drive (`runner.temp` on `C:\\` vs `GITHUB_WORKSPACE` on `D:\\`), so 4
Coverage tests had been RED on Windows × Python 3.11/3.12/3.13 for 9
days. This slice adds a third (drive-stripped POSIX) fallback step
via a new shared helper module `src/novetest/coverage/_paths.py`,
re-routes all 3 parsers through it, and POSIX-normalizes the LCOV
warning text so the literal-substring assertion holds on every
platform. The persisted-schema contract is unchanged (the B2-3
amendment's universal `not Path(file_path).is_absolute()` invariant
is STRENGTHENED, not amended). 12 new tests pin the 3-step fallback
chain + the POSIX-warning-text invariant on the Linux host via a
monkeypatched `os.path.relpath` that simulates the Windows
cross-drive `ValueError`.

## Worktree

- Branch: `coverage/windows-parser-fixes`
- Worktree path: `/home/yjshin/dev/novetest-windows-parser-fixes`
- Based on: `230420c` (main tip at slice start)
- Conflicts expected with parallel slices (Localization / Run): **none**
  (file footprints fully disjoint — Coverage's edits all live under
  `src/novetest/coverage/` and `tests/unit/coverage/`; Localization
  edits `src/novetest/localization/`; Run edits only `tests/{unit,
  integration}/run/`).
- FF-merge order per brief: **coverage → localization → run**
  (alphabetical).

## Files changed

| File | Type | Δ |
|---|---|---|
| `src/novetest/coverage/_paths.py` | **new** | +108 LOC; 2 public functions (`to_workspace_relative_posix`, `relpath_or_drive_stripped`); module docstring pins the WHY (Windows cross-drive ValueError + B2-3 amendment universal contract). |
| `src/novetest/coverage/istanbul_parser.py` | edit | `_workspace_relative` collapses to a one-liner calling `to_workspace_relative_posix`; `import os` removed; module docstring extended with the 2026-06-09 amendment note. |
| `src/novetest/coverage/lcov_parser.py` | edit | `_workspace_relative` outside-workspace branch routes through `relpath_or_drive_stripped`; warning-text `workspace_root=` segment coerced via `Path(workspace_root).as_posix()` (was `os.fspath(workspace_root)`); `import os` removed. |
| `src/novetest/coverage/cobertura_parser.py` | edit | `_resolve_workspace_relative` Step 2 routes through `relpath_or_drive_stripped`; algorithm-matrix docstrings (both module-level and function-level) updated to describe the third step; `import os` removed. |
| `tests/unit/coverage/test_paths.py` | **new** | +9 tests for the helper directly: step-1 subpath, step-2 sibling, step-3 cross-drive simulation, drive-prefix regex tolerance, universal contract `not is_absolute()` parametrized. |
| `tests/unit/coverage/test_istanbul_parser.py` | edit | +1 test `test_cross_drive_value_error_falls_back_to_drive_stripped` — monkeypatched `os.path.relpath` raises; istanbul parser still produces non-absolute POSIX path. |
| `tests/unit/coverage/test_lcov_parser.py` | edit | +1 test `test_outside_workspace_warning_text_is_posix_separator_agnostic` — verifies POSIX separator in warning text under cross-drive simulation. |
| `tests/unit/coverage/test_cobertura_parser.py` | edit | +1 test `test_cross_drive_value_error_falls_back_to_drive_stripped` — monkeypatched `os.path.relpath` raises; cobertura parser still produces non-absolute POSIX path ending in expected file. |
| `WORKLOG.md` | edit | +1 entry "## 2026-06-09 — windows-ci-fix-triple / coverage-windows-parser-fixes (1/3 of parallel cycle)" at the top. |

Net source delta: **1 new + 3 edited src + 1 new + 3 edited tests + 1
worklog = 9 file changes**; ~140 src LOC + ~210 test LOC. Algorithm
docstrings updated in 2 places (cobertura module + function). No
`pyproject.toml`, `.github/workflows/`, `cli/`, `models/`, or any
other-team territory touched.

## Phase 1 audit — parser path-handling matrix

The brief's "5 parsers + derive_xunit helpers" framing surveyed:

| Parser source file | Path-handling | Cross-drive `ValueError` risk on Windows | Action this slice |
|---|---|---|---|
| `parser.py` (coverage.py JSON) | adapter pre-relativizes via `[run] relative_files = True`; no `.relative_to()` in parser | **none** | no change |
| `istanbul_parser.py` | `_workspace_relative` had 2-step `try relative_to → except: os.path.relpath` | **HIGH** — Step 2 raised on cross-drive too | routed through `to_workspace_relative_posix` |
| `lcov_parser.py` | `_workspace_relative` had 2-step chain + warning emission | **HIGH** — Step 2 raised + warning text used `os.fspath` (Windows separators) | routed through `relpath_or_drive_stripped` + POSIX-flavored warning |
| `jacoco_parser.py` | synthesizes paths from `<package name>` + `<sourcefile name>` (no abs path handling) | **none** | no change |
| `cobertura_parser.py` | `_resolve_workspace_relative` had per-source loop + 2-step fallback on first source | **HIGH** — Step 2 raised on cross-drive | Step 2 routed through `relpath_or_drive_stripped` |
| `derive.py` (orchestration) | no `.relative_to()` or `os.path.relpath` in path-narrowing role; `_derive_xunit_cobertura` only post-filters by `is_file()` | **none directly** — indirectly affected via cobertura | covered transitively |

**Asymmetry surface narrower than brief assumed**: the brief named
"`derive_xunit`" as an additional parser. Audit found no such source
module — only `test_derive_xunit.py` as a test file. The actual
derive flow transits `parse_cobertura_xml`, so fixing cobertura's
Step 2 transitively fixes the derive_xunit test failure. No question
filed because the scenario A direction is unchanged; only the
file-footprint matrix shrank.

## Phase 2-3 implementation summary

### Phase 2 — shared helper + parser re-route

New `src/novetest/coverage/_paths.py` with:

```python
def to_workspace_relative_posix(path: Path, workspace_root: Path) -> str:
    """3-step: subpath → relpath → drive-stripped POSIX."""
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return relpath_or_drive_stripped(path, workspace_root)

def relpath_or_drive_stripped(path: Path, workspace_root: Path) -> str:
    """Step 2/3 half: os.path.relpath, or drive-stripped POSIX fallback."""
    try:
        return Path(os.path.relpath(path, workspace_root)).as_posix()
    except ValueError:
        # Windows cross-drive: emit a syntactically-relative POSIX form
        # preserving structure but stripping the drive prefix and any
        # leading "/".
        posix = PurePath(path).as_posix()
        return _WINDOWS_DRIVE_PREFIX_RE.sub("", posix).lstrip("/")
```

The drive-strip step (`re.sub(r"^[A-Za-z]:", "", posix).lstrip("/")`)
is the new step 3. It satisfies the universal `not is_absolute()`
contract on every platform — verified by the parametrized
`test_result_never_absolute`.

### Phase 3 — LCOV warning-text POSIX-normalize (option α)

Changed:
```python
warnings.append(
    f"outside-workspace path (preserved as relpath "
    f"against workspace_root={os.fspath(workspace_root)!r}): "
    f"{abs_path} -> {relpath}"
)
```
to:
```python
warnings.append(
    f"outside-workspace path (preserved as relpath "
    f"against workspace_root={Path(workspace_root).as_posix()!r}): "
    f"{abs_path} -> {relpath}"
)
```

PM-recommended option α was production-side (vs option β which would
have changed only the test assertion). Picked α because the warning
is user-/AI-facing and a leaking `\\` would be confusing in any
operator-debugging scenario, not only this test.

### Phase 4 — tests

The 4 originally-RED Windows tests (cobertura ×2 + derive_xunit ×1 +
lcov ×1) are now covered by:

1. **Direct helper coverage** in `tests/unit/coverage/test_paths.py`
   — 9 tests, including 3 that monkey-patch `os.path.relpath` to raise
   `ValueError("path is on mount 'D:', start on mount 'C:'")` to
   simulate the Windows cross-drive scenario on Linux.
2. **Per-parser cross-drive simulation** — 1 test added to each of
   the three parser test files (`test_paths.py`,
   `test_istanbul_parser.py`, `test_lcov_parser.py`,
   `test_cobertura_parser.py`) using the same monkey-patch pattern.
3. **LCOV POSIX-warning invariant** —
   `test_outside_workspace_warning_text_is_posix_separator_agnostic`
   pins the warning text contains the literal `'/ws/cargo-project'`
   POSIX form regardless of platform, and that no `\\` leaks through.

The originally-failing tests themselves did NOT need assertion
changes — they were already correct on Linux; the production fix
makes them green on Windows.

## Verification

```bash
$ cd /home/yjshin/dev/novetest-windows-parser-fixes

# Targeted coverage suite
$ uv run pytest -q tests/unit/coverage tests/integration/coverage
156 passed, 3 skipped in 0.22s

# Full unit + integration suite
$ uv run pytest -q tests/unit tests/integration
1218 passed, 26 skipped, 1 failed in 35.01s
# FAILED tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter
# Cause: `dotnet` not found on PATH (host equipment dependency)
# Status: PRE-EXISTING — see Gotcha #1 below + the 2026-06-08
#         B2-3 cycle's WORKLOG entry + the 2026-06-09 MVP
#         release-readiness WORKLOG entry. NOT a regression
#         from this slice.

# mypy strict
$ uv run mypy --strict src/novetest
Success: no issues found in 93 source files
# (was 92 before this slice; +1 = new _paths.py module)

# Targeted Windows-fix-class tests
$ uv run pytest -v \
    tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning \
    tests/unit/coverage/test_lcov_parser.py::test_outside_workspace_warning_text_is_posix_separator_agnostic \
    tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_cross_drive_value_error_falls_back_to_drive_stripped \
    tests/unit/coverage/test_istanbul_parser.py::test_cross_drive_value_error_falls_back_to_drive_stripped
4 passed in 0.01s
```

**Windows CI matrix verdict** (brief §"새 verdict 기준"): NOT
verifiable from this Linux host. Per brief, Main Branch team after
FF-merging the alphabetic triple (coverage → localization → run)
runs:

```bash
gh run list --workflow ci.yml --branch main --limit 3
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

and cites the `ci.yml` run number in the verification doc. The 4
originally-RED tests on Windows that this slice targets:

```
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_fixture_coverlet_basic_yields_one_file_fully_covered
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlMultiClass::test_fixture_partial_coverage_yields_two_files
FAILED tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found
FAILED tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning
```

are addressed structurally via the cross-drive monkey-patched
siblings on Linux (which all pass post-this-slice). The Linux
equivalents of these 4 tests already passed pre-this-slice; they
pass post-this-slice too — confirming no Linux regression.

## DoD bullets believed closed

The 10 bullets in the task brief §"Definition of done":

1. ✅ Phase 1 parser audit 결과 handoff에 명시 — see §"Phase 1 audit" matrix above (5 parsers + derive surveyed).
2. ✅ Category A (3 tests) Windows에서 그린 — cross-drive ValueError 해결 via Step 3 drive-stripped POSIX fallback in `relpath_or_drive_stripped`; structurally verified on Linux via monkey-patched ValueError siblings.
3. ✅ Category B (1 test) Windows에서 그린 — LCOV warning text POSIX separator via `Path(workspace_root).as_posix()` coercion; structurally verified on Linux via new POSIX-separator-agnostic test.
4. ✅ Universal contract `not Path(f.file_path).is_absolute()` (B2-3 amend contract) 유지 — STRENGTHENED, not changed; the Step 3 fallback closes the Windows escape hatch that previously violated the contract by raising rather than emitting a non-absolute value.
5. ✅ `uv run mypy --strict src/novetest` 클린 (93 src files).
6. ✅ `uv run pytest -q tests/unit tests/integration` 그린 (1218 passed + 26 skipped + 1 pre-existing dotnet host-equip; see Gotcha #1).
7. ❌ **CI matrix verdict criterion** — NOT verifiable from this slice. Brief explicitly assigns this to Main Branch / PM: after FF-merging the alphabetic triple, query `gh run list --workflow ci.yml`, view the Windows jobs, cite the run number. The 4 RED tests have the production fix landed in this slice; the verdict pin is Main Branch's job.
8. ✅ WORKLOG.md entry (charter 양식) — landed at the top.
9. ✅ Handoff `agent-comms/handoffs/coverage-team-2026-06-09-windows-parser-fixes.md` (this file) + DoD bullets believed closed.
10. ⏳ `python3 tools/regen_comms_index.py` — will run before commit.

## Gotchas (pin for future agents)

### 1. `os.path.relpath` ITSELF raises `ValueError` on Windows cross-drive — not just `Path.relative_to`

The PM brief's `os.path.relpath은 same-drive면 자연스럽게 동작,
cross-drive면 fallback` reads as if `os.path.relpath` always
succeeds; in fact on Windows, `ntpath.relpath` calls `abspath` on
both args (which resolves missing drives against `os.getcwd()`'s
drive) and compares the resulting drives — raising the exact
`ValueError: path is on mount 'X:', start on mount 'Y:'` if they
differ. This is the failure mode the GH Actions Windows runner hits
because `runner.temp` lives on `C:\\` while `GITHUB_WORKSPACE` lives
on `D:\\` — any source path without a drive (e.g. Cobertura
`<source>/abs/path/to/workspace`) inherits `C:\\` via `abspath`,
then fails the drive-equality check against the D-drive
`workspace_root`.

The PM brief's "unconditional `os.path.relpath`" recommendation is
**necessary-but-insufficient** — Step 3 (drive-stripped POSIX
fallback) had to be added.

Pin for next agent reading the brief: the brief's Cat A diagnosis
("`Path.relative_to` cross-drive ValueError") covers half the
surface; `os.path.relpath` shares the same fault.

### 2. `derive_xunit.py` source module does not exist

Brief §"Phase 1" says "5 parsers (`coverage_parser`,
`istanbul_parser`, `lcov_parser`, `jacoco_parser`,
`cobertura_parser`) + derive helpers (특히 `derive_xunit`)" but
`ls src/novetest/coverage/` returns no `derive_xunit.py`. The actual
derive module is `derive.py` and the engine-specific function is
`_derive_xunit_cobertura` (which itself does NOT do `.relative_to()`
or `os.path.relpath` — it post-filters via `is_file()`).

The brief's `test_derive_xunit_all_sources_unresolvable_returns_sources_not_found`
failure routes through `parse_cobertura_xml` — so the cobertura
Step 3 fix transitively addresses it.

No question filed because the scenario A direction is unchanged —
only the file-footprint matrix shrank from "5 parsers +
derive_xunit" to "3 parsers (istanbul/lcov/cobertura)" with
derive_xunit fixed-by-transit.

### 3. Pre-existing `test_dotnet_warnings.py` failure is Run-team territory

`tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
requires `dotnet` on PATH and fails on hosts without the .NET SDK
installed — same as the 26 other toolchain-gated tests that cleanly
skip. The Run-team follow-up was suggested in the 2026-06-08 B2-3
cycle (Coverage slice's handoff Gotcha #1) but not actioned;
surfaces here again.

PM may want to add a `pytest.importorskip`-style skip-guard to the
dotnet integration tests so they degrade-gracefully on non-equipped
hosts. Coverage-team did not action this — it lives in Run-team
territory (`tests/integration/run/`) which the Coverage charter
forbids.

## B2-3 amendment relationship

The 2026-06-08 amendment to
`decisions/2026-05-15-coverage-facts-json-layout.md` pinned the
"Universal contract `not Path(f.file_path).is_absolute()`"
invariant. This slice does NOT amend the decision — it makes the
invariant **actually hold on Windows** by closing the cross-drive
escape hatch (where previously `os.path.relpath` raised
`ValueError`, the parser propagated the error, the test failed, and
no `file_path` was emitted at all — the invariant held vacuously by
non-emission, not by enforcement). After this slice the invariant
is enforced in the positive case.

No further decision amend filed because the contract didn't change —
only the enforcement code did. The amendment's sentence becomes
load-bearing-enforced on every platform after this slice.

## Suggested commit message

```
fix(coverage): handle Windows cross-drive ValueError in workspace-relative path resolution (Windows-CI-fix 1/3)

The 3 native-path parsers (istanbul, LCOV, cobertura) used a 2-step
`try relative_to → except: os.path.relpath` chain that broke on
Windows: `os.path.relpath` itself raises ValueError when the inputs
are on different drives (the GH Actions Windows runner has
`runner.temp` on C:\\ and `GITHUB_WORKSPACE` on D:\\). 4 Coverage
tests had been RED on Windows × Python 3.11/3.12/3.13 for 9 days as
a result.

Extract a shared helper `src/novetest/coverage/_paths.py` with a
third (drive-stripped POSIX) fallback step. Re-route all 3 parsers
through it. POSIX-normalize the LCOV warning text so the literal
`/ws/cargo-project` substring assertion holds on every platform.

12 new tests pin the 3-step chain + the POSIX warning invariant on
the Linux host via a monkeypatched `os.path.relpath` that simulates
the Windows cross-drive ValueError.

The persisted-schema contract is unchanged; the B2-3 amendment's
universal `not Path(file_path).is_absolute()` invariant is
strengthened (the Step 3 fallback closes the Windows escape hatch).
```
