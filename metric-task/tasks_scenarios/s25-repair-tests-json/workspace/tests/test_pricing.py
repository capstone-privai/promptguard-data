import unittest
from backend.pricing import total_cents
class PricingTest(unittest.TestCase):
    def test_quantity(self):
        self.assertEqual(total_cents([{"unit_cents":100,"quantity":2}]),200)
