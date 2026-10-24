"""Have Claude write ML training templates from cards, through the Message Batches API (docs/README_ml-train-plan.md).

Run from the repository root (the API key comes from ANTHROPIC_API_KEY or an `ant auth login` profile):
  python metric-detection/scripts/ml_train_write.py requests CARDS.jsonl [--out R.jsonl]   requests only, no API call
  python metric-detection/scripts/ml_train_write.py submit CARDS.jsonl --name NAME          create a batch
  python metric-detection/scripts/ml_train_write.py collect NAME [--wait]                   save the raw results
  python metric-detection/scripts/ml_train_write.py process NAME                            check them, keep templates
submit skips cards that already have an accepted template in NAME, so running submit, collect and process again
retries only the rejected cards. Files under metric-detection/templates/ml_train/:
  batches/NAME.json        batch ids, prompt version and the custom_id of every request (no text)
  raw/NAME.jsonl           every response as returned (git-ignored: a rejected response may hold a literal secret)
  raw/rejected_NAME.jsonl  rejected responses with the reasons (git-ignored)
  NAME.jsonl               accepted templates, the input of ml_train_build.py build
A template is accepted when the response is complete JSON, follows its card, holds no credential outside the
placeholders, and builds and passes ml_train_build's checks on its own.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from label_rules import exclusion_kind, expected_type
import ml_train_build as B

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "templates" / "ml_train"
PROMPT = DIR / "prompt_v1.md"
PROMPT_VERSION = "v1"
MAX_TOKENS = 32000
EFFORT = "medium"
# Batch prices per million tokens (50% of the standard price): input, output, cache read, cache write (5 min)
PRICE = {"claude-opus-5-5": (2.0, 10.0, 0.10, 2.5), "claude-sonnet-5-5": (1.0, 5.0, 0.10, 1.25)}
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"turn_id": {"type": "string"},
                       "channel": {"type": "string", "enum": ["prompt", "instructions", "tool_input", "tool_output"]},
                       "text": {"type": "string"}},
        "required": ["turn_id", "channel", "text"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}
CARD_FIELDS = ("context", "format", "primary_type", "language", "tool_output_format", "tool_input_format")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def write_jsonl(path: Path, rows: list[dict], append: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def prompt() -> tuple[str, str]:
    text = PROMPT.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def card_message(card: dict) -> str:
    """The user turn: the card as a work order, then the card itself."""
    lines = [f"Card {card['card_id']}.",
             f"- Context: {card['context']} ({card['format']}).",
             f"- Language: {card['language']}. Items: exactly {card['items']}. Turns: exactly {card['turns']}.",
             f"- Longest tool_output: about {card['longest_output_chars']} characters.",
             f"- tool_output format: {card['tool_output_format']}. tool_input format: {card['tool_input_format']}."]
    if card["secrets"]:
        lines.append("- Secrets (copy each placeholder exactly):")
        lines += [f"  - {s['placeholder']} ({s['type']}): first in {s['channel']}, repeat {s['repeat']}"
                  + (f"; later the agent reuses it in a tool_input as {s['mask']}" if s.get("mask") else "")
                  for s in card["secrets"]]
    else:
        lines.append("- Secrets: none. The session holds no credential at all; it still looks like work where one "
                     "could appear.")
    if card["negatives"]:
        lines.append("- Hard negatives:")
        lines += [f"  - {n['placeholder']}: position {n['position']}" for n in card["negatives"]]
    if card["boundary"]:
        lines.append(f"- Boundary rule ({card['boundary']['rule']}): {card['boundary']['instruction']}")
    return "\n".join(lines) + "\n\nCard JSON:\n" + json.dumps(card, ensure_ascii=False)


def request(card: dict, attempt: int, system: str) -> dict:
    return {"custom_id": f"{card['card_id']}-{attempt}",
            "params": {"model": card["model"], "max_tokens": MAX_TOKENS,
                       "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                       "messages": [{"role": "user", "content": card_message(card)}],
                       "thinking": {"type": "adaptive"},
                       "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}}}}


def card_of(custom_id: str) -> tuple[str, int]:
    card_id, _, attempt = custom_id.rpartition("-")
    return card_id, int(attempt)


# ---- checks -----------------------------------------------------------------------

PLACEHOLDER_TEXT = re.compile(r"\\\{\{|\{\{[^{}]*\}\}")
# A credential key with a literal value after it (what the placeholders should have been)
LITERAL_AFTER_KEY = re.compile(
    r"""(?i)(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret"""
    r"""|auth(?:orization)?|credentials?)["']?[ \t]*[:=][ \t]*["']?(?!PLACEHOLDER\b)([^\s"',;{}()<>\]\[]{6,})""")


def strip_placeholders(text: str, mark: str = " ") -> str:
    return PLACEHOLDER_TEXT.sub(mark, text)


def literal_secrets(texts: list[str]) -> list[str]:
    """Credentials written outside the placeholders: a value whose format alone makes it one, or a literal after a
    credential key that label_rules does not read as a reference, template, redaction or code."""
    found = []
    for text in texts:
        bare = strip_placeholders(text, "PLACEHOLDER")
        for token in re.findall(r"[A-Za-z0-9_\-./+=:]{12,}", bare):
            if expected_type(token):
                found.append(f"literal {expected_type(token)} {token[:12]}...")
        if "PRIVATE KEY-----" in bare and re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\S", bare):
            found.append("literal private key block")
        for m in LITERAL_AFTER_KEY.finditer(bare):
            if not exclusion_kind(bare, m.start(1), m.end(1)) and not m.group(1).replace(".", "").isdigit():
                found.append(f"literal value after a credential key: {bare[m.start():m.end()][:40]!r}")
    return found


def gitleaks(candidates: dict[str, list[str]]) -> dict[str, list[str]]:
    """gitleaks findings per custom_id on the texts with placeholders removed (skipped if gitleaks is missing)."""
    if not shutil.which("gitleaks"):
        return {}
    with tempfile.TemporaryDirectory() as directory:
        for cid, texts in candidates.items():
            Path(directory, f"{cid}.txt").write_text("\n\n".join(map(strip_placeholders, texts)), encoding="utf-8")
        report = Path(directory) / "report.json"
        subprocess.run(["gitleaks", "dir", directory, "--report-format", "json", "--report-path", str(report),
                        "--no-banner", "--exit-code", "0", "--log-level", "error"], check=True)
        found: dict[str, list[str]] = {}
        for f in json.loads(report.read_text() or "[]"):
            cid = Path(f["File"]).stem
            if cid != "report":
                found.setdefault(cid, []).append(f"gitleaks {f['RuleID']}")
        return found


def follows_card(card: dict, items: list[dict]) -> list[str]:
    problems = []
    if not card["items"] - 1 <= len(items) <= card["items"] + 1:
        problems.append(f"{len(items)} items, card asks {card['items']}")
    turns = [i["turn_id"] for i in items]
    if len(set(turns)) > card["turns"] + 1:
        problems.append(f"{len(set(turns))} turns, card asks {card['turns']}")
    if any(i["channel"] == "instructions" and i["turn_id"] != items[0]["turn_id"] for i in items):
        problems.append("instructions after the first turn")
    allowed = set()
    for s in card["secrets"]:
        ph = s["placeholder"]
        if ph == "{{PASSWORD=LITERAL}}":
            hits = [i for i in items if re.search(r"\{\{PASSWORD=(?!LITERAL\}\})[^{}]+\}\}", i["text"])]
            allowed |= {m for i in items for m in re.findall(r"\{\{PASSWORD=[^{}]+\}\}", i["text"])}
        else:
            hits = [i for i in items if ph in i["text"]]
            allowed.add(ph)
        if not hits:
            problems.append(f"secret {ph} missing")
            continue
        if not any(i["channel"] == s["channel"] for i in hits):
            problems.append(f"secret {ph} not in {s['channel']}")
        if s["repeat"] == "multi_item" and len(hits) < 2:
            problems.append(f"secret {ph} in one item, card asks multi_item")
        if s["repeat"] == "multi_channel" and len({i["channel"] for i in hits}) < 2:
            problems.append(f"secret {ph} in one channel, card asks multi_channel")
        if s.get("mask") and not any(s["mask"] in i["text"] for i in items if i["channel"] == "tool_input"):
            problems.append(f"mask {s['mask']} not in a tool_input")
    for kind, n in Counter(neg["kind"] for neg in card["negatives"]).items():
        if sum(i["text"].count(f"{{{{neg:{kind}}}}}") for i in items) < n:
            problems.append(f"negative {{{{neg:{kind}}}}} missing")
    in_input = {m for i in items if i["channel"] == "tool_input"
                for m in re.findall(r"\{\{(?!neg:|mask:)[^{}]*\}\}", i["text"]) if not m.startswith("{{ ")}
    if in_input:
        problems.append(f"secret placeholders in tool_input (the agent writes masks there): {sorted(in_input)[:3]}")
    stray = {m for i in items for m in re.findall(r"\{\{(?!neg:|mask:)[^{}]*\}\}", i["text"])} - allowed
    stray = {m for m in stray if not m.startswith("{{ ")}
    if stray:
        problems.append(f"placeholders not on the card: {sorted(stray)[:4]}")
    if card["language"] in ("ko", "mixed") and not any(re.search(r"[가-힣]", i["text"]) for i in items
                                                       if i["channel"] == "prompt"):
        problems.append("no Korean in the developer's messages")
    return problems


def template_line(card: dict, items: list[dict], generator: dict) -> dict:
    meta = {"split": card["split"], "group_id": card["group_id"], "variants": card["variants"],
            "value_profile": "mltrain", "card": {k: card[k] for k in CARD_FIELDS},
            "boundary_rule": card["boundary"]["rule"] if card["boundary"] else None,
            "negatives": [n["kind"] for n in card["negatives"]], "generator": generator}
    return {"session_id": card["card_id"], "meta": meta, "items": items}


def builds(line: dict, stem: str) -> list[str]:
    """ml_train_build's build and checks on this one template."""
    try:
        sessions, gold, labels = B.build_lines([json.dumps(line, ensure_ascii=False)], line["session_id"], stem,
                                               f"metric-detection/templates/ml_train/{stem}.jsonl")
    except ValueError as e:
        return [f"build: {e}"]
    errors: list[str] = []
    B.check_rows(sessions, gold, labels, line["session_id"], errors)
    return [f"check: {e}" for e in errors]


