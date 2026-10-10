"""Collect credential candidates of a dataset whose gold is set by review, and record the verdicts.

Some sources have no labels of their own (shared agent trajectories). Their gold comes from a review: every
distinct value that a detector or one of the regular expressions below flags is judged once against the metric 1
definition (metric-1/README.md, "정답의 정의"), and the converter turns verdict "credential" into gold.

Run from the repository root:
  # 1. candidates, from evaluator runs over the dataset (their per_edit.jsonl) and the regexes below
  python metric-1/scripts/review_candidates.py collect metric-1/data_test/sessions_from_X.jsonl \\
      --runs metric-1/results/review/<credsweeper run> metric-1/results/review/<gitleaks run> --out metric-1/results/review/X.worksheet.jsonl
  # 2. fill in "verdict" (credential | not_credential), "reason" and, for credentials, "type"
  # 3. record the verdicts without the values
  python metric-1/scripts/review_candidates.py apply metric-1/results/review/X.worksheet.jsonl --out metric-1/reviews/X.jsonl

The worksheet holds the values with their context: keep it under metric-1/results/ (ignored by git). The review file holds,
per value, its SHA-256, one place it occurs (session_id, item_id, start, end), type, verdict, reason and which
detectors found it; the converter reads the value back from that place.

collect pre-fills verdicts that follow mechanically from the definition and from the privesc and CredData
conversions (placeholders, references, numbers, values shorter than 9 characters); the rest is left empty.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

MIN_VALUE_LEN = 9
REVIEWS_DIR = Path(__file__).resolve().parents[1] / "reviews"
KEY = r"(?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|auth|credential|client[_-]?secret)"
REGEXES = {
    "key_value": re.compile(rf"(?i)[\w.-]*{KEY}[\w.-]*[\"']?\s*(?:=|:|=>)\s*[\"']?(?P<value>[^\s\"',;)}}\]]{{6,}})"),
    "bearer": re.compile(r"(?i)\b(?:bearer|basic|token)\s+(?P<value>[A-Za-z0-9._~+/=-]{16,})"),
    "url_credentials": re.compile(r"[a-z][a-z0-9+.-]*://[^\s:/@]+:(?P<value>[^\s@/]{3,})@"),
    "cli_password": re.compile(r"(?:\s-p|--password[= ]|sshpass\s+-p\s*)[\"']?(?P<value>[^\s\"']{6,})"),
    "provider_prefix": re.compile(r"(?P<value>\b(?:gh[pousr]_[A-Za-z0-9_-]{8,}|github_pat_[A-Za-z0-9_]{20,}|"
                                  r"sk-[A-Za-z0-9_-]{16,}|sk_(?:live|test)_[A-Za-z0-9]{10,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
                                  r"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}|ya29\.[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|"
                                  r"glpat-[A-Za-z0-9_-]{16,}|npm_[A-Za-z0-9]{30,}))"),
    "jwt": re.compile(r"(?P<value>\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"),
    "pem": re.compile(r"(?P<value>-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$))", re.S),
}
PLACEHOLDER = re.compile(r"x{3}|X{3}|\*{3}|<[^>]*>|\{\{|\$\{|redacted|your[_-]|_here\b|example|dummy|placeholder|"
                         r"\.\.\.|changeme|<|>", re.I)
REFERENCE = re.compile(r"^(?:\$\w|\$\(|self\.|os\.|process\.env|env\.|config\.|settings\.|req\.|request\.|args\.|"
                       r"\{|\[|%\()|^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\)?$")
NUMBER = re.compile(r"^[\d\s.,;:^~<>=+*/-]+$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$|^[A-Z][A-Z0-9_]*$|^[A-Z][a-z]+$")
CODE = re.compile(r"^[A-Za-z_][\w.]*[(\[]|^\w+\[[\w.]+$|^[\w.]+\(\w*$|\)\s*$")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SECRET_WORD = re.compile(r"(?i)secret|passw|pwd|token|api.?key|auth|credential|private")
ARN = re.compile(r"^(?:arn:aws[\w-]*:|[a-z]{2}-[a-z]+-\d:\d+:)")
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
PATH = re.compile(r"^(?:/|\./|~/)|/workspace/")


def load_review(name: str) -> dict[tuple[str, str], dict]:
    """metric-1/reviews/<name>.jsonl keyed by (session_id, value SHA-256): one value can be judged in several sessions."""
    path = REVIEWS_DIR / f"{name}.jsonl"
    if not path.is_file():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    return {(r["where"][0], r["sha256"]): r for r in rows}


def apply_review(sessions: list[dict], review: dict[tuple[str, str], dict], name: str):
    """Gold and label rows from a review file (see review_candidates.py). Each verdict names one place the value
    occurs; the value is read back from there and checked against its SHA-256, so the file stores no values. A
    value judged a credential is gold at every occurrence in that session."""
    texts = {(s["session_id"], i["item_id"]): i["text"] for s in sessions for i in s["items"]}
    channels = {(s["session_id"], i["item_id"]): i["channel"] for s in sessions for i in s["items"]}
    items_of_session: dict[str, list[int]] = {}
    for sid, iid in texts:
        items_of_session.setdefault(sid, []).append(iid)
    per_item: dict[tuple[str, int], list[tuple[int, int, str, dict]]] = {}
    stats = Counter()
    for r in review.values():
        sid, iid, a, b = r["where"]
        value = texts.get((sid, iid), "")[a:b]
        if sha256(value) != r["sha256"]:
            raise ValueError(f"review {r['sha256'][:12]} no longer matches {sid}/{iid}; regenerate the review for {name}")
        for item_id in items_of_session[sid]:
            for m in re.finditer(re.escape(value), texts[(sid, item_id)]):
                per_item.setdefault((sid, item_id), []).append((m.start(), m.end(), r["type"], r))
        stats[f"reviewed_{r['verdict']}"] += 1
    gold, labels = [], []
    order = {key: n for n, key in enumerate(texts)}
    for key in sorted(per_item, key=order.__getitem__):
        taken: list[tuple[int, int, str]] = []
        for a, b, kind, r in sorted(per_item[key], key=lambda x: (-(x[1] - x[0]), x[0])):
            labels.append({"session_id": key[0], "item_id": key[1], "start": a, "end": b,
                           "gold": r["verdict"] == "credential", "verdict": r["verdict"], "reason": r["reason"],
                           "found_by": r.get("found_by", [])})
            if r["verdict"] == "credential" and not any(x < b and a < y for x, y, _ in taken):
                taken.append((a, b, kind))
        for span_id, (a, b, kind) in enumerate(sorted(taken)):
            gold.append({"session_id": key[0], "item_id": key[1], "span_id": span_id,
                         "span": {"start": a, "end": b, "type": kind}})
            stats[f"gold_{kind}_{channels[key]}"] += 1
    labels.sort(key=lambda r: (r["session_id"], r["item_id"], r["start"]))
    return gold, labels, stats


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def suggest(value: str, before: str = "") -> tuple[str | None, str | None]:
    """A verdict that follows mechanically, or (None, None) when a person has to judge. before: text right before
    the value, which decides whether a UUID sits in a secret's place."""
    if UUID.match(value) and not SECRET_WORD.search(before[-60:]):
        return "not_credential", "UUID outside a secret's place (request id, resource id)"
    if CODE.search(value):
        return "not_credential", "code expression"
    if ARN.match(value) or EMAIL.match(value) or PATH.search(value):
        return "not_credential", "resource name, email address or path"
    if PLACEHOLDER.search(value):
        return "not_credential", "placeholder or redaction mark"
    if REFERENCE.search(value):
        return "not_credential", "variable or attribute reference"
    if NUMBER.match(value):
        return "not_credential", "number, version or time format"
    if len(value) < MIN_VALUE_LEN:
        return "not_credential", "shorter than 9 characters (privesc, CredData)"
    if IDENTIFIER.match(value):
        return "not_credential", "plain identifier or word"
    return None, None


