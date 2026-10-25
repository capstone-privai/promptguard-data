"""Deterministic fake-value generator and snippet renderers for the v3 master dataset.

Every secret-shaped value is produced from a shake_256 stream seeded by (VERSION, tag). The values follow the
public *format* of each service (prefix, alphabet, length, checksum) but are generated from a public rule, so they
are not real credentials. The same seed yields the same bytes on any machine, so the CSV rebuilds byte-for-byte.

Run anything that imports this with `python3 -I`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib

VERSION = "secret-sources-v3"

LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
HEX = "0123456789abcdef"
ALNUM = LOWER + UPPER + DIGITS
B64 = ALNUM + "+/"
B64URL = ALNUM + "-_"
BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


class Draw:
    """A deterministic stream of choices for one seed (mirrors value_gen.Draw)."""

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
        return int.from_bytes(self._bytes(4), "big") % n

    def between(self, lo: int, hi: int) -> int:
        return lo + self.int(hi - lo + 1)

    def choice(self, seq):
        return seq[self.int(len(seq))]

    def chars(self, n: int, alphabet: str) -> str:
        return "".join(alphabet[b % len(alphabet)] for b in self._bytes(n))

    def raw(self, n: int) -> bytes:
        return self._bytes(n)


def d(tag: str) -> Draw:
    return Draw(tag)


def base62(n: int, width: int) -> str:
    out = ""
    for _ in range(width):
        n, r = divmod(n, 62)
        out = (DIGITS + UPPER + LOWER)[r] + out
    return out


# ---- token builders. Each returns a format-correct fake value for one tag. -------------------------

def tok(prefix: str, n: int, alphabet: str = ALNUM, sep: str = "", tag: str = "") -> str:
    """prefix + sep + n chars."""
    return prefix + sep + d(tag or prefix).chars(n, alphabet)


def tok_crc(prefix: str, n: int, tag: str = "") -> str:
    """GitHub-style: prefix_ + body + base62(crc32(body)) 6 (passes the vendor's own checksum)."""
    body = d(tag or prefix).chars(n, ALNUM)
    return f"{prefix}_{body}{base62(zlib.crc32(body.encode()), 6)}"


def b64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt(tag: str, alg: str = "HS256", extra: dict | None = None) -> str:
    dd = d(tag)
    header = {"alg": alg, "typ": "JWT"}
    iat = 1_700_000_000 + dd.int(60_000_000)
    payload = {"sub": dd.chars(20, HEX), "iat": iat, "exp": iat + 3600}
    if extra:
        payload.update(extra)
    sig = dd.raw(32 if alg == "HS256" else 64)
    return ".".join([b64url_bytes(json.dumps(header, separators=(",", ":")).encode()),
                     b64url_bytes(json.dumps(payload, separators=(",", ":")).encode()), b64url_bytes(sig)])


def _pem_body(tag: str, n: int, width: int = 64) -> str:
    body = base64.b64encode(d(tag).raw(n)).decode()
    return "\n".join(body[i:i + width] for i in range(0, len(body), width))


def pem(label: str, tag: str, n: int = 610) -> str:
    return f"-----BEGIN {label}-----\n{_pem_body(tag, n)}\n-----END {label}-----"


def openssh_key(tag: str) -> str:
    body = base64.b64encode(b"openssh-key-v1\x00" + d(tag).raw(360)).decode()
    return ("-----BEGIN OPENSSH PRIVATE KEY-----\n"
            + "\n".join(body[i:i + 70] for i in range(0, len(body), 70))
            + "\n-----END OPENSSH PRIVATE KEY-----")


def aws_secret(tag: str) -> str:
    return d(tag).chars(40, B64)


def uuid(tag: str) -> str:
    h = d(tag).chars(32, HEX)
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-{'89ab'[int(h[16], 16) % 4]}{h[17:20]}-{h[20:]}"


def password(tag: str, style: str = "human") -> str:
    dd = d(tag)
    words = ("Harbor", "Falcon", "Cobalt", "Meadow", "Lantern", "Granite", "Juniper", "Willow", "Saffron",
             "Thunder", "Pixel", "Kernel", "Quartz", "Maple", "Otter")
    if style == "weak":
        return dd.choice(("admin123", "P@ssw0rd!", "changeme2024", "root1234", "qwerty123!", "Welcome1!",
                          "postgres", "letmein99", "dev_pass1"))
    if style == "random":
        pool = LOWER + UPPER + DIGITS + "!#$%&*?-_"
        return dd.chars(dd.between(14, 22), pool)
    return dd.choice(words) + dd.choice(words) + str(dd.between(10, 99)) + dd.choice("!@#$%&*")


# ---- hard-negative value builders (same shape, must NOT be masked) ---------------------------------

def neg_placeholder(prefix: str = "") -> str:
    base = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    return (prefix + ("_" if prefix and not prefix.endswith(("-", "_", ".")) else "") + base) if prefix else base


def neg_envref(name: str) -> str:
    return "${" + name + "}"


def neg_example(prefix: str, body: str = "EXAMPLE") -> str:
    return f"{prefix}{body}" if prefix.endswith(("_", "-", ".")) else f"{prefix}_{body}"