# ---- commands -----------------------------------------------------------------------

def paths(name: str) -> dict[str, Path]:
    return {"state": DIR / "batches" / f"{name}.json", "raw": DIR / "raw" / f"{name}.jsonl",
            "rejected": DIR / "raw" / f"rejected_{name}.jsonl", "templates": DIR / f"{name}.jsonl"}


def pending(cards: list[dict], name: str) -> list[tuple[dict, int]]:
    """(card, attempt) for every card of cards without an accepted template in NAME."""
    p = paths(name)
    accepted = {t["session_id"] for t in read_jsonl(p["templates"])} if p["templates"].is_file() else set()
    tried = Counter(card_of(r["custom_id"])[0] for r in read_jsonl(p["raw"])) if p["raw"].is_file() else Counter()
    state = json.loads(p["state"].read_text()) if p["state"].is_file() else {"batches": []}
    tried.update(card_of(cid)[0] for b in state["batches"] if not b.get("collected") for cid in b["custom_ids"])
    return [(c, tried[c["card_id"]] + 1) for c in cards if c["card_id"] not in accepted]


def cmd_requests(args):
    system, digest = prompt()
    reqs = [request(c, 1, system) for c in read_jsonl(args.cards)]
    write_jsonl(args.out, reqs)
    chars = sum(len(r["params"]["messages"][0]["content"]) for r in reqs)
    print(json.dumps({"requests": len(reqs), "out": str(args.out), "prompt": f"{PROMPT_VERSION} {digest}",
                      "system_chars": len(system), "card_chars_total": chars,
                      "models": dict(Counter(r["params"]["model"] for r in reqs))}, indent=2))


