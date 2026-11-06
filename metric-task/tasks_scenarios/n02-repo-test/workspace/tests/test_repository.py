import unittest
from db import connection


class RepositorySmokeTest(unittest.TestCase):
    def test_production_dsn_requires_in_memory_override(self):
        connection.verify_production_dsn()


if __name__ == "__main__":
    unittest.main()
