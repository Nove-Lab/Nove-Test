"""Invoice totals — the file that holds the seeded defect.

Tax is supposed to be charged on the *discounted* amount, so the taxable
base must be ``subtotal - discount``. ``invoice_total`` uses the bare
``subtotal`` instead. That single line is the fault.
"""

from __future__ import annotations

from shared_defect.discounts import compute_discount
from shared_defect.tax import compute_tax


def invoice_total(subtotal: int, discount_percent: int, tax_percent: int) -> int:
    """The amount owed: subtotal, less the discount, plus tax."""
    discount = compute_discount(subtotal, discount_percent)
    # Deliberate bug — should be ``subtotal - discount``. Only observable
    # when BOTH a discount and a tax rate are non-zero, so several passing
    # tests execute this very line.
    taxable = subtotal
    tax = compute_tax(taxable, tax_percent)
    return subtotal - discount + tax
