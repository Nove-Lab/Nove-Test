// Package gotestbasiccoverage is the SuT for the gotest-basic-coverage
// fixture. Two source files (`classifier.go`, `arithmetic.go`) give
// `cover.out` interesting block structure: multiple files, multiple
// functions, multiple branches, with one branch deliberately
// uncovered so the report carries a concrete uncovered region.
package gotestbasiccoverage

// Classify returns "positive", "zero", or "negative" depending on the
// sign of v. The negative branch is intentionally not exercised by the
// test suite — fixture contract — so `cover.out` carries an uncovered
// region for it.
func Classify(v int) string {
	if v > 0 {
		return "positive"
	}
	if v == 0 {
		return "zero"
	}
	return "negative"
}
