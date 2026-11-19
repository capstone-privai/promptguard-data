"""Deterministic, structural formats for CredData Category atoms.

Evidence: the Samsung/CredSweeper rules mirrored in
``metric-detection/secret-sources/rules_slim.json`` (source path
``credsweeper/rules/config.yaml``), and *only* creddata-v1 train gold spans.
No training values, excerpts, or runtime dependency on CredSweeper are included.
The companion test prints aggregate evidence directly from the ignored inputs.

Category names describe the captured VALUE, not an entire assignment/header:
Basic omits the scheme, JWK is a source fragment, and PEM includes
its armor. Generated PEM is always a canonical unindented block. Checks are
structural, not cryptographic: no signatures, key mathematics, or NKEY CRCs
are verified (the obfuscated train NKEYs do not preserve their CRCs).

Bearer Authorization is opaque and uses the train composition profiles.
AWS Multi uses access IDs (16/18) or a 40-character secret (2/18); source
syntax in the two non-ID spans is left to the integrator. JWK also has some
overmerged source spans; the material helper lets callers preserve that syntax.
PASETO/PASERK are rule-backed formats with zero observations in this train.
"""
from __future__ import annotations

import ast
import base64
import binascii
import json
import re
import struct
from collections.abc import Callable

import value_gen as vg

Generator = Callable[[vg.Draw], str]

# Exhaustive complement of the fixed-format atoms in the supplied train.
# These rules select a value by context, not a single fixed value grammar.
FREE_FORM_ATOMS = frozenset({
    "API", "Auth", "Bearer Authorization", "CMD ConvertTo-SecureString", "CMD Password",
    "CMD Secret", "CMD Token", "CURL Options", "CURL User Password",
    "Credential", "Key", "Other", "Password", "SQL Password", "Salt",
    "Secret", "Token", "URL Credentials",
})


def _kind(name: str) -> Generator:
    return vg.SECRET_KINDS[name][1]


def _json64(obj: dict) -> str:
    return vg.b64url(json.dumps(obj, separators=(",", ":")).encode("ascii"))


def _decode64(value: str) -> bytes:
    """Standard or URL-safe base64, with optional omitted padding."""
    if not re.fullmatch(r"[0-9A-Za-z_+/-]*={0,2}", value):
        raise ValueError("invalid base64 alphabet")
    body = value.rstrip("=")
    if len(body) % 4 == 1:
        raise ValueError("invalid base64 length")
    # Existing padding, if present, must be the required amount.
    padding = "=" * (-len(body) % 4)
    if "=" in value and value != body + padding:
        raise ValueError("invalid base64 padding")
    return base64.b64decode(body + padding, altchars=b"-_", validate=True)


# Joint username/password group-length counts from the 676 decodable train
# spans (one further span is malformed). Sampling the marginals independently
# creates mostly unseen pairs. Only lengths/counts are retained, never words.
_BASIC_SHAPES = (
    (((1, 4, 4, 4), (1, 4, 4, 8)), 218), (((4, 4), (1, 4, 4, 8)), 146),
    (((3,), (6, 8)), 52), (((3,), (32, 8, 8)), 33), (((7,), (8,)), 20),
    (((3,), (9, 8)), 18), (((5,), (5,)), 18), (((4,), (4,)), 13),
    (((4,), (8,)), 13), (((3, 4), (19,)), 11), (((3, 3, 4), (1, 4, 4, 8)), 10),
    (((6,), (6, 8)), 10), (((2, 5, 4), (1, 4, 4, 8)), 9),
    (((6, 8, 4), (1, 4, 4, 8)), 8), (((7,), (11,)), 7),
    (((4,), (1, 4, 4, 8)), 7), (((3,), (1, 4, 4, 8)), 6),
    (((3, 3, 7), (1, 4, 4, 8)), 5), (((12, 4), (6, 8)), 5),
    (((8,), (8,)), 5), (((6,), (6,)), 5), (((3, 3, 4, 1), (1, 4, 4, 8)), 4),
    (((4, 6), (11,)), 4), (((7,), (10,)), 3), (((5,), (8,)), 3),
    (((3,), (6, 9)), 3), (((6,), (4, 4, 8)), 3), (((7,), (1, 4, 4, 8)), 3),
    (((4, 5), (1, 4, 4, 8)), 2), (((6, 4), (1, 4, 4, 8)), 2),
    (((3, 3, 4), (6, 8)), 2), (((8,), (7,)), 2), (((4,), (6,)), 2),
    (((20,), (13, 6)), 2), (((4,), (9,)), 2), (((4, 5), (13,)), 1),
    (((5, 3), (6, 8)), 1), (((12, 4), (1, 4, 4, 8)), 1),
    (((3, 4, 4), (1, 4, 4, 8)), 1), (((3, 4), (1, 4, 4, 8)), 1),
    (((3, 4), (6, 8)), 1), (((4, 4), (6, 8)), 1),
    (((5, 7, 7, 4, 4), (6, 8)), 1), (((12, 4), (6, 9)), 1),
    (((2, 5), (7, 8)), 1), (((8, 5), (6, 8)), 1), (((7, 5), (6, 8)), 1),
    (((3,), (28,)), 1), (((5, 8, 4), (1, 4, 4, 8)), 1),
    (((10,), (10,)), 1), (((4,), (11,)), 1), (((2,), (6,)), 1),
    (((7,), (4,)), 1), (((3,), (6,)), 1), (((3,), (24, 8)), 1),
)


