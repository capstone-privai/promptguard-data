"""Convert the examples of Nosey Parker's built-in rules (praetorian-inc/noseyparker) into our session format.

Run from the repository root, after fetching the rules (see metric-1/README_noseyparker.md):
  python metric-1/scripts/convert_noseyparker.py --noseyparker ../noseyparker

Third-party data: origin=external, allowed_use=[rule_eval, ml_eval]. Needs PyYAML (installed with credsweeper).

Writes, under --out (default metric-1/):
  data_test/sessions_from_noseyparker.jsonl  one session per rule example or negative example, one tool_output item
                                             (a snippet of a file the agent read, like the CredData conversion)
  data_answer/gold_from_noseyparker.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_noseyparker.jsonl              every capture of every rule with our verdict (no values)

Each rule has a regular expression whose capture groups hold the secret, examples it must match and negative
examples it must not match. Every rule is applied to every item, so a negative example of one rule that another
rule matches gets that rule's gold.

Gold, with the criteria of the privesc-llm-data and CredData conversions:
  - Rules of category "secret": the captures listed in SECRET_GROUPS (default: group 1). A rule pairing a username,
    client id or host with the secret contributes only the secret.
  - Rules without "secret" capture identifiers (account ids, bucket names, OAuth client ids, public keys): not
    gold (identifier). Exceptions, as in the CredData conversion and the synthetic data: the AWS access key id
    (ACCESS_KEY) and Mapbox's public access token, a publishable key (ACCESS_KEY).
  - Password hashes (category "hashed") are not gold (password_hash), as in privesc.
  - Variable references ($Password, %PASS%) (reference), values shorter than MIN_VALUE_LEN (short),
    placeholders such as aaaa..., ABCDEFGH..., a1b2c3..., EXAMPLE (placeholder),
    public documentation examples such as RFC 7617's "open sesame" (known_example) and common passwords
    (common_password) are not gold.
  - Every other occurrence of a gold value in the item is gold too, as in privesc. Overlapping spans are merged;
    the type of the longest wins.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "noseyparker"
UPSTREAM = "https://github.com/praetorian-inc/noseyparker"
REVISION = "2e6e7f36ce36619852532bbe698d8cb7a26d2da7"
RULES_DIR = "crates/noseyparker/data/default/builtin/rules"
MIN_VALUE_LEN = 9

# Rules whose captures pair the secret with something that is not secret: which group(s) hold the secret.
SECRET_GROUPS = {
    "np.auth0.1": [3], "np.aws.6": [1, 2], "np.azure.1": [2], "np.azure.2": [3], "np.blynk.8": [2],
    "np.blynk.9": [2], "np.generic.3": [2], "np.generic.4": [2], "np.generic.7": [2], "np.generic.8": [3],
    "np.generic.9": [2], "np.generic.10": [2], "np.generic.13": [2], "np.generic.14": [2], "np.gitalk.1": [2],
    "np.google.6": [2], "np.gradle.1": [2], "np.kubernetes.2": [2], "np.mongodb.1": [2], "np.netrc.1": [3],
    "np.odbc.1": [2], "np.phpmailer.1": [3], "np.postgres.1": [2], "np.psexec.1": [2], "np.vmware.1": [2],
}
# Captures that are credentials although their rule is not in category "secret".
PUBLIC_CREDENTIALS = {"np.aws.1": "ACCESS_KEY", "np.mapbox.1": "ACCESS_KEY"}
PLACEHOLDER = re.compile(r"(.)\1{7}|abcdefgh|bcdefghi|ijklmnop|12345678|01234567|a1b2c3|1a2b3c|x{4}|example|<[^>]*>|"
                         r"\$\{|\{\{|your[_-]|redacted|changeme|placeholder", re.I)
REFERENCE = re.compile(r"^\$[A-Za-z_]\w*$|^%\w+%$|^\$\(|^\{\w+\}$")
KNOWN_EXAMPLES = {"open sesame", "open_sesame", "open-sesame", "QWxhZGRpbjpvcGVuIHNlc2FtZQ==", "mF_9.B5f-4.1JqM"}
COMMON_PASSWORDS = {"password", "password1", "password123", "123456789", "qwerty123", "letmein123", "welcome123",
                    "administrator", "changeme123", "secret123", "iloveyou1", "trustno1!"}


def compile_rule(pattern: str) -> re.Pattern:
    """Python rejects inline global flags after the start of the pattern, which Rust's regex allows."""
    try:
        return re.compile(pattern)
    except re.error:
        flags = "".join(sorted(set("".join(re.findall(r"\(\?([imsx]+)\)", pattern)))))
        return re.compile(f"(?{flags})" + re.sub(r"\(\?[imsx]+\)", "", pattern))


def gold_type(rule: dict, group: int) -> str:
    name = rule["name"].lower()
    if rule["id"] in PUBLIC_CREDENTIALS:
        return PUBLIC_CREDENTIALS[rule["id"]]
    if rule["id"] == "np.aws.6" and group == 1:
        return "ACCESS_KEY"
    if "private key" in name or "privatekey" in name:
        return "PRIVATE_KEY"
    if re.search(r"password|credential|netrc|username|basic auth", name):
        return "PASSWORD"
    if re.search(r"token|jwt|bearer|session", name):
        return "TOKEN"
    return "SECRET"


