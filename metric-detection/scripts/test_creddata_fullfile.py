"""Whole-file catalog (v3) mechanics on synthetic fixtures: positions, key layouts, values, labels. No LLM calls."""
import base64
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import convert_trajectory as C
import creddata_category_formats as formats
import creddata_fullfile as F
import creddata_preflight as P
import creddata_rollout as R

BODY = base64.b64encode(bytes(range(96))).decode()  # synthetic, 128 base64 characters
LINES = [BODY[i:i + 64] for i in range(0, len(BODY), 64)]


def span(text, piece, category="Password", coarse="PASSWORD", source="creddata", occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(piece, start + 1)
    return {"start": start, "end": start + len(piece), "category": category, "type": coarse, "category_source": source}


def task_for(text, spans, path="data/repo/file.txt"):
    language, _, parsed = F.file_language(path)
    mode = F.syntax_mode(text, language, parsed)
    template, slots, occurrences = F.make_template(text, spans, language, mode, "fixture:0")
    task = {"task_id": "analysis-fixture", "family": "analysis", "split": "train", "language": language,
            "syntax_mode": mode, "source_scope": "whole_file", "slots": slots, "occurrences": occurrences,
            "component_id": "component-fixture", "source_repo_id": "repo-fixture", "source_session_id": "fixture",
            "source_item_id": 0, "source_license": "fixture-only", "source_filename": "subject"}
    return task, template


class PemLayoutTest(unittest.TestCase):
    def roundtrip(self, surface):
        layout, original = F.pem_layout(surface)
        self.assertEqual(original, F.pem_value("RSA PRIVATE KEY", LINES))
        self.assertEqual(F.pem_surface(original, layout), surface)  # the source layout restores itself
        value = formats.FORMATS["PEM Private Key"](F.value_gen.Draw("fixture-pem"))
        label, lines = F.pem_lines(value, layout["width"])
        relaid = F.pem_surface(F.pem_value(label, lines), layout)
        self.assertEqual(F.pem_decode(relaid), F.pem_value(label, lines))
        return layout, relaid

    def test_plain_block(self):
        layout, relaid = self.roundtrip("-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(LINES) + "\n-----END RSA PRIVATE KEY-----")
        self.assertEqual((layout["join"], layout["width"]), ("\n", 64))
        self.assertTrue(formats.conforms("PEM Private Key", F.pem_decode(relaid)))

    def test_comment_prefix_and_indentation_are_kept(self):
        joined = "\n    #   ".join(LINES)
        layout, relaid = self.roundtrip("-----BEGIN RSA PRIVATE KEY-----\n    #   " + joined + "\n    #   -----END RSA PRIVATE KEY-----")
        self.assertTrue(all(line.startswith("    #   ") for line in relaid.split("\n")[1:]))

    def test_quoted_concatenated_lines_with_escapes(self):
        sep = '\\n" +\n    "'
        surface = '-----BEGIN RSA PRIVATE KEY----- fake' + sep + sep.join(LINES) + sep + "-----END RSA PRIVATE KEY-----"
        layout, relaid = self.roundtrip(surface)
        self.assertEqual(layout["join"], sep)
        self.assertTrue(relaid.startswith("-----BEGIN") and ' fake\\n" +\n    "' in relaid)

    def test_elided_or_code_bodies_are_excluded(self):
        with self.assertRaisesRegex(F.Ineligible, "pem_body_elided"):
            F.pem_layout("-----BEGIN RSA PRIVATE KEY-----\n" + LINES[0] + "\n...\n" + LINES[1] + "\n-----END RSA PRIVATE KEY-----")
        with self.assertRaisesRegex(F.Ineligible, "pem_irregular_layout"):
            F.pem_layout("-----BEGIN RSA PRIVATE KEY-----\n" + LINES[0] + "\n  " + LINES[1][:32] + "\n" + LINES[1][32:]
                         + "\n-----END RSA PRIVATE KEY-----")
        with self.assertRaisesRegex(F.Ineligible, "pem_body_too_short"):
            F.pem_layout('-----BEGIN PRIVATE KEY-----\\n" + encodedKey + "\\n-----END PRIVATE KEY-----')


JWK_SOURCE = ("const key = {\n  kty: 'RSA',\n  alg: 'RS256',\n  n: '" + "A" * 342 + "',\n  e: 'AQAB',\n  d: '"
              + "B" * 342 + "',\n};\n")


class JwkLayoutTest(unittest.TestCase):
    def test_fields_are_substituted_in_source_order_and_quoting(self):
        start = JWK_SOURCE.index("kty")
        end = JWK_SOURCE.index("',\n};")
        spec = F.jwk_layout(JWK_SOURCE, start, end)
        self.assertEqual((spec["kty"], spec["modulus_bits"]), ("RSA", 2048))
        self.assertEqual([p[1] for p in spec["pieces"] if p[0] == "field"], ["n", "d"])
        value = F.generate_slot({"structure": "jwk", "jwk": spec, "type": "JWK", "avoid": ""}, "fixture-jwk")
        self.assertTrue(value.startswith("kty: 'RSA',\n  alg: 'RS256',\n  n: '") and "e: 'AQAB'" in value)
        self.assertTrue(formats.conforms("JWK", value))
        self.assertNotIn("A" * 40, value)

    def test_a_span_that_starts_inside_the_first_value_and_crossing_spans(self):
        text = "x = {\n  k: '" + "D" * 43 + "',\n  kty: 'oct',\n}\n"
        spec = F.jwk_layout(text, text.index("D"), text.index("'oct'") + 5)
        self.assertEqual(([p[1] for p in spec["pieces"] if p[0] == "field"], spec["oct_bytes"]), (["k"], 32))
        with self.assertRaisesRegex(F.Ineligible, "jwk_field_not_generated"):
            wrong = text.replace("k: '", "d: '")
            F.jwk_layout(wrong, wrong.index("D"), wrong.index("'oct'") + 5)
        with self.assertRaisesRegex(F.Ineligible, "jwk_span_crosses_objects"):
            F.jwk_layout(JWK_SOURCE, JWK_SOURCE.index("kty"), len(JWK_SOURCE) - 1)


class PositionTest(unittest.TestCase):
    def test_raw_text_value_avoids_its_neighbours(self):
        text = "Login notes for the staging service.\nadmin_password=Synthetic9Value;\nport=8080\n"
        info = F.analyse_span(text, span(text, "Synthetic9Value"), [], "text.txt", "unparsed")
        self.assertEqual((info["position"], info["codec"]), ("raw_text", "raw"))
        self.assertTrue(set("=; \n'\"\\") <= set(info["avoid"]))

    def test_url_userinfo_avoids_url_syntax_and_fixed_formats_conflicting_are_excluded(self):
        text = "Connect with postgres://svc:Synthetic9Value@db.internal/app for the reports.\n"
        info = F.analyse_span(text, span(text, "Synthetic9Value"), [], "text.md", "unparsed")
        self.assertTrue(set(":/@?#%") <= set(info["avoid"]))
        with self.assertRaisesRegex(F.Ineligible, "fixed_format_conflicts_with_context"):
            F.analyse_span(text, span(text, "Synthetic9Value", "Basic Authorization", "TOKEN"), [], "text.md", "unparsed")

    def test_literal_keeps_the_escaping_codec_and_comments_are_raw(self):
        text = "# the default password: Synthetic9Comment\nPASSWORD = 'Synthetic9Literal'\n"
        task, template = task_for(text, [span(text, "Synthetic9Comment"), span(text, "Synthetic9Literal")], "a/b.py")
        self.assertEqual([(o["position"], o["codec"]) for o in task["occurrences"]],
                         [("raw_code", "raw"), ("literal", "python_single")])
        rendered, annotations = F.render(task, template, {n: "it's\\fine" if task["slots"][n]["avoid"] == "" else "Plain9Value"
                                                          for n in task["slots"]})
        self.assertIn("'it\\'s\\\\fine'", rendered)

    def test_one_value_per_slot_and_catalog_does_not_draw_values(self):
        text = "Use token Synthetic9Token in staging.\nThe same token Synthetic9Token works in qa.\n"
        spans = [span(text, "Synthetic9Token", "Token", "TOKEN"), span(text, "Synthetic9Token", "Token", "TOKEN", occurrence=1)]
        with patch.object(F, "generate_slot", side_effect=AssertionError("no draws while templating")):
            task, template = task_for(text, spans)
        self.assertEqual(len(task["slots"]), 1)
        self.assertEqual(task["slots"][next(iter(task["slots"]))]["type"], "Token")
        values, rendered, annotations, _, _ = F.sample_rendered_values(task, template, "fixture-seed")
        self.assertEqual(rendered.count(values[next(iter(values))]), 2)


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.text = ("Deployment notes for the synthetic service.\nThe service password is Synthetic9Value here.\n\n"
                     "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(LINES) + "\n-----END RSA PRIVATE KEY-----\n")
        spans = [span(self.text, "Synthetic9Value"),
                 {**span(self.text, self.text[self.text.index("-----BEGIN"):self.text.index("KEY-----\n", 200) + 8],
                         "PEM Private Key", "PRIVATE_KEY")}]
        self.task, self.template = task_for(self.text, spans)
        values, self.rendered, self.annotations, _, _ = F.sample_rendered_values(self.task, self.template, "fixture")
        self.registry = {"values": values, "source_annotations": self.annotations}

    def test_three_renderings_label_every_span_with_its_category(self):
        results = list(P.project_renderings(self.task, self.registry, self.rendered))
        self.assertEqual({r for r, _, _, _ in results}, {"raw", "cat_n", "grep_n"})
        self.assertTrue(all(result == "labeled_exactly" for _, _, result, _ in results))

    def test_numbered_key_block_is_one_span_with_the_prefixes_inside(self):
        shown, offsets = P.numbered(self.rendered, "cat_n")
        _, gold, _, _ = R.label_items(self.task, self.registry, [C.Item("t0", "tool_output", shown)], "fixture")
        pem = next(g["span"] for g in gold if g["span"]["type"] == "PEM Private Key")
        self.assertTrue(shown[pem["start"]:].startswith("-----BEGIN") and shown[:pem["end"]].endswith("KEY-----"))
        self.assertIn("\t", shown[pem["start"]:pem["end"]])

    def test_excerpt_tasks_keep_their_labeler(self):
        task = {"task_id": "t", "family": "analysis", "split": "train", "component_id": "c", "source_repo_id": "r",
                "source_session_id": "s", "source_item_id": 0, "source_license": "l",
                "slots": {"s_01": {"type": "PASSWORD", "generator_kind": "password_random"}}}
        registry = {"values": {"s_01": "nZ7vQ2mJ6pR9sK4x"}}
        text = '     1\tdb:\n     2\t  password: "nZ7vQ2mJ6pR9sK4x"\n'
        with patch.object(R, "strip_line_numbers", side_effect=AssertionError("excerpt tasks are not stripped")):
            _, gold, _, _ = R.label_items(task, registry, [C.Item("t0", "tool_output", text)], "fixture")
        self.assertEqual(gold[0]["span"]["type"], "PASSWORD")

    def test_strip_line_numbers_requires_increasing_numbers(self):
        self.assertIsNone(R.strip_line_numbers("12:30 start\n12:31 stop\n")[1])
        plain, offsets = R.strip_line_numbers("3:alpha\n4:beta\n")
        self.assertEqual(plain, "alpha\nbeta\n")
        self.assertEqual(offsets[plain.index("beta")], "3:alpha\n4:beta\n".index("beta"))


@unittest.skipUnless((F.FULLFILE / "gold_category_train.jsonl").is_file(), "whole-file conversion not present")
class GoldCategoryRebuildTest(unittest.TestCase):
    def test_rebuild_is_byte_identical(self):
        import creddata_gold_categories as G
        self.assertEqual(G.build(), (F.FULLFILE / "gold_category_train.jsonl").read_bytes())


if __name__ == "__main__":
    unittest.main()
