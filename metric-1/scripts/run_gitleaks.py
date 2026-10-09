"""Scan a sessions file with gitleaks and write where it found secrets, for `evaluate.py run --system gitleaks`.

Run from the repository root (gitleaks must be on PATH, e.g. `brew install gitleaks`):
  python metric-1/scripts/run_gitleaks.py [--sessions S] [--channels all|a,b] [--out F]

The evaluator never runs subprocesses (evaluation/tests/test_dependency_rules.py), so gitleaks runs here and
the evaluator only reads the result. Each item in the chosen channels is written to its own file in a
temporary folder, scanned once with `gitleaks dir` and its built-in config, and the folder (including
gitleaks' report, which holds the secrets) is deleted afterwards.

Writes (default runs/gitleaks/<sessions name>.jsonl, next to the evaluator's run folders):
  <out>            one finding per line: session_id, item_id, start, end, rule_id (item text offsets, no secrets)
  <out>.meta.json  gitleaks version, sessions path and SHA-256, channels, counts, scan time

Locating a finding: gitleaks' line numbers are used, but not its columns (they do not line up with the
text). The finding's Secret (else its Match) is searched in its reported lines, and every occurrence there
is kept. A secret gitleaks found by decoding (base64, hex) is located as the encoded token in those lines
that decodes to it. Findings still not found are counted as unlocated and left out.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

METRIC_ROOT = Path(__file__).resolve().parents[1]
CHANNELS = ("prompt", "instructions", "tool_input", "tool_output")
PROMPTGUARD_CHANNELS = "prompt,instructions,tool_output"  # evaluation/adapters/promptguard_adapter.py CHANNEL_MAP


ENCODED = re.compile(r"[A-Za-z0-9+/_-]{12,}={0,2}")  # base64 (standard or URL-safe) and hex tokens
DECODE_DEPTH = 5  # gitleaks' default --max-decode-depth


def decodings(token: str) -> list[str]:
    out = []
    for decode in (lambda t: base64.b64decode(t + "=" * (-len(t) % 4), validate=True),
                   lambda t: base64.urlsafe_b64decode(t + "=" * (-len(t) % 4)),
                   bytes.fromhex):
        try:
            out.append(decode(token).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            pass
    return out


def encoded_hits(text: str, needle: str, depth: int) -> list[tuple[int, int]]:
    """Spans of encoded tokens in `text` that decode (up to `depth` times) to something containing `needle`."""
    def holds(decoded: str, depth: int) -> bool:
        return needle in decoded or (depth > 1 and bool(encoded_hits(decoded, needle, depth - 1)))
    return [m.span() for m in ENCODED.finditer(text) if any(holds(d, depth) for d in decodings(m.group()))]


def locate(text: str, finding: dict) -> list[tuple[int, int]]:
    """Offsets in `text` of the finding's Secret (else Match) within its reported lines. A secret gitleaks
    found by decoding (tags decoded:*) is located as the encoded token that holds it."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    first, last = finding["StartLine"], finding["EndLine"]
    if not 1 <= first <= last <= len(starts):
        return []
    a = starts[first - 1]
    b = starts[last] - 1 if last < len(starts) else len(text)
    region = text[a:b]
    for needle in (finding.get("Secret"), finding.get("Match")):
        if needle:
            hits = [(a + m.start(), a + m.end()) for m in re.finditer(re.escape(needle), region)]
            if hits:
                return hits
    if finding.get("Secret"):
        return [(a + s, a + e) for s, e in encoded_hits(region, finding["Secret"], DECODE_DEPTH)]
    return []


def scan(items: list[tuple[str, int, str]], gitleaks: str) -> tuple[list[dict], Counter, float]:
    """items: (session_id, item_id, text). Returns findings as item offsets, counts and scan seconds."""
    stats: Counter = Counter()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_CONFIG")}  # built-in config only
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "items"
        target.mkdir()
        for n, (_, _, text) in enumerate(items):
            with (target / f"{n:07d}.txt").open("w", encoding="utf-8", newline="") as f:
                f.write(text)
        report = Path(tmp) / "report.json"
        started = time.perf_counter()
        subprocess.run([gitleaks, "dir", str(target), "--report-format", "json", "--report-path", str(report),
                        "--no-banner", "--exit-code", "0", "--log-level", "error"],
                       cwd=tmp, env=env, check=True)  # cwd: no .gitleaksignore from this repository
        elapsed = time.perf_counter() - started
        raw = json.loads(report.read_text(encoding="utf-8"))
    findings = []
    for f in raw:
        session_id, item_id, text = items[int(Path(f["File"]).stem)]
        spans = locate(text, f)
        stats["findings"] += 1
        stats["unlocated" if not spans else "located"] += 1
        for start, end in spans:
            findings.append({"session_id": session_id, "item_id": item_id, "start": start, "end": end,
                             "rule_id": f["RuleID"]})
    findings.sort(key=lambda r: (r["session_id"], r["item_id"], r["start"], r["end"], r["rule_id"]))
    return findings, stats, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, default=METRIC_ROOT / "data_test" / "sessions.jsonl")
    parser.add_argument("--channels", default=PROMPTGUARD_CHANNELS,
                        help=f"comma-separated channels to scan, or 'all' (default: {PROMPTGUARD_CHANNELS}, as PromptGuard)")
    parser.add_argument("--out", type=Path, help="findings file (default: runs/gitleaks/<sessions name>.jsonl)")
    parser.add_argument("--gitleaks", default="gitleaks", help="gitleaks executable")
    args = parser.parse_args()
    channels = CHANNELS if args.channels == "all" else tuple(dict.fromkeys(args.channels.split(",")))
    if unknown := [c for c in channels if c not in CHANNELS]:
        parser.error(f"unknown channel(s) {unknown}; expected 'all' or some of {list(CHANNELS)}")
    out = args.out or Path("runs") / "gitleaks" / f"{args.sessions.stem}.jsonl"

    data = args.sessions.read_bytes()
    items = [(s["session_id"], it["item_id"], it["text"])
             for s in map(json.loads, filter(None, data.decode("utf-8").split("\n")))  # not splitlines(): texts may hold U+2028
             for it in s["items"] if it["channel"] in channels]
    version = subprocess.run([args.gitleaks, "version"], capture_output=True, text=True, check=True).stdout.strip()
    findings, stats, elapsed = scan(items, args.gitleaks)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in findings), encoding="utf-8")
    meta = {"gitleaks_version": version, "config": "built-in",
            "sessions": str(args.sessions), "sessions_sha256": hashlib.sha256(data).hexdigest(),
            "channels": list(channels), "items_scanned": len(items),
            "findings": stats["findings"], "unlocated_findings": stats["unlocated"], "spans": len(findings),
            "scan_seconds": round(elapsed, 3), "created_at": datetime.now().isoformat(timespec="seconds")}
    Path(f"{out}.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"findings_file": str(out), **meta}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