def judge(rule: dict, value: str) -> str:
    categories = rule.get("categories") or []
    if "hashed" in categories:
        return "password_hash"
    if "secret" not in categories and rule["id"] not in PUBLIC_CREDENTIALS:
        return "identifier"
    if REFERENCE.search(value):
        return "reference"
    if value in KNOWN_EXAMPLES or "EXAMPLE" in value:
        return "known_example"
    if PLACEHOLDER.search(value):
        return "placeholder"
    if len(value) < MIN_VALUE_LEN:
        return "short"
    if value.lower() in COMMON_PASSWORDS:
        return "common_password"
    return "gold"


def load_rules(root: Path) -> list[dict]:
    import yaml  # ships with credsweeper's dependencies

    folder = root / RULES_DIR
    files = sorted(folder.glob("*.yml"))
    if not files:
        raise FileNotFoundError(f"no rules under {folder}; fetch {UPSTREAM} first (README_{NAME}.md)")
    rules = []
    for path in files:
        for rule in yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]:
            rule["regex"] = compile_rule(rule["pattern"])
            rule["file"] = path.name
            rules.append(rule)
    return rules


def captures(rules: list[dict], text: str) -> list[dict]:
    out = []
    for rule in rules:
        groups = SECRET_GROUPS.get(rule["id"], [1])
        for m in rule["regex"].finditer(text):
            for g in groups:
                if g > rule["regex"].groups or m.group(g) is None or m.start(g) == m.end(g):
                    continue
                a, b = m.span(g)
                value = text[a:b].strip().strip("\"'")
                a = text.index(value, a) if value else a
                out.append({"start": a, "end": a + len(value), "rule": rule["id"], "group": g,
                            "kind": judge(rule, value), "type": gold_type(rule, g)})
    return [c for c in out if c["end"] > c["start"]]


def merge(spans: list[dict], stats: Counter) -> list[dict]:
    spans = sorted(spans, key=lambda s: (s["start"], -s["end"]))
    merged: list[dict] = []
    for s in spans:
        if merged and s["start"] < merged[-1]["end"]:
            m = merged[-1]
            stats["merged_overlapping"] += 1
            longest = max((m, s), key=lambda x: x["end"] - x["start"])
            merged[-1] = {**longest, "start": m["start"], "end": max(m["end"], s["end"])}
        else:
            merged.append(s)
    return merged


def convert(root: Path):
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rules = load_rules(root)
    sessions, gold, labels, stats = [], [], [], Counter()
    for rule in rules:
        for kind, texts in (("example", rule.get("examples") or []), ("negative_example", rule.get("negative_examples") or [])):
            for n, text in enumerate(texts):
                session_id = f"np-{rule['id'].removeprefix('np.')}-{'ex' if kind == 'example' else 'neg'}{n}"
                found = captures(rules, text)
                positive = [c for c in found if c["kind"] == "gold"]
                for value, kind_type in {(text[c["start"]:c["end"]], c["type"]) for c in positive}:
                    for m in re.finditer(re.escape(value), text):
                        if not any(c["start"] <= m.start() and m.end() <= c["end"] for c in positive):
                            positive.append({"start": m.start(), "end": m.end(), "rule": None, "group": None,
                                             "kind": "gold", "type": kind_type})
                            stats["gold_repeated_value"] += 1
                spans = merge(positive, stats)
                for span_id, s in enumerate(spans):
                    gold.append({"session_id": session_id, "item_id": 0, "span_id": span_id,
                                 "span": {"start": s["start"], "end": s["end"], "type": s["type"]}})
                for c in sorted(found, key=lambda c: (c["start"], c["end"])):
                    labels.append({"session_id": session_id, "item_id": 0, "start": c["start"], "end": c["end"],
                                   "gold": c["kind"] == "gold", "kind": c["kind"], "rule": c["rule"],
                                   "group": c["group"], **({"type": c["type"]} if c["kind"] == "gold" else {})})
                    stats[f"capture_{c['kind']}"] += 1
                stats[f"{kind}s"] += 1
                stats[f"{kind}s_with_gold"] += bool(spans)
                stats["cross_rule_captures"] += sum(1 for c in found if c["rule"] != rule["id"])
                sessions.append({"session_id": session_id,
                                 "items": [{"item_id": 0, "turn_id": "t0", "channel": "tool_output", "text": text}],
                                 "meta": {
                                     "dataset_version": f"{NAME}@{(commit or REVISION)[:12]}", "source": NAME,
                                     "origin": "external", "allowed_use": ALLOWED_USE["external"],
                                     "group_id": f"np-{rule['file'].removesuffix('.yml')}",
                                     "rule_id": rule["id"], "rule_name": rule["name"],
                                     "categories": rule.get("categories") or [], "example_kind": kind,
                                     "upstream_commit": commit, "license": f"Apache-2.0 ({UPSTREAM})",
                                 }})
    return sessions, gold, labels, stats


def write_outputs(root: Path, out: Path) -> dict:
    sessions, gold, labels, stats = convert(root)
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{NAME}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{NAME}.jsonl", gold)
    write_jsonl(out / f"labels_from_{NAME}.jsonl", labels)
    return {"sessions": len(sessions), "gold_spans": len(gold),
            "gold_by_type": dict(Counter(g["span"]["type"] for g in gold)), **dict(sorted(stats.items()))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--noseyparker", type=Path, default=REPO_ROOT.parent / NAME,
                        help=f"checkout of {UPSTREAM} (at least {RULES_DIR}) at {REVISION[:12]}")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.noseyparker, args.out), indent=2))


if __name__ == "__main__":
    main()
