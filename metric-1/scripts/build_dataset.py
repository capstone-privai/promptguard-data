"""Build session corpora with gold spans recorded at insertion time, independently of any detector.

Run from the repository root:
  python metric-1/scripts/build_dataset.py                       built-in corpus below
  python metric-1/scripts/build_dataset.py --template T.jsonl --origin authored|injected
This is normalized evaluation input, NOT a captured agent session; channels follow opencode's hooks.

Writes two files under --out (default metric-1/; with --template T.jsonl: sessions_from_T.jsonl, gold_from_T.jsonl):
  data_test/sessions.jsonl  one session per line: session_id, items, meta (no gold)
  data_answer/gold.jsonl    one gold span per line: session_id, item_id, span_id, span
                            (span = {start, end, type}; items without spans are omitted)

Template file: same shape as sessions.jsonl, but item text holds placeholders that are
replaced by deterministic synthetic secrets (see metric-1/templates/README.md):
  {{kind}} {{kind:name}} {{kind:name|transform|...}}   generated value, e.g. {{password:db|base64}}
  {{TYPE=literal}}                                    fixed value labeled TYPE, e.g. {{PASSWORD=changeme}}
  \\{{                                                 a literal "{{"
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

from dataset_policy import ALLOWED_USE

VERSION = "metric1-v0.1"
REPO_ROOT = Path(__file__).resolve().parents[2]
# Where the text passes through opencode (plugin hook):
#   prompt        user message                        chat.message
#   instructions  AGENTS.md / CLAUDE.md / config      experimental.chat.system.transform
#   tool_input    tool arguments written by the model tool.execute.before (e.g. a bash command)
#   tool_output   tool result returned to the model   tool.execute.after (bash merges stdout and stderr)
CHANNELS = {"prompt", "instructions", "tool_input", "tool_output"}
TYPES = {"PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY"}


@dataclass(frozen=True)
class Slot:
    value: str
    kind: str


def value(name: str, length: int = 32, alphabet: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") -> str:
    # Public deterministic synthetic values. Never use these for authentication.
    raw = hashlib.shake_256((VERSION + ":" + name).encode()).digest(length)
    return "".join(alphabet[b % len(alphabet)] for b in raw)


def password(name: str, suffix: str = "#7!") -> Slot:
    return Slot(value(name, 13) + suffix, "PASSWORD")


def token(name: str, prefix: str = "") -> Slot:
    return Slot(prefix + value(name, 36), "TOKEN")


def uri(name: str, scheme: str = "postgresql", encoded: bool = False) -> Slot:
    # Full URI is the gold unit per the 2026-10-02 label guide. No query ambiguity.
    text = f"{scheme}://service:{quote(password(name).value, safe='')}@db.example.invalid:5432/app"
    return Slot(quote(text, safe="") if encoded else text, "SECRET")


class Corpus:
    def __init__(self):
        self.sessions = []
        self.gold = []

    def session(self, slug: str, title: str):
        self.add_session(f"m1-{slug}", {
            "dataset_version": VERSION, "source": "authored_synthetic_injection",
            "origin": "authored", "allowed_use": ALLOWED_USE["authored"],
            "scenario": title, "group_id": slug,
            "label_policy": "notion-2026-10-02+metric1-2026-10-04",
            "human_review": "pending",
        })

    def add_session(self, session_id: str, meta: dict):
        self.current = {"session_id": session_id, "items": [], "meta": meta}
        self.sessions.append(self.current)

    def item(self, channel: str, *parts: str | Slot, turn: str = "t0"):
        session_id, item_id = self.current["session_id"], len(self.current["items"])
        text, spans = "", []
        for part in parts:
            if isinstance(part, str):
                text += part
                continue
            start = len(text)
            text += part.value
            spans.append({"start": start, "end": len(text), "type": part.kind})
        for span_id, span in enumerate(spans):
            self.gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id, "span": span})
        self.current["items"].append({"item_id": item_id, "turn_id": turn, "channel": channel, "text": text})


def build() -> Corpus:
    c = Corpus()
    c.session("01-node-env", "Node API의 환경 설정 확인")
    c.item("prompt", "로컬 API가 인증 오류로 시작되지 않아. 환경 설정과 예시 파일의 차이를 확인해줘.")
    c.item("tool_output", "NODE_ENV=development\nPORT=3000\nDB_HOST=db.example.invalid\nDB_PASSWORD=\"", password("node-db"),
           "\"\nPAYMENT_API_KEY=", Slot(value("payment", 40), "SECRET"), "\nLOG_LEVEL=info\n")
    c.item("tool_output", "# Required variables\nDB_PASSWORD=", Slot("changeme", "PASSWORD"), "\nAPI_KEY=${PAYMENT_API_KEY}\nPORT=3000\n")
    c.item("tool_output", "Error: upstream returned 401\n    at connect (/workspace/api/client.js:42:9)\nretry_count=3\n")

    c.session("02-python-uri", "Python DB 연결 실패와 예외 출력")
    db = uri("python-db")
    c.item("prompt", "Find why the worker cannot connect to the database after the configuration change.")
    c.item("tool_output", "[database]\nurl = \"", db, "\"\npool_size = 5\n[worker]\nconcurrency = 2\n")
    c.item("tool_output", "Traceback (most recent call last):\n  File \"/workspace/worker.py\", line 21, in main\n    connect(settings.url)\nConnectionError: connection refused for ", db, "\n")
    c.item("tool_output", "request_id=ca9728a4-a732-4cda-88e9-543f5c34204f\nstatus=retrying\nbackoff_seconds=2\n")

    c.session("03-compose", "Docker Compose의 기본값과 테스트 비밀번호")
    c.item("prompt", "컨테이너를 다시 만든 뒤 DB 인증이 실패해. Compose에서 전달하는 값을 확인해줘.")
    c.item("tool_output", "services:\n  database:\n    image: postgres:16\n    environment:\n      POSTGRES_USER: app\n      POSTGRES_PASSWORD: ", Slot("postgres", "PASSWORD"),
           "\n  api:\n    environment:\n      SESSION_SECRET: ", Slot(value("compose-session", 48), "SECRET"), "\n")
    c.item("tool_output", "tests/auth.test.ts:8:const apiToken = '", Slot("dummy_token_123", "TOKEN"),
           "';\ntests/auth.test.ts:9:const password = '", Slot("test1234", "PASSWORD"), "';\n")
    c.item("tool_output", "api-1 | password authentication failed for user app\ndatabase-1 | connection closed\n")

    c.session("04-http", "HTTP 클라이언트 인증 헤더와 쿠키")
    bearer = token("http-bearer")
    basic = Slot(base64.b64encode(("deploy:" + password("http-basic").value).encode()).decode(), "TOKEN")
    c.item("prompt", "Inspect the API client's authentication error without changing the retry policy.")
    c.item("tool_output", "* Connected to api.example.invalid port 443\n> GET /v1/status HTTP/1.1\n> Host: api.example.invalid\n> Authorization: Bearer ", bearer,
           "\n> X-Request-ID: ace39be0-09f5-425d-a18f-6c5b31f91dfb\n< HTTP/1.1 401 Unauthorized\n")
    c.item("tool_output", "HTTP/1.1 200 OK\nContent-Type: application/json\nSet-Cookie: session=", token("session-cookie"),
           "; HttpOnly; Secure; SameSite=Lax\nETag: \"" + value("etag", 32, "0123456789abcdef") + "\"\n")
    c.item("tool_output", "DEBUG retrying with Authorization: Basic ", basic, "\nERROR upstream status=403\n")

    c.session("05-git-history", "Git 이력에 남은 클라우드 키")
    access = Slot("AKIA" + value("aws-access", 16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "ACCESS_KEY")
    secret = Slot(value("aws-secret", 40, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/+"), "SECRET")
    c.item("prompt", "현재 설정에는 없는 AWS 인증 오류의 원인이 최근 변경에 있는지 살펴봐줘.")
    c.item("tool_output", "commit " + value("commit", 40, "0123456789abcdef") +
           "\nAuthor: Build Bot <build@example.invalid>\n\n    remove local credentials\n\ndiff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n@@ -1,3 +1 @@\n-AWS_ACCESS_KEY_ID=", access,
           "\n-AWS_SECRET_ACCESS_KEY=", secret, "\n AWS_REGION=ap-northeast-2\n")
    c.item("tool_output", "AWS_REGION=ap-northeast-2\nAWS_PROFILE=dev\ncredential_source=Environment\n")
    c.item("tool_output", "InvalidClientTokenId: the security token included in the request is invalid\nrequest_id=848237a0-011a-4df9-9574-36a28b8c094b\n")

    c.session("06-process", "프로세스 명령줄과 셸 기본값 속 비밀")
    c.item("prompt", "The background export job is stuck. Check its arguments and environment.")
    c.item("tool_output", "USER       PID COMMAND\nworker     201 mysql --host=db.example.invalid --user=export -p", password("mysql-cli", "!8"),
           " app\nworker     208 sh -c 'curl -H \"X-Api-Key: ${SERVICE_KEY:-", Slot(value("shell-default", 36), "SECRET"),
           "}\" https://api.example.invalid/jobs'\n")
    c.item("tool_output", "HOME=/home/worker\nPATH=/usr/local/bin:/usr/bin\nGITHUB_TOKEN=", token("github", "ghp_"),
           "\nJOB_ID=batch-20261004-021\n")
    c.item("tool_output", "mysql: [Warning] Using a password on the command line interface can be insecure.\nERROR 2003: connection refused\n")

    c.session("07-kubernetes", "Kubernetes Secret의 인코딩된 값")
    pw = password("k8s-db")
    encoded = Slot(base64.b64encode(pw.value.encode()).decode(), "PASSWORD")
    c.item("prompt", "배포한 Pod가 DB 인증에 실패해. Secret과 앱 로그의 설정이 일치하는지 확인해줘.")
    c.item("tool_output", "apiVersion: v1\nkind: Secret\nmetadata:\n  name: app-db\n  namespace: staging\ntype: Opaque\ndata:\n  password: ", encoded,
           "\n  api-token: ", Slot(base64.b64encode(token("k8s-api").value.encode()).decode(), "TOKEN"), "\n")
    c.item("tool_output", "2026-10-04T08:00:00Z INFO opening connection\n2026-10-04T08:00:01Z DEBUG connection_uri_encoded=", uri("k8s-db", encoded=True),
           "\n2026-10-04T08:00:02Z ERROR auth failed\n")
    c.item("tool_output", "NAME                   READY   STATUS\napi-7cbd6f9d4b-qx2n8   0/1     Running\n")

    c.session("08-prompt-agents", "프롬프트와 자동 로드 파일의 채널 누락")
    pw = password("natural-ko")
    c.item("prompt", "스테이징 DB 비밀번호는 ", pw, " 이야. 연결이 왜 끊기는지 로그를 확인해줘.")
    c.item("instructions", "# Workspace notes\nRun unit tests before changing deployment scripts.\nThe temporary deploy password is ", password("agents"),
           ".\nUse the package manager lockfile.\n")
    c.item("tool_output", "2026-10-04 INFO db_host=db.example.invalid\n2026-10-04 ERROR connection timeout\nretries=3\n")
    c.item("prompt", "The service token was rotated to ", token("natural-en"), ". Check whether the retry changed the error.", turn="t1")
    c.item("tool_output", "인증 재시도 실패: password=", pw, "\nnetwork_timeout_ms=5000\n", turn="t1")

    c.session("09-private-key", "PEM 개인키와 줄 경계")
    # RFC 8410 Ed25519 PKCS#8, created from a public deterministic seed; never registered.
    der = bytes.fromhex("302e020100300506032b657004220420") + hashlib.sha256((VERSION + ":ed25519").encode()).digest()
    pem = "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----"
    c.item("prompt", "The signing worker rejects its local key. Inspect the configured key format.")
    c.item("tool_output", "signing_key_path=/workspace/keys/signing.pem\nalgorithm=Ed25519\n")
    c.item("tool_output", Slot(pem, "PRIVATE_KEY"), "\n")
    c.item("tool_output", "KeyError: remote key id does not match\nkey_id=signer-2026-10\n")

    c.session("10-negative-build", "비밀이 없는 빌드 출력과 고엔트로피 식별자")
    c.item("prompt", "Check whether the dependency build completed and identify the changed artifact.")
    c.item("tool_output", "lockfileVersion: 9\npackage: web-client\nintegrity: sha512-" + base64.b64encode(hashlib.sha512(b"public package artifact").digest()).decode() +
           "\nresolved: https://registry.npmjs.org/typescript/-/typescript-5.7.3.tgz\n")
    c.item("tool_output", "image=web-client\ndigest=sha256:" + value("image-digest", 64, "0123456789abcdef") +
           "\nrequest_id=792a25e2-93f1-4892-b14e-fcfb66bc6074\nmodules=248\nbuild completed in 2.4s\n")
    c.item("tool_output", "warning: source map omitted for vendor.js\n0 errors, 1 warning\n")

    c.session("11-negative-config", "비밀이 없는 참조 표현과 식별자")
    c.item("prompt", "설정 문서에서 필요한 환경 변수와 공개 식별자 목록을 정리해줘.")
    c.item("tool_output", "DB_PASSWORD=${DB_PASSWORD}\nAPI_TOKEN=<API_TOKEN>\nSECRET_NAME=service-config\npassword=\n")
    c.item("tool_output", "# Runtime metrics\ntoken_count=2048\nmax_tokens=8192\nchecksum=" + value("checksum", 64, "0123456789abcdef") +
           "\nasset_id=1af68b2a-3e30-41f7-a825-bcc4e8c5c6d1\n")
    c.item("tool_output", "Reference variables are substituted by the deployment environment.\nNo literal credentials are defined in this template.\n")

    c.session("12-rotation", "여러 턴의 반복 노출·한국어·CRLF·공개용 키")
    old, new = password("rotation-old"), password("rotation-new")
    public = Slot("pk_test_" + value("publishable", 24), "ACCESS_KEY")
    c.item("prompt", "🔎 윈도우 설정과 인증 오류를 확인하고, 교체 전후 값을 비교해줘.")
    c.item("tool_output", "# 인증 설정 🔐\r\nDB_USER=배포\r\nDB_PASSWORD=\"", old, "\"\r\nPUBLISHABLE_KEY=", public, "\r\n")
    c.item("tool_output", "connect failed; password=", old, "; retry_password=", old, "\n")
    c.item("prompt", "설정 파일을 교체했어. 다시 확인하고 새 오류를 비교해줘.", turn="t1")
    c.item("tool_output", "# updated config\nDB_PASSWORD='", new, "'\nPUBLISHABLE_KEY=", public, "\n", turn="t1")
    c.item("tool_output", "new connection failed; password=", new, turn="t1")
    return c


# ---- templates -------------------------------------------------------------

def strong_password(seed: str) -> str:
    # 14 chars with every character class, without a fixed suffix a model could learn.
    body = value(seed + ":body", 11, "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    extra = value(seed + ":upper", 1, "ABCDEFGHJKLMNPQRSTUVWXYZ") + value(seed + ":digit", 1, "23456789") + \
        value(seed + ":symbol", 1, "!#$%&*+-=?@^_~")
    cut = hashlib.sha256(seed.encode()).digest()[0] % len(body)
    return body[:cut] + extra + body[cut:]


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt(seed: str) -> str:
    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(json.dumps({"sub": value(seed + ":sub", 8, "0123456789"), "iat": 1790000000}, separators=(",", ":")).encode())
    return f"{header}.{payload}.{b64url(hashlib.sha256((VERSION + ':' + seed).encode()).digest())}"


def ed25519_pem(seed: str) -> str:
    # RFC 8410 PKCS#8 wrapper around a public deterministic seed; never registered anywhere.
    der = bytes.fromhex("302e020100300506032b657004220420") + hashlib.sha256((VERSION + ":" + seed).encode()).digest()
    return "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----"


DIGITS = "0123456789"
UPPER_ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
AWS_SECRET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/+"

# kind -> (gold type, generator(seed) -> value)
GENERATORS = {
    "password": ("PASSWORD", strong_password),
    "token": ("TOKEN", lambda s: value(s, 40)),
    "github_token": ("TOKEN", lambda s: "ghp_" + value(s, 36)),
    "slack_token": ("TOKEN", lambda s: f"xoxb-{value(s + ':a', 12, DIGITS)}-{value(s + ':b', 13, DIGITS)}-{value(s, 24)}"),
    "jwt": ("TOKEN", jwt),
    "api_key": ("SECRET", lambda s: value(s, 40)),
    "secret": ("SECRET", lambda s: value(s, 48)),
    "aws_access_key": ("ACCESS_KEY", lambda s: "AKIA" + value(s, 16, UPPER_ALNUM)),
    "aws_secret_key": ("SECRET", lambda s: value(s, 40, AWS_SECRET)),
    "publishable_key": ("ACCESS_KEY", lambda s: "pk_test_" + value(s, 24)),
    "db_uri": ("SECRET", lambda s: f"postgresql://service:{quote(strong_password(s), safe='')}@db.example.invalid:5432/app"),
    "private_key": ("PRIVATE_KEY", ed25519_pem),
}


def transform(text: str, name: str, arg: str | None) -> tuple[str, str | None]:
    """Returns the encoded text and, if the transform changes it, the new gold type."""
    if name == "base64":
        return base64.b64encode(text.encode()).decode(), None
    if name == "url":
        return quote(text, safe=""), None
    if name == "basic":
        # HTTP Basic credential: base64("user:secret"), labeled as a token like the built-in corpus.
        return base64.b64encode(f"{arg or 'user'}:{text}".encode()).decode(), "TOKEN"
    raise ValueError(f"unknown transform {name!r}")


PLACEHOLDER = re.compile(r"""
    \\\{\{                                                     # escaped literal "{{"
  | \{\{ (?P<kind>[a-z][a-z0-9_]*) (?::(?P<name>[\w.-]+))?
         (?P<transforms>(?:\|[a-z0-9_]+(?:=[^|}]*)?)*) \}\}    # {{kind:name|t1|t2=arg}}
  | \{\{ (?P<type>[A-Z][A-Z_]*) = (?P<literal>.+?) \}\}        # {{TYPE=literal}}
""", re.VERBOSE | re.DOTALL)
SUSPICIOUS = re.compile(r"\{\{[A-Za-z][^\s{}]*\}\}")


def parse_text(text: str, seed: str, unnamed: list[int]) -> list[str | Slot]:
    """Split template text into literal strings and Slots."""
    parts, pos = [], 0
    for m in PLACEHOLDER.finditer(text):
        parts.append(text[pos:m.start()])
        pos = m.end()
        if m.group(0) == "\\{{":
            parts.append("{{")
        elif m.group("type"):
            if m.group("type") not in TYPES:
                raise ValueError(f"unknown gold type in {m.group(0)!r}, expected one of {sorted(TYPES)}")
            parts.append(Slot(m.group("literal"), m.group("type")))
        else:
            kind = m.group("kind")
            if kind not in GENERATORS:
                raise ValueError(f"unknown kind in {m.group(0)!r}, expected one of {sorted(GENERATORS)}")
            kind_type, generate = GENERATORS[kind]
            name = m.group("name")
            if name is None:  # each unnamed placeholder gets its own value
                unnamed[0] += 1
                name = f"#{unnamed[0]}"
            out = generate(f"{seed}:{kind}:{name}")
            for t in filter(None, m.group("transforms").split("|")):
                t_name, _, t_arg = t.partition("=")
                out, new_type = transform(out, t_name, t_arg or None)
                kind_type = new_type or kind_type
            parts.append(Slot(out, kind_type))
    parts.append(text[pos:])
    for part in parts:
        if isinstance(part, str) and (m := SUSPICIOUS.search(part)):
            raise ValueError(f"{m.group(0)!r} looks like a placeholder but is not one; escape it as \\{{{{ if it is literal text")
    return [p for p in parts if p != ""]


def from_template(path: Path, origin: str) -> Corpus:
    if origin not in ALLOWED_USE:
        raise ValueError(f"unknown origin {origin!r}, expected one of {sorted(ALLOWED_USE)}")
    try:
        template = str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        template = str(path.resolve())
    c = Corpus()
    seen = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        s = json.loads(line)
        if set(s) - {"session_id", "items", "meta"} or not {"session_id", "items"} <= set(s):
            raise ValueError(f"{where}: a session needs session_id and items, and may have meta; got {sorted(s)}")
        sid = s["session_id"]
        if sid in seen:
            raise ValueError(f"{where}: duplicate session_id {sid}")
        seen.add(sid)
        meta = dict(s.get("meta", {}))
        owned = {"dataset_version": VERSION, "source": "template", "template": template,
                 "origin": origin, "allowed_use": ALLOWED_USE[origin]}
        for key, val in owned.items():
            if key in meta and meta[key] != val:
                raise ValueError(f"{where}: meta.{key} is set by the builder ({val!r}); remove {meta[key]!r} from the template")
        meta = {**owned, "group_id": sid, **meta}
        c.add_session(sid, meta)
        unnamed = [0]
        for i, item in enumerate(s["items"]):
            if set(item) - {"item_id", "turn_id", "channel", "text"} or not {"channel", "text"} <= set(item):
                raise ValueError(f"{where}: item {i} needs channel and text, and may have item_id and turn_id; got {sorted(item)}")
            if item.get("item_id", i) != i:
                raise ValueError(f"{where}: item at index {i} has item_id {item['item_id']!r}")
            if item["channel"] not in CHANNELS:
                raise ValueError(f"{where}: item {i} unknown channel {item['channel']!r}, expected one of {sorted(CHANNELS)}")
            try:
                parts = parse_text(item["text"], f"{path.stem}:{sid}", unnamed)
            except ValueError as e:
                raise ValueError(f"{where}: item {i}: {e}") from None
            c.item(item["channel"], *parts, turn=item.get("turn_id", "t0"))
    return c


def output_paths(out: Path, template: Path | None) -> tuple[Path, Path]:
    suffix = "" if template is None else f"_from_{template.stem}"
    return out / "data_test" / f"sessions{suffix}.jsonl", out / "data_answer" / f"gold{suffix}.jsonl"


def write_jsonl(path: Path, rows):
    path.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))


def validate(c: Corpus):
    items = {(s["session_id"], i["item_id"]): i for s in c.sessions for i in s["items"]}
    assert len(items) == sum(len(s["items"]) for s in c.sessions)
    assert {(g["session_id"], g["item_id"]) for g in c.gold} <= set(items)
    spans = [((g["session_id"], g["item_id"]), g["span"]["start"], g["span"]["end"]) for g in c.gold]
    # Find every occurrence of longer injected secrets independently of insertion.
    # Short/default words are scoped by insertion only, since they also appear as ordinary text.
    for secret in {items[g[0]]["text"][g[1]:g[2]] for g in spans}:
        if len(secret) < 9:
            continue
        for key, item in items.items():
            for m in re.finditer(re.escape(secret), item["text"]):
                assert any(g[0] == key and g[1] <= m.start() < m.end() <= g[2] for g in spans), (key, secret)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--template", type=Path, help="session template JSONL with {{...}} placeholders")
    parser.add_argument("--origin", choices=sorted(ALLOWED_USE),
                        help="required with --template: authored if the secrets fit the context they were written in, "
                             "injected if placeholders were added to a trajectory not written for them (rule_eval only)")
    args = parser.parse_args()
    if args.template and not args.origin:
        parser.error("--template requires --origin")
    if args.origin and not args.template:
        parser.error("--origin only applies to --template")
    c = from_template(args.template, args.origin) if args.template else build()
    validate(c)
    sessions_path, gold_path = output_paths(args.out, args.template)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(sessions_path, c.sessions)
    write_jsonl(gold_path, c.gold)
    print(f"{sessions_path.name}, {gold_path.name}: {len(c.sessions)} sessions, "
          f"{sum(len(s['items']) for s in c.sessions)} items, {len(c.gold)} gold spans")


if __name__ == "__main__":
    main()
