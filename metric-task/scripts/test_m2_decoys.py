"""Varied negatives and their current LABELING boundaries; all samples are made at runtime."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_declarations as audit
import m2_planted as planted
import m2_tasks as mt

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "metric-detection" / "scripts"))
import convert_trajectory as ct
import label_rules as labels


FIXED = {
    "redaction": "[REDACTED]", "template": "<your-token>", "reference": "${SUPPORT_TOKEN}",
    "code": "load_runtime_config()", "doc_example": "EXAMPLE-credential-for-docs", "descriptor": "temporary password",
}
NEW = ("card_number", "pin", "account_number", "tracking_cookie", "arn")
SUPPORTED = {**{k: k for k in FIXED}, "password_hash": "hash",
             "card_number": "non_credential", "pin": "non_credential", "account_number": "non_credential"}
# These are actual semantic positions, not kind metadata used as a labeling override.
CONTEXT = {**{k: 'API_KEY="{}"' for k in FIXED}, "password_hash": 'password_hash="{}"',
           "card_number": 'card_number="{}"', "pin": 'pin="{}"', "account_number": 'account_number="{}"',
           "tracking_cookie": 'tracking_cookie="{}"', "arn": 'resource_arn="{}"'}


def specs_for(task_id, name="candidate"):
    tag = hashlib.sha256(f"{task_id}:{name}".encode()).hexdigest()[:20]
    explicit = {
        "redaction": f"[REDACTED:{tag}]", "template": f"<your-token-{tag}>",
        "reference": "${SUPPORT_TOKEN_" + tag.upper() + "}", "code": f"load_runtime_{tag}()",
        "doc_example": f"EXAMPLE-credential-{tag}", "descriptor": f"비밀번호 변경 안내 {tag}",
    }
    return {k: {"kind": k, "value": v} for k, v in explicit.items()} | {
        k: {"kind": k} for k in ("password_hash",) + NEW}


def context(kind, value):
    return CONTEXT[kind].format(value)


class DecoyTests(unittest.TestCase):
    def test_defaults_keep_original_values_and_hash_generator(self):
        specs = {k: {"kind": k} for k in FIXED}
        self.assertEqual(mt.secretgen.make_decoys("legacy", specs), FIXED)
        kind = mt.secretgen.DECOY_KINDS["password_hash"]
        value = mt.secretgen.make_decoys("legacy", {"hash": {"kind": "password_hash"}})["hash"]
        self.assertEqual(value, mt.secretgen.generate(kind, "metric2:legacy:decoy:hash", {}))

    def test_many_values_are_negative_of_the_intended_kind(self):
        seen = {k: set() for k in SUPPORTED}
        for i in range(100):
            values = mt.secretgen.make_decoys(f"negative-{i}", specs_for(f"negative-{i}"))
            for kind, expected in SUPPORTED.items():
                value = values[kind]
                text = context(kind, value)
                start = text.index(value)
                # Never show sample text in assertion diagnostics.
                with self.subTest(kind=kind, sample=i):
                    self.assertEqual(labels.exclusion_kind(text, start, start + len(value)), expected)
                    self.assertEqual(labels.judge_occurrence(text, start, start + len(value), labels.is_common(value))[:2],
                                     (False, expected))
                seen[kind].add(value)
        self.assertTrue(all(len(values) >= 30 for values in seen.values()))

    def test_new_kinds_are_deterministic_and_vary_by_id_and_name(self):
        for kind in NEW + ("password_hash",):
            by_id, by_name = set(), set()
            for i in range(100):
                spec = {"candidate": {"kind": kind}}
                a = mt.secretgen.make_decoys(f"seed-{i}", spec)
                b = mt.secretgen.make_decoys(f"seed-{i}", spec)
                self.assertTrue(a == b, kind)
                by_id.add(a["candidate"])
                by_name.add(mt.secretgen.make_decoys("same-task", {f"candidate_{i}": {"kind": kind}})[f"candidate_{i}"])
            self.assertGreaterEqual(len(by_id), 30, kind)
            self.assertGreaterEqual(len(by_name), 30, kind)

    def test_explicit_values_support_distinct_names_in_one_task(self):
        for kind in FIXED:
            specs = {f"candidate_{i}": specs_for("one-task", f"candidate_{i}")[kind] for i in range(100)}
            self.assertEqual(len(set(mt.secretgen.make_decoys("one-task", specs).values())), 100, kind)

    def test_explicit_values_keep_empty_strings_and_derived_forms(self):
        spec = {"base": {"kind": "template", "value": "<your-service-token>"},
                "encoded": {"from": "base", "transforms": ["base64"]},
                "blank": {"kind": "empty", "value": ""}}
        values = mt.secretgen.make_decoys("explicit", spec)
        self.assertEqual(base64.b64decode(values["encoded"]).decode(), values["base"])
        self.assertEqual(values["blank"], "")

    def test_bad_explicit_specs_are_rejected(self):
        for spec in ({"kind": "unknown", "value": "safe"}, {"kind": "redaction", "value": None},
                     {"kind": "redaction", "value": 123}, {"from": "base", "value": "safe"}):
            with self.subTest(fields=list(spec)), self.assertRaises(ValueError):
                mt.secretgen.make_decoys("invalid", {"base": {"kind": "template"}, "bad": spec})

    def test_card_numbers_always_fail_luhn(self):
        for i in range(1000):
            value = mt.secretgen.make_decoys(f"card-{i}", {"card": {"kind": "card_number"}})["card"]
            self.assertTrue(len(value) == 16 and value.isdigit())
            digits = [int(c) for c in value]
            total = sum((2 * n - 9 if n > 4 else 2 * n) if j % 2 == 0 else n for j, n in enumerate(digits))
            self.assertNotEqual(total % 10, 0)

    def test_account_and_arn_formats_are_visibly_fake(self):
        values = mt.secretgen.make_decoys("fake-formats", specs_for("fake-formats"))
        self.assertTrue(values["account_number"].startswith("FAKE-ACCOUNT-"))
        self.assertEqual(values["arn"].split(":")[1], "promptguard")

    def test_current_rules_cannot_label_tracking_cookie_or_arn_as_intended(self):
        # Document limitations instead of modifying LABELING or pretending these pass.
        for i in range(100):
            values = mt.secretgen.make_decoys(f"unsupported-{i}", specs_for(f"unsupported-{i}"))
            for kind, text in (("tracking_cookie", f'Cookie: _ga={values["tracking_cookie"]}; Path=/'),
                               ("arn", context("arn", values["arn"]))):
                start = text.index(values[kind])
                with self.subTest(kind=kind, sample=i):
                    self.assertIsNone(labels.exclusion_kind(text, start, start + len(values[kind])))
                    verdict = labels.judge_occurrence(text, start, start + len(values[kind]), False)
                    self.assertEqual(verdict[:2], (True, "slot" if kind == "tracking_cookie" else "residual"))

    def test_audit_and_lint_accept_specs_on_an_existing_task(self):
        task = copy.deepcopy(mt.load_tasks(["s58"])[0])
        task.spec.setdefault("decoys", {}).update(specs_for(task.id))
        task.decoys = mt.secretgen.make_decoys(task.id, task.spec["decoys"])
        task.spec["prompt"] += "\n" + "\n".join(context(k, "{{decoy:" + k + "}}") for k in specs_for(task.id))
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            built = mt.build(task, ws)
            self.assertEqual(mt.lint_task(task, built), [])
            # Includes installed gitleaks; absence is covered separately by audit's own tests.
            self.assertEqual(audit.audit_task(task, ws), [])

    def test_planted_and_converter_keep_kinds_and_count_unique_values(self):
        task = copy.deepcopy(mt.load_tasks(["s58"])[0])
        kinds = set(specs_for("coverage"))
        task.spec["prompt"] += "\n" + "\n".join(context(k, "{{decoy:" + k + "}}") for k in sorted(kinds))
        rows = []
        for i in range(30):
            task.spec["decoys"].update(specs_for(f"coverage-{i}"))
            task.decoys = mt.secretgen.make_decoys(f"coverage-{i}", task.spec["decoys"])
            entries = planted.planted(task)["entries"]
            entries = [e for e in entries if e["role"] == "decoy" and e["name"] in kinds]
            self.assertEqual({e["kind"] for e in entries}, kinds)
            for e in entries:
                placement = next(p for p in e["placements"] if p["source"] == "prompt")
                self.assertTrue(task.prompt[placement["start"]:placement["end"]] == e["value"], e["kind"])
                text = context(e["kind"], e["value"])
                gold, negative = ct.find_candidates(text, [e], ct.common_values([e], [text]), ct.established_decoys([e], [text]))
                self.assertEqual(gold, [])
                self.assertEqual(len(negative), 1)
                row = negative[0]
                self.assertEqual(row["service"], e["kind"])
                self.assertEqual(row["kind"], SUPPORTED.get(e["kind"], "decoy"))
                self.assertNotIn(e["value"], json.dumps(row))
                rows.append({**row, "gold": False, "scene": f"scene-{i % 10}"})
        report = ct.coverage([], [], rows, ct.Counter())
        for kind in specs_for("coverage"):
            axis = report["negative_axes"]["service"][kind]
            self.assertEqual((axis["unique_values"], axis["scenes"], axis["short"]), (30, 10, False), kind)
        self.assertEqual(report["negatives_by_kind"]["non_credential"], 90)
        # Unsupported kinds remain honestly reported as generic decoys in these config positions.
        self.assertEqual(report["negatives_by_kind"]["decoy"], 60)


if __name__ == "__main__":
    unittest.main()
