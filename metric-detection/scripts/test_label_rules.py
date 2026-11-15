"""Cases for label_rules.py, one per rule that once went wrong.

Run from the repository root:
  python metric-detection/scripts/test_label_rules.py
"""
import json
import unittest

from label_rules import (classify, exclusion_kind, is_common, is_gold, is_literal, judge_occurrence, normalize_span,
                         path_components, path_tokens, position_type)


def at(text: str, value: str, nth: int = 0) -> tuple[int, int]:
    start = -1
    for _ in range(nth + 1):
        start = text.index(value, start + 1)
    return start, start + len(value)


class CommandLinePositions(unittest.TestCase):
    """A common value is gold only in a credential position, so these must read as one (LABELING.md 퍼뜨림 기준)."""

    def assert_slot(self, text, value, nth=0):
        self.assertTrue(is_common(value))
        self.assertEqual(classify(text, *at(text, value, nth))[0], "slot", text)
        self.assertTrue(is_gold(True, classify(text, *at(text, value, nth))[0]), text)

    def assert_not_slot(self, text, value, nth=0):
        self.assertNotEqual(classify(text, *at(text, value, nth))[0], "slot", text)

    def test_redis_cli(self):
        self.assert_slot("redis-cli -a 1234 ping", "1234")
        self.assert_slot("redis-cli -h db -p 6379 -a 1234", "1234")
        self.assert_slot("redis-cli -a 'admin' ping", "admin")
        self.assert_not_slot("redis-cli -p 6379 ping", "6379")
        self.assert_not_slot("ls -a 1234", "1234")

    def test_mongo(self):
        self.assert_slot("mongosh -u admin -p 1234", "1234")
        self.assert_slot("mongo -u admin -p 1234 db", "1234")
        self.assert_slot("mongodump -u admin -p 1234 --db x", "1234")
        self.assert_not_slot("mongosh -u admin -p 1234", "admin")

    def test_psql_p_is_a_port(self):
        self.assert_not_slot("psql -h db -p 5432 -U app", "5432")
        self.assert_not_slot("psql -p 5432", "5432")
        self.assert_slot("docker login -u me -p 1234", "1234")

    def test_htpasswd(self):
        self.assert_slot("htpasswd -b .htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -bc /etc/nginx/.htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -c -b .htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -nb admin 1234", "1234")
        self.assert_not_slot("htpasswd -b .htpasswd admin 1234", "admin")
        self.assert_not_slot("htpasswd -nb admin 1234", "admin")
        self.assert_not_slot("htpasswd .htpasswd admin 1234", "1234")

    def test_sed_substitution_delimiters_are_not_paths(self):
        cmd = "sed -i '' 's/oldVal91x/newVal82y/; s/oldVal73z/newVal64w/g' /etc/app/profiles.yml"
        self.assertEqual(path_components(cmd), {"etc", "app", "profiles.yml"})
        self.assertIn("s/oldVal91x/newVal82y/;", path_tokens(cmd))
        for tok in ("oldVal91x", "newVal82y", "oldVal73z", "newVal64w"):
            self.assertEqual(classify(cmd, *at(cmd, tok)), ("residual", None), tok)
            self.assertEqual(judge_occurrence(cmd, *at(cmd, tok), common=False), (True, "residual", None), tok)
        self.assertEqual(classify(cmd, *at(cmd, "profiles.yml")), ("ident", "path"))


    def test_sed_shaped_relative_paths_stay_identifiers(self):
        for text in ('directory s/ledger/settled/', 'open s/ledger/settled/g',
                     "sed 's/old/new/' s/ledger/settled/", "sed -f rules.sed s/ledger/settled/"):
            with self.subTest(text=text):
                self.assertIn('ledger', path_components(text))
                self.assertEqual(classify(text, *at(text, 'ledger')), ('ident', 'path'))

    def test_only_inline_sed_script_delimiters_are_exempt(self):
        for text in ("sed -e 's/oldLedger/newLedger/g' config.ini",
                     "sed -i '' 's/oldLedger/newLedger/; s/oldValue/newValue/' config.ini",
                     'sed "s/oldLedger/newLedger/" config.ini'):
            for value in ('oldLedger', 'newLedger'):
                with self.subTest(value=value, text=text):
                    self.assertNotIn(value, path_components(text))
                    self.assertEqual(classify(text, *at(text, value)), ('residual', None))



