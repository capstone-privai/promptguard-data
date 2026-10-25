"""Deterministic synthetic values for ML training templates (docs/README_ml-train-plan.md, 4절).

Every value comes from a shake_256 stream over (VERSION, seed), so a template builds to the same bytes on any
machine and Python version. The values follow public formats (prefixes, alphabets, lengths, checksums) but are
generated from a public rule: never use them for authentication.

  SECRET_KINDS  kind -> (gold type, generator). Service formats, password families, generic secrets whose
                length and alphabet vary, private keys.
  PROFILE       value_profile "mltrain": the base kinds of the metric1 templates (password, token, api_key,
                secret, hex_secret) drawn from the varied families instead of one fixed shape.
  NEGATIVE_KINDS  kind -> generator for {{neg:kind}}: values that are not gold (LABELING.md 정답이 아닌 것).
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib

VERSION = "metric1-v0.1"  # same as dataset_build.VERSION; split and template name in the seed keep values apart

LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
HEX = "0123456789abcdef"
ALNUM = LOWER + UPPER + DIGITS
B64 = ALNUM + "+/"
B64URL = ALNUM + "-_"
BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
SYMBOLS = "!#$%&*+-=?@^_~.,:;/"


class Draw:
    """A deterministic stream of choices for one seed."""

    def __init__(self, seed: str):
        self.seed, self.buf, self.pos, self.block = seed, b"", 0, 0

    def _bytes(self, n: int) -> bytes:
        while self.pos + n > len(self.buf):
            self.buf += hashlib.shake_256(f"{VERSION}:{self.seed}:{self.block}".encode()).digest(256)
            self.block += 1
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def int(self, n: int) -> int:
        """0 <= x < n."""
        return int.from_bytes(self._bytes(4), "big") % n

    def between(self, lo: int, hi: int) -> int:
        return lo + self.int(hi - lo + 1)

    def choice(self, seq):
        return seq[self.int(len(seq))]

    def weighted(self, pairs):
        total = sum(w for _, w in pairs)
        x = self.int(total)
        for item, w in pairs:
            if x < w:
                return item
            x -= w
        raise AssertionError

    def chars(self, n: int, alphabet: str) -> str:
        return "".join(alphabet[b % len(alphabet)] for b in self._bytes(n))

    def raw(self, n: int) -> bytes:
        return self._bytes(n)


# Neutral words people put in passwords and passphrases (hand-picked; no word list of leaked passwords).
WORDS = tuple("""
apple amber anchor arrow autumn badger bamboo banana basil beacon bear birch bison blossom breeze bridge
brook bronze butter cactus camel candle canyon carbon castle cedar cherry cinder citrus clover cobalt comet
copper coral cosmos cotton coyote crane crystal dagger daisy delta desert dolphin dragon eagle ember falcon
fennel fern ferret forest fossil fox galaxy garden garnet ginger glacier granite grape gravel harbor hazel
helium heron hickory honey horizon island ivory jade jaguar jasmine juniper kettle kiwi koala lagoon lantern
lemon leopard lilac lily linen lizard lotus magnet mango maple marble meadow melon meteor mint monsoon moose
mosaic nebula nickel nutmeg oasis ocean olive onyx orange orbit orchid otter owl panda panther papaya parrot
peach pebble pepper pine planet plum polar poppy prairie puffin quartz quill rabbit radish raven reef ribbon
river robin rocket rose ruby saffron salmon sapphire satin seal shadow shell sierra silver sky slate snow
sparrow spice spruce squid star stone storm summer sunset swan tango thunder tiger timber topaz tulip tundra
turtle valley velvet violet walnut walrus willow winter wolf yellow zebra zephyr seoul busan jeju hangang
coffee latte mocha pizza noodle kimchi tofu biscuit cookie muffin pretzel waffle soccer tennis guitar piano
violin pixel vector kernel socket packet router cluster docker module python rust golang lambda
""".split())


# ---- passwords ---------------------------------------------------------------

# Hand-picked defaults and weak choices (vendor defaults, keyboard walks, the word "password"); not a leak list.
WEAK = ("admin", "root", "toor", "postgres", "mysql", "oracle", "guest", "test", "secret", "password", "passw0rd",
        "Password1", "password123", "P@ssw0rd", "admin123", "admin1234", "changeme", "letmein", "welcome",
        "Welcome1", "qwerty", "qwerty123", "qwer1234", "asdf1234", "1q2w3e4r", "12345678", "123456", "000000",
        "111111", "abc123", "iloveyou", "dragon", "monkey", "default", "ubuntu", "raspberry", "debian", "vagrant",
        "docker", "redis", "rabbitmq", "minio123", "minioadmin", "elastic", "kibana", "jenkins", "tomcat",
        "s3cr3t", "testtest", "dev", "devpass", "localdev", "pass1234", "hunter2", "trustno1", "master")
KEYBOARD = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890", "1q2w3e4r5t", "qazwsx", "!@#$%^&*")
LEET = {"a": "@", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7"}
# 두벌식: 한글 자모 -> 영문 자판 키
CHO = "rRseEfaqQtTdwWczxvg"
JUNG = ("k", "o", "i", "O", "j", "p", "u", "P", "h", "hk", "ho", "hl", "y", "n", "nj", "np", "nl", "b", "m", "ml", "l")
JONG = ("", "r", "R", "rt", "s", "sw", "sg", "e", "f", "fr", "fa", "fq", "ft", "fx", "fv", "fg", "a", "q", "qt", "t",
        "T", "d", "w", "c", "z", "x", "v", "g")


def password_random(d: Draw) -> str:
    n = d.weighted([(d.between(6, 9), 3), (d.between(10, 16), 5), (d.between(17, 24), 2), (d.between(25, 40), 1)])
    sets = d.weighted([((LOWER,), 1), ((LOWER, DIGITS), 2), ((LOWER, UPPER), 1), ((LOWER, UPPER, DIGITS), 4),
                       ((LOWER, UPPER, DIGITS, "S"), 4), ((HEX,), 1), ((UPPER, DIGITS), 1)])
    symbols = "".join(c for c in SYMBOLS if d.int(3) == 0) or "!"
    pools = [symbols if s == "S" else s for s in sets]
    chars = [d.choice(p) for p in pools] + [d.choice("".join(pools)) for _ in range(max(0, n - len(pools)))]
    for i in range(len(chars) - 1, 0, -1):  # shuffle so the required classes are not always in front
        j = d.int(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _hangul_keys(d: Draw, syllables: int) -> str:
    return "".join(d.choice(CHO) + d.choice(JUNG) + d.weighted([("", 3), (d.choice(JONG[1:]), 1)])
                   for _ in range(syllables))


def password_human(d: Draw) -> str:
    word = d.choice(WORDS)
    style = d.weighted([("cap_year_sym", 4), ("leet", 2), ("two_words", 2), ("keyboard", 1), ("hangul", 2),
                        ("word_digits", 2)])
    year = str(d.between(1985, 2026))
    sym = d.choice("!@#$%&*?.")
    if style == "cap_year_sym":
        return word.capitalize() + d.choice((year, year[2:])) + d.weighted([(sym, 3), ("", 1)])
    if style == "leet":
        return "".join(LEET.get(c, c) if d.int(2) else c for c in word.capitalize()) + d.choice(("", sym, year[2:]))
    if style == "two_words":
        return word.capitalize() + d.choice(WORDS).capitalize() + str(d.between(0, 99))
    if style == "keyboard":
        walk = d.choice(KEYBOARD)
        return walk[:d.between(6, len(walk))] + d.choice(("", sym, "!!"))
    if style == "hangul":
        return _hangul_keys(d, d.between(2, 4)) + d.choice(("", str(d.between(1, 9999)), sym))
    return word + str(d.between(1, 99999))


def password_weak(d: Draw) -> str:
    return d.choice(WEAK)


def passphrase(d: Draw) -> str:
    # Joined without spaces: label_rules.is_phrase reads a spaced run of common words as a descriptor.
    sep = d.choice(("-", "_", ".", ""))
    ws = [d.choice(WORDS) for _ in range(d.between(3, 5))]
    if sep == "":
        ws = [w.capitalize() for w in ws]
    if sep == ".":  # "a.b.c" is code to label_rules; a digit at the end keeps it a value
        return ".".join(ws) + str(d.between(1, 99))
    return sep.join(ws)


def password_encoded(d: Draw) -> str:
    n = d.between(16, 64)
    return d.weighted([(d.chars(n, HEX), 1), (base64.b64encode(d.raw(n * 3 // 4)).decode(), 1)])


def password_mix(d: Draw) -> str:
    family = d.weighted([(password_random, 35), (password_human, 30), (password_weak, 20), (passphrase, 10),
                         (password_encoded, 5)])
    return family(d)


# ---- generic secrets -----------------------------------------------------------

def generic(d: Draw, lo: int = 16, hi: int = 64) -> str:
    n = d.between(lo, hi)
    alphabet = d.weighted([(HEX, 3), (ALNUM, 4), (B64URL, 2), (B64, 1)])
    out = d.chars(n, alphabet)
    if alphabet == B64 and d.int(2):
        out = out[:len(out) - len(out) % 4] + "=" * d.int(3)
    return out


def generic_token(d: Draw) -> str:
    return d.weighted([(generic(d, 20, 64), 5), (jwt(d), 2), (d.chars(d.between(32, 48), ALNUM), 2)])


# ---- service formats -------------------------------------------------------------

def base62(n: int, width: int) -> str:
    out = ""
    for _ in range(width):
        n, r = divmod(n, 62)
        out = (DIGITS + UPPER + LOWER)[r] + out
    return out


def github(prefix: str):
    # ghp_ + 30 random + base62(crc32) 6: the checksum makes the value pass GitHub's own format check
    def gen(d: Draw) -> str:
        body = d.chars(30, ALNUM)
        return f"{prefix}_{body}{base62(zlib.crc32(body.encode()), 6)}"
    return gen


def github_pat(d: Draw) -> str:
    return f"github_pat_11{d.chars(20, BASE32 + DIGITS)}_{d.chars(59, ALNUM)}"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt(d: Draw) -> str:
    alg = d.choice(("HS256", "RS256", "ES256", "HS512"))
    header = {"alg": alg, "typ": "JWT"} if d.int(2) else {"typ": "JWT", "alg": alg, "kid": d.chars(8, HEX)}
    iat = 1_700_000_000 + d.int(90_000_000)
    claims = [("sub", d.weighted([(d.chars(d.between(6, 12), DIGITS), 1), (d.chars(24, HEX), 1)])), ("iat", iat),
              ("exp", iat + d.choice((900, 3600, 86400, 604800)))]
    claims += d.weighted([([], 1), ([("scope", d.choice(("read", "read write", "repo", "openid profile")))], 1),
                          ([("role", d.choice(("service_role", "authenticated", "admin")))], 1)])
    if d.int(2):
        claims.append(("iss", d.choice(("auth.example.invalid", "https://id.example.invalid/", "api"))))
    payload = dict(claims)
    sig = d.raw(64 if alg in ("HS512", "ES256") else 32 if alg == "HS256" else 256)
    return ".".join([b64url(json.dumps(header, separators=(",", ":")).encode()),
                     b64url(json.dumps(payload, separators=(",", ":")).encode()), b64url(sig)])


def _pem(label: str, der: bytes) -> str:
    body = base64.b64encode(der).decode()
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----"


def _der_len(n: int) -> bytes:
    return bytes([n]) if n < 128 else b"\x81" + bytes([n]) if n < 256 else b"\x82" + struct.pack(">H", n)


def _der(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(body)) + body


def _int(raw: bytes) -> bytes:
    return _der(0x02, b"\x00" + raw if raw[0] & 0x80 else raw)


def rsa_key(d: Draw) -> str:
    # The DER shape of an RSA-2048 key (PKCS#1 or PKCS#8) filled with random numbers; not a usable key.
    n = d.raw(256)
    parts = [_int(b"\x00"), _int(b"\xc0" + n[1:]), _int(b"\x01\x00\x01"), _int(d.raw(256)), _int(d.raw(128)),
             _int(d.raw(128)), _int(d.raw(128)), _int(d.raw(128)), _int(d.raw(128))]
    pkcs1 = _der(0x30, b"".join(parts))
    if d.int(2):
        return _pem("RSA PRIVATE KEY", pkcs1)
    algo = _der(0x30, bytes.fromhex("06092a864886f70d0101010500"))
    return _pem("PRIVATE KEY", _der(0x30, _int(b"\x00") + algo + _der(0x04, pkcs1)))


def ec_key(d: Draw) -> str:
    der = _der(0x30, _int(b"\x01") + _der(0x04, d.raw(32)) + bytes.fromhex("a00a06082a8648ce3d030107")
               + b"\xa1\x44\x03\x42\x00\x04" + d.raw(64))
    return _pem("EC PRIVATE KEY", der)


def ed25519_key(d: Draw) -> str:
    return _pem("PRIVATE KEY", bytes.fromhex("302e020100300506032b657004220420") + d.raw(32))


def _ssh_str(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


def openssh_key(d: Draw) -> str:
    pub = d.raw(32)
    pubkey = _ssh_str(b"ssh-ed25519") + _ssh_str(pub)
    check = d.raw(4)
    comment = f"{d.choice(('deploy', 'ci', 'dev', 'backup'))}@{d.choice(('build-01', 'laptop', 'bastion'))}".encode()
    priv = check + check + pubkey + _ssh_str(d.raw(32) + pub) + _ssh_str(comment)
    priv += bytes(range(1, 1 + (-len(priv)) % 8))
    blob = (b"openssh-key-v1\x00" + _ssh_str(b"none") + _ssh_str(b"none") + _ssh_str(b"") + struct.pack(">I", 1)
            + _ssh_str(pubkey) + _ssh_str(priv))
    body = base64.b64encode(blob).decode()
    return ("-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(body[i:i + 70] for i in range(0, len(body), 70))
            + "\n-----END OPENSSH PRIVATE KEY-----")


def private_key_mix(d: Draw) -> str:
    return d.weighted([(rsa_key, 4), (openssh_key, 3), (ec_key, 2), (ed25519_key, 1)])(d)


def slack_webhook(d: Draw) -> str:
    return (f"https://hooks.slack.com/services/T{d.chars(d.between(8, 10), BASE32[:26] + DIGITS)}"
            f"/B{d.chars(d.between(8, 10), BASE32[:26] + DIGITS)}/{d.chars(24, ALNUM)}")


def discord_webhook(d: Draw) -> str:
    return f"https://discord.com/api/webhooks/{d.between(1, 9)}{d.chars(17, DIGITS)}/{d.chars(68, B64URL)}"


# kind -> (gold type, generator). Types agree with label_rules.expected_type where the format decides it.
SECRET_KINDS = {
    # passwords
    "password_mix": ("PASSWORD", password_mix),
    "password_random": ("PASSWORD", password_random),
    "password_human": ("PASSWORD", password_human),
    "password_weak": ("PASSWORD", password_weak),
    "passphrase": ("PASSWORD", passphrase),
    # generic
    "generic_secret": ("SECRET", generic),
    "generic_token": ("TOKEN", generic_token),
    "jwt_any": ("TOKEN", jwt),
    # cloud
    "aws_access_key_id": ("ACCESS_KEY", lambda d: d.choice(("AKIA", "ASIA")) + d.chars(16, BASE32)),
    "aws_secret_access_key": ("SECRET", lambda d: d.chars(40, B64)),
    "aws_session_token": ("TOKEN", lambda d: "IQoJb3JpZ2luX2Vj" + d.chars(d.between(300, 420), B64)),
    "gcp_api_key": ("SECRET", lambda d: "AIza" + d.chars(35, B64URL)),
    "azure_storage_key": ("SECRET", lambda d: base64.b64encode(d.raw(64)).decode()),
    "digitalocean_token": ("TOKEN", lambda d: "dop_v1_" + d.chars(64, HEX)),
    "cloudflare_token": ("TOKEN", lambda d: d.chars(40, B64URL)),
    # code hosting, packages
    "github_classic": ("TOKEN", github("ghp")),
    "github_oauth": ("TOKEN", github("gho")),
    "github_app": ("TOKEN", lambda d: github(d.choice(("ghs", "ghu", "ghr")))(d)),
    "github_fine_grained": ("TOKEN", github_pat),
    "gitlab_pat": ("TOKEN", lambda d: "glpat-" + d.chars(20, B64URL)),
    "npm_token": ("TOKEN", lambda d: "npm_" + d.chars(36, ALNUM)),
    "pypi_token": ("TOKEN", lambda d: "pypi-AgEIcHlwaS5vcmc" + d.chars(d.between(60, 150), B64URL)),
    "dockerhub_pat": ("TOKEN", lambda d: "dckr_pat_" + d.chars(27, B64URL)),
    "huggingface_token": ("TOKEN", lambda d: "hf_" + d.chars(34, ALNUM)),
    # chat, mail, payments, AI
    "slack_bot": ("TOKEN", lambda d: f"xoxb-{d.chars(d.between(10, 13), DIGITS)}-{d.chars(13, DIGITS)}-{d.chars(24, ALNUM)}"),
    "slack_user": ("TOKEN", lambda d: f"xoxp-{d.chars(12, DIGITS)}-{d.chars(12, DIGITS)}-{d.chars(13, DIGITS)}-{d.chars(32, HEX)}"),
    "slack_webhook": ("SECRET", slack_webhook),
    "discord_webhook": ("SECRET", discord_webhook),
    "sendgrid_key": ("SECRET", lambda d: f"SG.{d.chars(22, B64URL)}.{d.chars(43, B64URL)}"),
    "twilio_auth_token": ("SECRET", lambda d: d.chars(32, HEX)),
    "twilio_api_key": ("SECRET", lambda d: "SK" + d.chars(32, HEX)),
    "stripe_secret": ("SECRET", lambda d: d.choice(("sk_live_", "sk_test_", "rk_live_")) + d.chars(d.between(24, 99), ALNUM)),
    "stripe_publishable": ("ACCESS_KEY", lambda d: d.choice(("pk_live_", "pk_test_")) + d.chars(d.between(24, 99), ALNUM)),
    "openai_key": ("SECRET", lambda d: d.weighted([("sk-proj-" + d.chars(d.between(80, 156), B64URL), 3),
                                                     ("sk-" + d.chars(48, ALNUM), 1)])),
    "anthropic_key": ("SECRET", lambda d: "sk-ant-api03-" + d.chars(93, B64URL) + "AA"),
    "datadog_api_key": ("SECRET", lambda d: d.chars(32, HEX)),
    "shopify_token": ("TOKEN", lambda d: d.choice(("shpat_", "shpss_")) + d.chars(32, HEX)),
    "postman_key": ("SECRET", lambda d: f"PMAK-{d.chars(24, HEX)}-{d.chars(34, HEX)}"),
    "mapbox_public": ("ACCESS_KEY", lambda d: "pk.eyJ1Ijoi" + d.chars(d.between(40, 60), B64URL) + "." + d.chars(22, B64URL)),
    # keys
    "private_key_any": ("PRIVATE_KEY", private_key_mix),
    "rsa_private_key": ("PRIVATE_KEY", rsa_key),
    "ec_private_key": ("PRIVATE_KEY", ec_key),
    "openssh_private_key": ("PRIVATE_KEY", openssh_key),
}

# value_profile "mltrain": what the base kinds of dataset_build.GENERATORS become
PROFILE = {"mltrain": {
    "password": "password_mix",
    "db_uri": "password_mix",
    "token": "generic_token",
    "api_key": "generic_secret",
    "secret": "generic_secret",
    "hex_secret": "generic_secret",
    "jwt": "jwt_any",
    "github_token": "github_classic",
    "slack_token": "slack_bot",
    "aws_access_key": "aws_access_key_id",
    "aws_secret_key": "aws_secret_access_key",
    "publishable_key": "stripe_publishable",
    "private_key": "private_key_any",
}}
# Families a value of a non-credential position may not come from (common strings; LABELING.md 퍼뜨림 기준)
NOT_COMMON = {"password_mix": "password_random"}


# ---- negatives ({{neg:kind}}) ------------------------------------------------------

def _uuid(d: Draw) -> str:
    h = d.chars(32, HEX)
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-{'89ab'[int(h[16], 16) % 4]}{h[17:20]}-{h[20:]}"


def _luhn(digits: str) -> str:
    total = 0
    for i, c in enumerate(reversed(digits)):
        n = int(c) * (2 if i % 2 == 0 else 1)
        total += n - 9 if n > 9 else n
    return digits + str(-total % 10)


def neg_redaction(d: Draw) -> str:
    return d.weighted([("*" * d.between(3, 16), 4), ("[REDACTED]", 2), ("<redacted>", 1), ("REDACTED", 1),
                       ("x" * d.between(4, 12), 1), ("X" * d.between(4, 12), 1), ("sk-..." + d.chars(4, HEX), 1),
                       ("ghp_..." + d.chars(4, ALNUM), 1), ("****" + d.chars(4, DIGITS), 1), ("…", 1),
                       ("#" * d.between(4, 10), 1), ("password_removed", 1)])


def neg_template(d: Draw) -> str:
    thing = d.choice(("token", "api-key", "password", "secret", "access-key", "key"))
    return d.weighted([(f"<your-{thing}>", 3), (f"<{thing}>", 2), (f"YOUR_{thing.upper().replace('-', '_')}", 3),
                       (f"your-{thing}-here", 2), (f"{{{{ .Values.{thing.replace('-', '')} }}}}", 1),
                       (f"<generate-with-openssl-rand-hex-{d.choice(('32', '64'))}>", 1),
                       (f"your-{thing}-change-this-in-production", 1), ("REPLACE_ME_PLACEHOLDER", 1),
                       (f"{{{{ secrets.{thing.upper().replace('-', '_')} }}}}", 1)])


def neg_reference(d: Draw) -> str:
    name = d.choice(("DB_PASSWORD", "API_KEY", "SECRET_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "REDIS_PASS",
                     "SMTP_PASSWORD", "STRIPE_SECRET_KEY", "JWT_SECRET", "PGPASSWORD"))
    return d.weighted([("${" + name + "}", 4), ("$" + name, 3), ("%" + name + "%", 1), ("{" + name.lower() + "}", 1),
                       (f'os.environ["{name}"]', 2), (f"process.env.{name}", 2), (f'os.getenv("{name}")', 1),
                       ("@" + name + "@", 1)])


def neg_code(d: Draw) -> str:
    return d.weighted([("getpass.getpass()", 1), ('kwargs.get("password")', 1), ('config["db"]["password"]', 1),
                       ("settings.secret_key", 1), ("self.api_key", 1), ("null", 1), ("None", 1), ("undefined", 1),
                       ("generate_password_hash(raw)", 1), ("read_secret(path)", 1), ("creds[0]", 1)])


DOC_EXAMPLES = ("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "EXAMPLE_TOKEN_123",
                "sk_test_EXAMPLE", "ghp_EXAMPLEexampleEXAMPLEexample0000")


def neg_doc_example(d: Draw) -> str:
    return d.choice(DOC_EXAMPLES)


def neg_descriptor(d: Draw) -> str:
    return d.choice(("new password", "your password", "temporary password", "Authentication token",
                     "current password", "API access key", "service account secret", "the shared secret"))


def neg_hash(d: Draw) -> str:
    salt = d.chars(16, ALNUM + "./")
    return d.weighted([(f"$6${salt}${d.chars(86, ALNUM + './')}", 3), (f"$2b$12${d.chars(53, ALNUM + './')}", 3),
                       (f"$argon2id$v=19$m=65536,t=3,p=4${d.chars(22, B64)}${d.chars(43, B64)}", 2),
                       (f"$y$j9T${d.chars(22, ALNUM + './')}${d.chars(43, ALNUM + './')}", 2),
                       (f"pbkdf2_sha256$600000${d.chars(22, ALNUM)}${base64.b64encode(d.raw(32)).decode()}", 1)])


def neg_identifier(d: Draw) -> str:
    return d.weighted([(_uuid(d), 4), ("req_" + d.chars(24, ALNUM), 1), (d.chars(40, HEX), 3),
                       (d.chars(d.choice((7, 12)), HEX), 1), (d.chars(12, DIGITS), 1),
                       (f"arn:aws:iam::{d.chars(12, DIGITS)}:role/{d.choice(('deploy', 'ci-runner', 'app'))}", 1),
                       (f"{d.chars(12, DIGITS)}-{d.chars(32, LOWER + DIGITS)}.apps.googleusercontent.com", 1),
                       ("Iv1." + d.chars(16, HEX), 1), (d.chars(26, DIGITS + UPPER), 1),
                       ("sha256:" + d.chars(64, HEX), 2)])


def neg_non_credential(d: Draw) -> str:
    return d.weighted([(d.chars(d.between(32, 64), B64URL), 3), (f"GA1.2.{d.chars(10, DIGITS)}.{d.chars(10, DIGITS)}", 1),
                       (d.chars(d.choice((4, 6)), DIGITS), 1), (_luhn("4" + d.chars(14, DIGITS)), 1),
                       (d.chars(3, DIGITS), 1)])


def neg_setting(d: Draw) -> str:
    return d.choice(("4096", "8192", "12", "8", "3600", "bearer", "Bearer", "sha256", "true", "300", "16"))


def neg_public_key(d: Draw) -> str:
    pub = base64.b64encode(_ssh_str(b"ssh-ed25519") + _ssh_str(d.raw(32))).decode()
    return d.weighted([(f"ssh-ed25519 {pub} {d.choice(('deploy', 'ci'))}@{d.choice(('host', 'laptop'))}", 2),
                       (_pem("PUBLIC KEY", bytes.fromhex("302a300506032b6570032100") + d.raw(32)), 1),
                       (_pem("CERTIFICATE", d.raw(d.between(300, 600))), 1)])


def neg_pem_header(d: Draw) -> str:
    return d.choice(("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----",
                     "-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----"))


# kind -> (generator, label_rules.exclusion_kind the value must get in place, or None when only the position
# makes it a non-credential)
NEGATIVE_KINDS = {
    "redaction": (neg_redaction, "redaction"),
    "template": (neg_template, "template"),
    "reference": (neg_reference, "reference"),
    "code": (neg_code, "code"),
    "doc_example": (neg_doc_example, "doc_example"),
    "descriptor": (neg_descriptor, "descriptor"),
    "empty": (lambda d: "", "empty"),
    "hash": (neg_hash, None),
    "identifier": (neg_identifier, None),
    "non_credential": (neg_non_credential, None),
    "setting": (neg_setting, None),
    "public_key": (neg_public_key, None),
    "pem_header": (neg_pem_header, None),
}


# ---- masks ({{mask:NAME}}) ---------------------------------------------------------

# The placeholder kind PromptGuard's Native Mod writes for a value, [KIND_n] (promptguard-claude-demoV0
# src/native-mod/hooks/register.mjs, kinds from src/detector/pgdetector/core.py CANONICAL_TYPES). Which kind the
# detector really reports depends on the adapter that found the value; this is the one its type_for() gives the format.
MASK_KIND_PREFIXES = [
    (("aws_",), "AWS_KEY"),
    (("github",), "GITHUB_TOKEN"),
    (("slack",), "SLACK_TOKEN"),
    (("jwt",), "JWT"),
    (("password", "passphrase", "db_uri"), "PASSWORD"),
    (("private_key", "rsa_private", "ec_private", "openssh_private"), "PRIVATE_KEY"),
    (("api_key", "openai", "anthropic", "gcp_api", "sendgrid", "postman", "datadog", "twilio", "stripe", "mapbox",
      "publishable"), "API_KEY"),
    (("token", "generic_token", "gitlab", "npm", "pypi", "dockerhub", "huggingface", "shopify", "digitalocean", "cloudflare"), "TOKEN"),
    (("secret", "hex_secret", "uuid_key", "discord", "azure", "generic_secret"), "SECRET"),
]
# {{TYPE=literal}}: gold type -> mask kind
MASK_KIND_OF_TYPE = {"PASSWORD": "PASSWORD", "TOKEN": "TOKEN", "SECRET": "SECRET", "ACCESS_KEY": "API_KEY",
                     "PRIVATE_KEY": "PRIVATE_KEY"}


def mask_kind(kind: str) -> str:
    for prefixes, mask in MASK_KIND_PREFIXES:
        if kind.startswith(prefixes):
            return mask
    return "CREDENTIAL"
