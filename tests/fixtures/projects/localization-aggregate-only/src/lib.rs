//! Library root for the `localization-aggregate-only` Nove Test fixture.
//!
//! Splits the SuT into two modules (`arithmetic` + `classifier`) so the
//! LCOV report carries cross-file block structure. `arithmetic::divide`
//! has a DELIBERATE bug (returns `a + b` instead of `a / b`).
//!
//! The **failing** `test_divide` test lives INSIDE `arithmetic.rs`
//! (Option A from the 2026-05-31 equipped-host defect Q&A) so the
//! `assert_eq!` panic site IS the bug site — the panic trace
//! references `src/arithmetic.rs:<line>:<col>` and the Localization
//! engine's `sbfl_aggregate` mode lifts that file's suspicion above
//! every other covered file.
//!
//! The PASSING tests below (`test_add`, `test_subtract`,
//! `test_classify_positive`) stay at the crate root because their
//! bug-site/assert-site alignment doesn't matter — they pass.

pub mod arithmetic;
pub mod classifier;

#[cfg(test)]
mod tests {
    use super::arithmetic::{add, subtract};
    use super::classifier::classify;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn test_subtract() {
        assert_eq!(subtract(10, 4), 6);
    }

    /// Covers the positive branch of `classify`.
    #[test]
    fn test_classify_positive() {
        assert_eq!(classify(7), "positive");
    }
}
