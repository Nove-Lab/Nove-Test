// Package mathx is the tested subpackage of the gotest-subpackages
// fixture. Mirrors gotest-basic's math.go, but deliberately placed one
// directory below the module root so recursive target conversion
// (`.` → `./...`) is observable.
package mathx

func Add(a, b int) int {
	return a + b
}

func Double(a int) int {
	return a * 2
}
