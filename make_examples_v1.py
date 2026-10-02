"""examples_v1.jsonl을 만든다. 예시마다 원문(chunk)을 직접 만들고 location.locate()로 위치·문맥을 채운다.
손으로 위치를 적지 않으므로 예시가 항상 현재 규칙(location.py)과 맞는다.

사용법: python make_examples_v1.py > examples_v1.jsonl
"""
import hashlib, json
from location import Chunk, locate


def sha(v):
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


def fill(rec, chunk, value, **kw):
    ch = Chunk(chunk)
    start = chunk.index(value)
    loc = locate(ch, start, start + len(value), **kw)
    rec.update(value=loc["value"], span=loc["span"], line=loc["line"], context=loc["context"])
    rec["meta"] = dict(rec.get("meta") or {}, line_crop_offset=loc["line_crop_offset"])
    return rec


def base(cid, gid, chunk_id, source, typ, detector, label, meta=None):
    return {"schema_version": "candidate-v1", "candidate_id": cid, "group_id": gid, "chunk_id": chunk_id,
            "source": source, "granularity": "value", "value": None, "value_redacted": False, "value_hash": None,
            "span": None, "line": None, "context": None, "type": typ, "detector": detector, "label": label,
            "meta": meta or {}}


# 예시 1: .env 파일을 cat한 tool 출력 속 진짜 비밀번호 → MASK
env = "DB_HOST=db-prod-2\nDB_USER=deploy\nDB_PASSWORD=Tq7!mZ2p#Lw9\nLOG_LEVEL=info\n"
ex1 = base("trace:s001:t04:c1", "task:env-setup-01", "trace:s001:t04",
           {"dataset": "agent_trace", "agent": "codex", "channel": "tool_output", "tool_name": "Bash",
            "command": "cat config/prod.env", "file_path": "config/prod.env", "session_id": "s001", "turn_index": 4},
           "PASSWORD", {"name": "gitleaks-rules", "rule_id": "password-assignment", "raw_type": "password", "score": None},
           {"action": "MASK", "reason": "real_credential", "source": "injection", "provisional": False, "note": None})
fill(ex1, env, "Tq7!mZ2p#Lw9")
ex1["value_hash"] = sha(ex1["value"])

# 예시 2: 실시간 로그 — 사용자 프롬프트 속 비밀번호. 값은 남기지 않고 해시만 남긴다 (원문도 █로 가린 상태로 저장)
prompt = "DB 비번은 ██████████ 이야. 접속 에러 좀 고쳐줘"
ex2 = base("live:s777:t00:c1", "live:s777", "live:s777:t00",
           {"dataset": "live", "agent": "codex", "channel": "user_prompt", "tool_name": None, "command": None,
            "file_path": None, "session_id": "s777", "turn_index": 0},
           "PASSWORD", {"name": "ko-keyword-rules", "rule_id": "ko-password-is", "raw_type": None, "score": None},
           None, {"note": "실시간 로그 예시: 값은 남기지 않고 해시만 남김"})
fill(ex2, prompt, "██████████")
ex2.update(value=None, value_redacted=True,
           value_hash="sha256:ebf286784205d662e26bc8ef4fb70e1316ab665aa1ffd32ceb05ea6d6486954a")

# 예시 3: package-lock.json을 sed로 120줄 출력 → 무결성 해시는 비밀 아님 → KEEP
INTEGRITY = "sha512-2lfu57JtzctfIrcGMz992hyLlByuzgIk3tYCrb1Rj5xLpA+JNDnHs2hW1hHbKHRXYbHd1Lx9e7L4vT0sVbXQ=="
PKGS = [("@ampproject/remapping", "2.3.0", "Apache-2.0"), ("@babel/code-frame", "7.27.1", "MIT"),
        ("@babel/compat-data", "7.28.6", "MIT"), ("@babel/core", "7.28.6", "MIT"),
        ("@babel/generator", "7.28.6", "MIT"), ("@babel/helper-compilation-targets", "7.27.2", "MIT"),
        ("@babel/helper-globals", "7.28.0", "MIT"), ("@babel/helper-module-imports", "7.27.1", "MIT"),
        ("@babel/helper-module-transforms", "7.28.3", "MIT"), ("@babel/helper-string-parser", "7.27.1", "MIT"),
        ("@babel/helper-validator-identifier", "7.27.1", "MIT"), ("@babel/helper-validator-option", "7.27.1", "MIT")]
lines = ["{", '  "name": "demo-app",', '  "version": "1.0.0",', '  "lockfileVersion": 3,', '  "requires": true,',
         '  "packages": {', '    "": {', '      "name": "demo-app",', '      "version": "1.0.0",',
         '      "devDependencies": {', '        "@babel/core": "^7.28.0",', '        "jest": "^30.0.0"', "      }", "    },"]
for i, (name, ver, lic) in enumerate(PKGS):
    short = name.split("/")[-1]
    fake = hashlib.sha512(name.encode()).hexdigest()[:86]
    lines += [f'    "node_modules/{name}": {{', f'      "version": "{ver}",',
              f'      "resolved": "https://registry.npmjs.org/{name}/-/{short}-{ver}.tgz",',
              f'      "integrity": "{INTEGRITY if name == "@babel/core" else "sha512-" + fake + "=="}",',
              '      "dev": true,', f'      "license": "{lic}",', '      "engines": {', '        "node": ">=6.9.0"',
              "      }", "    },"]
lock = "\n".join(lines[:120]) + "\n"
ex3 = base("trace:s002:t02:c7", "task:dep-bump-03", "trace:s002:t02",
           {"dataset": "agent_trace", "agent": "codex", "channel": "tool_output", "tool_name": "Bash",
            "command": "sed -n '1,120p' package-lock.json", "file_path": "package-lock.json",
            "session_id": "s002", "turn_index": 2},
           "GENERIC_SECRET", {"name": "detect-secrets", "rule_id": "Base64HighEntropyString",
                              "raw_type": "Base64 High Entropy String", "score": None},
           {"action": "KEEP", "reason": "non_secret_id", "source": "human", "provisional": False, "note": "lockfile 무결성 해시"})
fill(ex3, lock, INTEGRITY)
ex3["value_hash"] = sha(ex3["value"])

for r in (ex1, ex2, ex3):
    print(json.dumps(r, ensure_ascii=False))
