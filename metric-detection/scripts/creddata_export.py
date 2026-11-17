"""Label finished whole-file runs, add value-substituted variants, and write the training handoff folder.

For every instance with a finished run: the captured trajectory is labeled again with the current labeler (the
instance's own labeled/ folder is left as it was), then --variants copies are made in which every occurrence of an
injected value is replaced by a freshly drawn value of the same slot, in the same written form. A variant is kept
only if labeling it from scratch with the new values gives exactly the replaced spans; otherwise it is dropped and
counted. Sessions without gold are kept once, as negatives. Everything inherits the source split and component.
The output holds licensed source text and generated secrets: write it under the ignored runs/ tree only.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import quote

import creddata_fullfile as F
import creddata_rollout as R
import creddata_tasks as T
import convert_trajectory as C


class Unsupported(Exception):
    pass


# Identifiers of the machine and account the runs were made on. They are replaced before labeling, so spans are
# computed on the text that is written. A run in which the agent wandered into the dataset's own files is dropped.
SCRUB = ((re.compile(r"[A-Za-z0-9._+-]*capstonedesign[A-Za-z0-9._+-]*@[A-Za-z0-9.-]+"), "user@example.com"),
         (re.compile(r"/develop/jungwoo\b"), "/develop/user"), (re.compile(r"jungwoo"), "user"),
         (re.compile(r"promptguard-data"), "py-env"), (re.compile(r"(?i)promptguard"), "project"),
         (re.compile(r"\.claude-trajectory"), ".claude"))
OUTSIDE = re.compile(r"(?i)creddata")


def scrub(text: str, counts: Counter) -> str:
    for pattern, replacement in SCRUB:
        text, n = pattern.subn(replacement, text)
        counts[replacement] += n
    return text


def written(value: str, how: str, task: dict, name: str, text: str | None = None, old: str | None = None) -> str:
    """The value in the written form a label row names. A source-layout key needs the old text to pick its layout."""
    slot = task["slots"][name]
    if how == "exact":
        return value
    if how == "layout":
        for occurrence in task["occurrences"]:
            if occurrence["secret_id"] == name and (text is None or F.encode(old, occurrence, slot) == text):
                return F.encode(value, occurrence, slot)
        raise Unsupported("layout_not_found")
    if how == "urlencoded":
        return quote(value, safe="")
    if how == "base64":
        return base64.b64encode(value.encode()).decode()
    try:
        if how.startswith("json_of_"):
            return json.dumps(T.encode_fragment(value, how[len("json_of_"):]), ensure_ascii=False)[1:-1]
        return T.encode_fragment(value, how)
    except (ValueError, KeyError):
        raise Unsupported("form_" + how) from None


def substitute(task: dict, old: dict, new: dict, session: dict, labels: list[dict]):
    """(items with new values, expected gold spans per item). Raises Unsupported when a span cannot be rewritten."""
    by_item = {}
    for row in labels:
        if row["gold"] or (row.get("role") == "secret" and row.get("value_class") == "distinct" and row.get("how")):
            by_item.setdefault(row["item_id"], []).append(row)
    items, expected = [], set()
    for item in session["items"]:
        text, pieces, cursor, length = item["text"], [], 0, 0
        for row in sorted(by_item.get(item["item_id"], []), key=lambda r: r["start"]):
            name, how = row["entry"], row["how"]
            if row["start"] < cursor:
                raise Unsupported("overlapping_spans")
            if how not in ("exact", "layout", "urlencoded", "base64") and not how.startswith(("json", "python", "yaml", "native")):
                raise Unsupported("form_" + how)
            if name not in old:
                raise Unsupported("derived_entry")
            before = text[row["start"]:row["end"]]
            if written(old[name], how, task, name) != before and how != "layout":
                raise Unsupported("span_is_not_one_written_value")
            after = written(new[name], how, task, name, before, old[name])
            pieces += [text[cursor:row["start"]], after]
            length += row["start"] - cursor
            if row["gold"]:
                expected.add((item["item_id"], length, length + len(after), row["type"]))
            length += len(after)
            cursor = row["end"]
        pieces.append(text[cursor:])
        items.append({**item, "text": "".join(pieces)})
    return items, expected


def label(task: dict, registry: dict, items: list[dict], session_id: str):
    return R.label_items(task, registry, [C.Item(i["turn_id"], i["channel"], i["text"]) for i in items], session_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variants", type=int, default=2)
    parser.add_argument("--seed", default="augment-01")
    args = parser.parse_args()
    if T.ROOT / "runs" not in args.out.resolve().parents:
        parser.error("--out must be under the ignored runs/ tree")
    pack, stats, dropped, scrubbed = args.catalog / "templates", Counter(), Counter(), Counter()
    config = json.loads((args.catalog / "tasks.json").read_text())
    catalog, split = config["version"], config["split"]
    if split != "train" and args.variants:
        parser.error("value-substituted variants are for training data; pass --variants 0 for a val/test catalog")
    sessions, gold_rows, label_rows = [], [], []

    def keep(session, gold, labels):
        sessions.append(session)
        gold_rows.extend(gold)
        label_rows.extend(labels)
        meta = session["meta"]
        kind = "augmented" if "augmented_from" in meta else "recorded"
        stats[kind + "_sessions"] += 1
        stats[kind + "_gold_spans"] += len(gold)
        stats[kind + "_items"] += len(session["items"])
        stats[f"{kind}_sessions/{meta['family']}/{meta['instruction_language']}"] += 1
        for row in gold:
            stats[kind + "_gold/type/" + row["span"]["type"]] += 1
        for row in labels:
            if row["gold"]:
                stats[kind + "_gold/channel/" + row["channel"]] += 1
                stats[kind + "_gold/how/" + row["how"]] += 1
            elif row.get("review") or row.get("kind") in ("partial", "undeclared"):
                stats[kind + "_review_candidates"] += 1

    for instance in sorted(p for p in args.instances.iterdir() if (p / "run.json").is_file()):
        run = json.loads((instance / "run.json").read_text())
        stats["runs/" + run["status"]] += 1
        if run["status"] != "finished":
            continue
        task = json.loads((instance / "task.json").read_text())
        registry = json.loads((instance / "private/registry.json").read_text())
        items = C.session_items(C.read_requests(instance / "capture/api_requests.jsonl.xz"))
        if any(OUTSIDE.search(i.text) for i in items):
            stats["runs_dropped/agent_left_the_workspace"] += 1
            continue
        raw_gold = len(R.label_items(task, registry, items, "x")[1])
        for item in items:
            item.text = scrub(item.text, scrubbed)
        session_id = "creddata-traj-" + run["session_id"]
        session, gold, labels, _ = R.label_items(task, registry, items, session_id)
        if len(gold) != raw_gold:
            stats["runs_dropped/scrub_changed_labels"] += 1
            continue
        extra = {"dataset_version": catalog, "run_status": run["status"], "model": run["models_sent"],
                 "effort": run.get("effort"), "auth_mode": run["auth_mode"], "source_scope": "whole_file",
                 "value_seed": registry["seed"]}
        session["meta"].update(extra)
        keep(session, gold, labels)
        if not gold:
            stats["recorded_sessions_without_gold"] += 1
            continue
        for number in range(1, args.variants + 1):
            seed = f"{args.seed}-{number}"
            fresh = json.loads(T.instantiate(pack, task["task_id"], seed)["private/registry.json"])
            try:
                if any(fresh["values"][name] == value for name, value in registry["values"].items()):
                    raise Unsupported("same_value_drawn")
                new_items, expected = substitute(task, registry["values"], fresh["values"], session, labels)
                variant_id = f"{session_id}-aug{number}"
                variant, new_gold, new_labels, _ = label(task, fresh, new_items, variant_id)
                found = {(g["item_id"], g["span"]["start"], g["span"]["end"], g["span"]["type"]) for g in new_gold}
                if found != expected:
                    raise Unsupported("relabel_differs")
            except Unsupported as reason:
                dropped[str(reason)] += 1
                continue
            variant["meta"].update({**extra, "origin": "augmented", "augmented_from": session_id,
                                    "augmentation": "value_substitution", "value_seed": seed})
            keep(variant, new_gold, new_labels)

    groups = {s["meta"]["group_id"] for s in sessions}
    manifest = {"catalog": catalog, "instances": str(args.instances), "split": split, "variants_per_session": args.variants,
                "augmentation_seed": args.seed, "sessions": len(sessions), "gold_spans": len(gold_rows),
                "components": len(groups), "source_files": len({s["meta"]["source_session_id"] for s in sessions}),
                "counts": dict(sorted(stats.items())), "variants_dropped": dict(sorted(dropped.items())),
                "scrubbed_replacements": dict(sorted(scrubbed.items())),
                "success_grading": None,
                "scope": "Known injected values only; completeness of annotation is not certified. All sources are "
                         "from the CredData " + split + " partition (creddata-v1): keep group_id (component) together and do "
                         "not re-split at random. Augmented sessions repeat their recorded session with other values, "
                         "so a recorded session and its variants must stay in one fold."}
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in ((f"sessions_{split}.jsonl", sessions), (f"gold_{split}.jsonl", gold_rows), (f"labels_{split}.jsonl", label_rows)):
        with (args.out / name).open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.out / "manifest.json").write_bytes(T.jb(manifest))
    print(json.dumps({k: v for k, v in manifest.items() if k != "scope"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
