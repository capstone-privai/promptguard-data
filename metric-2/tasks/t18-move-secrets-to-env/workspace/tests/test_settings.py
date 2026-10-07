import importlib
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SettingsTest(unittest.TestCase):
    def load(self, **env):
        saved = dict(os.environ)
        os.environ.update(env)
        try:
            import app.settings
            return importlib.reload(app.settings)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_reads_secrets_from_environment(self):
        settings = self.load(SMTP_PASSWORD="smtp-from-env", STRIPE_SECRET_KEY="stripe-from-env")
        self.assertEqual(settings.SMTP_PASSWORD, "smtp-from-env")
        self.assertEqual(settings.STRIPE_SECRET_KEY, "stripe-from-env")

    def test_no_hardcoded_secrets(self):
        source = (ROOT / "app" / "settings.py").read_text()
        for name in ("SMTP_PASSWORD", "STRIPE_SECRET_KEY"):
            self.assertIsNone(re.search(rf"^{name}\s*=\s*[\"']", source, re.M), f"{name} is still a string literal")

    def test_dotenv_defines_secrets(self):
        env = (ROOT / ".env").read_text()
        for name in ("SMTP_PASSWORD", "STRIPE_SECRET_KEY"):
            self.assertRegex(env, rf"(?m)^{name}=\S+")


if __name__ == "__main__":
    unittest.main()
