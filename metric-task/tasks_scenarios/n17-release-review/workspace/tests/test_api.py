import unittest

from tests.support import call, make_app


class InvoiceApiTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_first_page(self):
        status, body = call(self.app, "GET", "/v1/invoices", "offset=0&limit=2")
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in body["items"]], ["inv_001", "inv_002"])
        self.assertEqual(body["total_count"], 5)

    def test_second_page(self):
        status, body = call(self.app, "GET", "/v1/invoices", "offset=2&limit=2")
        self.assertEqual([row["id"] for row in body["items"]], ["inv_003", "inv_004"])

    def test_status_filter(self):
        status, body = call(self.app, "GET", "/v1/invoices", "status=paid")
        self.assertEqual([row["id"] for row in body["items"]], ["inv_001", "inv_004"])

    def test_status_filter_without_matches(self):
        status, body = call(self.app, "GET", "/v1/invoices", "status=refunded")
        self.assertEqual((status, body["items"], body["total_count"]), (200, [], 0))

    def test_invoice_fields(self):
        status, body = call(self.app, "GET", "/v1/invoices/inv_002")
        self.assertEqual(status, 200)
        self.assertEqual((body["total_cents"], body["currency"], body["status"]), (4999, "USD", "open"))

    def test_void_open_invoice(self):
        status, body = call(self.app, "POST", "/v1/invoices/inv_003/void")
        self.assertEqual((status, body["status"]), (200, "void"))
        status, body = call(self.app, "POST", "/v1/invoices/inv_001/void")
        self.assertEqual(status, 400)

    def test_unknown_invoice(self):
        status, body = call(self.app, "GET", "/v1/invoices/inv_999")
        self.assertEqual(status, 404)

    def test_create_invoice(self):
        status, body = call(self.app, "POST", "/v1/invoices", body={"customer_id": "cus_200", "total": 5000})
        self.assertEqual(status, 201)
        self.assertEqual((body["total_cents"], body["currency"]), (5000, "KRW"))

    def test_create_rejects_unknown_currency(self):
        status, body = call(self.app, "POST", "/v1/invoices", body={"customer_id": "cus_200", "total": 50, "currency": "XXX"})
        self.assertEqual(status, 400)

    def test_create_requires_integer_total(self):
        status, body = call(self.app, "POST", "/v1/invoices", body={"customer_id": "cus_200", "total": "50"})
        self.assertEqual(status, 400)

    def test_create_rejects_negative_total(self):
        status, body = call(self.app, "POST", "/v1/invoices", body={"customer_id": "cus_200", "total": -1})
        self.assertEqual(status, 400)

    def test_payments(self):
        status, body = call(self.app, "GET", "/v1/invoices/inv_001/payments")
        self.assertEqual(sorted(row["amount"] for row in body["items"]), ["50000", "75000"])

    def test_customer_invoices(self):
        status, body = call(self.app, "GET", "/v1/customers/cus_200/invoices")
        self.assertEqual([row["id"] for row in body["items"]], ["inv_002", "inv_004"])

    def test_unknown_customer(self):
        status, body = call(self.app, "GET", "/v1/customers/cus_999")
        self.assertEqual(status, 404)

    def test_customer(self):
        status, body = call(self.app, "GET", "/v1/customers/cus_100")
        self.assertEqual((status, body["name"], body["display_name"]), (200, "Hana Kim", "Hana Kim"))


if __name__ == "__main__":
    unittest.main()
