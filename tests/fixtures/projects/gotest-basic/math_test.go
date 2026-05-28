package gotestbasic

import "testing"

// TestAdd is the passing baseline test. Mirrors `pytest-basic`'s
// `test_add` and `jest-basic`'s "add returns the sum" test.
func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2, 3) = %d, want 5", got)
	}
}

// TestSubtract intentionally fails. The fixture's contract: this test
// MUST fail so the adapter's failure-detail-capture path can be
// exercised against a real Go test run. Do NOT "fix" the assertion.
func TestSubtract(t *testing.T) {
	if got := Subtract(10, 4); got != 5 {
		t.Errorf("Subtract(10, 4) = %d, want 5 (this test is intentionally failing)", got)
	}
}

// TestAddSubtests exercises the `t.Run("subtest", ...)` path. The
// `Parent/Child` naming format is what the adapter's NDJSON
// reassembly logic uses to recognise subtests, so the fixture must
// emit at least one. Both subtests pass.
func TestAddSubtests(t *testing.T) {
	t.Run("zero_left", func(t *testing.T) {
		if got := Add(0, 7); got != 7 {
			t.Errorf("Add(0, 7) = %d, want 7", got)
		}
	})
	t.Run("commutative", func(t *testing.T) {
		if Add(1, 2) != Add(2, 1) {
			t.Errorf("Add is not commutative: Add(1, 2) != Add(2, 1)")
		}
	})
}
