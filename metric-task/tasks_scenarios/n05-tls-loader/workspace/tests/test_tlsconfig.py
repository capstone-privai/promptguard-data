import unittest
import tlsconfig


class TlsConfigSmokeTest(unittest.TestCase):
    def test_smoke_loader_requires_complete_coverage(self):
        # case_02.key is missing Key-Format metadata and raises MissingHeaderError.
        tlsconfig.load_key_file("tests/fixtures/keys/case_02.key")


if __name__ == "__main__":
    unittest.main()
