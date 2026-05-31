---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-05-31
slug: aggregate-fixture-redesign
related:
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - agent-comms/tasks/localization-team-2026-05-31-fallback-modes.md
  - agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - tests/fixtures/projects/localization-aggregate-only/
---

# Task: Localization aggregate-only fixture — redesign so panic site = bug site (Defect 2, Option A)

## TL;DR

Your 2026-05-31 fallback-modes slice (parked at worktree `a42ea87`)
was kicked back by Main Branch on Defect 2 — `localization-aggregate-only`
fixture has the test in `lib.rs` and the bug in `arithmetic.rs`, so
cargo's panic trace (which only mentions the assert site, not the
bug site without `RUST_BACKTRACE=1`) doesn't include `arithmetic.rs`.
Your `_derive_aggregate()` algorithm correctly lifts panic trace
files to `e_f`, so `arithmetic.rs` gets `e_f=0`, gets filtered out
in Step 5, and cannot top-rank — making `test_aggregate_mode_ranks_buggy_file_top`
assertion impossible.

CEO chose **Option A** (per
`questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
§Defect 2 fix paths): **move the `test_divide` test INSIDE
`arithmetic.rs`** so the assert site IS the bug site. The panic
trace then naturally mentions `arithmetic.rs:N` and the algorithm
ranks it top-1.

This is **purely a fixture redesign** — algorithm, parser, mode
selection logic, integration test code all stay byte-for-byte
unchanged. Your existing parked worktree `a42ea87` is preserved;
this slice continues on it.

## Dispatch ordering (BINDING)

This slice's handoff MUST wait until
`agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`
(Defect 1) has **merged into main**. Reason:

- Defect 1 (cargo-llvm-cov bails without LCOV on failing tests)
  blocks your aggregate-mode e2e regardless of your fixture fix.
  Without Defect 1's fix, no LCOV → no CoverageFactSet → e2e fails
  before reaching the file-ranking assertion.
- With Defect 1's fix + Defect 2 fix together, the e2e passes.

You CAN start fixture work immediately on `a42ea87` (the fixture
redesign is independent of Defect 1 source-side). But you CAN'T
open a clean handoff until Defect 1 lands in main AND you rebase.

**Concrete flow:**
1. Pull origin/main; confirm Run team's `run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail`
   has merged (look for `--ignore-run-fail` in cargo_adapter.py).
2. In your parked worktree at `a42ea87`, rebase onto the new main
   tip:
   ```sh
   cd /home/yjshin/dev/novetest-localization-fallback-modes
   git fetch origin main
   git rebase origin/main
   ```
3. Apply the fixture redesign per §"Scope" below.
4. Run full gate locally on equipped host. Both fixes together
   should make the aggregate-mode e2e PASS.
5. Open handoff at
   `agent-comms/handoffs/localization-team-2026-05-31-aggregate-fixture-redesign.md`.
6. Main Branch will re-attempt FF-merge; this time the gate passes.

## Scope (what this slice DOES)

### 1. Move `test_divide` into `arithmetic.rs`

Currently the fixture has:
- `tests/fixtures/projects/localization-aggregate-only/src/arithmetic.rs`
  with the intentional bug `pub fn divide(a, b) -> i32 { a + b }`
- `tests/fixtures/projects/localization-aggregate-only/src/lib.rs`
  with a `#[cfg(test)] mod tests { ... test_divide ... }` block
  that calls `divide(10, 2)` and asserts the result.

Redesign target (Option A from the question doc):

**`src/arithmetic.rs`** — append a `#[cfg(test)] mod tests` block
INSIDE the file:

```rust
// existing functions: add, subtract, divide(buggy), multiply, etc.
// (keep all the production code untouched)

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2), 5);  // panics HERE if divide is buggy
                                        // panic site: src/arithmetic.rs:<line>
    }

    // Optionally move/copy any other passing tests for divide-adjacent
    // functions here too — but the LOAD-BEARING change is test_divide
    // living IN arithmetic.rs so the panic trace mentions arithmetic.rs.
}
```

**`src/lib.rs`** — REMOVE the `test_divide` test from the existing
`#[cfg(test)] mod tests` block there. Keep all OTHER tests in
`lib.rs::tests` intact (the fixture probably has `test_add`,
`test_subtract`, etc. that pass — leave them where they are).

If `lib.rs::tests` becomes empty after `test_divide` removal, you
can drop the whole `mod tests` block in `lib.rs` — but if other
tests remain, keep the block with just those.

### 2. Validate the new panic trace shape

After redesign, the panic trace from `cargo nextest run`
(without `RUST_BACKTRACE=1`) should look like:

```
thread 'arithmetic::tests::test_divide' panicked at src/arithmetic.rs:<line>:<col>:
assertion `left == right` failed
  left: 12
 right: 5
```

The crucial differences from the pre-redesign trace:
- Thread name now contains `arithmetic::tests::` not `tests::`
- Panic site is `src/arithmetic.rs:<N>` not `src/lib.rs:<N>`

The Localization `failure_proximity` cargo regex
(`panicked at (\S+\.rs):(\d+):(\d+)`) will extract
`("src/arithmetic.rs", <line>)` → `e_f["src/arithmetic.rs"] = 1`
→ Ochiai > 0 → not filtered out → top-rankable.

### 3. Verify the e2e test passes

The existing test
`tests/integration/localization/test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top`
should now pass without code changes. The assertion is:

```python
assert top.code_location.file.endswith("arithmetic.rs")
```

After Defect 1 + Defect 2 fixes:
- Defect 1: cargo-llvm-cov writes LCOV → CoverageFactSet built
- Defect 2: panic trace mentions arithmetic.rs → `e_f["src/arithmetic.rs"]=1`
  → arithmetic.rs ranks top-1
- Assertion: `top.code_location.file == "src/arithmetic.rs"` → endswith check holds

### 4. Re-run full gate

After fixture redesign + rebase onto Run defect-1 fix in main,
run `uv run pytest -q tests/unit tests/integration` on the
equipped host. Expected:
- Previously failing `test_aggregate_mode_ranks_buggy_file_top`
  now PASSES.
- All other tests stay green.
- Net count should be the **original** slice's +41 with the e2e
  now PASSING instead of FAILING.

## Out of scope (do NOT touch)

- **Algorithm in `_derive_aggregate()`** — correct as-is. Defect
  was in the fixture, not the algorithm.
- **`parse_failure_log()` regexes** — the cargo regex is correct.
- **Other fixtures** — `localization-no-coverage`,
  `localization-branch` are unrelated to Defect 2.
- **Source files outside `src/novetest/`** — wait, you don't touch
  src at all in this slice. ONLY fixture files under
  `tests/fixtures/projects/localization-aggregate-only/`.
- **`tests/integration/localization/test_aggregate_mode_e2e.py`**
  — the test code stays unchanged. Only the fixture changes so
  the SAME test now passes.
- **Pre-existing handoff doc** (`a42ea87` includes one) — update
  to reflect the redesign + the rebase, OR add a 2nd handoff for
  this fix-up slice (your call; either is fine; just be clear
  which is the active one).
- **CEO's Option B and C** from the question doc — explicitly
  REJECTED in favor of Option A.

## Pre-flight checks (before opening handoff)

1. **Defect 1 IS in main** — verify before rebase:
   ```sh
   git fetch origin main
   git log origin/main --oneline | grep -i "ignore-run-fail\|cargo-llvm-cov"
   # Expected: commit visible referencing the swap
   ```
   If not found, WAIT — Run team's fix hasn't merged yet.

2. **Rebase clean**:
   ```sh
   cd /home/yjshin/dev/novetest-localization-fallback-modes
   git rebase origin/main
   # Expected: clean rebase, no conflicts (fixture vs Run team's
   # cargo_adapter.py changes are orthogonal)
   ```

3. **Equipped host + fixture redesigned**:
   ```sh
   . "$HOME/.cargo/env"
   cargo nextest --version  # 0.9.50+
   ```

4. **Empirical panic trace check** on the redesigned fixture:
   ```sh
   cp -r tests/fixtures/projects/localization-aggregate-only /tmp/lao-redesign
   cd /tmp/lao-redesign
   NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo nextest run \
     --no-fail-fast --workspace 2>&1 | grep "panicked at"
   # Expected post-redesign:
   #   panicked at src/arithmetic.rs:<line>:<col>:
   # NOT:
   #   panicked at src/lib.rs:<line>:<col>:
   ```
   The string `src/arithmetic.rs:` MUST appear in the stderr — that's
   the smoking-gun proof the redesign worked.

5. **e2e test passes** in isolation:
   ```sh
   uv run pytest -q tests/integration/localization/test_aggregate_mode_e2e.py -v
   # Expected: 1 passed, 0 failed
   ```

6. **Full gate green**:
   ```sh
   uv run pytest -q tests/unit tests/integration
   # Expected (equipped host, with both fixes): ~755 passed + ~5 skipped
   # (the previously-1-failed now passes; numbers may shift ±2 based
   # on Run team's exact test count)
   ```

7. **mypy strict clean**.

## DoD

- [ ] Defect 1 fix verified present in main; rebase clean.
- [ ] `src/arithmetic.rs` contains `#[cfg(test)] mod tests` block
      with `test_divide`.
- [ ] `src/lib.rs` no longer contains `test_divide` (other tests
      in `lib.rs::tests`, if any, preserved unchanged).
- [ ] Empirical panic trace mentions `src/arithmetic.rs:<line>`
      (verbatim in pre-flight evidence).
- [ ] `test_aggregate_mode_ranks_buggy_file_top` now PASSES.
- [ ] Full gate green; mypy strict clean.
- [ ] No source code changes outside the fixture.
- [ ] All other Localization tests from the original slice still
      pass (regression-pinning the +40 other new tests from 1A).

## Handoff format

`agent-comms/handoffs/localization-team-2026-05-31-aggregate-fixture-redesign.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Empirical panic trace evidence** — paste the verbatim
   `cargo nextest run` stderr line showing
   `panicked at src/arithmetic.rs:<line>:<col>`.
3. **e2e test PASSES** — paste the verbatim pytest output for
   `test_aggregate_mode_ranks_buggy_file_top`.
4. **Diff stats** — show that ONLY fixture files changed:
   ```sh
   git diff --stat origin/main..HEAD
   # Expected: 2 files (arithmetic.rs, lib.rs) under
   # tests/fixtures/projects/localization-aggregate-only/src/
   ```
5. **DoD §4 verification**: confirm the original 1A slice's
   Phase 4 §4 #2 DoD bullet ("Mode field populated correctly
   across all three fixtures") is **still closed** after this
   redesign — the redesign doesn't change WHICH mode the fixture
   triggers (still `sbfl_aggregate`), only ensures the e2e
   succeeds rather than fails.
6. **Open questions for PM** — any surprises during rebase or
   redesign.

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness:

1. Append `WORKLOG.md` entry per format (or amend the existing
   1A entry from `a42ea87` — your call; both are defensible).
2. Write the handoff.
3. Run `python3 tools/regen_comms_index.py`.
4. Stage all changes + run the full gate one last time before
   announcing ready-to-merge.

## Cross-references

- **Defect 2 analysis + Option A spec**:
  `agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
  §Defect 2 + §Suggested fix paths.
- **Defect 1 fix (BLOCKS this slice's handoff)**:
  `agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`.
- **Original 1A slice + parked worktree**:
  `agent-comms/tasks/localization-team-2026-05-31-fallback-modes.md`
  + worktree at `/home/yjshin/dev/novetest-localization-fallback-modes`
  @ `a42ea87`.
- **Envelope freeze (still in force; no amendment needed for this
  fix-up)**:
  `agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md`.