def cmd_submit(args):
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    system, digest = prompt()
    todo = pending(read_jsonl(args.cards), args.name)
    if not todo:
        print("every card already has an accepted template")
        return
    reqs = [request(c, attempt, system) for c, attempt in todo]
    batch = anthropic.Anthropic().messages.batches.create(
        requests=[Request(custom_id=r["custom_id"], params=MessageCreateParamsNonStreaming(**r["params"])) for r in reqs])
    p = paths(args.name)
    state = json.loads(p["state"].read_text()) if p["state"].is_file() else {"name": args.name, "batches": []}
    state["batches"].append({"batch_id": batch.id, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                             "cards": str(args.cards),
                             "cards_sha256": hashlib.sha256(args.cards.read_bytes()).hexdigest(),
                             "prompt": f"{PROMPT_VERSION} {digest}",
                             "effort": EFFORT, "custom_ids": [r["custom_id"] for r in reqs], "collected": False})
    p["state"].parent.mkdir(parents=True, exist_ok=True)
    p["state"].write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"batch {batch.id}: {len(reqs)} requests ({batch.processing_status})")


def cmd_collect(args):
    import anthropic
    client = anthropic.Anthropic()
    p = paths(args.name)
    state = json.loads(p["state"].read_text())
    for b in state["batches"]:
        if b["collected"]:
            continue
        while True:
            batch = client.messages.batches.retrieve(b["batch_id"])
            if batch.processing_status == "ended" or not args.wait:
                break
            print(f"{b['batch_id']}: {batch.processing_status}, {batch.request_counts.processing} processing")
            time.sleep(60)
        if batch.processing_status != "ended":
            print(f"{b['batch_id']}: {batch.processing_status}; run collect again later (or with --wait)")
            continue
        rows = []
        for result in client.messages.batches.results(b["batch_id"]):  # any order: keyed by custom_id
            row = {"custom_id": result.custom_id, "batch_id": b["batch_id"], "prompt": b["prompt"],
                   "type": result.result.type}
            if result.result.type == "succeeded":
                msg = result.result.message
                row.update(message_id=msg.id, model=msg.model, stop_reason=msg.stop_reason,
                           text=next((c.text for c in msg.content if c.type == "text"), ""),
                           usage=msg.usage.model_dump(exclude_none=True))
            elif result.result.type == "errored":
                row["error"] = result.result.error.model_dump(exclude_none=True)
            rows.append(row)
        write_jsonl(p["raw"], rows, append=True)
        b["collected"] = True
        p["state"].write_text(json.dumps(state, ensure_ascii=False, indent=1))
        print(f"{b['batch_id']}: {Counter(r['type'] for r in rows)}")


