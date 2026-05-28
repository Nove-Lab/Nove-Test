// Package gotestbasic is the tiny library under test for the
// gotest-basic Nove Test fixture. Mirrors `pytest_basic.math_utils`
// and `jest-basic`'s `src/math.js` so the Go fixture stays narrow in
// scope: just enough surface for one passing test and one (intentionally)
// failing test.
package gotestbasic

func Add(a, b int) int {
	return a + b
}

func Subtract(a, b int) int {
	return a - b
}
