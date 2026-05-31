//! Arithmetic primitives. `add` and `subtract` are correct; `divide`
//! has a DELIBERATE bug (returns `a + b` instead of `a / b`).
//!
//! When the `test_divide` test in `lib.rs::tests` runs, the `assert_eq!`
//! macro fires a panic that includes `src/arithmetic.rs:<line>:<col>`
//! in its message (via the `assert_eq!` formatter's call-site). The
//! cargo adapter captures that panic into a per-test failure log; the
//! Localization engine's `sbfl_aggregate` parser extracts the file
//! reference and ranks `src/arithmetic.rs` top-1.

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub fn subtract(a: i32, b: i32) -> i32 {
    a - b
}

pub fn divide(a: i32, b: i32) -> i32 {
    // Deliberate bug — should be `a / b`. The `tests::test_divide` case
    // fails because of this line.
    a + b
}
