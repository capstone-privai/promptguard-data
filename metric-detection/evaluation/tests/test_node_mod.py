"""The Node path: mapping a Mod's output to original-text edits, saved detections, and the driver's refusals."""

from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.adapters.node_mod import ModDriverError, ModMappingError, NodeMod, map_edits
from evaluation.adapters.promptguard_adapter import PromptGuardAdapter
from evaluation.dataset.schema import Item, Session
from evaluation.scorer.edits import Edit
from evaluation.tests.support import (BLOCKED_TEXT, HAS_NODE, NODE_REASON, SYSTEM_ROOT, ScriptedWorker, finding, found,
                                      mod_at)


class MappingTests(unittest.TestCase):
    def test_adjacent_placeholders_are_two_edits(self) -> None:
        text = "k=abcdefXYZW\n"
        result = found(finding(text, "abcdef", value_hash="a"), finding(text, "XYZW", value_hash="b"))
        out = "k=[PASSWORD_1][PASSWORD_2]\n"
        self.assertEqual(map_edits(text, result, out, None, None),
                         [Edit(2, 8, "[PASSWORD_1]"), Edit(8, 12, "[PASSWORD_2]")])

    def test_public_prefix_stays_kept_text(self) -> None:
        # 668c2c1 with PG_PLACEHOLDER_PUBLIC_PREFIX=on writes the prefix, then the placeholder.
        text = "T=ghp_0123456789abcdefABCDEF\n"
        result = found(finding(text, "ghp_0123456789abcdefABCDEF", "TOKEN"))
        self.assertEqual(map_edits(text, result, "T=ghp_[GITHUB_TOKEN_1]\n", None, None),
                         [Edit(6, 28, "[GITHUB_TOKEN_1]")])

    def test_part_marker_maps_the_longest_run(self) -> None:
        text = "cut: uIo7Hg2Lk5, done\n"
        vault = [["Qw3rTy9uIo7Hg2Lk5Z", "[PASSWORD_1]", "[PASSWORD_1]"]]
        out = "cut: [PASSWORD_1_PART], done\n"
        self.assertEqual(map_edits(text, found(), out, text, vault), [Edit(5, 15, "[PASSWORD_1_PART]")])

    def test_kept_brackets_around_a_remasked_value(self) -> None:
        text = "x=[Qw3rTy9uIo]\n"
        vault = [["Qw3rTy9uIo", "[PASSWORD_1]", "[PASSWORD_1]"]]
        self.assertEqual(map_edits(text, found(), "x=[[PASSWORD_1]]\n", text, vault), [Edit(3, 13, "[PASSWORD_1]")])

    def test_part_markers_inside_placeholders(self) -> None:
        # ff87b4c / f07bbfb mask a run of a known value even when it is only a word: a value "PASSWORD" is then
        # found inside every [PASSWORD_N] the Mod wrote, and inside the part markers of itself.
        text = 'PASSWORD = "ab12cd34"\n'
        result = found(finding(text, "ab12cd34"))
        vault = [["ab12cd34", "[PASSWORD_1]", "[PASSWORD_1]"], ["PASSWORD", "[PASSWORD_2]", "[PASSWORD_2]"]]
        out = '[[PASSWORD_2_PART]_2] = "[[[PASSWORD_2_PART]_2]_1]"\n'
        self.assertEqual(map_edits(text, result, out, 'PASSWORD = "[PASSWORD_1]"\n', vault),
                         [Edit(0, 8, "[[PASSWORD_2_PART]_2]"), Edit(12, 20, "[[[PASSWORD_2_PART]_2]_1]")])

    @unittest.skipUnless(HAS_NODE, NODE_REASON)
    def test_word_runs_of_ff87b4c_map(self) -> None:
        mod_path = mod_at("ff87b4c")
        if mod_path is None:
            self.skipTest("no ff87b4c in the checkout's history")
        mod = NodeMod(mod_path)
        session = mod.session()
        first, second = "P1=ab12cd34 P2=PASSWORD\n", 'PASSWORD = "ab12cd34"\n'
        session.process(first, found(finding(first, "ab12cd34", value_hash="a"),
                                     finding(first, "PASSWORD", value_hash="b")))
        output = session.process(second, found())
        self.assertIn("_PART]", output.text)
        self.assertEqual([(edit.start, edit.end) for edit in output.edits], [(0, 8), (12, 20)])
        mod.close()

    def test_unexplained_output_raises(self) -> None:
        text = "key=abcdefgh\n"
        with self.assertRaises(ModMappingError):
            map_edits(text, found(), "key=zzz\n", text, [])
        with self.assertRaises(ModMappingError):  # a placeholder with no known value behind it
            map_edits(text, found(), "key=[PASSWORD_9]\n", text, [])
        with self.assertRaises(ModMappingError):  # no placeholder where the finding is
            map_edits(text, found(finding(text, "abcdefgh")), "key=abcdefgh!\n", None, None)


