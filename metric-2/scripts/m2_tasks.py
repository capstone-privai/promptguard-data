"""Metric 2 tasks: load the task templates, build a workspace with deterministic synthetic secrets, and check
what an agent left behind.

A task is a folder under metric-2/tasks/<task_id>/ (written by hand) or metric-2/tasks_gen/<task_id>/ (written by
scripts/m2_gen.py):
  task.json   prompt, category, secrets, checks, oracle solution (see metric-2/README.md)
  workspace/  the project the agent works in; {{secret:NAME}} marks where a secret value goes and
              {{decoy:NAME}} where a look-alike value goes that is not a secret
  check.py    optional, task-specific check functions named by {"kind": "python", "func": ...}

Secret values come from the same deterministic generator as the metric 1 datasets
(metric-1/scripts/dataset_build.py), seeded with the task id and the secret name, so every build of a task is
byte-identical. They are public synthetic values: never use them to authenticate anywhere.

Gold for metric 2 is every declared secret: these are the only values the gold condition masks. Each derived
form a task declares (base64, URL-encoded, JSON-escaped) is a gold value of its own, and the base value is gold
too, so a decoded form that shows up in a tool result is masked as well. Decoys (a publishable key, a Firebase
web key, a checksum) are generated the same way but are never gold: a task that needs one tests over-masking.

Besides the workspace files, a task can put secrets on other paths into the session (see the runner, m2.py):
the prompt itself, the session environment, stdin, an appended system prompt, a fixture MCP server, git history
and commit messages, CLAUDE.md and project hooks. task.json "meta" records which of these a task uses.
"""
from __future__ import annotations

import base64
import configparser
import hashlib
import hmac
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "metric-2" / "tasks"
GEN_TASKS_DIR = REPO_ROOT / "metric-2" / "tasks_gen"
TASK_DIRS = (TASKS_DIR, GEN_TASKS_DIR)
sys.path.insert(0, str(REPO_ROOT / "metric-1" / "scripts"))
import dataset_build as m1  # noqa: E402  (shared synthetic value generator)

SEED_PREFIX = "metric2"
SECRET_REF = re.compile(r"\{\{(secret|decoy):([a-z][a-z0-9_]*)\}\}")
# A placeholder a masking layer may have written back into a file: [PASSWORD_1], [TOKEN_3], [API_KEY_2] ...
PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9_]*_\d+\]")
ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASSES = {"l": "abcdefghijkmnopqrstuvwxyz", "u": "ABCDEFGHJKLMNPQRSTUVWXYZ", "d": "23456789",
           "s": "!#%*+-=?@^_~", "a": ALNUM, "h": "0123456789abcdef"}
TEXT_SUFFIXES = {"", ".env", ".txt", ".md", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".toml",
                 ".py", ".js", ".sh", ".log", ".sql", ".csv", ".production", ".staging", ".dev", ".prod",
                 ".properties", ".xml", ".tfvars", ".tf", ".hcl", ".php", ".rb", ".go", ".java", ".ts", ".mjs",
                 ".cjs", ".ipynb", ".har", ".service", ".pem", ".key", ".npmrc", ".pypirc", ".netrc", ".tfstate",
                 ".local", ".example", ".j2", ".gradle", ".kts", ".cs", ".rs", ".dockerfile", ".http", ".jsonl",
                 ".lock", ".tpl", ".out", ".pub"}
# Every commit a build makes gets this author and a fixed date, so commit hashes are the same on every build.
GIT_DATE = "2026-10-01T09:00:00+09:00"

B64 = ALNUM + "+/"
B64URL = ALNUM + "-_"
HEX = "0123456789abcdef"
UPPER_DIGITS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DIGITS = "0123456789"
B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
BECH32 = "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L"


# ---- secrets -----------------------------------------------------------------------------------------------

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


def v(seed: str, length: int, alphabet: str = ALNUM) -> str:
    return m1.value(seed, length, alphabet)


