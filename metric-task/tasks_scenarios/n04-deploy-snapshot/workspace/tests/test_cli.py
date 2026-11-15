import unittest
import cli


class DeploySmokeTest(unittest.TestCase):
    def test_smoke_invalid_region_reports_loaded_profiles(self):
        cli.render_manifest(env="prod", region="ap-south-99", replicas=2)


if __name__ == "__main__":
    unittest.main()