def _basic_authorization(d: vg.Draw) -> str:
    user_sizes, password_sizes = d.weighted(_BASIC_SHAPES)
    user = "_".join(d.chars(n, vg.LOWER) for n in user_sizes)
    if d.int(40) == 0:
        user = user[:-1] + d.chars(1, vg.DIGITS)
    if password_sizes == (32, 8, 8):
        # This family is digit-heavy, unlike the dominant lowercase groups.
        password = "-".join(d.chars(n, vg.LOWER + vg.DIGITS * 3) for n in password_sizes)
    elif password_sizes == (6, 8):
        password = d.chars(6, vg.LOWER) + "-" + d.chars(7, vg.LOWER) + d.chars(1, vg.DIGITS)
    else:
        password = "-".join(d.chars(n, vg.LOWER) for n in password_sizes)
    return base64.b64encode(f"{user}:{password}".encode("ascii")).decode("ascii")


# Registered JWT/OpenID claims and common application claims. The vocabulary
# is public; neither field order nor values come from an observed payload.
_JWT_CLAIMS = (
    "iss", "sub", "aud", "exp", "nbf", "iat", "jti", "name", "email", "scope", "role",
    "roles", "admin", "id", "uid", "user", "permissions", "azp", "nonce", "acr", "amr",
    "auth_time", "at_hash", "c_hash", "sid", "email_verified", "preferred_username",
    "given_name", "family_name", "nickname", "picture", "profile", "website", "gender",
    "birthdate", "zoneinfo", "locale", "phone_number", "phone_number_verified", "address",
    "updated_at", "client_id", "groups", "tenant", "appid", "ver",
)
_JWT_DATES = frozenset(("exp", "nbf", "iat", "auth_time", "updated_at"))
_JWT_BOOLS = frozenset(("admin", "email_verified", "phone_number_verified"))
_AZURE_CLAIMS = (
    "aud", "iss", "iat", "nbf", "exp", "aio", "appid", "appidacr", "idp", "oid",
    "rh", "sub", "tid", "uti", "ver", "jti", "nonce", "roles", "scp", "azp",
)