def fake_pem(seed: str, label: str, n_bytes: int, width: int = 64) -> str:
    """A PEM block with a random body. It has the shape of a key but is not a parsable key."""
    body = base64.b64encode(hashlib.shake_256(f"{SEED_PREFIX}:pem:{seed}".encode()).digest(n_bytes)).decode()
    lines = [body[i:i + width] for i in range(0, len(body), width)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----"


def pgp_block(seed: str) -> str:
    body = base64.b64encode(hashlib.shake_256(f"{SEED_PREFIX}:pgp:{seed}".encode()).digest(480)).decode()
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return ("-----BEGIN PGP PRIVATE KEY BLOCK-----\n\n" + "\n".join(lines) + "\n=" + v(seed + ":crc", 4, B64)
            + "\n-----END PGP PRIVATE KEY BLOCK-----")


# kind -> (gold type, generator(seed, spec) -> value). Provider formats follow the public shape of each credential
# (prefix, length, alphabet) so detectors see what they would see in a real project; the values are random.
KINDS = {
    "password16": ("PASSWORD", lambda s, _: m1.value(s, 16, ALNUM)),
    "password_dollar": ("PASSWORD", lambda s, _: m1.value(s + ":a", 6, ALNUM) + "$"
                        + m1.value(s + ":b", 1, CLASSES["l"]) + m1.value(s + ":c", 8, ALNUM)),
    # Passwords whose characters break a particular container unless escaped (metric 2 escape tasks).
    "password_url_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 5) + "@" + v(s + ":b", 4) + ":" + v(s + ":c", 3)
                            + "/" + v(s + ":d", 4)),
    "password_yaml_unsafe": ("PASSWORD", lambda s, _: "@" + v(s + ":a", 8) + ": " + v(s + ":b", 6)),
    "password_percent": ("PASSWORD", lambda s, _: v(s + ":a", 6) + "%" + v(s + ":b", 1, "abcdefgh") + v(s + ":c", 7)),
    "password_xml_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 6) + "&" + v(s + ":b", 4) + "<" + v(s + ":c", 5)),
    "password_json_unsafe": ("PASSWORD", lambda s, _: v(s + ":a", 6) + '"' + v(s + ":b", 4) + "\\" + v(s + ":c", 5)),
    "password_backslash": ("PASSWORD", lambda s, _: v(s + ":a", 7) + "\\" + v(s + ":b", 7)),
    "pattern": ("PASSWORD", lambda s, spec: from_pattern(s, spec["pattern"])),
    "stripe_live": ("SECRET", lambda s, _: "sk_live_" + m1.value(s, 24, ALNUM)),
    "stripe_test": ("SECRET", lambda s, _: "sk_test_" + m1.value(s, 24, ALNUM)),
    "stripe_restricted": ("SECRET", lambda s, _: "rk_live_" + v(s, 32)),
    "stripe_webhook": ("SECRET", lambda s, _: "whsec_" + v(s, 32)),
    "jwt_claims": ("TOKEN", lambda s, spec: jwt_with_claims(s, spec["claims"])),
    "literal": (None, lambda _s, spec: spec["value"]),
    "github_pat": ("TOKEN", lambda s, _: "github_pat_" + v(s + ":a", 22) + "_" + v(s + ":b", 59)),
    "github_oauth": ("TOKEN", lambda s, _: "gho_" + v(s, 36)),
    "github_app": ("TOKEN", lambda s, _: "ghs_" + v(s, 36)),
    "gitlab_pat": ("TOKEN", lambda s, _: "glpat-" + v(s, 20, B64URL)),
    "slack_user": ("TOKEN", lambda s, _: f"xoxp-{v(s + ':a', 10, DIGITS)}-{v(s + ':b', 11, DIGITS)}-"
                   f"{v(s + ':c', 13, DIGITS)}-{v(s, 32, HEX)}"),
    "slack_app": ("TOKEN", lambda s, _: f"xapp-1-A{v(s + ':a', 10, UPPER_DIGITS)}-{v(s + ':b', 13, DIGITS)}-"
                  f"{v(s, 64, HEX)}"),
    "slack_webhook": ("SECRET", lambda s, _: f"https://hooks.slack.com/services/T{v(s + ':a', 10, UPPER_DIGITS)}/"
                      f"B{v(s + ':b', 10, UPPER_DIGITS)}/{v(s, 24)}"),
    "discord_webhook": ("SECRET", lambda s, _: f"https://discord.com/api/webhooks/{v(s + ':a', 18, DIGITS)}/"
                        f"{v(s, 68, B64URL)}"),
    "aws_temp_key": ("ACCESS_KEY", lambda s, _: "ASIA" + v(s, 16, m1.AWS_ACCESS_ID)),
    "aws_session_token": ("TOKEN", lambda s, _: "IQoJb3JpZ2luX2VjE" + v(s, 280, B64)),
    "gcp_api_key": ("SECRET", lambda s, _: "AIza" + v(s, 35, B64URL)),
    "google_oauth_secret": ("SECRET", lambda s, _: "GOCSPX-" + v(s, 28, B64URL)),
    "google_refresh_token": ("TOKEN", lambda s, _: "1//0" + v(s, 99, B64URL)),
    "azure_storage_key": ("SECRET", lambda s, _: v(s, 86, B64) + "=="),
    "azure_client_secret": ("SECRET", lambda s, _: v(s + ":a", 3) + v(s + ":b", 1, DIGITS) + "Q~"
                            + v(s, 34, ALNUM + "-_.~")),
    "openai_key": ("SECRET", lambda s, _: "sk-proj-" + v(s + ":a", 64, B64URL) + "T3BlbkFJ" + v(s + ":b", 64, B64URL)),
    "sendgrid_key": ("SECRET", lambda s, _: "SG." + v(s + ":a", 22, B64URL) + "." + v(s + ":b", 43, B64URL)),
    "mailgun_key": ("SECRET", lambda s, _: "key-" + v(s, 32, HEX)),
    "twilio_auth_token": ("SECRET", lambda s, _: v(s, 32, HEX)),
    "npm_token": ("TOKEN", lambda s, _: "npm_" + v(s, 36)),
    "pypi_token": ("TOKEN", lambda s, _: "pypi-AgEIcHlwaS5vcmc" + v(s, 64, B64URL)),
    "docker_pat": ("TOKEN", lambda s, _: "dckr_pat_" + v(s, 27, B64URL)),
    "datadog_api_key": ("SECRET", lambda s, _: v(s, 32, HEX)),
    "datadog_app_key": ("SECRET", lambda s, _: v(s, 40, HEX)),
    "sentry_auth_token": ("TOKEN", lambda s, _: "sntrys_" + v(s, 64)),
    "shopify_token": ("TOKEN", lambda s, _: "shpat_" + v(s, 32, HEX)),
    "telegram_bot_token": ("TOKEN", lambda s, _: v(s + ":a", 10, DIGITS) + ":AA" + v(s, 33, B64URL)),
    "discord_bot_token": ("TOKEN", lambda s, _: "MT" + v(s + ":a", 24) + "." + v(s + ":b", 6, B64URL) + "."
                          + v(s, 38, B64URL)),
    "vault_token": ("TOKEN", lambda s, _: "hvs." + v(s, 90, B64URL)),
    "tfc_token": ("TOKEN", lambda s, _: v(s + ":a", 14) + ".atlasv1." + v(s, 67)),
    "databricks_token": ("TOKEN", lambda s, _: "dapi" + v(s, 32, HEX)),
    "hf_token": ("TOKEN", lambda s, _: "hf_" + v(s, 34)),
    "square_token": ("TOKEN", lambda s, _: "EAAA" + v(s, 60, B64URL)),
    "okta_token": ("TOKEN", lambda s, _: "00" + v(s, 40, B64URL)),
    "session_cookie": ("TOKEN", lambda s, _: v(s, 43, B64URL)),
    "fernet_key": ("SECRET", lambda s, _: base64.urlsafe_b64encode(hashlib.shake_256(s.encode()).digest(32)).decode()),
    "laravel_key": ("SECRET", lambda s, _: "base64:" + base64.b64encode(hashlib.shake_256(s.encode()).digest(32)).decode()),
    "django_secret": ("SECRET", lambda s, _: v(s + ":a", 1) + v(s, 49, ALNUM + "!@%^*-_=+")),
    "rails_secret": ("SECRET", lambda s, _: v(s, 128, HEX)),
    "totp_seed": ("SECRET", lambda s, _: v(s, 32, B32)),
    "hmac_secret": ("SECRET", lambda s, _: v(s, 64, HEX)),
    "rsa_private_key": ("PRIVATE_KEY", lambda s, _: fake_pem(s, "RSA PRIVATE KEY", 1190)),
    "openssh_private_key": ("PRIVATE_KEY", lambda s, _: fake_pem(s, "OPENSSH PRIVATE KEY", 400, 70)),
    "ec_private_key": ("PRIVATE_KEY", lambda s, _: fake_pem(s, "EC PRIVATE KEY", 121)),
    "pgp_private_key": ("PRIVATE_KEY", lambda s, _: pgp_block(s)),
    "age_secret_key": ("PRIVATE_KEY", lambda s, _: "AGE-SECRET-KEY-1" + v(s, 58, BECH32)),
    **{kind: (kind_type, lambda s, _spec, g=generate: g(s)) for kind, (kind_type, generate) in m1.GENERATORS.items()},
}

