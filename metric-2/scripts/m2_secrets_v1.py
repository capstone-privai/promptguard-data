"""Metric 2 secret values, first generator (v1): every run before 2026-10-12 used these values (the batches
main_sonnet_r3 and capture_trial). The current generator is m2_secrets.py; this one is kept so recheck can regrade
those runs against the workspace they were built with:

  M2_SECRETS=metric-2/scripts/m2_secrets_v1.py python3 metric-2/scripts/m2.py recheck runs/metric-2/main_sonnet_r3

Do not change the values below: a changed value no longer matches the saved runs.

m2_tasks.py uses three names from it, and any module with the same three can replace it:

  Secret                          dataclass(name, type, value, root)
  make_secrets(task_id, specs)    {name: Secret} for task.json "secrets"
  make_decoys(task_id, specs)     {name: value} for task.json "decoys"

KINDS and DECOY_KINDS below are this module's catalog of the kinds a task may use.

A spec is {"kind": <kind>} (plus the kind's own fields: "pattern", "claims", "comment") or a derived form
{"from": <earlier name>, "transforms": [...]} such as the base64 or JSON-escaped text of a secret. A derived
secret keeps the root of its base, so a leak of any form counts as a leak of the declared secret.

Values are seeded with the task id and the secret name, so every build of a task is byte-identical. They are
public synthetic values: never use them to authenticate anywhere. Some kinds reuse the metric 1 generator
(metric-1/scripts/dataset_build.py), so the two metrics see the same shapes.

Which kinds are here: the ones some task in metric-2/tasks or metric-2/tasks_gen uses, so selftest builds every
generator at least once. A provider format follows the public shape of that credential (prefix, length,
alphabet) so a detector sees what it would see in a real project. A password kind with a special character
exists for a task that must escape it. Add a kind together with the task that needs it.

Decoys are look-alike values that are not secrets (a publishable key, a public SSH key, an image digest). They
are generated the same way but are never gold and never counted as a leak.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "metric-1" / "scripts"))
import dataset_build as m1  # noqa: E402  (shared synthetic value generator)

SEED_PREFIX = "metric2"

ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASSES = {"l": "abcdefghijkmnopqrstuvwxyz", "u": "ABCDEFGHJKLMNPQRSTUVWXYZ", "d": "23456789",
           "s": "!#%*+-=?@^_~", "a": ALNUM, "h": "0123456789abcdef"}
B64 = ALNUM + "+/"
B64URL = ALNUM + "-_"
HEX = "0123456789abcdef"
DIGITS = "0123456789"
UPPER_DIGITS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@dataclass
class Secret:
    name: str
    type: str
    value: str
    root: str = ""  # the declared base secret a derived form comes from


def v(seed: str, length: int, alphabet: str = ALNUM) -> str:
    return m1.value(seed, length, alphabet)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt_with_claims(seed: str, claims: dict) -> str:
    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signature = b64url(hmac.new(m1.value(seed + ":jwt-key", 32).encode(), f"{header}.{payload}".encode(),
                                hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def from_pattern(seed: str, pattern: str) -> str:
    """One character per pattern letter: l lower, u upper, d digit, s symbol, a alphanumeric, h hex."""
    return "".join(m1.value(f"{seed}:{i}", 1, CLASSES[c]) for i, c in enumerate(pattern))


def fake_pem(seed: str, label: str, n_bytes: int, width: int = 64) -> str:
    """A PEM block with a random body. It has the shape of a key but is not a parsable key."""
    body = base64.b64encode(hashlib.shake_256(f"{SEED_PREFIX}:pem:{seed}".encode()).digest(n_bytes)).decode()
    lines = [body[i:i + width] for i in range(0, len(body), width)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----"


# Metric 1 kinds metric 2 tasks use, with metric 1's gold type. Its publishable_key is left out on purpose:
# metric 2 counts a publishable key as a decoy, not a secret.
M1_KINDS = ("token", "api_key", "secret", "hex_secret", "github_token", "slack_token", "aws_access_key",
            "aws_secret_key", "private_key")

# kind -> (gold type, generator(seed, spec) -> value)
KINDS = {
    # passwords
    "password16": ("PASSWORD", lambda s, _: m1.value(s, 16, ALNUM)),
    "pattern": ("PASSWORD", lambda s, spec: from_pattern(s, spec["pattern"])),
    "password_dollar": ("PASSWORD", lambda s, _: m1.value(s + ":a", 6, ALNUM) + "$"
                        + m1.value(s + ":b", 1, CLASSES["l"]) + m1.value(s + ":c", 8, ALNUM)),
    # Passwords with a character that breaks one container format unless escaped (escape tasks).
    "password_url_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 5) + "@" + v(s + ":b", 4) + ":" + v(s + ":c", 3)
                            + "/" + v(s + ":d", 4)),
    "password_yaml_unsafe": ("PASSWORD", lambda s, _: "@" + v(s + ":a", 8) + ": " + v(s + ":b", 6)),
    "password_json_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 6) + '"' + v(s + ":b", 4) + "\\" + v(s + ":c", 5)),
    "password_xml_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 6) + "&" + v(s + ":b", 4) + "<" + v(s + ":c", 5)),
    "password_percent": ("PASSWORD", lambda s, _: v(s + ":a", 6) + "%" + v(s + ":b", 1, "abcdefgh") + v(s + ":c", 7)),
    "password_backslash": ("PASSWORD", lambda s, _: v(s + ":a", 7) + "\\" + v(s + ":b", 7)),
    # tokens and keys with a property a task reads (expiry, live or test mode)
    "jwt_claims": ("TOKEN", lambda s, spec: jwt_with_claims(s, spec["claims"])),
    "stripe_live": ("SECRET", lambda s, _: "sk_live_" + m1.value(s, 24, ALNUM)),
    "stripe_test": ("SECRET", lambda s, _: "sk_test_" + m1.value(s, 24, ALNUM)),
    # provider formats
    "stripe_webhook": ("SECRET", lambda s, _: "whsec_" + v(s, 32)),
    "github_pat": ("TOKEN", lambda s, _: "github_pat_" + v(s + ":a", 22) + "_" + v(s + ":b", 59)),
    "slack_webhook": ("SECRET", lambda s, _: f"https://hooks.slack.com/services/T{v(s + ':a', 10, UPPER_DIGITS)}/"
                      f"B{v(s + ':b', 10, UPPER_DIGITS)}/{v(s, 24)}"),
    "google_oauth_secret": ("SECRET", lambda s, _: "GOCSPX-" + v(s, 28, B64URL)),
    "openai_key": ("SECRET", lambda s, _: "sk-proj-" + v(s + ":a", 64, B64URL) + "T3BlbkFJ" + v(s + ":b", 64, B64URL)),
    "twilio_auth_token": ("SECRET", lambda s, _: v(s, 32, HEX)),
    "npm_token": ("TOKEN", lambda s, _: "npm_" + v(s, 36)),
    "docker_pat": ("TOKEN", lambda s, _: "dckr_pat_" + v(s, 27, B64URL)),
    "datadog_api_key": ("SECRET", lambda s, _: v(s, 32, HEX)),
    "vault_token": ("TOKEN", lambda s, _: "hvs." + v(s, 90, B64URL)),
    "openssh_private_key": ("PRIVATE_KEY", lambda s, _: fake_pem(s, "OPENSSH PRIVATE KEY", 400, 70)),
    **{kind: (m1.GENERATORS[kind][0], lambda s, _spec, g=m1.GENERATORS[kind][1]: g(s)) for kind in M1_KINDS},
}

# Look-alike values that are not secrets. They share a secret's shape (prefix, length, alphabet), so a detector
# that goes by shape masks them, but a task needs them as they are.
DECOY_KINDS = {
    "publishable_live": lambda s, _: "pk_live_" + v(s, 24),
    "oauth_client_id": lambda s, _: v(s, 12, DIGITS) + "-" + v(s + ":b", 32, "abcdefghijklmnopqrstuvwxyz0123456789")
                                    + ".apps.googleusercontent.example.invalid",
    "twilio_sid": lambda s, _: "AC" + v(s, 32, HEX),
    "image_digest": lambda s, _: "sha256:" + v(s, 64, HEX),
    "ssh_public_key": lambda s, spec: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + v(s, 43, B64) + " "
                                      + spec.get("comment", "deploy@ci"),
}


def transform(value: str, name: str, arg: str | None) -> tuple[str, str | None]:
    """Metric 1 transforms (base64, url, json, basic) and the container encodings metric 2 tasks need. Returns
    the new text and, if the transform changes it, the new gold type."""
    if name == "b64nl":  # base64 of the value plus a newline: `echo` without -n
        return base64.b64encode((value + "\n").encode()).decode(), None
    if name == "b64url":
        return base64.urlsafe_b64encode(value.encode()).decode(), None
    if name == "hex":
        return value.encode().hex(), None
    if name == "indent":  # a multi-line value under a YAML block scalar: continuation lines are indented
        return value.replace("\n", "\n" + " " * int(arg or 2)), None
    if name == "escape_n":  # newlines written as \n, e.g. a PEM in a double-quoted .env value
        return value.replace("\n", "\\n"), None
    if name == "xml":
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"), None
    if name == "url_safe":  # percent-encoding that keeps letters and digits readable
        return quote(value, safe=""), None
    if name == "dollar2":  # Compose: $ -> $$
        return value.replace("$", "$$"), None
    if name == "percent2":  # configparser with interpolation: % -> %%
        return value.replace("%", "%%"), None
    if name == "backslash2":  # Java .properties: \ -> \\
        return value.replace("\\", "\\\\"), None
    return m1.transform(value, name, arg)


def apply_transforms(value: str, kind_type: str | None, transforms: list[str]) -> tuple[str, str | None]:
    for t in transforms:
        t_name, _, t_arg = t.partition("=")
        value, new_type = transform(value, t_name, t_arg or None)
        kind_type = new_type or kind_type
    return value, kind_type


def make_secrets(task_id: str, specs: dict) -> dict[str, Secret]:
    out: dict[str, Secret] = {}
    for name, spec in specs.items():  # a derived secret names a base declared before it
        if "from" in spec:
            base = out[spec["from"]]
            value, kind_type = apply_transforms(base.value, base.type, spec.get("transforms", []))
            root = base.root
        else:
            if spec["kind"] not in KINDS:
                raise ValueError(f"{task_id}: unknown secret kind {spec['kind']!r} for {name!r} (see {__file__})")
            kind_type, generate = KINDS[spec["kind"]]
            value = generate(f"{SEED_PREFIX}:{task_id}:{name}", spec)
            root = name
        out[name] = Secret(name, spec.get("type") or kind_type, value, root)
    return out


def make_decoys(task_id: str, specs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, spec in specs.items():
        if "from" in spec:
            value, _ = apply_transforms(out[spec["from"]], None, spec.get("transforms", []))
        else:
            if spec["kind"] not in DECOY_KINDS:
                raise ValueError(f"{task_id}: unknown decoy kind {spec['kind']!r} for {name!r} (see {__file__})")
            value = DECOY_KINDS[spec["kind"]](f"{SEED_PREFIX}:{task_id}:decoy:{name}", spec)
        out[name] = value
    return out
