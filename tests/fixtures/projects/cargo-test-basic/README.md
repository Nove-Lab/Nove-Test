# cargo-test-basic

Minimal `cargo nextest`-based fixture project used by Nove Test as software
under test. Parallel to `pytest-basic` (+ `pytest-failing`), `jest-basic`,
and `gotest-basic` for the Rust ecosystem — the engine-adapters plan
calls out failure-detail capture as the meaningful surface for Rust, so
this single fixture consolidates one passing test, one (intentionally)
failing test, and one integration-binary test.

## What this fixture validates

A `cargo nextest run --message-format=libtest-json` loop with the
`cargo-test` Native Engine:

- `probe_engine(<this dir>, "rust", "cargo-test")` should classify this
  workspace as `ready` once `cargo` + `cargo-nextest` are on `PATH` (no project-side
  dependency install needed; the crate has zero `[dependencies]`).
- `novetest run` should detect the failing case and emit a Run Record
  with `summary_counts.passed=2` and `summary_counts.failed=1` (one
  passing unit test + one failing unit test + one passing integration
  test = 3 leaf tests; 2 pass, 1 fails).
- The adapter must reassemble per-test `stdout` (the panic message +
  backtrace under `RUST_BACKTRACE=1`) into a single failure log for the
  failing test and register a `failure_reference` path.

## Layout

```
cargo-test-basic/
├── Cargo.toml                # name = "cargo_test_basic"; edition = "2021"; rust-version = "1.74"
├── src/
│   └── lib.rs                # add, subtract — the SuT; two unit tests in `mod tests`
├── tests/
│   └── integration_test.rs   # one passing integration-binary test
├── README.md                 # this file
└── .gitignore                # ignores `target/`
```

## Isolation

The fixture is self-contained — `Cargo.toml` declares no external
dependencies, so `cargo nextest run` builds against `std` only and does
not consult the registry. It does NOT import any `novetest` code. The
adapter spawns `cargo nextest` with `cwd=` this directory and
`CARGO_TERM_COLOR=never` so output is deterministic.

## The deliberate failure

`test_subtract_intentionally_fails` asserts that `subtract(10, 4) == 5`
(the actual result is `6`). This is the fixture's contract: the failure
path is what the integration test exercises end-to-end. Do NOT "fix" the
assertion.