def _jwt_payload(d: vg.Draw, budget: int, *, azure: bool = False) -> dict:
    if azure:
        # The small-count tail belongs to short tokens, not giant strings in
        # long tokens. Couple it to length before sampling the common counts.
        count = (d.weighted(((1, 1), (3, 2), (8, 1))) if budget < 150 else
                 d.weighted(((8, 1), (13, 1), (14, 7), (15, 1), (17, 1), (18, 7), (20, 3))))
        first = d.weighted((("jti", 16), ("iss", 3), ("aud", 2),
                            (d.choice(("sub", "appid", "tid")), 3)))
        available, names = [n for n in _AZURE_CLAIMS if n != first], [first]
        # Common audience/issuer/time/subject claims have high train coverage.
        for name in ("aud", "iss", "iat", "sub", "exp"):
            if len(names) < count and name in available:
                names.append(name)
                available.remove(name)
    else:
        count = d.weighted(((1, 3), (2, 3), (3, 6), (4, 22), (5, 23), (6, 17), (8, 16), (10, 10)))
        # Long payloads need several claims rather than one giant string.
        count = max(count, min(8, budget // 60))
        available, names = list(_JWT_CLAIMS), []
    for _ in range(count):
        if len(names) >= count:
            break
        if not azure and sum(n in _JWT_DATES | _JWT_BOOLS for n in names) >= count // 3:
            available = [n for n in available if n not in _JWT_DATES | _JWT_BOOLS]
        names.append(available.pop(d.int(len(available))))
    strings = [name for name in names if name not in _JWT_DATES | _JWT_BOOLS]
    if not strings:
        names[-1] = d.choice(tuple(n for n in _JWT_CLAIMS if n not in _JWT_DATES | _JWT_BOOLS))
    payload = {name: (1_700_000_000 + d.int(90_000_000) if name in _JWT_DATES else
                      bool(d.int(2)) if name in _JWT_BOOLS else d.chars(3, vg.LOWER)) for name in names}
    if azure:
        if "ver" in payload:
            payload["ver"] = d.choice(("1.0", "2.0"))
        if "appidacr" in payload:
            payload["appidacr"] = d.choice(("0", "1", "2"))
    # Remove claims until the target fits, retaining one expandable string.
    while len(json.dumps(payload, separators=(",", ":"))) > budget and len(payload) > 1:
        removable = [name for name in payload if name in _JWT_DATES | _JWT_BOOLS]
        del payload[(removable or list(payload))[-1]]
    if not any(isinstance(v, str) for v in payload.values()):
        payload = {d.choice(("sub", "jti", "aud", "role")): ""}
    padding = max(0, budget - len(json.dumps(payload, separators=(",", ":"))))
    strings = [k for k, v in payload.items() if isinstance(v, str)
               and (not azure or k not in ("ver", "appidacr"))]
    weights = [d.between(1, 3) for _ in strings]
    sizes = [padding * w // sum(weights) for w in weights]
    for i in range(padding - sum(sizes)):
        sizes[i] += 1
    for name, size in zip(strings, sizes):
        payload[name] += d.chars(size, vg.ALNUM)
    return payload


def _jwt_header(d: vg.Draw, *, azure: bool = False) -> dict:
    # Obfuscation hides train algorithm identities. Use public JOSE names;
    # retain observed header-layout shares, not obfuscated header values.
    alg = d.choice(("HS256", "HS384", "HS512", "RS256", "RS384", "RS512",
                    "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"))
    if azure:
        layout = d.weighted(((("alg", "kid", "typ"), 13),
                             (("typ", "alg", "x5t", "kid"), 2),
                             (("alg", "typ", "kid"), 2), (("typ", "alg", "kid"), 1),
                             (("alg", "x5t"), 6)))
    else:
        alg = d.weighted(((alg, 95), ("Ed25519", 26), ("ES256K", 5)))
        # No ordinary selected JWT header in train contains kid.
        layout = d.weighted(((("alg", "typ"), 81), (("typ", "alg"), 40), (("alg",), 8)))
    fields = {"alg": alg, "typ": d.choice(("JWT", "jwt")),
              "kid": vg.b64url(d.raw(d.choice((16, 20, 24)))), "x5t": vg.b64url(d.raw(20))}
    return {name: fields[name] for name in layout}


def _jwt(d: vg.Draw) -> str:
    # Aggregate train length knots, excluding Azure (which has precedence).
    # Interpolate between deciles instead of sampling a uniform giant payload.
    target = _length_draw(d, (56, 105, 124, 144, 160, 228, 312, 457, 538, 663, 1008))
    signature_size = d.weighted(((32, 8), (64, 1), (256, 1)))
    if target < 450:
        signature_size = min(signature_size, 64 if target > 160 else 32)
    header = _jwt_header(d)
    if target < 95:
        signature_size = 8
    h, s = _json64(header), vg.b64url(d.raw(signature_size))
    budget = max(12, (target - len(h) - len(s) - 2) * 3 // 4)
    return ".".join((h, _json64(_jwt_payload(d, budget)), s))


def _length_draw(d: vg.Draw, knots: tuple[int, ...]) -> int:
    i = d.int(len(knots) - 1)
    return d.between(knots[i], knots[i + 1])


def _azure_access_token(d: vg.Draw) -> str:
    # Azure's rule additionally requires a longer header and an eyJ payload.
    header = _jwt_header(d, azure=True)
    target = _length_draw(d, (200, 385, 914, 957, 1017, 1042, 1077, 1080, 1155, 1254, 1254))
    signature_size = d.weighted(((256, 21), (64, 2), (32, 1)))
    if target < 500:
        signature_size = d.choice((32, 64))
    h, s = _json64(header), vg.b64url(d.raw(signature_size))
    budget = max(12, (target - len(h) - len(s) - 2) * 3 // 4)
    return ".".join((h, _json64(_jwt_payload(d, budget, azure=True)), s))


def _ntlm_token(d: vg.Draw) -> str:
    # 120..180 bytes -> 160..240 base64 characters (train: 168..219).
    n = d.weighted(((132, 41), (162, 55), (d.between(126, 164), 30)))
    # NTLM includes flags, offsets and reserved zero fields, not opaque random
    # bytes throughout. This also preserves the uppercase-heavy base64 mix.
    message = b"NTLMSSP\x00" + struct.pack("<I", d.between(1, 3))
    message += bytes(72) + d.raw(n - 84)
    return base64.b64encode(message).decode("ascii")


def _synthetic_pkcs8(d: vg.Draw, n: int) -> bytes:
    # A PKCS#8 ASN.1 container with synthetic opaque private-key bytes. Like
    # value_gen's random RSA integers, this is not a usable cryptographic key.
    algo = vg._der(0x30, bytes.fromhex("06092a864886f70d0101010500"))
    return vg._der(0x30, vg._int(b"\x00") + algo + vg._der(0x04, d.raw(n)))


# Named-curve OIDs and scalar sizes (bytes), grouped from train EC families.
# These are public ASN.1 identifiers, never copied key material.
_EC_CURVES = (
    (("2b81040009", 20), 114),   # secp160k1
    (("2a8648ce3d030101", 24), 87),  # prime192v1
    (("2b81040021", 28), 86),   # secp224r1
    (("2a8648ce3d030107", 32), 97),  # prime256v1
    (("2b81040022", 48), 46),   # secp384r1
    (("2b81040023", 66), 34),   # secp521r1
    (("2b81040001", 21), 79),   # sect163k1
    (("2b8104001a", 30), 64),   # sect233k1
    (("2b81040010", 36), 58),   # sect283k1
    (("2b81040024", 52), 58),   # sect409k1
    (("2b81040026", 72), 62),   # sect571k1
)
_RSA_ALGORITHM = vg._der(0x30, bytes.fromhex("06092a864886f70d0101010500"))


def _rsa_pkcs1(d: vg.Draw, size: int) -> bytes:
    # Correct RSA field counts and integer sizes; numbers are synthetic and
    # deliberately need not satisfy RSA key mathematics.
    def integer(n):
        raw = d.raw(n)
        return vg._int(bytes((raw[0] | 128,)) + raw[1:])
    return vg._der(0x30, vg._int(b"\x00") + integer(size) + vg._int(b"\x01\x00\x01")
                   + integer(size) + b"".join(integer(size // 2) for _ in range(5)))


def _pkcs8(algorithm: bytes, private: bytes) -> bytes:
    return vg._der(0x30, vg._int(b"\x00") + algorithm + vg._der(0x04, private))


def _ec_private(d: vg.Draw, pkcs8: bool) -> bytes:
    oid, size = d.weighted(_EC_CURVES)
    curve = vg._der(0x06, bytes.fromhex(oid))
    body = vg._int(b"\x01") + vg._der(0x04, d.raw(size))
    if not pkcs8:
        body += vg._der(0xa0, curve)
    if d.int(745) >= 163:  # train: 582 with public point, 163 without
        body += vg._der(0xa1, vg._der(0x03, b"\x00\x04" + d.raw(2 * size)))
    private = vg._der(0x30, body)
    algorithm = vg._der(0x30, bytes.fromhex("06072a8648ce3d0201") + curve)
    return _pkcs8(algorithm, private) if pkcs8 else private


def _openssh_private(d: vg.Draw) -> bytes:
    if d.int(13) < 8:
        return _decode64("".join(vg.openssh_key(d).splitlines()[1:-1]))
    size = d.weighted(((128, 2), (256, 3), (384, 1)))
    integer = lambda n: b"\x00" + bytes((d.raw(1)[0] | 128,)) + d.raw(n - 1)
    n, e = integer(size), b"\x01\x00\x01"
    public = b"".join(vg._ssh_str(v) for v in (b"ssh-rsa", e, n))
    check = d.raw(4)
    comment = f"{d.choice(('deploy', 'ci', 'dev', 'backup'))}@{d.choice(('build-01', 'laptop', 'bastion'))}".encode("ascii")
    private = check * 2 + b"".join(vg._ssh_str(v) for v in (
        b"ssh-rsa", n, e, integer(size), integer(size // 2), integer(size // 2), integer(size // 2), comment))
    private += bytes(range(1, 1 + (-len(private)) % 8))
    return (b"openssh-key-v1\x00" + vg._ssh_str(b"none") * 2 + vg._ssh_str(b"")
            + struct.pack(">I", 1) + vg._ssh_str(public) + vg._ssh_str(private))


def _pem_block(label: str, data: bytes, width: int = 64, headers: str = "") -> str:
    body = base64.b64encode(data).decode("ascii")
    return (f"-----BEGIN {label}-----\n" + headers
            + "\n".join(body[i:i + width] for i in range(0, len(body), width))
            + f"\n-----END {label}-----")


def _pem_private_key(d: vg.Draw) -> str:
    # Train armor counts; PRIVATE KEY splits into EC (749), RSA (58), and
    # Edwards/Montgomery (46). No arbitrary-length RSA-labelled byte strings.
    kind = d.weighted((("ec8", 749), ("rsa8", 58), ("ed8", 46), ("rsa1", 129),
                       ("ec1", 25), ("dsa", 15), ("ssh", 13), ("encrypted", 11), ("pgp", 4)))
    label = "PRIVATE KEY"
    if kind in ("ec8", "ec1"):
        der = _ec_private(d, kind == "ec8")
        if kind == "ec1":
            label = "EC PRIVATE KEY"
    elif kind in ("rsa1", "rsa8"):
        # Valid modulus byte sizes, roughly train's 1024/2048/4096 shares.
        size = d.weighted(((64, 4), (128, 48), (256, 84), (512, 13)))
        der = _rsa_pkcs1(d, size)
        if kind == "rsa8":
            der = _pkcs8(_RSA_ALGORITHM, der)
        else:
            label = "RSA PRIVATE KEY"
    elif kind == "ed8":
        oid, size = d.weighted(((("2b6570", 32), 24), (("2b6571", 57), 16),
                                (("2b656e", 32), 3), (("2b656f", 56), 3)))
        der = _pkcs8(vg._der(0x30, vg._der(0x06, bytes.fromhex(oid))), vg._der(0x04, d.raw(size)))
    elif kind == "ssh":
        label, der = "OPENSSH PRIVATE KEY", _openssh_private(d)
    elif kind == "dsa":
        label = "DSA PRIVATE KEY"
        size = d.weighted(((128, 11), (256, 4)))
        der = vg._der(0x30, vg._int(b"\x00") + b"".join(vg._int(d.raw(n)) for n in (size, 20, size, size, 20)))
    elif kind == "encrypted":
        label = "ENCRYPTED PRIVATE KEY"
        params = vg._der(0x30, vg._der(0x04, d.raw(8)) + vg._int(b"\x08\x00"))
        algo = vg._der(0x30, bytes.fromhex("060a2a864886f70d010c0103") + params)
        size = len(_pkcs8(_RSA_ALGORITHM, _rsa_pkcs1(d, 256)))
        der = vg._der(0x30, algo + vg._der(0x04, d.raw((size // 8 + 1) * 8)))
    else:
        label = "PGP PRIVATE KEY BLOCK"
        mpi = lambda n: struct.pack(">H", n * 8) + bytes((d.raw(1)[0] | 128,)) + d.raw(n - 1)
        public = b"\x04" + struct.pack(">I", 1_700_000_000 + d.int(90_000_000)) + b"\x01" + mpi(256) + b"\x00\x11\x01\x00\x01"
        private = mpi(256) + mpi(128) + mpi(128) + mpi(128)
        packet = public + b"\x00" + private + struct.pack(">H", sum(private) % 65536)
        der = b"\xc5\xff" + struct.pack(">I", len(packet)) + packet
    # Wrapping is conditional on armor: all 13 OpenSSH spans use 70, and
    # 76-column wrapping occurs only for PKCS#8 and traditional RSA armor.
    width = (70 if kind == "ssh" else
             d.weighted(((64, 746), (76, 107))) if label == "PRIVATE KEY" else
             d.weighted(((64, 121), (76, 8))) if kind == "rsa1" else 64)
    headers = ""
    legacy = {"rsa1": (9, 129), "ec1": (1, 25), "dsa": (2, 15)}.get(kind)
    if legacy and d.int(legacy[1]) < legacy[0]:
        cipher, block = d.weighted(((("DES-EDE3-CBC", 8), 3), (("AES-128-CBC", 16), 7),
                                    (("AES-256-CBC", 16), 2)))
        headers = f"Proc-Type: 4,ENCRYPTED\nDEK-Info: {cipher},{d.chars(2 * block, vg.HEX).upper()}\n\n"
        der = d.raw((len(der) // block + 1) * block)
        width = 64
    elif kind == "pgp":
        headers = "Version: " + d.choice(("GnuPG v1.4.23 (GNU/Linux)", "GnuPG v2.0.22 (GNU/Linux)",
                                          "GnuPG v2.2.40", "GnuPG v2.4.5")) + "\n\n"
    return _pem_block(label, der, width, headers)


def _base64_private_key(d: vg.Draw) -> str:
    # This category has its own length distribution, unlike PEM armor.
    target = _length_draw(d, (460, 461, 500, 600, 720, 849, 1200, 1620, 1900, 2125, 3620))
    n = target * 3 // 4 - len(_synthetic_pkcs8(d, 0)) - 4
    der = _synthetic_pkcs8(d, n)
    return base64.b64encode(der).decode("ascii")


def _base64_pem_private_key(d: vg.Draw) -> str:
    # Five of six spans encode RSA-2048 armor; the sixth is a shorter PKCS#8
    # block. Reusing the EC-dominated general PEM mix loses this distinction.
    kind = d.int(6)
    if kind == 0:
        pem = _pem_block("PRIVATE KEY", _ec_private(d, True))
    else:
        der = _rsa_pkcs1(d, 256)
        pem = (_pem_block("RSA PRIVATE KEY", der) if kind < 4 else
               _pem_block("PRIVATE KEY", _pkcs8(_RSA_ALGORITHM, der)))
    return base64.b64encode(pem.encode("ascii")).decode("ascii")


def _nkey_seed(d: vg.Draw) -> str:
    # NATS packs the seed/type prefix into two bytes, appends a 32-byte seed,
    # and writes the little-endian CRC16-XMODEM before unpadded base32.
    public_prefix = d.choice((0, 16, 104, 112, 120, 160, 184))
    prefix = bytes((144 | (public_prefix >> 5), (public_prefix & 31) << 3))
    data = prefix + d.raw(32)
    data += binascii.crc_hqx(data, 0).to_bytes(2, "little")
    return base64.b32encode(data).decode("ascii").rstrip("=")


_JWK_CURVES = {"P-256": 32, "P-384": 48, "P-521": 66}
_JWK_OKP_CURVES = {"Ed25519": 32, "X25519": 32, "Ed448": 57, "X448": 56}


def _jwk_size(draw: vg.Draw, kty: str, curve: str | None, modulus_bits: int | None) -> int:
    if kty == "RSA":
        if curve is not None:
            raise ValueError("RSA does not have a curve")
        if modulus_bits is None:
            return draw.weighted(((128, 2), (256, 8), (512, 1)))
        if (not isinstance(modulus_bits, int) or isinstance(modulus_bits, bool)
                or not 512 <= modulus_bits <= 16384 or modulus_bits % 16):
            raise ValueError("RSA modulus_bits must be 512..16384 and divisible by 16")
        return modulus_bits // 8
    if modulus_bits is not None:
        raise ValueError("modulus_bits is only supported for RSA")
    if kty in ("EC", "OKP"):
        sizes = _JWK_CURVES if kty == "EC" else _JWK_OKP_CURVES
        if curve is None:
            curve = draw.choice(tuple(sizes)) if kty == "EC" else "Ed25519"
        if curve not in sizes:
            raise ValueError("unsupported JWK curve for this key type")
        return sizes[curve]
    if kty == "oct" and curve is None:
        return draw.choice((16, 24, 32))
    raise ValueError("unsupported JWK key type or curve")


def jwk_private_fields(draw: vg.Draw, kty: str, *, curve: str | None = None,
                       modulus_bits: int | None = None) -> dict[str, str]:
    """Fresh private material only; callers retain field order and quoting.

    RSA returns all six private fields so an integrator can replace only the
    fields present in its source. EC/OKP return d; oct returns k. Pass the
    source curve (P-256/P-384/P-521) or RSA modulus_bits to preserve sizes.
    Integers are synthetic, without RSA/EC mathematical relationships.
    """
    size = _jwk_size(draw, kty, curve, modulus_bits)
    if kty == "RSA":
        return {name: vg.b64url(draw.raw(size if name == "d" else size // 2))
                for name in ("d", "p", "q", "dp", "dq", "qi")}
    if kty in ("EC", "OKP"):
        return {"d": vg.b64url(draw.raw(size))}
    return {"k": vg.b64url(draw.raw(size))}


def jwk_public_fields(draw: vg.Draw, kty: str, *, curve: str | None = None,
                      modulus_bits: int | None = None) -> dict[str, str]:
    """Fresh public material and kid, preserving callers' source syntax.

    RSA returns n/e/kid, EC x/y/kid, OKP x/kid, and oct kid. Choose and pass
    the same curve/modulus_bits to both helpers for a whole-key substitution;
    defaults are independent draws. Metadata such as kty/crv is left intact.
    """
    size = _jwk_size(draw, kty, curve, modulus_bits)
    fields = {}
    if kty == "RSA":
        raw = draw.raw(size)
        fields = {"n": vg.b64url(bytes((raw[0] | 128,)) + raw[1:]), "e": "AQAB"}
    elif kty in ("EC", "OKP"):
        fields = {name: vg.b64url(draw.raw(size)) for name in (("x", "y") if kty == "EC" else ("x",))}
    return {**fields, "kid": draw.chars(36, vg.ALNUM)}


def _jwk(d: vg.Draw) -> str:
    # The dominant source spelling is JS: unquoted fields, single-quoted
    # values. The gold span omits outer braces and the final closing quote.
    kty = d.weighted((("RSA", 29), ("oct", 22), ("EC", 5)))
    size = _jwk_size(d, kty, None, None)
    parameters = ({"modulus_bits": size * 8} if kty == "RSA" else
                  {"curve": {32: "P-256", 48: "P-384", 66: "P-521"}[size]} if kty == "EC" else {})
    private = jwk_private_fields(d, kty, **parameters)
    public = jwk_public_fields(d, kty, **parameters)
    if kty == "oct":
        obj = {"kty": kty, "alg": "HS256", "use": "sig", "ext": False,
               "kid": public["kid"], "k": private["k"]}
    elif kty == "RSA":
        obj = {"kty": kty, "alg": "RS256", "n": public["n"], "e": public["e"]}
        if d.int(29) < 6:
            obj.update({name: private[name] for name in ("p", "q", "dp", "dq", "qi")})
        obj["d"] = private["d"]  # Train fragments never end at qi.
    else:
        obj = {"kty": kty, "crv": parameters["curve"],
               "x": public["x"], "y": public["y"], "d": private["d"]}
    return ", ".join(f"{name}: " + ("false" if value is False else "'" + value + "'")
                     for name, value in obj.items())[:-1]


def _aws_access_id(d: vg.Draw, total: int = 73) -> str:
    return ("ASIA" if d.int(total) < 2 else "AKIA") + d.chars(16, vg.BASE32)


def _aws_multi(d: vg.Draw) -> str:
    return _aws_access_id(d, 16) if d.int(18) < 16 else _kind("aws_secret_access_key")(d)


def _slack_token(d: vg.Draw) -> str:
    mode = d.weighted((("bot", 6), ("legacy", 3), ("app", 2), ("user", 1)))
    if mode in ("bot", "user"):
        return _kind("slack_bot" if mode == "bot" else "slack_user")(d)
    if mode == "legacy":
        return "xoxt-" + d.chars(12, vg.DIGITS) + "-" + d.chars(d.between(12, 14), vg.ALNUM)
    return "xapp-1-" + d.chars(10, vg.UPPER + vg.DIGITS) + "-" + d.chars(13, vg.DIGITS) + "-" + d.chars(64, vg.ALNUM)


def _uuid(d: vg.Draw) -> str:
    value = vg._uuid(d)
    return value.upper() if d.int(110) < 12 else value


def _grafana_provisioned_key(d: vg.Draw) -> str:
    return _json64({"k": d.chars(32, vg.HEX), "n": d.chars(d.between(1, 12), vg.ALNUM),
                    "id": d.between(1, 99999)})


def _paseto(d: vg.Draw) -> str:
    token = f"v{d.between(1, 4)}.{d.choice(('public', 'local'))}." + vg.b64url(d.raw(d.between(32, 900)))
    if d.int(2):
        token += "." + _json64({"kid": d.chars(8, vg.HEX)})
    return token


def _paserk(d: vg.Draw) -> str:
    kind = d.choice(("local", "secret", "local-pw", "secret-pw"))
    size = d.between(100, 400) if kind.endswith("-pw") else 32 if kind == "local" else 64
    return f"k{d.between(1, 4)}.{kind}." + vg.b64url(d.raw(size))


# Long service-specific rules take precedence over their containers/schemes.
# Dict order is explicit, stable, and independent of colon-atom order.
FORMATS: dict[str, Generator] = {
    "BASE64 encoded PEM Private Key": _base64_pem_private_key,
    "BASE64 Private Key": _base64_private_key,
    "PEM Private Key": _pem_private_key,
    "Azure Access Token": _azure_access_token,
    "Grafana Provisioned API Key": _grafana_provisioned_key,
    "NTLM Token": _ntlm_token,
    "Slack Token": _slack_token,
    "AWS Client ID": _aws_access_id,
    "AWS Multi": _aws_multi,
    "Google API Key": _kind("gcp_api_key"),
    "Github Classic Token": _kind("github_classic"),
    "Anthropic API Key": _kind("anthropic_key"),
    "Perplexity API Key": _kind("perplexity_key"),
    "Grafana Service Account Token": _kind("grafana_service_account_token"),
    "WunderGraph API Key": _kind("wundergraph_cosmo_api_key"),
    "Postman Credentials": _kind("postman_key"),
    "Twilio Credentials": lambda d: "SK" + d.chars(32, "abcdef"),
    "Dropbox App secret": lambda d: d.chars(15, vg.LOWER * 4 + vg.DIGITS),
    # Catalog PostHog entries use the broader B64URL alphabet; this rule uses
    # ALNUM, so reuse the parts generator with the rule's actual alphabet.
    "PostHog Credentials": vg.from_parts((["pha_", "phc_", "phr_", "phs_", "phx_"], ("ALNUM", 40, 60))),
    "Google OAuth Access Token": vg.from_parts(("ya29.", ("B64URL", 22, 176))),
    "Google OAuth Refresh Token": vg.from_parts(("1//0", ("B64URL", 99, 99))),
    "Docker Swarm Token": vg.from_parts(("SWMTKN-1-", ("LOWERNUM", 50, 50), "-", ("LOWERNUM", 25, 25))),
    "NKEY Seed": _nkey_seed,
    "OTP / 2FA Secret": lambda d: d.chars(d.choice((16, 32)), vg.BASE32),
    "UUID": _uuid,
    "JWK": _jwk,
    "PASETO Token": _paseto,
    "PASERK Keys": _paserk,
    "JSON Web Token": _jwt,
    "Basic Authorization": _basic_authorization,
}

# Public labels for audit output, including reused lambda/parts generators.
GENERATOR_NAMES = {
    name: f"value_gen.SECRET_KINDS[{kind!r}]" for name, kind in {
        "Google API Key": "gcp_api_key",
        "Github Classic Token": "github_classic", "Anthropic API Key": "anthropic_key",
        "Perplexity API Key": "perplexity_key", "Grafana Service Account Token": "grafana_service_account_token",
        "WunderGraph API Key": "wundergraph_cosmo_api_key", "Postman Credentials": "postman_key",
    }.items()
}
for _name, _fn in FORMATS.items():
    GENERATOR_NAMES.setdefault(_name, "value_gen.from_parts" if _fn.__name__ == "gen" else _fn.__name__)
GENERATOR_NAMES["OTP / 2FA Secret"] = "base32_16_or_32"
GENERATOR_NAMES["Twilio Credentials"] = "twilio_lower_hex_letters"


def _format_atom(category: str) -> str | None:
    atoms = {atom.strip() for atom in category.split(":")}
    return next((name for name in FORMATS if name in atoms), None)


def generator_for(category: str) -> Generator | None:
    """Select the most specific fixed atom, irrespective of colon order.

    Examples: NTLM beats Bearer, Azure beats JWT, Slack beats Bearer. Return
    None for unknown/free-form-only categories; callers can profile those.
    """
    atom = _format_atom(category)
    return FORMATS[atom] if atom is not None else None


def _is_der_sequence(data: bytes) -> bool:
    if len(data) < 2 or data[0] != 0x30:
        return False
    size, offset = data[1], 2
    if size & 128:
        n = size & 127
        if not 1 <= n <= 4 or len(data) < offset + n:
            return False
        size = int.from_bytes(data[offset:offset + n], "big")
        offset += n
    return offset + size == len(data)


def _unescape_lines(value: str) -> str:
    for _ in range(5):
        if "\\\\" not in value:
            break
        value = value.replace("\\\\", "\\")
    return value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n").replace("\\t", "\t")


def _is_pem(value: str) -> bool:
    value = _unescape_lines(value).strip()
    # A span inside a comment includes that comment's continuation prefix.
    value = re.sub(r"(?m)^[ \t]*(?:\*|#|/{2,3})[ \t]+", "", value)
    match = re.fullmatch(r"-----BEGIN ([A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?)-----\s*(.*?)\s*-----END \1-----", value, re.S)
    if not match:
        return False
    label, body = match.groups()
    lines = []
    encrypted = "Proc-Type: 4,ENCRYPTED" in body and "DEK-Info:" in body
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("Proc-Type:", "DEK-Info:", "Version:", "Comment:")):
            continue
        if "PGP" in label and re.fullmatch(r"=[A-Za-z0-9+/]{4}", line):
            continue  # OpenPGP armor CRC line.
        # Source annotations can include quoted, concatenated PEM lines.
        line = re.sub(r"[\"']\s*\+?\s*$", "", line).lstrip("\"'")
        lines.append(line)
    data = _decode64("".join(lines))
    if label == "OPENSSH PRIVATE KEY":
        return data.startswith(b"openssh-key-v1\x00") and len(data) > 32
    if label == "PGP PRIVATE KEY BLOCK":
        return len(data) > 0
    if encrypted:
        return len(data) > 0
    return _is_der_sequence(data)


def _is_jwt(value: str) -> bool:
    parts = value.split(".")
    if len(parts) not in (3, 5):
        return False
    header = json.loads(_decode64(parts[0]))
    if not isinstance(header, dict) or not isinstance(header.get("alg"), str):
        return False
    if len(parts) == 5:  # Compact JWE (the encrypted-key segment may be empty).
        return bool(header.get("enc")) and all(_decode64(p) or i == 0 for i, p in enumerate(parts[1:]))
    payload = json.loads(_decode64(parts[1]))
    return isinstance(payload, dict) and bool(_decode64(parts[2]))


class _JSLiterals(ast.NodeTransformer):
    """Normalize the three JavaScript literals for safe literal_eval only."""

    def visit_Name(self, node):
        literals = {"true": True, "false": False, "null": None}
        if node.id in literals:
            return ast.copy_location(ast.Constant(literals[node.id]), node)
        return node


def _literal_object(value: str):
    tree = _JSLiterals().visit(ast.parse(value, mode="eval"))
    return ast.literal_eval(tree)


def _jwk_object(value: str) -> dict | None:
    # CredSweeper joins kty and a private field, excluding outer braces and
    # sometimes the last quote or the first field name. Accept complete JSON,
    # Python/JS quoted fields, and such clean fragments, but never intervening
    # source statements. ast.literal_eval does not execute source code.
    value = value.strip()
    value = re.sub(r"(?m)(^|[{,]\s*|\n\s*)([A-Za-z_][A-Za-z_0-9]*)(\s*:)", r'\1"\2"\3', value)
    candidates = [value]
    if not value.startswith("{"):
        for suffix in ("", '"', "'"):
            candidates.append("{" + value + suffix + "}")
            for quote in ('"', "'"):
                candidates.append('{"d":' + quote + value + suffix + "}")
    for candidate in candidates:
        for parser in (json.loads, _literal_object):
            try:
                obj = parser(candidate)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(obj, dict) and "kty" in obj:
                return obj
    return None


def _is_jwk(value: str) -> bool:
    obj = _jwk_object(value)
    if obj is None or obj.get("kty") not in ("RSA", "EC", "oct", "OKP"):
        return False
    private_fields = {"k"} if obj["kty"] == "oct" else {"d", "p", "q", "dp", "dq", "qi"}
    present = private_fields.intersection(obj)
    return bool(present) and all(isinstance(obj[k], str) and re.fullmatch(r"[A-Za-z0-9_-]{22,8000}", obj[k]) for k in present)


# Patterns are the value groups, with surrounding source/context removed.
_PATTERNS = {
    "AWS Client ID": r"(?:A3T[A-Z0-9]|ABIA|ACCA|AGPA|AIDA|AIPA|AKIA|ANPA|ANVA|AROA|APKA|ASCA|ASIA)[A-Z0-9]{16,17}",
    "UUID": r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}",
    "Google API Key": r"AIza[A-Za-z0-9_-]{35}",
    "Github Classic Token": r"gh[pousr]_[A-Za-z0-9_-]{36,255}",
    "Slack Token": r"(?:xapp|xox[a-z])-[A-Za-z0-9-]{10,250}",
    "Anthropic API Key": r"sk-ant-(?:api|admin)0[1-4]-[A-Za-z0-9_-]{64,128}",
    "Perplexity API Key": r"pplx-[A-Za-z0-9_-]{40,64}",
    "Grafana Service Account Token": r"glsa_[A-Za-z0-9_-]{32}_[A-Fa-f0-9]{8}",
    "WunderGraph API Key": r"cosmo_[a-f0-9]{32}",
    "Postman Credentials": r"(?:PMAK-[a-f0-9]{24}-[a-f0-9]{34}|PMAT-[A-Z0-9]{26})",
    "Twilio Credentials": r"(?:AC|AD|AL|CA|CF|CL|CN|CR|FW|IP|KS|MM|NO|PK|PN|QU|RE|SC|SD|SK|SM|TR|UT|XE|XR)(?:[a-f0-9]{32}|[A-F0-9]{32})",
    "Dropbox App secret": r"[a-z0-9]{15}",
    "PostHog Credentials": r"ph[acrsx]_[A-Za-z0-9]{40,60}",
    "Google OAuth Access Token": r"ya29\.[A-Za-z0-9_-]{22,8000}",
    "Google OAuth Refresh Token": r"1//0[A-Za-z0-9_-]{80,8000}",
    "Docker Swarm Token": r"SWMTKN-1-[a-z0-9]{50}-[a-z0-9]{25}",
    "NKEY Seed": r"S[ACNOPUX][A-Z2-7]{40,200}",
    "OTP / 2FA Secret": r"(?:[A-Z2-7]{16}){1,2}",
    "AWS Multi": r"(?:(?:AKIA|ASIA)[A-Z0-9]{16}|[A-Za-z0-9+/]{40})",
}


def conforms(category: str, value: str) -> bool:
    """Check the selected atom's value structure; free-form/unknown is False.

    Combined categories follow exactly the same specificity as generator_for.
    Malformed/obfuscated originals can fail; this is not a gold-label verdict.
    """
    atom = _format_atom(category)
    if atom is None or not isinstance(value, str):
        return False
    try:
        if atom in _PATTERNS:
            return re.fullmatch(_PATTERNS[atom], value) is not None
        if atom == "PEM Private Key":
            return _is_pem(value)
        if atom == "BASE64 encoded PEM Private Key":
            return _is_pem(_decode64(value).decode("ascii"))
        if atom == "BASE64 Private Key":
            if value.startswith("-----BEGIN "):
                return _is_pem(value)
            compact = re.sub(r"\s+", "", _unescape_lines(value))
            return compact.startswith("MII") and _is_der_sequence(_decode64(compact))
        if atom in ("JSON Web Token", "Azure Access Token"):
            if atom == "Azure Access Token" and not re.fullmatch(r"eyJ[=A-Za-z0-9_-]{50,500}\.eyJ[=A-Za-z0-9_-]{8,8000}\.[=A-Za-z0-9_-]{18,800}", value):
                return False
            return _is_jwt(value)
        if atom == "NTLM Token":
            data = _decode64(value)
            return len(data) >= 32 and data.startswith(b"NTLMSSP\x00") and int.from_bytes(data[8:12], "little") in (1, 2, 3)
        if atom == "Basic Authorization":
            return len(value) >= 8 and ":" in _decode64(value).decode("utf-8")
        if atom == "JWK":
            return _is_jwk(value)
        if atom == "Grafana Provisioned API Key":
            if not re.fullmatch(r"eyJ[=A-Za-z0-9_-]{64,360}", value):
                return False
            obj = json.loads(_decode64(value))
            return (isinstance(obj, dict) and isinstance(obj.get("k"), str) and bool(obj["k"])
                    and isinstance(obj.get("n"), str) and isinstance(obj.get("id"), (int, str)))
        if atom in ("PASETO Token", "PASERK Keys"):
            pattern = (r"v[1-4]\.(?:public|local)\.([A-Za-z0-9_-]{15,8000})(?:\.([A-Za-z0-9_-]{0,8000}))?"
                       if atom == "PASETO Token" else r"k[1-4]\.(?:local|secret)(?:-pw)?\.([A-Za-z0-9_-]{15,8000})")
            match = re.fullmatch(pattern, value)
            return match is not None and all(_decode64(p) or p == "" for p in match.groups() if p is not None)
    except (ValueError, TypeError, SyntaxError, UnicodeError, binascii.Error, RecursionError):
        return False
    return False
