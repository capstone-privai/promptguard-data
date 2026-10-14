"""Format-preserving replacement of secret values.

A fake keeps everything a format checker could look at:
- length, separators and every fixed literal (vendor prefixes such as AKIA / xoxb- / AIzaSy, infixes such as
  OpenAI's T3BlbkFJ), taken from three sources: Kingfisher v1 rule regexes, prefixes learned from the data
  (format_hints.learn), and a short curated list (CURATED_PREFIXES / CURATED_INFIXES);
- the character class (upper / lower / digit) of every position and the narrowest pool of each class within
  its run (hex stays hex, base32 stays base32), plus per-position pools the rules or the data impose;
- checksums (GitHub, npm, Vercel, Atlassian, Bitbucket, Zuplo, Confluent, GitLab; algorithms from
  Kingfisher's liquid_filters.rs);
- the structure inside encodings: canonical base64 (incl. trailing-bit rules), JSON keys inside base64 and
  JWTs, DER/ASN.1 trees, PEM blocks and line layout, OpenSSH private keys, SSH public keys (keys are
  regenerated with the same algorithm, size and length);
- the set of format-specific Kingfisher v1 rules the value matches (no rule lost, none gained).
Every fake is checked against these before it is accepted; a value that cannot be faked raises ValueError.
Randomness comes from `secrets`, so a fake carries no information about the original beyond its format.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import secrets
import struct
import zlib
from collections import Counter
from pathlib import Path

import yaml

DIGITS = "0123456789"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
ALNUM = UPPER + LOWER + DIGITS
B64CHARS = set(ALNUM + "+/=")

# Vendor prefixes and infixes that must stay even where no rule fires (e.g. a truncated key). Each is a
# documented literal of the vendor's token format.
CURATED_PREFIXES = [
    "sk-proj-", "sk-ant-api03-", "sk-ant-", "sk-or-v1-", "sk-",            # OpenAI, Anthropic, OpenRouter
    "sk_live_", "sk_test_", "rk_live_", "rk_test_", "pk_live_", "pk_test_",  # Stripe
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "glpat-",         # GitHub, GitLab
    "xoxb-", "xoxp-", "xoxa-", "xoxs-", "xoxe-", "xoxr-", "xapp-",           # Slack
    "AKIA", "ASIA", "AGPA", "AIDA", "AROA", "ANPA", "ANVA", "AIza", "ya29.",  # AWS, Google
    "EAA", "SG.", "hf_", "npm_", "pypi-", "dop_v1_", "shpat_", "shpss_", "base64:", "django-insecure-",
]
CURATED_INFIXES = ["T3BlbkFJ", ":APA91b"]                                   # OpenAI, Firebase FCM
HEX_PREFIX = re.compile(r"0x(?=[0-9a-fA-F]{8,}$)")                           # 0x + hex: keep the 0x


# ---------------------------------------------------------------- small helpers

def char_class(c: str) -> str:
    if c in DIGITS:
        return "9"
    if c in UPPER:
        return "A"
    if c in LOWER:
        return "a"
    return "."


def shape(s: str) -> str:
    """upper -> A, lower -> a, digit -> 9, others kept, runs compressed. Safe to print."""
    out, prev, n = [], None, 0
    for c in s:
        k = char_class(c)
        if k == ".":
            k = c if c.isascii() and c.isprintable() else "?"
        if k == prev:
            n += 1
            continue
        if prev is not None:
            out.append(prev if n == 1 else f"{prev}{{{n}}}")
        prev, n = k, 1
    if prev is not None:
        out.append(prev if n == 1 else f"{prev}{{{n}}}")
    return "".join(out)


def entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _pick(pool: str) -> str:
    return pool[secrets.randbelow(len(pool))]


# ---------------------------------------------------------------- checksums (Kingfisher liquid filters)

B62 = DIGITS + UPPER + LOWER  # encode_base62 alphabet in crates/kingfisher-rules/src/liquid_filters.rs
B36 = DIGITS + LOWER


def base_n(value: int, alphabet: str, width: int) -> str:
    out = ""
    while value:
        value, r = divmod(value, len(alphabet))
        out = alphabet[r] + out
    return out.rjust(width, alphabet[0])


def crc32(s: str) -> int:
    return zlib.crc32(s.encode()) & 0xFFFFFFFF


CHECKSUM_FORMATS = [
    # name, regex (groups: 1 = checksum input, 2 = checksum), checksum function
    ("github-classic", r"gh[pousr]_([A-Za-z0-9]{30})([A-Za-z0-9]{6})", lambda b: base_n(crc32(b), B62, 6)),
    ("npm", r"npm_([A-Za-z0-9]{30})([A-Za-z0-9]{6})", lambda b: base_n(crc32(b), B62, 6)),
    ("vercel", r"vc[pikra]_([A-Za-z0-9_-]{50})([A-Za-z0-9]{6})", lambda b: base_n(crc32(b), B62, 6)),
    ("github-fine", r"(github_pat_[0-9][A-Za-z0-9]{21}_[A-Za-z0-9]{43})([A-Za-z2-7]{8})[A-Za-z0-9]{8}",
     lambda b: base64.b32encode(hashlib.sha256(b.encode()).digest()).decode()[:8]),
    ("atlassian", r"(ATATT3xFfGF0[A-Za-z0-9_-]{20,800}=)([0-9A-Fa-f]{8})", lambda b: f"{crc32(b):08x}"),
    ("bitbucket-app", r"(ATCTT3xFfGN0[A-Za-z0-9_-]{80,800}=)([0-9A-Fa-f]{8})", lambda b: f"{crc32(b):08x}"),
    ("bitbucket-atbb", r"(ATBB[A-Za-z0-9]{24})([0-9A-Fa-f]{8})", lambda b: f"{crc32(b):08x}"),
    ("zuplo", r"(?i:zpka_)([A-Za-z0-9]{32})_([0-9A-Fa-f]{8})", lambda b: f"{crc32(b):08x}"),
    ("confluent", r"(?i:cflt)([A-Za-z0-9+/]{54})([A-Za-z0-9+/]{6})",
     lambda b: base64.b64encode(crc32(b).to_bytes(4, "little")).decode()[:6]),
    ("gitlab-v2", r"(glpat-[0-9A-Za-z_-]{27,300}\.01\.[0-9a-zA-Z]{2})([0-9a-z]{7})", lambda b: base_n(crc32(b), B36, 7)),
]
CHECKSUM_FORMATS = [(n, re.compile(p), f) for n, p, f in CHECKSUM_FORMATS]


def checksum_valid(v: str) -> str | None:
    for name, rx, fn in CHECKSUM_FORMATS:
        m = rx.fullmatch(v)
        if m and fn(m.group(1)).lower() == m.group(2).lower():
            return name
    return None


def checksum_span(v: str, name: str | None) -> tuple[int, int]:
    for n, rx, _ in CHECKSUM_FORMATS:
        if n == name:
            return rx.fullmatch(v).span(2)
    return (0, 0)


def fix_checksum(fake: str, name: str, original: str) -> str:
    """Recompute the checksum of fake; hex checksums keep the original's letter case."""
    for n, rx, fn in CHECKSUM_FORMATS:
        if n != name:
            continue
        m = rx.fullmatch(fake)
        if not m:
            return fake
        ck = fn(m.group(1))
        orig = rx.fullmatch(original).group(2)
        if re.fullmatch(r"[0-9A-F]+", orig) and re.search(r"[A-F]", orig):
            ck = ck.upper()
        return fake[:m.start(2)] + ck + fake[m.end(2):]
    raise KeyError(name)


