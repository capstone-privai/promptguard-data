"""metric-task secret values: synthetic keys in the shape real projects hold.

Every kind follows the public format of the credential it stands for: its prefix, length, alphabet and structure
(mixed-case base62 where the provider uses it, the CRC32 checksum GitHub and npm put in their tokens, the binary
layout of an OpenSSH key). The random part is drawn with rstr (github.com/leapfrogonline/rstr, BSD), a Python
regex-to-string generator, seeded with the task id and the secret name, so every build of a task is
byte-identical. The values are public synthetic values: never use them to authenticate anywhere.

A kind names the gitleaks rule (github.com/gitleaks/gitleaks, MIT) that should find it, where gitleaks has one,
and selftest runs the installed gitleaks to check that it does: an independent scanner agrees the value looks like
that provider's key.

  python3 metric-task/scripts/m2_secrets.py     list the kinds and check them with the installed gitleaks

m2_tasks.py uses three names from this module, and any module with the same three can replace it (set
M2_SECRETS=path/to/module.py; m2_secrets_v1.py is the generator every run before 2026-10-12 used):

  Secret                          dataclass(name, type, value, root)
  make_secrets(task_id, specs)    {name: Secret} for task.json "secrets"
  make_decoys(task_id, specs)     {name: value} for task.json "decoys"

A spec is {"kind": <kind>} (plus the kind's own fields: "pattern", "claims", "comment") or a derived form
{"from": <earlier name>, "transforms": [...]} such as the base64 or JSON-escaped text of a secret. A derived
secret keeps the root of its base, so a leak of any form counts as a leak of the declared secret.

Which kinds are here: the ones some task in metric-task/tasks or metric-task/tasks_gen uses, so selftest builds every
generator at least once. Add a kind together with the task that needs it. Decoys are look-alike values that are
not secrets (a publishable key, a public SSH key, an image digest): generated the same way, never gold, never
counted as a leak.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import shutil
import subprocess
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

try:
    import rstr
except ImportError:  # pragma: no cover
    raise SystemExit("metric-task needs rstr: pip install -r metric-task/requirements.txt")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "metric-detection" / "scripts"))
import dataset_build as m1  # noqa: E402  (metric-detection transforms and its Ed25519 PKCS#8 builder)

SEED_PREFIX = "metric2"


@dataclass
class Secret:
    name: str
    type: str
    value: str
    root: str = ""  # the declared base secret a derived form comes from


@dataclass(frozen=True)
class Kind:
    type: str | None                 # gold type (None for a decoy)
    regex: str = ""                  # the value is a random string matching this regex
    source: str = ""                 # the real format it follows
    rule: str = ""                   # the gitleaks rule that should find it ("" if gitleaks has none)
    build: Callable[[rstr.Rstr, str, dict], str] | None = None  # for a value a regex cannot describe


# ---- builders for structured values ------------------------------------------------------------------------

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def checksummed(prefix: str) -> Callable[[rstr.Rstr, str, dict], str]:
    """GitHub's token format (github.blog, 2021-04-05), which npm adopted: prefix, 30 random base62 characters,
    then the CRC32 of those 30 characters in base62, zero-padded to 6. Scanners check it offline."""
    def build(gen: rstr.Rstr, _seed: str, _spec: dict) -> str:
        body = gen.xeger("[A-Za-z0-9]{30}")
        crc, digits = zlib.crc32(body.encode()), ""
        while crc:
            crc, r = divmod(crc, 62)
            digits = BASE62[r] + digits
        return prefix + body + digits.rjust(6, "0")
    return build


def jwt_with_claims(gen: rstr.Rstr, _seed: str, spec: dict) -> str:
    """An HS256 JWT whose payload is the task's claims (a task reads the expiry), signed with a random key."""
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")
    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(json.dumps(spec["claims"], separators=(",", ":")).encode())
    key = gen.xeger(r"[A-Za-z0-9]{32}").encode()
    return f"{header}.{payload}.{b64url(hmac.new(key, f'{header}.{payload}'.encode(), hashlib.sha256).digest())}"