@unittest.skipUnless(HAS_NODE and SYSTEM_ROOT, NODE_REASON if not HAS_NODE else "no checkout")
class SavedDetectionsTests(unittest.TestCase):
    TEXTS = ["A_PASSWORD=Qw3rTy9uIo7Hg2Lk5Z\n", "echo Qw3rTy9uIo7Hg2Lk5Z; cut uIo7Hg2Lk5\n", "DB_PASSWORD=x\n",
             "nothing here\n"]

    def _worker(self) -> ScriptedWorker:
        first = self.TEXTS[0]
        return ScriptedWorker({first: found(finding(first, "Qw3rTy9uIo7Hg2Lk5Z")),
                               self.TEXTS[2]: RuntimeError("ml timeout")})

    def _session(self) -> Session:
        items = [Item(index, "t0", "tool_output", text) for index, text in enumerate(self.TEXTS)]
        items.append(Item(len(items), "t1", "tool_input", self.TEXTS[0]))
        return Session("s", items, [])

    def test_replay_equals_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "shard.jsonl.gz"
            live = PromptGuardAdapter(self._worker(), detections_out=saved)
            live_out = live.run_session(self._session())
            live.close()
            rows = [json.loads(line) for line in gzip.open(saved, "rt", encoding="utf-8")]
            self.assertEqual(rows[0]["detector"], ScriptedWorker.DESCRIPTION)
            self.assertEqual([row["item_id"] for row in rows[1:]], [0, 1, 2, 3])  # tool_input is not scanned
            self.assertEqual(rows[3]["result"], {"ok": False, "exception": "RuntimeError"})
            replay = PromptGuardAdapter.replaying(Path(tmp), SYSTEM_ROOT)
            replay_out = replay.run_session(self._session())
            self.assertEqual({k: (v.text, v.edits) for k, v in replay_out.items()},
                             {k: (v.text, v.edits) for k, v in live_out.items()})
            self.assertEqual(replay_out[2].text, BLOCKED_TEXT)
            self.assertEqual((replay.describe()["detections"], replay.describe()["blocked_items"]), ("replayed", 1))
            # the same detections under an older Mod: no partial remask, and the failed item passes unchanged
            old = mod_at("424df6a")
            if old is not None:
                older = PromptGuardAdapter(replay=replay.replay, mod=old).run_session(self._session())
                self.assertEqual(older[2].text, self.TEXTS[2])
                self.assertIn("uIo7Hg2Lk5", older[1].text)
                self.assertNotIn("uIo7Hg2Lk5", replay_out[1].text)

    def test_missing_item_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = PromptGuardAdapter(self._worker(), detections_out=Path(tmp) / "a.jsonl.gz")
            live.close()
            with self.assertRaises(KeyError):
                PromptGuardAdapter.replaying(Path(tmp), SYSTEM_ROOT).run_session(self._session())


@unittest.skipUnless(HAS_NODE, NODE_REASON)
class DriverTests(unittest.TestCase):
    def test_a_mod_it_cannot_drive_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "register.mjs"
            path.write_text("export function register(on) {}\n", encoding="utf-8")
            with self.assertRaises(ModDriverError):
                NodeMod(path)

    def test_sessions_do_not_share_a_ledger(self) -> None:
        if SYSTEM_ROOT is None:
            self.skipTest("no checkout")
        mod = NodeMod(SYSTEM_ROOT / "src/native-mod/hooks/register.mjs")
        text = "A_PASSWORD=Qw3rTy9uIo\n"
        first = mod.session().process(text, found(finding(text, "Qw3rTy9uIo")))
        second = mod.session().process("echo Qw3rTy9uIo\n", found())
        self.assertEqual((first.text, second.text), ("A_PASSWORD=[PASSWORD_1]\n", "echo Qw3rTy9uIo\n"))
        mod.close()


if __name__ == "__main__":
    unittest.main()
