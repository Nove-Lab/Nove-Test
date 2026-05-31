//! Three-branch classifier. Only the positive branch is exercised by a
//! test; the zero and negative branches are intentionally unreached so
//! the LCOV report has missing-region structure. This module is NOT
//! involved in the seeded fault — it exists so the SBFL ranking has
//! multiple covered files to discriminate against.

pub fn classify(v: i32) -> &'static str {
    if v > 0 {
        "positive"
    } else if v == 0 {
        "zero"
    } else {
        "negative"
    }
}
