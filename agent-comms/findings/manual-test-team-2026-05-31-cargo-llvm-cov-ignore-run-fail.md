---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-06-01
slug: cargo-llvm-cov-ignore-run-fail
verdict: passed
related:
  - agent-comms/verifications/2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
---

# Manual Test findings — cargo adapter `--no-fail-fast` → `--ignore-run-fail` (Defect 1 fix)

**Verdict**: **passed**.

The Run-team fix-up slice merged at `18fc224` ships a surgical
one-flag swap on the cargo adapter's coverage-collection argv: the
`cargo llvm-cov nextest` spawn now uses `--ignore-run-fail` instead
of `--no-fail-fast`. The two flags are mutually exclusive on
cargo-llvm-cov's CLI, and the pre-fix flag — though correct for the
plain `cargo nextest run` invocation — has a documented misbehavior
on the wrapper: it tells cargo-llvm-cov to surface the inner
nextest's non-zero exit (any failing test → exit 100) as the
wrapper's own failure, which suppresses LCOV report emission. As a
result, `novetest run --coverage` against any cargo workspace with a
failing test would raise `AdapterInvocationError(kind="unparseable-output")`
("cargo llvm-cov did not write coverage.lcov") and exit with envelope
code 4 (adapter-error) — completely blocking the Coverage engine
downstream.

Post-fix, the cargo-llvm-cov path uses `--ignore-run-fail`, which
internally implies `--no-fail-fast` AND commits to writing the LCOV
report regardless of test outcomes. The non-coverage path (plain
`cargo nextest run` invoked without the wrapper) still uses
`--no-fail-fast` because `--ignore-run-fail` is a
cargo-llvm-cov-specific flag — passing it to plain nextest would
error.

All 6 verification scenarios + 4 edge-case probes passed. No source
regressions. One doc-level observation on the verification request
itself worth flagging for next-cycle PM polish (recurring pattern
across the last two cycles).

## What was tested

A CEO-readable narrative:

1. **The all-passing happy path still works end-to-end.** A clean
   `novetest init` + `novetest run --coverage` against
   `cargo-test-basic-coverage` (4 passing tests, no failures)
   produces shell exit 0, `coverage_outcome.kind: "fact-set"`,
   96.0% statement coverage, all artifact keys present
   (`cargo_events_jsonl`, `coverage_lcov`, `stderr`, `stdout`),
   `metadata = {"native_exit_code": 0, "nextest_version": "0.9.137"}`.
   The flag swap does NOT change this path's behavior — both
   `--no-fail-fast` (pre-fix) and `--ignore-run-fail` (post-fix)
   produce identical results when no tests fail, because they only
   diverge on cargo-llvm-cov's behavior in response to inner
   nextest's non-zero exit.

2. **THE LOAD-BEARING PROOF — failing-test-with-coverage now works.**
   `novetest run --coverage` against `localization-aggregate-only`
   (3 passing tests + 1 by-design failing test, copied from the
   parked Localization worktree) produces:
   - Shell exit **3** (test-failures-detected) — pre-fix would have
     been **4** (adapter-error)
   - Envelope `ok: true`, `errors: []` — pre-fix would have carried
     `errors: [{code: "adapter-unparseable-output", ...}]`
   - `status: "failed"` (3 passed + 1 failed, per fixture design)
   - `has_coverage_facts: true` — **was `false` pre-fix**
   - `coverage_outcome.kind: "fact-set"` — **was `"unavailable"` pre-fix**
   - `coverage_outcome.mapping_granularity: "aggregate"`
   - `coverage_outcome.summary.percent_covered: 85.71` (24/28 statements)
   - `artifact_paths` includes `coverage_lcov`
   - **`coverage.lcov` file on disk: 1990 bytes** of valid LCOV
     content (SF, FN, FNDA records pointing at `arithmetic.rs`)
   This is the EXACT scenario the fix targets. Empirically proven.

3. **The non-coverage cargo path is unaffected.** `novetest run`
   (no `--coverage`) against `cargo-test-basic` (2 passing + 1
   failing) produces shell exit 3, `status: failed`, `metadata =
   {"native_exit_code": 100, ...}`, `artifact_paths` does NOT
   include `coverage_lcov`, `coverage_outcome: null`. The
   `native_exit_code: 100` (vs 0 in Scenario 2) is the empirical
   tell of the asymmetric flag handling: `--no-fail-fast` surfaces
   the inner nextest's exit 100 to the outer process; `--ignore-run-fail`
   (wrapper-only) swallows it to 0. Both are correct behaviors for
   their respective paths.

