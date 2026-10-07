"""Convert sailab-vienna/privesc-llm-data (paper SFT traces) into our session format, with automatic gold.

Run from the repository root, after downloading the dataset (see metric-1/README_privesc-llm-data.md):
  python metric-1/scripts/convert_privesc.py --privesc ../privesc-llm-data

Real agent runs (deepseek-v4-flash) against Linux privilege-escalation scenarios whose credentials were
planted before the run, so origin=recorded. Every run records the planted values in its metadata; gold is
where those values occur, found by search, independently of any detector.

Writes, under --out (default metric-1/):
  data_test/sessions_from_privesc-llm-data.jsonl  one session per trace (training and validation splits)
  data_answer/gold_from_privesc-llm-data.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_privesc-llm-data.jsonl              gold spans plus excluded candidates, for analysis (no values)

Channels: system message -> instructions, user message -> prompt, each assistant tool call's arguments
(the JSON string as the model wrote it) -> tool_input, tool message -> tool_output. Assistant text and
reasoning have no channel and are left out. turn_id counts assistant messages: a tool result shares the
turn of the call that produced it.

Gold:
  - PASSWORD: planted values from metadata (prompt_vars.password, root_password, user_password,
    credential_candidates[].password) that are at least MIN_VALUE_LEN characters. Shorter ones come from a
    public common-password list ("toor", "P@ssw0rd"); like CredData, they are not gold.
  - A planted password identical to a username in the same trace (the weak_password scenario reuses the
    username as the password) is gold only where CRED_POS shows it being supplied as a credential. The same
    string in a home directory path or an /etc/passwd user field is not a secret.
  - PRIVATE_KEY: PEM private key blocks, BEGIN line through END line. Without an END line (truncated
    output), through the last body line; a BEGIN line with no body is not gold. Some truncated blocks hold
    only the public header and part of the public key (`head -5` on a key file), with no secret material;
    they are still gold, because a detector is expected to mask a private key block as a whole.
  - A value broken by terminal wrapping (the scenario terminal is 80 columns) is one span that includes
    the line break. Inside tool messages and tool arguments a line break is the two characters \\n.
  - Overlapping spans are merged; PRIVATE_KEY wins over PASSWORD.
Excluded candidates, kept only in the labels file:
  - password_hash: crypt(3) hashes such as /etc/shadow entries (not usable to authenticate).
  - username_occurrence: a planted password identical to a username, outside a credential position.
  - attempted_password: a password the agent tried (test_credentials, `echo '...' | su`, sudo -S,
    sshpass -p) that is not a planted gold value, e.g. guesses or passwords the agent set itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "privesc-llm-data"
HF_REPO = "sailab-vienna/privesc-llm-data"
REVISION = "39a9d2ff37222184fcaf2a6d9a124906e8bb49ad"
MIN_VALUE_LEN = 9

# A line break as it appears in item text: a real newline, or an escaped one inside a JSON string
# (\n, or \\n when the JSON holds a shell string that itself escapes it).
BREAK = r"(?:\r?\n|(?:\\{1,2}r)?\\{1,2}n)"
PEM = re.compile(
    r"-----BEGIN ((?:[A-Z0-9]+ )*)PRIVATE KEY-----"
    rf"((?:{BREAK}[A-Za-z0-9+/=]+)*)"
    rf"(?:{BREAK}-----END \1PRIVATE KEY-----)?")
PEM_MIN_BODY = 16
HASH = re.compile(r"\$(?:1|5|6|y|2[aby])\$[A-Za-z0-9./$]{8,}")
# Text right before a value that is being supplied as a credential: a password field or key, or the secret
# argument of an authentication command. Used only for values that are also a username.
CRED_POS = re.compile(
    r"""password\\?["']?\s*[:=]\s*\\?["']?$"""  # "password": "...", password=...
    r"""|pass:$"""                              # openssl -password pass:...
    r"""|sshpass\s+-p\s*\\?["']?$"""
    r"""|(?:echo|printf|send)\s+\\?["']$""")    # echo '...' | su, expect send "..."
