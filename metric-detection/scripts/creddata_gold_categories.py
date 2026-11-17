"""Rebuild runs/creddata-source-fullfile/gold_category_train.jsonl from its inputs. No LLM calls.

Every train gold row of the whole-file conversion (labels_from_CredData.jsonl, gold=true) becomes one line in the
same order. The CredData Category is kept where the source has one (category_source=creddata). A missing category
takes the most common category of the identical value among categorized train gold rows (same_value; ties keep the
first category seen). The rest take the stored model assignment of category_llm/assigned_train.jsonl, joined to
category_llm/uncategorized_train.jsonl by id (opus). Those two files are inputs and are not regenerated here.
NOT_A_CREDENTIAL/UNSURE assignments and the reviewed template placeholders are written as {dropped: reason}:
dropped spans are not gold for task generation.

  python3 -B metric-detection/scripts/creddata_gold_categories.py            # writes the default output
  python3 -B metric-detection/scripts/creddata_gold_categories.py --check    # compares with the stored file
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FULLFILE = ROOT / "runs/creddata-source-fullfile"
SPLIT_DIR = ROOT / "metric-detection/source_splits/creddata-v1"
# Reviewed by hand: the model assigned a category, but the span is a template placeholder, not a value.
TEMPLATE_PLACEHOLDER_IDS = frozenset({16, 17, 20, 22, 47, 138})
DROPPED = {"NOT_A_CREDENTIAL": "not_a_credential", "UNSURE": "unsure"}


def rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def load(fullfile: Path, split: str):
    """(gold rows of the split, value of a row, category counts by identical value within the split)."""
    train = set((SPLIT_DIR / f"{split}.txt").read_text().split())
    gold = [r for r in rows(fullfile / "labels_from_CredData.jsonl") if r.get("gold") and r["session_id"] in train]
    wanted = {r["session_id"] for r in gold}
    texts = {}
    for session in rows(fullfile / "data_test/sessions_from_CredData.jsonl"):
        if session["session_id"] in wanted:
            texts[session["session_id"]] = [item["text"] for item in session["items"]]

    def value(row):
        return texts[row["session_id"]][row["item_id"]][row["start"]:row["end"]]

    by_value = defaultdict(Counter)
    for row in gold:
        if row["category"]:
            by_value[value(row)][row["category"]] += 1
    return gold, value, by_value


def pending(fullfile: Path, split: str) -> bytes:
    """The gold rows that need a model-assigned category, in the layout of category_llm/uncategorized_<split>.jsonl."""
    gold, value, by_value = load(fullfile, split)
    texts, out = {}, []
    for session in rows(fullfile / "data_test/sessions_from_CredData.jsonl"):
        texts[session["session_id"]] = session
    for row in gold:
        if row["category"] or by_value.get(value(row)):
            continue
        session = texts[row["session_id"]]
        text = session["items"][row["item_id"]]["text"]
        a, b = text.rfind("\n", 0, max(0, text.rfind("\n", 0, row["start"]))), row["end"]
        for _ in range(3):
            nxt = text.find("\n", b + 1)
            b = len(text) if nxt < 0 else nxt
        a = max(a, row["start"] - 400)
        b = min(b, row["end"] + 400)
        context = text[a + 1:row["start"]] + "\u27e6" + text[row["start"]:row["end"]] + "\u27e7" + text[row["end"]:b]
        out.append({"id": len(out), "session_id": row["session_id"], "start": row["start"], "end": row["end"],
                    "file": Path(session["meta"]["creddata_file"]).name, "our_rule": row["kind"],
                    "our_type": row["type"], "context": context})
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out).encode()


def build(fullfile: Path = FULLFILE, split: str = "train") -> bytes:
    gold, value, by_value = load(fullfile, split)
    uncategorized = {(r["session_id"], r["start"], r["end"]): r["id"]
                     for r in rows(fullfile / f"category_llm/uncategorized_{split}.jsonl")}
    assigned = {r["id"]: r for r in rows(fullfile / f"category_llm/assigned_{split}.jsonl")}
    source = "opus" if split == "train" else "model"  # the train assignments were made by Opus
    out = []
    for row in gold:
        record = {k: row[k] for k in ("session_id", "item_id", "start", "end", "type")}
        record["rule"] = row["kind"]
        if row["category"]:
            record.update(category=row["category"], category_source="creddata")
        elif by_value.get(value(row)):
            record.update(category=by_value[value(row)].most_common(1)[0][0], category_source="same_value")
        else:
            ident = uncategorized[(row["session_id"], row["start"], row["end"])]
            answer = assigned[ident]
            if split == "train" and ident in TEMPLATE_PLACEHOLDER_IDS:
                record.update(dropped="template_placeholder", category_source=source)
            elif answer["category"] in DROPPED:
                record.update(dropped=DROPPED[answer["category"]], category_source=source)
            else:
                record.update(category=answer["category"], category_source=source, confidence=answer["confidence"])
        out.append(json.dumps(record) + "\n")
    return "".join(out).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fullfile", type=Path, default=FULLFILE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true", help="compare with the stored file instead of writing")
    parser.add_argument("--split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--pending", action="store_true",
                        help="write category_llm/uncategorized_<split>.jsonl: the rows a model has to categorize")
    args = parser.parse_args()
    if args.pending:
        path = args.fullfile / f"category_llm/uncategorized_{args.split}.jsonl"
        data = pending(args.fullfile, args.split)
        path.write_bytes(data)
        print(json.dumps({"file": str(path), "lines": data.count(b"\n")}))
        return
    out = args.out or args.fullfile / f"gold_category_{args.split}.jsonl"
    data = build(args.fullfile, args.split)
    if args.check:
        same = out.is_file() and out.read_bytes() == data
        print(json.dumps({"file": str(out), "byte_identical": same, "lines": data.count(b"\n")}))
        sys.exit(0 if same else 1)
    out.write_bytes(data)
    print(json.dumps({"file": str(out), "lines": data.count(b"\n")}))


if __name__ == "__main__":
    main()