4. **The new focused unit test pins both invariants.**
   `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail`
   asserts `"--ignore-run-fail" in captured_argv` (positive, the
   swap target landed) AND `"--no-fail-fast" not in captured_argv`
   (negative, load-bearing against a future polish naively re-adding
   the old flag thinking they're complementary — they would error
   at runtime, and the assertion would fail). Plus `"llvm-cov" in
   captured_argv` as a paranoia guard against stub-routing bugs.

5. **The existing non-coverage argv tests still pin `--no-fail-fast`.**
   `test_argv_uses_default_workspace_when_expression_empty`,
   `test_collect_coverage_adds_flags_and_registers_artifact`,
   `test_collect_coverage_false_omits_flags_and_artifact` — all 3
   pass and lock the non-coverage branch's invariants.

6. **The 19-line docstring above the coverage argv list explains
   the swap rationale** in language an AI consumer or future
   maintainer can act on: the flags' mutual exclusivity, the
   internal `--no-fail-fast` implication of `--ignore-run-fail`,
   the empirical evidence pointer to the question doc, and the
   asymmetric constraint (plain cargo-nextest rejects `--ignore-run-fail`).

7. **mypy strict gate is clean at 71 source files** (baseline
   unchanged — pure flag swap, no new files).

8. **The full pytest gate is green at 715 + 5 skipped in 29.17s**
   (baseline 714 + 5 → +1 net = exactly the new focused argv-swap
   test, matching Main Branch's pre-merge gate evidence
   line-for-line).

## Commands run (verbatim) + observed output

### Pre-flight — full pytest gate + mypy

```
$ . "$HOME/.cargo/env" && uv run pytest -q tests/unit tests/integration
[...]
--------------------------- snapshot report summary ----------------------------
1 snapshot passed.
715 passed, 5 skipped in 29.17s

$ . "$HOME/.cargo/env" && uv run mypy
Success: no issues found in 71 source files
```

Result: ✅ **715 + 5** / **71 src** — matches Main Branch claim.

### Scenario 1 — Happy path: `novetest run --coverage` on `cargo-test-basic-coverage`

```
$ cd tests/manual-test-workspace/ignore-run-fail/cargo-test-basic-coverage
$ novetest init    # ok: true
$ novetest run --coverage
$ echo $?
0
```

Envelope projection:
| Path | Observed |
|---|---|
| `ok` | `true` ✓ |
| `errors` | `[]` ✓ |
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` ✓ |
| `data.memory_entry.run_record.status` | `"passed"` ✓ |
| `data.memory_entry.run_record.summary_counts` | `{passed: 4, failed: 0, skipped: 0, total: 4}` ✓ |
| `data.memory_entry.run_record.metadata` | `{native_exit_code: 0, nextest_version: "0.9.137"}` ✓ |
| `data.memory_entry.run_record.artifact_paths` keys | `[cargo_events_jsonl, coverage_lcov, stderr, stdout]` ✓ |
| `data.memory_entry.has_coverage_facts` | `true` ✓ |
| `data.coverage_outcome.kind` | `"fact-set"` ✓ |
| `data.coverage_outcome.summary.percent_covered` | `96.0` ✓ |

Result: ✅ **Happy path unaffected by the flag swap.**

### Scenario 2 — Failing-test-with-coverage on `localization-aggregate-only` (LOAD-BEARING)

```
$ cd tests/manual-test-workspace/ignore-run-fail/localization-aggregate-only
$ novetest init    # ok: true
$ novetest run --coverage
$ echo $?
3
```

Envelope projection:
| Path | Observed | Pre-fix would have been |
|---|---|---|
| Shell exit | `3` (test-failures-detected) | `4` (adapter-error) |
| `ok` | `true` | `false` |
| `errors` | `[]` | `[{code: "adapter-unparseable-output", ...}]` |
| `data.memory_entry.run_record.status` | `"failed"` | `"failed"` (status itself unchanged; but adapter would have raised before persisting) |
| `data.memory_entry.run_record.summary_counts` | `{passed: 3, failed: 1, skipped: 0, total: 4}` | — |
| `data.memory_entry.run_record.metadata` | `{native_exit_code: 0, nextest_version: "0.9.137"}` | — (native_exit_code=0 because `--ignore-run-fail` swallows inner exit) |
| `data.memory_entry.run_record.artifact_paths` keys | `[cargo_events_jsonl, coverage_lcov, stderr, stdout]` | — |
| **`data.memory_entry.has_coverage_facts`** | **`true`** | **`false`** |
| **`data.coverage_outcome.kind`** | **`"fact-set"`** | **`"unavailable"`** |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` | — |
| `data.coverage_outcome.summary.percent_covered` | `85.71` (24/28) | — |

