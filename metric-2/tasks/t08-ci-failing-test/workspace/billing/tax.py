from decimal import ROUND_HALF_UP, Decimal


def round_tax(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
