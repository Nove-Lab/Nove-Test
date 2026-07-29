"""Totals tests — three pass, two fail, all five execute the defective line."""

from shared_defect.totals import invoice_total


def test_total_no_discount_no_tax() -> None:
    assert invoice_total(3000, 0, 0) == 3000


def test_total_tax_only() -> None:
    assert invoice_total(5000, 0, 10) == 5500


def test_total_discount_only() -> None:
    assert invoice_total(8000, 25, 0) == 6000


def test_total_percentage_discount_with_tax() -> None:
    """Fails: taxable base should be 9000, the defect taxes the full 10000."""
    assert invoice_total(10000, 10, 8) == 9720


def test_total_larger_discount_with_tax() -> None:
    """Fails: taxable base should be 16000, the defect taxes the full 20000."""
    assert invoice_total(20000, 20, 5) == 16800
