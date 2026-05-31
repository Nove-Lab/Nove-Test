---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-31
slug: cargo-llvm-cov-ignore-run-fail
related:
  - agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Handoff: cargo adapter — swap `--no-fail-fast` for `--ignore-run-fail` on `cargo llvm-cov nextest`

## TL;DR

Closes Defect 1 from Main Branch's 2026-05-31 question. The cargo adapter's coverage-collection argv now uses `--ignore-run-fail` instead of `--no-fail-fast` so cargo-llvm-cov emits the LCOV report even when the inner cargo-nextest exits non-zero (any failing test). The non-coverage `cargo nextest run` argv is UNCHANGED (still uses `--no-fail-fast`; `--ignore-run-fail` is a cargo-llvm-cov-only flag). **2 src+tests files modified, +125/-3 lines, 0 new src files.** Pre-flight gates all green, including the load-bearing E2E `novetest run --coverage` proof against the `localization-aggregate-only` fixture. Ready to merge. Unblocks the parked Localization fallback-modes slice.

## Worktree

- **Path:** `/home/yjshin/dev/novetest-cargo-llvm-cov-ignore-run-fail`
- **Branch:** `worktree-run-team-cargo-llvm-cov-ignore-run-fail`
- **Base commit:** `e8fe8f16d435f027e47587937c081496812b6088` (main HEAD: `comms: queue two fix-up slices — cargo --ignore-run-fail + aggregate fixture redesign`)
- **Tip commit:** TBD (filled in after commit; see "Commit message" below)

## Files modified

| File | Lines | Nature |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +25 / −2 | One-line flag swap in the `if collect_coverage:` branch + 19-line docstring block explaining the swap rationale; small docstring extension on the non-coverage branch noting why it stays `--no-fail-fast`. |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +100 / −1 | Updated existing happy-path coverage test's `--no-fail-fast` assertion to `--ignore-run-fail` (mandatory; old assertion would fail post-fix); added new focused test `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail` pinning BOTH invariants in isolation. |
| `WORKLOG.md` | +8 / −0 | Top entry `2026-05-31 — phase3 / cargo-llvm-cov-ignore-run-fail` per format. |
| `agent-comms/handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md` | NEW | This file. |
| `agent-comms/INDEX.md` | regen (no diff) | `python3 tools/regen_comms_index.py` output. INDEX doesn't list handoffs; pending-task entry stays unchanged until PM moves it post-merge. |

**Source-file count: 71 → 71** (no new src files; the argv split was already cleanly two-branch in `run_cargo`, so no helper refactor needed).

## DoD bullets believed closed (PM verifies + ticks)

All 8 from task brief §DoD:

- [x] cargo-llvm-cov argv uses `--ignore-run-fail` instead of `--no-fail-fast` (`cargo_adapter.py:185`, post-swap).
- [x] Non-coverage cargo-nextest argv UNCHANGED — still uses `--no-fail-fast` (`cargo_adapter.py:212`). Verified by the regression-pin test `test_argv_uses_default_workspace_when_expression_empty`.
- [x] Docstring at the argv-assembly site documents the flag-swap rationale (19-line block above the coverage argv list cross-referencing the question doc).
- [x] Unit test asserts `--ignore-run-fail` IN cargo-llvm-cov argv AND `--no-fail-fast` NOT IN cargo-llvm-cov argv (new `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail`).
- [x] Non-coverage path's existing argv tests still pass (regression pinning) — 4-of-4 targeted regression tests green.
- [x] Empirical `lcov_written: YES` proof on `localization-aggregate-only` fixture (1710 bytes; verbatim shell output below).
- [x] `novetest run --coverage` E2E produces `has_coverage_facts: true` post-fix (verbatim envelope dump below).
- [x] Full pytest suite green (715 + 5 on equipped host); mypy strict clean (71 source files).

## Pre-flight check evidence

### #2 PRE-FIX reproduction on `localization-aggregate-only` fixture (`lcov written: NO`)

```
$ rm -rf /tmp/lao-probe && cp -r .../localization-aggregate-only /tmp/lao-probe
$ cd /tmp/lao-probe && rm -f coverage.lcov
$ NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
    --no-fail-fast --workspace --message-format=libtest-json \
    --lcov --output-path coverage.lcov
[...]
{"type":"test","event":"failed","name":"localization_aggregate_only::localization_aggregate_only$tests::test_divide",...}
{"type":"suite","event":"failed","passed":3,"failed":1,...}
     Summary [   0.007s] 4 tests run: 3 passed, 1 failed, 0 skipped
        FAIL [   0.005s] (4/4) localization_aggregate_only tests::test_divide
error: test run failed
error: process didn't exit successfully: `... cargo nextest run ... --no-fail-fast ... --message-format=libtest-json` (exit status: 100)

$ test -f coverage.lcov && echo YES || echo NO
NO
```

