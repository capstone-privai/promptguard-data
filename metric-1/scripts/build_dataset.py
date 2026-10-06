"""Build a small authored, injected session corpus, independently of any detector.

Run from the repository root: python metric-1/scripts/build_dataset.py
This is normalized evaluation input, NOT a captured Codex rollout.

Writes exactly two files:
  sessions.jsonl  one session per line: session_id, items, meta (no gold)
  gold.jsonl      one gold span per line: session_id, item_id, span_id, span
                  (span = {start, end, type}; items without spans are omitted)
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

VERSION = "metric1-v0.1"


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
        self.current = {"session_id": f"m1-{slug}", "items": [], "meta": {
            "dataset_version": VERSION, "source": "authored_synthetic_injection",
            "scenario": title, "group_id": slug, "split": "pilot_test",
            "label_policy": "notion-2026-10-02+metric1-2026-10-04",
            "human_review": "pending", "real_codex_rollout": False,
        }}
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
    c.item("stdout", "NODE_ENV=development\nPORT=3000\nDB_HOST=db.example.invalid\nDB_PASSWORD=\"", password("node-db"),
           "\"\nPAYMENT_API_KEY=", Slot(value("payment", 40), "SECRET"), "\nLOG_LEVEL=info\n")
    c.item("stdout", "# Required variables\nDB_PASSWORD=", Slot("changeme", "PASSWORD"), "\nAPI_KEY=${PAYMENT_API_KEY}\nPORT=3000\n")
    c.item("stderr", "Error: upstream returned 401\n    at connect (/workspace/api/client.js:42:9)\nretry_count=3\n")

    c.session("02-python-uri", "Python DB 연결 실패와 예외 출력")
    db = uri("python-db")
    c.item("prompt", "Find why the worker cannot connect to the database after the configuration change.")
    c.item("stdout", "[database]\nurl = \"", db, "\"\npool_size = 5\n[worker]\nconcurrency = 2\n")
    c.item("stderr", "Traceback (most recent call last):\n  File \"/workspace/worker.py\", line 21, in main\n    connect(settings.url)\nConnectionError: connection refused for ", db, "\n")
    c.item("stdout", "request_id=ca9728a4-a732-4cda-88e9-543f5c34204f\nstatus=retrying\nbackoff_seconds=2\n")

    c.session("03-compose", "Docker Compose의 기본값과 테스트 비밀번호")
    c.item("prompt", "컨테이너를 다시 만든 뒤 DB 인증이 실패해. Compose에서 전달하는 값을 확인해줘.")
    c.item("stdout", "services:\n  database:\n    image: postgres:16\n    environment:\n      POSTGRES_USER: app\n      POSTGRES_PASSWORD: ", Slot("postgres", "PASSWORD"),
           "\n  api:\n    environment:\n      SESSION_SECRET: ", Slot(value("compose-session", 48), "SECRET"), "\n")
    c.item("stdout", "tests/auth.test.ts:8:const apiToken = '", Slot("dummy_token_123", "TOKEN"),
           "';\ntests/auth.test.ts:9:const password = '", Slot("test1234", "PASSWORD"), "';\n")
    c.item("stderr", "api-1 | password authentication failed for user app\ndatabase-1 | connection closed\n")

    c.session("04-http", "HTTP 클라이언트 인증 헤더와 쿠키")
    bearer = token("http-bearer")
    basic = Slot(base64.b64encode(("deploy:" + password("http-basic").value).encode()).decode(), "TOKEN")
    c.item("prompt", "Inspect the API client's authentication error without changing the retry policy.")
    c.item("stderr", "* Connected to api.example.invalid port 443\n> GET /v1/status HTTP/1.1\n> Host: api.example.invalid\n> Authorization: Bearer ", bearer,
           "\n> X-Request-ID: ace39be0-09f5-425d-a18f-6c5b31f91dfb\n< HTTP/1.1 401 Unauthorized\n")
    c.item("stdout", "HTTP/1.1 200 OK\nContent-Type: application/json\nSet-Cookie: session=", token("session-cookie"),
           "; HttpOnly; Secure; SameSite=Lax\nETag: \"" + value("etag", 32, "0123456789abcdef") + "\"\n")
    c.item("stderr", "DEBUG retrying with Authorization: Basic ", basic, "\nERROR upstream status=403\n")

    c.session("05-git-history", "Git 이력에 남은 클라우드 키")
    access = Slot("AKIA" + value("aws-access", 16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "ACCESS_KEY")
    secret = Slot(value("aws-secret", 40, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/+"), "SECRET")
    c.item("prompt", "현재 설정에는 없는 AWS 인증 오류의 원인이 최근 변경에 있는지 살펴봐줘.")
    c.item("stdout", "commit " + value("commit", 40, "0123456789abcdef") +
           "\nAuthor: Build Bot <build@example.invalid>\n\n    remove local credentials\n\ndiff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n@@ -1,3 +1 @@\n-AWS_ACCESS_KEY_ID=", access,
           "\n-AWS_SECRET_ACCESS_KEY=", secret, "\n AWS_REGION=ap-northeast-2\n")
    c.item("stdout", "AWS_REGION=ap-northeast-2\nAWS_PROFILE=dev\ncredential_source=Environment\n")
    c.item("stderr", "InvalidClientTokenId: the security token included in the request is invalid\nrequest_id=848237a0-011a-4df9-9574-36a28b8c094b\n")

    c.session("06-process", "프로세스 명령줄과 셸 기본값 속 비밀")
    c.item("prompt", "The background export job is stuck. Check its arguments and environment.")
    c.item("stdout", "USER       PID COMMAND\nworker     201 mysql --host=db.example.invalid --user=export -p", password("mysql-cli", "!8"),
           " app\nworker     208 sh -c 'curl -H \"X-Api-Key: ${SERVICE_KEY:-", Slot(value("shell-default", 36), "SECRET"),
           "}\" https://api.example.invalid/jobs'\n")
    c.item("stdout", "HOME=/home/worker\nPATH=/usr/local/bin:/usr/bin\nGITHUB_TOKEN=", token("github", "ghp_"),
           "\nJOB_ID=batch-20261004-021\n")
    c.item("stderr", "mysql: [Warning] Using a password on the command line interface can be insecure.\nERROR 2003: connection refused\n")

    c.session("07-kubernetes", "Kubernetes Secret의 인코딩된 값")
    pw = password("k8s-db")
    encoded = Slot(base64.b64encode(pw.value.encode()).decode(), "PASSWORD")
    c.item("prompt", "배포한 Pod가 DB 인증에 실패해. Secret과 앱 로그의 설정이 일치하는지 확인해줘.")
    c.item("stdout", "apiVersion: v1\nkind: Secret\nmetadata:\n  name: app-db\n  namespace: staging\ntype: Opaque\ndata:\n  password: ", encoded,
           "\n  api-token: ", Slot(base64.b64encode(token("k8s-api").value.encode()).decode(), "TOKEN"), "\n")
    c.item("stdout", "2026-10-04T08:00:00Z INFO opening connection\n2026-10-04T08:00:01Z DEBUG connection_uri_encoded=", uri("k8s-db", encoded=True),
           "\n2026-10-04T08:00:02Z ERROR auth failed\n")
    c.item("stdout", "NAME                   READY   STATUS\napi-7cbd6f9d4b-qx2n8   0/1     Running\n")

    c.session("08-prompt-agents", "프롬프트와 자동 로드 파일의 채널 누락")
    pw = password("natural-ko")
    c.item("prompt", "스테이징 DB 비밀번호는 ", pw, " 이야. 연결이 왜 끊기는지 로그를 확인해줘.")
    c.item("agents_md", "# Workspace notes\nRun unit tests before changing deployment scripts.\nThe temporary deploy password is ", password("agents"),
           ".\nUse the package manager lockfile.\n")
    c.item("stdout", "2026-10-04 INFO db_host=db.example.invalid\n2026-10-04 ERROR connection timeout\nretries=3\n")
    c.item("prompt", "The service token was rotated to ", token("natural-en"), ". Check whether the retry changed the error.", turn="t1")
    c.item("stderr", "인증 재시도 실패: password=", pw, "\nnetwork_timeout_ms=5000\n", turn="t1")

    c.session("09-private-key", "PEM 개인키와 줄 경계")
    # RFC 8410 Ed25519 PKCS#8, created from a public deterministic seed; never registered.
    der = bytes.fromhex("302e020100300506032b657004220420") + hashlib.sha256((VERSION + ":ed25519").encode()).digest()
    pem = "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----"
    c.item("prompt", "The signing worker rejects its local key. Inspect the configured key format.")
    c.item("stdout", "signing_key_path=/workspace/keys/signing.pem\nalgorithm=Ed25519\n")
    c.item("stdout", Slot(pem, "PRIVATE_KEY"), "\n")
    c.item("stderr", "KeyError: remote key id does not match\nkey_id=signer-2026-10\n")

    c.session("10-negative-build", "비밀이 없는 빌드 출력과 고엔트로피 식별자")
    c.item("prompt", "Check whether the dependency build completed and identify the changed artifact.")
    c.item("stdout", "lockfileVersion: 9\npackage: web-client\nintegrity: sha512-" + base64.b64encode(hashlib.sha512(b"public package artifact").digest()).decode() +
           "\nresolved: https://registry.npmjs.org/typescript/-/typescript-5.7.3.tgz\n")
    c.item("stdout", "image=web-client\ndigest=sha256:" + value("image-digest", 64, "0123456789abcdef") +
           "\nrequest_id=792a25e2-93f1-4892-b14e-fcfb66bc6074\nmodules=248\nbuild completed in 2.4s\n")
    c.item("stderr", "warning: source map omitted for vendor.js\n0 errors, 1 warning\n")

    c.session("11-negative-config", "비밀이 없는 참조 표현과 식별자")
    c.item("prompt", "설정 문서에서 필요한 환경 변수와 공개 식별자 목록을 정리해줘.")
    c.item("stdout", "DB_PASSWORD=${DB_PASSWORD}\nAPI_TOKEN=<API_TOKEN>\nSECRET_NAME=service-config\npassword=\n")
    c.item("stdout", "# Runtime metrics\ntoken_count=2048\nmax_tokens=8192\nchecksum=" + value("checksum", 64, "0123456789abcdef") +
           "\nasset_id=1af68b2a-3e30-41f7-a825-bcc4e8c5c6d1\n")
    c.item("stdout", "Reference variables are substituted by the deployment environment.\nNo literal credentials are defined in this template.\n")

    c.session("12-rotation", "여러 턴의 반복 노출·한국어·CRLF·공개용 키")
    old, new = password("rotation-old"), password("rotation-new")
    public = Slot("pk_test_" + value("publishable", 24), "ACCESS_KEY")
    c.item("prompt", "🔎 윈도우 설정과 인증 오류를 확인하고, 교체 전후 값을 비교해줘.")
    c.item("stdout", "# 인증 설정 🔐\r\nDB_USER=배포\r\nDB_PASSWORD=\"", old, "\"\r\nPUBLISHABLE_KEY=", public, "\r\n")
    c.item("stderr", "connect failed; password=", old, "; retry_password=", old, "\n")
    c.item("prompt", "설정 파일을 교체했어. 다시 확인하고 새 오류를 비교해줘.", turn="t1")
    c.item("stdout", "# updated config\nDB_PASSWORD='", new, "'\nPUBLISHABLE_KEY=", public, "\n", turn="t1")
    c.item("stderr", "new connection failed; password=", new, turn="t1")
    return c


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
    args = parser.parse_args()
    c = build()
    validate(c)
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "sessions.jsonl", c.sessions)
    write_jsonl(args.out / "gold.jsonl", c.gold)
    print(f"{len(c.sessions)} sessions, {sum(len(s['items']) for s in c.sessions)} items, {len(c.gold)} gold spans")


if __name__ == "__main__":
    main()
