"""Build a small authored, injected session corpus, independently of any detector.

Run from the repository root: python metric-1/scripts/build_metric1_v0.py
This is normalized evaluation input, NOT a captured Codex rollout.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

VERSION = "metric1-v0.1"
REFERENCE_COMMIT = "027a3e0d0cb4d86e9b310293229dddc7d4459b9c"


@dataclass(frozen=True)
class Slot:
    value: str
    kind: str
    reason: str = "test_value"
    exposure: str = "direct"
    subtype: str = ""
    action: str = "MASK"


def keep(value: str, reason: str) -> Slot:
    return Slot(value, "NON_SECRET", reason=reason, action="KEEP")


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
    return Slot(quote(text, safe="") if encoded else text, "SECRET", exposure="url_encoded" if encoded else "embedded", subtype="URL_CREDENTIAL")


class Corpus:
    def __init__(self):
        self.sessions = []
        self.annotations = []
        self.bases = []
        self.operations = []

    def session(self, slug: str, title: str):
        self.current = {"session_id": f"m1-{slug}", "items": [], "gold": [], "meta": {
            "dataset_version": VERSION, "source": "authored_synthetic_injection",
            "scenario": title, "group_id": slug, "split": "pilot_test",
            "label_policy": "notion-2026-10-02+metric1-2026-10-04",
            "human_review": "pending", "real_codex_rollout": False,
        }}
        self.sessions.append(self.current)

    def item(self, channel: str, *parts: str | Slot, turn: str = "t0", command: str | None = None):
        item_id = f"{self.current['session_id']}/{len(self.current['items']):02d}"
        text, base = "", ""
        for part in parts:
            if isinstance(part, str):
                text += part
                base += part
                continue
            start = len(text)
            text += part.value
            base += "<REDACTED>" if part.action == "MASK" else part.value
            annotation = {"session_id": self.current["session_id"], "item_id": item_id,
                "start": start, "end": len(text), "value": part.value, "action": part.action,
                "type": part.kind, "reason": part.reason, "exposure": part.exposure,
                "subtype": part.subtype, "channel": channel}
            self.annotations.append(annotation)
            if part.action == "MASK":
                self.current["gold"].append({k: annotation[k] for k in ("item_id", "start", "end", "type")})
        self.current["items"].append({"item_id": item_id, "turn_id": turn, "channel": channel, "text": text})
        self.bases.append({"item_id": item_id, "channel": channel, "text": base})
        self.operations.append({"item_id": item_id, "command_context": command,
            "provenance": "authored text; command is context only, not executed"})


def build() -> Corpus:
    c = Corpus()
    c.session("01-node-env", "Node API의 환경 설정 확인")
    c.item("prompt", "로컬 API가 인증 오류로 시작되지 않아. 환경 설정과 예시 파일의 차이를 확인해줘.")
    c.item("stdout", "NODE_ENV=development\nPORT=3000\nDB_HOST=db.example.invalid\nDB_PASSWORD=\"", password("node-db"),
           "\"\nPAYMENT_API_KEY=", Slot(value("payment", 40), "SECRET"), "\nLOG_LEVEL=info\n", command="cat .env")
    c.item("stdout", "# Required variables\nDB_PASSWORD=", Slot("changeme", "PASSWORD", reason="real_credential"),
           "\nAPI_KEY=", keep("${PAYMENT_API_KEY}", "variable_reference"), "\nPORT=3000\n", command="cat .env.example")
    c.item("stderr", "Error: upstream returned 401\n    at connect (/workspace/api/client.js:42:9)\nretry_count=3\n")

    c.session("02-python-uri", "Python DB 연결 실패와 예외 출력")
    db = uri("python-db")
    c.item("prompt", "Find why the worker cannot connect to the database after the configuration change.")
    c.item("stdout", "[database]\nurl = \"", db, "\"\npool_size = 5\n[worker]\nconcurrency = 2\n", command="cat config.toml")
    c.item("stderr", "Traceback (most recent call last):\n  File \"/workspace/worker.py\", line 21, in main\n    connect(settings.url)\nConnectionError: connection refused for ", db, "\n", command="python worker.py")
    c.item("stdout", "request_id=", keep("ca9728a4-a732-4cda-88e9-543f5c34204f", "uuid"), "\nstatus=retrying\nbackoff_seconds=2\n")

    c.session("03-compose", "Docker Compose의 기본값과 테스트 비밀번호")
    c.item("prompt", "컨테이너를 다시 만든 뒤 DB 인증이 실패해. Compose에서 전달하는 값을 확인해줘.")
    c.item("stdout", "services:\n  database:\n    image: postgres:16\n    environment:\n      POSTGRES_USER: app\n      POSTGRES_PASSWORD: ", Slot("postgres", "PASSWORD", reason="real_credential"),
           "\n  api:\n    environment:\n      SESSION_SECRET: ", Slot(value("compose-session", 48), "SECRET"), "\n", command="docker compose config")
    c.item("stdout", "tests/auth.test.ts:8:const apiToken = '", Slot("dummy_token_123", "TOKEN"),
           "';\ntests/auth.test.ts:9:const password = '", Slot("test1234", "PASSWORD"), "';\n", command="rg -n 'apiToken|password' tests/")
    c.item("stderr", "api-1 | password authentication failed for user app\ndatabase-1 | connection closed\n")

    c.session("04-http", "HTTP 클라이언트 인증 헤더와 쿠키")
    bearer = token("http-bearer")
    basic = Slot(base64.b64encode(("deploy:" + password("http-basic").value).encode()).decode(), "TOKEN", exposure="base64", subtype="BASIC_AUTH")
    c.item("prompt", "Inspect the API client's authentication error without changing the retry policy.")
    c.item("stderr", "* Connected to api.example.invalid port 443\n> GET /v1/status HTTP/1.1\n> Host: api.example.invalid\n> Authorization: Bearer ", bearer,
           "\n> X-Request-ID: ", keep("ace39be0-09f5-425d-a18f-6c5b31f91dfb", "uuid"), "\n< HTTP/1.1 401 Unauthorized\n", command="curl -v https://api.example.invalid/v1/status")
    c.item("stdout", "HTTP/1.1 200 OK\nContent-Type: application/json\nSet-Cookie: session=", token("session-cookie"),
           "; HttpOnly; Secure; SameSite=Lax\nETag: \"", keep(value("etag", 32, "0123456789abcdef"), "etag"), "\"\n")
    c.item("stderr", "DEBUG retrying with Authorization: Basic ", basic, "\nERROR upstream status=403\n")

    c.session("05-git-history", "Git 이력에 남은 클라우드 키")
    access = Slot("AKIA" + value("aws-access", 16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "ACCESS_KEY")
    secret = Slot(value("aws-secret", 40, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/+"), "SECRET")
    c.item("prompt", "현재 설정에는 없는 AWS 인증 오류의 원인이 최근 변경에 있는지 살펴봐줘.")
    c.item("stdout", "commit ", keep(value("commit", 40, "0123456789abcdef"), "commit_hash"),
           "\nAuthor: Build Bot <build@example.invalid>\n\n    remove local credentials\n\ndiff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n@@ -1,3 +1 @@\n-AWS_ACCESS_KEY_ID=", access,
           "\n-AWS_SECRET_ACCESS_KEY=", secret, "\n AWS_REGION=ap-northeast-2\n", command="git log -p -1 -- .env")
    c.item("stdout", "AWS_REGION=ap-northeast-2\nAWS_PROFILE=dev\ncredential_source=Environment\n", command="printenv | sort")
    c.item("stderr", "InvalidClientTokenId: the security token included in the request is invalid\nrequest_id=", keep("848237a0-011a-4df9-9574-36a28b8c094b", "uuid"), "\n")

    c.session("06-process", "프로세스 명령줄과 셸 기본값 속 비밀")
    c.item("prompt", "The background export job is stuck. Check its arguments and environment.")
    c.item("stdout", "USER       PID COMMAND\nworker     201 mysql --host=db.example.invalid --user=export -p", password("mysql-cli", "!8"),
           " app\nworker     208 sh -c 'curl -H \"X-Api-Key: ${SERVICE_KEY:-", Slot(value("shell-default", 36), "SECRET", exposure="embedded"),
           "}\" https://api.example.invalid/jobs'\n", command="ps aux")
    c.item("stdout", "HOME=/home/worker\nPATH=/usr/local/bin:/usr/bin\nGITHUB_TOKEN=", token("github", "ghp_"),
           "\nJOB_ID=", keep("batch-20261004-021", "job_identifier"), "\n", command="printenv")
    c.item("stderr", "mysql: [Warning] Using a password on the command line interface can be insecure.\nERROR 2003: connection refused\n")

    c.session("07-kubernetes", "Kubernetes Secret의 인코딩된 값")
    pw = password("k8s-db")
    encoded = Slot(base64.b64encode(pw.value.encode()).decode(), "PASSWORD", exposure="base64", subtype="K8S_SECRET_DATA")
    c.item("prompt", "배포한 Pod가 DB 인증에 실패해. Secret과 앱 로그의 설정이 일치하는지 확인해줘.")
    c.item("stdout", "apiVersion: v1\nkind: Secret\nmetadata:\n  name: app-db\n  namespace: staging\ntype: Opaque\ndata:\n  password: ", encoded,
           "\n  api-token: ", Slot(base64.b64encode(token("k8s-api").value.encode()).decode(), "TOKEN", exposure="base64", subtype="K8S_SECRET_DATA"), "\n", command="kubectl get secret app-db -o yaml")
    c.item("stdout", "2026-10-04T08:00:00Z INFO opening connection\n2026-10-04T08:00:01Z DEBUG connection_uri_encoded=", uri("k8s-db", encoded=True),
           "\n2026-10-04T08:00:02Z ERROR auth failed\n", command="kubectl logs deploy/api")
    c.item("stdout", "NAME                   READY   STATUS\napi-7cbd6f9d4b-qx2n8   0/1     Running\n", command="kubectl get pods")

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
    c.item("stdout", Slot(pem, "PRIVATE_KEY", exposure="multiline", subtype="ED25519_PKCS8"), "\n", command="cat keys/signing.pem")
    c.item("stderr", "KeyError: remote key id does not match\nkey_id=", keep("signer-2026-10", "key_identifier"), "\n")

    c.session("10-negative-build", "비밀이 없는 빌드 출력과 고엔트로피 식별자")
    c.item("prompt", "Check whether the dependency build completed and identify the changed artifact.")
    c.item("stdout", "lockfileVersion: 9\npackage: web-client\nintegrity: sha512-", keep(base64.b64encode(hashlib.sha512(b"public package artifact").digest()).decode(), "package_integrity_hash"),
           "\nresolved: https://registry.npmjs.org/typescript/-/typescript-5.7.3.tgz\n", command="cat pnpm-lock.yaml")
    c.item("stdout", "image=web-client\ndigest=sha256:", keep(value("image-digest", 64, "0123456789abcdef"), "image_digest"),
           "\nrequest_id=", keep("792a25e2-93f1-4892-b14e-fcfb66bc6074", "uuid"), "\nmodules=248\nbuild completed in 2.4s\n")
    c.item("stderr", "warning: source map omitted for vendor.js\n0 errors, 1 warning\n")

    c.session("11-negative-config", "비밀이 없는 참조 표현과 식별자")
    c.item("prompt", "설정 문서에서 필요한 환경 변수와 공개 식별자 목록을 정리해줘.")
    c.item("stdout", "DB_PASSWORD=", keep("${DB_PASSWORD}", "variable_reference"), "\nAPI_TOKEN=", keep("<API_TOKEN>", "unfilled_placeholder"),
           "\nSECRET_NAME=", keep("service-config", "resource_name"), "\npassword=\n", command="cat config.template")
    c.item("stdout", "# Runtime metrics\ntoken_count=", keep("2048", "token_count"), "\nmax_tokens=8192\nchecksum=", keep(value("checksum", 64, "0123456789abcdef"), "checksum"),
           "\nasset_id=", keep("1af68b2a-3e30-41f7-a825-bcc4e8c5c6d1", "uuid"), "\n")
    c.item("stdout", "Reference variables are substituted by the deployment environment.\nNo literal credentials are defined in this template.\n")

    c.session("12-rotation", "여러 턴의 반복 노출·한국어·CRLF·공개용 키")
    old, new = password("rotation-old"), password("rotation-new")
    public = Slot("pk_test_" + value("publishable", 24), "ACCESS_KEY", reason="public_by_design", subtype="PUBLISHABLE_KEY")
    c.item("prompt", "🔎 윈도우 설정과 인증 오류를 확인하고, 교체 전후 값을 비교해줘.")
    c.item("stdout", "# 인증 설정 🔐\r\nDB_USER=배포\r\nDB_PASSWORD=\"", old,
           "\"\r\nPUBLISHABLE_KEY=", public, "\r\n", command="Get-Content config.env (Bash wrapper stdout)")
    c.item("stderr", "connect failed; password=", old, "; retry_password=", old, "\n")
    c.item("prompt", "설정 파일을 교체했어. 다시 확인하고 새 오류를 비교해줘.", turn="t1")
    c.item("stdout", "# updated config\nDB_PASSWORD='", new, "'\nPUBLISHABLE_KEY=", public, "\n", turn="t1", command="cat config.env")
    c.item("stderr", "new connection failed; password=", new, turn="t1")
    return c


def write_jsonl(path: Path, rows):
    path.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))


def validate(c: Corpus):
    items = {i["item_id"]: i for s in c.sessions for i in s["items"]}
    assert len(items) == sum(len(s["items"]) for s in c.sessions)
    gold_keys = {(g["item_id"], g["start"], g["end"], g["type"]) for s in c.sessions for g in s["gold"]}
    mask_keys = set()
    for a in c.annotations:
        assert items[a["item_id"]]["text"][a["start"]:a["end"]] == a["value"], a
        if a["action"] == "MASK":
            mask_keys.add((a["item_id"], a["start"], a["end"], a["type"]))
        else:
            assert not any(g[0] == a["item_id"] and a["start"] < g[2] and a["end"] > g[1] for g in gold_keys)
    assert gold_keys == mask_keys
    # Find every occurrence of longer injected secrets independently of insertion.
    # Short/default words are scoped by annotations, since they also appear as ordinary text.
    for a in c.annotations:
        if a["action"] != "MASK" or len(a["value"]) < 9:
            continue
        for item in items.values():
            for m in re.finditer(re.escape(a["value"]), item["text"]):
                assert any(g[0] == item["item_id"] and g[1] <= m.start() < m.end() <= g[2] for g in gold_keys), (item["item_id"], a)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    c = build()
    validate(c)
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "sessions.jsonl", c.sessions)
    write_jsonl(args.out / "annotations.jsonl", c.annotations)
    write_jsonl(args.out / "carrier_review.jsonl", c.bases)
    write_jsonl(args.out / "item_provenance.jsonl", c.operations)
    items = [i for s in c.sessions for i in s["items"]]
    masked = [a for a in c.annotations if a["action"] == "MASK"]
    negatives = [a for a in c.annotations if a["action"] == "KEEP"]
    lines = sum(i["text"].count("\n") + bool(i["text"] and not i["text"].endswith("\n")) for i in items)
    stats = {"version": VERSION, "reference_commit": REFERENCE_COMMIT,
        "sessions": len(c.sessions), "items": len(items), "gold_spans": len(masked),
        "annotated_negative_spans": len(negatives), "negative_only_sessions": sum(not s["gold"] for s in c.sessions),
        "lines": lines, "gold_per_1000_lines": len(masked) / lines * 1000,
        "gold_by_type": dict(Counter(a["type"] for a in masked)),
        "gold_by_channel": dict(Counter(a["channel"] for a in masked)),
        "gold_by_exposure": dict(Counter(a["exposure"] for a in masked)),
        "gold_by_reason": dict(Counter(a["reason"] for a in masked)),
        "unsupported_channel_gold": sum(a["channel"] not in ("stdout", "stderr") for a in masked),
        "dataset_sha256": hashlib.sha256((args.out / "sessions.jsonl").read_bytes()).hexdigest()}
    (args.out / "manifest.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review = ["# 최소 테스트셋 v0 — 전체 데이터 검토", "", "합성 입력이며 실제 Codex 실행 기록이 아닙니다. 모든 위치는 Python 문자열의 [start, end)입니다.", ""]
    for s in c.sessions:
        review += [f"## {s['session_id']} · {s['meta']['scenario']}", ""]
        for i in s["items"]:
            review += [f"### {i['item_id']} · {i['channel']} · {i['turn_id']}", "", "```text", i["text"].replace("\r", "␍"), "```", ""]
            for a in c.annotations:
                if a["item_id"] == i["item_id"]:
                    shown = a["value"].replace("\n", "\\n")
                    review.append(f"- **{a['action']}** [{a['start']}, {a['end']}) `{shown}` — {a['type']}; {a['reason']}; {a['exposure']}")
            review.append("")
    (args.out / "REVIEW.md").write_text("\n".join(review), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
