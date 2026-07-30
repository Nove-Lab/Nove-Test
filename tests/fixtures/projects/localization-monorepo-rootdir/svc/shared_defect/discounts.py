"""Percentage discounts. Correct — exercised by both failing and passing tests."""

from __future__ import annotations


def compute_discount(subtotal: int, percent: int) -> int:
    """The discount owed on ``subtotal`` at ``percent`` percent."""
    return subtotal * percent // 100
