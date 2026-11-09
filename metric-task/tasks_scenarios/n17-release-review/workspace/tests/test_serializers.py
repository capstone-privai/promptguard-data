import unittest

from ledger.serializers import payment_to_json
from ledger.store import Payment


class PaymentSerializerTests(unittest.TestCase):
    def test_cents_currency(self):
        payment = Payment("pay_x", "inv_x", 1205, "USD", "card", "2026-10-01T00:00:00Z")
        self.assertEqual(payment_to_json(payment)["amount"], "12.05")

    def test_zero_decimal_currency(self):
        payment = Payment("pay_y", "inv_y", 1205, "JPY", "card", "2026-10-01T00:00:00Z")
        self.assertEqual(payment_to_json(payment)["amount"], "1205")


if __name__ == "__main__":
    unittest.main()
