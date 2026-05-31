# localization-aggregate-only

Cargo (Rust) fixture project used by Nove Test's Localization engine to
validate the **`sbfl_aggregate` mode** — file-level FLUCCS-style SBFL
ranking when coverage carries `mapping_granularity = "aggregate"`.

## What this fixture validates

- `cargo llvm-cov nextest --lcov` emits an LCOV file whose
  `CoverageFactSet.mapping_granularity` is `"aggregate"` (no per-test
  attribution — `cargo-llvm-cov` merges across the suite).
- The Localization engine routes to `sbfl_aggregate` for this coverage
  shape.
- The buggy file is ranked top-1 because the failing test's panic
  message points at the buggy source file via the cargo failure log.

## The deliberate gap

`src/arithmetic.rs` defines `divide(a, b)` which returns `a + b` instead
of `a / b`. The failing `arithmetic::tests::test_divide` test —
**co-located with the bug inside `arithmetic.rs`** so the assertion site
IS the bug site — panics with a message referencing
`src/arithmetic.rs:<line>:<col>`. The `failure_proximity` parser inside
`sbfl_aggregate` lifts that file's `ef` to 1 (one failing test mentions
the file), while every other covered file has `ef = 0` and is filtered
out by the score-zero filter.

**Why the test is co-located with the bug**: cargo's default panic
trace (without `RUST_BACKTRACE=1`) shows only the assertion frame, not
the call stack. If `test_divide` lived in `lib.rs::tests`, the panic
trace would only mention `src/lib.rs:<assert_line>` — `arithmetic.rs`
would never appear in the failure log, so the aggregate-mode algorithm
could not lift its suspicion. Option A from the 2026-05-31 equipped-host
defect Q&A (in `agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`)
selects this co-location strategy.

**Do not "fix" the bug** — the fixture's contract is the bug.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `tests::test_add` | passed |
| `tests::test_subtract` | passed |
| `arithmetic::tests::test_divide` | **failed** (panic at `src/arithmetic.rs:<line>:<col>`) |
| `tests::test_classify_positive` | passed |

## Layout

```
localization-aggregate-only/
├── Cargo.toml
├── src/
│   ├── lib.rs              # crate root + passing tests (test_add, test_subtract, test_classify_positive)
│   ├── arithmetic.rs       # add + subtract (correct) + divide (BUGGY) + failing `test_divide` co-located
│   └── classifier.rs       # classify (correct)
```

## Toolchain skip-guard

The end-to-end integration test against this fixture spawns
`cargo llvm-cov nextest --lcov`, so it skips cleanly when any of
`cargo`, `cargo-nextest`, or `cargo-llvm-cov` is not on `PATH`. This
matches the pattern at
`tests/integration/coverage/test_cargo_lcov_e2e.py` — the same trio of
binaries is required.

**Dependency on the Run-team `--ignore-run-fail` fix**: this fixture
also depends on Run team's
`tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md` slice
having landed in `main` — without that fix, `cargo llvm-cov nextest`
bails without writing the LCOV when nextest exits non-zero (which it
does because of the deliberate `test_divide` failure here), so the
Coverage engine gets no input to build a `CoverageFactSet` from. The
two fixes are independent in their territories (Run vs Localization
fixtures) but together unlock the e2e on equipped hosts.

## Isolation

Own `Cargo.toml`, no `novetest` import, no external crate dependencies.
Same hermetic discipline as the other fixture projects under
`tests/fixtures/projects/`.