PATTERN_CLASSES = {"l": "[a-km-z]", "u": "[A-HJ-NP-Z]", "d": "[2-9]", "s": r"[!#%*+\-=?@^_~]", "a": "[A-Za-z0-9]",
                   "h": "[0-9a-f]"}


def from_pattern(gen: rstr.Rstr, _seed: str, spec: dict) -> str:
    """A password with a fixed character class per position: l lower, u upper, d digit, s symbol, a alphanumeric,
    h hex (a task reads its policy)."""
    return gen.xeger("".join(PATTERN_CLASSES[c] for c in spec["pattern"]))


# Ed25519 public key from a seed (RFC 8032, section 5.1.5), so an OpenSSH key holds a matching key pair.
_P = 2 ** 255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P


def _x_from_y(y: int) -> int:
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    return _P - x if x & 1 else x


def _add(a: tuple, b: tuple) -> tuple:
    p, q = (a[1] - a[0]) * (b[1] - b[0]) % _P, (a[1] + a[0]) * (b[1] + b[0]) % _P
    r, s = 2 * a[3] * b[3] * _D % _P, 2 * a[2] * b[2] % _P
    e, f, g, h = q - p, s - r, s + r, q + p
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


_GY = 4 * pow(5, _P - 2, _P) % _P
_G = (_x_from_y(_GY), _GY, 1, _x_from_y(_GY) * _GY % _P)


