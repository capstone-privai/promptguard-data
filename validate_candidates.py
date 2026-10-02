"""후보 레코드 v1 검증기. 스키마 + 스키마로 못 잡는 규칙(위치가 실제 값과 맞는지 등)을 확인한다.

사용법:
  python validate_candidates.py candidate_v1.schema.json creddata_candidates_v1.jsonl
  python validate_candidates.py candidate_v1.schema.json creddata_candidates_v1.jsonl --creddata /path/to/CredData
    --creddata를 주면 원본 파일(chunk)을 다시 읽어서 span·line이 원문과 맞는지까지 확인한다.
"""
import argparse, json, os, collections
from jsonschema import Draft202012Validator
from location import check_span


def load_creddata_chunk(root, chunk_id, cache):
    """chunk_id 'creddata:<path>' → 원본 파일 str (location.py 규칙 1과 같은 방식으로 읽음)."""
    if not chunk_id or not chunk_id.startswith("creddata:"):
        return None
    path = os.path.join(root, "data", chunk_id[len("creddata:"):])
    if path not in cache:
        if len(cache) > 2000:
            cache.clear()
        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as f:
                cache[path] = f.read()
        except FileNotFoundError:
            cache[path] = None
    return cache[path]


def record_problems(rec):
    """chunk 없이도 확인할 수 있는 규칙."""
    problems = []
    ln = rec.get("line") or {}
    vs, ve = ln.get("value_start"), ln.get("value_end")
    if vs is not None and ve is not None:
        if not (0 <= vs < ve <= len(ln.get("text", ""))):
            problems.append("line.value_start/end가 line.text 범위를 벗어남")
        elif rec.get("value") is not None and ln["text"][vs:ve] != rec["value"]:
            problems.append("line.text[value_start:value_end] != value")
    ctx = rec.get("context") or {}
    n = ctx.get("chars_each_side")
    if n and vs is not None and ve is not None and "before" in ctx:
        before_len = len("\n".join(ctx["before"])) + 1 if ctx["before"] else 0
        after_len = len("\n".join(ctx["after"])) + 1 if ctx["after"] else 0
        if before_len + vs > n:
            problems.append("값 앞 문맥이 chars_each_side보다 김")
        if (len(ln.get("text", "")) - ve) + after_len > n:
            problems.append("값 뒤 문맥이 chars_each_side보다 김")
    sp = rec.get("span")
    if sp:
        if sp["end"] <= sp["start"]:
            problems.append("span.end <= span.start")
        if rec.get("value") is not None and sp["end"] - sp["start"] != len(rec["value"]):
            problems.append("span 길이 != value 길이")
        if vs is not None and ve is not None and sp["end"] - sp["start"] != ve - vs:
            problems.append("span 길이 != line.value_end - line.value_start")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("schema")
    ap.add_argument("data")
    ap.add_argument("--creddata", help="CredData 루트. 주면 원본 파일과 대조한다")
    ap.add_argument("--max-report", type=int, default=20)
    a = ap.parse_args()

    v = Draft202012Validator(json.load(open(a.schema, encoding="utf-8")))
    errs, seen, n, shown, chunk_cache, checked = collections.Counter(), set(), 0, 0, {}, 0
    for i, line in enumerate(open(a.data, encoding="utf-8"), 1):
        rec = json.loads(line); n += 1
        problems = [e.message for e in v.iter_errors(rec)]
        cid = rec.get("candidate_id")
        if cid in seen:
            problems.append("candidate_id 중복")
        seen.add(cid)
        problems += record_problems(rec)
        if a.creddata:
            chunk = load_creddata_chunk(a.creddata, rec.get("chunk_id"), chunk_cache)
            if chunk is not None:
                problems += check_span(chunk, rec); checked += 1
        for p in problems:
            errs[p[:80]] += 1
            if shown < a.max_report:
                print(f"line {i} ({cid}): {p}"); shown += 1
    print(f"records={n} invalid_messages={sum(errs.values())}" + (f" chunk_checked={checked}" if a.creddata else ""))
    for m, c in errs.most_common(10):
        print(f"  {c:6d}  {m}")
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