class SedShellBoundaries(unittest.TestCase):
    left = 'auditLeafNode'
    right = 'auditBranchNode'

    def variants(self, command):
        return (command, json.dumps({'command': command}))

    def assert_script(self, command, values=None):
        serialized_slashes = json.dumps({'command': command}).replace('/', '\\/')
        for text in (*self.variants(command), serialized_slashes):
            for value in values or (self.left, self.right):
                with self.subTest(command=command, value=value, serialized=text != command):
                    self.assertNotIn(value, path_components(text))
                    self.assertEqual(classify(text, *at(text, value)), ('residual', None))
                    self.assertEqual(judge_occurrence(text, *at(text, value), common=False),
                                     (True, 'residual', None))

    def assert_path(self, command, value=None):
        value = value or self.left
        for text in self.variants(command):
            with self.subTest(command=command, serialized=text != command):
                self.assertIn(value, path_components(text))
                self.assertEqual(classify(text, *at(text, value)), ('ident', 'path'))

    def test_attached_options_preserve_input_and_script_file_paths(self):
        for option in ('-fscript.sed', '-nfscript.sed', '--file=script.sed',
                       '-es/firstOperand/otherOperand/', '-nes/firstOperand/otherOperand/',
                       '--expression=s/firstOperand/otherOperand/'):
            self.assert_path(f'sed {option} s/{self.left}/{self.right}/g')
        for option in ('-f', '-nf', '--file'):
            self.assert_path(f'sed {option} s/{self.left}/{self.right}/g input.txt')
        self.assert_path(f'sed -fs/{self.left}/{self.right}/g input.txt')

    def test_quoted_filename_is_never_a_sed_command(self):
        for program in ('git add', 'cat', "printf '%s'"):
            for quoted in (f'"sed \'s/{self.left}/{self.right}/g\'"',
                           f"'sed s/{self.left}/{self.right}/g'",
                           f'"notes; sed s/{self.left}/{self.right}/g"'):
                self.assert_path(f'{program} {quoted}')
        text = json.dumps({'file_path': f"sed 's/{self.left}/{self.right}/g'"})
        self.assertIn(self.left, path_components(text))
        self.assertEqual(classify(text, *at(text, self.left)), ('ident', 'path'))

    def test_json_quotes_escapes_and_offsets(self):
        for quote in ("'", '"', ''):
            self.assert_script(f'sed {quote}s/{self.left}/{self.right}/{quote} file')
        command = f"sed 's/prefix\\/{self.left}/{self.right}/' file"
        self.assert_script(command, [self.right])
        self.assert_path(command)
        # Decoding JSON must not confuse a quoted filename with a command key.
        self.assert_path(f'cat "command: sed s/{self.left}/{self.right}/g"')
        self.assert_script(f"sed 's/{self.left}/{self.right}/' café.txt")

    def test_interleaved_options_and_bsd_suffix(self):
        for options in ("-e 's/firstOperand/otherOperand/' -n -e", '-i .bak',
                        "-i ''", '-i.bak', '-nE', '-ne', '--expression'):
            self.assert_script(f"sed {options} 's/{self.left}/{self.right}/g' file")
        self.assert_script(f"sed -f rules.sed -e 's/{self.left}/{self.right}/' file")
        self.assert_script(f"sed --expression='s/{self.left}/{self.right}/' file")
        self.assert_script(f"sed -- 's/{self.left}/{self.right}/' file")

    def test_addresses_and_compound_script(self):
        for script in (f'/marker/s/{self.left}/{self.right}/g',
                       f'1,/marker/s/{self.left}/{self.right}/g',
                       f'/start/,/end/!s/{self.left}/{self.right}/2g',
                       f's/{self.left}/{self.right}/; p',
                       f'p; s/{self.left}/{self.right}/',
                       f'1,4s/{self.left}/{self.right}/I'):
            self.assert_script(f"sed '{script}' file")

    def test_sed_text_and_filename_arguments_are_not_substitutions(self):
        for command in ('w', 'r', 'a', 'i', 'c', '#'):
            self.assert_path(f"sed '{command} notes; s/{self.left}/{self.right}/' file")
        self.assert_path(f"sed 'a\\\ns/{self.left}/{self.right}/' file")

    def test_command_positions_and_redirected_paths(self):
        for prefix in ('', 'cat file | ', 'cd app && ', 'true; ', '( ',
                       'LC_ALL=C ', '> output.txt '):
            suffix = ' )' if prefix == '( ' else ''
            self.assert_script(f"{prefix}/usr/bin/sed 's/{self.left}/{self.right}/' file{suffix}")
        self.assert_path(f"cat file > 'sed s/{self.left}/{self.right}/'")
        self.assert_path(f"cat >& sed 's/{self.left}/{self.right}/'")
        self.assert_path(f"sed 's/firstOperand/otherOperand/' > s/{self.left}/{self.right}/")
        self.assert_path(f"sed 's/firstOperand/otherOperand/' s/{self.left}/{self.right}/")