def guess_type(value: str, context: str) -> str:
    if "PRIVATE KEY" in value:
        return "PRIVATE_KEY"
    if value.startswith("AKIA"):
        return "ACCESS_KEY"
    if value.startswith("eyJ") or re.search(r"(?i)token|bearer|session|cookie", context[-60:]):
        return "TOKEN"
    if re.search(r"(?i)pass|pwd", context[-60:]):
        return "PASSWORD"
    return "SECRET"


def trimmed(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a] in " \t\r\n\"'`":
        a += 1
    while b > a and text[b - 1] in " \t\r\n\"'`,;.":
        b -= 1
    return a, b


def cmd_collect(args):
    sessions = read_jsonl(Path(args.sessions))
    texts = {(s["session_id"], i["item_id"]): i["text"] for s in sessions for i in s["items"]}
    found: dict[tuple[str, str], dict] = {}

    def add(sid, iid, a, b, by):
        a, b = trimmed(texts[(sid, iid)], a, b)
        value = texts[(sid, iid)][a:b]
        if not value:
            return
        row = found.setdefault((sid, value), {"session_id": sid, "value": value, "where": [sid, iid, a, b],
                                               "found_by": set(), "occurrences": 0})
        row["found_by"].add(by)

    for run in args.runs:
        name = Path(run).name.split("_", 1)[-1]
        for e in read_jsonl(Path(run) / "per_edit.jsonl"):
            add(e["session_id"], e["item_id"], e["start"], e["end"], name)
    for (sid, iid), text in texts.items():
        for by, regex in REGEXES.items():
            for m in regex.finditer(text):
                add(sid, iid, m.start("value"), m.end("value"), f"regex:{by}")
    session_texts: dict[str, list[str]] = defaultdict(list)
    for (sid, _), text in texts.items():
        session_texts[sid].append(text)
    joined = {sid: "\n".join(parts) for sid, parts in session_texts.items()}
    rows = []
    for (sid, value), row in sorted(found.items()):
        session_text = joined[sid]
        sid_, iid, a, b = row["where"]
        context = texts[(sid_, iid)][max(0, a - 80):b + 40]
        verdict, reason = suggest(value, texts[(sid_, iid)][max(0, a - 80):a])
        rows.append({"session_id": sid, "value": value, "where": row["where"], "found_by": sorted(row["found_by"]),
                     "occurrences": session_text.count(value), "context": context,
                     "suggested": verdict is not None, "verdict": verdict, "reason": reason,
                     "type": guess_type(value, texts[(sid_, iid)][max(0, a - 80):a])})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    open_rows = sum(r["verdict"] is None for r in rows)
    print(f"{len(rows)} candidate value(s), {open_rows} to judge by hand -> {out}")


def cmd_apply(args):
    rows = read_jsonl(Path(args.worksheet))
    missing = [r["value"][:30] for r in rows if r["verdict"] not in ("credential", "not_credential")]
    if missing:
        raise SystemExit(f"{len(missing)} row(s) without a verdict, e.g. {missing[:3]}")
    out_rows, seen = [], set()
    for r in rows:
        key = (r["session_id"], sha256(r["value"]))
        if key in seen:
            continue
        seen.add(key)
        out_rows.append({"sha256": key[1], "where": r["where"], "length": len(r["value"]),
                         "type": r["type"] if r["verdict"] == "credential" else None, "verdict": r["verdict"],
                         "reason": r["reason"], "reviewed_by": r.get("reviewed_by", "manual"),
                         "found_by": r["found_by"], "sessions": [r["session_id"]]})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows), encoding="utf-8")
    counts = defaultdict(int)
    for r in out_rows:
        counts[r["verdict"]] += 1
    print(f"{len(out_rows)} verdict(s) {dict(counts)} -> {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect")
    p.add_argument("sessions")
    p.add_argument("--runs", nargs="*", default=[], help="evaluator run folders (per_edit.jsonl) over the same file")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser("apply")
    p.add_argument("worksheet")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_apply)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
