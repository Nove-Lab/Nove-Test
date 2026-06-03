package com.example;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Tests for {@link Calculator}. Designed so that one test predictably
 * fails ({@code testSubtract}), one is skipped ({@code testIgnored}),
 * and the remainder pass — giving the adapter all four outcome
 * categories (passed / failed / skipped / errored) to surface.
 */
class CalculatorTest {

    private final Calculator calc = new Calculator();

    @Test
    void testAdd() {
        assertEquals(5, calc.add(2, 3));
    }

    @Test
    void testSubtract() {
        // FAILS because Calculator.subtract has a deliberate off-by-one bug.
        assertEquals(1, calc.subtract(3, 2));
    }

    @Test
    void testMultiply() {
        assertEquals(6, calc.multiply(2, 3));
    }

    @Test
    void testDivide() {
        assertEquals(2, calc.divide(10, 5));
    }

    @Test
    void testDivideByZero() {
        assertThrows(ArithmeticException.class, () -> calc.divide(1, 0));
    }

    @Test
    @Disabled("smoke skipped test")
    void testIgnored() {
        // Body deliberately wrong; @Disabled prevents execution.
        assertEquals(0, 1);
    }
}
