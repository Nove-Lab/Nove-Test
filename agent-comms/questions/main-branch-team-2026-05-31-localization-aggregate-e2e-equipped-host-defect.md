---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: open
created: 2026-05-31
slug: localization-aggregate-e2e-equipped-host-defect
related:
  - agent-comms/handoffs/localization-team-2026-05-31-fallback-modes.md
  - agent-comms/tasks/localization-team-2026-05-31-fallback-modes.md
  - src/novetest/run/adapters/cargo_adapter.py
  - tests/integration/localization/test_aggregate_mode_e2e.py
  - tests/fixtures/projects/localization-aggregate-only/
---

# Question: Localization fallback-modes slice — cargo aggregate e2e fails on equipped host (TWO defects)

## TL;DR

Main Branch attempted to FF-merge the Localization fallback-modes worktree
(`a42ea87`) onto `main` and ran the full gate. **One integration test failed**:
`tests/integration/localization/test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top`.
Gate result: **1 failed + 752 passed + 5 skipped** + mypy clean 72 src files.
Per charter ("If the gate fails, kick the slice back: write
`agent-comms/questions/` referencing the failing handoff. The originating
team fixes; you do not."), I rolled back the merge to `061e741` and
escalate here.

Two distinct defects in the Localization slice on equipped hosts (the
slice's handoff §"Real-cargo aggregate-mode e2e never ran on this host"
explicitly admitted this gap — they only ran on Rust-less and reported
749+9 with the e2e SKIPPED). Both reproduced empirically below.

The parallel Run slice (`worktree-run-team-build-failure-heuristic-polish`,
tip `58bb603`) is INDEPENDENT, passes its gate cleanly (714+5, mypy clean
71 src), and was merged solo. The Localization slice is parked pending
this resolution.

## Defect 1 — cargo-llvm-cov bails without writing LCOV when nextest exits non-zero

### Symptom

When the new `localization-aggregate-only` fixture's intentionally-failing
`test_divide` causes cargo nextest to exit 100, `cargo llvm-cov nextest`
does NOT write the `coverage.lcov` file. The Run adapter's existing
`unparseable-output` path (at `cargo_adapter.py:282`, the existing branch
— NOT the new misconfigured-environment branch from the Run polish slice)
then raises:

```
novetest.run.errors.AdapterInvocationError: cargo llvm-cov did not write
  /tmp/.../coverage.lcov; stderr tail: ... cargo nextest run
  --manifest-path ... --target-dir ... --no-fail-fast --workspace
  --message-format=libtest-json` (exit status: 100)
```

The `test_aggregate_mode_ranks_buggy_file_top` test pre-condition asserts
`isinstance(fact_set, CoverageFactSet)` after the run, which is unreachable
when the adapter raises before producing a CoverageFactSet.

### Reproduction (manual, no novetest)

```bash
# cp the fixture to /tmp (fresh build cache)
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/lao-probe
cd /tmp/lao-probe

# WITHOUT --ignore-run-fail: tests run, nextest exits 100, NO lcov file written
PATH=$HOME/.cargo/bin:$PATH NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 \
  cargo llvm-cov nextest --no-fail-fast --workspace \
  --message-format=libtest-json --lcov --output-path coverage.lcov
# stderr: "process didn't exit successfully: ... cargo nextest run ... (exit status: 100)"
# Result: NO coverage.lcov file produced.

# WITH --ignore-run-fail (REPLACES --no-fail-fast — they are mutually exclusive
# per `cargo llvm-cov nextest --help`): tests run, lcov IS written
PATH=$HOME/.cargo/bin:$PATH NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 \
  cargo llvm-cov nextest --ignore-run-fail --workspace \
  --message-format=libtest-json --lcov --output-path coverage.lcov
# stderr: "Finished report saved to coverage.lcov"
# Result: 1710-byte coverage.lcov produced.
```

`cargo llvm-cov --help` documents the flag verbatim:

```
--no-fail-fast       Run all tests regardless of failure
--ignore-run-fail    Run all tests regardless of failure and generate report
```

`--ignore-run-fail` internally implies `--no-fail-fast` (per the `cargo
llvm-cov 0.8.7` source and the empirical stderr trace which shows
`cargo nextest run --no-fail-fast ...` after the flag swap). The two
flags are mutually exclusive on the CLI; cargo-llvm-cov errors with
`--ignore-run-fail may not be used together with --no-fail-fast` if
both are passed.

### Suggested fix (Run team territory)

In `src/novetest/run/adapters/cargo_adapter.py`, in the cargo-llvm-cov
argv assembly path (currently passes `--no-fail-fast`), **swap
`--no-fail-fast` for `--ignore-run-fail`** when invoking
`cargo llvm-cov nextest`. This makes the coverage-collection path
robust to failing tests — which is the whole point of running coverage
on a failing run (you want to see what code the failing tests touched).

The non-coverage path (`cargo nextest run` without llvm-cov wrapper)
should KEEP `--no-fail-fast` — `--ignore-run-fail` is a cargo-llvm-cov
flag, not a cargo-nextest flag.

This is a tiny one-line change but it's a **Run team slice**, not
Main Branch territory. I cannot author it.

## Defect 2 — fixture's failing test panics at assertion site, not bug site

### Symptom

Even if Defect 1 is fixed (cargo-llvm-cov emits the lcov), the test's
final assertion `top.code_location.file.endswith("arithmetic.rs")` is
still unreachable with the current fixture design.

The fixture's seeded bug is in `src/arithmetic.rs::divide` (returns
`a + b` instead of `a / b`). The failing `test_divide` is defined in
`src/lib.rs::tests::test_divide`. The panic trace from
`cargo nextest run` reads:

```
thread 'tests::test_divide' (83146) panicked at src/lib.rs:35:9:
assertion `left == right` failed
  left: 12
 right: 5
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
```

The trace mentions ONLY `src/lib.rs:35` (the `assert_eq!` site) — it
does NOT mention `arithmetic.rs` anywhere. Without `RUST_BACKTRACE=1`
in the child env, the panic frame is just the assertion site.

The aggregate-mode algorithm (verified by reading
`src/novetest/localization/derive.py::_derive_aggregate` lines 327-498
in the slice's worktree) uses the failure log's parsed `(file, line)`
tuples to populate `e_f`:

```python
for tr in record.test_results:
    if tr.outcome not in _FAILED_OUTCOMES: continue
    failure_text = resolve_failure_text(...)
    tuples = parse_failure_log(record.engine_name, failure_text)
    for file_path, line in tuples:
        file_to_failed_tests[file_path].add(tr.node_id)
        file_to_evidence_lines[file_path].add(line)
# ...
ef_array[j] = len(file_to_failed_tests.get(file_path, set()))
# Step 5 (line 486): drop non-positive-score candidates
candidates = [c for c in candidates if c[1][formula] > 0]
```

Applied to this fixture:
- `parse_failure_log("cargo-test", panic_trace)` extracts only
  `[("src/lib.rs", 35)]` (the only `<file>.rs:<line>` reference in the
  trace).
- `e_f["src/lib.rs"] = 1`, `e_f["src/arithmetic.rs"] = 0`,
  `e_f["src/classifier.rs"] = 0`.
- Step 5's filter drops `arithmetic.rs` and `classifier.rs` (Ochiai
  score = 0 for files with `e_f = 0`).
- Only `lib.rs` survives → top entry is `lib.rs`, NOT `arithmetic.rs`.

The test's assertion `top.code_location.file.endswith("arithmetic.rs")`
cannot succeed with this fixture.

### Why the handoff's "Mode B" synthetic envelope worked

The handoff §"Mode B" envelope was a SYNTHETIC test, not real cargo:
they hand-constructed `failure_reference="src/buggy.py:7: AssertionError"`
pointing at the bug site directly. The cargo path produces panic traces
that point to the ASSERT site, not the bug site. Two different test
inputs; the handoff's synthetic input doesn't validate the real cargo
case.

### Suggested fix paths (Localization team territory — choose ONE)

**Option A (preferred — fixture redesign)**: Inline the failing test
INSIDE `arithmetic.rs` so the assertion site IS the bug site.

```rust
// src/arithmetic.rs
pub fn divide(a: i32, b: i32) -> i32 { a + b }  // BUG (preserved)

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2), 5);  // panic site: src/arithmetic.rs:N
    }
}
```

This makes the panic trace naturally mention `arithmetic.rs:N` and the
test assertion becomes correct without algorithm changes.

**Option B (panic from inside the bug)**: Change the bug from
"returns wrong value" to "panics with a custom message" so the bug site
itself is in the panic trace.

```rust
pub fn divide(a: i32, b: i32) -> i32 {
    panic!("divide intentionally broken — see arithmetic.rs");
}
```

The panic site would then be `arithmetic.rs:N` directly. But this
changes the semantic — the test would still need to assert this panic
mode, and the localization signal becomes "the test that panics" rather
than "the test that fails an assertion".

**Option C (algorithm change)**: Enable `RUST_BACKTRACE=1` in the cargo
adapter's child env AND extend `parse_failure_log("cargo-test", ...)` to
extract call-stack frames (not just the top panic site). This is a
larger change, touches both Run and Localization, and is probably
out-of-scope for this slice.

The handoff's Open Q #1 ("Mode C absolute-path artifact") flagged a
related concern about pytest path resolution — but the cargo case here
is a different surface (stack-frame depth, not absolute-vs-relative
paths).

## Gate evidence

### Failed gate (immediately after `git merge --ff-only a42ea87`)

```
$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
... 1 failed, 752 passed, 5 skipped in 33.73s
FAILED tests/integration/localization/test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top
  - novetest.run.errors.AdapterInvocationError: cargo llvm-cov did not write
    /tmp/.../coverage.lcov; stderr tail: ... cargo nextest run ...
    --no-fail-fast --workspace --message-format=libtest-json` (exit status: 100)

$ uv run mypy
Success: no issues found in 72 source files
```

