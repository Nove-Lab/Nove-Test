// Package gotestsubpackages is the ROOT package of the
// gotest-subpackages fixture. The fixture's contract: this package has
// NO tests — every test lives in the ./pkg subpackage. Pre-RUN-01, a
// `novetest run .` compiled exactly this package, found zero tests,
// exited 0, and the run was reported "passed" (silent false green).
// Do NOT add a _test.go file here.
package gotestsubpackages

// Version exists only so the root package has compilable content.
const Version = "0.0.0"
