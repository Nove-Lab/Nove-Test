//! Arithmetic primitives. `add` and `subtract` are correct; `divide`
//! has a DELIBERATE bug (returns `a + b` instead of `a / b`).
//!
//! The failing `test_divide` test lives INSIDE this file (Option A from
//! the 2026-05-31 equipped-host defect Q&A) so the `assert_eq!` panic
//! site IS the bug site — `panicked at src/arithmetic.rs:<line>:<col>`.
//! The cargo adapter captures that panic into a per-test failure log;
//! the Localization engine's `sbfl_aggregate` parser extracts the file
//! reference and lifts `src/arithmetic.rs`'s `e_f` to 1, which makes it
//! top-rank under Ochiai while every other covered file has `e_f = 0`
//! and is filtered out by the score-zero gate.
//!
//! **Why the test lives here, not in `lib.rs::tests`**: cargo's default
//! panic message (without `RUST_BACKTRACE=1`) shows only the assertion
//! frame, not the function call stack. If the test were in `lib.rs`,
//! the panic trace would only mention `src/lib.rs:<assert_line>` —
//! `arithmetic.rs` would never appear in the failure log, so the
//! aggregate-mode algorithm could not lift its suspicion. Co-locating
//! the test with the bug solves this without changing the algorithm or
//! requiring `RUST_BACKTRACE=1` in the child env.

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub fn subtract(a: i32, b: i32) -> i32 {
    a - b
}

pub fn divide(a: i32, b: i32) -> i32 {
    // Deliberate bug — should be `a / b`. The `tests::test_divide` case
    // below fails because of this line.
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;

    /// THIS TEST FAILS. The seeded bug in `divide` returns `a + b`
    /// instead of `a / b`; the `assert_eq!` fires with a panic
    /// referencing **this file** (`src/arithmetic.rs:<line>:<col>`)
    /// because the assertion site IS the bug site. Do NOT fix the bug
    /// — the fixture's contract is the bug.
    ///
    /// Localization's `sbfl_aggregate` parser extracts the file
    /// reference, sets `e_f["src/arithmetic.rs"] = 1`, and ranks the
    /// file top-1 (every other covered file has `e_f = 0` and is
    /// filtered out by the score-zero gate at `_derive_aggregate`
    /// Step 5).
    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2), 5);
    }
}
