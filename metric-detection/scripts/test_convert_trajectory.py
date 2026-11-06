"""convert_trajectory.py on hand-made request bodies. Values are generated here, in no provider's format."""
import base64
from collections import Counter
import json
import lzma
from pathlib import Path
import random
import string
import sys
import tempfile
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_trajectory as ct
import dataset_verify as dv


def made_up(seed: str) -> str:
    return "".join(random.Random(seed).choices(string.ascii_letters + string.digits, k=20))


SECRET = made_up("planted")


def entry(name, value, role="secret", kind="token", type_="TOKEN", forms=None):
    return {"name": name, "role": role, "kind": kind, "type": type_, "root": name, "value": value,
            "forms": forms or [{"how": "exact", "text": value}], "placements": []}


def body(*messages, system="You are a coding agent."):
    return {"system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}], "messages": list(messages)}


def user(*blocks):
    return {"role": "user", "content": list(blocks)}


def text(value):
    return {"type": "text", "text": value}


def call(call_id, name, tool_input):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}


def result(call_id, value):
    return {"type": "tool_result", "tool_use_id": call_id, "content": value}


class SessionItemsTests(unittest.TestCase):
    def test_channels_and_turns(self):
        items = ct.session_items([body(
            user(text("<system-reminder>project notes</system-reminder>"), text("fix the build")),
            call("a", "Read", {"file_path": ".env"}), user(result("a", "PORT=1")),
            {"role": "assistant", "content": [{"type": "text", "text": "done"}, {"type": "thinking", "thinking": "hm"}]},
            {"role": "system", "content": "mid-session note"})])
        self.assertEqual([(i.turn_id, i.channel, i.text) for i in items], [
            ("t0", "instructions", "You are a coding agent."), ("t0", "instructions", "<system-reminder>project notes</system-reminder>"),
            ("t0", "prompt", "fix the build"), ("t0", "tool_input", '{"file_path": ".env"}'), ("t0", "tool_output", "PORT=1"),
            ("t2", "instructions", "mid-session note")])

    def test_a_later_request_adds_only_what_is_new_and_a_true_repeat_stays(self):
        first = body(user(text("go")), call("a", "Bash", {"command": "ls"}), user(result("a", "same")))
        second = body(user(text("go")), call("a", "Bash", {"command": "ls"}), user(result("a", "same")),
                      call("b", "Bash", {"command": "ls"}), user(result("b", "same")))
        outputs = [i for i in ct.session_items([first, second]) if i.channel == "tool_output"]
        self.assertEqual(len(outputs), 2)
        self.assertEqual([i.turn_id for i in outputs], ["t0", "t1"])

    def test_a_tool_result_with_blocks_keeps_text_only(self):
        items = ct.session_items([body(call("a", "Read", {}), user(result(
            "a", [text("visible"), {"type": "image", "source": {}}])))])
        self.assertEqual([i.text for i in items if i.channel == "tool_output"], ["visible"])


class ContextTests(unittest.TestCase):
    def context(self, tool, tool_input, output="x"):
        return ct.context_of(ct.Item("t0", "tool_output", output, tool, tool_input))

    def test_where_the_text_came_from_decides(self):
        cases = [(("Read", {"file_path": "web/.env.production"}), "config"), (("Read", {"file_path": "logs/app.jsonl"}), "log"),
                 (("Read", {"file_path": "src/app.py"}), "source"), (("Read", {"file_path": "docs/auth.md"}), "docs"),
                 (("Read", {"file_path": "id_ed25519"}), "key_file"), (("Read", {"file_path": "notes.bin"}), "unknown"),
                 (("Bash", {"command": "env"}), "command_output"), (("Bash", {"command": "cat app.log"}), "log"),
                 (("Bash", {"command": "cd web && sed -n 1,5p .env | grep -v PORT"}), "config"),
                 (("Bash", {"command": "git log -p -3"}), "diff"), (("Bash", {"command": "git diff HEAD~1"}), "diff"),
                 (("Grep", {"pattern": "x"}), "command_output"), (("mcp__ops__get_logs", {}), "unknown")]
        for (tool, tool_input), want in cases:
            self.assertEqual(self.context(tool, tool_input), want, tool_input)

    def test_the_text_of_a_command_decides_http_and_stack_traces(self):
        self.assertEqual(self.context("Bash", {"command": "python3 run.py"}, "< HTTP/1.1 200 OK\n"), "http")
        self.assertEqual(self.context("Bash", {"command": "python3 run.py"},
                                      "Traceback (most recent call last):\n  File"), "stacktrace")

    def test_other_channels(self):
        self.assertEqual(ct.context_of(ct.Item("t0", "prompt", "x")), "natural_language")
        self.assertEqual(ct.context_of(ct.Item("t0", "instructions", "x")), "docs")


