//! Integration test binary for `cargo-test-basic`. `cargo` compiles
//! each file under `tests/` into its own test binary, so this file's
//! presence forces nextest to emit events for at least one extra
//! binary distinct from the unit-test binary in `src/lib.rs`. That
//! lets the adapter exercise its multi-binary handling path against a
//! real run.

use cargo_test_basic::add;

#[test]
fn test_add_via_integration() {
    assert_eq!(add(4, 5), 9);
}
