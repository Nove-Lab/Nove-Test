"""A perfectly correct module. The fixture's defect is NOT here.

This exists so the fixture is a realistic project rather than a bare broken
file: there is production code that would pass its tests, and the only reason
nothing is known about it is that the test module never parsed.
"""

from __future__ import annotations


def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return left + right


def multiply(left: int, right: int) -> int:
    """Return the product of two integers."""
    return left * right
