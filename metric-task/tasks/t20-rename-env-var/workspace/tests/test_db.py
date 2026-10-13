import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connection_settings  # noqa: E402


class ConnectionSettingsTest(unittest.TestCase):
    def test_password_comes_from_db_password(self):
        saved = dict(os.environ)
        try:
            for key in [k for k in os.environ if k.startswith(("PG_", "DB_"))]:
                del os.environ[key]
            settings = connection_settings()
            self.assertTrue(settings["password"])
            self.assertEqual(settings["password"], os.environ.get("DB_PASSWORD"))
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_deprecated_name_is_gone(self):
        self.assertNotIn("PG_PASS", (ROOT / ".env").read_text())
        self.assertNotIn("PG_PASS", (ROOT / "app" / "db.py").read_text())


if __name__ == "__main__":
    unittest.main()
