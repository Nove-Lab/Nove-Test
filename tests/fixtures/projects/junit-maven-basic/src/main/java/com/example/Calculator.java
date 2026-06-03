package com.example;

/**
 * Minimal arithmetic SuT for the JUnit adapter fixture.
 *
 * The {@code subtract} method carries a deliberate one-line bug
 * (returns {@code a - b - 1} instead of {@code a - b}) so the
 * companion test class has a predictable failure to surface. All
 * other methods are correct. The pattern mirrors the existing
 * pytest-failing / cargo-test-basic / gotest-basic fixture shapes:
 * tiny, deterministic, and obviously buggy in exactly one place so
 * downstream Localization / Recommendation slices can demonstrate
 * suspect ranking on real data.
 */
public class Calculator {

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        // BUG (intentional): off-by-one. Should be `a - b`.
        return a - b - 1;
    }

    public int multiply(int a, int b) {
        return a * b;
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("divide by zero");
        }
        return a / b;
    }
}
