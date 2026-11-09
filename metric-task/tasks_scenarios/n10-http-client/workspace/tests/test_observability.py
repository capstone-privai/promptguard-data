from integrations import datadog, opsgenie, pagerduty, sentry, statuspage
from tests.support import IntegrationTest


class DatadogTests(IntegrationTest):
    def test_metrics_are_chunked_per_site(self):
        self.reply(202, json={})
        self.reply(202, json={})
        metrics = [(f"orders.queue.{i}", [(1730000000, i)], ["env:prod"], datadog.GAUGE) for i in range(150)]
        self.assertEqual(datadog.submit_metrics(metrics, site="eu1"), 2)
        self.assertEqual([len(r.json()["series"]) for r in self.sent], [100, 50])
        self.assertTrue(all(r.url == "https://api.datadoghq.eu/api/v2/series" for r in self.sent))
        self.assertEqual(self.sent[0].header("DD-API-KEY"), datadog.SITES["eu1"][1])

    def test_events_and_errors(self):
        self.reply(202, json={"event": {"id": 7719}})
        self.assertEqual(datadog.send_event("deploy", "x" * 5000, tags=["b", "a"]), 7719)
        payload = self.sent[-1].json()
        self.assertEqual((len(payload["text"]), payload["tags"]), (3996, ["a", "b"]))
        self.reply(403, json={"errors": ["Forbidden"]})
        with self.assertRaises(datadog.DatadogError):
            datadog.gauge("orders.open", 3, ts=1730000000)


class SentryTests(IntegrationTest):
    def test_create_and_finalize_release(self):
        self.reply(201, json={"version": "api@2026.10.30"})
        self.reply(400, body=b'{"version": ["Release with this version already exists."]}')
        self.reply(json={"dateReleased": "2026-10-30T10:00:00Z"})
        self.assertEqual(sentry.create_release("api@2026.10.30", ["a1b2c3"]), "api@2026.10.30")
        self.assertEqual(sentry.create_release("api@2026.10.30", ["a1b2c3"]), "api@2026.10.30")
        self.assertEqual(sentry.finalize_release("api@2026.10.30", released_at="2026-10-30T10:00:00Z"),
                         "2026-10-30T10:00:00Z")
        self.assertEqual(self.sent[0].url, "https://sentry.io/api/0/organizations/orderdesk/releases/")
        self.assertEqual(self.sent[2].method, "PUT")


class PagingTests(IntegrationTest):
    def test_pagerduty_trigger(self):
        self.reply(201, json={"incident": {"id": "Q2W3E4R5T6"}})
        self.assertEqual(pagerduty.trigger("payments 5xx", service_id="PX1Y2Z3", dedup_key="pay-5xx"), "Q2W3E4R5T6")
        req = self.only_request()
        self.assertEqual(req.url, "https://api.pagerduty.com/incidents")
        self.assertEqual(req.header("Authorization").split(" ", 1)[0], "Token")
        self.assertEqual(req.header("From"), pagerduty.SENDER)
        self.assertEqual(req.json()["incident"]["incident_key"], "pay-5xx")

    def test_statuspage_incident(self):
        self.reply(201, json={"id": "p31zjtct2jer"})
        self.assertEqual(statuspage.set_components({"cmp1": "partial_outage"}, notice="Checkout errors"), "p31zjtct2jer")
        req = self.only_request()
        self.assertTrue(req.url.endswith(f"/pages/{statuspage.PAGE_ID}/incidents"))
        self.assertTrue(req.header("Authorization").startswith("OAuth "))

    def test_opsgenie_alert(self):
        self.reply(202, json={"result": "Request will be processed", "requestId": "43a29c5c-3dbf"})
        self.assertEqual(opsgenie.create_alert("conveyor 3 stopped", alias="conv-3", priority="P2"), "43a29c5c-3dbf")
        req = self.only_request()
        self.assertEqual(req.url, "https://api.opsgenie.com/v2/alerts")
        self.assertTrue(req.header("Authorization").startswith("GenieKey "))
