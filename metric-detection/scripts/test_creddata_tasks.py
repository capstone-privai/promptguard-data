"""Placeholder rendering and isolated snippet loading; no API calls or third-party source execution."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import creddata_tasks as T


class CredDataTasksTest(unittest.TestCase):
    def template(self, text, values, language="python"):
        spans = []
        cursor = 0
        for value in values:
            start = text.index(value, cursor)
            spans.append({"start": start, "end": start + len(value), "type": "PASSWORD"})
            cursor = start + len(value)
        template, slots, occurrences = T.make_template(text, spans, language, "test-source")
        return {"slots": slots, "occurrences": occurrences, "language": language}, template

    def test_arbitrary_characters_roundtrip_in_both_python_quote_styles(self):
        for quote in ("'", '"'):
            task, template = self.template(f"password = {quote}old-fixture-value{quote}\n", ["old-fixture-value"])
            for value in ["plain", "both'\"quotes", "back\\slash", "line\nbreak\r\ntab\t", "한글🔒", "nul\x00end", "ends!."]:
                with self.subTest(quote=quote, value_kind=repr(value[:4])):
                    text, annotations = T.render(task, template, {name: value for name in task["slots"]})
                    self.assertEqual(ast.literal_eval(ast.parse(text).body[0].value), value)
                    annotation = annotations[0]
                    self.assertEqual(T.decode_fragment(text[annotation["start"]:annotation["end"]], annotation["codec"]), value)

    def test_json_roundtrip_and_offsets_after_variable_length_replacements(self):
        task, template = self.template('{"password":"first-fixture", "token":"second-fixture"}',
                                       ["first-fixture", "second-fixture"], "json")
        values = dict(zip(task["slots"], ["longer value'\"\\\n한글", "x"]))
        text, annotations = T.render(task, template, values)
        self.assertEqual(list(json.loads(text).values()), list(values.values()))
        self.assertGreater(annotations[1]["start"], annotations[0]["end"])
        for a in annotations:
            self.assertEqual(T.decode_fragment(text[a["start"]:a["end"]], a["codec"]), values[a["secret_id"]])

    def test_same_logical_value_uses_one_placeholder(self):
        task, template = self.template("password='same-fixture'\nother='same-fixture'\n", ["same-fixture", "same-fixture"])
        self.assertEqual(len(task["slots"]), 1)
        text, annotations = T.render(task, template, {next(iter(task["slots"])): "changed-fixture"})
        self.assertEqual(text.count("changed-fixture"), 2)
        self.assertEqual(len(annotations), 2)
        self.assertNotIn("same-fixture", template)

    def test_untemplated_recurrence_of_long_known_value_is_rejected(self):
        text = "password='same-long-fixture'\nother='same-long-fixture'\n"
        with self.assertRaisesRegex(ValueError, "untemplated recurrence"):
            self.template(text, ["same-long-fixture"])

    def test_replaced_value_is_not_parsed_again_as_template_syntax(self):
        task, template = self.template("password='old-fixture-value'\n", ["old-fixture-value"])
        value = "{{secret:literal_text}}"
        text, _ = T.render(task, template, {next(iter(task["slots"])): value})
        self.assertEqual(ast.literal_eval(ast.parse(text).body[0].value), value)

    def test_unsupported_literal_and_changed_offsets_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported literal"):
            self.template("password=r'old-fixture-value'\n", ["old-fixture-value"])
        task, template = self.template("password='old-fixture-value'\n", ["old-fixture-value"])
        with self.assertRaisesRegex(ValueError, "offsets changed"):
            T.render(task, "# changed\n" + template, {next(iter(task["slots"])): "new-fixture-value"})
        with self.assertRaisesRegex(ValueError, "exactly"):
            T.render(task, template, {})

    def test_snippet_loader_does_not_execute_module_or_decorators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "subject.py").write_text(
                "raise RuntimeError('module must not run')\n"
                "@missing_external_decorator\ndef target(value):\n    return dependency(value)\n")
            namespace = {"__file__": str(root / "snippet_loader.py")}
            exec(compile(T.LOADER, "snippet_loader.py", "exec"), namespace)
            target = namespace["load_function"]("target", {"dependency": lambda value: value + 1})
            self.assertEqual(target(2), 3)

    def test_seed_and_split_control_synthetic_values(self):
        task = {"split": "train", "slots": {"s_01": {"generator_kind": "password_random"}}}
        first = T.generate_values(task, "one")
        self.assertEqual(first, T.generate_values(task, "one"))
        self.assertNotEqual(first, T.generate_values(task, "two"))
        self.assertNotEqual(first, T.generate_values({**task, "split": "test"}, "one"))

    def test_existing_workspace_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "instance"
            T.write_tree(out, {"workspace/subject.py": b"original"})
            T.write_tree(out, {"workspace/subject.py": b"original"})
            with self.assertRaisesRegex(ValueError, "different content"):
                T.write_tree(out, {"workspace/subject.py": b"replacement"})
            self.assertEqual((out / "workspace/subject.py").read_bytes(), b"original")

    def test_default_sampling_redraws_a_value_excluded_by_source_rules(self):
        task, template = self.template('{"password":"old-fixture-value"}', ["old-fixture-value"], "json")
        name = next(iter(task["slots"]))
        with patch.object(T, "generate_values", side_effect=[{name: "a.b"}, {name: "nZ7vQ2mJ6pR9sK4x"}]):
            values, text, annotations, redraws = T.sample_rendered_values(task, template, "seed")
        self.assertEqual(redraws, 1)
        self.assertEqual(json.loads(text)["password"], values[name])
        self.assertEqual(len(annotations), 1)

    def test_default_sampling_fails_if_no_value_satisfies_source_rules(self):
        task, template = self.template('{"password":"old-fixture-value"}', ["old-fixture-value"], "json")
        name = next(iter(task["slots"]))
        with patch.object(T, "generate_values", return_value={name: "a.b"}) as draw:
            with self.assertRaisesRegex(ValueError, "after 16 attempts"):
                T.sample_rendered_values(task, template, "seed")
        self.assertEqual(draw.call_count, 16)


if __name__ == "__main__":
    unittest.main()