class Exclusions(unittest.TestCase):
    def kind(self, text, value, nth=0):
        return exclusion_kind(text, *at(text, value, nth))

    def test_hash(self):
        for value in ("$6$rounds=5$abc$def", "$2a$11$abcdef", "pbkdf2_sha256$36000$a$b", "{SHA}e982f17b", "sha1$1b$ed"):
            self.assertEqual(self.kind(f'password: "{value}"', value), "hash", value)
        self.assertIsNone(self.kind('password: "Pa$$w0rd"', "Pa$$w0rd"))

    def test_non_credential(self):
        self.assertEqual(self.kind("New PIN: 876543", "876543"), "non_credential")
        self.assertEqual(self.kind('csrf_token="dummytoken"', "dummytoken"), "non_credential")
        self.assertEqual(self.kind("SSN: 557-24-7186", "557-24-7186"), "non_credential")
        self.assertIsNone(self.kind("| Password/PIN | River95!", "River95!"))

    def test_placeholders(self):
        for value in ("<define>", "[FUZZ]", "xxx", "ghp_-XXX", "YOURPASSWROD", "__TODO:_GENERATE_YOUR_OWN_VALUE_HERE__"):
            self.assertIsNotNone(self.kind(f'password: "{value}"', value), value)

    def test_screen_strings(self):
        self.assertEqual(self.kind("'password' => 'lozinka'", "lozinka"), "descriptor")
        self.assertEqual(self.kind('"password": "Password:"', "Password:"), "descriptor")
        self.assertEqual(self.kind('"TITLE_CHANGE_PASSWORD": "Endre'  ' x"', "Endre"), "descriptor")
        self.assertIsNone(self.kind('"password": "senha123"', "senha123"))

    def test_examples(self):
        self.assertEqual(self.kind("For example:\n\n```\nAuthorization: Bearer abc123XYZ\n```", "abc123XYZ"), "doc_example")
        self.assertIsNone(self.kind("user@example.com\npassword: hunter2", "hunter2"))
        self.assertIsNone(self.kind("Host: example.com\nAuthorization: Bearer abc123XYZ", "abc123XYZ"))
        # the announcement must be on the line above, not somewhere further up
        self.assertIsNone(self.kind("Example:\n```\nGET /\n```\nnext\npassword: hunter2", "hunter2"))

    def test_literals_stay(self):
        for text, value, nth in [("POSTGRES_PASSWORD=password", "password", 0), ("wrong_password = 'wrong_password'", "wrong_password", 1),
                                 ("password=password", "password", 1), ("api_key='test_api_key'", "test_api_key", 0)]:
            self.assertIsNone(self.kind(text, value, nth), text)

    def test_variable(self):
        self.assertEqual(exclusion_kind("self.password = password", *at("self.password = password", "password", 1)), "code")


class Literals(unittest.TestCase):
    def test_code_is_not_a_literal(self):
        for text, value in [("token = Token::SAR;", "Token::SAR"), ("password: string;", "string"),
                            ("'password': PasswordField('x')", "PasswordField"), ("$pass = ConvertTo-SecureString 'x'", "ConvertTo-SecureString")]:
            self.assertFalse(is_literal(text, *at(text, value)), text)

    def test_config_values_are(self):
        for text, value in [("Password = dljxwjsx", "dljxwjsx"), ("x?api_key=abc123", "abc123"), ("  password: mohgj", "mohgj"),
                            ("user=virtual password=rmlsw", "rmlsw")]:
            self.assertTrue(is_literal(text, *at(text, value)), text)


class Spans(unittest.TestCase):
    def test_escaped_quotes(self):
        text = '$password = \\"goodspec\\";'
        a = text.index("\\")
        b = text.rindex("\\") + 1
        self.assertEqual(text[slice(*normalize_span(text, a, b))], "goodspec")

    def test_types(self):
        self.assertEqual(position_type("Authorization: Bearer x", len("Authorization: Bearer ")), "TOKEN")
        self.assertEqual(position_type("client_secret=x", len("client_secret=")), "SECRET")


if __name__ == "__main__":
    unittest.main()
