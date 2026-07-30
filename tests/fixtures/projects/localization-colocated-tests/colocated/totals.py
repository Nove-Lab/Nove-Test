"""Production code AND its tests, in one file — the co-located layout.

``pyproject.toml`` sets ``python_files = ["*.py"]``, so pytest collects the
two ``test_*`` functions below out of this production module. The defect
sits in ``invoice_total`` in the SAME file.
"""

from colocated.helpers import discount, tax


def invoice_total(subtotal: float, pct: float, rate: float) -> float:
    # SEEDED DEFECT: taxes the UNDISCOUNTED subtotal (should be
    # ``tax(subtotal - d, rate)``).
    d = discount(subtotal, pct)
    t = tax(subtotal, rate)
    return subtotal - d + t


def test_total_no_discount_no_tax() -> None:
    assert invoice_total(100, 0, 0) == 100


def test_total_discount_with_tax() -> None:
    assert round(invoice_total(100, 0.1, 0.1), 2) == 99.0
