"""CredData(메타 CSV + 다운로드된 data/) -> 후보 레코드 v1 JSONL.

사용법:
  python creddata_to_v1.py --credata /path/to/CredData --out creddata_candidates_v1.jsonl
  python creddata_to_v1.py ... --chars-each-side 2000   # 문맥 창 크기 바꾸기 (값 앞뒤 글자 수, 기본 1000)

규칙
- chunk = 파일 1개. 위치 필드(span, line, context)는 location.py로 만든다 (위치 규칙은 location.py 참고).
- 파일은 newline=""로 읽는다. 그래야 \r\n이 \n으로 바뀌지 않고 원문 그대로 남는다.
- CredData 라벨은 우리 기준과 달라서 provisional=true로 옮긴다.
  T -> MASK/real_credential, F -> KEEP/not_secret, X -> KEEP/unknown(테스트 값 또는 플레이스홀더)
"""
import argparse, csv, glob, hashlib, json, os
from location import Chunk, build_location, DEFAULT_CHARS_EACH_SIDE

TYPE_RULES = [  # 위에서부터 먼저 맞는 것 (대소문자 무시)
    ("PRIVATE_KEY", ["private key", "pem", "jwk", "paserk", "nkey seed", "ssh"]),
    ("URL_CREDENTIAL", ["url credentials"]),
    ("CLOUD_CREDENTIAL", ["aws", "azure", "google", "gcp"]),
    ("PASSWORD", ["password"]),
    ("TOKEN", ["token", "bearer", "basic authorization", "auth", "paseto", "ntlm"]),
    ("API_KEY", ["api", "key"]),
    ("GENERIC_SECRET", ["secret", "salt", "nonce", "otp", "credential", "uuid", "seed"]),
]

def map_type(category: str) -> str:
    c = category.lower()
    for t, words in TYPE_RULES:
        if any(w in c for w in words):
            return t
    return "OTHER"

LABELS = {
    "T": ("MASK", "real_credential", "CredData T: 진짜처럼 생긴 비밀(테스트용 포함)"),
    "F": ("KEEP", "not_secret", "CredData F: 오탐"),
    "X": ("KEEP", "unknown", "CredData X: 테스트 값 또는 플레이스홀더"),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--credata", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars-each-side", type=int, default=DEFAULT_CHARS_EACH_SIDE)
    a = ap.parse_args()
    cache, n, miss = {}, 0, 0
    with open(a.out, "w", encoding="utf-8") as out:
        for meta_path in sorted(glob.glob(os.path.join(a.credata, "meta", "*.csv"))):
            with open(meta_path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    path = os.path.join(a.credata, r["FilePath"])
                    if path not in cache:
                        if len(cache) > 2000:
                            cache.clear()
                        try:
                            with open(path, encoding="utf-8", errors="replace", newline="") as f:
                                cache[path] = Chunk(f.read())
                        except FileNotFoundError:
                            cache[path] = None
                    if cache[path] is None:
                        miss += 1; continue
                    ch = cache[path]
                    lines = ch.lines
                    ls, le = int(r["LineStart"]), int(r["LineEnd"])
                    if ls < 1 or le > len(lines) or le < ls:
                        miss += 1; continue
                    vs = int(r["ValueStart"]) if r["ValueStart"] not in ("", "-1") else None
                    ve = int(r["ValueEnd"]) if r["ValueEnd"] not in ("", "-1") else None
                    # CredData의 ValueStart/End는 첫 줄 기준. 첫 줄 안에 들어올 때만 값 위치로 인정
                    has_value = vs is not None and ve is not None and 0 <= vs < ve <= len(lines[ls - 1])
                    loc = build_location(ch, ls, le, vs if has_value else None, ve if has_value else None,
                                         chars_each_side=a.chars_each_side)
                    value = loc["value"]
                    rel = r["FilePath"][len("data/"):] if r["FilePath"].startswith("data/") else r["FilePath"]
                    repo = r["RepoName"]
                    action, reason, note = LABELS[r["GroundTruth"]]
                    rec = {
                        "schema_version": "candidate-v1",
                        "candidate_id": f"creddata:{r['Id']}",
                        "group_id": f"creddata:{repo}",
                        "chunk_id": f"creddata:{rel}",
                        "source": {"dataset": "creddata", "agent": None, "channel": "file", "tool_name": None,
                                   "command": None, "file_path": rel, "session_id": None, "turn_index": None},
                        "granularity": "value" if has_value else "line",
                        "value": value,
                        "value_redacted": False,
                        "value_hash": ("sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()) if value else None,
                        "span": loc["span"],
                        "line": loc["line"],
                        "context": loc["context"],
                        "type": map_type(r["Category"]),
                        "detector": {"name": "creddata-meta", "rule_id": None, "raw_type": r["Category"], "score": None},
                        "label": {"action": action, "reason": reason, "source": "creddata", "provisional": True, "note": note},
                        "meta": {"creddata": {"id": r["Id"], "file_id": r["FileID"], "ground_truth": r["GroundTruth"],
                                              "cryptography_key": r["CryptographyKey"] or None,
                                              "predefined_pattern": r["PredefinedPattern"] or None},
                                 "line_crop_offset": loc["line_crop_offset"]},
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1
    print(f"written={n} missing={miss}")

if __name__ == "__main__":
    main()