Disk-level proof (the load-bearing artifact):
```
$ find .novetest -name 'coverage.lcov' -exec ls -l {} \;
-rw-r--r-- 1 yjshin yjshin 1990 Jun  1 00:08 .novetest/run/artifacts/run_01KSZ992VX1KDMKW5MFRWCD9VE/native/coverage.lcov
$ head -8 .../coverage.lcov
SF:.../src/arithmetic.rs
FN:22,_RNvN..._add
FN:30,_RNvN..._divide
FN:26,_RNvN..._subtract
FN:52,_RNvN..._test_divide
FNDA:1,_RNvN..._add
FNDA:1,_RNvN..._divide
FNDA:1,_RNvN..._subtract
```

Persisted `record.json`:
```
.novetest/memory/runs/2026/05/31/run_01KSZ992VX1KDMKW5MFRWCD9VE/record.json
  schema_version: 1
  engine_name: cargo-test
  status: failed
  metadata: {'native_exit_code': 0, 'nextest_version': '0.9.137'}
  summary_counts: {'passed': 3, 'failed': 1, 'skipped': 0, 'total': 4}
  artifact_paths keys: ['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']
```

Result: ✅ **THE SLICE'S VALUE PROPOSITION IS PROVEN END-TO-END.**
A failing cargo test no longer blocks coverage collection. The
Coverage engine receives 1990 bytes of valid LCOV, derives 4
function-level facts (3 production functions + 1 test function),
and reports 85.71% statement coverage. Memory persists the run with
both `status: failed` AND `artifact_paths.coverage_lcov` present.
`has_coverage_facts: true` flips correctly. This unblocks
Localization's Defect-2 fixture redesign (separate parked slice).

### Scenario 3 — Non-coverage path on `cargo-test-basic`

```
$ cd tests/manual-test-workspace/ignore-run-fail/cargo-test-basic
$ novetest init    # ok: true
$ novetest run
$ echo $?
3
```

