"""Minor-unit helpers."""
from decimal import Decimal

EXPONENTS = {"KRW": 0, "JPY": 0, "USD": 2, "EUR": 2}


def is_known(currency):
    return currency in EXPONENTS


def to_decimal(minor, currency):
    """1250 USD cents -> Decimal('12.50'); 1250 KRW -> Decimal('1250')."""
    return Decimal(minor).scaleb(-EXPONENTS[currency])
