---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
slug: cargo-nextest-env-var-hotfix
created: 2026-05-31
verdict: passed
related:
  - agent-comms/verifications/2026-05-31-cargo-nextest-env-var-hotfix.md
  - agent-comms/findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md
  - agent-comms/handoffs/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
---

# Findings — cargo adapter `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` hotfix

## Verdict

**`passed`** — ship the hotfix as-is. Issue 1 from the 2026-05-30 cargo
E2E sweep is **fully closed**; trigger-(b) on
`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3 can be
ticked resolved during cycle close. No new issues found. No
recommendations to defer.

## Narrative for the CEO

A week ago we declared the cargo adapter "done" in source but couldn't
verify it end-to-end because no one on the dev team had a Rust toolchain
installed. We deferred the equipped-host sweep with two closure
triggers: (a) someone fires it up on an equipped CI cell, or (b) a
human installs Rust locally and runs it by hand.

I fired trigger-(b) on the previous cycle and the cargo adapter
**completely failed** end-to-end: every `novetest run` against a real
Rust workspace returned exit `4` ("adapter-unparseable-output") with
zero parsed test results. I diagnosed the root cause to a two-word
omission in the cargo adapter's env-var setup — `cargo-nextest 0.9.50+`
requires `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` to honor the
`--message-format=libtest-json` flag we depend on. The adapter passed
the flag but didn't set the env var, so nextest aborted with exit 95
("experimental feature not enabled") before writing a single event,
and our build-failure heuristic mislabeled that as adapter-unparseable.
Ship-blocker.

The Run team applied my 2-line fix exactly as proposed
(`env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"` inside
`_build_child_env()`), added a unit test pinning the env var to `"1"`,
and Main Branch merged. I ran the verification today on the same
equipped host I used for the sweep last week.

