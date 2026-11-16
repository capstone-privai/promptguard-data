"""Syntax, byte/character offsets and literal semantics for additional source languages."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import creddata_languages as L
import creddata_tasks as T


SAMPLES = {
    "javascript": '// 한글😀\nconst password = "old-fixture-value"; function add(a,b) { return a+b; }',
    "typescript": '// 한글😀\nconst password: string = "old-fixture-value"; function add(a:number,b:number) { return a+b; }',
    "go": '// 한글😀\npackage example\nvar password = "old-fixture-value"\nfunc add(a int,b int) int { return a+b }',
    "java": '// 한글😀\nclass Example { String password="old-fixture-value"; int add(int a,int b) { return a+b; } }',
    "ruby": '# 한글😀\npassword = "old-fixture-value"\ndef add(a,b)\n a+b\nend',
    "php": '<?php // 한글😀\n$password = "old-fixture-value"; function add($a,$b) { return $a+$b; }',
    "c": '// 한글😀\nconst char *password="old-fixture-value"; int add(int a,int b) { return a+b; }',
    "cpp": '// 한글😀\nconst char *password="old-fixture-value"; int add(int a,int b) { return a+b; }',
    "csharp": '// 한글😀\nclass Example { string password="old-fixture-value"; int Add(int a,int b) { return a+b; } }',
    "kotlin": '// 한글😀\nval password="old-fixture-value"\nfun add(a:Int,b:Int):Int { return a+b }',
    "scala": '// 한글😀\nobject Example { val password="old-fixture-value"; def add(a:Int,b:Int):Int = a+b }',
    "toml": '# 한글😀\npassword="old-fixture-value"\nport=8080\n',
}


class LanguageAdaptersTest(unittest.TestCase):
    def prepare(self, source, language):
        value = "old-fixture-value"
        start = source.index(value)
        template, slots, occurrences = T.make_template(source, [{"start": start, "end": start + len(value),
                                                                 "type": "PASSWORD"}], language, "fixture")
        return {"language": language, "slots": slots, "occurrences": occurrences}, template

    def test_quoted_literals_roundtrip_with_unicode_prefixes_and_interpolation_characters(self):
        value = "new'\"\\\n$token#{name}한글."
        for language, source in SAMPLES.items():
            with self.subTest(language=language):
                task, template = self.prepare(source, language)
                text, annotations = T.render(task, template, {name: value for name in task["slots"]})
                annotation = annotations[0]
                self.assertEqual(T.decode_fragment(text[annotation["start"]:annotation["end"]], annotation["codec"]), value)
                L.validate(text, language)

    def test_yaml_plain_values_are_quoted_but_gold_excludes_wrapper_quotes(self):
        task, template = self.prepare("password: old-fixture-value\nport: 8080\n", "yaml")
        value = "'quoted'\nline\\한글"
        text, annotations = T.render(task, template, {name: value for name in task["slots"]})
        self.assertEqual(L.config_data(text, "yaml")["password"], value)
        a = annotations[0]
        self.assertEqual(text[a["start"] - 1], '"')
        self.assertEqual(text[a["end"]], '"')
        self.assertEqual(T.decode_fragment(text[a["start"]:a["end"]], a["codec"]), value)

    def test_yaml_single_quotes_have_correct_quote_semantics(self):
        task, template = self.prepare("password: 'old-fixture-value'\nport: 8080\n", "yaml")
        value = "O'Brien\\path"
        text, _ = T.render(task, template, {name: value for name in task["slots"]})
        self.assertEqual(L.config_data(text, "yaml")["password"], value)
        with self.assertRaisesRegex(ValueError, "control characters"):
            T.render(task, template, {name: "line\nbreak" for name in task["slots"]})

    def test_interpolated_strings_are_not_treated_as_plain_literals(self):
        cases = [("javascript", 'const password = `old-fixture-value${token}`;'),
                 ("kotlin", 'val password="old-fixture-value$token"'),
                 ("ruby", 'password="old-fixture-value#{token}"')]
        for language, source in cases:
            with self.subTest(language=language), self.assertRaisesRegex(ValueError, "unsupported literal"):
                self.prepare(source, language)

    @unittest.skipUnless(shutil.which("node"), "Node is needed to validate JavaScript literal semantics")
    def test_javascript_literal_value_matches_node_runtime(self):
        value = "quote'\"\\\n한글\x00"
        encoded = T.encode_fragment(value, "native:javascript:double")
        result = subprocess.run(["node", "-e", 'process.stdout.write(JSON.stringify("' + encoded + '"))'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), value)

    @unittest.skipUnless(shutil.which("node"), "Node is needed for the isolated function loader")
    def test_javascript_loader_uses_utf16_ranges_and_skips_module_initialization(self):
        source = 'throw new Error("module must not run"); const label="한글😀"; function add(a,b) { return a+b; }'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "subject.js").write_text(source)
            (root / "snippet_functions.json").write_text(json.dumps(L.javascript_ranges(source)))
            loader = root / "snippet_loader.cjs"
            loader.write_text(L.javascript_loader("subject.js"))
            result = subprocess.run(["node", "-e", "const m=require(process.argv[1]); console.log(m.loadFunction('add')(2,3));", str(loader)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "5")


if __name__ == "__main__":
    unittest.main()
