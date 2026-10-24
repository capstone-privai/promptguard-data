"""Convert sailab-vienna/privesc-llm-data (paper SFT traces) into our session format, with automatic gold.

Run from the repository root, after downloading the dataset (see metric-detection/README_privesc-llm-data.md):
  python metric-detection/scripts/convert_privesc.py --privesc ../privesc-llm-data

Real agent runs (deepseek-v4-flash) against Linux privilege-escalation scenarios whose credentials were
planted before the run, so origin=recorded. Every run records the planted values in its metadata; gold is
where those values occur, found by search, independently of any detector.

Writes, under --out (default metric-detection/):
  data_test/sessions_from_privesc-llm-data.jsonl  one session per trace (training and validation splits)
  data_answer/gold_from_privesc-llm-data.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_privesc-llm-data.jsonl              gold spans plus excluded candidates, for analysis (no values)

Channels: system message -> instructions, user message -> prompt, each assistant tool call's arguments
(the JSON string as the model wrote it) -> tool_input, tool message -> tool_output. Assistant text and
reasoning have no channel and are left out. turn_id counts assistant messages: a tool result shares the
turn of the call that produced it.

Gold, by the rules of metric-detection/LABELING.md (label_rules.py):
  - PASSWORD candidates: planted values from metadata (prompt_vars.password, root_password, user_password,
    credential_candidates[].password) and passwords the agent tried (ATTEMPT: test_credentials, `echo '...' | su`,
    sudo -S, sshpass -p), of any length. Whether a value was planted or works does not decide gold.
  - Every occurrence of a candidate is classified by the text around it (label_rules.classify). A credential
    position is gold. Elsewhere, a distinct value is gold too unless it is in an identifier position; a common
    value (label_rules.is_common, plus this trace's usernames, container host names and path parts) is not.
  - PRIVATE_KEY: PEM private key blocks, BEGIN line through END line. Without an END line (truncated
    output), through the last body line; a BEGIN line with no body is not gold. Some truncated blocks hold
    only the public header and part of the public key (`head -5` on a key file), with no secret material;
    they are still gold, because a detector is expected to mask a private key block as a whole.
  - A value broken by terminal wrapping (the scenario terminal is 80 columns) is one span that includes
    the line break. Inside tool messages and tool arguments a line break is the two characters \\n.
  - Overlapping spans are merged; PRIVATE_KEY wins over PASSWORD.
Excluded candidates, kept only in the labels file:
  - password_hash: crypt(3) hashes such as /etc/shadow entries (not usable to authenticate).
  - identifier: a candidate in an identifier position (a username, path, host name, ls owner column).
  - not_propagated: a common candidate outside a credential position ("Running as root", "password" as a JSON key).
Every labels row of a candidate occurrence also records its rule and value class (common or distinct).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE
from label_rules import BREAK, classify, is_common, is_gold, occurrences

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "privesc-llm-data"
HF_REPO = "sailab-vienna/privesc-llm-data"
REVISION = "39a9d2ff37222184fcaf2a6d9a124906e8bb49ad"
PEM = re.compile(
    r"-----BEGIN ((?:[A-Z0-9]+ )*)PRIVATE KEY-----"
    rf"((?:{BREAK}[A-Za-z0-9+/=]+)*)"
    rf"(?:{BREAK}-----END \1PRIVATE KEY-----)?")
PEM_MIN_BODY = 16
HASH = re.compile(r"\$(?:1|5|6|y|2[aby])\$[A-Za-z0-9./$]{8,}")
ATTEMPT = re.compile(
    r"""password\\?["']?\s*[:=]\s*\\?["']([^"'\\\s]+)\\?["']"""  # test_credentials(password=...) arguments
    r"""|echo\s+\\?["']([^"'\\\s]+)\\?["']\s*\|\s*(?:su\b|sudo\s+-S)"""
    r"""|printf\s+\\?["']([^"'\\\s%]+?)(?:\\\\n|\\n)?\\?["']\s*\|\s*(?:su\b|sudo\s+-S)"""
    r"""|sshpass\s+-p\s*\\?["']?([^"'\\\s]+)""")
# Container host names (uname -a, sudo's "unable to resolve host", user@host prompts) and /etc/hosts names.
HOST = re.compile(r"(?:\bLinux |\bsudo on |@)([0-9a-f]{12})\b|\d+\.\d+\.\d+\.\d+\s+([\w.-]+)")
# The scenario's system prompt, whose "root shell", "password" are about the task, not credentials.
SYSTEM_PROMPT = re.compile(r"penetration testing assistant|MISSION|Simply seeing|got_root` is true|interactive\*{0,2} $")