Envelope projection:
| Path | Observed | Note |
|---|---|---|
| Shell exit | `3` | (Doc Obs 1: verification doc said "exit 0" — this fixture has by-design failing test) |
| `ok` | `true` ✓ | |
| `errors` | `[]` ✓ | |
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` ✓ | |
| `data.memory_entry.run_record.status` | `"failed"` | (by-design fixture; the slice doesn't touch behavior) |
| `data.memory_entry.run_record.summary_counts` | `{passed: 2, failed: 1, skipped: 0, total: 3}` | |
| `data.memory_entry.run_record.metadata` | `{native_exit_code: 100, nextest_version: "0.9.137"}` | ← Note: `native_exit_code: 100` (vs Scenario 2's `0`) is the empirical tell of the **asymmetric flag handling** — `--no-fail-fast` surfaces inner nextest's exit 100 to the outer process |
| `data.memory_entry.run_record.artifact_paths` keys | `[cargo_events_jsonl, stderr, stdout]` ✓ | NO `coverage_lcov` (no `--coverage` flag) |
| `data.coverage_outcome` | `null` ✓ | |

Result: ✅ **Non-coverage path unaffected.** The asymmetric
`native_exit_code` (100 here vs 0 in Scenario 2) is the smoking-gun
empirical proof that the flag swap is correctly confined to the
coverage branch.

### Scenario 4 — Focused argv-swap unit test

```
$ uv run pytest -q tests/unit/run/adapters/test_cargo_adapter.py::test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail -v
collected 1 item
tests/unit/run/adapters/test_cargo_adapter.py . [100%]
1 passed in 0.03s
```

Test source verified verbatim (lines 832-924). Stub captures the
cargo-llvm-cov spawn argv (routing version-probe argvs to canned
responses to keep the captured list clean), then asserts:
- `"--ignore-run-fail" in captured_argv` (positive)
- `"--no-fail-fast" not in captured_argv` (negative — **load-bearing**)
- `"llvm-cov" in captured_argv` (paranoia)

Result: ✅ **Both invariants pinned. The negative assertion is the
guard against a future re-introduction of the old mutually-exclusive
flag.**

### Scenario 5 — Targeted regression: argv invariants across branches

```
$ uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_argv_uses_default_workspace_when_expression_empty \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_adds_flags_and_registers_artifact \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_false_omits_flags_and_artifact -v
collected 3 items
tests/unit/run/adapters/test_cargo_adapter.py ... [100%]
3 passed in 0.03s
```

Result: ✅ **All 3 pin the cross-branch invariants** — non-coverage
default workspace argv (still `--no-fail-fast`), coverage argv shape
(now `--ignore-run-fail`), no-coverage path with no LCOV artifact.

### Scenario 6 — Docstring rationale (lines 160-220)

```python
# Coverage-mode and execution-mode are MUTUALLY EXCLUSIVE per
# `engine-adapters.md §5` + Q3 decision §"What this decision does
# NOT decide". `cargo-llvm-cov` wraps nextest internally; running
# both would produce conflicting LLVM-instrumented invocations.
argv: list[str]
if collect_coverage:
    # `cargo llvm-cov nextest` forwards nextest args; including
    # `--message-format=libtest-json` keeps per-test result fidelity
    # during coverage runs (unlike Go where coverage just augments
    # the same `-json` invocation, Rust's coverage path requires the
    # llvm-cov wrapper).
    #
    # `--ignore-run-fail` (NOT `--no-fail-fast`) is the load-bearing
    # flag here. The two are mutually exclusive on cargo-llvm-cov's
    # CLI; `--no-fail-fast` runs every test but tells cargo-llvm-cov
    # to surface nextest's non-zero exit (any failing test → exit
    # 100) as the wrapper's own failure, which suppresses the LCOV
    # report. `--ignore-run-fail` also runs every test (it implies
    # `--no-fail-fast` internally — verify via stderr trace: cargo-
    # llvm-cov passes `--no-fail-fast` to the inner cargo-nextest
    # invocation regardless), BUT also commits to emitting the LCOV
    # report even when nextest exits non-zero. That is exactly the
    # behavior we need: a Localization / Coverage consumer of a
    # failing run wants to see what code the failing tests touched.
    # Empirical proof in
    # `agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
    # §Defect 1: pre-fix `lcov written: NO`; post-fix `lcov written:
    # YES (1710 bytes)` on the `localization-aggregate-only`
    # fixture. Plain cargo-nextest (the non-coverage path below)
    # does NOT accept `--ignore-run-fail` — it is a cargo-llvm-cov-
    # only flag — so the swap is confined to this branch.
    argv = [
        cargo_path,
        "llvm-cov",
        "nextest",
        "--lcov",
        "--output-path",
        str(coverage_path),
        "--ignore-run-fail",
        "--workspace",
        "--message-format=libtest-json",
    ]
else:
    # `--no-fail-fast` keeps nextest running after the first failure
    # so the Run Record captures every test outcome — matches the
    # `pytest --maxfail=1` opt-out posture (default is no
    # short-circuit). The cargo-llvm-cov-specific
    # `--ignore-run-fail` (used in the coverage branch above) is
    # NOT applicable here: it is a wrapper-level flag that plain
    # cargo-nextest rejects.
    argv = [
        cargo_path,
        "nextest",
        "run",
        "--message-format=libtest-json",
        "--no-fail-fast",
        "--workspace",
    ]
