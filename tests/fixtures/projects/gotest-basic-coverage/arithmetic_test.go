package gotestbasiccoverage

import "testing"

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2, 3) = %d, want 5", got)
	}
}

func TestSubtract(t *testing.T) {
	if got := Subtract(10, 4); got != 6 {
		t.Errorf("Subtract(10, 4) = %d, want 6", got)
	}
}

// TestClassifyPositive covers the positive branch of Classify.
// The zero branch is covered by TestClassifyZero; the negative branch
// is INTENTIONALLY left uncovered — see README.md.
func TestClassifyPositive(t *testing.T) {
	if got := Classify(7); got != "positive" {
		t.Errorf(`Classify(7) = %q, want "positive"`, got)
	}
}

func TestClassifyZero(t *testing.T) {
	if got := Classify(0); got != "zero" {
		t.Errorf(`Classify(0) = %q, want "zero"`, got)
	}
}
