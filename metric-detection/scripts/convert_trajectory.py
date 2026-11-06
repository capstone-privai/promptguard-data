"""Convert a metric-task batch (real Claude Code runs on tasks with planted secrets) into our session format.

Run from the repository root, after metric-task/scripts/m2_planted.py wrote planted.json into the batch:
  python metric-detection/scripts/convert_trajectory.py runs/metric-task/<batch>

Only valid runs of the none condition become sessions: nothing was masked, so the text is what a detector would see.
origin=recorded and split=test, so these sessions are never trained on (dataset_policy.allowed_use).

Writes, under --out (default metric-detection/):
  data_test/sessions_from_trajectory-<batch>.jsonl  one session per run
  data_answer/gold_from_trajectory-<batch>.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_trajectory-<batch>.jsonl              gold spans, excluded candidates and rows to review (no values)

Items come from api_requests.jsonl.xz, what the server received, not the transcript, which has neither the system
prompt nor the system reminders. Every /v1/messages request that succeeded is read, so a subagent's or a side request's
text is included. A later request repeats the earlier ones; a text enters as many times as one request holds it.
Channels: system prompt, system messages and <system-reminder> text -> instructions, other user text -> prompt, tool
arguments as JSON -> tool_input, tool result -> tool_output. Assistant text, thinking and tool definitions have no
channel and are left out. turn_id counts assistant messages: a tool result shares the turn of its call.

Gold, by the rules of metric-detection/LABELING.md (label_rules.py). planted.json lists candidates; it decides nothing:
  - A planted secret is a gold value: every occurrence, in any listed form (exact, base64, URL-encoded, hex), goes
    through label_rules.judge_occurrence. Whether the task needed the value or the agent used it does not matter.
  - A decoy is gold only where the text says so: in a credential position, or in a format that is a credential by
    itself (a Stripe publishable key). Then its other occurrences follow the propagation rule like any gold value.
  - PEM private key blocks are gold wherever they are, planted or not (convert_privesc.find_keys).
Not gold, and listed in the labels file for a person to judge (review=true):
  - identifier: a distinct planted secret the rules read as an identifier (the key in https://KEY@host, the last part of
    a webhook URL on an unknown host). The text alone may not show it is a credential, so it should not drop silently.
  - partial: part of a planted value (half its length, at least 10 characters), or a PEM body line on its own, as
    `head -c 20` prints it. LABELING.md has no rule for it except for private key blocks.
  - undeclared: a literal in a credential position that nothing planted (label_rules.slot_literals), such as a value
    the agent made up or one a task left undeclared. It stays out of gold until a person decides.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import lzma
from pathlib import Path
import re
import statistics
from urllib.parse import quote

from convert_privesc import find_keys, merge
from dataset_build import write_jsonl
from dataset_policy import allowed_use
from label_rules import (classify, exclusion_kind, expected_type, has_credential_format, is_common, judge_occurrence,
                         normalize_span, occurrences, path_components, position_type, slot_literals)

SOURCE = "agent-trajectory"
SPLIT = "test"
REQUESTS_FILE = "api_requests.jsonl.xz"
PARTIAL_MIN_VALUE = 16
PARTIAL_MIN_WINDOW = 10
SCORED_CHANNELS = ("prompt", "instructions", "tool_output")
# The minimum for a coverage axis value (per the trajectory evaluation plan).
MIN_UNIQUE_VALUES = 30
MIN_SCENES = 10


@dataclass
class Item:
    turn_id: str
    channel: str
    text: str
    tool: str | None = None
    tool_input: dict | None = None


# ---- items ---------------------------------------------------------------------------------------------------------

def read_requests(path: Path) -> list[dict]:
    """Bodies of the Messages requests the API accepted, oldest first."""
    bodies = []
    with lzma.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if not str(row.get("path", "")).startswith("/v1/messages") or "count_tokens" in row["path"]:
                continue
            if not str(row.get("status", "")).startswith("2"):
                continue
            body = row.get("body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except ValueError:
                    continue
            if isinstance(body, dict) and "messages" in body:
                bodies.append(body)
    return bodies


def block_texts(value) -> list[str]:
    """The text of a system field or a tool result: a string, or a list of blocks of which only text blocks count."""
    if isinstance(value, str):
        return [value]
    return [b.get("text") or "" for b in value or [] if isinstance(b, dict) and b.get("type") == "text"]


def session_items(bodies: list[dict]) -> list[Item]:
    items: list[Item] = []
    seen: Counter = Counter()
    for body in bodies:
        here: Counter = Counter()

        def add(item: Item):
            key = (item.channel, item.text)
            here[key] += 1
            if item.text and here[key] > seen[key]:
                seen[key] += 1
                items.append(item)

        for text in block_texts(body.get("system")):
            add(Item("t0", "instructions", text))
        assistants, calls = 0, {}
        for message in body["messages"]:
            role, content = message.get("role"), message.get("content")
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
            if role == "assistant":
                turn = f"t{assistants}"
                assistants += 1
                for block in blocks:
                    if block.get("type") == "tool_use":
                        calls[block.get("id")] = (turn, block.get("name"), block.get("input"))
                        add(Item(turn, "tool_input", json.dumps(block.get("input"), ensure_ascii=False),
                                 block.get("name"), block.get("input")))
                continue
            for block in blocks:
                if block.get("type") == "tool_result":
                    turn, tool, tool_input = calls.get(block.get("tool_use_id"), (f"t{assistants}", None, None))
                    for text in block_texts(block.get("content")):
                        add(Item(turn, "tool_output", text, tool, tool_input))
                elif block.get("type") == "text":
                    text = block.get("text") or ""
                    reminder = role == "system" or text.lstrip().startswith("<system-reminder>")
                    add(Item(f"t{assistants}", "instructions" if reminder else "prompt", text))
    return items


# ---- context -------------------------------------------------------------------------------------------------------

KEY_FILE = re.compile(r"(?:\.pem|\.key|\.ppk|\bid_(?:rsa|ed25519|ecdsa))$")
LOG_FILE = re.compile(r"(?:\.log|(?:^|/)logs?/[^/]+)$")
HTTP_FILE = re.compile(r"\.har$")
CONFIG_FILE = re.compile(r"(?:\.env(?:\.[\w-]+)?|\.ya?ml|\.json|\.toml|\.ini|\.properties|\.conf|\.cfg|\.xml|\.tf|\.tfvars"
                         r"|Dockerfile|\.npmrc|\.netrc|\.pypirc|\.gitconfig|\.git-credentials|credentials|config)$")
SOURCE_FILE = re.compile(r"\.(?:py|js|jsx|ts|tsx|go|java|rb|rs|sh|sql|kt|kts|c|cc|cpp|h|cs|php|ipynb)$")
DOC_FILE = re.compile(r"\.(?:md|rst)$")
PRINT_FILE = re.compile(r"^\s*(?:cat|head|tail|nl|less|more|bat|sed\s+-n\s+\S+)\b(?:\s+-\S+(?:\s+\d+)?)*\s+([^\s|;&<>]+)\s*$")
GIT_DIFF = re.compile(r"\bgit\s+(?:diff|show|blame|log\b[^|;&]*\s(?:-p|--patch)\b)")
HTTP_TEXT = re.compile(r"(?m)^[<>]?\s*HTTP/\d")
STACK_TEXT = re.compile(r"Traceback \(most recent call last\)|(?m:^\s+at \S+\(.*:\d+\)$)")


def file_context(path: str) -> str:
    for context, pattern in (("key_file", KEY_FILE), ("log", LOG_FILE), ("http", HTTP_FILE), ("config", CONFIG_FILE),
                             ("source", SOURCE_FILE), ("docs", DOC_FILE)):
        if pattern.search(path):
            return context
    return "unknown"


def printed_file(command: str) -> str | None:
    """The file a shell command prints whole or in part: the last command of a chain, before any filter."""
    last = re.split(r"&&|;", command)[-1].split("|")[0]
    m = PRINT_FILE.match(last)
    return m.group(1) if m else None


def context_of(item: Item) -> str:
    """Which coverage context a text belongs to. What is ambiguous stays unknown rather than guessed."""
    if item.channel == "prompt":
        return "natural_language"
    if item.channel == "instructions":
        return "docs"
    if item.channel == "tool_input":
        return "tool_input"
    tool_input = item.tool_input if isinstance(item.tool_input, dict) else {}
    if item.tool in ("Read", "Edit", "Write", "NotebookEdit"):
        return file_context(str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""))
    if item.tool == "Bash":
        command = str(tool_input.get("command") or "")
        if GIT_DIFF.search(command):
            return "diff"
        if HTTP_TEXT.search(item.text):
            return "http"
        if STACK_TEXT.search(item.text):
            return "stacktrace"
        path = printed_file(command)
        return file_context(path) if path else "command_output"
    if item.tool in ("Grep", "Glob"):
        return "command_output"
    return "unknown"


# ---- gold ----------------------------------------------------------------------------------------------------------

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def common_values(entries: list[dict], texts: list[str]) -> set[str]:
    paths = {part for text in texts for part in path_components(text)}
    return {e["value"] for e in entries if is_common(e["value"]) or e["value"] in paths}


def form_how(entry: dict, form: dict, entries: dict[str, dict]) -> str:
    """Recover a declared derived entry's encoding from its root and surface text.

    m2_planted records root != name for derived entries, but calls their own value 'exact' and does not
    retain transforms. This is metadata only: never add forms or change matching/labeling decisions.
    """
    how = form["how"]
    root = entries.get(entry.get("root"))
    if how != "exact" or root is None or entry["name"] == entry.get("root"):
        return how
    value, text = root["value"], form["text"]
    if text == value:
        return how  # a no-op transform is still the original surface text
    raw = value.encode()
    for encoding, encoded in (
            ("base64", base64.b64encode(raw).decode()),
            ("base64", base64.b64encode(raw + b"\n").decode()),
            ("base64url", base64.urlsafe_b64encode(raw).decode()),
            ("urlencoded", quote(value, safe="")),
            ("hex", raw.hex())):
        if text == encoded:
            return encoding
    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        return how
    if decoded.partition(b":")[1:] == (b":", raw):
        return "basic"
    return how


def established_decoys(entries: list[dict], texts: list[str]) -> set[str]:
    """Names of the decoys that are gold somewhere: in a credential position, or a credential by their format."""
    found = set()
    for entry in entries:
        if entry["role"] != "decoy" or not entry["value"]:
            continue
        value = entry["value"]
        for text in texts:
            for m in occurrences(text, value):
                if exclusion_kind(text, m.start(), m.end()) is None and (
                        has_credential_format(value) or classify(text, m.start(), m.end())[0] == "slot"):
                    found.add(entry["name"])
    return found


def span_type(text: str, start: int, end: int, entry: dict) -> str:
    return expected_type(text[start:end]) or entry["type"] or position_type(text, start) or "SECRET"


def find_candidates(text: str, entries: list[dict], common: set[str], golden: set[str]) -> tuple[list[dict], list[dict]]:
    """(gold spans, occurrences of a gold value that are not gold) of the planted values in a text."""
    spans, others = [], []
    by_name = {e["name"]: e for e in entries}
    for entry in entries:
        if not entry["value"]:
            continue  # a decoy can be the empty value (DB_PASSWORD=), which no search can place
        if entry["role"] == "decoy" and entry["name"] not in golden:
            for m in occurrences(text, entry["value"]):  # a hard negative the session really showed: counted, never gold
                others.append({"entry": entry["name"], "role": "decoy", "service": entry["kind"], "start": m.start(),
                               "end": m.end(), "kind": exclusion_kind(text, m.start(), m.end()) or "decoy",
                               "how": "exact", "value_class": "decoy", "value_sha256": digest(entry["value"])})
            continue
        info = {"entry": entry["name"], "role": entry["role"], "service": entry["kind"],
                "value_class": "common" if entry["value"] in common else "distinct",
                "value_sha256": digest(entry["value"])}
        for form in entry["forms"]:
            if form["how"] == "pem_part" or "-----BEGIN" in form["text"]:
                continue  # a whole block is find_keys' job, a part of one is review's
            for m in occurrences(text, form["text"]):
                gold, kind, rule = judge_occurrence(text, m.start(), m.end(), entry["value"] in common)
                row = {**info, "start": m.start(), "end": m.end(), "rule": rule,
                       "how": form_how(entry, form, by_name)}
                if not gold:
                    others.append({**row, "kind": kind})
                    continue
                start, end = normalize_span(text, m.start(), m.end())
                if start < end:
                    spans.append({**row, "start": start, "end": end, "type": span_type(text, start, end, entry),
                                  "kind": "credential_slot" if kind == "slot" else "propagated"})
    return spans, others


def overlaps(start: int, end: int, rows: list[dict]) -> bool:
    return any(r["start"] < end and start < r["end"] for r in rows)


def needs_review(occurrence: dict) -> bool:
    """A planted random secret in an identifier position: the rules say not gold, but the text may not show what it is."""
    return (occurrence["role"] == "secret" and occurrence["kind"] == "identifier"
            and occurrence["value_class"] == "distinct")


def to_review(text: str, entries: list[dict], taken: list[dict]) -> list[dict]:
    """Rows a person has to judge: parts of planted values, and credential literals nothing planted."""
    rows: list[dict] = []
    for entry in entries:
        if entry["role"] != "secret":
            continue
        value = entry["value"]
        pieces = [f["text"] for f in entry["forms"] if f["how"] == "pem_part"]
        if len(value) >= PARTIAL_MIN_VALUE and "-----BEGIN" not in value:
            size = max(PARTIAL_MIN_WINDOW, len(value) // 2)
            pieces += [value[i:i + size] for i in range(0, len(value) - size + 1, max(1, size // 4))]
        for piece in pieces:
            at = text.find(piece)
            if at >= 0 and not overlaps(at, at + len(piece), taken + rows):
                rows.append({"start": at, "end": at + len(piece), "kind": "partial", "entry": entry["name"],
                             "role": "secret", "service": entry["kind"], "review": True,
                             "value_sha256": digest(piece)})
    for start, end in slot_literals(text):
        if not overlaps(start, end, taken + rows):
            rows.append({"start": start, "end": end, "kind": "undeclared", "review": True,
                         "value_sha256": digest(text[start:end])})
    return rows


# ---- conversion ----------------------------------------------------------------------------------------------------

def run_folders(batch: Path) -> list[Path]:
    return sorted(p.parent for p in batch.glob("*/none-r*/result.json"))


def convert(batch: Path):
    meta = json.loads((batch / "batch.json").read_text(encoding="utf-8"))
    sessions, gold, labels = [], [], []
    stats: Counter = Counter()
    planted_rows: list[dict] = []
    for run in run_folders(batch):
        result = json.loads((run / "result.json").read_text(encoding="utf-8"))
        if not result.get("valid"):
            stats["runs_invalid"] += 1
            continue
        planted_path = run / "planted.json"
        if not planted_path.is_file():
            raise FileNotFoundError(f"{planted_path}: run metric-task/scripts/m2_planted.py on the batch first")
        if not (run / REQUESTS_FILE).is_file():
            raise FileNotFoundError(f"{run / REQUESTS_FILE}: this converter needs a batch recorded with capture on")
        planted = json.loads(planted_path.read_text(encoding="utf-8"))
        entries = planted["entries"]
        items = session_items(read_requests(run / REQUESTS_FILE))
        texts = [i.text for i in items]
        common = common_values(entries, texts)
        golden = established_decoys(entries, texts)
        session_id = f"traj-{batch.name}-{run.parent.name}-{run.name}"
        contexts, reached = [], set()
        rows_for_session = []
        for item_id, item in enumerate(items):
            context = context_of(item)
            contexts.append(context)
            spans, others = find_candidates(item.text, entries, common, golden)
            keys = [{**k, "service": "private_key", "role": "any"} for k in find_keys(item.text)]
            merged = merge(spans + keys, stats)
            for span_id, s in enumerate(merged):
                gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id,
                             "span": {"start": s["start"], "end": s["end"], "type": s["type"]}})
                rows_for_session.append({"session_id": session_id, "item_id": item_id, "gold": True, "channel": item.channel,
                                         "context": context, "value_sha256": digest(item.text[s["start"]:s["end"]]),
                                         "scene": planted["scene"], **{k: s.get(k) for k in (
                                             "start", "end", "kind", "type", "rule", "value_class", "entry", "role",
                                             "service", "how", "truncated")}})
                if item.channel in SCORED_CHANNELS and s.get("entry"):
                    reached.add(s["entry"])
            kept = [{**o, "review": True} if needs_review(o) else o for o in others
                    if not overlaps(o["start"], o["end"], merged)]
            for row in kept + to_review(item.text, entries, merged + others):
                rows_for_session.append({"session_id": session_id, "item_id": item_id, "gold": False,
                                         "channel": item.channel, "context": context, "scene": planted["scene"], **row})
        labels += rows_for_session
        secrets = [e["name"] for e in entries if e["role"] == "secret"]
        planted_rows.append({"secrets": len(secrets), "reached": len(reached & set(secrets))})
        sessions.append({"session_id": session_id, "items": [
            {"item_id": n, "turn_id": i.turn_id, "channel": i.channel, "text": i.text} for n, i in enumerate(items)],
            "meta": {"dataset_version": f"{SOURCE}@{batch.name}", "source": SOURCE, "origin": "recorded",
                     "allowed_use": allowed_use("recorded", SPLIT), "split": SPLIT, "group_id": planted["scene"],
                     "task": planted["task"], "batch": batch.name, "run": run.name, "model": meta.get("model"),
                     "claude_version": meta.get("claude_version"), "system_commit": meta.get("system_commit"),
                     "data_commit": meta.get("data_commit"), "task_success": result.get("success"),
                     "item_contexts": contexts}})
    stats["planted_secrets"] = sum(r["secrets"] for r in planted_rows)
    stats["planted_secrets_reached"] = sum(r["reached"] for r in planted_rows)
    stats["sessions_without_gold"] = len(sessions) - len({g["session_id"] for g in gold})
    return sessions, gold, labels, stats


def axis_counts(rows: list[dict], field: str) -> dict:
    """{value: spans, unique values, scenes, short} of the rows, short meaning below the minimum for a coverage axis."""
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get(field))].append(row)
    out = {}
    for value, group in sorted(groups.items()):
        unique, scenes = len({r["value_sha256"] for r in group}), len({r["scene"] for r in group})
        out[value] = {"spans": len(group), "unique_values": unique, "scenes": scenes,
                      "short": unique < MIN_UNIQUE_VALUES or scenes < MIN_SCENES}
    return out


def coverage(sessions: list[dict], gold: list[dict], labels: list[dict], stats: Counter) -> dict:
    """The numbers the plan compares with its targets: session shape against real traffic, axes against the minimums."""
    items = [i for s in sessions for i in s["items"]]
    outputs = sorted(len(i["text"]) for i in items if i["channel"] == "tool_output")
    positive = {(g["session_id"], g["item_id"]) for g in gold}
    contexts = Counter(c for s in sessions for c in s["meta"]["item_contexts"])
    scored_gold = [r for r in labels if r["gold"] and r["channel"] in SCORED_CHANNELS]
    negatives = [r for r in labels if not r["gold"] and not r.get("review")]
    return {
        "shape": {"sessions": len(sessions), "items": len(items),
                  "items_by_channel": dict(Counter(i["channel"] for i in items)),
                  "items_per_session_median": statistics.median(len(s["items"]) for s in sessions) if sessions else None,
                  "tool_output_chars_median": statistics.median(outputs) if outputs else None,
                  "tool_output_over_3000": round(sum(n > 3000 for n in outputs) / len(outputs), 3) if outputs else None,
                  "tool_output_over_6000": round(sum(n > 6000 for n in outputs) / len(outputs), 3) if outputs else None,
                  "positive_item_rate": round(len(positive) / len(items), 3) if items else None},
        "reach": {k: stats[k] for k in ("planted_secrets", "planted_secrets_reached", "sessions_without_gold",
                                        "runs_invalid")},
        "context_of_items": dict(contexts),
        "unknown_context_rate": round(contexts["unknown"] / len(items), 3) if items else None,
        "axes": {field: axis_counts(scored_gold, field) for field in ("type", "service", "context", "channel", "how")},
        "negatives_by_kind": dict(Counter(r["kind"] for r in negatives)),
        "to_review": dict(Counter(r["kind"] for r in labels if r.get("review"))),
        "gold_spans": len(gold),
    }


def write_outputs(batch: Path, out: Path) -> dict:
    sessions, gold, labels, stats = convert(batch)
    name = f"trajectory-{batch.name}"
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{name}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{name}.jsonl", gold)
    write_jsonl(out / f"labels_from_{name}.jsonl", labels)
    return coverage(sessions, gold, labels, stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.batch, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