def candidate_values(metadata: dict, texts: list[str]) -> dict[str, str]:
    """value -> where it came from: planted (a metadata field) or attempted (the agent tried it)."""
    found = [metadata["prompt_vars"].get("password"), metadata.get("root_password"), metadata.get("user_password")]
    found += [c.get("password") for c in metadata.get("credential_candidates") or []]
    values = {v: "planted" for v in found if isinstance(v, str) and v}
    for text in texts:
        for m in ATTEMPT.finditer(text):
            values.setdefault(next(g for g in m.groups() if g), "attempted")
    return {v: origin for v, origin in values.items() if v.strip() and not v.startswith("$")}


def usernames(metadata: dict) -> set[str]:
    """Account names in the trace, which a weak_password scenario may also use as the password."""
    found = [metadata.get("user"), metadata["prompt_vars"].get("user"),
             metadata.get("intended_target_user"), metadata.get("intended_reuse_user")]
    found += [c.get("user") for c in (metadata.get("credential_candidates") or [])
              + (metadata.get("decoy_credentials") or [])]
    return {v for v in found if isinstance(v, str) and v}


def common_values(values, metadata: dict, texts: list[str]) -> set[str]:
    """Candidates that are common in this trace: label_rules.is_common, or a username, a container host name or
    part of a path here (the weak_password scenario reuses the username as the password)."""
    identifiers = {n.lower() for n in usernames(metadata)}
    identifiers |= {h.lower() for text in texts for m in HOST.findall(text) for h in m if h}
    path_tokens = {t for text in texts for t in re.split(r"[\s'\"]+", text) if "/" in t}
    return {v for v in values if is_common(v, identifiers) or any(v in t for t in path_tokens)}


def find_values(text: str, channel: str, values, common: set[str]) -> tuple[list[dict], list[dict]]:
    """(gold password spans, candidate occurrences that are not gold)."""
    negative_context = SYSTEM_PROMPT if channel == "instructions" else None
    spans, others = [], []
    for value in values:
        value_class = "common" if value in common else "distinct"
        for m in occurrences(text, value):
            verdict, rule = classify(text, m.start(), m.end(), negative_context)
            row = {"start": m.start(), "end": m.end(), "rule": rule, "value_class": value_class}
            if is_gold(value in common, verdict):
                spans.append({**row, "type": "PASSWORD", "kind": "credential_slot" if verdict == "slot" else "propagated",
                              "wrapped": m.group() != value})
            else:
                others.append({**row, "kind": "identifier" if verdict == "ident" else "not_propagated"})
    return spans, others


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


def excluded(text: str, gold: list[dict], others: list[dict]) -> list[dict]:
    def inside(a, b):
        return any(g["start"] <= a and b <= g["end"] for g in gold)
    out = [o for o in others if not inside(o["start"], o["end"])]
    out += [{"start": m.start(), "end": m.end(), "kind": "password_hash"}
            for m in HASH.finditer(text) if not inside(m.start(), m.end())]
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
            messages = items_of(trace["messages"])
            texts = [text for _, _, text in messages]
            values = candidate_values(metadata, texts)
            common = common_values(values, metadata, texts)
            stats["candidates_planted"] += sum(o == "planted" for o in values.values())
            stats["candidates_attempted"] += sum(o == "attempted" for o in values.values())
            stats["candidates_common"] += len(common)
            session_id = f"privesc-{split}-{scenario}-{trace['run_id']}"
            items, seen = [], set()
            for item_id, (turn_id, channel, text) in enumerate(messages):
                items.append({"item_id": item_id, "turn_id": turn_id, "channel": channel, "text": text})
                password_spans, others = find_values(text, channel, values, common)
                seen |= {re.sub(BREAK, "", text[o["start"]:o["end"]]) for o in password_spans + others}
                spans = merge(password_spans + find_keys(text), stats)
                for span_id, s in enumerate(spans):
                    gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id,
                                 "span": {"start": s["start"], "end": s["end"], "type": s["type"]}})
                    labels.append({"session_id": session_id, "item_id": item_id, "start": s["start"], "end": s["end"],
                                   "gold": True, "kind": s["kind"], "type": s["type"], "channel": channel,
                                   "rule": s.get("rule"), "value_class": s.get("value_class"),
                                   "wrapped": s.get("wrapped", False), "truncated": s.get("truncated", False)})
                    stats[f"gold_{s['kind']}_{channel}"] += 1
                    stats["gold_wrapped"] += bool(s.get("wrapped"))
                    stats["gold_truncated_key"] += bool(s.get("truncated"))
                for e in excluded(text, spans, others):
                    labels.append({"session_id": session_id, "item_id": item_id, **e, "gold": False, "channel": channel})
                    stats[f"excluded_{e['kind']}"] += 1
            stats["planted_values_never_seen"] += sum(
                1 for v, o in values.items() if o == "planted" and v not in seen)
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
