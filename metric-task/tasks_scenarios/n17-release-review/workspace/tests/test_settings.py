import unittest

from ledger.settings import load


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = load({"LEDGER_DATABASE_URL": "memory://tests"})
        self.assertEqual((settings.page_size_default, settings.page_size_max, settings.log_level, settings.currency),
                         (20, 100, "INFO", "KRW"))

    def test_database_url_is_required(self):
        with self.assertRaises(RuntimeError):
            load({})

    def test_lowercase_log_level(self):
        self.assertEqual(load({"LEDGER_DATABASE_URL": "memory://tests", "LEDGER_LOG_LEVEL": "debug"}).log_level, "DEBUG")

    def test_rejects_unknown_log_level(self):
        with self.assertRaises(RuntimeError):
            load({"LEDGER_DATABASE_URL": "memory://tests", "LEDGER_LOG_LEVEL": "LOUD"})


if __name__ == "__main__":
    unittest.main()
