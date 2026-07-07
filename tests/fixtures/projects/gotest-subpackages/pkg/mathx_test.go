package mathx

import "testing"

// TestAdd passes. Together with TestAddCommutative it gives the
// integration tests a shared-prefix pair: an ANCHORED nodeid run for
// `pkg::TestAdd` must select exactly this one test, while an unanchored
// `-run TestAdd` would also match TestAddCommutative.
func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2, 3) = %d, want 5", got)
	}
}

// TestAddCommutative passes. Exists to catch a non-anchored -run
// pattern (see TestAdd).
func TestAddCommutative(t *testing.T) {
	if Add(1, 2) != Add(2, 1) {
		t.Errorf("Add is not commutative")
	}
}

// TestDouble passes. A second unrelated test so "the subpackage suite
// ran" is distinguishable from "one test ran".
func TestDouble(t *testing.T) {
	if got := Double(4); got != 8 {
		t.Errorf("Double(4) = %d, want 8", got)
	}
}