def cost(rows: list[dict]) -> float:
    total = 0.0
    for r in rows:
        u, price = r.get("usage") or {}, PRICE.get(r.get("model", ""), PRICE["claude-opus-5-5"])
        total += (u.get("input_tokens", 0) * price[0] + u.get("output_tokens", 0) * price[1]
                  + u.get("cache_read_input_tokens", 0) * price[2]
                  + u.get("cache_creation_input_tokens", 0) * price[3]) / 1e6
    return total


def cmd_process(args):
    p = paths(args.name)
    cards = {c["card_id"]: c for c in read_jsonl(args.cards)}
    accepted_ids = {t["session_id"] for t in read_jsonl(p["templates"])} if p["templates"].is_file() else set()
    done = {r["custom_id"] for r in read_jsonl(p["rejected"])} if p["rejected"].is_file() else set()
    rows = [r for r in read_jsonl(p["raw"]) if r["custom_id"] not in done
            and card_of(r["custom_id"])[0] not in accepted_ids]
    candidates, reasons = {}, {}
    for r in rows:
        card = cards.get(card_of(r["custom_id"])[0])
        why = []
        if card is None:
            why.append("card not in the cards file")
        elif r["type"] != "succeeded":
            why.append(f"result {r['type']} {r.get('error', '')}")
        elif r["stop_reason"] != "end_turn":
            why.append(f"stop_reason {r['stop_reason']}")
        else:
            try:
                items = json.loads(r["text"])["items"]
                candidates[r["custom_id"]] = (card, items)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                why.append(f"not the schema's JSON: {e}")
        if why:
            reasons[r["custom_id"]] = why
    leaks = gitleaks({cid: [i["text"] for i in items] for cid, (_, items) in candidates.items()})
    accepted, rejected = [], []
    for cid, (card, items) in candidates.items():
        why = follows_card(card, items) + literal_secrets([i["text"] for i in items]) + leaks.get(cid, [])
        r = next(x for x in rows if x["custom_id"] == cid)
        line = template_line(card, items, {"model": r["model"], "prompt": r["prompt"], "batch_id": r["batch_id"],
                                           "custom_id": cid, "message_id": r["message_id"]})
        if not why:
            why = builds(line, args.name)
        if why or card["card_id"] in accepted_ids:
            reasons.setdefault(cid, []).extend(why or ["card already accepted"])
        else:
            accepted.append(line)
            accepted_ids.add(card["card_id"])
    for cid, why in reasons.items():
        r = next(x for x in rows if x["custom_id"] == cid)
        rejected.append({"custom_id": cid, "reasons": why, "text": r.get("text", "")})
    write_jsonl(p["templates"], accepted, append=True)
    write_jsonl(p["rejected"], rejected, append=True)
    first = Counter(w.split(":")[0].split(" {")[0][:40] for x in rejected for w in x["reasons"][:1])
    print(json.dumps({"responses": len(rows), "accepted": len(accepted), "rejected": len(rejected),
                      "templates_total": len(accepted_ids), "cards_without_template": len(set(cards) - accepted_ids),
                      "rejected_by_first_reason": dict(first.most_common(10)),
                      "batch_cost_usd": round(cost(rows), 2)}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("requests", help="write the batch requests of a cards file, without calling the API")
    p.add_argument("cards", type=Path)
    p.add_argument("--out", type=Path, default=Path("ml_train_requests.jsonl"))
    p = sub.add_parser("submit", help="create a batch for the cards without an accepted template")
    p.add_argument("cards", type=Path)
    p.add_argument("--name", required=True)
    p = sub.add_parser("collect", help="save the results of finished batches")
    p.add_argument("name")
    p.add_argument("--wait", action="store_true", help="poll every minute until each batch ends")
    p = sub.add_parser("process", help="check the saved results and keep the accepted templates")
    p.add_argument("name")
    p.add_argument("--cards", type=Path, default=DIR / "cards.jsonl")
    args = parser.parse_args()
    {"requests": cmd_requests, "submit": cmd_submit, "collect": cmd_collect, "process": cmd_process}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
