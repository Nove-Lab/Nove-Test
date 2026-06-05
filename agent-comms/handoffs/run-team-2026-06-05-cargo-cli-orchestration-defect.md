---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-05
slug: cargo-cli-orchestration-defect
related:
  - agent-comms/tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - design/implementation-plan/engine-adapters.md
---

# Handoff — cargo CLI orchestration defect closure (P1 + P2 + Process)

## TL;DR

Closes the 2026-06-04 cargo CLI orchestration defect surfaced by Manual
Test's polyglot host-equipping pass (see related findings). Three
defects, one slice:

| # | Defect | Severity | Fix shape |
|---|---|---|---|
| 1 | `novetest run .` against `cargo-test-basic` returned `adapter-unparseable-output` because `target_resolver` classified `.` as `target_type="directory"` with `target_expression="."`, and cargo_adapter appended `.` as a nextest filter that matched zero tests | P1 | **Fix A (adapter-local)**: suppress positional-filter append when `target_type == "directory"` |
| 2 | Build-failure heuristic emitted misleading "likely build failure" wording on filter-mismatch outcomes (stderr clearly showed `Finished test profile … target(s)` proving build succeeded) | P2 | **Fix B**: detect two-literal conjunction `Starting 0 tests across` + `error: no tests to run`, emit distinct typed message |
| 3 | No CLI-level smoke for cargo; orchestration `.relative_to(store.path)` invariant + target_resolver → cargo_adapter filter handling never exercised end-to-end | Process | **+2 integration smokes** in `test_cargo_basic.py` (dot case + bare control) |

Scope: 1 short cycle. Slice diff `+629 / -1` across 5 files. Pre-handoff
gate ran on the equipped host per
`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`
(this slice modifies both `cargo_adapter.py` AND `test_cargo_*.py`, so
§2.5 is in force).

## Worktree info

- **Worktree path**: `/home/yjshin/dev/aispace/novetest-cargo-cli-defect`
- **Branch**: `run-team/cargo-cli-orchestration-defect`
- **Base commit**: `0ac3f4e` (current `main` tip — "comms: close JUnit Phase 2.5 cycle (passed); matrix Maven floor 3.9→3.8; cargo CLI defect unblocked")
- **Commit**: pending (will be created during merge — see "Pre-merge checklist" below)

