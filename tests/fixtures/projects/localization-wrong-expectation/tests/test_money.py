from wrong_expectation.money import cents, dollars


def test_cents_of_one() -> None:
    assert cents(1.0) == 100


def test_cents_of_two_fifty() -> None:
    # SEEDED DEFECT: the EXPECTATION is wrong (2.50 dollars is 250 cents).
    # ``cents`` is correct; the mistake lives on this line.
    assert cents(2.50) == 25


def test_dollars_roundtrip() -> None:
    assert dollars(cents(1.25)) == 1.25
