"""latency.condense reads what metric-latency/scripts/m4.py writes: a real run against its null detector."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import latency  # noqa: E402


class CondenseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.tmp.name) / "m4"
        subprocess.run([sys.executable, str(latency.M4), "run", "--out", str(cls.run_dir), "--detector", "null",
                        "--synth", "--repeat", "1", "--warmup", "1"], check=True, capture_output=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sweeps_fits_and_headline(self):
        data = latency.condense(self.run_dir)
        self.assertEqual(len(data["detectors"]), 1)
        null = data["detectors"][0]
        self.assertEqual(null["label"], "null")
        self.assertEqual([point["size"] for point in null["size_sweep"]], [128, 1024, 4096, 16384, 65536, 262144])
        self.assertEqual([point["batch"] for point in null["batch_sweep"]], [1, 4, 16, 64, 256])
        self.assertEqual(null["single_1k"]["n"], 2)  # plain and secrets, one repeat each
        self.assertIsNotNone(null["fit_items"])
        self.assertEqual(null["failed"], 0)
        self.assertIsNone(null["guard"])
        headline = latency.headline(data)
        self.assertEqual(headline["single_1k_p50"], null["single_1k"]["p50"])
        self.assertEqual(headline["over_timeout"], 0)

    def test_environment_fingerprint_follows_options(self):
        one = latency.environment("each", [], 5, 3)
        self.assertEqual(one["fingerprint"], latency.environment("each", [], 5, 3)["fingerprint"])
        self.assertNotEqual(one["fingerprint"], latency.environment("ensemble", [], 5, 3)["fingerprint"])


if __name__ == "__main__":
    unittest.main()
