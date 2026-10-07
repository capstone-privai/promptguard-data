from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.adapters.base import ItemOutput
from evaluation.adapters.reference import IdentityAdapter
from evaluation.cli import (EXIT_CONFIG, EXIT_DATASET, EXIT_OK, EXIT_SCORING, build_parser, default_use,
                            execute_run, main)
from evaluation.dataset.schema import Session
from evaluation.scorer.edits import Edit
from evaluation.tests.support import (CREDSWEEPER_REASON, GOLD, HAS_CREDSWEEPER, HAS_PROMPTGUARD, SESSIONS,
                                      SKIP_REASON, SYSTEM_ROOT)

DATA = ("--sessions", str(SESSIONS))


class LyingAdapter:
    """Claims to mask every gold span but returns the original text."""

    name = "lying"

    def describe(self) -> dict:
        return {"system": self.name}

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        return {
            item.item_id: ItemOutput(item.item_id, item.text,
                                     [Edit(start=span.start, end=span.end, replacement="[X]") for span in session.gold_for(item.item_id)])
            for item in session.items
        }


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out_dir = Path(self._tmp.name) / "runs"

    def _main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        code = main(list(argv), out=out)
        return code, out.getvalue()

    def _broken_dataset(self) -> Path:
        path = Path(self._tmp.name) / "sessions_broken.jsonl"
        record = json.loads(SESSIONS.read_text(encoding="utf-8").splitlines()[0])
        record["items"][0]["channel"] = "browser"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return path

    def test_validate(self) -> None:
        code, output = self._main("validate", *DATA)
        self.assertEqual(code, EXIT_OK)
        self.assertIn("OK: 8 sessions", output)
        code, output = self._main("validate", "--sessions", str(self._broken_dataset()), "--gold", str(GOLD))
        self.assertEqual(code, EXIT_DATASET)
        self.assertIn("invalid channel", output)

    def test_validate_defaults_to_repository_dataset(self) -> None:
        code, output = self._main("validate")
        self.assertEqual(code, EXIT_OK, output)

    def test_default_use_classifies_ml_evaluation(self) -> None:
        cases = [
            (["--system", "credsweeper", "--ml", "on"], "ml_eval"),
            (["--system", "credsweeper", "--ml", "off"], "rule_eval"),
            (["--system", "credsweeper"], "rule_eval"),
            (["--system", "promptguard", "--predictor", "custom"], "ml_eval"),
            (["--system", "promptguard", "--predictor", "mock"], "rule_eval"),
            (["--system", "oracle"], "rule_eval"),
            (["--system", "identity"], "rule_eval"),
            (["--system", "credsweeper", "--ml", "on", "--use", "ml_eval"], "ml_eval"),
            (["--system", "oracle", "--use", "ml_eval"], "ml_eval"),
        ]
        for options, expected in cases:
            with self.subTest(options=options):
                self.assertEqual(default_use(build_parser().parse_args(["run", *options])), expected)

    def test_credsweeper_ml_records_ml_eval_use(self) -> None:
        # Isolate the purpose selection and run metadata from the optional detector dependency.
        with patch("evaluation.cli.adapter_factory", return_value=(lambda _t: IdentityAdapter(),
                                                                   "credsweeper_ml-on", None)):
            code, output = self._main("run", *DATA, "--system", "credsweeper", "--ml", "on",
                                      "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_OK, output)
        meta = json.loads(next(self.out_dir.glob("*/run_meta.json")).read_text(encoding="utf-8"))
        self.assertEqual(meta["dataset"]["use"], "ml_eval")

    def test_credsweeper_ml_rejects_injected_before_running(self) -> None:
        sessions = Path(self._tmp.name) / "sessions_injected.jsonl"
        records = [json.loads(line) for line in SESSIONS.read_text(encoding="utf-8").splitlines()]
        records[0]["meta"].update(origin="injected", allowed_use=["rule_eval"])
        sessions.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        code, output = self._main("run", "--sessions", str(sessions), "--gold", str(GOLD),
                                  "--system", "credsweeper", "--ml", "on", "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_DATASET, output)
        self.assertIn("meta.allowed_use does not include 'ml_eval'", output)
        self.assertFalse(self.out_dir.exists())

    def test_run_reference_systems(self) -> None:
        for system, recall in (("oracle", "recall=1.0000"), ("identity", "recall=0.0000")):
            code, output = self._main("run", *DATA, "--system", system, "--out", str(self.out_dir))
            self.assertEqual(code, EXIT_OK, output)
            self.assertIn(recall, output)

    @unittest.skipUnless(HAS_PROMPTGUARD, SKIP_REASON)
    def test_run_promptguard(self) -> None:
        code, output = self._main("run", *DATA, "--system", "promptguard", "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_OK, output)
        self.assertIn("gold=12", output)
        self.assertIn("results: ", output)
        meta = json.loads(next(self.out_dir.glob("*/run_meta.json")).read_text(encoding="utf-8"))
        self.assertEqual(meta["system_git"]["root"], str(SYSTEM_ROOT))
        self.assertEqual(meta["dataset"]["use"], "rule_eval")

    @unittest.skipUnless(HAS_PROMPTGUARD, SKIP_REASON)
    def test_run_promptguard_sweep(self) -> None:
        code, output = self._main("run", *DATA, "--system", "promptguard", "--sweep", "0:1:0.5",
                                  "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_OK, output)
        self.assertEqual(output.count("threshold="), 3)
        self.assertIn("pr_auc=N/A", output)

    @unittest.skipUnless(HAS_CREDSWEEPER, CREDSWEEPER_REASON)
    def test_run_credsweeper(self) -> None:
        for ml in ("off", "on"):
            code, output = self._main("run", *DATA, "--system", "credsweeper", "--ml", ml, "--out", str(self.out_dir))
            self.assertEqual(code, EXIT_OK, output)
            self.assertIn(f"credsweeper_ml-{ml}", output)
        code, output = self._main("run", *DATA, "--system", "credsweeper", "--channels", "all", "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_OK, output)
        self.assertIn("credsweeper_ml-off_all", output)
        meta = json.loads(next(self.out_dir.glob("*_all/run_meta.json")).read_text(encoding="utf-8"))
        self.assertEqual(meta["system"]["channels"], ["prompt", "instructions", "tool_input", "tool_output"])

    def test_invalid_dataset_exits_1(self) -> None:
        code, output = self._main("run", "--sessions", str(self._broken_dataset()), "--gold", str(GOLD),
                                  "--system", "oracle", "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_DATASET)
        self.assertIn("nothing was run", output)

    def test_disallowed_use_exits_1(self) -> None:
        sessions = Path(self._tmp.name) / "sessions_injected.jsonl"
        records = [json.loads(line) for line in SESSIONS.read_text(encoding="utf-8").splitlines()]
        records[0]["meta"]["allowed_use"] = ["rule_eval"]
        sessions.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        code, output = self._main("run", "--sessions", str(sessions), "--gold", str(GOLD), "--system", "oracle",
                                  "--use", "ml_eval", "--out", str(self.out_dir))
        self.assertEqual(code, EXIT_DATASET)
        self.assertIn("s-0001 / - / meta.allowed_use does not include 'ml_eval'", output)
        self.assertFalse(self.out_dir.exists())

    def test_unverifiable_edits_exit_2_without_results(self) -> None:
        out = io.StringIO()
        code = execute_run(str(SESSIONS), str(GOLD), lambda _threshold: LyingAdapter(), out_root=self.out_dir, out=out)
        self.assertEqual(code, EXIT_SCORING)
        self.assertFalse(self.out_dir.exists())
        self.assertIn("session=s-0001 item=2", out.getvalue())
        self.assertIn("first difference at offset", out.getvalue())
        self.assertNotIn("mysecret123", out.getvalue())

    def test_configuration_errors_exit_3(self) -> None:
        code, _output = self._main("run", *DATA, "--system", "nope")
        self.assertEqual(code, EXIT_CONFIG)
        code, _output = self._main("run", *DATA)
        self.assertEqual(code, EXIT_CONFIG)
        code, _output = self._main("run", "--sessions", "other.jsonl", "--system", "oracle")
        self.assertEqual(code, EXIT_CONFIG)  # gold file cannot be derived
        cases = [["--system", "oracle", "--threshold", "0.5"],
                 ["--system", "oracle", "--sweep", "0:1:0.5"],
                 ["--system", "oracle", "--system-root", "."],
                 ["--system", "oracle", "--ml", "on"],
                 ["--system", "oracle", "--channels", "all"],
                 ["--system", "credsweeper", "--channels", "stdout"],
                 ["--system", "oracle", "--use", "train"],
                 ["--system", "promptguard", "--system-root", str(self._tmp.name)],
                 ["--system", "promptguard", "--sweep", "1:0:0.5"],
                 ["--system", "promptguard", "--threshold", "0.5", "--sweep", "0:1:0.5"]]
        if HAS_PROMPTGUARD:
            cases += [["--system", "promptguard", "--predictor", "does-not-exist"],
                      ["--system", "promptguard", "--threshold", "1.5"]]
        for extra in cases:
            code, _output = self._main("run", *DATA, "--out", str(self.out_dir), *extra)
            self.assertEqual(code, EXIT_CONFIG, extra)


if __name__ == "__main__":
    unittest.main()