def ed25519_public(seed: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    scalar = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    point, base = (0, 1, 1, 0), _G
    while scalar:
        if scalar & 1:
            point = _add(point, base)
        base, scalar = _add(base, base), scalar >> 1
    z = pow(point[2], _P - 2, _P)
    x, y = point[0] * z % _P, point[1] * z % _P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def _ssh_string(data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + data


def openssh_key(_gen: rstr.Rstr, seed: str, spec: dict) -> str:
    """An unencrypted OpenSSH Ed25519 private key in the layout ssh-keygen writes (openssh-key-v1)."""
    rng = random.Random(seed + ":ssh")
    secret, check = rng.randbytes(32), rng.randbytes(4)
    public = ed25519_public(secret)
    key_type = _ssh_string(b"ssh-ed25519")
    private = (check + check + key_type + _ssh_string(public) + _ssh_string(secret + public)
               + _ssh_string(spec.get("comment", "deploy@ci").encode()))
    private += bytes(range(1, 1 + (-len(private)) % 8))
    blob = (b"openssh-key-v1\0" + _ssh_string(b"none") + _ssh_string(b"none") + _ssh_string(b"")
            + (1).to_bytes(4, "big") + _ssh_string(key_type + _ssh_string(public)) + _ssh_string(private))
    body = base64.b64encode(blob).decode()
    return ("-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(body[i:i + 70] for i in range(0, len(body), 70))
            + "\n-----END OPENSSH PRIVATE KEY-----")


def ssh_public_key(_gen: rstr.Rstr, seed: str, spec: dict) -> str:
    """An authorized_keys line for an Ed25519 key."""
    public = ed25519_public(random.Random(seed + ":ssh").randbytes(32))
    blob = _ssh_string(b"ssh-ed25519") + _ssh_string(public)
    return f"ssh-ed25519 {base64.b64encode(blob).decode()} {spec.get('comment', 'deploy@ci')}"


# ---- kinds --------------------------------------------------------------------------------------------------

ALNUM = "[A-Za-z0-9]"

KINDS: dict[str, Kind] = {
    # provider keys
    "stripe_live": Kind("SECRET", r"sk_live_51[A-Za-z0-9]{97}", "Stripe secret key: sk_live_ + 99 base62",
                        "stripe-access-token"),
    "stripe_test": Kind("SECRET", r"sk_test_51[A-Za-z0-9]{97}", "Stripe test secret key: sk_test_ + 99 base62",
                        "stripe-access-token"),
    "stripe_webhook": Kind("SECRET", r"whsec_[A-Za-z0-9]{32}", "Stripe webhook signing secret"),
    "github_token": Kind("TOKEN", source="GitHub classic PAT: ghp_ + 30 base62 + CRC32", rule="github-pat",
                         build=checksummed("ghp_")),
    "github_pat": Kind("TOKEN", r"github_pat_11[A-Z0-9]{20}_[A-Za-z0-9]{59}",
                       "GitHub fine-grained PAT: github_pat_ + 22 + _ + 59", "github-fine-grained-pat"),
    "npm_token": Kind("TOKEN", source="npm access token: npm_ + 30 base62 + CRC32 (GitHub's format)",
                      rule="npm-access-token", build=checksummed("npm_")),
    "aws_access_key": Kind("ACCESS_KEY", r"AKIA[A-Z2-7]{16}", "AWS access key ID: AKIA + 16 base32",
                           "aws-access-token"),
    "aws_secret_key": Kind("SECRET", r"[A-Za-z0-9/+]{40}", "AWS secret access key: 40 base64 characters"),
    "openai_key": Kind("SECRET", r"sk-proj-[A-Za-z0-9_-]{74}T3BlbkFJ[A-Za-z0-9_-]{74}",
                       "OpenAI project key: sk-proj- + 74 + T3BlbkFJ + 74", "openai-api-key"),
    "slack_token": Kind("TOKEN", r"xoxb-[0-9]{13}-[0-9]{13}-[A-Za-z0-9]{24}",
                        "Slack bot token: xoxb-<team>-<bot>-<24 base62>", "slack-bot-token"),
    "slack_webhook": Kind("SECRET", r"https://hooks\.slack\.com/services/T[A-Z0-9]{10}/B[A-Z0-9]{10}/[A-Za-z0-9]{24}",
                          "Slack incoming webhook: /services/T<team>/B<bot>/<24 base62>", "slack-webhook-url"),
    "google_oauth_secret": Kind("SECRET", r"GOCSPX-[A-Za-z0-9_-]{28}", "Google OAuth client secret: GOCSPX- + 28"),
    "twilio_auth_token": Kind("SECRET", r"[a-f0-9]{32}", "Twilio auth token: 32 hex"),
    "docker_pat": Kind("TOKEN", r"dckr_pat_[A-Za-z0-9_-]{27}", "Docker Hub access token: dckr_pat_ + 27"),
    "datadog_api_key": Kind("SECRET", r"[a-f0-9]{32}", "Datadog API key: 32 hex"),
    "vault_token": Kind("TOKEN", r"hvs\.CAESI[A-Za-z0-9_-]{86}", "HashiCorp Vault service token: hvs. + 91 base64url",
                        "vault-service-token"),
    "jwt_claims": Kind("TOKEN", source="HS256 JWT with the task's claims", rule="jwt", build=jwt_with_claims),
    "openssh_private_key": Kind("PRIVATE_KEY", source="OpenSSH Ed25519 private key (openssh-key-v1)",
                                rule="private-key", build=openssh_key),
    "private_key": Kind("PRIVATE_KEY", source="Ed25519 PKCS#8 PEM (metric-detection's builder)", rule="private-key",
                        build=lambda _gen, seed, _spec: m1.ed25519_pem(seed)),
    # secrets with no provider format: what frameworks and scripts generate
    "token": Kind("TOKEN", ALNUM + "{40}", "API token: 40 base62"),
    "api_key": Kind("SECRET", ALNUM + "{32}", "API key: 32 base62"),
    "secret": Kind("SECRET", r"[A-Za-z0-9_-]{43}", "secrets.token_urlsafe(32): 43 base64url"),
    "hex_secret": Kind("SECRET", r"[a-f0-9]{64}", "secrets.token_hex(32): 64 hex"),
    # passwords
    "password16": Kind("PASSWORD", ALNUM + "{16}", "password: 16 alphanumeric"),
    "pattern": Kind("PASSWORD", source="password with a character class per position", build=from_pattern),
    "password_dollar": Kind("PASSWORD", ALNUM + r"{6}\$[a-z]" + ALNUM + "{8}",
                            "password with $x, which Compose reads as a variable"),
    # passwords with a character that breaks one container format unless escaped (escape tasks)
    "password_url_unsafe": Kind("PASSWORD", ALNUM + "{5}@" + ALNUM + "{4}:" + ALNUM + "{3}/" + ALNUM + "{4}",
                                "password with @ : / (URL)"),
    "password_yaml_unsafe": Kind("PASSWORD", "@" + ALNUM + "{8}: " + ALNUM + "{6}", "password with @ and ': ' (YAML)"),
    "password_json_unsafe": Kind("PASSWORD", ALNUM + '{6}"' + ALNUM + r"{4}\\" + ALNUM + "{5}",
                                 'password with " and \\ (JSON)'),
    "password_xml_unsafe": Kind("PASSWORD", ALNUM + "{6}&" + ALNUM + "{4}<" + ALNUM + "{5}", "password with & < (XML)"),
    "password_percent": Kind("PASSWORD", ALNUM + "{6}%[a-h]" + ALNUM + "{7}", "password with % (configparser)"),
    "password_backslash": Kind("PASSWORD", ALNUM + r"{7}\\" + ALNUM + "{7}", "password with \\ (Java properties)"),
}

# Appended kinds keep every pre-existing kind, seed and generation order unchanged.
KINDS.update({
    "gitlab_pat": Kind("TOKEN", r"glpat-[A-Za-z0-9_-]{20}", "GitLab personal access token", "gitlab-pat"),
    "azure_storage_key": Kind("SECRET", source="Azure Storage account key: 64 bytes in base64",
                              build=lambda _g, seed, _p: base64.b64encode(random.Random(seed).randbytes(64)).decode()),
    "stripe_publishable": Kind("ACCESS_KEY", r"pk_live_51[A-Za-z0-9]{97}", "Stripe publishable credential (LABELING.md)"),
    "anthropic_key": Kind("SECRET", r"sk-ant-api03-[A-Za-z0-9_-]{93}AA",
                          "Anthropic API key (gitleaks v8.30.1 anthropic.go)", "anthropic-api-key"),
    "session_cookie": Kind("TOKEN", r"[A-Za-z0-9_-]{43}", "opaque authenticated session cookie"),
})

DECOY_KINDS: dict[str, Kind] = {
    "request_id": Kind(None, r"req_[a-f0-9]{24}", "request correlation identifier"),
    "resource_id": Kind(None, r"res_[a-f0-9]{20}", "resource identifier"),
    "commit_hash": Kind(None, r"[a-f0-9]{40}", "commit identifier"),
    "redaction": Kind(None, source="visible redaction marker", build=lambda _g, _s, _p: "[REDACTED]"),
    "template": Kind(None, source="unfilled credential template", build=lambda _g, _s, _p: "<your-token>"),
    "reference": Kind(None, source="environment reference", build=lambda _g, _s, _p: "${SUPPORT_TOKEN}"),
    "code": Kind(None, source="code expression", build=lambda _g, _s, _p: "load_runtime_config()"),
    "doc_example": Kind(None, source="explicit documentation example", build=lambda _g, _s, _p: "EXAMPLE-credential-for-docs"),
    "descriptor": Kind(None, source="credential descriptor", build=lambda _g, _s, _p: "temporary password"),
    "password_hash": Kind(None, r"\$2b\$12\$[./A-Za-z0-9]{53}", "one-way bcrypt password hash"),
    "csrf_token": Kind(None, r"[A-Za-z0-9_-]{32}", "CSRF anti-forgery token, not authentication"),
    "empty": Kind(None, source="empty value", build=lambda _g, _s, _p: ""),
    # Public values in the shape of the secret they sit next to, so a detector that goes by shape masks them.
    "publishable_live": Kind(None, r"pk_live_51[A-Za-z0-9]{97}", "Stripe publishable key: pk_live_ + 99 base62"),
    "oauth_client_id": Kind(None, r"[0-9]{12}-[a-z0-9]{32}\.apps\.googleusercontent\.com", "Google OAuth client ID"),
    "twilio_sid": Kind(None, r"AC[a-f0-9]{32}", "Twilio Account SID: AC + 32 hex"),
    "image_digest": Kind(None, r"sha256:[a-f0-9]{64}", "container image digest"),
    "ssh_public_key": Kind(None, source="Ed25519 authorized_keys line", build=ssh_public_key),
}


def generate(kind: Kind, seed: str, spec: dict) -> str:
    gen = rstr.Rstr(random.Random(seed))
    return kind.build(gen, seed, spec) if kind.build else gen.xeger(kind.regex)


def transform(value: str, name: str, arg: str | None) -> tuple[str, str | None]:
    """metric-detection transforms (base64, url, json, basic) and the container encodings metric-task tasks need. Returns
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
            kind = KINDS[spec["kind"]]
            value, kind_type = generate(kind, f"{SEED_PREFIX}:{task_id}:{name}", spec), kind.type
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
            value = generate(DECOY_KINDS[spec["kind"]], f"{SEED_PREFIX}:{task_id}:decoy:{name}", spec)
        out[name] = value
    return out


# ---- checking against gitleaks ------------------------------------------------------------------------------

SAMPLE_SPECS = {"jwt_claims": {"claims": {"sub": "1042", "iat": 1790000000, "exp": 1790003600}}}


def gitleaks_check(samples: int = 5) -> tuple[str, list[str]]:
    """Runs the installed gitleaks on `samples` values of every kind that names a gitleaks rule and reports each
    value that rule did not find. A one-line value is written the way gitleaks' own tests write theirs
    (<name>_api_token = "<value>"), a PEM block as it is. Returns (gitleaks version, problems); the version is ""
    when gitleaks is not installed."""
    exe = shutil.which("gitleaks")
    if not exe:
        return "", []
    version = subprocess.run([exe, "version"], capture_output=True, text=True).stdout.strip()
    problems = []
    for name, kind in KINDS.items():  # one run per kind: gitleaks reads stdin in fragments and can miss a value
        if not kind.rule:              # that straddles two (seen with ~40 KB of input)
            continue
        text, starts = "", []
        for i in range(samples):
            value = generate(kind, f"gitleaks-check:{name}:{i}", SAMPLE_SPECS.get(name, {}))
            starts.append(text.count("\n") + 1)
            text += (value if "\n" in value else f'{name}_api_token = "{value}"') + "\n\n"
        proc = subprocess.run([exe, "stdin", "--no-banner", "--report-format", "json", "--report-path", "-",
                               "--exit-code", "0"], input=text, capture_output=True, text=True)
        try:
            found = {f["StartLine"] for f in json.loads(proc.stdout or "[]") if f["RuleID"] == kind.rule}
        except json.JSONDecodeError:
            return version, [f"gitleaks output is not JSON: {(proc.stderr or proc.stdout)[:200]}"]
        problems += [f"{name}: sample {i} not found by gitleaks rule {kind.rule}"
                     for i, line in enumerate(starts) if line not in found]
    return version, problems


def main():
    width = max(map(len, KINDS | DECOY_KINDS))
    for title, kinds in (("secrets", KINDS), ("decoys", DECOY_KINDS)):
        print(f"{title}:")
        for name, kind in kinds.items():
            print(f"  {name:{width}s} {kind.type or '-':11s} {kind.rule or '-':24s} {kind.source}")
    version, problems = gitleaks_check()
    if not version:
        print("\ngitleaks not installed: the values were not checked against its rules")
        return
    n = sum(bool(k.rule) for k in KINDS.values())
    print(f"\ngitleaks {version}: {n} kinds x 5 samples, {len(problems)} not found by their rule")
    for problem in problems:
        print("  " + problem)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
