"""Convert Samsung CredData (meta/*.csv + data/ from its download_data.py) into our session format.

Run from the repository root, after building CredData's data/ (see metric-1/README_CredData.md):
  python metric-1/scripts/convert_creddata.py --creddata ../CredData

EVALUATION ONLY. origin=external, allowed_use=[rule_eval, ml_eval]: never train on this.

Writes, under --out (default metric-1/):
  data_test/sessions_from_CredData.jsonl  one session per labeled file; each item is a window of the file
                                (labeled lines +- --context-lines, overlapping windows merged), channel tool_output
  data_answer/gold_from_CredData.jsonl  CredData T rows as gold spans (same schema as gold.jsonl)
  labels_from_CredData.jsonl    every CredData row (T/F/X) mapped to item offsets, for analysis

Gold is CredData's own verdict: T rows only. X and F rows stay in the sessions as negatives.

Conversion rules:
  - Lines are split the way CredData does: \\r\\n and \\r become \\n, then split on \\n.
    Offsets are Python code points into item text, like the rest of metric-1.
  - Value position: ValueStart on LineStart to ValueEnd on LineEnd. No ValueEnd means end of LineEnd;
    no ValueStart (whole-line PEM markup) means LineStart..LineEnd. Surrounding whitespace is trimmed.
  - Overlapping T spans: composite "... Multi" rows that overlap their component rows are dropped,
    any remaining overlaps are merged into their union, typed after the longest row.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "CredData"

PRIVATE_KEY_CATEGORIES = {"PEM Private Key", "BASE64 Private Key", "BASE64 encoded PEM Private Key",
                          "JWK", "PASERK Keys", "NKEY Seed"}
ACCESS_KEY_CATEGORIES = {"AWS Client ID", "Alibaba Access Key ID", "Tencent WeChat API App ID",
                         "AWS S3 Bucket", "Firebase Domain"}


def gold_type(category: str, crypto: str) -> str:
    """Map a CredData Category (colon-joined CredSweeper rules) to one of our five gold types."""
    cats = category.split(":")
    if crypto == "Private" or any(c in PRIVATE_KEY_CATEGORIES for c in cats):
        return "PRIVATE_KEY"
    if "URL Credentials" in cats:
        return "SECRET"  # full connection string, same as the built-in corpus
    if any("Password" in c for c in cats):
        return "PASSWORD"
    if any(c in ACCESS_KEY_CATEGORIES for c in cats):
        return "ACCESS_KEY"
    if any("Token" in c or "Authorization" in c or c == "Auth" for c in cats):
        return "TOKEN"
    return "SECRET"


@dataclass
class Row:
    raw: dict
    first: int  # 1-based line numbers
    last: int
    start_col: int | None
    end_col: int | None

    @property
    def truth(self) -> str:
        return self.raw["GroundTruth"]


def parse_row(r: dict) -> Row:
    col = lambda v: int(v) if v not in ("", "-1") else None
    return Row(r, int(r["LineStart"]), int(r["LineEnd"]), col(r["ValueStart"]), col(r["ValueEnd"]))


def read_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # trailing newline, not an extra line
    return lines


def windows(rows: list[Row], n_lines: int, context: int) -> list[tuple[int, int]]:
    ranges = sorted((max(1, r.first - context), min(n_lines, r.last + context)) for r in rows)
    merged: list[list[int]] = []
    for a, b in ranges:
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def locate(row: Row, lines: list[str], line_offset: dict[int, int]) -> tuple[int, int]:
    """Row -> trimmed [start, end) in the item text whose line offsets are given."""
    line_end = line_offset[row.last] + len(lines[row.last - 1])
    if row.start_col is None:  # whole-line markup
        return line_offset[row.first], line_end
    end = line_offset[row.last] + row.end_col if row.end_col is not None else line_end
    return line_offset[row.first] + row.start_col, end


def trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def resolve_overlaps(spans: list[dict], stats: Counter) -> list[dict]:
    """spans: {start, end, type, category}. Returns non-overlapping spans sorted by start."""
    def overlaps(a, b):
        return a["start"] < b["end"] and b["start"] < a["end"]
    spans = [{**s, "length": s["end"] - s["start"]} for s in spans]
    multi = [s for s in spans if "Multi" in s["category"]]
    rest = [s for s in spans if "Multi" not in s["category"]]
    for s in multi:
        if any(overlaps(s, o) for o in rest):
            stats["dropped_multi_overlapping_components"] += 1
        else:
            rest.append(s)
    rest.sort(key=lambda s: (s["start"], -s["end"]))
    merged: list[dict] = []
    for s in rest:
        if merged and s["start"] < merged[-1]["end"]:
            m = merged[-1]
            stats["merged_overlapping"] += 1
            longest = max((m, s), key=lambda x: x["length"])
            merged[-1] = {**longest, "start": m["start"], "end": max(m["end"], s["end"])}
        else:
            merged.append(s)
    return merged


def convert(creddata: Path, context: int):
    commit = subprocess.run(["git", "-C", str(creddata), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    by_file: dict[str, list[Row]] = defaultdict(list)
    for meta_path in sorted((creddata / "meta").glob("*.csv")):
        with meta_path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                by_file[r["FilePath"]].append(parse_row(r))

    sessions, gold, labels = [], [], []
    stats = Counter()
    for file_path in sorted(by_file):
        rows = sorted(by_file[file_path], key=lambda r: (r.first, r.start_col or 0))
        path = creddata / file_path
        if not path.is_file():
            raise FileNotFoundError(f"{path} is missing; run CredData's download_data.py first")
        lines = read_lines(path)
        repo, file_id = rows[0].raw["RepoName"], rows[0].raw["FileID"]
        session_id = f"creddata-{repo}-{file_id}"
        items, item_lines = [], []
        for item_id, (a, b) in enumerate(windows(rows, len(lines), context)):
            text_lines = lines[a - 1:b]
            text = "".join(line + "\n" for line in text_lines)
            line_offset, pos = {}, 0
            for n, line in zip(range(a, b + 1), text_lines):
                line_offset[n] = pos
                pos += len(line) + 1
            spans = []
            for row in (r for r in rows if a <= r.first and r.last <= b):
                start, end = trim(text, *locate(row, lines, line_offset))
                if start >= end:
                    stats[f"empty_{row.truth}"] += 1
                    continue
                kind = gold_type(row.raw["Category"], row.raw["CryptographyKey"])
                labels.append({"session_id": session_id, "item_id": item_id, "start": start, "end": end,
                               "ground_truth": row.truth, "category": row.raw["Category"],
                               "mapped_type": kind, "creddata_id": row.raw["Id"]})
                stats[f"rows_{row.truth}"] += 1
                if row.truth == "T":
                    spans.append({"start": start, "end": end, "type": kind, "category": row.raw["Category"]})
            for span_id, s in enumerate(resolve_overlaps(spans, stats)):
                gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id,
                             "span": {"start": s["start"], "end": s["end"], "type": s["type"]}})
            items.append({"item_id": item_id, "turn_id": "t0", "channel": "tool_output", "text": text})
            item_lines.append([a, b])
        sessions.append({"session_id": session_id, "items": items, "meta": {
            "dataset_version": f"creddata@{commit[:12]}", "source": "creddata",
            "origin": "external", "allowed_use": ALLOWED_USE["external"],
            "group_id": f"creddata-{repo}",
            "creddata_commit": commit, "creddata_file": file_path, "item_lines": item_lines,
            "context_lines": context,
            "license": f"each file keeps its source repository's license; see CredData data/{repo}/",
        }})
    return sessions, gold, labels, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--creddata", type=Path, default=REPO_ROOT.parent / "CredData",
                        help="CredData checkout with data/ built by its download_data.py")
    parser.add_argument("--context-lines", type=int, default=10, help="lines kept on each side of a labeled line")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.creddata, args.context_lines, args.out), indent=2))


def write_outputs(creddata: Path, context: int, out: Path) -> dict:
    sessions, gold, labels, stats = convert(creddata, context)
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{NAME}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{NAME}.jsonl", gold)
    write_jsonl(out / f"labels_from_{NAME}.jsonl", labels)
    return {"sessions": len(sessions), "items": sum(len(s["items"]) for s in sessions),
            "gold_spans": len(gold), "gold_by_type": dict(Counter(g["span"]["type"] for g in gold)),
            **dict(sorted(stats.items()))}


if __name__ == "__main__":
    main()