ATTEMPT = re.compile(
    r"""password\\?["']?\s*[:=]\s*\\?["']([^"'\\\s]+)\\?["']"""  # test_credentials(password=...) arguments
    r"""|echo\s+\\?["']([^"'\\\s]+)\\?["']\s*\|\s*(?:su\b|sudo\s+-S)"""
    r"""|printf\s+\\?["']([^"'\\\s%]+?)(?:\\\\n|\\n)?\\?["']\s*\|\s*(?:su\b|sudo\s+-S)"""
    r"""|sshpass\s+-p\s*\\?["']?([^"'\\\s]+)""")


def planted_values(metadata: dict) -> dict[str, str]:
    """value -> metadata field it came from, for credential-like planted passwords."""
    found = [("prompt_vars.password", metadata["prompt_vars"]["password"]),
             ("root_password", metadata.get("root_password")),
             ("user_password", metadata.get("user_password"))]
    found += [("credential_candidates", c.get("password")) for c in metadata.get("credential_candidates") or []]
    values: dict[str, str] = {}
    for field, value in found:
        if isinstance(value, str) and len(value) >= MIN_VALUE_LEN:
            values.setdefault(value, field)
    return values


def usernames(metadata: dict) -> set[str]:
    """Account names in the trace, which a weak_password scenario may also use as the password."""
    found = [metadata.get("user"), metadata["prompt_vars"].get("user"),
             metadata.get("intended_target_user"), metadata.get("intended_reuse_user")]
    found += [c.get("user") for c in (metadata.get("credential_candidates") or [])
              + (metadata.get("decoy_credentials") or [])]
    return {v for v in found if isinstance(v, str) and v}


def wrapped(value: str) -> re.Pattern:
    """Matches value, allowing one line break between any two characters (terminal wrapping)."""
    return re.compile(f"(?:{BREAK})?".join(re.escape(ch) for ch in value))


def find_values(text: str, patterns: dict[str, re.Pattern],
                account_names: set[str]) -> tuple[list[dict], list[dict]]:
    """(gold password spans, occurrences of a username-as-password outside a credential position)."""
    spans, names = [], []
    for value, pattern in patterns.items():
        if value[:6] not in text and value[-6:] not in text:  # a wrapped value keeps one half intact
            continue
        for m in pattern.finditer(text):
            if value in account_names and not CRED_POS.search(text[:m.start()]):
                names.append({"start": m.start(), "end": m.end(), "kind": "username_occurrence"})
                continue
            spans.append({"start": m.start(), "end": m.end(), "type": "PASSWORD",
                          "kind": "planted_password", "wrapped": m.group() != value})
    return spans, names


def find_keys(text: str) -> list[dict]:
    spans = []
    for m in PEM.finditer(text):
        body = re.sub(BREAK, "", m.group(2))
        if len(body) < PEM_MIN_BODY:
            continue
        spans.append({"start": m.start(), "end": m.end(), "type": "PRIVATE_KEY", "kind": "private_key",
                      "truncated": "-----END" not in m.group()})
    return spans


def merge(spans: list[dict], stats: Counter) -> list[dict]:
    spans = sorted(spans, key=lambda s: (s["start"], -s["end"]))
    merged: list[dict] = []
    for s in spans:
        if merged and s["start"] < merged[-1]["end"]:
            m = merged[-1]
            stats["merged_overlapping"] += 1
            kind = m if m["type"] == "PRIVATE_KEY" or s["type"] != "PRIVATE_KEY" else s
            merged[-1] = {**kind, "start": m["start"], "end": max(m["end"], s["end"])}
        else:
            merged.append(s)
    return merged


def excluded(text: str, gold: list[dict], planted: set[str], names: list[dict]) -> list[dict]:
    def inside(a, b):
        return any(g["start"] <= a and b <= g["end"] for g in gold)
    out = [n for n in names if not inside(n["start"], n["end"])]
    out += [{"start": m.start(), "end": m.end(), "kind": "password_hash"}
            for m in HASH.finditer(text) if not inside(m.start(), m.end())]
    for m in ATTEMPT.finditer(text):
        group = next(g for g in range(1, 5) if m.group(g) is not None)
        a, b = m.span(group)
        if m.group(group) not in planted and not inside(a, b):
            out.append({"start": a, "end": b, "kind": "attempted_password"})
    return out


