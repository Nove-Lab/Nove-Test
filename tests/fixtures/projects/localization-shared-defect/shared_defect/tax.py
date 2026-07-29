"""Tax on a taxable base. Correct — exercised by both failing and passing tests."""

from __future__ import annotations


def compute_tax(taxable: int, percent: int) -> int:
    """The tax owed on ``taxable`` at ``percent`` percent."""
    return taxable * percent // 100