**Every single pre-fix symptom is now gone.** `novetest run` against
the real cargo fixture returns exit `3` (test-failures-detected — the
fixture has 1 intentional failing test) with `ok: true`, all 3 test
results parsed, the failing one carrying a populated `failure_reference`,
the native events file containing 10 real libtest-JSON events (was 0
pre-fix), and the raw nextest exit code stashed as `100` (libtest's
"1+ tests failed" code) — NOT `95` (which would mean the env var still
isn't reaching the child process).

The coverage path through `cargo llvm-cov nextest` works too: exit `0`,
4/4 tests pass, and the LCOV artifact contains valid records for 3
source files (the env var propagates transitively through cargo
llvm-cov to its internal nextest invocation). And as a bonus E2E check,
the Regression engine successfully composed a `regression_outcome`
across two consecutive cargo runs — proving the cargo run records flow
through Memory and feed downstream engines cleanly, not just produce a
pretty envelope at the CLI seam.

**Ship-blocker resolved.** Trigger-(b) closed. Cargo adapter v1 is
genuinely E2E-verified for the first time.

## What was tested

Merged tip: **`1745480`** (Main Branch's verification commit on top of
the fix commit `1e736cc`). The actual fix is at `1e736cc`:
`fix(run): set NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 in cargo adapter env`.

Host: equipped polyglot dev box —
- `cargo 1.96.0` ✓ (above supported floor)
- `cargo-nextest 0.9.137` ✓ (above 0.9.50 floor)
- `cargo-llvm-cov 0.8.7` ✓
- All from `scripts/dev-host-setup.md` §3 install path.

Scope I covered:
- **All 4 Main Branch verification scenarios** (init / run / events.jsonl / run --coverage).
- **All 6 critical edges** Main Branch listed (env var grep, coverage path verification, native_exit_code stamp, plus the three out-of-scope ones acknowledged).
- **Both gates green** on the merged tip: `pytest -q tests/unit tests/integration` and full cargo-related cell.
- **3 additional E2E probes I added** beyond the verification doc, listed under "Bonus probes" below.

## Commands run (verbatim) + observed output

### Pre-flight: env + fix presence

```
$ git rev-parse HEAD
174548065c485e9e7af7364badb1de9aea2c9255

$ grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" src/novetest/run/adapters/cargo_adapter.py
365:    - ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`` is the gate that
384:    env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"

$ . "$HOME/.cargo/env" && cargo --version && cargo nextest --version && cargo-llvm-cov --version
cargo 1.96.0 (30a34c682 2026-05-25)
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)
cargo-llvm-cov 0.8.7
```

### Gate

```
$ . "$HOME/.cargo/env" && uv run pytest -q tests/unit tests/integration
678 passed, 5 skipped in 30.06s
```

Numbers match Main Branch's claim exactly. The 5 remaining skips are
pre-existing Node/jest integration tests that need `npm`. Both cargo
integration tests **ran and passed** when cargo is on PATH (otherwise
they correctly skip with the `shutil.which("cargo")` guard).

Cargo cell in isolation:
```
$ uv run pytest -v tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py
2 passed in 0.91s
```

### Scenario 1 — `novetest run` (the core fix proof)

```
$ . "$HOME/.cargo/env" \
  && cd tests/manual-test-workspace/cargo-test-basic \
  && uv run --project /home/yjshin/dev/Nove-Test novetest init > /tmp/init.json
$ echo exit=$?
exit=0
```

`init` envelope: `ok=true`, `engine_readiness.state="ready"`,
`engine_readiness.engine="cargo-test"`, `engine_readiness.engine_version="1.96.0"`,
`store_state="ready"`.

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest run > /tmp/run.json
$ echo exit=$?
exit=3
```

Parsed envelope:

| Field | Pre-fix (2026-05-30 sweep findings) | Post-fix (this run) |
|---|---|---|
| Exit code | `4` | **`3`** ✅ |
| `ok` | `false` | **`true`** ✅ |
| `errors[0].code` | `"adapter-unparseable-output"` | **`[]`** ✅ |
| `status` | `failed` (spurious) | **`failed`** (genuine — 1 test failed) ✅ |
| `summary_counts.total` | `0` | **`3`** ✅ |
| `summary_counts.passed/failed/skipped` | `0 / 0 / 0` | **`2 / 1 / 0`** ✅ |
| `test_results` length | `0` | **`3`** ✅ |
| `metadata.native_exit_code` | `95` (env-var-missing) | **`100`** (libtest 1+ failed) ✅ |
| Failing test's `failure_reference` | n/a (no parse) | populated → `native/failures/cargo_test_basic__cargo_test_basic$tests__test_subtract_intentionally_fails.log` ✅ |

The three parsed tests, with outcomes:
- `cargo_test_basic::integration_test$test_add_via_integration` → **passed**
- `cargo_test_basic::cargo_test_basic$tests::test_add_passes` → **passed**
- `cargo_test_basic::cargo_test_basic$tests::test_subtract_intentionally_fails` → **failed**

### Scenario 2 — events.jsonl is non-empty

```
$ EVENTS=".novetest/run/artifacts/run_01KSYM6E0KTPZADWDHGZTZ6ZDM/native/events.jsonl"
$ wc -l "$EVENTS"
10 .novetest/run/artifacts/run_01KSYM6E0KTPZADWDHGZTZ6ZDM/native/events.jsonl

$ head -5 "$EVENTS"
{"type": "suite", "event": "started", "test_count": 1}
{"type": "test", "event": "started", "name": "cargo_test_basic::integration_test$test_add_via_integration"}
{"type": "test", "event": "ok", "name": "cargo_test_basic::integration_test$test_add_via_integration", "exec_time": 0.003124203}
{"type": "suite", "event": "ok", "passed": 1, "failed": 0, "ignored": 0, "measured": 0, "filtered_out": 0, "exec_time": 0.003124203}
{"type": "suite", "event": "started", "test_count": 2}
```

**This is the smoking-gun proof the env var is propagating.** Pre-fix
`wc -l` was `0` (file existed but was empty because nextest exited 95
before writing anything). Post-fix: 10 real libtest-JSON events, all
well-formed and parseable.

### Scenario 3 — `novetest run --coverage` (LCOV path)

```
$ cd tests/manual-test-workspace/cargo-test-basic-coverage
$ uv run --project /home/yjshin/dev/Nove-Test novetest init > /tmp/cov_init.json
$ echo init exit=$?
init exit=0

$ uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage > /tmp/cov_run.json
$ echo run --coverage exit=$?
run --coverage exit=0
```

Parsed envelope:
- `ok=true`, `errors=[]`, `warnings=[]`
- `engine="cargo-test 1.96.0"`, `status="passed"`
- `summary_counts={failed:0, passed:4, skipped:0, total:4}` ✅
- `metadata={native_exit_code:0}` (all tests passed)
- `artifact_paths` keys: **`['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']`**

LCOV body inspection:
```
$ LCOV=".novetest/run/artifacts/run_01KSYM78RX9CNVCHGQTBYVVBYK/native/coverage.lcov"
$ wc -l "$LCOV"
62
$ echo "SF: $(grep -c '^SF:' "$LCOV"); DA: $(grep -c '^DA:' "$LCOV"); end_of_record: $(grep -c '^end_of_record' "$LCOV")"
SF: 3; DA: 25; end_of_record: 3
```

Three `SF:` records (one per source file), 25 `DA:` lines, three
`end_of_record` markers — well-formed LCOV. First record:
```
SF:/home/yjshin/dev/Nove-Test/tests/manual-test-workspace/cargo-test-basic-coverage/src/arithmetic.rs
FN:4,_RNvNtCsaOzczmaDpth_25cargo_test_basic_coverage10arithmetic3add
...
DA:4,1
DA:5,1
DA:6,1
DA:8,1
DA:9,1
DA:10,1
```

Coverage path proves the env var propagates through
`cargo llvm-cov → nextest` transitively as expected.

### Scenario 4 — env var grep (already shown in pre-flight) ✅

## Critical edges — Main Branch's list

1. **`cargo nextest` < 0.9.50.** Out of scope (no older nextest on
   box; adapter's contract is "0.9.50+" per supported-engine matrix).
   My `cargo-nextest 0.9.137` is well above the floor. Noted.
2. **Coverage path propagation.** ✅ Verified in Scenario 3 — LCOV
   artifact present and well-formed, which is only possible if the
   env var reached the nextest subprocess that cargo-llvm-cov spawned.
3. **Empty-events still classifies as adapter-unparseable.** Out of
   scope (pre-existing heuristic, no source change to it). `novetest
   run` doesn't expose a `--filter` flag so I couldn't easily force a
   zero-test scenario without modifying the fixture; Main Branch
   confirmed the heuristic at `cargo_adapter.py:263` is unchanged.
   Noted.
4. **`metadata.native_exit_code` value.** ✅ Confirmed **`100`** in
   Scenario 1 — libtest's "1+ tests failed" code, NOT `95`. This is
   the cleanest single-number proof that the env var reached the
   child process; if it hadn't, we'd see 95.
5. **CI cells without cargo skip cleanly.** ✅ Verified — the skip
   guard `shutil.which("cargo") is None` fires correctly; cargo
   integration tests skip with `2 skipped in 0.12s` when cargo is not
   on PATH.
6. **Trigger-(b) closure on
   `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`.**
   ✅ All conditions met. See "Recommendations" below.

## Bonus probes I added

These go beyond the verification doc to stress-test the fix in
realistic E2E flows.

### Bonus 1 — failure log artifact has real content

```
$ FAILLOG=".novetest/run/artifacts/run_01KSYM6E0KTPZADWDHGZTZ6ZDM/native/failures/cargo_test_basic__cargo_test_basic\$tests__test_subtract_intentionally_fails.log"
$ ls -la "$FAILLOG"
-rw-r--r-- 1 yjshin yjshin 1578 May 31 18:00 ...
```

Content (1578 bytes): panic message + full `RUST_BACKTRACE=1`
backtrace. The `failure_reference` in the run record isn't a dead
pointer — it points to a real, well-formed panic log. Two further
details to note:
- `RUST_BACKTRACE=1` was honored (we got the full backtrace, not the
  truncated "run with `RUST_BACKTRACE=1` for a backtrace" message).
- The panic message is the fixture's intentional `"subtract(10, 4)
  should equal 5 (this test is intentionally failing)"` — confirms
  the failure log is per-test, not per-suite.

### Bonus 2 — second consecutive `novetest run` accumulates cleanly

I ran `novetest run` a second time in the same workspace. New run got
its own ULID and its own artifact tree:
```
$ find .novetest/memory/runs -name "record.json" | sort
.novetest/memory/runs/2026/05/31/run_01KSYM6E0KTPZADWDHGZTZ6ZDM/record.json
.novetest/memory/runs/2026/05/31/run_01KSYM8PXCSRWTA4TKRMYXSD05/record.json
```

Both run records persisted; no stale-state issues; second run's
`metadata.native_exit_code=100` and `summary_counts={failed:1,
passed:2, total:3}` again — fully idempotent across consecutive
invocations.

### Bonus 3 — Regression engine composes across two cargo runs

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest regression compare \
    --baseline-run-id 01KSYM6E0KTPZADWDHGZTZ6ZDM \
    --target-run-id   01KSYM8PXCSRWTA4TKRMYXSD05 > /tmp/reg.json
$ echo exit=$?
exit=0
```

`regression_outcome` envelope:
- `baseline_engine_name="cargo-test"`, `baseline_engine_version="1.96.0"`
- `target_engine_name="cargo-test"`, `target_engine_version="1.96.0"`
- `summary.regressed=0`, `still_failing=1`, `still_passing=2`,
  `total_baseline_tests=3`, `total_target_tests=3`
- 3 `test_transitions`, all categorized correctly:
  - 2× `still_passing` (matching node_ids across runs)
  - 1× `still_failing` (matching node_ids across runs, both
    `failure_reference`s present)
- `output_diff` with non-null SHA-256 hashes for baseline / target
  stdout + stderr.

**This is meaningful**: it proves the cargo run records aren't just
a pretty-printed envelope at the CLI seam — they're correctly
structured for the rest of the engine stack to compose against.
Memory persists them, Regression reads them back and produces a typed
`regression_outcome` with stable `node_id` matching across runs.

## Issues found

**None.** No regressions. No surprises. No deferred items.

## Recommendations for PM

1. **Cycle close.** This finding closes the 2026-05-30 reopened cargo
   trigger-(b). Suggested cycle summary heading:
   `comms: close 2026-05-31 cycle — cargo env-var hotfix (passed), trigger-(b) resolved`.

2. **Tick trigger-(b) on
   `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3 as
   resolved.** All three closure conditions are now satisfied:
   - (a) The 2026-05-30 cargo E2E sweep findings were filed (`18a0287`).
   - (b) Those findings had blocked on Issue 1; the hotfix at
     `1e736cc` resolves Issue 1.
   - (c) Re-execution against the post-fix tip (this verification)
     demonstrates the cargo path is fully working end-to-end on an
     equipped host. No remaining ship-blockers.

3. **Issue 2 (typed `metadata` slot on `NativeResult`) is the only
   open cargo-related design item.** Per
   `decisions/2026-05-30-native-result-metadata-slot.md` (option b
   chosen), this is a separate slice. I verified during this run that
   `metadata={'native_exit_code': 100}` is the current shape; the
   typed-slot migration is independent and can happen on the regular
   slice cadence — no urgency from this verification.

4. **No follow-up tasks needed for Manual Test.** The cargo adapter
   is genuinely E2E-verified. Future cargo work (e.g. nextest output
   parser hardening, polishing the build-failure heuristic at
   `cargo_adapter.py:263` for the zero-filter case) is well-separated
   from the env-var fix and doesn't require a manual re-verification
   of this slice.

5. **Trust the dev-host-setup doc.** The reproducible polyglot-host
   setup pinned at `scripts/dev-host-setup.md` (commit `56faa8b`)
   continues to work cleanly — same toolchain versions, same Rust
   workflow, no drift across the two trigger-(b) firings (sweep and
   hotfix verification). The setup doc is paying for itself.

## Artifacts retained

- `tests/manual-test-workspace/cargo-test-basic/.novetest/` — both
  run records (`01KSYM6E0KTPZADWDHGZTZ6ZDM`,
  `01KSYM8PXCSRWTA4TKRMYXSD05`) with their artifact trees
  (events.jsonl, stderr.log, stdout.log, failures/*.log). Not
  committed; scratch only.
- `tests/manual-test-workspace/cargo-test-basic-coverage/.novetest/`
  — one coverage run record (`01KSYM78RX9CNVCHGQTBYVVBYK`) with LCOV
  artifact. Not committed; scratch only.
- `/tmp/init.json`, `/tmp/run.json`, `/tmp/run2.json`,
  `/tmp/cov_init.json`, `/tmp/cov_run.json`, `/tmp/status.json`,
  `/tmp/reg.json` — captured envelopes; ephemeral.
