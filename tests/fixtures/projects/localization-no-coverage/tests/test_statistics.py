"""Tests for the deliberately-buggy statistics helpers.

One test fails: ``test_average_of_empty_returns_zero``. Every other test
passes. The failure originates INSIDE the SuT (the buggy ``average``
function raises ``ZeroDivisionError``), so pytest's ``crash.path``
resolves to ``localization_no_coverage/statistics.py`` — which the
Localization engine's ``failure_proximity`` parser picks up and ranks
top-1.
"""

from localization_no_coverage.statistics import (
    average,
    maximum,
    total,
)


def test_sum_returns_total() -> None:
    assert total([1, 2, 3, 4]) == 10


def test_max_returns_largest() -> None:
    assert maximum([3, 7, 1, 4]) == 7


def test_average_of_empty_returns_zero() -> None:
    """This is the failing test — the SuT's ``average`` raises
    ``ZeroDivisionError`` on an empty list, so pytest's crash.path
    points to the SuT file."""
    assert average([]) == 0