class GoldTests(unittest.TestCase):
    def find(self, value_text, entries, golden=()):
        return ct.find_candidates(value_text, entries, ct.common_values(entries, [value_text]), set(golden))

    def test_a_distinct_planted_value_is_gold_also_outside_a_credential_position(self):
        line = f'TOKEN="{SECRET}" and later the log says {SECRET} failed'
        spans, others = self.find(line, [entry("t", SECRET)])
        self.assertEqual(len(spans), 2)
        self.assertEqual({s["kind"] for s in spans}, {"credential_slot", "propagated"})
        self.assertEqual(others, [])

    def test_a_common_planted_value_is_gold_only_in_a_credential_position(self):
        line = "DB_PASSWORD=admin\nconnected as admin"
        spans, others = self.find(line, [entry("p", "admin", kind="password16", type_="PASSWORD")])
        self.assertEqual([line[s["start"]:s["end"]] for s in spans], ["admin"])
        self.assertEqual(spans[0]["start"], line.index("admin"))
        self.assertEqual([o["kind"] for o in others], ["identifier"])

    def test_slashes_in_a_value_do_not_make_its_own_occurrence_a_path_component(self):
        for value in (f'{made_up("slash-a")}/{made_up("slash-b")}', f'{made_up("slash-end")}/'):
            with self.subTest(value_hash=ct.digest(value)):
                line = f'TOKEN="{value}"\nobserved {value} again'
                spans, others = self.find(line, [entry("t", value)])
                self.assertEqual(len(spans), 2)
                self.assertEqual({s["value_class"] for s in spans}, {"distinct"})
                self.assertEqual(others, [])
                self.assertFalse(dv.used_as_identifier(value, [0], {0: line}, source=ct.SOURCE))
        # An absolute path can still be an identifier occurrence; it must not make the value common.
        value = f'/{made_up("slash-start")}'
        self.assertEqual(ct.common_values([entry("t", value)], [value]), set())

    def test_only_a_whole_path_component_makes_a_distinct_value_common(self):
        value = made_up("path-user")
        for path, common in ((f'/home/{value}/x', True), (f'/home/{value}', True),
                             (f'{value}/x', True), (f'/home/prefix{value}/x', False),
                             (f'/home/{value}_suffix/x', False),
                             (f'https://example.invalid/{value}/x', False)):
            with self.subTest(path_hash=ct.digest(path)):
                line = f'TOKEN="{value}"\nobserved {value} again\n"{path}"'
                self.assertEqual(value in ct.common_values([entry("t", value)], [line]), common)
                # Test the path independently of classify's separate identifier-position rules.
                self.assertEqual(value in ct.path_components(path), common)
        self.assertIn("admin", ct.path_components('/home/admin/x'))
        line = f'TOKEN="{value}"\nobserved {value} again\n/home/{value}/x'
        spans, _ = self.find(line, [entry("t", value)])
        self.assertEqual(len(spans), 1)
        self.assertTrue(dv.used_as_identifier(value, [0], {0: line}, source=ct.SOURCE))

    def test_an_encoded_form_is_gold_and_records_how(self):
        spans, _ = self.find(f"the value was {SECRET[::-1]} in base64", [entry(
            "t", SECRET, forms=[{"how": "exact", "text": SECRET}, {"how": "base64", "text": SECRET[::-1]}])])
        self.assertEqual([s["how"] for s in spans], ["base64"])

    def test_declared_derived_forms_report_encoding_without_changing_gold(self):
        value = made_up("encoding-root") + '/+:x???'
        raw = value.encode()
        cases = [("base64", base64.b64encode(raw).decode()),
                 ("base64", base64.b64encode(raw + b'\n').decode()),
                 ("base64url", base64.urlsafe_b64encode(raw).decode()),
                 ("urlencoded", quote(value, safe="")),
                 ("basic", base64.b64encode(b'operator:' + raw).decode()),
                 ("hex", raw.hex())]
        for how, encoded in cases:
            with self.subTest(how=how):
                root = entry("root", value)
                derived = {**entry("derived", encoded, kind=None), "root": "root"}
                line = f'token="{encoded}"'
                old, _ = self.find(line, [root, {**derived, "root": "derived"}])
                spans, others = self.find(line, [root, derived])
                self.assertEqual([{k: v for k, v in s.items() if k != "how"} for s in old],
                                 [{k: v for k, v in s.items() if k != "how"} for s in spans])
                self.assertEqual([s["how"] for s in spans], [how])
                self.assertEqual(others, [])

    def test_noop_unknown_and_missing_root_keep_the_declared_how(self):
        root = entry("root", SECRET)
        for value, root_name in ((SECRET, "root"), (made_up("unknown-transform"), "root"),
                                 (SECRET, "absent")):
            derived = {**entry("derived", value), "root": root_name}
            self.assertEqual(ct.form_how(derived, derived["forms"][0], {"root": root}), "exact")

    def test_a_decoy_is_gold_only_where_the_text_says_so(self):
        decoy = entry("d", made_up("decoy"), role="decoy", kind="request_id", type_=None)
        in_slot, elsewhere = f"api_key={decoy['value']}\n", f"request {decoy['value']} finished\n"
        self.assertEqual(ct.established_decoys([decoy], [elsewhere]), set())
        spans, others = self.find(elsewhere, [decoy])
        self.assertEqual(spans, [])
        self.assertEqual([(o["kind"], o["service"]) for o in others], [("decoy", "request_id")])
        self.assertNotIn(decoy["value"], json.dumps(others))
        self.assertEqual(ct.established_decoys([decoy], [in_slot, elsewhere]), {"d"})
        self.assertEqual(len(self.find(in_slot, [decoy], {"d"})[0]), 1)

    def test_an_empty_decoy_matches_nothing(self):
        decoy = entry("d", "", role="decoy", kind="empty", type_=None)
        self.assertEqual(self.find("DB_PASSWORD=\nport = 1\n", [decoy]), ([], []))
        self.assertEqual(ct.established_decoys([decoy], ["DB_PASSWORD=\n"]), set())

    def test_a_planted_secret_read_as_an_identifier_is_flagged_for_review(self):
        line = f"https://{SECRET}@example.invalid/1\n"
        spans, others = self.find(line, [entry("t", SECRET)])
        self.assertEqual(spans, [])
        self.assertEqual([o["kind"] for o in others], ["identifier"])
        self.assertTrue(ct.needs_review(others[0]))
        self.assertFalse(ct.needs_review({"role": "secret", "kind": "identifier", "value_class": "common"}))
        self.assertFalse(ct.needs_review({"role": "secret", "kind": "code", "value_class": "distinct"}))

    def test_parts_and_undeclared_literals_go_to_review_and_not_to_gold(self):
        line = f'head says {SECRET[:12]}\npassword = "{made_up("undeclared")}"\n'
        rows = ct.to_review(line, [entry("t", SECRET)], [])
        self.assertEqual(sorted(r["kind"] for r in rows), ["partial", "undeclared"])
        self.assertTrue(all(r["review"] and "value_sha256" in r for r in rows))
        self.assertFalse(any(SECRET[:10] in json.dumps(r) for r in rows))

    def test_nothing_goes_to_review_over_a_span_already_taken(self):
        line = f'password = "{SECRET}"\n'
        spans, others = self.find(line, [entry("t", SECRET)])
        self.assertEqual(ct.to_review(line, [entry("t", SECRET)], spans + others), [])


