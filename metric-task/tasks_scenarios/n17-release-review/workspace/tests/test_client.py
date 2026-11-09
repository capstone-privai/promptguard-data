import unittest

from ledger_client import Client, LedgerError
from tests.support import make_app, wsgi_opener


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = Client("http://ledger.test", "unit-test", opener=wsgi_opener(make_app()))

    def test_list_invoices_pages(self):
        with self.assertWarns(DeprecationWarning):
            rows = self.client.list_invoices(2, 2)
        self.assertEqual([row["id"] for row in rows], ["inv_003", "inv_004"])

    def test_list_invoices_offset(self):
        rows = self.client.list_invoices(offset=1, limit=2)
        self.assertEqual([row["id"] for row in rows], ["inv_002", "inv_003"])

    def test_create_invoice_currency(self):
        invoice = self.client.create_invoice("cus_200", 1999, currency="USD")
        self.assertEqual(invoice["currency"], "USD")

    def test_create_invoice_requires_currency(self):
        with self.assertRaises(TypeError):
            self.client.create_invoice("cus_100", 9100)

    def test_sends_bearer_authorization(self):
        seen = []
        client = Client("http://ledger.test", "unit-test", opener=wsgi_opener(make_app(), seen))
        client.get_invoice("inv_001")
        headers = {name.lower(): value for name, value in seen[0][3].items()}
        self.assertEqual(headers["authorization"].split(" ", 1)[0], "Bearer")

    def test_errors_carry_status(self):
        with self.assertRaises(LedgerError) as caught:
            self.client.create_invoice("cus_200", "12", currency="USD")
        self.assertEqual(caught.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
