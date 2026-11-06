"""When m2_loop.py waits and when it stops. Starts no Claude."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_loop as loop

HOUR = 3600.0


def write_result(batch: Path, task: str, result: dict) -> None:
    run = batch / task / "none-r1"
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps(result), encoding="utf-8")


class ProgressTests(unittest.TestCase):
    def test_sorts_runs_into_valid_refused_and_hard(self):
        with tempfile.TemporaryDirectory() as d:
            batch = Path(d)
            (batch / "batch.json").write_text(
                json.dumps({"tasks": ["a", "b", "c", "d", "e"], "conditions": ["none"], "reps": 1}), encoding="utf-8")
            write_result(batch, "a", {"valid": True, "claude": {}})
            write_result(batch, "b", {"valid": False, "claude": {"is_error": True, "api_error_status": 429}})
            write_result(batch, "c", {"valid": False, "error": "timeout after 900s"})
            write_result(batch, "d", {"valid": False, "claude": {"is_error": True, "subtype": loop.BUDGET_SUBTYPE}})
            self.assertEqual(loop.batch_progress(batch), loop.Progress(expected=5, valid=1, refused=1, hard=2))


class DecideTests(unittest.TestCase):
    def decide(self, state, now, valid, refused=0, hard=0):
        return loop.decide(loop.Progress(10, valid, refused, hard), state, now, max_hard_stalls=2, max_wait=6 * HOUR)

    def test_done_when_every_run_is_valid(self):
        self.assertEqual(self.decide(loop.State(), 0, valid=10), "done")

    def test_a_limit_shorter_than_the_maximum_wait_does_not_stop_the_batch(self):
        state = loop.State()
        self.assertIsNone(self.decide(state, 0, valid=3, refused=7))
        self.assertIsNone(self.decide(state, 5 * HOUR, valid=3, refused=7))
        self.assertIsNone(self.decide(state, 5.5 * HOUR, valid=4, refused=6))
        self.assertIsNone(self.decide(state, 11 * HOUR, valid=4, refused=6))

    def test_stops_when_a_limit_outlasts_the_maximum_wait(self):
        state = loop.State()
        self.decide(state, 0, valid=3, refused=7)
        self.assertIn("refused", self.decide(state, 6 * HOUR, valid=3, refused=7))

    def test_stops_after_two_rounds_of_runs_that_spend_usage_and_still_fail(self):
        state = loop.State()
        self.decide(state, 0, valid=3, hard=7)
        self.assertIsNone(self.decide(state, 1, valid=3, hard=7))
        self.assertIn("reaching the model", self.decide(state, 2, valid=3, hard=7))

    def test_progress_resets_the_count_of_stalled_rounds(self):
        state = loop.State()
        self.decide(state, 0, valid=3, hard=7)
        self.decide(state, 1, valid=3, hard=7)
        self.assertIsNone(self.decide(state, 2, valid=4, hard=6))
        self.assertIsNone(self.decide(state, 3, valid=4, hard=6))


if __name__ == "__main__":
    unittest.main()
