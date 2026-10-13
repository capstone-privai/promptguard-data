from decimal import Decimal

from billing.tax import round_tax


def test_round_tax_two_places():
    assert round_tax(Decimal("1.234")) == Decimal("1.23")


def test_tax_rounding_half_even():
    assert round_tax(Decimal("10.005")) == Decimal("10.00")
