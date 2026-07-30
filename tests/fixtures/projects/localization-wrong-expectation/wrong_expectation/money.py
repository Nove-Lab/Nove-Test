"""Correct production code. The bug in this fixture is in the TEST."""


def cents(amount: float) -> int:
    return round(amount * 100)


def dollars(c: int) -> float:
    return c / 100