### #3 POST-FIX empirical proof (`lcov written: YES`)

```
$ cd /tmp/lao-probe && rm -f coverage.lcov
$ NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
    --ignore-run-fail --workspace --message-format=libtest-json \
    --lcov --output-path coverage.lcov
[...]
     Summary [   0.006s] 4 tests run: 3 passed, 1 failed, 0 skipped
        FAIL [   0.004s] (3/4) localization_aggregate_only tests::test_divide
error: test run failed
warning: process didn't exit successfully: `... cargo nextest run --no-fail-fast --manifest-path /tmp/lao-probe/Cargo.toml ... --message-format=libtest-json` (exit status: 100)

    Finished report saved to coverage.lcov

$ test -f coverage.lcov && echo YES || echo NO
YES (1710 bytes)
$ head -3 coverage.lcov
SF:/tmp/lao-probe/src/arithmetic.rs
FN:11,_RNvNtCskkRK6exwhoE_27localization_aggregate_only10arithmetic3add
FN:19,_RNvNtCskkRK6exwhoE_27localization_aggregate_only10arithmetic6divide
```

**Note:** the warning-line `cargo nextest run --no-fail-fast` in cargo-llvm-cov's stderr confirms `--ignore-run-fail` internally implies `--no-fail-fast` (cargo-llvm-cov passes it to the inner cargo-nextest invocation regardless). So the "run every test" semantic is preserved across the swap; the only behavior change is "always emit the LCOV report".

### #4 End-to-end `novetest run --coverage` evidence (the load-bearing acceptance bar)

```
$ rm -rf /tmp/lao-e2e && cp -r .../localization-aggregate-only /tmp/lao-e2e
$ cd /tmp/lao-e2e
$ uv run --project /home/yjshin/dev/novetest-cargo-llvm-cov-ignore-run-fail novetest init >/dev/null
$ echo "init exit=$?"
init exit=0
$ uv run --project /home/yjshin/dev/novetest-cargo-llvm-cov-ignore-run-fail novetest run --coverage > /tmp/lao-envelope.json 2>/dev/null
$ echo "run exit=$?"
run exit=3
```

```
=== TRANSPORT ===
exit code: 3 (test-failures-detected, expected — failing test by design)
ok: True
errors: []
warnings: []

=== COVERAGE OUTCOME (load-bearing) ===
coverage_outcome.kind: fact-set                    # ← was "unavailable" pre-fix
coverage_outcome.mapping_granularity: aggregate
coverage_outcome.summary: {
  covered_statements: 24,
  num_statements: 28,
  percent_covered: 85.71,
  covered_branches: 0, missing_branches: 0, num_branches: 0,
  missing_statements: 4, excluded_statements: 0
}

=== MEMORY ENTRY ===
has_coverage_facts: True                            # ← was False pre-fix
has_regression_facts: False
has_localization_findings: False

=== RUN RECORD ===
engine_name: cargo-test
ecosystem: rust
status: failed                                      # SuT's test_divide did fail; correct
summary_counts: {failed: 1, passed: 3, total: 4}
metadata: {native_exit_code: 0, nextest_version: '0.9.137'}
coverage_lcov artifact: run/artifacts/run_01KSZ6SG1RY6X0SBSAAQHM2QE9/native/coverage.lcov

=== ARTIFACT FILE ON DISK ===
/tmp/lao-e2e/.novetest/run/artifacts/run_01KSZ6SG1RY6X0SBSAAQHM2QE9/native/coverage.lcov
size: 1732 bytes
head:
  SF:/tmp/lao-e2e/src/arithmetic.rs
  FN:22,_RNvNtCskkRK6exwhoE_27localization_aggregate_only10arithmetic3add
  FN:30,_RNvNtCskkRK6exwhoE_27localization_aggregate_only10arithmetic6divide
```

Pre-fix this E2E would have failed with `adapter-unparseable-output` ("cargo llvm-cov did not write coverage.lcov") — exactly the Defect 1 symptom Main Branch reproduced.

### #5 Full gate green

```
$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
[...]
715 passed, 5 skipped in 32.09s
```

Baseline at `345b663` / current main `e8fe8f1` was **714 + 5** on equipped host per brief (`e8fe8f1` is comms-only commits on top, no src/tests delta). **Net: +1 = exactly the 1 new focused flag-swap test, zero regressions.** Rust-less baseline 676+7 is not exercised on this host (cargo is present); the +1 delta would still hold there since the new test is fully stubbed (no cargo invocation).

### #6 mypy strict clean

