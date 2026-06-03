package com.example;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Mirror of the Maven fixture's CalculatorTest. Same six tests,
 * same outcomes (4 passing, 1 failing, 1 skipped) so cross-fixture
 * assertions can pin identical shapes.
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
        assertEquals(0, 1);
    }
}
