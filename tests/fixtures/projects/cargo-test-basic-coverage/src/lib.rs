//! Library root for the `cargo-test-basic-coverage` Nove Test fixture.
//!
//! Splits the SuT into two modules (`arithmetic` + `classifier`) so the
//! LCOV report carries cross-file block structure. `classifier::classify`
//! has three branches; the negative branch is intentionally NOT covered
//! by any test, so `coverage.lcov` carries at least one uncovered region
//! (`DA:<line>,0`). See README.md for the fixture contract.

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

    /// Covers the zero branch of `classify`. The negative branch is
    /// INTENTIONALLY left uncovered — see README.md.
    #[test]
    fn test_classify_zero() {
        assert_eq!(classify(0), "zero");
    }
}