```

Result: ✅ **Docstring matches the verification doc's expected
rationale verbatim.** Cross-references the question doc; pins the
mutual-exclusivity invariant; explains the asymmetry.

## Edge case probes

### Edge 1 — Both flags simultaneously would error

The new focused unit test's negative assertion (`"--no-fail-fast"
not in captured_argv`) is the guard. A future polish naively
adding `--no-fail-fast` back (e.g. "for consistency with the
non-coverage branch") would fail this assertion at unit-test time
— before any runtime error from cargo-llvm-cov rejecting the
mutually-exclusive combination.

Result: ✅ **Negative assertion enforced by the unit suite.**

### Edge 2 — Asymmetric path constraint (grep evidence)

```
$ grep -n "ignore-run-fail\|no-fail-fast" src/novetest/run/adapters/cargo_adapter.py
172:        # `--ignore-run-fail` (NOT `--no-fail-fast`) is the load-bearing
174:        # CLI; `--no-fail-fast` runs every test but tells cargo-llvm-cov
177:        # report. `--ignore-run-fail` also runs every test (it implies
178:        # `--no-fail-fast` internally — verify via stderr trace: cargo-
179:        # llvm-cov passes `--no-fail-fast` to the inner cargo-nextest
189:        # does NOT accept `--ignore-run-fail` — it is a cargo-llvm-cov-
198:            "--ignore-run-fail",           # COVERAGE branch only
203:        # `--no-fail-fast` keeps nextest running after the first failure
207:        # `--ignore-run-fail` (used in the coverage branch above) is
215:            "--no-fail-fast",              # NON-COVERAGE branch
```

Flag literal occurrences in the argv lists (not comments):
- Line 198 (`--ignore-run-fail`) is in the `if collect_coverage:` branch ONLY.
- Line 215 (`--no-fail-fast`) is in the `else:` (non-coverage) branch.
- Each branch's docstring cross-references the other (lines 178-179, 207) so a maintainer touching either branch sees the asymmetric constraint.

Result: ✅ **Asymmetry preserved; cross-references in place.**

### Edge 3 — Existing all-passing fixture unchanged + integration trio

```
$ uv run pytest -q tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py \
    tests/integration/coverage/test_cargo_lcov_e2e.py -v
