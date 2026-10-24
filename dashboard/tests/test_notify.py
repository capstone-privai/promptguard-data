"""Discord alerts, with the webhook faked (nothing is sent)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import notify  # noqa: E402

HOOK = "https://discord.com/api/webhooks/1/secret-token"


class NotifyTest(unittest.TestCase):
    def sent(self, text, **kwargs):
        with patch("pipeline.notify.urlopen") as urlopen:
            notify.send(HOOK, text, **kwargs)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, HOOK)
        self.assertEqual(request.get_header("User-agent"), "promptguard-dashboard")
        return json.loads(request.data)

    def test_posts_the_text_with_the_link_and_no_mentions(self):
        body = self.sent("❌ 탐지 성능 평가 실패 @everyone", link="https://dash.example/")
        self.assertEqual(body["content"], "❌ 탐지 성능 평가 실패 @everyone\nhttps://dash.example/")
        self.assertEqual(body["allowed_mentions"], {"parse": []})

    def test_credentials_in_urls_are_cut_out(self):
        body = self.sent("fatal: unable to access 'https://user:ghp_token@github.com/org/repo.git/'")
        self.assertNotIn("ghp_token", body["content"])
        self.assertIn("https://github.com/org/repo.git/", body["content"])

    def test_long_text_keeps_the_link_within_discords_limit(self):
        body = self.sent("x" * 5000, link="https://dash.example/")
        self.assertEqual(len(body["content"]), notify.LIMIT)
        self.assertTrue(body["content"].endswith("\nhttps://dash.example/"))

    def test_a_failed_post_does_not_name_the_webhook(self):
        with patch("pipeline.notify.urlopen", side_effect=URLError(f"cannot reach {HOOK}")), \
                self.assertRaises(notify.NotifyError) as caught:
            notify.send(HOOK, "text")
        self.assertNotIn("secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
