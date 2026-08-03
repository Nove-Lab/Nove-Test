"""A perfectly correct module. This fixture's defects are NOT here.

It exists so the fixture is a realistic project rather than a bare erroring
test file: there is production code that would pass its tests, and the only
reason nothing is known about it is that the tests' fixtures blew up around
it.
"""

from __future__ import annotations


def reorder_quantity(on_hand: int, threshold: int) -> int:
    """Return how many units to reorder to reach ``threshold``."""
    return max(threshold - on_hand, 0)


def is_in_stock(on_hand: int) -> bool:
    """Return whether any units are on hand."""
    return on_hand > 0
