"""List whole-file candidates where a scanner finds something on a line nobody judged.

A whole file has many lines CredData never labeled. A credential there has no gold, so it would be
trained as a negative. This runs gitleaks and CredSweeper over the candidate files and excludes every
file with a finding on a line that has neither a CredData label row (any ground truth) nor one of our
judged spans. Files are excluded, never auto-labeled. It lowers the risk; it does not prove completeness.
Outputs go under the ignored runs/ tree; scanner-reported values are never written.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import creddata_tasks as T

FULLFILE = T.ROOT / "runs/creddata-source-fullfile"
CATALOG = T.ROOT / "runs/creddata-auto-v3-fullfile"


def judged_lines(creddata: Path, sessions: dict, fullfile: Path) -> dict[str, set[int]]:
    """1-based lines per session that CredData or our label rules already ruled on."""
    by_file = {s["meta"]["creddata_file"]: sid for sid, s in sessions.items()}
    lines = defaultdict(set)
    for meta in sorted((creddata / "meta").glob("*.csv")):
        with meta.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                sid = by_file.get(row["FilePath"])
                if sid:
                    lines[sid].update(range(int(row["LineStart"]), int(row["LineEnd"]) + 1))
    starts = {}
    for row in T.rows(fullfile / "labels_from_CredData.jsonl"):
        sid = row["session_id"]
        if sid not in sessions:
            continue
        if sid not in starts:
            text, offsets = sessions[sid]["items"][0]["text"], [0]
            offsets += [i + 1 for i, c in enumerate(text) if c == "\n"]
            starts[sid] = offsets
        first = bisect_right(starts[sid], row["start"])
        last = bisect_right(starts[sid], max(row["start"], row["end"] - 1))
        lines[sid].update(range(first, last + 1))
    return lines


def scan(folder: Path, work: Path) -> list[tuple[str, str, str, int, int]]:
    """(scanner, rule, session id, first line, last line) for every finding."""
    found = []
    report = work / "gitleaks.json"
    run = subprocess.run(["gitleaks", "detect", "--no-git", "--no-banner", "--source", str(folder), "--report-format",
                          "json", "--report-path", str(report), "--exit-code", "0"], capture_output=True, text=True)
    if run.returncode != 0 or not report.is_file():
        raise RuntimeError("gitleaks failed: " + run.stderr[-500:])
    for row in json.loads(report.read_text() or "[]"):
        found.append(("gitleaks", row["RuleID"], Path(row["File"]).stem, row["StartLine"], row["EndLine"]))
    report = work / "credsweeper.json"
    run = subprocess.run(["credsweeper", "--path", str(folder), "--save-json", str(report), "--log", "ERROR",
                          "--no-progress"], capture_output=True, text=True)
    if run.returncode != 0 or not report.is_file():
        raise RuntimeError("credsweeper failed: " + run.stderr[-500:])
    for row in json.loads(report.read_text() or "[]"):
        places = [(Path(l["path"]).stem, l["line_num"]) for l in row["line_data_list"]]
        for sid in {p[0] for p in places}:
            numbers = [n for s, n in places if s == sid]
            found.append(("credsweeper", row["rule"], sid, min(numbers), max(numbers)))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creddata", type=Path, default=T.ROOT.parent / "CredData")
    parser.add_argument("--fullfile", type=Path, default=FULLFILE)
    parser.add_argument("--eligibility", type=Path, default=CATALOG / "eligibility.jsonl",
                        help="candidates to scan; build the catalog without --exclude first")
    parser.add_argument("--out", type=Path, default=FULLFILE / "scanner_filter")
    args = parser.parse_args()
    wanted = {row["source_session_id"] for row in T.rows(args.eligibility)}
    sessions = {s["session_id"]: s for s in T.rows(args.fullfile / "data_test/sessions_from_CredData.jsonl")
                if s["session_id"] in wanted}
    if set(sessions) != wanted:
        raise ValueError("candidate sessions are missing from the whole-file source")
    judged = judged_lines(args.creddata, sessions, args.fullfile)
    with tempfile.TemporaryDirectory(prefix="creddata-scan-") as temporary:
        folder = Path(temporary) / "files"
        folder.mkdir()
        for sid, session in sessions.items():
            source = args.creddata / session["meta"]["creddata_file"]
            if source.read_text(encoding="utf-8", errors="surrogateescape") != session["items"][0]["text"]:
                # Scan exactly what the catalog uses, whatever the converter normalised.
                (folder / (sid + source.suffix)).write_text(session["items"][0]["text"], encoding="utf-8",
                                                           errors="surrogateescape")
            else:
                shutil.copyfile(source, folder / (sid + source.suffix))
        findings = scan(folder, Path(temporary))
    stats, per_rule, per_file = Counter(), Counter(), defaultdict(Counter)
    for scanner, rule, sid, first, last in findings:
        stats[scanner + "_findings"] += 1
        if any(n in judged[sid] for n in range(first, last + 1)):
            stats[scanner + "_on_judged_lines"] += 1
            continue
        stats[scanner + "_on_unjudged_lines"] += 1
        per_rule[scanner + ":" + rule] += 1
        per_file[sid][scanner] += 1
    excluded = sorted(per_file)
    both = sum(1 for c in per_file.values() if len(c) == 2)
    report = {"scanned_files": len(sessions), "excluded_files": len(excluded),
              "excluded_by_both_scanners": both,
              "excluded_by_gitleaks_only": sum(1 for c in per_file.values() if set(c) == {"gitleaks"}),
              "excluded_by_credsweeper_only": sum(1 for c in per_file.values() if set(c) == {"credsweeper"}),
              "findings": dict(sorted(stats.items())),
              "unjudged_findings_by_rule": dict(per_rule.most_common()),
              "scanners": {"gitleaks": subprocess.run(["gitleaks", "version"], capture_output=True, text=True).stdout.strip(),
                           "credsweeper": subprocess.run(["credsweeper", "--version"], capture_output=True,
                                                         text=True).stdout.strip().split()[-1]},
              "scope": "Excludes files with a scanner finding on a line without a CredData label row or one of our "
                       "judged spans. Reduces unannotated credentials; does not certify there are none."}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "exclude.txt").write_text("".join(sid + "\n" for sid in excluded))
    (args.out / "report.json").write_bytes(T.jb(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
