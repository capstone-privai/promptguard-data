"""Key material is labeled in renderings the exact search does not know."""
import json
import unittest

import creddata_category_formats as formats
import creddata_rollout as R
import value_gen


def entry(value):
    return {"name": "s1", "root": "s1", "kind": "category", "role": "secret", "value": value,
            "type": "PEM Private Key", "structured": True, "forms": [{"text": value, "how": "exact"}]}


class KeyStreamTests(unittest.TestCase):
    def setUp(self):
        for i in range(50):  # a block with several body lines
            self.pem = formats.generator_for("PEM Private Key")(value_gen.Draw(f"key-stream-test-{i}"))
            if self.pem.count("\n") >= 6 and "Proc-Type" not in self.pem:
                break
        self.lines = self.pem.split("\n")
        self.entries = [entry(self.pem)]

    def label(self, text):
        gold, _, review = R.label_whole_file_item(text, self.entries, set(), R.Counter())
        return gold, review

    def assert_whole(self, text, rendered):
        gold, _ = self.label(text)
        self.assertEqual(len(gold), 1, text[:200])
        start = text.index(rendered.split("\n")[0][:20])
        self.assertEqual(gold[0]["start"], start)
        self.assertTrue(text[gold[0]["start"]:gold[0]["end"]].rstrip("$").endswith("-----"))
        return gold[0]

    def test_exact_and_read_tool_numbering_still_exact(self):
        gold, _ = self.label("before\n" + self.pem + "\nafter\n")
        self.assertEqual([(g["how"]) for g in gold], ["exact"])
        numbered = "\n".join(f"{i + 1:>6}\t{line}" for i, line in enumerate(["x = 1", *self.lines, "y = 2"]))
        gold, _ = self.label(numbered)
        self.assertEqual(len(gold), 1)
        self.assertNotIn("stream", gold[0]["how"])

    def test_line_end_markers(self):
        text = "header$\n" + "".join(line + "$\n" for line in self.lines) + "tail$\n"
        span = self.assert_whole(text, self.pem)
        self.assertEqual(span["how"], "stream")
        self.assertEqual(span["coverage"], 1.0)

    def test_numbering_mixed_with_other_output(self):
        text = "--- file ---\n" + "\n".join(f"{i + 1:>6}\t{line}" for i, line in enumerate(self.lines)) + "\n--- done ---\n"
        self.assertEqual(self.assert_whole(text, self.pem)["coverage"], 1.0)

    def test_json_escaped_write_input(self):
        text = json.dumps({"file_path": "/w/NOTES.md", "content": "Key:\n\n" + self.pem + "\n\nEnd."})
        gold, _ = self.label(text)
        self.assertEqual(len(gold), 1)
        self.assertTrue(text[gold[0]["start"]:].startswith("-----BEGIN"))
        self.assertTrue(text[:gold[0]["end"]].endswith("-----"))

    def test_indented_quoted_and_rewrapped(self):
        body = "".join(self.lines[1:-1])
        rewrapped = [self.lines[0]] + [body[i:i + 48] for i in range(0, len(body), 48)] + [self.lines[-1]]
        text = "key = (\n" + "".join(f'    "{line}\\n"\n' for line in rewrapped) + ")\n"
        self.assertEqual(self.assert_whole(text, self.pem)["coverage"], 1.0)

    def test_grep_context_dash_separator(self):
        text = "".join(f"{i + 3}-{line}\n" for i, line in enumerate(self.lines))
        self.assert_whole(text, self.pem)

    def test_partial_body_lines_are_gold(self):
        text = "sed -n 2,3p\n" + self.lines[1] + "\n" + self.lines[2] + "\nnext\n"
        gold, _ = self.label(text)
        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["how"], "stream_partial")
        self.assertEqual(text[gold[0]["start"]:gold[0]["end"]], self.lines[1] + "\n" + self.lines[2])
        self.assertLess(gold[0]["coverage"], 1.0)

    def test_truncated_line_after_header(self):
        text = f"     1\t{self.lines[0]}\n     2\t{self.lines[1][:30]}\n     3\t----\n"
        gold, _ = self.label(text)
        self.assertEqual(len(gold), 1)
        self.assertTrue(text[gold[0]["start"]:].startswith("-----BEGIN"))
        self.assertTrue(text[:gold[0]["end"]].endswith(self.lines[1][:30]))

    def test_armor_alone_and_unrelated_base64_are_not_labeled(self):
        other = formats.generator_for("PEM Private Key")(value_gen.Draw("another-key"))
        gold, _ = self.label("The file starts with `" + self.lines[0] + "`.\n" + other + "\n")
        self.assertEqual(gold, [])

    def test_jwk_field_value_shown_alone(self):
        value = "kty: 'EC', crv: 'P-256', d: 'qhn97b91khmS-dOkHPYNu0nUZv_JDPCOmhlqtPRcFkf'"
        entries = [{**entry(value), "type": "JWK"}]
        text = '{"d": "qhn97b91khmS-dOkHPYNu0nUZv_JDPCOmhlqtPRcFkf", "use": "sig"}'
        gold, _, _ = R.label_whole_file_item(text, entries, set(), R.Counter())
        self.assertEqual([text[g["start"]:g["end"]] for g in gold], ["qhn97b91khmS-dOkHPYNu0nUZv_JDPCOmhlqtPRcFkf"])


if __name__ == "__main__":
    unittest.main()
