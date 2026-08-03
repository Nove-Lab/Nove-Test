"""SETUP-phase error: the fixture raises before the test body is entered.

WARNING TO FUTURE MAINTAINERS: ``warehouse_connection`` raises on purpose.
That is the module's entire contract — **do not fix it**.

pytest reports this module as "1 passed, 1 error" and exits ``1``. Note the
distinction that makes this shape dangerous: ``test_reorder_quantity_uses_
warehouse`` is *not* a failing test — its body never ran — so pytest classifies
it as an **error**, and a consumer counting only failures sees zero.
"""

import pytest

from pytest_fixture_error.inventory import is_in_stock, reorder_quantity


@pytest.fixture
def warehouse_connection() -> object:
    """Stand-in for the real-world shape this fixture reproduces.

    A missing environment variable, a database that is not up, an import
    inside a fixture that fails — all arrive here identically: the fixture
    raises during SETUP and every test depending on it errors.
    """

    raise RuntimeError("warehouse service unavailable")


def test_reorder_quantity_uses_warehouse(warehouse_connection: object) -> None:
    # Never runs: the fixture above raises during setup, so this test is
    # reported `error`, not `failed`, and this assertion is never evaluated.
    assert reorder_quantity(2, 10) == 8


def test_is_in_stock_needs_no_warehouse() -> None:
    # Passes. It is here to make the blast radius visible: a green test next
    # to an errored one is exactly what makes "0 failures" read as "green".
    assert is_in_stock(3) is True
