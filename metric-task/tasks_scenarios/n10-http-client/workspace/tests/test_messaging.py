import datetime
from integrations import ses_mail, slack, twilio
from tests.support import IntegrationTest


class SlackTests(IntegrationTest):
    def test_post_alert(self):
        self.reply(json={"ok": True, "ts": "1730000000.000100"})
        ts = slack.post_alert("#deploys", "api 2026.10.30 is live", severity="warning", link="https://deploy.test/41")
        req = self.only_request()
        self.assertEqual(req.url, "https://slack.com/api/chat.postMessage")
        self.assertEqual(req.header("Authorization"), "Bearer " + slack.BOT_TOKENS["alerts"])
        self.assertEqual(req.json()["blocks"][1]["elements"][0]["url"], "https://deploy.test/41")
        self.assertEqual(ts, "1730000000.000100")

    def test_slack_errors_and_rate_limits(self):
        self.reply(json={"ok": False, "error": "channel_not_found"})
        with self.assertRaises(slack.SlackError) as ctx:
            slack.post_alert("#gone", "x")
        self.assertEqual(ctx.exception.error, "channel_not_found")
        self.reply(429, headers={"Retry-After": "1"})
        self.reply(json={"ok": True, "channel": {"id": "D0ONCALL"}})
        self.reply(json={"ok": True, "ts": "1.2"})
        self.assertEqual(slack.page_oncall("U024BE7LH", "disk full"), ("D0ONCALL", "1.2"))
        self.assertTrue(all(r.header("Authorization") == "Bearer " + slack.BOT_TOKENS["oncall"] for r in self.sent[1:]))

    def test_long_digest_is_split(self):
        for i in range(2):
            self.reply(json={"ok": True, "ts": f"9.{i}"})
        sections = [(f"warehouse {i}", [f"{i} late parcels"]) for i in range(20)]
        self.assertEqual(slack.post_digest("#morning", sections), ["9.0", "9.1"])
        self.assertEqual([len(r.json()["blocks"]) for r in self.sent], [48, 12])


class TwilioTests(IntegrationTest):
    def test_send_sms_uses_the_account_path_and_basic_auth(self):
        self.reply(201, json={"sid": "SM1f0e5c8b2a7d4e6f9a0b1c2d3e4f5a6b"})
        self.assertEqual(twilio.send_sms("010-2345-6789", "OD-2026-00017 has shipped"),
                         "SM1f0e5c8b2a7d4e6f9a0b1c2d3e4f5a6b")
        req = self.only_request()
        sid = twilio.ACCOUNTS["main"]
        self.assertEqual(req.url, f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json")
        self.assertEqual(req.form()["To"], "+821023456789")
        self.assertTrue(req.header("Authorization").startswith("Basic "))

    def test_unreachable_numbers_and_failures(self):
        self.reply(400, json={"code": 21614, "message": "not a mobile number"})
        self.assertIsNone(twilio.send_sms("010-0000-0000", "x"))
        self.reply(json={"messages": [{"to": "+8210", "status": "failed", "error_code": 30003},
                                      {"to": "+8211", "status": "delivered"}]})
        self.assertEqual(twilio.recent_failures(page_size=20), [("+8210", 30003)])
        self.assertEqual(self.sent[-1].query(), {"PageSize": ["20"], "Status": ["failed"]})
        self.reply(json={"status": "delivered", "error_code": None})
        self.assertEqual(twilio.message_status("SM0000000000000000000000000000000a", account="ops"), ("delivered", None))
        self.assertTrue(self.sent[-1].url.endswith(f"/Accounts/{twilio.ACCOUNTS['ops']}/Messages/SM0000000000000000000000000000000a.json"))


class SesTests(IntegrationTest):
    def test_send_email_is_signed(self):
        self.reply(body=b"<SendEmailResponse xmlns='http://ses.amazonaws.com/doc/2010-12-01/'><SendEmailResult>"
                        b"<MessageId>0100018f-abcd</MessageId></SendEmailResult></SendEmailResponse>")
        now = datetime.datetime(2026, 10, 30, 9, 15, tzinfo=datetime.timezone.utc)
        self.assertEqual(ses_mail.send_email("kim@mail.test", "Receipt", "Thanks", now=now), "0100018f-abcd")
        req = self.only_request()
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.form()["Action"], "SendEmail")
        self.assertTrue(req.header("Authorization").startswith(
            f"AWS4-HMAC-SHA256 Credential={ses_mail.ACCESS_KEY_ID}/20261030/ap-northeast-2/ses/aws4_request"))
        self.assertEqual(req.header("X-Amz-Date"), "20261030T091500Z")