class VerificationCompatibilityTests(unittest.TestCase):
    def test_legacy_path_exemptions_remain_valid_only_for_nontrajectory_sources(self):
        for value in (made_up("legacy-left") + '/' + made_up("legacy-right"),
                      made_up("legacy-path-substring")):
            with self.subTest(value_hash=ct.digest(value)):
                line = f'password="{value}"\nobserved {value} again'
                if '/' not in value:
                    line += f'\n/home/prefix{value}/x'
                key = ("session", 0)
                texts = {key: line}
                first = line.index(value)
                second = line.index(value, first + len(value))
                spans = [(*key, first, first + len(value), "PASSWORD")]
                exempt = {key: [(second, second + len(value), "not_propagated")]}
                for source in (None, "privesc-llm-data", "noseyparker", "nemotron-pii", "other"):
                    self.assertTrue(dv.used_as_identifier(value, [key], texts, source=source))
                    errors = []
                    dv.check_coverage(spans, texts, errors, exempt, source=source)
                    self.assertEqual(errors, [])
                self.assertFalse(dv.used_as_identifier(value, [key], texts, source=ct.SOURCE))
                errors = []
                dv.check_coverage(spans, texts, errors, exempt, source=ct.SOURCE)
                self.assertEqual(len(errors), 1)
                self.assertTrue(errors[0].startswith("uncovered occurrence"))


