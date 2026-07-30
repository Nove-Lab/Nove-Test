"""Helper tests — both pass. They give ``compute_discount`` / ``compute_tax``
an extra passing observation each, so the defective ``invoice_total`` is the
strictly highest-scoring SOURCE symbol under Ochiai."""

from shared_defect.discounts import compute_discount
from shared_defect.tax import compute_tax


def test_discount_is_a_percentage_of_the_subtotal() -> None:
    assert compute_discount(10000, 10) == 1000


def test_tax_is_a_percentage_of_the_taxable_base() -> None:
    assert compute_tax(9000, 8) == 720
