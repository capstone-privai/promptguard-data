"""Ed25519 request signing for partner APIs (HTTP Signatures, draft-cavage-12 style).

Pure Python so integrations need no compiled dependency; RFC 8032 section 5.1 arithmetic. Keys are the
partners' sandbox signing keys; production keys come from the vault at deploy time.
"""
from __future__ import annotations
import base64
import hashlib

PRIVATE_KEYS = {
    "ledger": """{{secret:pem_ledger}}""",
    "relay": """{{secret:pem_relay}}""",
    "audit": """{{secret:pem_audit}}""",
}
KEY_IDS = {"ledger": "orderdesk-ledger-2026", "relay": "orderdesk-relay-1", "audit": "orderdesk-audit-2026q4"}

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_PKCS8_ED25519 = bytes.fromhex("302e020100300506032b657004220420")


def _recover_x(y: int, sign: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = x * _I % _P
    return _P - x if x % 2 != sign else x


_GY = 4 * pow(5, _P - 2, _P) % _P
_G = (_recover_x(_GY, 0), _GY, 1, _recover_x(_GY, 0) * _GY % _P)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _mul(scalar: int, point):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point, scalar = _add(point, point), scalar >> 1
    return result


def _encode(point) -> bytes:
    zi = pow(point[2], _P - 2, _P)
    x, y = point[0] * zi % _P, point[1] * zi % _P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def _seed(name: str) -> bytes:
    pem = PRIVATE_KEYS[name]
    der = base64.b64decode("".join(line for line in pem.splitlines() if not line.startswith("-----")))
    if len(der) != 48 or not der.startswith(_PKCS8_ED25519):
        raise ValueError(f"{name}: not an Ed25519 PKCS#8 private key")
    return der[16:]


def sign(name: str, message: bytes) -> bytes:
    digest = hashlib.sha512(_seed(name)).digest()
    a = int.from_bytes(digest[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    public = _encode(_mul(a, _G))
    r = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little") % _L
    big_r = _encode(_mul(r, _G))
    k = int.from_bytes(hashlib.sha512(big_r + public + message).digest(), "little") % _L
    return big_r + ((r + k * a) % _L).to_bytes(32, "little")


def digest_header(body: bytes) -> str:
    return "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")


def signature_header(name: str, method: str, path: str, body: bytes, created: int) -> str:
    """Signature over (request-target), (created) and digest, as the partners verify it."""
    signed = f"(request-target): {method.lower()} {path}\n(created): {created}\ndigest: {digest_header(body)}"
    value = base64.b64encode(sign(name, signed.encode("utf-8"))).decode("ascii")
    return (f'keyId="{KEY_IDS[name]}",algorithm="ed25519",created={created},'
            f'headers="(request-target) (created) digest",signature="{value}"')