def items_of(messages: list[dict]) -> list[tuple[str, str, str]]:
    """(turn_id, channel, text) per message part, in conversation order."""
    out, turn, call_turn = [], 0, {}
    assistants = 0
    for msg in messages:
        role = msg["role"]
        if role in ("system", "user"):
            turn = assistants
            out.append((f"t{turn}", "instructions" if role == "system" else "prompt", msg.get("content") or ""))
        elif role == "assistant":
            turn = assistants
            assistants += 1
            for call in msg.get("tool_calls") or []:
                call_turn[call["id"]] = turn
                out.append((f"t{turn}", "tool_input", call["function"]["arguments"]))
        elif role == "tool":
            out.append((f"t{call_turn.get(msg.get('tool_call_id'), turn)}", "tool_output", msg.get("content") or ""))
        else:
            raise ValueError(f"unknown role {role!r}")
    return [i for i in out if i[2]]


def convert(root: Path):
    traces = sorted((root / "paper_sft_dataset").glob("*/*/traces.jsonl"))
    if not traces:
        raise FileNotFoundError(f"no paper_sft_dataset/*/*/traces.jsonl under {root}; download {HF_REPO} first")
    sessions, gold, labels = [], [], []
    stats = Counter()
    for path in traces:
        split, scenario = path.parts[-3], path.parts[-2]
        for line_no, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if not line:
                continue
            trace = json.loads(line)
            metadata = json.loads(trace["metadata"])
            values = planted_values(metadata)
            patterns = {v: wrapped(v) for v in values}
            account_names = usernames(metadata)
            session_id = f"privesc-{split}-{scenario}-{trace['run_id']}"
            items = []
            for item_id, (turn_id, channel, text) in enumerate(items_of(trace["messages"])):
                items.append({"item_id": item_id, "turn_id": turn_id, "channel": channel, "text": text})
                password_spans, name_spans = find_values(text, patterns, account_names)
                spans = merge(password_spans + find_keys(text), stats)
                for span_id, s in enumerate(spans):
                    gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id,
                                 "span": {"start": s["start"], "end": s["end"], "type": s["type"]}})
                    labels.append({"session_id": session_id, "item_id": item_id, "start": s["start"], "end": s["end"],
                                   "gold": True, "kind": s["kind"], "type": s["type"], "channel": channel,
                                   "wrapped": s.get("wrapped", False), "truncated": s.get("truncated", False)})
                    stats[f"gold_{s['kind']}_{channel}"] += 1
                    stats["gold_wrapped"] += bool(s.get("wrapped"))
                    stats["gold_truncated_key"] += bool(s.get("truncated"))
                for e in excluded(text, spans, set(values), name_spans):
                    labels.append({"session_id": session_id, "item_id": item_id, **e, "gold": False, "channel": channel})
                    stats[f"excluded_{e['kind']}"] += 1
            stats["planted_values_never_seen"] += sum(
                1 for v in values if not any(p.search(i["text"]) for p in [patterns[v]] for i in items))
            sessions.append({"session_id": session_id, "items": items, "meta": {
                "dataset_version": f"{NAME}@{REVISION[:12]}", "source": NAME,
                "origin": "recorded", "allowed_use": ALLOWED_USE["recorded"],
                "group_id": f"privesc-{scenario}",
                "split": split, "scenario": scenario, "run_id": trace["run_id"],
                "model": trace["model"], "success": trace["success"],
                "upstream_file": path.relative_to(root).as_posix(), "upstream_line": line_no,
                "license": f"MIT ({HF_REPO})",
            }})
    return sessions, gold, labels, stats


def write_outputs(root: Path, out: Path) -> dict:
    sessions, gold, labels, stats = convert(root)
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{NAME}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{NAME}.jsonl", gold)
    write_jsonl(out / f"labels_from_{NAME}.jsonl", labels)
    return {"sessions": len(sessions), "items": sum(len(s["items"]) for s in sessions),
            "items_by_channel": dict(Counter(i["channel"] for s in sessions for i in s["items"])),
            "gold_spans": len(gold), "gold_by_type": dict(Counter(g["span"]["type"] for g in gold)),
            **dict(sorted(stats.items()))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--privesc", type=Path, default=REPO_ROOT.parent / NAME,
                        help=f"local copy of {HF_REPO} at revision {REVISION[:12]}")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.privesc, args.out), indent=2))


if __name__ == "__main__":
    main()
