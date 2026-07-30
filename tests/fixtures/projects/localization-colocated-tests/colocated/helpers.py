"""Correct helpers. Called only from ``colocated/totals.py``."""


def discount(subtotal: float, pct: float) -> float:
    return subtotal * pct


def tax(base: float, rate: float) -> float:
    return base * rate