## Pre-handoff gate environment (§2.5 compliance)

Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`,
this slice's diff matches the binding heuristic (modifies both
`src/novetest/run/adapters/cargo_adapter.py` AND
`tests/integration/run/test_cargo_*.py`), so the pre-handoff gate runs
on an equipped host.

### Detected toolchain versions

| Tool | Version | Matrix floor | Source |
|---|---|---|---|
| `cargo` | `1.96.0 (30a34c682 2026-05-25)` | 1.74 | `~/.cargo/bin/cargo` (rustup) |
| `cargo-nextest` | `0.9.137 (75ddba7e9 2026-05-26)` | 0.9.50 | `~/.cargo/bin/cargo-nextest` |
| `cargo-llvm-cov` | `0.8.7` | (any current) | `~/.cargo/bin/cargo-llvm-cov` |
| `llvm-tools-preview` rustup component | present | required by llvm-cov | rustup-installed |

All versions preserved on this host from Manual Test's 2026-06-04
equipping session per `findings/manual-test-team-2026-06-04-host-equip.md`.
Sourced via `source ~/.local/share/novetest-toolchains.sh` before each
gate run.

### Engine-specific integration counts (§2.5.4 requirement)

`uv run pytest -v tests/integration/run/test_cargo_*.py` (cargo cases only):

```
tests/integration/run/test_cargo_basic.py::test_cargo_basic_captures_failing_test_and_integration_binary PASSED
tests/integration/run/test_cargo_basic.py::test_cli_smoke_run_dot_emits_envelope                          PASSED
tests/integration/run/test_cargo_basic.py::test_cli_smoke_run_bare_emits_envelope                         PASSED
tests/integration/run/test_cargo_coverage.py::test_cargo_coverage_emits_lcov_report                       PASSED
```

**4 passed, 0 skipped, 0 failed.** §2.5 mandate ("skip count for the
engine's integration cases MUST be 0; failure count MUST be 0") satisfied.

## Files written / modified

| File | Lines | Change |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +82 / -1 | Fix A (directory-type carve-out) + Fix B (no-tests-match heuristic) + 2 new module-level constants |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +316 / 0 | 4 new tests: Fix A positive + Fix A scope guard + Fix B positive + Fix B scope guard |
| `tests/integration/run/test_cargo_basic.py` | +221 / 0 | 2 new CLI smokes (dot case + bare control) + `cli_smoke_workspace` fixture + `_spawn_novetest` helper + docstring expansion |
| `design/implementation-plan/engine-adapters.md` | +1 / 0 | §5 Edge cases — directory-typed-target paragraph (Fix A documentation + sub-crate-selection deferral) |
| `WORKLOG.md` | +10 / 0 | New top entry |

Total: **+630 / -1** across 5 files.

## Fix shape declaration (brief §8.3)

**Fix A chosen.** Adapter-local normalization in `cargo_adapter.py`.

Rationale (one paragraph): Fix A is contained to a single source file
(`cargo_adapter.py`) with no cross-engine coupling, matches the reality
that `cargo nextest` doesn't accept filesystem-directory args as
positional filters (positional = filter DSL expression), and aligns the
user-facing semantic (`novetest run .` ↔ `novetest run` bare ↔ "run the
whole workspace"). Fix B (target_resolver-side carve-out for the
workspace root) would alter the cross-adapter contract for "directory"
classification, affecting pytest/jest/gotest which currently consume
the verbatim path successfully through their own native engine
conventions. Fix C (translate `.` to nextest's `-E 'package(...)'`
expression DSL) would require per-crate-path expression construction
and brittle path-to-crate-identifier mapping. PM's recommendation in
brief §1 was Fix A; this slice took it.

Sub-crate directory selection (e.g. `novetest run crates/foo/`) is
documented as deferred in `engine-adapters.md §5` until a user requests
it — future work would translate the sub-crate path to either
`cargo -p crate` or nextest's `-E 'package(crate)'` selector.

## Before / after envelope capture (brief §8.2)

### Pre-fix baseline

Workspace: `/tmp/cargo-defect-sut` (clean copy of
`tests/fixtures/projects/cargo-test-basic`). Commands sourced
`~/.local/share/novetest-toolchains.sh` first.

```sh
uv run --project /home/yjshin/dev/aispace/novetest-cargo-cli-defect novetest init
uv run --project /home/yjshin/dev/aispace/novetest-cargo-cli-defect novetest run .
# exit 1
```

Envelope (verbatim, indented for readability):

```json
{
  "command": "run",
  "data": {},
  "errors": [
    {
      "code": "adapter-unparseable-output",
      "details": {},
      "message": "cargo nextest exited 4 without starting any test (likely build failure); stderr tail: test_basic v0.1.0 (/tmp/cargo-defect-sut)\n    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.31s\n────────────\n Nextest run ID 640954a3-958b-4054-862d-d00c2f0b2d57 with nextest profile: default\n    Starting 0 tests across 2 binaries (3 tests skipped)\n────────────\n     Summary [   0.001s] 0 tests run: 0 passed, 3 skipped\nerror: no tests to run\n(hint: use `--no-tests` to customize)\n"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

Matches the verbatim Manual Test 2026-06-04 findings file's
Evidence-B capture (modulo session-specific nextest run UUID + timing).

### Post-fix Run Record

Same workspace, same commands, after Fix A + Fix B landed on the
worktree.

```sh
uv run --project /home/yjshin/dev/aispace/novetest-cargo-cli-defect novetest run .
# exit 3 (EXIT_USER_TESTS_FAILED)
```

Envelope (trimmed for clarity; full envelope at
`/tmp/post-fix-envelope.json`):

```json
{
  "schema": "novetest/v1",
  "ok": true,
  "errors": [],
  "data": {
    "memory_entry": {
      "run_record": {
        "engine_name": "cargo-test",
        "engine_version": "1.96.0",
        "status": "failed",
        "target_expression": ".",
        "target_type": "directory",
        "summary_counts": {
          "failed": 1,
          "passed": 2,
          "skipped": 0,
          "total": 3
        },
        "test_results": [
          {"node_id": "cargo_test_basic::cargo_test_basic$tests::test_add_passes", "outcome": "passed", ...},
          {"node_id": "cargo_test_basic::integration_test$test_add_via_integration", "outcome": "passed", ...},
          {"node_id": "cargo_test_basic::cargo_test_basic$tests::test_subtract_intentionally_fails", "outcome": "failed", "failure_reference": "native/failures/...", ...}
        ]
      }
    }
  }
}
```

Notable shape facts:
- `target_expression == "."` and `target_type == "directory"` — the user's
  input is preserved on the audit trail even though the adapter
  suppressed the append at the nextest argv layer. Audit/replay can
  reconstruct what was requested.
- `summary_counts == {passed: 2, failed: 1, skipped: 0, total: 3}` matches
  the fixture's contract (1 pass unit + 1 fail unit + 1 pass integration).
- `engine_name == "cargo-test"` consistent with pre-fix shape.
- `engine_version == "1.96.0"` correctly probed from `cargo --version`.
- `status == "failed"` because of `test_subtract_intentionally_fails`.
- Exit 3 (`EXIT_USER_TESTS_FAILED`) — the dedicated CLI channel for
  "tests ran, some failed", NOT exit 1 (the pre-fix mode).

## Slice diff summary (brief §8.4)

```
 WORKLOG.md                                    |  10 +
 design/implementation-plan/engine-adapters.md |   1 +
 src/novetest/run/adapters/cargo_adapter.py    |  82 ++++++-
 tests/integration/run/test_cargo_basic.py     | 221 ++++++++++++++++++
 tests/unit/run/adapters/test_cargo_adapter.py | 316 ++++++++++++++++++++++++++
 5 files changed, 629 insertions(+), 1 deletion(-)
```

## Test counts post-fix (brief §8.5)

| Slice | Pre-fix baseline | Post-fix actual | Delta |
|---|---|---|---|
| `tests/unit/run/adapters/test_cargo_adapter.py` | 20 passed | 24 passed | **+4** (the new Fix A + B tests) |
| `tests/integration/run/test_cargo_*.py` (equipped host) | 2 passed | 4 passed | **+2** (the new CLI smokes) |
| `tests/integration/run/` (equipped host) | 12 passed + 2 skipped | 14 passed + 2 skipped | +2 passed, 0 skip delta |
| `uv run pytest -q tests/unit tests/integration` (equipped host) | 1034 passed + 5 skipped + 0 failed (post-JUnit-3 baseline) | 1042 passed + 3 skipped + 0 failed | **+8 passed, -2 skipped, 0 failed** |
| `uv run mypy --strict` | `Success: no issues found in 90 source files` | `Success: no issues found in 90 source files` | unchanged |

Note on the brief §8.5 baseline ("pre-fix 9-passed-1-failed-2-skipped
on equipped host"): that baseline was written before JUnit hotfix #3
landed at `ddfc5b9` (Manual Test re-pass verdict `passed` per
`history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md`).
With JUnit-3 merged the equipped-host `tests/integration/run/` baseline
is now 12 passed + 2 skipped (no failures). The +1 net new passing test
the brief targeted is delivered as the dot CLI smoke; the bare CLI
smoke is the additional control case (the brief allowed either-or
shape but explicitly recommended both). Spirit of "+1 net new on
equipped host" + "0 failed" is met with margin.

The 2 residual `tests/integration/run/` skips are `test_jest_basic.py`
+ `test_jest_coverage.py` because the worktree's `tests/fixtures/
projects/jest-basic/node_modules/` is absent (`git worktree add`
materializes only tracked files; the jest fixtures' `node_modules/` is
gitignored and was populated only in the main repo by Manual Test's
2026-06-04 `npm install`). Out of scope for this slice's §2.5
diff-classification heuristic (which binds only the engine in the diff
— cargo). See WORKLOG entry's Gotcha #3 for the suggested PM
follow-up.

## DoD bullets believed closed (brief §6)

| # | DoD bullet (paraphrased) | Evidence pointer | ✓ |
|---|---|---|---|
| 1 | `cargo_adapter.py` no longer appends non-empty `target_expression` to nextest argv when `target_type == "directory"`, unit-tested | `cargo_adapter.py:219-247` + `test_cargo_adapter.py::test_argv_omits_directory_target_expression` | ✓ |
| 2 | Build-failure heuristic detects `"Starting 0 tests across"` literal + emits message that does NOT include "likely build failure", unit-tested with stubbed subprocess returning Manual Test's verbatim stderr | `cargo_adapter.py:352-388` + `test_cargo_adapter.py::test_no_tests_match_stderr_surfaces_distinct_message` | ✓ |
| 3 | `tests/integration/run/test_cargo_*.py` includes ≥1 CLI-level smoke via `subprocess.run([..., "novetest", "run", "."])` asserting `returncode in (0, 3)` (NOT `(0, 1)`) + envelope `engine_name == "cargo-test"`; skip-gates on `shutil.which("cargo")` AND `shutil.which("cargo-nextest")` | `test_cargo_basic.py::test_cli_smoke_run_dot_emits_envelope` | ✓ |
| 4 | Second CLI smoke covers bare `novetest run` (no positional) case | `test_cargo_basic.py::test_cli_smoke_run_bare_emits_envelope` | ✓ |
| 5 | `engine-adapters.md §5` carries note about directory-type targets resolving to workspace-wide cargo execution (sub-crate deferred) | `design/implementation-plan/engine-adapters.md:396` (Edge cases section) | ✓ |
| 6 | `uv run pytest -q tests/unit tests/integration` on equipped host: 9 passed, 0 failed, 2 skipped (JUnit cases pass post-hotfix) | `tests/integration/run/` = 14 passed + 2 skipped + 0 failed (exceeds spirit; see "Test counts" §). Full default suite: 1042 + 3 + 0 | ✓ |
| 7 | `uv run mypy --strict` clean | `Success: no issues found in 90 source files` | ✓ |
| 8 | Handoff includes before/after capture of CLI envelope for `novetest run .` on `cargo-test-basic` | §"Before / after envelope capture" above | ✓ |

PM verifies + ticks these on cycle close.

## Pre-merge checklist (Main Branch team)

Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §1
+ §2.5` Main Branch's pre-merge gate ALSO runs on an equipped host
(same toolchain set as Run team's pre-handoff gate above).

1. `source ~/.local/share/novetest-toolchains.sh` before `pytest`.
2. `cd` into the worktree (`/home/yjshin/dev/aispace/novetest-cargo-cli-defect`).
3. `uv run pytest -q tests/unit tests/integration` — expect **1042 passed + 3 skipped + 0 failed**. The 3 skips are:
   - `test_jest_basic.py::test_jest_basic_runs_and_returns_passed_record`
   - `test_jest_coverage.py::test_jest_coverage_emits_istanbul_final_json`
   - 1 in `localization` (pre-existing pattern; see baseline). If jest in the worktree's `node_modules/` is empty, that's expected — the worktree is post-git-worktree-add. If Main Branch wants jest to execute too, `cd tests/fixtures/projects/jest-basic && npm install --no-audit --no-fund` (and same for `jest-basic-coverage`); ~30s each.
4. `uv run pytest -v tests/integration/run/test_cargo_*.py` — expect **4 passed + 0 skipped + 0 failed** (all cargo cases EXECUTE).
5. `uv run mypy --strict src` — expect `Success: no issues found in 90 source files`.
6. Optional sanity reproducer: `cd /tmp && rm -rf cargo-sut && cp -r /home/yjshin/dev/aispace/novetest-cargo-cli-defect/tests/fixtures/projects/cargo-test-basic cargo-sut && cd cargo-sut && uv run --project /home/yjshin/dev/aispace/novetest-cargo-cli-defect novetest init && uv run --project /home/yjshin/dev/aispace/novetest-cargo-cli-defect novetest run .` — expect exit 3, ok=true, no `adapter-unparseable-output` in errors. (Same reproducer Manual Test will exercise per brief §7.)
7. FF-merge the branch onto `main`. No conflicts expected (only one source file touched + new tests).
8. Write verification doc for Manual Test re-pass per `agent-comms/README.md` template + decision §3's required scenarios (CLI smoke gate + Gate A tool-floor + plugin-floor pre-flight).

## Decisions referenced

| Decision | Honored as |
|---|---|
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1` | Manual Test re-pass will run on equipped host (this Run-team handoff describes what to verify) |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2` | 2 CLI-level smokes added with skip-gate on `cargo + cargo-nextest`, canonical pattern source `tests/integration/orchestration/conftest.py::run_cli_in` |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5` | Pre-handoff gate ran on equipped host with toolchain versions detected ≥ matrix floors; engine integration cases skip=0, fail=0 |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §4` | Gate-A tool-floor + plugin-floor: cargo's matrix row already encodes both `cargo>=1.74` AND `cargo-nextest>=0.9.50` (the "plugin" floor); the integration smoke's skip-gate checks both `shutil.which("cargo")` AND `shutil.which("cargo-nextest")` (the strictly-correct pattern) |
| `2026-05-29-cargo-adapter-nextest-primary.md` | Unchanged. Nextest-only contract preserved; no plain-text fallback introduced; no nightly path |
| `2026-05-29-cargo-adapter-v1-without-rust-e2e.md §3` | Trigger (a) ("CI matrix gains a Rust cell") materially closed at the cargo-CLI-orchestration-path level for the running adapter, though the formal CI-matrix tick is Release-team territory and remains open |
| `2026-05-25-supported-engine-matrix.md` | Unchanged (no floor or ceiling bumps in this slice) |

## Open items / surprises for PM

### Operational (non-blocking)

1. **Jest fixture node_modules under worktrees** (WORKLOG Gotcha #3): each new `git worktree add` materializes only tracked files; the gitignored `node_modules/` under `tests/fixtures/projects/jest-basic{,-coverage}/` lives only in the main repo. Options PM may want to amend in `scripts/dev-host-setup.md` or the §2.5 heuristic: (a) document the `cd worktree && npm install` step as part of equipped-host setup; (b) treat `node_modules/` as cross-worktree-shared via symlink; or (c) constrain §2.5's "skip count for the engine's integration cases MUST be 0" to the engine in the diff (cargo here) — which is the de facto current interpretation. This slice took option (c) by design; no follow-up required for cargo.

2. **`adapter-unparseable-output` umbrella overload** (per 2026-06-04 history §"Surprises"): this slice adds yet another disambiguation message to the `unparseable-output` kind (compile-failure / env-var / llvm-cov-missing / **no-tests-match**). The brief §5 explicitly deferred the umbrella split to a future `engine-adapters.md §4.B` revision. The new "filter matched zero tests" wording is keyword-stable enough that an AI consumer or human can disambiguate at the message level; an explicit kind would be cleaner but per brief §10 requires a `questions/` entry first. Recommend PM consider the umbrella split as part of the next adapter-cycle cleanup (dotnet brings xunit/coverlet-specific signals that may warrant the same disambiguation pattern).

3. **`2026-05-29-cargo-adapter-v1-without-rust-e2e.md §3` closure trigger (a)** is now materially closed for cargo's running CLI-orchestration path (this slice's pre-handoff gate + the new CLI smokes prove the path stays green on the equipped host). The formal trigger ((a) "CI matrix gains a Rust cell") is Release-team territory and tied to PyApp matrix-cell work; PM may want to coordinate on whether the v1-exception remains formally open or can be closed now that the operational gap is closed.

### Process (compliance with the binding §2.5 mandate)

4. **§2.5.4 handoff section completeness**: this handoff carries §"Pre-handoff gate environment" with detected toolchain versions + engine-specific integration counts (cargo: 4 passed, 0 skipped, 0 failed) — exactly the §2.5.4 required shape. Pin this as the template precedent for future adapter cycles' handoffs.

5. **No new decisions filed**: this slice neither raised nor amended any decision. All work stayed inside the pre-bound contracts (nextest-primary, equip-and-exercise §1-2-2.5-4, supported-engine-matrix). Brief §5 explicitly listed out-of-scope; this slice obeyed.

## Worklog entry text (pasted verbatim)

```
## 2026-06-05 — phase2/3 / cargo-cli-orchestration-defect

- Landed: Closed the 2026-06-04 cargo CLI orchestration defect per
  `tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md` — 1 P1
  (Defect 1: `novetest run .` against `cargo-test-basic` returned
  `adapter-unparseable-output`) + 1 P2 (Defect 2: build-failure heuristic
  emitted misleading "likely build failure" wording on filter-mismatch
  outcomes) + 1 Process (Defect 3: no CLI-level smoke for cargo). 0 new
  src files (source count stays 90), 1 modified src file + 2 modified
  test files + 1 modified design doc. Fix A: `cargo_adapter.py` —
  directory-type carve-out before `argv.append(target_expression)` (the
  `if target_expression and test_target.target_type != "directory":`
  guard). Fix B: `cargo_adapter.py` — two new module-level constants
  `_NEXTEST_NO_TESTS_LITERAL` + `_NEXTEST_NO_TESTS_ERROR_LITERAL`; the
  build-failure heuristic gained a carve-out branch before the generic
  "likely build failure" raise that detects the conjunction of both
  literals + surfaces a distinct error message naming "filter matched
  zero tests" with the offending target_expression and target_type in
  the message text; stays on kind="unparseable-output" per brief §2.
  test_cargo_adapter.py +4 tests: Fix A positive + Fix A scope guard
  (file-type passthrough) + Fix B positive + Fix B scope guard
  (compile-failure passthrough). test_cargo_basic.py +2 CLI smokes
  (dot + bare control) + cli_smoke_workspace fixture + _spawn_novetest
  helper, both skip-gated on cargo+cargo-nextest. engine-adapters.md §5
  Edge cases: 1-paragraph note on directory-typed targets + deferred
  sub-crate selection.
- Verified: Pre-handoff gate on equipped host per
  `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`
  (this slice modifies both cargo_adapter.py and test_cargo_*.py so §2.5
  is in force). Toolchain: cargo 1.96.0 + cargo-nextest 0.9.137 +
  cargo-llvm-cov 0.8.7 (all ≥ matrix floors). Equipped-host integration:
  `uv run pytest -v tests/integration/run/` → 14 passed + 2 skipped +
  0 failed in 18.44s; all 4 cargo cases EXECUTE (no skips). §2.5
  mandate "skip=0, fail=0 for the engine's cases" satisfied. Pre-fix
  reproduction confirmed verbatim from findings (exit 1, ok=false,
  code=adapter-unparseable-output); post-fix verified exit 3,
  ok=true, no errors, summary_counts={passed:2, failed:1, total:3}.
  Default suite: 1042 passed + 3 skipped + 0 failed (was 1034+5+0
  pre-fix → +8 passed, -2 skipped, 0 failed). mypy --strict:
  Success no issues found in 90 source files (unchanged).
- Left open: 8 DoD bullets believed closed per brief §6 — directory
  carve-out unit-tested ✓; no-tests-match heuristic unit-tested ✓;
  CLI smoke dot case ✓; CLI smoke bare control case ✓;
  engine-adapters.md §5 paragraph ✓; equipped-host pytest baseline
  exceeded ✓; mypy strict clean ✓; before/after envelope capture in
  handoff ✓. Out of scope per brief §5: NO per-sub-crate -p/--package
  selector (deferred); NO new AdapterInvocationError.kind (stayed on
  unparseable-output per brief §2); NO target_resolver modification
  (Fix A is adapter-local; Fix B was Fix-B in the brief's variant
  taxonomy and would have required a questions/ entry); NO
  unparseable-output umbrella refactor; NO retroactive CLI-smoke
  backfill for pytest/jest/gotest. Hotfix continuity: JUnit-1/2/3
  + cargo env-var hotfix + cargo lcov polish + typed metadata slot
  all preserved unchanged.
- Gotcha: (1) Fix-B's message-text shape (target_expression repr +
  target_type repr) is load-bearing for AI consumers; a future
  "simplify error message" refactor that drops target_type would
  silently regress diagnostic quality. (2) Fix-B's two-literal
  conjunction is load-bearing scope-control: "Starting 0 tests across"
  alone matches "compiled-but-zero-#[test]-items" (build-adjacent);
  conjunction with "error: no tests to run" excludes that case
  because nextest only emits the second literal on filter mismatch.
  Scope-guard test pins this. (3) Worktree-isolated node_modules
  makes jest tests skip even on equipped hosts — git worktree add
  materializes only tracked files; the jest fixtures' node_modules/
  is gitignored. Out of scope for §2.5's cargo-diff classification;
  PM may want to amend setup docs or the heuristic for cycles where
  the originating team's pre-handoff gate is expected to be
  host-comprehensive.
- Next: Handoff written. PM verifies DoD bullets + dispatches Main
  Branch for FF-merge (Main Branch's pre-merge gate ALSO runs on
  equipped host per §2.5 + §1 parallel mandate) + dispatches Manual
  Test for re-pass on equipped host. Forward implication: this slice
  materially closes trigger (a) of cargo-adapter-v1-without-rust-e2e
  §3 for the running-cargo CLI path. The formal trigger remains
  Release-team territory but operationally the cargo CLI path is no
  longer "structurally unverifiable" — the next equip-and-exercise
  cycle's gate will catch any regression.
```

(Same content lives at WORKLOG.md top of file as the new entry.)
