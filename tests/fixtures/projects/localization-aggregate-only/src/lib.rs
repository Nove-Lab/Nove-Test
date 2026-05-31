//! Library root for the `localization-aggregate-only` Nove Test fixture.
//!
//! Splits the SuT into two modules (`arithmetic` + `classifier`) so the
//! LCOV report carries cross-file block structure. `arithmetic::divide`
//! has a DELIBERATE bug (returns `a + b` instead of `a / b`); the
//! `test_divide` test fails, and its panic message references
//! `src/arithmetic.rs:<line>:<col>` — which the Localization engine's
//! `sbfl_aggregate` mode parses to lift that file's suspicion above
//! every other covered file.

pub mod arithmetic;
pub mod classifier;

#[cfg(test)]
mod tests {
    use super::arithmetic::{add, divide, subtract};
    use super::classifier::classify;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn test_subtract() {
        assert_eq!(subtract(10, 4), 6);
    }

    /// THIS TEST FAILS. The seeded bug in `arithmetic::divide` returns
    /// `a + b` instead of `a / b`; the assert fires with a panic
    /// referencing `src/arithmetic.rs:<line>:<col>`. Do NOT fix the
    /// bug — the fixture's contract is the bug.
    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2), 5);
    }

    /// Covers the positive branch of `classify`.
    #[test]
    fn test_classify_positive() {
        assert_eq!(classify(7), "positive");
    }
}
