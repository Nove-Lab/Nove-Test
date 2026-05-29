# cargo-test-basic-coverage

`cargo nextest`-based fixture project used by Nove Test to validate the
Run engine's **coverage-emission path** for the Rust ecosystem. Parallel
to `pytest-coverage`, `jest-basic-coverage`, and
`gotest-basic-coverage`.

## What this fixture validates

- The `cargo_adapter`, invoked with `collect_coverage=True`, must run
  `cargo llvm-cov nextest --lcov --output-path=<...>/coverage.lcov
  --no-fail-fast --workspace --message-format=libtest-json` and register
  the resulting `coverage.lcov` in `NativeResult.artifact_paths` under
  the key `coverage_lcov`. (The key is deliberately NOT `coverage_json`
  — that's reserved for Istanbul / coverage.py JSON — and not
  `coverage_profile` — that's reserved for go-test's cover-profile
  format. The future Coverage-team slice will dispatch on
  `engine_name == "cargo-test"` to parse LCOV.)
- `coverage.lcov`'s structure follows the LCOV format (`TN:` /
  `SF:<file>` / `DA:<line>,<count>` / `end_of_record`).
- The fixture has TWO source files (`src/arithmetic.rs`,
  `src/classifier.rs`) so the report carries interesting block structure
  across files.
- `classifier::classify`'s negative branch is **intentionally not
  covered** by any test, so `coverage.lcov` carries at least one
  uncovered region for it (a `DA:<line>,0` entry, plus the `else`
  branch in the BRDA records when branch coverage is enabled). Do NOT
  "fix" this by adding a negative-value test.

## Expected outcomes

| Test | Status |
| --- | --- |
| `cargo_test_basic_coverage::tests::test_add` | passed |
| `cargo_test_basic_coverage::tests::test_subtract` | passed |
| `cargo_test_basic_coverage::tests::test_classify_positive` | passed |
| `cargo_test_basic_coverage::tests::test_classify_zero` | passed |

(No failing tests — coverage gaps are the fixture's only signal.)

## Layout

```
cargo-test-basic-coverage/
├── Cargo.toml          # name = "cargo_test_basic_coverage"; edition = "2021"
├── src/
│   ├── lib.rs          # library root + 4 passing unit tests
│   ├── arithmetic.rs   # add, subtract — fully covered
│   └── classifier.rs   # classify — three branches, negative intentionally uncovered
├── README.md           # this file
└── .gitignore          # ignores `target/`
```

## Isolation

The fixture is self-contained — `Cargo.toml` declares no external
dependencies. `cargo llvm-cov nextest` requires the `llvm-tools-preview`
rustup component (per the Q3 decision's "Affected" section); absent
that, the adapter surfaces `engine-misconfigured` rather than running.
The fixture does NOT import any `novetest` code.
