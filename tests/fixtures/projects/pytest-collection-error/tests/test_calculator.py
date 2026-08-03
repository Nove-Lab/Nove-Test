"""Tests for ``pytest_collection_error.calculator``.

WARNING TO FUTURE MAINTAINERS: this module does NOT parse, on purpose.

The last assertion below is missing its closing parenthesis. That is the
fixture's entire contract — **do not fix it**. Python cannot compile the
module, so pytest raises during COLLECTION, collects zero tests and exits
non-zero without ever running `test_add_returns_sum` either. One unparsable
file takes the whole session down; that is what makes this shape dangerous
and worth a fixture.
"""

from pytest_collection_error.calculator import add, multiply


def test_add_returns_sum() -> None:
    assert add(2, 3) == 5


def test_multiply_returns_product() -> None:
    assert multiply(4, 5 == 20