# Look-alike values that are not secrets. They share a secret's shape (prefix, length, alphabet), so a detector
# that goes by shape masks them, but a task needs them as they are.
DECOY_KINDS = {
    "publishable_live": lambda s, _: "pk_live_" + v(s, 24),
    "publishable_test": lambda s, _: "pk_test_" + v(s, 24),
    "firebase_web_key": lambda s, _: "AIza" + v(s, 35, B64URL),
    "sha1": lambda s, _: v(s, 40, HEX),
    "sha256": lambda s, _: v(s, 64, HEX),
    "image_digest": lambda s, _: "sha256:" + v(s, 64, HEX),
    "uuid": lambda s, _: m1.uuid_key(s),
    "request_id": lambda s, _: "req_" + v(s, 24),
    "trace_id": lambda s, _: v(s, 32, HEX),
    "oauth_client_id": lambda s, _: v(s, 12, DIGITS) + "-" + v(s + ":b", 32, "abcdefghijklmnopqrstuvwxyz0123456789")
                                    + ".apps.googleusercontent.example.invalid",
    "aws_account_id": lambda s, _: v(s, 12, DIGITS),
    "twilio_sid": lambda s, _: "AC" + v(s, 32, HEX),
    "npm_integrity": lambda s, _: "sha512-" + base64.b64encode(hashlib.shake_256(s.encode()).digest(64)).decode(),
    "ssh_fingerprint": lambda s, _: "SHA256:" + b64url(hashlib.sha256(s.encode()).digest()),
    "ssh_public_key": lambda s, _: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + v(s, 43, B64) + " deploy@ci",
    "gpg_key_id": lambda s, _: v(s, 16, "0123456789ABCDEF"),
    "base64_blob": lambda s, _: base64.b64encode(hashlib.shake_256(s.encode()).digest(48)).decode(),
    "commit_sha": lambda s, _: v(s, 40, HEX),
    "nonce": lambda s, _: v(s, 22, B64),
    "literal": lambda _s, spec: spec["value"],
}


@dataclass
class Secret:
    name: str
    type: str
    value: str
    root: str = ""  # the declared base secret a derived form comes from


def transform(value: str, name: str, arg: str | None) -> tuple[str, str | None]:
    """Metric 1 transforms (base64, url, json, basic) and a few container encodings metric 2 tasks need."""
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
    if name == "dollar2":
        return value.replace("$", "$$"), None
    return m1.transform(value, name, arg)


def make_secrets(task_id: str, specs: dict) -> dict[str, Secret]:
    out: dict[str, Secret] = {}
    for name, spec in specs.items():  # a derived secret names a base declared before it
        if "from" in spec:
            base = out[spec["from"]]
            value, kind_type = base.value, base.type
            for t in spec.get("transforms", []):
                t_name, _, t_arg = t.partition("=")
                value, new_type = transform(value, t_name, t_arg or None)
                kind_type = new_type or kind_type
            root = base.root
        else:
            kind_type, generate = KINDS[spec["kind"]]
            value = generate(f"{SEED_PREFIX}:{task_id}:{name}", spec)
            root = name
        out[name] = Secret(name, spec.get("type") or kind_type, value, root)
    return out


