"""Local web page for reviewing CredData X/F rows against the metric-1 label: a working credential or not (CRED or NOT_CRED).

Run from the repository root, then open the printed URL:
  python metric-1/manual_review/review_creddata.py --creddata ../CredData

Rows are grouped by value, so one decision covers every X/F occurrence of the same string; a row can
override its group or correct its span. Every change is saved to metric-1/creddata_review.jsonl
(CredData ids and decisions only, no file contents). "완료" saves and regenerates
data_test/sessions_from_CredData.jsonl and data_answer/gold_from_CredData.jsonl with
metric-1/scripts/convert_creddata.py, so CRED rows become gold. Unreviewed rows keep CredData's verdict (negative).
Serves on 127.0.0.1 only: the page shows CredData file contents, which are not ours to publish.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import re
import sys
import tempfile

OUT = Path(__file__).resolve().parents[1]  # metric-1/
sys.path.insert(0, str(OUT / "scripts"))
from convert_creddata import REPO_ROOT, REVIEW_PATH, convert, load_review, write_outputs

PAGE = Path(__file__).with_name("review_creddata.html")
CONTEXT_SHOWN = 2  # lines shown above and below the labeled line
LINE_SHOWN = 400  # longer lines are cut to a window around the value
NEAR_LINE = 160
PLACEHOLDER = re.compile(
    r"^(<[^<>]*>|\$\{[^}]*\}|\{\{.*\}\}|%[A-Za-z_]+%|#+[A-Za-z_]+#+|\$[A-Za-z_]\w*|\*{3,}|x{3,}|\.{3,})$"
    r"|(^|[_\-\s<*])your([_\-\s]|$)|^(insert|put|enter|replace|fill|add|create)[_\- ]|_here$|^change[_\-]?this",
    re.I)


def cut(line: str, start: int, end: int) -> tuple[str, int]:
    """(shown part of line, offset of the shown part in line)."""
    if len(line) <= LINE_SHOWN:
        return line, 0
    a = max(0, start - (LINE_SHOWN - (end - start)) // 2)
    return line[a:max(end, a + LINE_SHOWN)], a


def build_payload(creddata: Path, context: int) -> dict:
    # Original CredData positions (no review applied), so a corrected span can always be reverted.
    sessions, _, labels, _ = convert(creddata, context, review_path=Path(os.devnull))
    items = {(s["session_id"], it["item_id"]): (it["text"], s["meta"]) for s in sessions for it in s["items"]}
    rows, groups = {}, defaultdict(list)
    for r in labels:
        if not r["reviewable"]:
            continue
        text, meta = items[(r["session_id"], r["item_id"])]
        ls = text.rfind("\n", 0, r["start"]) + 1
        le = text.find("\n", r["start"])
        line = text[ls:le if le >= 0 else len(text)]
        s, e = r["start"] - ls, r["end"] - ls
        shown, off = cut(line, s, e)
        before = text[:ls].split("\n")[-1 - CONTEXT_SHOWN:-1] if ls else []
        after = text[le + 1:].split("\n")[:CONTEXT_SHOWN] if le >= 0 else []
        value = text[r["start"]:r["end"]]
        q = line[s - 1:s] if s else ""
        rows[r["creddata_id"]] = {
            "truth": r["ground_truth"], "cat": r["category"], "type": r["mapped_type"],
            "file": meta["creddata_file"],
            "ln": meta["item_lines"][r["item_id"]][0] + text.count("\n", 0, ls),
            "line": shown, "off": off, "len": len(line), "s": s, "e": e,
            "pre": [x[:NEAR_LINE] for x in before], "post": [x[:NEAR_LINE] for x in after],
            "quoted": bool(q) and q in "\"'`" and line[e:e + 1] == q,
        }
        groups[value].append(r["creddata_id"])
    out = []
    for value, ids in groups.items():
        # T values are obfuscated by CredData, so they cannot be matched against X/F values here.
        tags = ["placeholder"] if PLACEHOLDER.search(value) else []
        out.append({"v": value, "ids": sorted(ids, key=int), "tags": tags,
                    "sugg": "NOT_CRED" if tags else None})
    out.sort(key=lambda g: (-len(g["ids"]), g["v"]))
    return {"groups": out, "rows": rows}


def save_review(decisions: dict[str, dict], path: Path, known: dict[str, dict]):
    lines = []
    for cid in sorted(decisions, key=int):
        d = decisions[cid]
        if cid not in known:
            raise ValueError(f"unknown or non-reviewable creddata_id {cid}")
        rec = {"creddata_id": cid, "action": d["action"], "scope": d["scope"]}
        if d.get("value_start") is not None:
            rec["value_start"], rec["value_end"] = int(d["value_start"]), int(d["value_end"])
            if not 0 <= rec["value_start"] < rec["value_end"] <= known[cid]["len"]:
                raise ValueError(f"span of {cid} out of its line")
        lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write("".join(lines))
    try:
        load_review(Path(f.name))  # same validation the converter applies, before the saved file is replaced
    except Exception:
        os.unlink(f.name)
        raise
    os.replace(f.name, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--creddata", type=Path, default=REPO_ROOT.parent / "CredData")
    parser.add_argument("--context-lines", type=int, default=10, help="must match convert_creddata.py")
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print("reading CredData ...")
    payload = build_payload(args.creddata, args.context_lines)
    known = payload["rows"]
    stale = sorted(set(load_review(args.review)) - set(known), key=int)
    if stale:
        raise SystemExit(f"{args.review.name}: {len(stale)} id(s) are not reviewable rows: {stale[:5]}")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def send(self, code: int, body: bytes, kind: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def reply(self, obj, code: int = 200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            if self.path == "/":
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/data":
                self.send(200, data)
            elif self.path == "/review":
                self.reply(load_review(args.review))
            else:
                self.send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"):
                return self.send(403, b"forbidden", "text/plain")
            if self.path not in ("/save", "/complete"):
                return self.send(404, b"not found", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                save_review(body["decisions"], args.review, known)
                if self.path == "/save":
                    return self.reply({"saved": len(body["decisions"])})
                stats = write_outputs(args.creddata, args.context_lines, OUT, args.review)
                self.reply({"saved": len(body["decisions"]), "stats": stats})
            except Exception as e:  # report to the page instead of dropping the connection
                self.reply({"error": f"{type(e).__name__}: {e}"}, 400)

        def log_message(self, fmt, *a):
            if self.command == "POST":
                super().log_message(fmt, *a)

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"{len(payload['groups'])} values, {len(known)} rows -> http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
