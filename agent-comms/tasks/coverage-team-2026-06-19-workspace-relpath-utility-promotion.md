---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-06-19
slug: workspace-relpath-utility-promotion
parallel_cohort:
  - agent-comms/tasks/run-team-2026-06-19-v1-metadata-channel-sunset.md
  - agent-comms/tasks/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
related:
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md  # Amendment 2026-06-19 §4 applies
  - src/novetest/coverage/_paths.py
  - src/novetest/localization/failure_proximity.py
---

# Task: Promote `coverage/_paths.py` to `utils/path_utils.py` + migrate Localization callers (one-time charter cross-over)

## Mission

Lift the existing Coverage-internal cross-OS path-normalization helpers
(`to_workspace_relative_posix`, `relpath_or_drive_stripped` at
`src/novetest/coverage/_paths.py`) to a project-wide shared location
(`src/novetest/utils/path_utils.py`), and migrate the inline duplicate
implementations in Localization (`failure_proximity.py`'s
`_normalize_to_workspace_relative` + the outside-workspace check) to
call the shared utility.

Closes Future-cycle queue item #6 from the MVP release-ready sign-off
backlog. PM disposition #3 of
`agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
named the scenario A pattern as the project-wide canonical idiom; this
slice is the centralization step that disposition promised.

## Context

### Why this slice exists

The 2026-06-09 Windows-CI fix triple cycle (`4110645` Coverage +
`edb78f8` Localization + `a6ebd91` Run) closed a 9-day chronic Windows
red. Coverage and Localization independently implemented the same
"scenario A" pattern — `os.path.relpath` fallback after a
`Path.relative_to` try/except, with `.as_posix()` normalization. The
load-bearing lesson #4 of that cycle named the pattern as the
project-wide canonical idiom; the post-MVP polish queue carries this
centralization as item #6.

Coverage has already paid the architectural cost of building the
utility — `src/novetest/coverage/_paths.py` (112 lines) provides two
clean functions with full cross-drive Windows fallback (`relpath` →
drive-stripped POSIX form). The function body is **mature**: it
covers the three scenarios (clean subpath, ../-prefixed relpath,
cross-drive drive-stripped fallback) and has been exercised in
production since 2026-06-09. The work in this cycle is **relocation +
migration**, not reimplementation.

### Why charter cross-over is acceptable (CEO-approved)

CEO explicitly approved this cycle's charter cross-over: Coverage team
authors the migration of Localization callers (`src/novetest/localization/`)
even though that path is normally Localization team territory. The
authorization is scoped to:

- Pure refactor: behavior of Localization callers MUST be byte-equivalent
  before and after migration.
- Zero new logic: the migration replaces inline implementations with
  calls to the shared utility; no Localization-specific path-handling
  logic changes.
- Zero envelope-shape changes: the persisted localization findings
  must produce byte-identical envelope output before and after the
  migration (verifiable via syrupy snapshot pinning, see DoD #5).

This is the third application of the "in-cycle Option-A charter
exception" pattern (after v0.1.1 wheel version-bump 2026-06-10 and the
2026-06-18 Windows-pipeline cycle's CEO-push-gate deferral). Pattern is
mature; surface a question file ONLY if a scoped surprise emerges.

## Scope

### Files to modify (5-6)

| File | Change |
|---|---|
| `src/novetest/utils/path_utils.py` (NEW) | Move the `to_workspace_relative_posix` + `relpath_or_drive_stripped` functions + the `_WINDOWS_DRIVE_PREFIX_RE` constant from `coverage/_paths.py`. Preserve the docstrings byte-identically except for the "Internal to the Coverage engine" framing → rewrite as "Project-wide cross-platform workspace-relative path utility." Add a third public function `workspace_relpath(path, workspace_root) -> Path` per the canonical name in the backlog item — IMPLEMENT IT AS A `Path` RETURN WRAPPER over `to_workspace_relative_posix` (`return Path(to_workspace_relative_posix(path, workspace_root))`); this gives callers Path-typed convenience without duplicating the string function. The `__all__` exports all three names. |
| `src/novetest/utils/__init__.py` (CREATE IF MISSING; otherwise UPDATE) | Re-export the three public functions: `from novetest.utils.path_utils import workspace_relpath, to_workspace_relative_posix, relpath_or_drive_stripped`. Verify whether `src/novetest/utils/` currently has an `__init__.py` — if not, create the empty/minimal one. |
| `src/novetest/coverage/_paths.py` | Replace the function bodies with one-line re-exports from `utils.path_utils`: `from novetest.utils.path_utils import to_workspace_relative_posix as _t, relpath_or_drive_stripped as _r` + the public names. This keeps backward-compat for any internal Coverage caller while routing through the canonical surface. PM judgment call: alternative is to delete `coverage/_paths.py` entirely and update all Coverage-internal callers to import from `utils.path_utils` directly. **Coverage team chooses** based on call-site count — if ≤ 5 internal callers, delete + rewrite imports; if > 5, keep re-export shim. Either is acceptable. Document the chosen path in the handoff. |
| `src/novetest/localization/failure_proximity.py` | Refactor `_normalize_to_workspace_relative` (around line 520+) and the `_is_outside_workspace` check (around line 579+, 622+) to call `utils.path_utils.to_workspace_relative_posix` / `relpath_or_drive_stripped` / `workspace_relpath`. The local try/except/relpath logic at lines 543-633 collapses into 2-3 utility calls. Preserve the B2-2 outside-workspace asymmetry policy (failure_proximity stdlib frames remain absolute — that's a Localization-specific *policy* on TOP of the path utility, not a path-utility behavior). |
| `tests/unit/utils/test_path_utils.py` (NEW) | Move the Coverage-internal `_paths.py` tests if they exist (check `tests/unit/coverage/test_paths.py`) to this location. If no existing tests, write new ones covering: clean subpath, ../-prefixed relpath, cross-drive drive-stripped fallback (Windows-simulating via mocked `os.path.relpath`), `workspace_relpath` Path-return variant. ≥ 8 test cases. |
| `tests/unit/coverage/test_paths.py` (if it exists) | If it exists, delete (tests relocated to `tests/unit/utils/`). If it doesn't exist, no action. |
| `tests/unit/localization/test_failure_proximity.py` (if specific path-handling tests exist) | Leave the Localization-specific tests in place; the refactor is byte-equivalent so existing tests should pass without modification. If any test breaks because it mocked the inline implementation directly (e.g. `monkeypatch.setattr(failure_proximity, "_normalize_to_workspace_relative", ...)`), update the mock target to `novetest.utils.path_utils.to_workspace_relative_posix`. |

### Files NOT to modify

- `src/novetest/coverage/istanbul_parser.py`, `cobertura_parser.py`, `lcov_parser.py` — they already call `coverage/_paths.py` helpers; the function-body relocation OR re-export shim keeps them working unchanged. ZERO call-site changes in the parser files.
- `src/novetest/run/**`, `src/novetest/memory/**`, `src/novetest/orchestration/**` — these modules don't currently use the scenario A pattern; do NOT proactively migrate any path-handling there.
- `src/novetest/regression/**`, `src/novetest/replay/**` — out of scope for this slice.
- Any decision file (the scenario A pattern was already ratified in `2026-05-15-coverage-facts-json-layout.md` "Amendment 2026-06-08"). The amendment 2026-06-19 to `2026-06-08-equip-and-exercise...` was made by PM in the cycle dispatch commit; do NOT modify it.
- Any envelope-snapshot files. The refactor is byte-equivalent at the envelope layer.

## Definition of Done

1. `src/novetest/utils/path_utils.py` exists and exports 3 public names: `workspace_relpath`, `to_workspace_relative_posix`, `relpath_or_drive_stripped`. `src/novetest/utils/__init__.py` re-exports the same 3 names.
2. `grep -rn "from novetest.coverage._paths import\|from novetest.coverage import _paths" src/` returns either zero results (if Coverage team chose the delete+rewrite path) OR all results route through the re-export shim that re-imports from `utils.path_utils`.
3. `grep -rn "os.path.relpath\|relative_to(workspace_root)" src/novetest/localization/` returns ONLY references inside docstrings / comments / utility-call argument expressions; ZERO function-body `try/except/relpath` blocks remain inside `localization/`.
4. `uv run mypy --strict src/novetest` → `Success: no issues found in <N> source files` (baseline 109 +/- 1; new file adds 1 module, possibly +1 if `utils/__init__.py` is new).
5. `uv run pytest -q tests/unit tests/integration` → pass count is `prev + (new utils tests count)` with ZERO regressions and ZERO snapshot-file modifications (verify via `git status --porcelain tests/**/__snapshots__/*.ambr` — should show only NEW snapshot files if any, no MODIFIED). The 1 chronic dotnet host-equip failure stays unchanged.
6. Empirical envelope byte-identity: pick one localization end-to-end integration test that produces a non-trivial `data.findings[*].file_path` envelope field; capture the envelope before the slice (from the parallel cohort's pre-merge HEAD or `main` HEAD) and after the slice; `diff` of the two envelopes shows ZERO difference modulo the `verifiedAt` timestamp. Cite the test name + envelope diff command in the handoff.
7. Handoff documents the chosen `coverage/_paths.py` disposition (delete vs re-export shim) with the call-site count that drove the decision.

## Verification posture

- **Host**: equipped (per `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md` §1 SHOULD tier — Coverage team non-adapter slice). §2.5 pre-handoff gate does NOT fire (no adapter touch). Equipped-host pytest gate covers the cross-OS-relevant logic insofar as Linux can exercise it.
- **CI matrix verdict criterion (per §4 amendment 2026-06-19)**: this slice IS path/OS-sensitive per §4.1 #1 (touches `pathlib.Path` operations + `os.path` calls + workspace-relative path conversion). The §4 MUST fires — handoff MUST cite a `ci.yml` workflow run number on the merged HEAD with 9/9 matrix cells SUCCESS. The cross-OS evidence is the load-bearing assurance for this refactor; the 2026-06-09 Windows-CI fix triple's Scenario A pattern was empirically validated on Windows via that cycle's `ci.yml` `27187459586`, but the relocated utility surface MUST be re-validated on Windows + macOS as well.

## Out of scope

- DO NOT proactively migrate Run / Memory / Regression / Replay / Orchestration callers. None of them currently use the scenario A pattern; do NOT introduce path-handling normalization where there isn't one today.
- DO NOT change the function semantics. The relocated functions must produce byte-identical output for byte-identical input. The cross-drive Windows fallback (drive-stripped POSIX) must remain — do NOT simplify "for clarity."
- DO NOT introduce a `WorkspaceRelpath` class / wrapper type. Plain `Path` / `str` returns suffice; type discipline lives in caller signatures.
- DO NOT touch the B2-2 outside-workspace policy in failure_proximity (stdlib frames remain absolute by design). That's a Localization-specific filter on TOP of the path utility, not part of the utility.
- DO NOT add deprecation warnings to `coverage/_paths.py` if the re-export shim path is chosen. Internal re-exports don't merit deprecation; the shim is permanent until Coverage team decides to delete in a future cleanup.
- DO NOT modify the decision file `2026-05-15-coverage-facts-json-layout.md`. The "Amendment 2026-06-08" pin is still authoritative; this slice doesn't change the pattern, only its location.

## Failure modes (anticipated)

1. **Localization tests breakage on mock-target mismatch**: if any Localization test mocks the inline `_normalize_to_workspace_relative` directly via `monkeypatch.setattr(failure_proximity, "_normalize_to_workspace_relative", ...)`, the mock target moves to `novetest.utils.path_utils.to_workspace_relative_posix`. Fix in-place; do not regenerate test fixtures.
2. **Coverage `_paths.py` consumer count miscounted**: if `grep -rn "from novetest.coverage._paths\|from novetest.coverage import _paths" src/` returns more than 5 hits, prefer the re-export shim path (DoD #2 second clause). If it returns fewer, prefer delete + rewrite. Either is acceptable; pick the one that yields lower total LOC diff.
3. **`utils/__init__.py` may not exist**: `src/novetest/utils/` currently contains `git_inventory.py` and other utility modules (per repo layout). Confirm whether `__init__.py` exists first; if not, create it (do NOT mass-export every existing utils module — just add the 3 new path_utils exports; preserve current import surface).
4. **Snapshot-file collateral**: if any pre-existing snapshot includes a localization envelope's `file_path` field captured against a fixture with absolute paths, the refactor is byte-equivalent so no snapshot churn expected — but if a snapshot DOES change, the cause is upstream test fixture behavior, not this refactor; surface to PM via question file before regenerating.
5. **Windows-only behavior diff**: the cross-drive fallback was empirically validated on Windows CI by the 2026-06-09 triple. Linux dev-host pytest CANNOT exercise the cross-drive fallback path (no second drive). Rely on the CI matrix run citation per the verification posture above for the cross-OS empirical assurance.

## Procedural posture

- **Branch**: `coverage/workspace-relpath-utility-promotion` off `main` HEAD (currently `a2679a0`).
- **Worktree**: per Coverage team standard worktree root.
- **Handoff target**: Main Branch (standard worktree → FF-merge flow). FF-merge order is alphabetical-by-team — Coverage merges FIRST among the Wave 1 cohort.
- **WORKLOG entry required**: yes (this touches `src/` + `tests/`).
- **Handoff file**: `agent-comms/handoffs/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md` with "DoD bullets believed closed" list per CLAUDE.md convention.

## Parallel cohort awareness

This slice runs in **Wave 1 parallel** with two other team cycles + 1 PM-internal task (already merged in the cycle dispatch commit). File-footprint matrix:

| Slice | Owned area | Conflict with this slice? |
|---|---|---|
| Run: v1 metadata-channel sunset | `src/novetest/run/adapters/dotnet_adapter.py`, `tests/unit/run/adapters/test_dotnet_adapter.py` | None ✓ |
| Release: NOTICES + perf bench + wheel-NOTICES probe | `NOTICES.md`, `.github/workflows/release-test.yml`, `design/implementation-plan/foundations.md` | None ✓ |
| PM (no dispatch): CI verdict meta-decision amendment | `agent-comms/decisions/` (already merged in cycle dispatch commit) | None ✓ |

This slice is **THE first slice to qualify under §4 of the 2026-06-19
amendment** — handoff MUST cite a `ci.yml` matrix run on the merged
HEAD as the canonical cross-OS empirical assurance per §4.2.

## Estimated effort

~0.5-1 cycle. Code moves are mechanical (file rename + import-path rewrite); the load-bearing piece is the envelope byte-identity check (DoD #6) and the CI matrix citation (verification posture). ~150 LOC src move (mostly relocation, not net new), ~80-150 LOC test diff (new utils test file + possible Localization mock-target fix). Single-author; CEO-approved charter cross-over for the Localization touch.