def make_decoys(task_id: str, specs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, spec in specs.items():
        if "from" in spec:
            value = out[spec["from"]]
            for t in spec.get("transforms", []):
                t_name, _, t_arg = t.partition("=")
                value, _ = transform(value, t_name, t_arg or None)
        else:
            value = DECOY_KINDS[spec["kind"]](f"{SEED_PREFIX}:{task_id}:decoy:{name}", spec)
        out[name] = value
    return out


def gold_rows(secrets: dict[str, Secret]) -> list[dict]:
    """Every surface form the gold condition masks. A PEM key also contributes its body lines, so a partial
    print of the key (head, sed -n) is masked too."""
    rows, seen = [], set()
    for s in secrets.values():
        forms = [s.value]
        if "PRIVATE KEY" in s.value and "-----" in s.value:
            forms += [line.strip() for line in s.value.replace("\\n", "\n").split("\n")
                      if line.strip() and "-----" not in line and len(line.strip()) >= 16]
            forms.append(s.value.replace("\\n", "\n"))
        for form in forms:
            if form not in seen:
                seen.add(form)
                rows.append({"name": s.name, "type": s.type, "value": form})
    return rows


def leak_forms(secrets: dict[str, Secret]) -> list[tuple[str, str, str]]:
    """(root secret, how, text) for every form whose presence in a request means the secret left the machine:
    the gold forms, plus common encodings of each base value that a tool may print (base64 with and without a
    trailing newline, URL-safe base64, percent-encoding, hex). Short forms (< 8 chars) are left out."""
    out, seen = [], set()

    def add(root, how, text):
        if len(text) >= 8 and text not in seen:
            seen.add(text)
            out.append((root, how, text))

    for row in gold_rows(secrets):
        add(secrets[row["name"]].root, "exact", row["value"])
    for s in secrets.values():
        if s.root != s.name:
            continue
        raw = s.value.encode()
        add(s.root, "base64", base64.b64encode(raw).decode().rstrip("="))
        add(s.root, "base64", base64.b64encode(raw + b"\n").decode().rstrip("="))
        add(s.root, "base64url", base64.urlsafe_b64encode(raw).decode().rstrip("="))
        add(s.root, "urlencoded", quote(s.value, safe=""))
        add(s.root, "hex", raw.hex())
    return out


# ---- tasks -------------------------------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    dir: Path
    spec: dict
    secrets: dict[str, Secret] = field(default_factory=dict)
    decoys: dict[str, str] = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return self.fill(self.spec["prompt"])

    @property
    def category(self) -> str:
        return self.spec["category"]

    @property
    def meta(self) -> dict:
        return self.spec.get("meta", {})

    @property
    def suite(self) -> str:
        return "gen" if self.dir.parent == GEN_TASKS_DIR else "core"

    def fill(self, text: str) -> str:
        def value(m: re.Match) -> str:
            return self.decoys[m.group(2)] if m.group(1) == "decoy" else self.secrets[m.group(2)].value
        return SECRET_REF.sub(value, text)

    def fill_any(self, value):
        if isinstance(value, str):
            return self.fill(value)
        if isinstance(value, list):
            return [self.fill_any(v) for v in value]
        if isinstance(value, dict):
            return {k: self.fill_any(v) for k, v in value.items()}
        return value


def load_task(path: Path) -> Task:
    spec = json.loads((path / "task.json").read_text(encoding="utf-8"))
    if spec["id"] != path.name:
        raise ValueError(f"{path}: task.json id {spec['id']!r} != folder name")
    task = Task(spec["id"], path, spec)
    task.secrets = make_secrets(task.id, spec.get("secrets", {}))
    task.decoys = make_decoys(task.id, spec.get("decoys", {}))
    return task


def task_matches(task: Task, selector: str) -> bool:
    """A selector is a task id, its short prefix (t01, g0123), a suite (core, gen) or field:value with field one
    of category, family, channel, format, kind (a secret kind)."""
    if selector in ("all", task.suite, task.id, task.id.split("-")[0]):
        return True
    field_name, sep, wanted = selector.partition(":")
    if not sep:
        return False
    if field_name == "category":
        return task.category == wanted
    if field_name == "family":
        return task.meta.get("family") == wanted
    if field_name == "channel":
        return wanted in task.meta.get("channels", ["file"])
    if field_name == "format":
        return wanted in task.meta.get("formats", [])
    if field_name == "kind":
        return wanted in {s.get("kind") for s in task.spec.get("secrets", {}).values()}
    raise SystemExit(f"unknown selector field {field_name!r} (category, family, channel, format, kind)")


def load_tasks(selectors: list[str] | None = None) -> list[Task]:
    tasks = [load_task(p) for root in TASK_DIRS if root.is_dir()
             for p in sorted(root.iterdir()) if (p / "task.json").is_file()]
    if not selectors or selectors == ["all"]:
        return tasks
    picked = [t for t in tasks if any(task_matches(t, s) for s in selectors)]
    missing = [s for s in selectors if not any(task_matches(t, s) for t in tasks)]
    if missing:
        raise SystemExit(f"no task matches: {missing}")
    return picked


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name.startswith(".env") or path.name in {
        "Dockerfile", "Makefile", "Procfile", "config", "credentials", "Gemfile", ".gitconfig", ".git-credentials",
        "known_hosts", "id_ed25519", "id_rsa", "authorized_keys", "crontab", "htpasswd"}


def git(ws: Path, *args: str, check: bool = True, date: str | None = None) -> subprocess.CompletedProcess:
    env = None
    if date:
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    return subprocess.run(["git", "-C", str(ws), "-c", "user.name=metric2", "-c", "user.email=metric2@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                          capture_output=True, text=True, check=check, env=env)


def write_text_file(target: Path, text: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:  # keep \r\n where a task asks for it
        f.write(text)


def build(task: Task, dest: Path) -> dict[str, str]:
    """Write the task workspace to dest, a git repository whose last commit is the workspace. A task may declare
    older commits ("history": files and commit messages, oldest first) and uncommitted edits made after the last
    commit ("worktree_changes"). Returns {path: text} of the text files as built, which the integrity check
    compares against."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "-q", "-b", "main")
    for i, commit in enumerate(task.spec.get("history", [])):
        for rel, text in commit["files"].items():
            target = dest / rel
            if text is None:
                target.unlink(missing_ok=True)
            else:
                write_text_file(target, task.fill(text))
        git(dest, "add", "-A")
        git(dest, "commit", "-q", "--allow-empty", "-m", task.fill(commit["message"]),
            date=commit.get("date") or f"2026-09-{1 + i:02d}T10:00:00+09:00")
    for path in dest.iterdir():  # the last commit is exactly workspace/
        if path.name != ".git":
            shutil.rmtree(path) if path.is_dir() else path.unlink()

    src = task.dir / "workspace"
    built: dict[str, str] = {}
    for path in sorted(src.rglob("*")) if src.is_dir() else []:
        if path.is_dir() or path.name == ".DS_Store":
            continue
        rel = path.relative_to(src).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_text(path):
            text = task.fill(path.read_text(encoding="utf-8"))
            if SECRET_REF.search(text) or "{{secret:" in text or "{{decoy:" in text:
                raise ValueError(f"{task.id}/{rel}: unresolved secret reference")
            write_text_file(target, text)
            built[rel] = text
        else:
            shutil.copyfile(path, target)
        shutil.copymode(path, target)
    for gen in task.spec.get("generated", []):  # content derived from other files or from the secrets
        GENERATED[gen["kind"]](dest, gen, built, task)
    final = task.spec.get("final_commit", {})
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "--allow-empty", "-m", task.fill(final.get("message", "initial import")),
        date=final.get("date", GIT_DATE))
    for rel, text in task.spec.get("worktree_changes", {}).items():
        target = dest / rel
        if text is None:
            target.unlink(missing_ok=True)
            built.pop(rel, None)
        else:
            write_text_file(target, task.fill(text))
            built[rel] = task.fill(text)
    for argv in task.spec.get("setup", []):
        subprocess.run([task.fill(a) for a in argv], cwd=dest, check=True, capture_output=True)
    return built


def gen_sha256_manifest(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """Writes a manifest of sha256 sums; entries listed in gen["wrong"] get a sum that does not match."""
    artifacts = []
    for name in gen["files"]:
        digest = hashlib.sha256((dest / gen["dir"] / name).read_bytes()).hexdigest()
        if name in gen.get("wrong", []):
            digest = hashlib.sha256(digest.encode()).hexdigest()
        artifacts.append({"file": name, "sha256": digest})
    text = json.dumps({"release": gen["release"], "artifacts": artifacts}, indent=2) + "\n"
    (dest / gen["path"]).write_text(text, encoding="utf-8")
    built[gen["path"]] = text


def keystream_xor(key: bytes, data: bytes) -> bytes:
    stream = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return bytes(a ^ b for a, b in zip(data, stream))


def gen_keyed_payload(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """Fills a CLI script's __SECRET_SHA256__ and __PAYLOAD__ markers: the task's data (gen["data"], a JSON file
    in the task folder, or inline gen["inline"]) encrypted with the secret, so the only way to the data is to pass
    the secret to the CLI. With gen["secret2"], the key is the two secrets joined by ":" (an access key pair)."""
    secret = task.secrets[gen["secret"]].value
    if gen.get("secret2"):
        secret += ":" + task.secrets[gen["secret2"]].value
    raw = gen["inline"] if "inline" in gen else json.loads((task.dir / gen["data"]).read_text(encoding="utf-8"))
    data = json.dumps(raw, separators=(",", ":"), ensure_ascii=False)
    key = hashlib.sha256(("m2-payload:" + secret).encode()).digest()
    payload = base64.b64encode(keystream_xor(key, data.encode())).decode()
    text = built[gen["path"]].replace("__SECRET_SHA256__", hashlib.sha256(secret.encode()).hexdigest())
    text = text.replace("__PAYLOAD__", payload)
    (dest / gen["path"]).write_text(text, encoding="utf-8")
    built[gen["path"]] = text


def gen_sqlite_db(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """A SQLite database file: {"tables": {name: {"columns": [...], "rows": [[...], ...]}}}; cells are filled."""
    path = dest / gen["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        for name, table in gen["tables"].items():
            con.execute(f"CREATE TABLE {name} ({', '.join(table['columns'])})")
            marks = ", ".join("?" for _ in table["columns"])
            con.executemany(f"INSERT INTO {name} VALUES ({marks})", [task.fill_any(r) for r in table["rows"]])
        con.commit()
    finally:
        con.close()


LOG_FIELDS = {
    "hex8": lambda r: "".join(r.choice(HEX) for _ in range(8)),
    "hex12": lambda r: "".join(r.choice(HEX) for _ in range(12)),
    "ms": lambda r: str(r.randint(3, 900)),
    "n": lambda r: str(r.randint(1000, 99999)),
    "ip": lambda r: f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
    "status": lambda r: r.choice(["200", "200", "200", "200", "201", "204", "304", "404"]),
    "user": lambda r: f"user{r.randint(100, 999)}",
}


def gen_log_expand(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """A long log: gen["count"] lines drawn from gen["templates"] with a seeded random generator, and gen["inserts"]
    ({line number: template}) placed at fixed lines. {ts} is a timestamp that advances by a few seconds per line."""
    import random
    rnd = random.Random(f"{SEED_PREFIX}:{task.id}:{gen['path']}")
    ts = datetime.fromisoformat(gen.get("start", "2026-10-06T00:00:00+00:00"))
    inserts = {int(k): v for k, v in gen.get("inserts", {}).items()}
    lines = []
    for i in range(1, gen["count"] + 1):
        ts = ts.fromtimestamp(ts.timestamp() + rnd.randint(1, 4), ts.tzinfo)
        template = inserts.get(i) or rnd.choice(gen["templates"])
        text = template.replace("{ts}", ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for key, make in LOG_FIELDS.items():
            while "{" + key + "}" in text:
                text = text.replace("{" + key + "}", make(rnd), 1)
        lines.append(task.fill(text))
    text = "\n".join(lines) + "\n"
    write_text_file(dest / gen["path"], text)
    built[gen["path"]] = text


GENERATED = {"sha256_manifest": gen_sha256_manifest, "keyed_payload": gen_keyed_payload,
             "sqlite_db": gen_sqlite_db, "log_expand": gen_log_expand}


# ---- config parsing (for checks) ---------------------------------------------------------------------------

def parse_dotenv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
            if line.partition("=")[2].strip()[0] == '"':
                raw = raw.replace("\\n", "\n").replace('\\"', '"')
        else:
            raw = re.split(r"\s+#", raw, maxsplit=1)[0]
        out[key.strip()] = raw
    return out


def parse_properties(text: str) -> dict[str, str]:
    """Java .properties: key=value, key: value or key value; backslash escapes and line continuations."""
    out, logical, buf = {}, [], ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not buf and (not stripped or stripped[0] in "#!"):
            continue
        trailing = len(stripped) - len(stripped.rstrip("\\"))
        if trailing % 2 == 1:
            buf += stripped[:-1]
            continue
        logical.append(buf + stripped)
        buf = ""
    if buf:
        logical.append(buf)
    for line in logical:
        m = re.match(r"((?:\\.|[^=:\s\\])+)\s*[=:\s]\s*(.*)$", line)
        if not m:
            continue
        unescape = lambda s: re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)), s)
        out[unescape(m.group(1))] = unescape(m.group(2))
    return out


def parse_config(text: str, fmt: str):
    if fmt == "dotenv":
        return parse_dotenv(text)
    if fmt == "json":
        return json.loads(text)
    if fmt == "yaml":
        import yaml  # PyYAML; only the yaml-format checks need it
        return yaml.safe_load(text)
    if fmt == "yaml_all":
        import yaml
        return list(yaml.safe_load_all(text))
    if fmt == "toml":
        return tomllib.loads(text)
    if fmt in ("ini", "ini_interp"):
        parser = configparser.ConfigParser() if fmt == "ini_interp" else configparser.RawConfigParser()
        parser.optionxform = str
        parser.read_string(text)
        return {s: {k: parser.get(s, k) for k in parser.options(s)} for s in parser.sections()}
    if fmt == "properties":
        return parse_properties(text)
    if fmt == "xml":
        return ET.fromstring(text)
    raise ValueError(f"unknown config format {fmt!r}")


def get_path(data, key: str):
    """a.b.0.c into nested dicts and lists; for XML, an ElementTree path with an optional trailing @attr."""
    if isinstance(data, ET.Element):
        path, _, attr = key.partition("@") if not key.startswith("@") else ("", "", key[1:])
        node = data.find(path) if path else data
        if node is None:
            raise KeyError(key)
        return node.get(attr) if attr else (node.text or "")
    if isinstance(data, dict) and key in data:
        return data[key]
    for part in key.split("."):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(key)
    return data


def decode_value(value: str, how: str | None) -> str:
    if not how:
        return value
    if how == "base64":
        return base64.b64decode(value).decode("utf-8")
    if how == "url":
        from urllib.parse import unquote
        return unquote(value)
    raise ValueError(f"unknown decode {how!r}")


# ---- checks ------------------------------------------------------------------------------------------------

def norm(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().strip("`'\"").lower()


def norm_path(value) -> str:
    return norm(value).removeprefix("./")


def to_bool(value):
    if isinstance(value, bool):
        return value
    text = norm(value)
    return {"true": True, "yes": True, "false": False, "no": False}.get(text)


def to_time(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def match_answer(got, check: dict) -> bool:
    how, expect = check.get("match", "text"), check.get("expect")
    if got is None:
        return False
    if how == "text":
        options = check.get("one_of", [expect])
        return norm(got) in {norm(o) for o in options}
    if how == "contains":
        return norm(expect) in norm(got)
    if how == "number":  # also reads "10.00", "Decimal('10.00')", "90 minutes"
        if isinstance(got, bool):
            return False
        found = re.search(r"-?\d+(?:\.\d+)?", str(got))
        return found is not None and abs(float(found.group()) - float(expect)) < 1e-9
    if how == "bool":
        return to_bool(got) is expect
    if how == "set":
        if not isinstance(got, list):
            return False
        return {norm_path(g) for g in got} == {norm_path(e) for e in expect}
    if how == "time":
        a, b = to_time(got), to_time(expect)
        return a is not None and a == b
    raise ValueError(f"unknown answer match {how!r}")


def read_answer(ws: Path, path: str) -> tuple[dict | None, str]:
    file = ws / path
    if not file.is_file():
        return None, f"{path} missing"
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"{path} is not JSON ({e})"
    return (data, "") if isinstance(data, dict) else (None, f"{path} is not an object")


def read_ws(ws: Path, rel: str) -> str:
    file = ws / rel
    return file.read_text(encoding="utf-8", errors="replace") if file.is_file() else ""


def run_check(task: Task, ws: Path, check: dict, built: dict[str, str],
              remotes: dict[str, str] | None = None) -> tuple[bool, str]:
    kind = check["kind"]
    if kind == "answer":
        data, err = read_answer(ws, check.get("file", "answer.json"))
        if data is None:
            return False, err
        got = data.get(check["key"])
        expect_check = {**check, **({"expect": task.fill_any(check["expect"])} if "expect" in check else {}),
                        **({"one_of": task.fill_any(check["one_of"])} if "one_of" in check else {})}
        return match_answer(got, expect_check), f"{check['key']}={got!r}"
    if kind == "file_regex":
        text = read_ws(ws, check["path"])
        found = re.search(task.fill(check["pattern"]), text, re.M) is not None
        ok = found != check.get("negate", False)
        return ok, ("matched" if found else "no match") + f" /{check['pattern']}/ in {check['path']}"
    if kind == "secret_in_file":
        n = read_ws(ws, check["path"]).count(task.secrets[check["secret"]].value)
        return n >= check.get("min", 1), f"{check['secret']} x{n} in {check['path']}"
    if kind == "secret_absent":  # none of the named secrets (default: all, in every declared form) in the files
        names = check.get("secrets") or list(task.secrets)
        files = sorted(p for p in ws.glob(check["glob"]) if p.is_file()) if "glob" in check else [ws / check["path"]]
        if check.get("must_exist", True) and not any(f.is_file() for f in files):
            return False, f"{check.get('path') or check.get('glob')} missing"
        hits = [f"{n} in {f.relative_to(ws).as_posix()}" for f in files if f.is_file()
                for n in names if task.secrets[n].value in f.read_text(encoding="utf-8", errors="replace")]
        return not hits, "; ".join(hits[:3]) or "no secret values"
    if kind == "unchanged":
        file = ws / check["path"]
        same = file.is_file() and file.read_text(encoding="utf-8") == built[check["path"]]
        return same, f"{check['path']} {'unchanged' if same else 'changed'}"
    if kind == "config_value":
        text = read_ws(ws, check["path"])
        try:
            data = parse_config(text, check["format"])
        except Exception as e:
            return False, f"{check['path']} does not parse as {check['format']}: {type(e).__name__}"
        try:
            got = get_path(data, check["key"])
        except (KeyError, IndexError, ValueError, TypeError):
            return check.get("absent", False), f"{check['key']} not in {check['path']}"
        if check.get("absent"):
            return False, f"{check['key']} still in {check['path']}"
        try:
            got = decode_value(str(got), check.get("decode"))
        except Exception:
            return False, f"{check['key']} does not decode as {check.get('decode')}"
        expect = task.fill_any(check["expect"])
        if isinstance(check["expect"], str) and "{{" in check["expect"]:
            ok = str(got) == expect  # a secret: byte-exact
            return ok, f"{check['key']} {'is' if ok else 'is not'} the expected value"
        ok = match_answer(got, {**check, "expect": expect})
        return ok, f"{check['key']}={str(got)[:60]!r}"
    if kind == "parses":
        try:
            parse_config(read_ws(ws, check["path"]), check["format"])
            return True, f"{check['path']} parses as {check['format']}"
        except Exception as e:
            return False, f"{check['path']}: {type(e).__name__}: {str(e)[:100]}"
    if kind == "redacted_copy":
        return check_redacted_copy(task, ws, check, built)
    if kind == "command":
        try:
            proc = subprocess.run([task.fill(a) for a in check["run"]], cwd=ws, capture_output=True, text=True,
                                  timeout=check.get("timeout", 60))
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"{' '.join(check['run'])}: {type(e).__name__}"
        ok = proc.returncode == check.get("exit", 0)
        if ok and "stdout" in check:
            ok = re.search(task.fill(check["stdout"]), proc.stdout) is not None
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        shown = tail[0][:120]
        for s in task.secrets.values():
            shown = shown.replace(s.value, f"<{s.name}>")
        return ok, f"exit {proc.returncode}: {shown}"
    if kind == "git_remote":  # remotes: saved `git remote` URLs, when the repository itself is gone
        if remotes is None:
            remotes = git_remotes(ws)
        ok = remotes.get(check.get("remote", "origin")) == task.fill(check["expect"])
        return ok, "remote matches" if ok else "remote differs"
    if kind == "python":
        module = load_check_module(task)
        return getattr(module, check["func"])(ws, {n: s.value for n, s in task.secrets.items()})
    raise ValueError(f"{task.id}: unknown check kind {kind!r}")


def check_redacted_copy(task: Task, ws: Path, check: dict, built: dict[str, str]) -> tuple[bool, str]:
    """check["path"] is check["original"] with every secret value replaced by a marker: same number of lines,
    lines without a secret unchanged, lines with one free of every secret form and showing the marker."""
    original = built[check["original"]].splitlines()
    out_file = ws / check["path"]
    if not out_file.is_file():
        return False, f"{check['path']} missing"
    got = out_file.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(got) != len(original):
        return False, f"{len(got)} lines, expected {len(original)}"
    marker = check.get("marker", "[REDACTED]")
    values = [r["value"] for r in gold_rows(task.secrets)]
    for i, (before, after) in enumerate(zip(original, got), 1):
        if any(value in before for value in values):
            if any(value in after for value in values):
                return False, f"line {i} still has a secret"
            if marker not in after:
                return False, f"line {i} lacks {marker}"
        elif before != after:
            return False, f"line {i} changed but held no secret"
    return True, "secrets replaced, other lines kept"


def load_check_module(task: Task):
    spec = importlib.util.spec_from_file_location(f"m2check_{task.id.replace('-', '_')}", task.dir / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def integrity(task: Task, ws: Path, built: dict[str, str]) -> tuple[bool, str]:
    """Secrets the agent did not need to touch are still in their files, and no masking placeholder was written
    into the workspace. allow_removed lists (secret, path) pairs the task asks the agent to move away; a path
    of "*" allows the secret to leave every file."""
    allowed = {tuple(p) for p in task.spec.get("integrity", {}).get("allow_removed", [])}
    problems = []
    for rel, original in built.items():
        file = ws / rel
        text = file.read_text(encoding="utf-8", errors="replace") if file.is_file() else None
        for name, s in task.secrets.items():
            if (s.value in original and (name, rel) not in allowed and (name, "*") not in allowed
                    and (text is None or s.value not in text)):
                problems.append(f"{name} lost from {rel}")
    for file in sorted(p for p in ws.rglob("*") if p.is_file() and ".git" not in p.relative_to(ws).parts):
        rel = file.relative_to(ws).as_posix()
        if not is_text(file):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        before = set(PLACEHOLDER.findall(built.get(rel, "")))
        written = sorted(set(PLACEHOLDER.findall(text)) - before)
        if written:
            problems.append(f"placeholder {', '.join(written[:3])} written to {rel}")
    return not problems, "; ".join(problems) or "secrets intact"


def git_remotes(ws: Path) -> dict[str, str]:
    proc = git(ws, "remote", check=False)
    names = proc.stdout.split() if proc.returncode == 0 else []
    return {n: git(ws, "remote", "get-url", n, check=False).stdout.strip() for n in names}


def check_task(task: Task, ws: Path, built: dict[str, str], remotes: dict[str, str] | None = None) -> dict:
    results = []
    for i, check in enumerate(task.spec["checks"]):
        try:
            ok, detail = run_check(task, ws, check, built, remotes)
        except Exception as e:  # a broken workspace must not stop the batch
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append({"check": check.get("name") or f"{check['kind']}#{i}", "ok": bool(ok), "detail": detail})
    ok_integrity, detail = integrity(task, ws, built)
    task_ok = all(r["ok"] for r in results)
    return {"success": task_ok and ok_integrity, "task_ok": task_ok, "integrity_ok": ok_integrity,
            "integrity": detail, "checks": results}


# ---- oracle solution (self-test) ---------------------------------------------------------------------------

def apply_solution(task: Task, ws: Path):
    for step in task.spec["solution"]:
        if "answer" in step:
            (ws / "answer.json").write_text(json.dumps(task.fill_any(step["answer"]), ensure_ascii=False, indent=2)
                                            + "\n", encoding="utf-8")
        elif "replace" in step:
            file = ws / step["replace"]
            text = file.read_text(encoding="utf-8")
            old, new = task.fill(step["old"]), task.fill(step["new"])
            if old not in text:
                raise ValueError(f"{task.id}: solution text not found in {step['replace']}: {step['old'][:60]!r}")
            write_text_file(file, text.replace(old, new, step.get("count", -1)))
        elif "append" in step:
            with (ws / step["append"]).open("a", encoding="utf-8") as f:
                f.write(task.fill(step["text"]))
        elif "write" in step:
            write_text_file(ws / step["write"], task.fill(step["text"]))
        elif "run" in step:
            subprocess.run([task.fill(a) for a in step["run"]], cwd=ws, check=True, capture_output=True)
        else:
            raise ValueError(f"{task.id}: unknown solution step {step}")


def corrupt_with_placeholder(task: Task, ws: Path, built: dict[str, str]) -> bool:
    """Replace the first secret found in a workspace file with [PASSWORD_1], the way an agent that only saw the
    masked text would write it back. Returns False if no file holds a secret."""
    for rel in built:
        file = ws / rel
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        for s in task.secrets.values():
            if s.value in text:
                write_text_file(file, text.replace(s.value, "[PASSWORD_1]"))
                return True
    return False