```
$ uv run mypy
Success: no issues found in 71 source files
```

Source-file count unchanged from baseline `e8fe8f1`. This slice adds zero src files.

### Targeted regression pin (non-coverage path's `--no-fail-fast` invariant preserved)

```
$ uv run pytest -q tests/unit/run/adapters/test_cargo_adapter.py::test_argv_uses_default_workspace_when_expression_empty \
                  ::test_collect_coverage_adds_flags_and_registers_artifact \
                  ::test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail \
                  ::test_collect_coverage_false_omits_flags_and_artifact -v
[...]
4 passed in 0.04s
```

The non-coverage path's existing `--no-fail-fast` assertion remains pinned; the coverage path's existing happy-path assertion is updated; the new focused flag-swap test is green; the no-coverage-no-llvm-cov path test is green.

## DoD implications

**None on `delivery-phasing.md`** — this is a bug fix to a landed adapter, not a phase-gated feature.

**Unblocks the parked Localization fallback-modes slice** (`worktree-localization-fallback-modes` @ `a42ea87`) — its aggregate-mode e2e test (`tests/integration/localization/test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top`) was failing at the adapter-side (Defect 1). That blocker is resolved. Defect 2 (fixture-redesign per CEO's Option A) is queued separately as `tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md` — independent file surface, can dispatch any time.

## Open question for PM (non-blocking)

**Argv split — was the refactor needed?** No. The `if collect_coverage: argv = [...]; else: argv = [...]` shape was already cleanly two-branch in `run_cargo`, so the swap was a true one-line change in the source body (plus a 19-line rationale docstring). A shared `_build_*_argv()` helper would have introduced an indirection for one-line-difference branches — over-engineering for the current two-branch case. If a future slice adds a third path (e.g. a nightly-coverage-only mode, or a `--no-coverage-but-collect-llvm-profiles` mode), the helper refactor becomes worth considering; until then, the two-branch shape is the minimum-coupling design.

**Was implementing the `+1 new test` brief expectation literal a good fit?** Mostly yes. I updated the existing happy-path coverage test's `--no-fail-fast` assertion (mandatory — it would have failed otherwise) AND added one new focused test that pins both invariants (positive + negative) in isolation. Net `+1 test`. The negative assertion (`"--no-fail-fast" not in captured_argv`) is the load-bearing one — without it, a future polish that re-added the old flag thinking it's complementary would silently regress (cargo-llvm-cov would error at runtime). Worth keeping the focused test separate from the happy-path test for that intent-signaling reason.

## Commit message (HEREDOC; used in commit)

```
fix(run): swap --no-fail-fast for --ignore-run-fail on cargo-llvm-cov path

Closes Defect 1 from main-branch-team-2026-05-31 question. cargo-llvm-cov
refuses to emit the LCOV report when inner cargo-nextest exits non-zero
under --no-fail-fast; --ignore-run-fail is cargo-llvm-cov's flag that
internally implies --no-fail-fast AND commits to writing the report
even when nextest fails. The two flags are mutually exclusive on
cargo-llvm-cov's CLI.

Real-world consequence pre-fix: any Rust developer with a failing
test gets `adapter-unparseable-output` from `novetest run --coverage` —
exactly the use case Localization needs. Unblocks the parked
Localization fallback-modes slice's aggregate-mode e2e.

Per tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md.
No new src files; no DoD checkbox implications.

- src/novetest/run/adapters/cargo_adapter.py (+25/-2): swap on
  coverage branch only + 19-line rationale docstring; non-coverage
  branch keeps --no-fail-fast (--ignore-run-fail is cargo-llvm-cov-
  only; plain cargo-nextest would error).
- tests/unit/run/adapters/test_cargo_adapter.py (+100/-1): updated
  existing happy-path coverage test's --no-fail-fast assertion
  (mandatory); added focused test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail
  pinning both invariants (positive + negative) in isolation.

Pre-flight evidence on equipped host:
- empirical pre-fix: lcov written: NO
- empirical post-fix: lcov written: YES (1710 bytes)
- E2E novetest run --coverage: exit 3, has_coverage_facts: true,
  coverage_outcome.kind: fact-set, LCOV 1732 bytes on disk
- mypy strict: 71 source files. Full gate: 715+5 (baseline 714+5).
- 4/4 targeted regression tests green (non-coverage --no-fail-fast
  invariant preserved).
```

## Worklog entry text (full 5-bullet entry lives at WORKLOG.md top)

See `WORKLOG.md` top entry `2026-05-31 — phase3 / cargo-llvm-cov-ignore-run-fail` for the full 5-bullet retrospective (Landed / Verified / Left open / Gotcha [5 sub-gotchas] / Next).