# ---------------------------------------------------------------- Kingfisher v1 rules as a format oracle

POSIX = {"alnum": "a-zA-Z0-9", "alpha": "a-zA-Z", "digit": "0-9", "lower": "a-z", "upper": "A-Z",
         "xdigit": "0-9A-Fa-f", "blank": r" \t", "space": r"\s", "punct": r"!-/:-@\[-`{-~", "word": r"\w"}


def to_python(p: str) -> tuple[str, str]:
    """Rust regex -> Python. Returns (pattern without global flags, global flags)."""
    p = re.sub(r"\[:(\w+):\]", lambda m: POSIX[m.group(1)], p)
    p = re.sub(r"\(\?<(?![=!])", "(?P<", p)
    flags = "".join(sorted(set("".join(re.findall(r"\(\?([imsx]+)\)", p)))))
    p = re.sub(r"\(\?[imsx]+\)", "", p)
    return p, flags


def first_capture(p: str, xmode: bool) -> str | None:
    """Source of the first unnamed capture group (Kingfisher reports that group as the secret)."""
    i, n, start, stack = 0, len(p), None, []
    while i < n:
        c = p[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            j = i + 1
            if j < n and p[j] == "^":
                j += 1
            if j < n and p[j] == "]":
                j += 1
            while j < n and p[j] != "]":
                if p[j] == "\\":
                    j += 2
                    continue
                if p[j] == "[" and j + 1 < n and p[j + 1] == ":":
                    j = p.index(":]", j) + 2
                    continue
                j += 1
            i = j + 1
            continue
        if xmode and c == "#":
            nl = p.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue
        if c == "(":
            unnamed = not p.startswith("(?", i)
            stack.append(unnamed and start is None)
            if unnamed and start is None:
                start = i + 1
        elif c == ")" and stack and stack.pop():
            return p[start:i]
        i += 1
    return None


def literal_prefixes(rx: re.Pattern, limit: int = 64, maxlen: int = 24) -> set[str]:
    """Every literal string the pattern must start with (expanding alternations and small literal classes)."""
    from re import _constants as C
    from re import _parser as P

    def walk(items, prefixes):
        for op, av in items:
            if op is C.LITERAL:
                prefixes = {p + chr(av) for p in prefixes}
            elif op is C.SUBPATTERN:
                prefixes, lit = walk(av[-1], prefixes)
                if not lit:
                    return prefixes, False
            elif op is C.BRANCH:
                new, all_lit = set(), True
                for alt in av[1]:
                    got, lit = walk(alt, prefixes)  # a non-literal branch still contributes its literal start
                    new |= got
                    all_lit &= lit
                prefixes = new
                if not all_lit:
                    return prefixes, False
            elif op is C.IN and len(av) <= 12 and all(o is C.LITERAL for o, _ in av):
                prefixes = {p + chr(a) for p in prefixes for _, a in av}
            elif op is C.AT:
                continue
            else:
                return prefixes, False
            if len(prefixes) > limit or any(len(p) > maxlen for p in prefixes):
                return prefixes, False
        return prefixes, True

    try:
        tree = P.parse(rx.pattern, rx.flags)
    except Exception:
        return set()
    got, _ = walk(list(tree), {""})
    return {p for p in got if len(p) >= 2}


class Oracle:
    """Kingfisher v1 rules whose capture says something about a value's format."""

    def __init__(self, kingfisher_v1: Path):
        self.rules = []
        for f in sorted((kingfisher_v1 / "crates/kingfisher-rules/data/rules").glob("*.yml")):
            for r in (yaml.safe_load(f.read_text()) or {}).get("rules", []):
                src, flags = to_python(r["pattern"])
                # rules with only named groups (JWT, PEM, connection strings) report the whole match
                cap = first_capture(src, "x" in flags) or src
                try:
                    rx = re.compile(f"(?{flags})(?:{cap})" if flags else f"(?:{cap})")
                except re.error:
                    continue
                req = r.get("pattern_requirements") or {}
                self.rules.append({"id": r["id"], "rx": rx, "prefixes": literal_prefixes(rx),
                                   "min_entropy": r.get("min_entropy"), "min_digits": req.get("min_digits"),
                                   "min_lowercase": req.get("min_lowercase"),
                                   "min_uppercase": req.get("min_uppercase")})
        self.generic = self._drop_generic()
        self.by_id = {r["id"]: r for r in self.rules}

    def _drop_generic(self) -> list[str]:
        """Drop rules whose capture accepts random strings: their meaning lives in the context keywords
        around the value, not in the value's format."""
        import random
        rnd = random.Random(0)
        alphabets = [ALNUM, DIGITS + "abcdef", DIGITS + "ABCDEF", UPPER + DIGITS, ALNUM + "+/", ALNUM + "-_",
                     "".join(chr(c) for c in range(33, 127))]
        probes = ["".join(rnd.choice(a) for _ in range(n)) for n in list(range(6, 41, 2)) + list(range(44, 129, 8))
                  for a in alphabets for _ in range(2)]
        generic = {r["id"] for r in self.rules if any(self._ok(r, x) for x in probes)}
        self.rules = [r for r in self.rules if r["id"] not in generic]
        return sorted(generic)

    @staticmethod
    def _ok(rule, v: str) -> bool:
        if not rule["rx"].fullmatch(v):
            return False
        if rule["min_digits"] and sum(c in DIGITS for c in v) < rule["min_digits"]:
            return False
        if rule["min_lowercase"] and sum(c in LOWER for c in v) < rule["min_lowercase"]:
            return False
        if rule["min_uppercase"] and sum(c in UPPER for c in v) < rule["min_uppercase"]:
            return False
        if rule["min_entropy"] and entropy(v) < rule["min_entropy"]:
            return False
        return True

    def match(self, v: str, rules=None) -> frozenset:
        return frozenset(r["id"] for r in (self.rules if rules is None else rules) if self._ok(r, v))

    def subset(self, ids) -> list:
        return [self.by_id[i] for i in ids]


# ---------------------------------------------------------------- base64

def b64_decode(seg: str) -> tuple[bytes, str, bool] | None:
    """Decode a canonical base64 / base64url string: (bytes, alphabet, padded), or None."""
    if not seg or not re.fullmatch(r"[A-Za-z0-9+/_-]+={0,2}", seg):
        return None
    url = "-" in seg or "_" in seg
    if url and ("+" in seg or "/" in seg):
        return None
    padded = seg.endswith("=")
    body = seg.rstrip("=")
    if len(body) % 4 == 1 or (padded and len(seg) % 4):
        return None
    try:
        raw = (base64.urlsafe_b64decode if url else base64.b64decode)(body + "=" * (-len(body) % 4))
    except (binascii.Error, ValueError):
        return None
    if b64_encode(raw, "url" if url else "std", padded) != seg:
        return None  # non-zero trailing bits
    return raw, "url" if url else "std", padded


def b64_encode(raw: bytes, alphabet: str, padded: bool) -> str:
    s = (base64.urlsafe_b64encode if alphabet == "url" else base64.b64encode)(raw).decode()
    return s if padded else s.rstrip("=")


def printable(raw: bytes) -> str | None:
    try:
        t = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return t if t and all(c.isprintable() or c in "\r\n\t" for c in t) else None


# ---------------------------------------------------------------- class-preserving text

def class_pools(run: str) -> dict[str, str]:
    """Narrowest pool per character class over one alphanumeric run (erring narrow stays a valid instance)."""
    up = {c for c in run if c in UPPER}
    lo = {c for c in run if c in LOWER}
    dg = {c for c in run if c in DIGITS}
    return {
        "A": "ABCDEF" if up <= set("ABCDEF") else UPPER,
        "a": "abcdef" if lo <= set("abcdef") else LOWER,
        "9": "234567" if dg and dg <= set("234567") and not (up and lo) and len(run) >= 16 else DIGITS,
    }


def class_preserving(s: str, keep: set[int] | None = None, allowed: dict[int, str] | None = None) -> str:
    """Replace each ASCII alphanumeric by one of the same class from its class pool within the run.

    keep: positions that stay. allowed: extra per-position restriction. Non-alphanumerics stay. A digit run
    that does not start with 0 keeps a non-zero first digit.
    """
    keep = keep or set()
    allowed = allowed or {}
    out = list(s)
    for m in re.finditer(r"[A-Za-z0-9]+", s):
        run = m.group()
        # pools come from the characters that change: a kept prefix such as 0x must not widen hex to a-z
        pools = class_pools("".join(c for k, c in enumerate(run) if m.start() + k not in keep) or run)
        for k, c in enumerate(run):
            i = m.start() + k
            if i in keep:
                continue
            same = pools[char_class(c)]
            if i in allowed:
                same = "".join(x for x in same if x in allowed[i]) or c
            if c in DIGITS and c != "0" and (i == 0 or s[i - 1] not in DIGITS):
                same = same.replace("0", "") or same
            out[i] = _pick(same)
    return "".join(out)


JSON_STR = re.compile(r'"((?:[^"\\]|\\.)*)"(\s*:)?|(?<=:)(\s*)(-?\d+(?:\.\d+)?)')
JSON_KEEP_VALUES = {"alg", "typ", "cty", "enc", "zip", "crv", "kty", "use"}
JOSE_HEADER_KEYS = JSON_KEEP_VALUES | {"kid", "x5t", "x5t#S256", "x5u", "jku", "jwk", "crit", "b64"}
JSON_TIME_KEYS = {"iat", "exp", "nbf", "auth_time", "updated_at", "created_at"}


def fake_json_text(t: str) -> str:
    """Keep keys, literals and layout; replace string and number values with the same length and classes.

    Header fields (alg, typ, ...) stay. Time claims keep their first 4 digits so they stay plausible.
    """
    out, last, key = [], 0, None
    for m in JSON_STR.finditer(t):
        out.append(t[last:m.start()])
        if m.group(4) is not None:  # a number value
            num = m.group(4)
            if key in JSON_TIME_KEYS:
                digits = [i for i, c in enumerate(num) if c.isdigit()]
                keep = set(digits[:4])
            else:
                keep = set()
            out.append(m.group(3) + class_preserving(num, keep=keep))
            last = m.end()
            continue
        content = m.group(1)
        if m.group(2):
            key = content
            out.append(m.group(0))
        elif key in JSON_KEEP_VALUES:
            out.append(m.group(0))
        else:
            parts = re.split(r"(\\u[0-9a-fA-F]{4}|\\.)", content)
            out.append('"' + "".join(p if p.startswith("\\") else class_preserving(p) for p in parts) + '"')
        last = m.end()
    out.append(t[last:])
    return "".join(out)


def fake_json_prefix(t: str) -> str:
    """fake_json_text for JSON cut anywhere: a trailing unterminated string value is faked too (a cut key
    name stays, like every key)."""
    last, key = 0, None
    for m in JSON_STR.finditer(t):
        last = m.end()
        if m.group(2):
            key = m.group(1)
    out = fake_json_text(t[:last])
    tail = t[last:]
    q = tail.find('"')
    if q < 0:
        return out + tail
    before = (t[:last] + tail[:q]).rstrip()
    content = tail[q + 1:]
    if before.endswith(":") and key not in JSON_KEEP_VALUES:
        parts = re.split(r"(\\u[0-9a-fA-F]{0,4}|\\.?)", content)
        content = "".join(p if p.startswith("\\") else class_preserving(p) for p in parts)
    return out + tail[:q + 1] + content


B64_STD = UPPER + LOWER + DIGITS + "+/"
B64_URL = UPPER + LOWER + DIGITS + "-_"


def b64_prefix_decode(seg: str, alphabet: str) -> tuple[bytes, int, int]:
    """Bytes fully encoded by seg (any length, no padding), plus the k leftover bits (k, value)."""
    table = (B64_URL if alphabet == "url" else B64_STD)
    val = 0
    for c in seg:
        val = val << 6 | table.index(c)
    k = len(seg) * 6 % 8
    return (val >> k).to_bytes(len(seg) * 6 // 8, "big"), k, val & ((1 << k) - 1)


def b64_prefix_encode(raw: bytes, k: int, bits: int, alphabet: str) -> str:
    table = (B64_URL if alphabet == "url" else B64_STD)
    n = (len(raw) * 8 + k) // 6
    val = int.from_bytes(raw, "big") << k | bits
    return "".join(table[val >> 6 * (n - 1 - i) & 63] for i in range(n))



def _json_chunks(t: str) -> list[str]:
    """Split text into top-level JSON objects (the last may be cut); text outside objects is its own chunk."""
    out, start, depth, in_str, esc = [], 0, 0, False, False
    for i, c in enumerate(t):
        if in_str:
            esc, in_str = (False, in_str) if esc else (c == "\\", c != '"')
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                out.append(t[start:i + 1])
                start = i + 1
    if start < len(t):
        out.append(t[start:])
    return out


def _is_header_json(t: str) -> bool:
    """A JOSE header, complete or cut: every key a header field, a cut key a prefix of one."""
    keys = json_keys(t)
    tail_key = re.search(r'[{,]\s*"([^"]*)$', t)
    if tail_key and not any(k.startswith(tail_key.group(1)) for k in JOSE_HEADER_KEYS):
        return False
    return set(keys) <= JOSE_HEADER_KEYS and (bool(keys) or bool(tail_key))


def fake_jose_segment(seg: str) -> str | None:
    """Fake one base64url segment that starts with eyJ ('{"'), cut at any length.

    JOSE headers stay (public metadata, as in full JWTs). Payload JSON keeps keys and layout, values change
    (fake_json_prefix). Bytes after the readable JSON are random. Leftover bits of a cut last character keep
    the classes they allow: when every printable character they allow is of one class (say a-d), they are
    redrawn from that whole class, otherwise they stay.
    """
    alphabet = "std" if re.search(r"[+/]", seg) else "url"
    if not re.fullmatch(r"[A-Za-z0-9_-]+|[A-Za-z0-9+/]+", seg):
        return None
    raw, k, bits = b64_prefix_decode(seg, alphabet)
    text, n = None, len(raw)
    for cut in range(len(raw), max(len(raw) - 4, 0) - 1, -1):
        try:
            text = raw[:cut].decode("utf-8")
            n = cut
            break
        except UnicodeDecodeError:
            continue
    if not text or not text.startswith("{"):
        return None
    good = len(text)
    for i, c in enumerate(text):
        if not (c.isprintable() or c in "\r\n\t"):
            good = i
            break
    readable = text[:good]
    fake = []
    for chunk in _json_chunks(readable):
        fake.append(chunk if _is_header_json(chunk) else fake_json_prefix(chunk))
    new = "".join(fake).encode("utf-8")
    rest = len(raw) - len(readable.encode("utf-8"))
    new += secrets.token_bytes(rest)
    if rest or n < len(raw):
        bits = secrets.randbelow(1 << k) if k else 0
    elif k:
        allowed = [c for c in map(chr, range(32, 127)) if ord(c) >> (8 - k) == bits]
        classes = {char_class(c) for c in allowed}
        if len(classes) == 1 and classes != {"."}:
            pool = {"A": UPPER, "a": LOWER, "9": DIGITS}[classes.pop()]
            bits = ord(_pick(pool)) >> (8 - k)
    return b64_prefix_encode(new, k, bits, alphabet)


JOSE_SEGMENT = re.compile(r"eyJ[A-Za-z0-9_-]+")


def keep_jose_headers(v: str, f: str) -> str:
    """Put back every complete JOSE header segment of v that a fake path changed (a JWT glued to other
    characters, inside a URL): headers are public and every JWT keeps its own."""
    for m in JOSE_SEGMENT.finditer(v):
        seg = m.group()
        raw = b64_prefix_decode(seg, "url")[0]
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if t.endswith("}") and _is_header_json(t) and is_json(t) and f[m.start():m.end()] != seg:
            f = f[:m.start()] + seg + f[m.end():]
    return f


def jws_alphabet(seg: str) -> str:
    """JWT segments are base64url; a segment without - or _ is still url unless it shows + or /."""
    return "std" if re.search(r"[+/]", seg) else "url"


JOSE_ANY = re.compile(r"(?P<pre>[A-Za-z]{1,8}\.)?(?P<body>[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*){0,2})")


def json_keys(t: str) -> list[str]:
    return [m.group(1) for m in JSON_STR.finditer(t) if m.group(2)]


def json_has_payload(t: str) -> bool:
    """False for JSON holding only header fields (alg/typ/...): nothing in it can be a secret."""
    for m in JSON_STR.finditer(t):
        pass
    try:
        j = json.loads(t)
    except ValueError:
        return True
    return not (isinstance(j, dict) and j and set(j) <= JSON_KEEP_VALUES)


def is_json(t: str) -> bool:
    try:
        json.loads(t)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- binary structures

def der_parse(b: bytes, i: int = 0, end: int | None = None):
    """Yield (tag, header_start, content_start, content_end) for TLVs in b[i:end]; raise ValueError if bad."""
    end = len(b) if end is None else end
    while i < end:
        tag = b[i]
        if tag & 0x1F == 0x1F:
            raise ValueError("high tag")
        if i + 1 >= end:
            raise ValueError("short")
        ln = b[i + 1]
        j = i + 2
        if ln & 0x80:
            k = ln & 0x7F
            if k == 0 or k > 4 or j + k > end:
                raise ValueError("length")
            ln = int.from_bytes(b[j:j + k], "big")
            j += k
        if j + ln > end:
            raise ValueError("overrun")
        yield tag, i, j, j + ln
        i = j + ln


STRING_TAGS = {0x0C, 0x12, 0x13, 0x14, 0x16, 0x1A, 0x1E}
KEEP_TAGS = {0x01, 0x05, 0x06, 0x17, 0x18}  # BOOLEAN, NULL, OID, UTCTime, GeneralizedTime


def der_fake(b: bytes) -> bytes:
    """Same TLV tree; tags, lengths, OIDs, times and small integers kept; key material and text replaced."""
    out = bytearray(b)

    def walk(i, end):
        for tag, h, c, e in list(der_parse(b, i, end)):
            if tag & 0x20:  # constructed
                try:
                    list(der_parse(b, c, e))
                except ValueError:  # a broken subtree (pasted and cut): as der-partial
                    keep = {c + k for k in _der_header_bytes(b[c:e])}
                    for k in range(c, e):
                        if k not in keep:
                            out[k] = secrets.randbelow(256)
                    continue
                walk(c, e)
            elif tag in KEEP_TAGS:
                continue
            elif tag == 0x02:  # INTEGER: small ones (versions) stay
                if e - c > 2:
                    new = bytearray(secrets.token_bytes(e - c))
                    new[0] = (new[0] & 0x7F) | (b[c] & 0x80)
                    if b[c] == 0 and e - c > 1:
                        new[0] = 0
                        new[1] |= 0x80 if b[c + 1] & 0x80 else 0
                    elif new[0] == 0 and e - c > 1:
                        new[0] = 1
                    out[c:e] = new
            elif tag in (0x03, 0x04):  # BIT STRING / OCTET STRING: recurse if it wraps DER
                s = c + (1 if tag == 0x03 else 0)
                try:
                    list(der_parse(b, s, e))
                    if e > s and b[s] in (0x30, 0x02, 0x04):
                        walk(s, e)
                        continue
                except ValueError:
                    pass
                out[s:e] = secrets.token_bytes(e - s)
            elif tag in STRING_TAGS:
                t = b[c:e].decode("latin1")
                out[c:e] = class_preserving(t).encode("latin1")
            else:
                out[c:e] = secrets.token_bytes(e - c)

    walk(0, len(b))
    return bytes(out)


def regenerate_der_key(der: bytes) -> bytes | None:
    """A fresh private key of the same algorithm, size/curve and encoding (PKCS#1/SEC1 or PKCS#8)."""
    from cryptography.hazmat.primitives import serialization as S
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa
    try:
        key = S.load_der_private_key(der, password=None)
    except Exception:
        return None
    try:
        return _regenerate(key, der, S, dsa, ec, ed448, ed25519, rsa)
    except ValueError:  # the library refuses the size or exponent (old test keys): caller keeps the tree
        return None


def _regenerate(key, der, S, dsa, ec, ed448, ed25519, rsa):
    if isinstance(key, rsa.RSAPrivateKey):
        new = rsa.generate_private_key(public_exponent=key.private_numbers().public_numbers.e, key_size=key.key_size)
    elif isinstance(key, ec.EllipticCurvePrivateKey):
        new = ec.generate_private_key(key.curve)
    elif isinstance(key, dsa.DSAPrivateKey):
        new = dsa.generate_private_key(key_size=key.key_size)
    elif isinstance(key, ed25519.Ed25519PrivateKey):
        new = ed25519.Ed25519PrivateKey.generate()
    elif isinstance(key, ed448.Ed448PrivateKey):
        new = ed448.Ed448PrivateKey.generate()
    else:
        return None
    # PKCS#8 has an AlgorithmIdentifier SEQUENCE right after the version INTEGER; PKCS#1 / SEC1 do not
    _, _, c, e = next(der_parse(der))
    kids = list(der_parse(der, c, e))
    pkcs8 = len(kids) > 1 and kids[1][0] == 0x30
    fmt = S.PrivateFormat.PKCS8 if pkcs8 else S.PrivateFormat.TraditionalOpenSSL
    return new.private_bytes(S.Encoding.DER, fmt, S.NoEncryption())


def ssh_fields(b: bytes, i: int = 0):
    """Split SSH wire-format strings: yields (start, end) of each length-prefixed field."""
    while i < len(b):
        if i + 4 > len(b):
            raise ValueError("short")
        n = struct.unpack(">I", b[i:i + 4])[0]
        if i + 4 + n > len(b):
            raise ValueError("overrun")
        yield i + 4, i + 4 + n
        i += 4 + n


def _new_ssh_key(keytype: str, bits: int | None):
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
    if keytype == "ssh-ed25519":
        return ed25519.Ed25519PrivateKey.generate()
    if keytype == "ssh-rsa":
        return rsa.generate_private_key(65537, bits or 2048)
    curves = {"ecdsa-sha2-nistp256": ec.SECP256R1(), "ecdsa-sha2-nistp384": ec.SECP384R1(),
              "ecdsa-sha2-nistp521": ec.SECP521R1()}
    if keytype in curves:
        return ec.generate_private_key(curves[keytype])
    return None


def fake_ssh_public_blob(b: bytes) -> bytes | None:
    """SSH public key blob -> blob of a fresh key with the same type and length."""
    from cryptography.hazmat.primitives import serialization as S
    try:
        fields = list(ssh_fields(b))
    except ValueError:
        return None
    keytype = b[fields[0][0]:fields[0][1]].decode("latin1")
    bits = None
    if keytype == "ssh-rsa" and len(fields) >= 3:
        n = b[fields[2][0]:fields[2][1]]
        bits = (len(n.lstrip(b"\0"))) * 8
    for _ in range(50):
        k = _new_ssh_key(keytype, bits)
        if k is None:
            return None
        pub = k.public_key().public_bytes(S.Encoding.OpenSSH, S.PublicFormat.OpenSSH).split()[1]
        new = base64.b64decode(pub)
        if len(new) == len(b):
            return new
    return None


OPENSSH_MAGIC = b"openssh-key-v1\0"


def fake_openssh_private(b: bytes) -> bytes | None:
    """openssh-key-v1 blob -> same layout with a fresh key (unencrypted) or fresh public part and random
    ciphertext (encrypted). Comment keeps its classes; checkints and padding follow the format."""
    from cryptography.hazmat.primitives import serialization as S
    if not b.startswith(OPENSSH_MAGIC):
        return None
    try:
        f = list(ssh_fields(b, len(OPENSSH_MAGIC)))[:3]          # cipher, kdf, kdfoptions
        cipher = b[f[0][0]:f[0][1]]
        p = f[2][1]
        nkeys = struct.unpack(">I", b[p:p + 4])[0]
        if nkeys != 1:
            return None
        pub_s, pub_e = next(ssh_fields(b, p + 4))
        priv_s, priv_e = next(ssh_fields(b, pub_e))
    except (ValueError, StopIteration):
        return None
    if priv_e != len(b):
        return None
    pub = b[pub_s:pub_e]
    new_pub = fake_ssh_public_blob(pub)
    if new_pub is None:
        return None
    if cipher != b"none":
        kdfopt = bytearray(b[f[2][0]:f[2][1]])
        try:
            salt_s, salt_e = next(ssh_fields(bytes(kdfopt)))
            kdfopt[salt_s:salt_e] = secrets.token_bytes(salt_e - salt_s)
        except (ValueError, StopIteration):
            pass
        out = bytearray(b)
        out[f[2][0]:f[2][1]] = kdfopt
        out[pub_s:pub_e] = new_pub
        out[priv_s:priv_e] = secrets.token_bytes(priv_e - priv_s)
        return bytes(out)
    # unencrypted: rebuild the private section from a fresh key of the same type and size
    keytype = pub[4:4 + struct.unpack(">I", pub[:4])[0]].decode("latin1")
    priv = b[priv_s:priv_e]
    try:
        pf = list(ssh_fields(priv, 8))
    except ValueError:
        pf = None
    for _ in range(80):
        bits = None
        if keytype == "ssh-rsa":
            fl = list(ssh_fields(pub))
            bits = len(pub[fl[2][0]:fl[2][1]].lstrip(b"\0")) * 8
        k = _new_ssh_key(keytype, bits)
        if k is None:
            return None
        blob = base64.b64decode(b"".join(
            k.private_bytes(S.Encoding.PEM, S.PrivateFormat.OpenSSH, S.NoEncryption()).splitlines()[1:-1]))
        nf = list(ssh_fields(blob, len(OPENSSH_MAGIC)))
        q = nf[2][1]
        npub_s, npub_e = next(ssh_fields(blob, q + 4))
        npriv_s, npriv_e = next(ssh_fields(blob, npub_e))
        npriv = blob[npriv_s:npriv_e]
        # fresh section without its comment and padding: checkints + fields up to (excluding) the comment
        nfields = list(ssh_fields(npriv, 8))
        body = npriv[8:nfields[-1][0] - 4]  # cryptography writes an empty comment last
        if pf is None:
            return None
        comment = priv[pf[-1][0]:pf[-1][1]] if len(pf) >= 1 else b""
        # original comment is the last field before padding: find it by walking the same field count
        ofields = list(ssh_fields(priv, 8))
        ocomment_s, ocomment_e = ofields[len(nfields) - 1] if len(ofields) >= len(nfields) else (0, 0)
        comment = class_preserving(priv[ocomment_s:ocomment_e].decode("latin1")).encode("latin1")
        check = secrets.token_bytes(4)
        sec = check + check + body + struct.pack(">I", len(comment)) + comment
        pad = bytes(range(1, 1 + (-len(sec) % 8)))
        sec += pad
        if len(sec) != len(priv) or sec[8:8 + len(body)] == priv[8:8 + len(body)]:
            continue
        out = bytearray(b)
        out[pub_s:pub_e] = blob[npub_s:npub_e]
        out[priv_s:priv_e] = sec
        return bytes(out)
    return None


def classify_binary(raw: bytes) -> str:
    if raw.startswith(OPENSSH_MAGIC):
        return "openssh"
    if raw[:4] in (b"\0\0\0\x07", b"\0\0\0\x0b", b"\0\0\0\x13") and \
            raw[4:4 + struct.unpack(">I", raw[:4])[0]].startswith((b"ssh-", b"ecdsa-")):
        return "ssh-pub"
    if raw[:1] == b"\x30":
        try:
            parts = list(der_parse(raw))
            if len(parts) == 1 and parts[0][3] == len(raw):
                return "der"
        except ValueError:
            pass
        return "der-partial"
    return "binary"


def fake_binary(raw: bytes) -> tuple[bytes, str]:
    kind = classify_binary(raw)
    if kind == "openssh":
        new = fake_openssh_private(raw)
        if new:
            return new, "openssh"
    if kind == "ssh-pub":
        new = fake_ssh_public_blob(raw)
        if new:
            return new, "ssh-pub"
    if kind == "der":
        for _ in range(50):  # DER integer lengths vary by a byte; keep the original length
            new = regenerate_der_key(raw)
            if new is None or len(new) == len(raw):
                break
        if new is not None and len(new) == len(raw):
            return new, "der-key"
        return der_fake(raw), "der-tree"
    if kind == "der-partial":  # truncated DER: keep the parsable headers, replace the rest
        out = bytearray(raw)
        keep = _der_header_bytes(raw)
        for i in range(len(raw)):
            if i not in keep:
                out[i] = secrets.randbelow(256)
        return bytes(out), "der-partial"
    return secrets.token_bytes(len(raw)), "bytes"


def _der_header_bytes(raw: bytes) -> set[int]:
    """Indexes of tag/length bytes (and OID contents) reachable in a truncated DER prefix."""
    keep = set()

    def walk(i, end, depth=0):
        while i < end and depth < 20:
            if i + 2 > len(raw):
                return
            tag, ln, j = raw[i], raw[i + 1], i + 2
            if ln & 0x80:
                k = ln & 0x7F
                if k == 0 or k > 4:
                    return
                ln = int.from_bytes(raw[j:j + k], "big")
                j += k
            keep.update(range(i, min(j, len(raw))))
            if tag in KEEP_TAGS or (tag == 0x02 and ln <= 2):
                keep.update(range(j, min(j + ln, len(raw))))
            if tag & 0x20:
                walk(j, min(j + ln, len(raw)), depth + 1)
            elif tag == 0x03 and j < len(raw):
                keep.add(j)
            i = j + ln

    walk(0, len(raw))
    return keep


# ---------------------------------------------------------------- the faker

PEM = re.compile(r"(-----BEGIN ([A-Z0-9 ]+)-----)(.*?)(-----END \2-----|$)", re.S)
JWT_LIKE = re.compile(r"(?P<pre>[A-Za-z]{1,8}\.)?(?P<jwt>eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*)")
URL = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)(?:(?P<user>[^:/@\s]*)(?::(?P<pw>[^@\s/]*))?@)?"
                 r"(?P<host>[^/\s?#]*)(?P<path>/[^\s?#]*)?(?P<query>\?[^\s#]*)?(?P<frag>#\S*)?")