- 752 passed: includes Localization's +40 new tests (their 41st was the
  failing aggregate-e2e + a few new-skip transitions on equipped host).
- 5 skipped: the team's reported 9-skipped on Rust-less became 5 on
  equipped (cargo-toolchain-gated skips fired off).
- mypy: clean at 72 (baseline 71 + 1 new `failure_proximity.py`).

### Rolled back

```
$ git reset --hard 061e741
HEAD is now at 061e741 ...
```

### Empirical reproduction (with `lao-probe` fixture copy)

See Defect 1 §Reproduction above. Without `--ignore-run-fail`: no lcov
file written. With `--ignore-run-fail`: 1710-byte lcov produced.

### Run slice merged solo (independent, green)

```
$ git merge --ff-only worktree-run-team-build-failure-heuristic-polish
Updating 061e741..58bb603
$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
... 714 passed, 5 skipped in 30.77s
$ uv run mypy
Success: no issues found in 71 source files
```

## Why this wasn't caught pre-handoff

The slice's handoff explicitly admitted:

> "**Real-cargo aggregate-mode e2e never ran on this host**: the test
> is skip-guarded on cargo-toolchain presence. Manual Test on equipped
> hosts will validate the real-cargo path."

The team developed on a Rust-less host where the new e2e test SKIPPED.
They reported 749+9 (749 = 709 baseline + 40 new tests; 9 = 8 baseline
+ 1 new skip from the cargo aggregate e2e). They flagged the gap but
expected Manual Test (not Main Branch's gate) to surface it.

Per charter, **Main Branch's gate runs all integration tests on the
equipped host** before merge. The skip-guard only fires when toolchain
is absent; when toolchain IS present (this Main Branch host), the test
RUNS and FAILS.

The handoff also flagged this in Open Q #3:

> "**Real-cargo aggregate-mode e2e never ran on this host**: ... Suggest
> Manual Test verifies on the equipped host as part of this cycle's
> verification."

But by the time Manual Test would run, the slice would already be on
`main`. The bug would land before being caught. The gate's job is to
catch this BEFORE merge.

## Recommended path forward

1. **Block this cycle's Localization merge** until the originating team
   addresses both defects.
2. **Dispatch a Run team slice** to add `--ignore-run-fail` to the
   cargo-llvm-cov argv (~1-line src + ~1-line test). Independent of
   Localization. Could land in a separate cycle.
3. **Dispatch a Localization team follow-up** to either redesign the
   fixture (Option A above is cleanest) OR add a TODO + skip-guard on
   equipped hosts WITH explicit rationale (less ideal — kicks the can).
4. **Update the slice's task brief** to require equipped-host validation
   on the originating team's side (not deferred to Manual Test), at
   least for this kind of fixture-dependent integration test.

The Run polish slice (this cycle's parallel sibling) merged
independently — `main` is now at `58bb603`. Verification doc lists
that slice only.

## Open question for CEO (process)

Should Main Branch always block merges on equipped-host integration
test failures, OR should slices be allowed to ship with
known-skip-on-rust-less-but-untested-on-equipped tests when the team
flags the gap explicitly in the handoff? The current charter says
"both must be green before commit", which is unambiguous, but I want
to confirm this is the intended posture. If the answer is "always
block", consider adding equipped-host validation as a hard pre-flight
gate for any team whose slice touches Rust integration paths.

---

Filed by: novetest-main-branch-team
Date: 2026-05-31
