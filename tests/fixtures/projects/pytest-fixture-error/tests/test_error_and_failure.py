"""An ERROR and a genuine assertion FAILURE in the same suite.

WARNING TO FUTURE MAINTAINERS: both defects below are intentional —
``warehouse_connection`` raises, and ``test_reorder_quantity_wrong_expectation``
asserts a value the (correct) production code does not return. **Do not fix
either.**

This is the row of the blast-radius table that was already reported correctly
before the row-49 fix, because one genuine ``failed`` test is enough to make
the run non-green on its own. It is a fixture so that stays true: the mapping
fix must not change this shape's answer, only the shapes with no ``failed``
test in them.
"""

import pytest

from pytest_fixture_error.inventory import reorder_quantity


@pytest.fixture
def warehouse_connection() -> object:
    """Raises during setup, exactly like ``test_setup_error.py``'s."""

    raise RuntimeError("warehouse service unavailable")


def test_reorder_quantity_against_warehouse(warehouse_connection: object) -> None:
    # Errors: the fixture raises during setup.
    assert reorder_quantity(2, 10) == 8


def test_reorder_quantity_wrong_expectation() -> None:
    # Fails: `reorder_quantity(2, 10)` is 8, and this asserts 99. The
    # production code is right; the expectation is deliberately wrong, which
    # is how this fixture gets a `failed` outcome without a buggy module.
    assert reorder_quantity(2, 10) == 99
