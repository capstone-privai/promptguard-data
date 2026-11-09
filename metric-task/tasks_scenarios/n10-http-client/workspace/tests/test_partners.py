import datetime
import json
from pathlib import Path

from auth import signer
from integrations import audit_export, directory_sync, partner_ledger, s3_exports, webhook_relay
from tests.support import IntegrationTest

FIXTURES = Path(__file__).parent / "fixtures"


class LedgerTests(IntegrationTest):
    def test_settlement_is_signed_and_duplicates_reuse_the_receipt(self):
        self.reply(201, json={"receipt_id": "rcpt_81"})
        self.reply(409, json={"existing_receipt_id": "rcpt_81"})
        for _ in range(2):
            self.assertEqual(partner_ledger.post_settlement("B-1030", [("OD-1", 12900)], created=1730000000), "rcpt_81")
        req = self.sent[0]
        self.assertEqual(req.url, "https://ledger.partner.test/v2/settlements")
        self.assertIn('keyId="orderdesk-ledger-2026"', req.header("Signature"))
        self.assertEqual(req.header("Digest"), signer.digest_header(req.body))


class RelayTests(IntegrationTest):
    def test_forward_and_gone_topics(self):
        self.reply(202, json={"delivery_id": "dlv_9"})
        self.reply(410, json={})
        event = {"id": 501, "type": "shipment.updated", "order": "OD-2026-00017"}
        self.assertEqual(webhook_relay.forward(event, created=1730000000), "dlv_9")
        self.assertIsNone(webhook_relay.forward(event, created=1730000001))
        self.assertEqual(self.sent[0].url, "https://relay.orderdesk.test/hooks/shipment/updated")
        self.assertEqual(self.sent[0].header("X-Event-Id"), "501")


class AuditTests(IntegrationTest):
    def test_upload_sorts_events(self):
        self.reply(json={"stored_bytes": "64"})
        events = [{"at": "2026-10-30T10:00:00Z", "who": "kim"}, {"at": "2026-10-30T09:00:00Z", "who": "lee"}]
        self.assertEqual(audit_export.upload_day("2026-10-30", events, created=1730000000), 64)
        req = self.only_request()
        self.assertEqual((req.method, req.url), ("PUT", "https://audit-archive.partner.test/v1/days/2026-10-30.jsonl"))
        self.assertEqual([json.loads(line)["who"] for line in req.body.decode().splitlines()], ["lee", "kim"])
        self.assertIn('keyId="orderdesk-audit-2026q4"', req.header("Signature"))


class S3Tests(IntegrationTest):
    def test_export_rows(self):
        self.reply(headers={"ETag": '"9b2cf535f27731c974343645a3985328"'})
        now = datetime.datetime(2026, 10, 30, 1, 0, tzinfo=datetime.timezone.utc)
        etag = s3_exports.export_rows("2026-10-29", [{"order": "OD-1", "total": 12900}], now=now)
        self.assertEqual(etag, "9b2cf535f27731c974343645a3985328")
        req = self.only_request()
        self.assertEqual(req.url, s3_exports.BUCKET_URL + "/finance/2026/10/29/orders.csv")
        self.assertEqual(req.body, b"order,total\nOD-1,12900\n")
        self.assertIn(f"Credential={s3_exports.ACCESS_KEY_ID}/", req.header("Authorization"))


class DirectoryTests(IntegrationTest):
    def test_pages_are_followed_and_hashes_dropped(self):
        pages = json.loads((FIXTURES / "directory_export.json").read_text())
        for page in pages:
            self.reply(json=page)
        users = directory_sync.fetch_users("2026-10-01T00:00:00Z", page_size=2)
        self.assertEqual([u["email"] for u in users], [u["email"] for p in pages for u in p["users"]])
        self.assertFalse(any("password_hash" in u for u in users))
        self.assertEqual([r.query()["page"] for r in self.sent], [["1"], ["2"]])
