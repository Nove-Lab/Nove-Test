"""Tests for the deliberately-buggy calculator.

One test fails: ``test_divide_yields_quotient``. Every other test
passes. Combined with ``pytest --cov=. --cov-context=test``, the
resulting per-test ``CoverageFactSet`` lets the SBFL engine rank
``divide`` top-1 under Ochiai.
"""

from localization_branch.calculator import (
    Counter,
    add,
    divide,
    multiply,
    negate,
    subtract,
)


def test_add_sums_two_numbers() -> None:
    assert add(2, 3) == 5


def test_subtract_yields_difference() -> None:
    assert subtract(7, 2) == 5


def test_multiply_yields_product() -> None:
    assert multiply(4, 3) == 12


def test_divide_yields_quotient() -> None:
    """This is the failing test — exercises the deliberate bug in ``divide``."""
    assert divide(10, 2) == 5.0


def test_negate_flips_sign() -> None:
    assert negate(7) == -7


def test_counter_increments_monotonically() -> None:
    counter = Counter()
    assert counter.increment() == 1
    assert counter.increment() == 2
