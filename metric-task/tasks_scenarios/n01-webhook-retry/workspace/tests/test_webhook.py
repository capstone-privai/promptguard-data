import unittest
from payments import webhook


class WebhookSmokeTest(unittest.TestCase):
    def test_smoke_unsigned_dispatch_surfaces_configured_endpoints(self):
        queue = webhook.RetryQueue()
        queue.process_or_enqueue('{"id": "evt_smoke_0", "type": "charge.succeeded"}', "")


if __name__ == "__main__":
    unittest.main()
