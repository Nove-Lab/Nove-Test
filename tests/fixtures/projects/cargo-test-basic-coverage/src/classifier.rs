//! Three-branch classifier. The negative branch is intentionally not
//! exercised by any test so `coverage.lcov` carries at least one
//! uncovered region.

pub fn classify(v: i32) -> &'static str {
    if v > 0 {
        "positive"
    } else if v == 0 {
        "zero"
    } else {
        // Fixture contract: this branch is intentionally not covered by
        // any test. Do NOT add a test that hits a negative value.
        "negative"
    }
}
