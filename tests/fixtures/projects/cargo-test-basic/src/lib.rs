//! Minimal library under test for the `cargo-test-basic` Nove Test
//! fixture. Parallel to `pytest-basic` + `pytest-failing` and
//! `gotest-basic` — the surface stays as narrow as possible: just enough
//! for one passing unit test, one (intentionally) failing unit test, and
//! one integration test (in `tests/integration_test.rs`).

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub fn subtract(a: i32, b: i32) -> i32 {
    a - b
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `test_add_passes` is the passing baseline. Mirrors
    /// `pytest-basic::test_add` and `gotest-basic::TestAdd`.
    #[test]
    fn test_add_passes() {
        assert_eq!(add(2, 3), 5);
    }

    /// `test_subtract_intentionally_fails` is the contract failure case.
    /// The assertion is deliberately wrong (`subtract(10, 4)` is `6`, not
    /// `5`) so the adapter's failure-detail capture path runs against a
    /// real cargo-nextest invocation. Do NOT "fix" the assertion.
    #[test]
    fn test_subtract_intentionally_fails() {
        assert_eq!(
            subtract(10, 4),
            5,
            "subtract(10, 4) should equal 5 (this test is intentionally failing)"
        );
    }
}
