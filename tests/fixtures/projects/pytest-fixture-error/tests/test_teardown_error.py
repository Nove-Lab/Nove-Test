"""TEARDOWN-phase error: the test body passes, then the fixture raises.

WARNING TO FUTURE MAINTAINERS: ``warehouse_session`` raises after its
``yield`` on purpose. That is the module's entire contract — **do not fix
it**.

pytest reports this module as "1 passed, 1 error" and exits ``1`` — the same
two-line summary as the setup-error module, but for a single test that both
passed and errored. pytest-json-report resolves the whole test item to the
non-passing category, so the per-test outcome is ``error`` and the report's
``summary`` block carries no ``passed`` key at all.
"""

from collections.abc import Iterator

import pytest

from pytest_fixture_error.inventory import is_in_stock


@pytest.fixture
def warehouse_session() -> Iterator[object]:
    """Yields fine, then fails to close — the teardown half of the shape."""

    yield object()
    raise RuntimeError("warehouse session close failed")


def test_is_in_stock_with_session(warehouse_session: object) -> None:
    # The body passes. The error arrives afterwards, during teardown, and it
    # is just as much "this run established nothing" as a setup error is.
    assert is_in_stock(1) is True
