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
of `a / b`. The corresponding `tests::test_divide` test fails with a
panic referencing `src/arithmetic.rs:<line>:<col>` — the
`failure_proximity` parser inside `sbfl_aggregate` lifts that file's
`ef` to 1 (one failing test mentions the file), while every other
covered file has `ef = 0` and is filtered out by the score-zero filter.

**Do not "fix" the bug** — the fixture's contract is the bug.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `tests::test_add` | passed |
| `tests::test_subtract` | passed |
| `tests::test_divide` | **failed** (panic: `assertion left == right failed`) |
| `tests::test_classify_positive` | passed |

## Layout

```
localization-aggregate-only/
├── Cargo.toml
├── src/
│   ├── lib.rs              # crate root + the `tests` module
│   ├── arithmetic.rs       # add + subtract (correct) + divide (BUGGY)
│   └── classifier.rs       # classify (correct)
```

## Toolchain skip-guard

The end-to-end integration test against this fixture spawns
`cargo llvm-cov nextest --lcov`, so it skips cleanly when any of
`cargo`, `cargo-nextest`, or `cargo-llvm-cov` is not on `PATH`. This
matches the pattern at
`tests/integration/coverage/test_cargo_lcov_e2e.py` — the same trio of
binaries is required.

## Isolation

Own `Cargo.toml`, no `novetest` import, no external crate dependencies.
Same hermetic discipline as the other fixture projects under
`tests/fixtures/projects/`.
