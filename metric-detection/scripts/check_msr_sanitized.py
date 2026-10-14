"""List the positive rows of the sanitized MSR package whose fake does not match the original's format.

Compares the original package with the output of sanitize_msr_issues.py, row by row, and writes the rows to
leave out (file, data row, reasons; no values). A positive row is listed when
- format: a token of its candidate string differs from the original in a format fingerprint (length, base64
  form and decoded kind, Kingfisher v1 rule set, checksum, JSON keys, JWT/JOSE layout, DER tag tree, SSH key
  type, vendor prefix, whitespace layout);
- text: where the original value stood in the row's text, the text does not hold the candidate's fake;
- length: a text field changed length (an escaped variant);
- leftover: the sanitizer's verification left an original piece in the row (SANITIZE_REPORT.json).

usage: python check_msr_sanitized.py --src <extracted package dir> --out <sanitized dir> \
           --kingfisher ../kingfisher-v1 --list ../msr_excluded_rows.csv [--drop]

--drop rewrites the sanitized CSVs without the listed rows. To regenerate without them later, pass the list to
sanitize_msr_issues.py --exclude-rows. Fakes are random, so a new run can mismatch on other rows: run this
check again on the new output.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import struct
import sys
from pathlib import Path

import fmtkeep as F
import sanitize_msr_issues as S

csv.field_size_limit(sys.maxsize)


def der_tags(b, i=0, end=None, depth=0):
    out = []
    try:
        for tag, _, c, e in F.der_parse(b, i, end):
            out.append((depth, tag))
            if tag & 0x20:
                out += der_tags(b, c, e, depth + 1)
    except ValueError:
        out.append(("partial",))
    return out


def fingerprint(tok: str, oracle: F.Oracle) -> dict:
    """Format properties of one token that a faithful fake keeps."""
    d = F.b64_decode(tok)
    fp = {"len": len(tok), "b64": d is not None, "rules": oracle.match(tok), "checksum": F.checksum_valid(tok),
          "prefix": next((p for p in F.CURATED_PREFIXES if tok.startswith(p)), None)}
    if d:
        raw = d[0]
        kind = F.classify_binary(raw)
        fp["b64kind"] = (d[1], d[2], len(raw), kind)
        t = F.printable(raw)
        if t and F.is_json(t.strip()):
            fp["json_keys"] = F.json_keys(t)
        elif kind == "der":
            fp["der"] = der_tags(raw)
        elif kind == "ssh-pub":
            fp["ssh"] = raw[4:4 + struct.unpack(">I", raw[:4])[0]]
        elif kind == "openssh":
            fp["ssh"] = raw[:40]
    m = F.JOSE_ANY.fullmatch(tok)
    if m and any(x.startswith("eyJ") for x in m.group("body").split(".")):
        segs = []
        for x in m.group("body").split("."):
            raw = F.b64_prefix_decode(x, F.jws_alphabet(x))[0] if x else b""
            if x[:1] == "e" and raw[:1] == b"{":
                t = raw.decode("utf-8", "replace")
                segs.append(("json", F.json_keys(t), t if F._is_header_json(t) else None))
            else:
                segs.append(("other", len(x), bool(re.search(r"[+/]", x))))
        fp["jose"] = (m.group("pre"), segs)
    return fp


def format_reasons(co: str, cs: str, oracle: F.Oracle) -> set[str]:
    po, ps = F.SPLIT.split(co), F.SPLIT.split(cs)
    if len(co) != len(cs) or len(po) != len(ps) or po[1::2] != ps[1::2]:
        return {"format:layout"}
    out = set()
    for a, b in zip(po[::2], ps[::2]):
        if a == b:
            continue
        a, b = a.strip("\"'`,;()[]{}<>"), b.strip("\"'`,;()[]{}<>")
        fa, fb = fingerprint(a, oracle), fingerprint(b, oracle)
        out |= {"format:" + k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True, help="extracted Secret-Leak-Detection-Issue-Report dir")
    ap.add_argument("--out", type=Path, required=True, help="sanitize_msr_issues.py output dir")
    ap.add_argument("--kingfisher", type=Path, required=True, help="Kingfisher checkout at the v1 rules commit")
    ap.add_argument("--list", type=Path, required=True, help="CSV to write: file,data_row,reasons")
    ap.add_argument("--drop", action="store_true", help="rewrite the sanitized CSVs without the listed rows")
    a = ap.parse_args()
    oracle = F.Oracle(a.kingfisher)
    report_path = a.out / "SANITIZE_REPORT.json"
    report = json.loads(report_path.read_text())
    if report.get("excluded_rows"):
        raise SystemExit("rows were already dropped from this output; check a fresh sanitizer output")
    leftover = {(p["file"], p["data_row"]) for p in report["verification"].get("leftover_places", []) if "data_row" in p}

    listed = []
    summary = collections.Counter()
    by_type = collections.Counter()
    for name in S.CSV_FILES:
        h, rows_o, _ = S.read_csv(a.src / "Data" / name)
        h2, rows_s, _ = S.read_csv(a.out / "Data" / name)
        if h != h2 or len(rows_o) != len(rows_s):
            raise SystemExit(f"{name}: header or row count differs from the original")
        ci, li = h.index("candidate_string"), h.index("label")
        ti = h.index("secret_type") if "secret_type" in h else None
        tcols = [i for i, c in enumerate(h) if c in S.TEXT_COLUMNS and i != ci]
        for k, (ro, rs) in enumerate(zip(rows_o, rows_s), start=1):
            if ro[li].strip() != "1":
                continue
            summary[f"{name}: positive rows"] += 1
            why = set()
            if (f"Data/{name}", k) in leftover:
                why.add("leftover")
            if ro[ci] != rs[ci]:
                why |= format_reasons(ro[ci], rs[ci], oracle)
            pre, v, _ = S.split_candidate(ro[ci])
            fake_v = rs[ci][len(pre):len(pre) + len(v)]
            for i in tcols:
                if len(ro[i]) != len(rs[i]):
                    why.add("length")
                    continue
                if any(rs[i][m.start():m.end()] != fake_v for m in re.finditer(re.escape(v), ro[i])):
                    why.add("text")
            if why:
                listed.append((f"Data/{name}", k, ";".join(sorted(why))))
                summary[f"{name}: listed"] += 1
                for w in why:
                    summary["reason " + w] += 1
                if ti is not None:
                    by_type[ro[ti]] += 1

    a.list.parent.mkdir(parents=True, exist_ok=True)
    with a.list.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "data_row", "reasons"])
        w.writerows(listed)

    if a.drop:
        skip = collections.defaultdict(set)
        for file, k, _ in listed:
            skip[file].add(k)
        for name in S.CSV_FILES:
            h, rows, eol = S.read_csv(a.out / "Data" / name)
            S.write_csv(a.out / "Data" / name, h, [r for k, r in enumerate(rows, start=1)
                                                   if k not in skip[f"Data/{name}"]], eol)
        report["excluded_rows"] = {"list": a.list.name, "per_file": {f: len(s) for f, s in sorted(skip.items())}}
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({"summary": dict(sorted(summary.items())), "main_data listed by secret_type": dict(
        by_type.most_common())}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