KEYVAL = re.compile(r"(?P<k>[\"']?[A-Za-z_][\w.\-]*[\"']?\s*(?:=>|:=|[:=])\s*[\"']?)(?P<v>.+)")
SPLIT = re.compile(r"(\s+|\\[nrt])")
KEEP_WORDS = {
    "bearer", "basic", "token", "authorization", "auth", "key", "apikey", "api_key", "api-key", "secret",
    "password", "passwd", "pass", "pwd", "user", "username", "login", "export", "set", "setx", "env", "curl",
    "wget", "http", "https", "header", "headers", "get", "post", "put", "delete", "patch", "true", "false",
    "null", "none", "client_id", "client_secret", "access_token", "refresh_token", "private_key", "public_key",
    "content-type", "accept", "x-api-key", "x-auth-token", "cookie", "-----begin", "-----end", "private",
    "public", "rsa", "ec", "openssh", "key-----", "certificate", "value", "default", "os.getenv(", "os.environ",
}
KEYWORD_HINT = re.compile(r"(?i)key|token|secret|pass|pwd|auth|user|login|cred|api|client|id$|url|host|port|db")


def keep_token(t: str) -> bool:
    """Tokens that cannot be the secret: known words, CLI options, key names, pure punctuation."""
    core = t.strip("\"'`,;()[]{}<>")
    if not core or not re.search(r"[A-Za-z0-9]", core):
        return True
    if core.lower() in KEEP_WORDS:
        return True
    if re.fullmatch(r"-[A-Za-z]|--[a-z][a-z0-9-]{1,30}", core):  # CLI option (-x or --word), not -pSECRET
        return True
    if re.fullmatch(r"[A-Za-z_][\w.\-]*[:=]", core) and KEYWORD_HINT.search(core):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]*[A-Z]", core) and "_" in core and KEYWORD_HINT.search(core):
        return True  # ENV_VAR_NAME
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[_.][a-z0-9]+)+", core) and len(core) <= 32 and KEYWORD_HINT.search(core) \
            and sum(c.isdigit() for c in core) <= 2 and re.search(r"[\"']?[:=,]$", t):
        return True  # snake_case / dotted key name in key position, such as "secret_key": or db.password=
    return False


