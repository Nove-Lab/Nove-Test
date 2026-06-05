---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-05
slug: cargo-cli-orchestration-defect
merged_commit: 176e593
related:
  - agent-comms/handoffs/run-team-2026-06-05-cargo-cli-orchestration-defect.md
  - agent-comms/tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
---

# Verification — cargo CLI orchestration defect closure (P1 + P2 + Process)

## TL;DR

- **Merged commit**: `176e593` (`fix(run): cargo CLI orchestration defect — directory-type carve-out + no-tests-match heuristic + CLI smokes`)
- **Source handoff**: [`run-team-2026-06-05-cargo-cli-orchestration-defect.md`](../handoffs/run-team-2026-06-05-cargo-cli-orchestration-defect.md)
- **Source task**: [`run-team-2026-06-04-cargo-cli-orchestration-defect.md`](../tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md)
- **Source finding** (defect surfaced here): [`manual-test-team-2026-06-04-host-equip.md`](../findings/manual-test-team-2026-06-04-host-equip.md) §"Cargo adapter — CLI vs adapter-direct discrepancy"
- **Equip mandate**: [`2026-06-04-equip-and-exercise-for-adapter-cycles.md`](../decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md) §1 (Manual Test re-pass MUST run on equipped host)

Three defects closed in one slice — FF-merged from a single Run-team commit on top of `0ac3f4e`. Pre-merge gate ran on the equipped host (toolchain: cargo 1.96.0 + cargo-nextest 0.9.137 + cargo-llvm-cov 0.8.7 + JDK 17 + Maven + Gradle, all sourced via `~/.local/share/novetest-toolchains.sh`).

| # | Defect closure | Verify via |
|---|---|---|
| 1 | `novetest run .` on cargo workspace no longer returns `adapter-unparseable-output` | Scenario A below (CLI smoke reproducer) |
| 2 | Build-failure heuristic no longer misfires on filter-mismatch outcomes (no more "likely build failure" wording when stderr clearly shows `Finished test profile`) | Scenario C (negative-path probe) |
| 3 | `tests/integration/run/test_cargo_*.py` carries 2 new CLI-level smokes (dot case + bare control); equipped-host `tests/integration/run/test_cargo_*.py` = **4 passed / 0 skipped / 0 failed** | `pytest -v tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py` |

## Pre-merge gate captured (equipped host, this session)

`source ~/.local/share/novetest-toolchains.sh` then:

| Command | Expected | Actual |
|---|---|---|
| `uv run pytest -q tests/unit tests/integration` | 1042 passed + 3 skipped + 0 failed | **1042 passed + 3 skipped + 0 failed in 50.75s** ✓ |
| `uv run pytest -v tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py` | 4 passed + 0 skipped + 0 failed | **4 passed + 0 skipped + 0 failed in 1.68s** ✓ |
| `uv run mypy --strict src` | Success: no issues found in 90 source files | **Success: no issues found in 90 source files** ✓ |

The 3 skips in the full suite are: `test_jest_basic.py::test_jest_basic_runs_and_returns_passed_record`, `test_jest_coverage.py::test_jest_coverage_emits_istanbul_final_json`, and 1 localization case. Jest skips are worktree `node_modules/` artifacts (handoff §"Test counts" gotcha; not regression-relevant). If Manual Test wants jest to execute too: `cd tests/fixtures/projects/jest-basic && npm install --no-audit --no-fund` (and same for `jest-basic-coverage`).

## Verification environment

This verification was prepared on the polyglot-equipped host preserved across the JUnit 2.5 cycle. Manual Test re-pass MUST run on the same equipped host (or equivalent). Source the toolchain script first:

```sh
source ~/.local/share/novetest-toolchains.sh
which cargo cargo-nextest cargo-llvm-cov   # all three must resolve
cargo --version                            # >= 1.74 (matrix floor)
cargo nextest --version                    # >= 0.9.50 (matrix floor)
```