class ConvertTests(unittest.TestCase):
    def make_run(self, batch, task, run, valid=True, condition_output=f'TOKEN="{SECRET}"', entries=None):
        folder = batch / task / run
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(json.dumps({"valid": valid, "success": True}))
        (folder / "planted.json").write_text(json.dumps({"task": task, "scene": "scene-a",
                                                       "entries": entries or [entry("t", SECRET)]}))
        request = {"path": "/v1/messages?beta=true", "status": 200, "body": body(
            user(text("fix it")), call("a", "Read", {"file_path": ".env"}), user(result("a", condition_output)))}
        refused = {"path": "/v1/messages", "status": 429, "body": body(user(text("not reached")))}
        with lzma.open(folder / ct.REQUESTS_FILE, "wt", encoding="utf-8") as f:
            f.write(json.dumps(request) + "\n" + json.dumps(refused) + "\n")

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            batch = Path(d) / "b1"
            batch.mkdir()
            (batch / "batch.json").write_text(json.dumps({"model": "sonnet", "claude_version": "x", "system_commit": "c"}))
            self.make_run(batch, "t01-a", "none-r1")
            self.make_run(batch, "t02-b", "none-r1", valid=False)
            self.make_run(batch, "t03-c", "gold-r1")
            sessions, gold, labels, stats = ct.convert(batch)
            self.assertEqual([s["session_id"] for s in sessions], ["traj-b1-t01-a-none-r1"])
            self.assertEqual(stats["runs_invalid"], 1)
            meta = sessions[0]["meta"]
            self.assertEqual((meta["origin"], meta["split"], meta["group_id"]), ("recorded", "test", "scene-a"))
            self.assertNotIn("ml_train", meta["allowed_use"])
            self.assertEqual(meta["item_contexts"], ["docs", "natural_language", "tool_input", "config"])
            self.assertFalse(any("not reached" == i["text"] for i in sessions[0]["items"]))
            self.assertEqual([g["item_id"] for g in gold], [3])
            self.assertEqual(gold[0]["span"]["type"], "TOKEN")
            self.assertNotIn(SECRET, json.dumps(labels))
            report = ct.coverage(sessions, gold, labels, stats)
            self.assertEqual(report["reach"]["planted_secrets_reached"], 1)
            self.assertEqual(report["axes"]["context"]["config"]["unique_values"], 1)
            self.assertTrue(report["axes"]["context"]["config"]["short"])

    def test_a_batch_without_planted_files_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            batch = Path(d) / "b1"
            batch.mkdir()
            (batch / "batch.json").write_text("{}")
            self.make_run(batch, "t01-a", "none-r1")
            (batch / "t01-a" / "none-r1" / "planted.json").unlink()
            with self.assertRaises(FileNotFoundError):
                ct.convert(batch)

    def test_declared_encoding_reaches_labels_and_the_how_axis(self):
        value = SECRET + '/+'
        encoded = quote(value, safe="")
        derived = {**entry("encoded", encoded, kind=None), "root": "root"}
        with tempfile.TemporaryDirectory() as d:
            batch = Path(d) / "b1"
            batch.mkdir()
            (batch / "batch.json").write_text("{}")
            self.make_run(batch, "t01-a", "none-r1", condition_output=f'TOKEN="{encoded}"',
                          entries=[entry("root", value), derived])
            sessions, gold, labels, stats = ct.convert(batch)
            self.assertIsInstance(stats, Counter)
            self.assertEqual(len(gold), 1)
            self.assertEqual([r["how"] for r in labels if r["gold"]], ["urlencoded"])
            self.assertEqual(ct.coverage(sessions, gold, labels, stats)["axes"]["how"],
                             {"urlencoded": {"spans": 1, "unique_values": 1, "scenes": 1, "short": True}})


if __name__ == "__main__":
    unittest.main()