collected 3 items
3 passed in 1.39s
```

The `test_cargo_coverage` integration test uses
`cargo-test-basic-coverage` (all-passing) — pre/post-fix, this test
passes. It does NOT exercise the failure-with-coverage path the fix
targets (which is why the bug remained latent until Localization's
e2e test surfaced it). Scenario 1 above is the explicit happy-path
confirmation.

Result: ✅ **All 3 integration tests pass; happy path preserved
across the slice.**

### Edge 4 — `coverage_lcov` artifact reliable for failing runs

Scenario 2's `data.memory_entry.run_record.artifact_paths` includes
`"coverage_lcov"` even with `status: "failed"`. Disk file is 1990
bytes of valid LCOV content (SF, FN, FNDA records well-formed).
Downstream consumers (Coverage engine `_derive_cargo_lcov`, `coverage
show`, `coverage diff`, `inspect`) no longer need to defensively
check for LCOV absence on failing cargo runs — the artifact contract
now holds across pass/fail outcomes.

Result: ✅ **Artifact-path contract is now reliable across pass/fail
outcomes for cargo coverage runs.**

## Issues found

**No source-level issues.** One recurring doc-level observation on
the verification request (not a slice defect).

### Obs 1 — Verification doc Scenario 3 expected `exit 0, all tests pass` for `cargo-test-basic`

The verification doc's Scenario 3 says:

> **Expected**: exit 0, `engine_name: cargo-test`, all tests pass

But `cargo-test-basic` is a by-design failing fixture (2 passing +
1 failing tests, native_exit_code 100, status failed). The actual
result is shell exit 3 (test-failures-detected), `status: "failed"`,
`summary_counts: {failed: 1, passed: 2, skipped: 0, total: 3}`.

This is the **same recurring doc nit pattern** Manual Test flagged
in:
- The 2026-05-31 typed-metadata-slot cycle's findings.
- The 2026-05-31 cargo build-failure heuristic polish cycle's
  findings (Obs 1, same fixture).

The substantive Scenario 3 invariants the verification doc actually
cares about — engine_name, NO `coverage_lcov` in `artifact_paths`,
`coverage_outcome: null`, AND the asymmetric `--no-fail-fast`
preservation on the non-coverage path — ARE all confirmed. The
"exit 0 / all tests pass" prediction appears to be a copy-paste
oversight from Scenario 1's all-passing fixture (`cargo-test-basic-coverage`).

**Not a slice defect.** The slice's correctness is independent of
fixture behavior.

Suggested doc fix:
```diff
-**Expected**: exit 0, `engine_name: cargo-test`, all tests pass,
-artifact_paths does NOT include `coverage_lcov`...
+**Expected**: exit 3 (`cargo-test-basic` has a by-design failing test
+— see prior cycle's WORKLOG entry on the typed-slot smoking-gun grep),
+`engine_name: cargo-test`, `status: "failed"`,
+`metadata.native_exit_code: 100` (note the contrast with Scenario 2's
+native_exit_code: 0 — that's the empirical tell of the asymmetric
+flag handling, since the non-coverage path keeps `--no-fail-fast`
+which surfaces inner nextest's exit 100 to the outer process),
+`artifact_paths` does NOT include `coverage_lcov`, `coverage_outcome: null`.
```

## Recommendations for PM

1. **Close the 2026-05-31 cargo-llvm-cov-ignore-run-fail slice as
   `passed`.** Source is clean; tests pass; mypy is green; gate
   matches Main Branch claim (715 + 5); all 6 scenarios + 4 edges
   verified, including the load-bearing empirical proof on the
   parked Loc fixture (`localization-aggregate-only`).

2. **Push of `18fc224` already authorized** per the Main Branch
   verification doc's Next §3 ("CEO's '확인하고 머지 푸시해'") and
   git log shows it's already on origin. No further authorization
   needed.

3. **Defect 3 (parser stdlib pollution) is now the load-bearing
   blocker for Localization's aggregate-e2e.** Per the question doc
   `main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md`,
   four fix options exist (A: drop catch-all regex, B: parser-output
   filter, C: algorithm coverage-files filter, D: combine A+C). PM
   recommendation per Main Branch is Option D. Whatever option PM
   picks, the Loc team can now build on top of this fix knowing
   the cargo adapter's `--ignore-run-fail` swap is solid — the
   Defect 1 unblocking is complete.

4. **Recurring verification-doc nit**: the "expected values" tables
   in the last three verification requests have all had at least
   one pinned-value typo (Scenario 5 glob path + field name in
   typed-metadata-slot cycle; Scenario 2 fixture confusion in
   build-failure-polish cycle; Scenario 3 fixture confusion in this
   cycle). Each is a doc nit, not a slice defect — but the recurrence
   suggests a Main Branch process gap. Suggested mitigation: have
   Main Branch dry-run each verification doc's exact command
   snippets against the freshly-merged tip BEFORE filing, catching
   expected-output mismatches at source. The merge gate already
   exercises the SAME commands; piping the actual envelope into the
   doc would close this loop. Low priority — Manual Test catches
   these every cycle without much friction — but recurring enough
   to mention.

5. **No `delivery-phasing.md` checkbox movement** — this is a bug
   fix to an already-landed adapter, not a phase-gated feature
   (per task brief + verification doc).

## Confirmation matrix

| Scenario | Subject | Verdict |
|---|---|---|
| Pre-flight | Full pytest gate (715 + 5) + mypy strict (71 src) | ✅ |
| 1  | `run --coverage` happy path on cargo-test-basic-coverage | ✅ |
| 2  | **Failing-test + coverage on localization-aggregate-only (THE VALUE PROP)** | ✅ |
| 2b | Disk-level LCOV bytes + persisted record.json | ✅ |
| 3  | Non-coverage path on cargo-test-basic | ✅ (source correct; doc nit per Obs 1) |
| 4  | Focused `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail` | ✅ |
| 5  | Targeted regression argv tests (×3) | ✅ |
| 6  | Docstring rationale (lines 160-220) | ✅ |
| E1 | Both flags simultaneously would error (negative assertion) | ✅ |
| E2 | Asymmetric path constraint (grep) | ✅ |
| E3 | Integration trio (basic + coverage + lcov-e2e) | ✅ |
| E4 | `coverage_lcov` reliable for failing runs | ✅ |

**Final verdict: passed.** The cargo adapter's coverage-collection
path now correctly emits the LCOV report regardless of inner test
outcomes. Defect 1 of the 2026-05-31 equipped-host gate failure is
closed. The fix unblocks downstream Coverage consumers (Localization
aggregate-mode, `coverage diff` across failing runs, `inspect` on
failing cargo runs).

---

Filed by: novetest-manual-test-team
Date: 2026-06-01
Cycle: 2026-05-31 fix-up cycle (cargo-llvm-cov-ignore-run-fail +
       aggregate-fixture-redesign) — Run slice verified passed;
       Loc parallel sibling parked AGAIN (Defect 3 surfaced)
