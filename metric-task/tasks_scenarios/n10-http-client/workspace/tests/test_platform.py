from integrations import exchange_rates, github, launchdarkly, mapbox
from tests.support import IntegrationTest


class GithubTests(IntegrationTest):
    def test_release_and_issue(self):
        self.reply(json={"tag_name": "v2026.10.30", "body": None})
        self.reply(201, json={"number": 412})
        self.assertEqual(github.latest_release("orderdesk/monorepo"), ("v2026.10.30", ""))
        self.assertEqual(github.open_issue("orderdesk/monorepo", "Follow-up: INC-88", "details"), 412)
        self.assertEqual(self.sent[0].url, "https://api.github.com/repos/orderdesk/monorepo/releases/latest")
        self.assertTrue(all(r.header("Authorization").startswith("token ") for r in self.sent))
        self.assertNotEqual(self.sent[0].header("Authorization"), self.sent[1].header("Authorization"))


class FlagTests(IntegrationTest):
    def test_flag_states_skip_archived(self):
        self.reply(json={"items": [{"key": "new-checkout", "environments": {"staging": {"on": True}}},
                                   {"key": "old-banner", "archived": True, "environments": {"staging": {"on": True}}}]})
        self.assertEqual(launchdarkly.flag_states("staging"), {"new-checkout": True})
        req = self.only_request()
        self.assertEqual(req.query(), {"env": ["staging"], "summary": ["true"]})


class GeocodeTests(IntegrationTest):
    def test_geocode(self):
        self.reply(json={"features": [{"place_name": "Seoul Station", "center": [126.9707, 37.5547]}]})
        self.assertEqual(mapbox.geocode("서울역"), [("Seoul Station", 126.9707, 37.5547)])
        req = self.only_request()
        self.assertTrue(req.url.startswith("https://api.mapbox.com/geocoding/v5/mapbox.places/%EC%84%9C"))
        self.assertIn("access_token", req.query())
        self.assertEqual(req.query()["types"], ["address,poi"])


class RatesTests(IntegrationTest):
    def test_latest_and_convert(self):
        self.reply(json={"rates": {"USD": 0.00072, "JPY": 0.1102}, "timestamp": 1730000000})
        rates, ts = exchange_rates.latest()
        self.assertEqual(ts, 1730000000)
        self.assertEqual((exchange_rates.convert(12900, "USD", rates), exchange_rates.convert(12900, "JPY", rates)),
                         (9.29, 1422))
        req = self.only_request()
        self.assertEqual(req.query(), {"base": ["KRW"], "symbols": ["USD,JPY"]})
        self.assertIsNotNone(req.header("X-Api-Key"))
