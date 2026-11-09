import unittest

from ledger.logging import REDACTED_FIELDS, access_line


class AccessLineTests(unittest.TestCase):
    def test_credential_fields_keep_their_name_only(self):
        fields = dict.fromkeys(REDACTED_FIELDS, "visible")
        fields["status"] = "open"
        line = access_line("GET", "/v1/invoices", 200, 3, fields)
        self.assertNotIn("visible", line)
        self.assertIn("status=open", line)
        self.assertTrue(line.startswith("GET /v1/invoices 200 3ms authorization=[REDACTED:"))


if __name__ == "__main__":
    unittest.main()
