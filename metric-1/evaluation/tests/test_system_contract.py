"""Values the evaluation side spells out on its own must match the data scripts and the system."""

from __future__ import annotations

import dataclasses
import sys
import typing
import unittest
from pathlib import Path

from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import CHANNELS, GOLD_TYPES
from evaluation.scorer.edits import Edit
from evaluation.tests.support import GOLD, HAS_PROMPTGUARD, SESSIONS, SKIP_REASON

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


class DataContractTests(unittest.TestCase):
    def test_channels_and_types_match_build_dataset(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import build_dataset
        finally:
            sys.path.remove(str(SCRIPTS))
        self.assertEqual(set(CHANNELS), build_dataset.CHANNELS)
        self.assertEqual(set(GOLD_TYPES), build_dataset.TYPES)


@unittest.skipUnless(HAS_PROMPTGUARD, SKIP_REASON)
class SystemContractTests(unittest.TestCase):
    def test_gold_types_match_candidate_types(self) -> None:
        from promptguard.common.schema import CandidateType

        self.assertEqual(set(GOLD_TYPES), set(typing.get_args(CandidateType)))

    def test_edit_fields_match(self) -> None:
        from promptguard.redaction.engine import Edit as SystemEdit

        self.assertEqual([field.name for field in dataclasses.fields(Edit)], list(SystemEdit._fields))

    def test_channel_map_targets_processed_channels(self) -> None:
        from evaluation.adapters.credsweeper_adapter import CredSweeperAdapter
        from evaluation.adapters.promptguard_adapter import CHANNEL_MAP
        from promptguard.pipeline import PROCESSED_CHANNELS

        self.assertLessEqual(set(CHANNEL_MAP), set(CHANNELS))
        self.assertLessEqual(set(CHANNEL_MAP.values()), set(PROCESSED_CHANNELS))
        # The CredSweeper baseline sees the same inputs as PromptGuard.
        self.assertEqual(CredSweeperAdapter().channels, tuple(CHANNEL_MAP))

    def test_converted_edits_equal_system_edits(self) -> None:
        from evaluation.adapters.promptguard_adapter import PromptGuardAdapter, system_channel

        adapter = PromptGuardAdapter("mock", debug=True)
        checked = 0
        for session in load_sessions(SESSIONS, GOLD):
            outputs = adapter.run_session(session)
            for item in session.items:
                if not system_channel(item.channel):
                    continue
                output = outputs[item.item_id]
                system = [(edit["start"], edit["end"], edit["replacement"]) for edit in output.debug["system_edits"]]
                self.assertEqual([(edit.start, edit.end, edit.replacement) for edit in output.edits], system)
                checked += len(system)
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