class Faker:
    def __init__(self, oracle: Oracle, data_prefixes: dict[str, str | None] | None = None, tries: int = 400):
        """data_prefixes: learned format prefix -> pool of the next position (or None)."""
        self.o = oracle
        self.data = data_prefixes or {}
        self.tries = tries
        self._allowed = {}
        self.force = False

    # ------------------------------------------------------------ fixed parts

    def fixed_positions(self, v: str, rules: list) -> tuple[set[int], dict[int, str]]:
        best = 0
        for r in rules:
            ci = bool(r["rx"].flags & re.I)
            for p in r["prefixes"]:
                if (v[:len(p)].lower() == p.lower()) if ci else v.startswith(p):
                    best = max(best, len(p))
        for p in CURATED_PREFIXES:
            if v.startswith(p) and len(p) < len(v):
                best = max(best, len(p))
        m = HEX_PREFIX.match(v)
        if m:
            best = max(best, 2)
        allowed = {}
        dp = max((p for p in self.data if v.startswith(p) and len(p) < len(v)), key=len, default="")
        if len(dp) >= best:
            best = len(dp)
            if self.data.get(dp) and best < len(v):
                allowed[best] = self.data[dp]
        keep = set(range(best))
        for inf in CURATED_INFIXES:
            for m in re.finditer(re.escape(inf), v):
                keep |= set(range(m.start(), m.end()))
        return keep, allowed

    def allowed_positions(self, v: str, rules: list) -> dict[int, str]:
        """Per position, the characters that keep every rule v matches still matching."""
        if not rules:
            return {}
        target = frozenset(r["id"] for r in rules)
        out = {}
        for m in re.finditer(r"[A-Za-z0-9]", v):
            i, c = m.start(), m.group()
            pool = class_pools(c)[char_class(c)]
            ok = "".join(x for x in pool if x == c or self.o.match(v[:i] + x + v[i + 1:], rules) == target)
            if len(ok) < len(pool):
                out[i] = ok
        return out

    # ------------------------------------------------------------ entry points

    def fake_value(self, v: str) -> tuple[str, str]:
        """Fake a whole value (may hold several tokens, PEM blocks, multi-line base64).

        A positive value always changes when it has any letter or digit: if every token looked harmless
        (a key name, an option such as -pPASSWORD, a bare URL), it is faked again in force mode.
        """
        self.force = False
        if self._header_only(v):
            return v, "jose-header"
        f, m = self._fake_value(v)
        if not m.startswith(("pem", "blob", "base64")):
            f = keep_jose_headers(v, f)
        if f == v and m == "jose-public":
            return f, m
        if f == v and re.search(r"[A-Za-z0-9]", v):
            self.force = True
            try:
                f, m = self._fake_value(v)
                m = "force:" + m
            finally:
                self.force = False
        return f, m

    @staticmethod
    def _header_only(v: str) -> bool:
        """A JWT/JOSE header or a leading piece of one (base64url of '{"alg":"RS256","kid":...'), possibly
        followed by '.'. Headers are public metadata; full JWTs keep theirs, so these stay as they are."""
        parts = [x for x in re.split(r"[.\s\"'\[\]]+", v) if x]
        if not parts:
            return False
        for part in parts:
            if not part.startswith("eyJ"):
                return False
            cut = part[:len(part) // 4 * 4]
            try:
                t = base64.urlsafe_b64decode(cut).decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                return False
            keys = [m.group(1) for m in JSON_STR.finditer(t) if m.group(2)]
            # every complete key is a header field, and no key of a payload has started
            tail_key = re.search(r'[{,]\s*"([^"]*)$', t)
            if not keys or not set(keys) <= JOSE_HEADER_KEYS or (tail_key and not any(
                    k.startswith(tail_key.group(1)) for k in JOSE_HEADER_KEYS)):
                return False
        return True

    def _fake_value(self, v: str) -> tuple[str, str]:
        if PEM.search(v):
            out, last, methods = [], 0, []
            for m in PEM.finditer(v):
                out.append(self._fake_text_part(v[last:m.start()], methods))
                body, meth = self._fake_blob(m.group(3), m.group(2))
                methods.append(meth)
                out.append(m.group(1) + body + m.group(4))
                last = m.end()
            out.append(self._fake_text_part(v[last:], methods))
            return "".join(out), "+".join(sorted(set(methods))) or "pem"
        methods = []
        f = self._fake_text_part(v, methods)
        return f, "+".join(sorted(set(methods))) or "kept"

    def _fake_text_part(self, s: str, methods: list) -> str:
        if not s:
            return s
        pieces = SPLIT.split(s)
        # multi-line base64 runs (keys split over lines): handle as one blob
        out = list(pieces)
        i = 0
        while i < len(pieces):
            j, run = i, []
            while j < len(pieces):
                p = pieces[j]
                if j % 2 == 0:
                    core = p[1:] if p.startswith("n") and p[1:3] in ("MI", "MH", "b3") else p
                    if p and set(core) <= B64CHARS and len(core) >= 8:
                        run.append(j)
                        j += 2
                        continue
                break
            if len(run) >= 2 and sum(len(pieces[k]) for k in run) >= 64:
                joined = "".join(pieces[k][1:] if (k == run[0] and pieces[k].startswith("n") and
                                                    pieces[k][1:3] in ("MI", "MH", "b3")) else pieces[k] for k in run)
                d = b64_decode(joined)
                if d and classify_binary(d[0]) != "binary":
                    new_raw, meth = fake_binary(d[0])
                    new = b64_encode(new_raw, d[1], d[2])
                    pos = 0
                    for k in run:
                        lead = 1 if (k == run[0] and pieces[k].startswith("n") and pieces[k][1:3] in ("MI", "MH", "b3")) else 0
                        n = len(pieces[k]) - lead
                        out[k] = pieces[k][:lead] + new[pos:pos + n]
                        pos += n
                    methods.append("blob-" + meth)
                    i = run[-1] + 2
                    continue
            if i % 2 == 0 and pieces[i]:
                if keep_token(pieces[i]) and not (self.force and re.search(r"[A-Za-z0-9]", pieces[i])):
                    out[i] = pieces[i]
                else:
                    out[i], meth = self.fake_token(pieces[i])
                    methods.append(meth)
            i += 1
        return "".join(out)

    def _fake_blob(self, body: str, label: str) -> tuple[str, str]:
        lines = SPLIT.split(body)
        header_lines = []
        # legacy encrypted PEM headers (Proc-Type / DEK-Info) stay; the IV keeps its classes
        datas = [k for k in range(0, len(lines), 2) if lines[k] and set(lines[k]) <= B64CHARS]
        joined = "".join(lines[k] for k in datas)
        d = b64_decode(joined)
        if not d:
            return self._fake_text_part(body, []), "pem-text"
        new_raw, meth = fake_binary(d[0])
        new = b64_encode(new_raw, d[1], d[2])
        out, pos = list(lines), 0
        for k in datas:
            out[k] = new[pos:pos + len(lines[k])]
            pos += len(lines[k])
        for k in range(0, len(lines), 2):
            if k not in datas and lines[k]:
                if re.match(r"[A-Za-z-]+:", lines[k]):  # Proc-Type / DEK-Info / Comment headers
                    out[k] = re.sub(r"(DEK-Info:\s*[\w-]+,)([0-9A-Fa-f]+)", lambda m: m.group(1) + class_preserving(m.group(2)), lines[k])
                else:  # key data written escaped (\/ in JSON): same classes, escapes in place
                    out[k] = class_preserving(lines[k])
        return "".join(out), "pem-" + meth

    def fake_token(self, t: str) -> tuple[str, str]:
        """Fake one whitespace-free token."""
        lead = re.match(r"[\"'`(\[{<]*", t).group()
        trail = re.search(r"[\"'`)\]}>,;]*$", t[len(lead):]).group()
        core = t[len(lead):len(t) - len(trail)] if trail else t[len(lead):]
        if not core:
            return t, "kept"
        f, meth = self._fake_core(core)
        return lead + f + trail, meth

    def _fake_core(self, v: str) -> tuple[str, str]:
        m = URL.fullmatch(v)
        if m and m.group("scheme"):
            return self._fake_url(m), "url"
        m = JWT_LIKE.fullmatch(v)
        if m:
            f = self._fake_jwt(m.group("jwt"))
            if f:
                return (m.group("pre") or "") + f, "jwt"
        m = JOSE_ANY.fullmatch(v)
        if m and any(p.startswith("eyJ") for p in m.group("body").split(".")):
            f = self._fake_jose(m.group("body"))
            if f is not None:
                return (m.group("pre") or "") + f, "jose-public" if f == m.group("body") else "jose-fragment"
        m = KEYVAL.fullmatch(v)
        if m and KEYWORD_HINT.search(m.group("k")) and len(m.group("v")) >= 1:
            f, meth = self.fake_token(m.group("v"))
            return m.group("k") + f, "keyval-" + meth
        d = b64_decode(v) if len(v) >= 16 else None
        if d:
            raw, alpha, padded = d
            kind = classify_binary(raw)
            text = printable(raw)
            evidence = bool(re.search(r"[+/=_-]", v)) or kind in ("openssh", "ssh-pub", "der") or \
                (text is not None and len(text) >= 8)
            if evidence:
                if text is not None and is_json(text.strip()) and text.strip()[:1] in "{[":
                    return b64_encode(fake_json_text(text).encode(), alpha, padded), "base64-json"
                if text is not None:
                    inner, meth = self.fake_value(text) if not self.force else self._fake_value(text)
                    if len(inner.encode()) == len(raw):
                        return b64_encode(inner.encode(), alpha, padded), "base64-text(" + meth + ")"
                if kind != "binary" or re.search(r"[+/=]", v):
                    new_raw, meth = fake_binary(raw)
                    return b64_encode(new_raw, alpha, padded), "base64-" + meth
        return self.fake_generic(v)

    def _fake_url(self, m: re.Match) -> str:
        g = m.groupdict()
        out = g["scheme"]
        if g["user"] is not None:
            out += g["user"] + (":" + self.fake_generic(g["pw"])[0] if g["pw"] else "") + "@"
        host = g["host"] or ""
        if self.force and host:  # keep the TLD and the port
            hp, _, port = host.partition(":")
            labels = hp.split(".")
            host = ".".join([class_preserving(x) for x in labels[:-1]] + labels[-1:]) + (":" + port if port else "")
        out += host
        if g["path"]:
            segs = g["path"].split("/")
            secretish = (lambda s: re.search(r"[A-Za-z0-9]", s)) if self.force else \
                (lambda s: len(s) >= 16 and entropy(s) >= 3.3)
            out += "/".join(self.fake_generic(s)[0] if secretish(s) else s for s in segs)
        if g["query"]:
            out += "?" + "&".join(
                (kv.split("=", 1)[0] + "=" + self.fake_token(kv.split("=", 1)[1])[0]) if "=" in kv and kv.split("=", 1)[1]
                else kv for kv in g["query"][1:].split("&"))
        if g["frag"]:
            out += g["frag"]
        return out

    def _fake_jwt(self, v: str) -> str | None:
        parts = v.split(".")
        dec = [b64_decode(p) if p else None for p in parts]
        if not dec[0] or not dec[1]:
            return None
        head, body = printable(dec[0][0]), printable(dec[1][0])
        if not head or not body or not is_json(head) or not is_json(body):
            return None
        new_body = fake_json_text(body).encode()
        sig = dec[2]
        if parts[2] and not sig:
            sig_new = self.fake_generic(parts[2])[0]
        else:
            sig_new = b64_encode(secrets.token_bytes(len(sig[0])), jws_alphabet(parts[2]), sig[2]) if sig else ""
        return ".".join([parts[0], b64_encode(new_body, jws_alphabet(parts[1]), dec[1][2]), sig_new])

    def _fake_jose(self, v: str) -> str | None:
        """A JWT or a piece of one (cut anywhere, signature missing, Mapbox-style pk.<payload>.<sig>):
        every eyJ segment through fake_jose_segment, other segments (signatures) random in the same alphabet.
        The Kingfisher rules it matches must stay the same."""
        target = self.o.match(v)
        for _ in range(self.tries):
            out = []
            for p in v.split("."):
                f = fake_jose_segment(p) if p[:1] == "e" else None
                if f is not None:
                    pass
                elif p.startswith("eyJ"):
                    return None
                elif not p:
                    f = p
                else:
                    d = b64_decode(p)
                    if d:
                        f = b64_encode(secrets.token_bytes(len(d[0])), jws_alphabet(p), d[2])
                    else:
                        # not canonical base64 (cut, or non-zero trailing bits): random, and not canonical either
                        pool = B64_STD[:62] + ("+/" if re.search(r"[+/]", p) else "-_")
                        f = "".join(_pick(pool) for _ in p)
                        while len(p) % 4 in (2, 3) and b64_decode(f) is not None:
                            f = f[:-1] + _pick(pool)
                out.append(f)
            f = ".".join(out)
            if len(f) == len(v) and self.o.match(f) == target:
                return f
        raise ValueError(f"no faithful JOSE fake ({shape(v)[:60]})")

    # ------------------------------------------------------------ generic values with verification

    def fake_generic(self, v: str) -> tuple[str, str]:
        if not re.search(r"[A-Za-z0-9]", v):
            return v, "kept"
        target = self.o.match(v)
        ck = checksum_valid(v)
        rules = self.o.subset(target)
        keep, data_allowed = self.fixed_positions(v, rules)
        key = (v, target)
        if key not in self._allowed:
            self._allowed[key] = self.allowed_positions(v, rules)
        allowed = dict(self._allowed[key])
        for i, pool in data_allowed.items():
            allowed[i] = "".join(c for c in allowed.get(i, pool) if c in pool) or v[i]
        free = [i for i, c in enumerate(v) if c.isascii() and c.isalnum() and i not in keep]
        if not free:
            return v, "kept-literal"
        props = self._props(v)
        last = None
        for _ in range(self.tries):
            f = class_preserving(v, keep=keep, allowed=allowed)
            if ck:
                f = fix_checksum(f, ck, v)
            why = self._check(v, f, target, ck, keep, props)
            if why == ["rule set"]:  # usually an entropy threshold: move the fake's entropy to the original's
                f = self._match_entropy(v, f, keep, allowed, ck)
                why = self._check(v, f, target, ck, keep, props)
            if not why:
                return f, "class" + ("+checksum" if ck else "") + ("+rules" if rules else "")
            last = why
        raise ValueError(f"no faithful fake ({shape(v)}): {last}")

    @staticmethod
    def _match_entropy(v: str, f: str, keep: set[int], allowed: dict[int, str], ck: str | None,
                       steps: int = 400) -> str:
        """Greedy single-character changes (same class, same pools) that bring entropy(f) to entropy(v)."""
        goal = entropy(v)
        span = checksum_span(v, ck) if ck else (0, 0)
        free = [i for i, c in enumerate(v) if c.isascii() and c.isalnum() and i not in keep
                and not span[0] <= i < span[1]]
        if not free:
            return f
        pools = {}
        for m in re.finditer(r"[A-Za-z0-9]+", v):
            cp = class_pools("".join(c for k, c in enumerate(m.group()) if m.start() + k not in keep) or m.group())
            for k in range(m.start(), m.end()):
                pool = cp[char_class(v[k])]
                pools[k] = "".join(x for x in pool if x in allowed[k]) if k in allowed else pool
        cur = list(f)
        for _ in range(steps):
            h = entropy("".join(cur))
            if abs(h - goal) < 0.005:
                break
            cnt = Counter(cur)
            i = free[secrets.randbelow(len(free))]
            pool = pools.get(i) or cur[i]
            if h < goal:  # raise: replace a frequent char by a rarer one
                if cnt[cur[i]] <= min(cnt[x] for x in pool):
                    continue
                cands = sorted(pool, key=lambda x: cnt[x])[:3]
            else:
                if cnt[cur[i]] >= max(cnt[x] for x in pool):
                    continue
                cands = sorted(pool, key=lambda x: -cnt[x])[:3]
            old = cur[i]
            cur[i] = _pick("".join(cands))
            if abs(entropy("".join(cur)) - goal) > abs(h - goal):
                cur[i] = old
        out = "".join(cur)
        return fix_checksum(out, ck, v) if ck else out

    @staticmethod
    def _props(v: str) -> tuple:
        return (b64_decode(v) is not None, )

    def _check(self, v, f, target, ck, keep, props) -> list[str]:
        why = []
        if len(f) != len(v):
            return ["length"]
        if f == v:
            why.append("unchanged")
        span = checksum_span(v, ck) if ck else (0, 0)
        if [char_class(c) for i, c in enumerate(v) if not span[0] <= i < span[1]] != \
                [char_class(c) for i, c in enumerate(f) if not span[0] <= i < span[1]]:
            why.append("class pattern")
        if [c for c in v if char_class(c) == "."] != [c for c in f if char_class(c) == "."]:
            why.append("separators")
        if any(f[i] != v[i] for i in keep):
            why.append("fixed part")
        if self.o.match(f) != target:
            why.append("rule set")
        if ck and checksum_valid(f) != ck:
            why.append("checksum")
        if self._props(f) != props:
            why.append("base64 canonicity")
        return why
