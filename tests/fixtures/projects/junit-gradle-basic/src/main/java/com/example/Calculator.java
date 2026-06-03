package com.example;

/**
 * Mirror of the Maven fixture's Calculator with the same intentional
 * off-by-one bug in {@code subtract}. Mirrored verbatim across both
 * fixtures so the Maven + Gradle integration tests can assert the same
 * failure shape without per-fixture branching.
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
