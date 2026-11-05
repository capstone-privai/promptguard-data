"""Cases for label_rules.py, one per rule that once went wrong.

Run from the repository root:
  python metric-detection/scripts/test_label_rules.py
"""
import unittest

from label_rules import classify, exclusion_kind, is_common, is_gold, is_literal, normalize_span, position_type


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

    def test_htpasswd(self):
        self.assert_slot("htpasswd -b .htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -bc /etc/nginx/.htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -c -b .htpasswd admin 1234", "1234")
        self.assert_slot("htpasswd -nb admin 1234", "1234")
        self.assert_not_slot("htpasswd -b .htpasswd admin 1234", "admin")
        self.assert_not_slot("htpasswd -nb admin 1234", "admin")
        self.assert_not_slot("htpasswd .htpasswd admin 1234", "1234")


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