## Scenarios (CLI smokes)

All paths in these scenarios were captured **verbatim from the merged-code envelope on this session** (commit `176e593`), per the Main Branch charter's "Verification-doc envelope/API path discipline" rule. No path was carried over from prior cycles' templates.

### Scenario A — `novetest run .` (directory-type target — the original defect reproducer)

**Setup** (fresh fixture copy; the `~/.local/share/novetest-toolchains.sh` source must already be in effect):

```sh
cd /tmp && rm -rf cargo-sut
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/cargo-test-basic cargo-sut
cd cargo-sut
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init
```

**Reproducer**:

```sh
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run . > /tmp/cargo-run-dot.json
echo "exit=$?"
```

**Expected**:
- **Exit code = 3** (`EXIT_USER_TESTS_FAILED`; per `src/novetest/cli/output.py:15`). NOT exit 1 (the pre-fix mode), NOT exit 2 (usage).
- **`ok = true`** in the envelope JSON.
- **No `adapter-unparseable-output` in `errors[]`** — `errors[]` must be empty.
- **`data.memory_entry.run_record.engine_name == "cargo-test"`**.
- **`data.memory_entry.run_record.target_expression == "."`** AND **`data.memory_entry.run_record.target_type == "directory"`** — the user's input is preserved on the audit trail even though the adapter suppressed the append at the nextest argv layer.
- **`data.memory_entry.run_record.summary_counts == {"passed": 2, "failed": 1, "skipped": 0, "total": 3}`** — the canonical fixture's contract (1 pass unit + 1 fail unit + 1 pass integration binary).
- **`data.memory_entry.run_record.status == "failed"`** (because `test_subtract_intentionally_fails` fails by design).
- **`data.memory_entry.run_record.metadata.nextest_version`** present and matches `cargo nextest --version` output.
- **`data.memory_entry.run_record.metadata.native_exit_code == 100`** (cargo-test's native exit when ≥1 test fails).
- **`data.memory_entry.run_record.test_results`** is a 3-element list with these `node_id`s (order may vary by run, but all 3 must be present):
  - `cargo_test_basic::cargo_test_basic$tests::test_add_passes` → outcome `passed`
  - `cargo_test_basic::integration_test$test_add_via_integration` → outcome `passed`
  - `cargo_test_basic::cargo_test_basic$tests::test_subtract_intentionally_fails` → outcome `failed`, with a non-null `failure_reference` pointing under `native/failures/`.

**Quick assertion script** (copy-paste; uses observed paths from the post-merge envelope dump):

```sh
python3 - <<'PY'
import json
e = json.load(open('/tmp/cargo-run-dot.json'))
rr = e['data']['memory_entry']['run_record']
assert e['ok'] is True, e
assert e['errors'] == [], e['errors']
assert rr['engine_name'] == 'cargo-test', rr['engine_name']
assert rr['target_expression'] == '.', rr['target_expression']
assert rr['target_type'] == 'directory', rr['target_type']
assert rr['summary_counts'] == {'passed': 2, 'failed': 1, 'skipped': 0, 'total': 3}, rr['summary_counts']
assert rr['status'] == 'failed', rr['status']
assert rr['metadata']['native_exit_code'] == 100, rr['metadata']
node_ids = sorted(t['node_id'] for t in rr['test_results'])
assert node_ids == [
    'cargo_test_basic::cargo_test_basic$tests::test_add_passes',
    'cargo_test_basic::cargo_test_basic$tests::test_subtract_intentionally_fails',
    'cargo_test_basic::integration_test$test_add_via_integration',
], node_ids
print('Scenario A PASS')
PY
```

### Scenario B — `novetest run` (bare; workspace-type target — control case)

Same workspace as Scenario A (continuing the same `/tmp/cargo-sut` shell). Proves Fix A is scope-respecting: bare `novetest run` (workspace-classified) was never affected by the bug and stays correct.

**Reproducer**:

```sh
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run > /tmp/cargo-run-bare.json
echo "exit=$?"
```

**Expected**:
- **Exit code = 3** (same fixture, same 1-failure outcome).
- **`ok = true`**, **`errors[] == []`**, **`engine_name == "cargo-test"`**, **`status == "failed"`**, **same `summary_counts`** as Scenario A.
- **`data.memory_entry.run_record.target_expression == ""`** (empty string — the workspace-classified branch) AND **`data.memory_entry.run_record.target_type == "workspace"`**.

**Quick assertion script**:

```sh
python3 - <<'PY'
import json
e = json.load(open('/tmp/cargo-run-bare.json'))
rr = e['data']['memory_entry']['run_record']
assert e['ok'] is True
assert rr['target_expression'] == '', repr(rr['target_expression'])
assert rr['target_type'] == 'workspace', rr['target_type']
assert rr['summary_counts'] == {'passed': 2, 'failed': 1, 'skipped': 0, 'total': 3}
print('Scenario B PASS')
PY
```

**Critical**: Scenarios A + B must produce **identical `summary_counts` and `status`**. The two CLI invocations differ only in `target_expression` + `target_type`; the test execution outcome is the same because both resolve to "run the whole workspace" semantically. If they diverge, the directory-type carve-out broke scope-control somewhere.

### Scenario C — Defect 2 negative probe (heuristic no longer misfires) — optional

Defect 2's closure is covered structurally by the unit test (`test_cargo_adapter.py::test_no_tests_match_stderr_surfaces_distinct_message`). For a CLI-level cross-check Manual Test may probe via a deliberately mismatching nodeid filter:

```sh
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run 'nonexistent::module::test_nothing_here' > /tmp/cargo-run-nomatch.json 2>&1
echo "exit=$?"
cat /tmp/cargo-run-nomatch.json | python3 -m json.tool | head -40
```

**Expected** (loose):
- **No "likely build failure" string** anywhere in the envelope `errors[].message` field.
- If the error code is `adapter-unparseable-output`, the message text should mention "filter matched zero tests" with the offending target_expression + target_type cited literally (per handoff §"Fix shape declaration" + `cargo_adapter.py:352-388`).

If the orchestration short-circuits before reaching the heuristic, that's acceptable — Defect 2 is covered structurally by the unit test.

## Equipped-host gating to confirm before re-pass (per decision §2 + §4)

| Skip gate | Check | If skip → escalate? |
|---|---|---|
| `shutil.which("cargo")` | toolchain script sourced; cargo on PATH | Yes — verification requires running cargo |
| `shutil.which("cargo-nextest")` | nextest installed (>= 0.9.50) | Yes — nextest-primary contract |
| `shutil.which("cargo-llvm-cov")` | llvm-cov installed | Only for the coverage smoke (`test_cargo_coverage.py`); skip is acceptable but please log |

## Files merged (this slice)

| File | Lines | Change |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +82 / -1 | Fix A (directory-type carve-out, lines ~219-247) + Fix B (no-tests-match heuristic, lines ~352-388) + 2 new module-level constants |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +316 / 0 | 4 new tests: Fix A positive + Fix A scope guard + Fix B positive + Fix B scope guard |
| `tests/integration/run/test_cargo_basic.py` | +221 / 0 | 2 new CLI smokes (dot + bare control) + `cli_smoke_workspace` fixture + `_spawn_novetest` helper |
| `design/implementation-plan/engine-adapters.md` | +1 / 0 | §5 Edge cases — directory-typed-target paragraph (Fix A doc + sub-crate-selection deferral) |
| `WORKLOG.md` | +10 / 0 | Run team's new entry |
| `agent-comms/handoffs/run-team-2026-06-05-cargo-cli-orchestration-defect.md` | +393 / 0 | The handoff doc itself |

Total: **+1022 / -1** across 6 files. 0 new source files (source count stays 90; mypy strict checks 90 source files unchanged).

## DoD bullets (per task §6) — pre-merge gate evidence

| # | DoD bullet (paraphrased) | Evidence on merged commit `176e593` | ✓ |
|---|---|---|---|
| 1 | `cargo_adapter.py` directory-type carve-out implemented + unit-tested | `cargo_adapter.py:219-247` + `test_cargo_adapter.py::test_argv_omits_directory_target_expression` | ✓ |
| 2 | Build-failure heuristic detects `"Starting 0 tests across"` literal + emits non-"likely build failure" message, unit-tested | `cargo_adapter.py:352-388` + `test_cargo_adapter.py::test_no_tests_match_stderr_surfaces_distinct_message` | ✓ |
| 3 | `tests/integration/run/test_cargo_*.py` ≥1 CLI smoke for `novetest run .` asserting `returncode in (0, 3)` + envelope `engine_name == "cargo-test"` | `test_cargo_basic.py::test_cli_smoke_run_dot_emits_envelope` | ✓ |
| 4 | Second CLI smoke for bare `novetest run` case | `test_cargo_basic.py::test_cli_smoke_run_bare_emits_envelope` | ✓ |
| 5 | `engine-adapters.md §5` carries note about directory-type targets resolving to workspace-wide cargo execution (sub-crate deferred) | `design/implementation-plan/engine-adapters.md:396` (Edge cases section) | ✓ |
| 6 | Equipped-host full-suite gate green | This session: 1042 passed + 3 skipped + 0 failed | ✓ |
| 7 | `uv run mypy --strict src` clean | This session: Success no issues, 90 source files | ✓ |
| 8 | Handoff carries before/after envelope capture | `agent-comms/handoffs/run-team-2026-06-05-cargo-cli-orchestration-defect.md` §"Before / after envelope capture" | ✓ |

PM verifies + ticks on cycle close.

## Critical edge cases worth probing (Manual Test discretion)

1. **Verify `metadata.native_exit_code` ≠ 4 anymore in the dot case** — pre-fix exit-from-cargo-nextest was 4 (no tests matched); post-fix should be 100 (1 test failed). This is the smoking-gun evidence that Fix A redirected the filter-DSL append away from `.`.

2. **Verify Scenario B's `target_type == "workspace"` AND `target_expression == ""`** — these confirm the `target_resolver` empty-expression branch is the one running for bare `novetest run`, and the carve-out didn't accidentally promote dot-typed runs into workspace-typed runs (which would silently corrupt the audit trail).

3. **Cross-check the coverage smoke still works**: `uv run pytest -v tests/integration/run/test_cargo_coverage.py` — the lcov path is untouched by this slice, but the same `cargo_adapter.py` file is modified; passing here proves the cargo-llvm-cov path wasn't accidentally regressed.

4. **Pre-fix reproduction is no longer expected to be possible from `main`** — the original pre-fix capture (Manual Test's 2026-06-04 findings §"Evidence-B") is preserved in the handoff; the post-fix envelope captured this session is preserved at `/tmp/cargo-run-dot.json` for cross-reference.

## Conflict resolution notes

None. Run team's branch (`run-team/cargo-cli-orchestration-defect`) was based on `0ac3f4e` (the exact `main` tip at handoff time), and FF-merge applied cleanly:

```
Updating 0ac3f4e..176e593
Fast-forward
 6 files changed, 1022 insertions(+), 1 deletion(-)
```

No conflicts, no rebases, no force-push needed.

## Manual Test → PM finding template

When writing findings, please pin:
- This verification doc: `agent-comms/verifications/2026-06-05-cargo-cli-orchestration-defect.md`
- The merged commit: `176e593`
- Toolchain versions detected at run time (`cargo --version`, `cargo nextest --version`, `cargo llvm-cov --version`)
- Verdict + per-scenario PASS/FAIL/SKIPPED

Reminder per decision `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1`: a "passed" verdict requires the smoke-gate path to have actually executed (not been skip-gated away).
