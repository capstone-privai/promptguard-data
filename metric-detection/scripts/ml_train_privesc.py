"""Turn the privesc-llm-data conversion into ML training rows (docs/README_ml-train-plan.md 5절, privesc).

convert_privesc.py keeps the agent's commands (tool_input) as they were, real passwords included, and leaves
their gold out of scoring only. Training data keeps secrets out of tool_input: in deployment the agent sees only
what PromptGuard's Native Mod showed it, so it writes the placeholder [KIND_n] where it reuses a secret. This
script rewrites each tool_input gold span into that placeholder and writes the result in the ml_train_build.py
format. The evaluation conversion and its files are not touched.

Run from the repository root, after downloading the dataset (see metric-detection/README_privesc-llm-data.md):
  python metric-detection/scripts/ml_train_privesc.py build --privesc ../privesc-llm-data --target-gold N
  python metric-detection/scripts/ml_train_privesc.py build --privesc ../privesc-llm-data --synthetic-train-gold M
  python metric-detection/scripts/ml_train_privesc.py build --privesc ../privesc-llm-data --sessions N
  python metric-detection/scripts/ml_train_privesc.py verify --privesc ../privesc-llm-data
build writes, under --out (default metric-detection/ml_build/, outside the evaluation data_test/: the scorer
refuses train sessions), data_test/sessions_ml_privesc.jsonl, data_answer/gold_ml_privesc.jsonl and
labels_ml_privesc.jsonl.

Masks: [KIND_n], KIND from the gold type (value_gen.MASK_KIND_OF_TYPE), n numbered per KIND in the order a
value is first gold outside tool_input, as ml_train_build.Masks does. A value the agent writes before it was ever
gold outside tool_input (a guess, a common value it saw unmasked) is masked too, numbered where it first appears
in tool_input: tool_input holds no secret either way (decided 2026-10-25). Each mask is a labels row of kind mask.
Labels rows of the other items' coordinates do not move; in a tool_input item they are shifted past the masks.

Splits: password_reuse and ssh_key_reuse go to test_ood, whole; the other eight scenarios go to train, sampled.
group_id is privesc-<scenario>, apart from the card ids (c0001) and hand templates (hand-) of the synthetic set.
The train sample takes sessions round robin over the scenarios, each in a fixed hash order, while their gold
(instructions and tool_output, the only gold left) stays within the target; meta.sample records the target so
verify can rebuild the files byte for byte.

Labels rows have the ml_train_build.py fields (session_id, item_id, start, end, gold false, kind). Besides mask,
they keep the candidates convert_privesc.py left out of gold: identifier, not_propagated, hash (its password_hash),
code, reference, redaction. dataset_verify's coverage check needs identifier and not_propagated.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

from convert_privesc import NAME, REPO_ROOT, REVISION, convert
from dataset_build import write_jsonl
from dataset_policy import allowed_use
import dataset_verify as V
from label_rules import BREAK, is_common
import value_gen

STEM = "privesc"
SOURCE = "ml_train_privesc"
ORIGIN = "recorded"
TEST_OOD = ("password_reuse", "ssh_key_reuse")
TRAIN_SHARE = 0.3  # privesc gold at most this share of all train gold (docs/README_ml-train-plan.md 5절)
MASK = "mask"
MASK_TEXT = re.compile(r"\[[A-Z0-9_]+_\d+\]")
KIND_OF_EXCLUDED = {"password_hash": "hash"}  # convert_privesc.py's name -> LABELING.md's


def paths(out: Path) -> tuple[Path, Path, Path]:
    return (out / "data_test" / f"sessions_ml_{STEM}.jsonl", out / "data_answer" / f"gold_ml_{STEM}.jsonl",
            out / f"labels_ml_{STEM}.jsonl")


class Masks:
    """[KIND_n] per value, numbered per KIND in the order values are first seen."""

    def __init__(self):
        self.mask: dict[str, str] = {}
        self.count: Counter = Counter()

    def of(self, value: str, gold_type: str) -> str:
        value = re.sub(BREAK, "", value)  # a value wrapped by the terminal is the same secret
        if value not in self.mask:
            kind = value_gen.MASK_KIND_OF_TYPE[gold_type]
            self.count[kind] += 1
            self.mask[value] = f"[{kind}_{self.count[kind]}]"
        return self.mask[value]


def mask_session(session: dict, spans: dict[int, list[dict]], others: dict[int, list[dict]]):
    """(items, gold spans per item, labels rows per item) with every tool_input gold span replaced by its mask."""
    masks, items, gold, labels = Masks(), [], {}, {}
    for item in session["items"]:
        iid, text = item["item_id"], item["text"]
        item_spans, rows = spans.get(iid, []), others.get(iid, [])
        if item["channel"] != "tool_input":
            for sp in item_spans:
                masks.of(text[sp["start"]:sp["end"]], sp["type"])
            items.append(item)
            gold[iid], labels[iid] = item_spans, rows
            continue
        out, pos, shifts, new_rows = "", 0, [], []
        for sp in item_spans:
            mask = masks.of(text[sp["start"]:sp["end"]], sp["type"])
            out += text[pos:sp["start"]]
            new_rows.append({"start": len(out), "end": len(out) + len(mask), "kind": MASK})
            out += mask
            pos = sp["end"]
            shifts.append((sp["start"], sp["end"], len(out) - sp["end"]))
        out += text[pos:]
        for r in rows:
            if any(a < r["end"] and r["start"] < b for a, b, _ in shifts):
                raise ValueError(f"{session['session_id']}/{iid}: labels row {r} overlaps a gold span")
            delta = next((d for _, b, d in reversed(shifts) if b <= r["start"]), 0)
            new_rows.append({**r, "start": r["start"] + delta, "end": r["end"] + delta})
        items.append({**item, "text": out})
        gold[iid], labels[iid] = [], sorted(new_rows, key=lambda r: (r["start"], r["end"], r["kind"]))
    return items, gold, labels


def sample_order(session_id: str) -> str:
    return hashlib.sha256(f"{SOURCE}:{REVISION}:{session_id}".encode()).hexdigest()


def choose(train: list[dict], gold_count: dict[str, int], sample: dict) -> set[str]:
    """Train session ids: round robin over the scenarios, each in sample_order, until the target is reached."""
    queues = defaultdict(list)
    for s in sorted(train, key=lambda s: sample_order(s["session_id"])):
        queues[s["meta"]["scenario"]].append(s["session_id"])
    order = []
    for k in range(max(map(len, queues.values()), default=0)):
        order += [queues[scenario][k] for scenario in sorted(queues) if k < len(queues[scenario])]
    chosen, total = set(), 0
    for sid in order:
        if "sessions" in sample and len(chosen) >= sample["sessions"]:
            break
        if "target_gold" in sample and total + gold_count[sid] > sample["target_gold"]:
            break
        chosen.add(sid)
        total += gold_count[sid]
    return chosen


def build(root: Path, sample: dict) -> tuple[list[dict], list[dict], list[dict]]:
    sessions, gold, labels, _ = convert(root)
    spans, others = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for g in gold:
        spans[g["session_id"]][g["item_id"]].append(g["span"])
    for r in labels:
        if not r["gold"]:
            others[r["session_id"]][r["item_id"]].append(
                {"start": r["start"], "end": r["end"], "kind": KIND_OF_EXCLUDED.get(r["kind"], r["kind"])})
    channel = {(s["session_id"], i["item_id"]): i["channel"] for s in sessions for i in s["items"]}
    gold_count = Counter(g["session_id"] for g in gold if channel[(g["session_id"], g["item_id"])] != "tool_input")
    train = [s for s in sessions if s["meta"]["scenario"] not in TEST_OOD]
    chosen = choose(train, gold_count, sample) | {s["session_id"] for s in sessions if s["meta"]["scenario"] in TEST_OOD}

    out_sessions, out_gold, out_labels = [], [], []
    for s in sessions:
        sid = s["session_id"]
        if sid not in chosen:
            continue
        upstream = {k: v for k, v in s["meta"].items() if k not in ("source", "origin", "allowed_use", "group_id", "split")}
        split = "test_ood" if s["meta"]["scenario"] in TEST_OOD else "train"
        items, item_gold, item_labels = mask_session(s, spans[sid], others[sid])
        out_sessions.append({"session_id": sid, "items": items, "meta": {
            "dataset_version": upstream.pop("dataset_version"), "source": SOURCE, "origin": ORIGIN,
            "allowed_use": allowed_use(ORIGIN, split), "group_id": f"privesc-{s['meta']['scenario']}", "split": split,
            "upstream_split": s["meta"]["split"], "sample": sample, **upstream}})
        for item in items:
            iid = item["item_id"]
            out_gold += [{"session_id": sid, "item_id": iid, "span_id": j, "span": sp}
                         for j, sp in enumerate(item_gold[iid])]
            out_labels += [{"session_id": sid, "item_id": iid, "start": r["start"], "end": r["end"], "gold": False,
                            "kind": r["kind"]} for r in item_labels[iid]]
    return out_sessions, out_gold, out_labels


def summary(sessions, gold, labels) -> dict:
    split_of = {s["session_id"]: s["meta"]["split"] for s in sessions}
    gold_by_split = Counter(split_of[g["session_id"]] for g in gold)
    return {"sessions_by_split": dict(sorted(Counter(split_of.values()).items())),
            "sessions_by_scenario": dict(sorted(Counter(s["meta"]["scenario"] for s in sessions).items())),
            "items": sum(len(s["items"]) for s in sessions),
            "gold_by_split": dict(sorted(gold_by_split.items())),
            "gold_by_type": dict(sorted(Counter(g["span"]["type"] for g in gold).items())),
            "labels_by_kind": dict(sorted(Counter(r["kind"] for r in labels).items()))}


# ---- verify -----------------------------------------------------------------------

def check_masks(sessions, spans, labels, texts, errors):
    """No gold in tool_input; every [KIND_n] in tool_input is a mask row and every mask row is a [KIND_n] there."""
    channels = {(s["session_id"], i["item_id"]): i["channel"] for s in sessions for i in s["items"]}
    for sid, iid, start, _, _ in spans:
        if channels[(sid, iid)] == "tool_input":
            errors.append(f"gold in tool_input {sid}/{iid} at {start}: training data keeps secrets out of tool_input")
    masks = defaultdict(set)
    for r in labels:
        key = (r["session_id"], r["item_id"])
        if key not in texts or not 0 <= r["start"] < r["end"] <= len(texts[key]):
            errors.append(f"labels: bad row {r}")
        elif r["kind"] == MASK:
            if channels[key] != "tool_input" or not MASK_TEXT.fullmatch(texts[key][r["start"]:r["end"]]):
                errors.append(f"mask {texts[key][r['start']:r['end']][:30]!r} in {key[0]}/{key[1]} ({channels[key]}): "
                              "a mask is a [KIND_n] in tool_input")
            masks[key].add((r["start"], r["end"]))
    for key, channel in channels.items():
        if channel == "tool_input":
            for m in MASK_TEXT.finditer(texts[key]):
                if (m.start(), m.end()) not in masks[key]:
                    errors.append(f"{m.group()} in {key[0]}/{key[1]} at {m.start()} has no mask row")


def check_meta(sessions, errors):
    for s in sessions:
        meta, sid = s["meta"], s["session_id"]
        split = "test_ood" if meta.get("scenario") in TEST_OOD else "train"
        if meta.get("split") != split or meta.get("group_id") != f"privesc-{meta.get('scenario')}":
            errors.append(f"{sid}: split {meta.get('split')!r}, group_id {meta.get('group_id')!r}; expected {split!r}, "
                          f"'privesc-{meta.get('scenario')}'")
    if len({json.dumps(s["meta"].get("sample"), sort_keys=True) for s in sessions}) > 1:
        errors.append("meta.sample differs between sessions; build writes one")


def shared_values(sessions, spans, texts) -> list[str]:
    """Distinct gold values found in both splits. Not an error here: the planted values are random per run, and
    what repeats is the agent's own guesses (toor, changeme, P@ssw0rd), tried in every scenario."""
    split_of = {s["session_id"]: s["meta"]["split"] for s in sessions}
    splits = defaultdict(set)
    for sid, iid, start, end, _ in spans:
        value = texts[(sid, iid)][start:end]
        if not is_common(value):
            splits[value].add(split_of[sid])
    return sorted(v for v, found in splits.items() if len(found) > 1)


def verify(out: Path, root: Path | None, synthetic_train_gold: int | None) -> dict:
    sessions_path, gold_path, labels_path = paths(out)
    errors: list[str] = []
    sessions = V.read_jsonl(sessions_path, errors)
    gold = V.read_jsonl(gold_path, errors)
    labels = V.read_jsonl(labels_path, errors)
    texts = V.check_sessions(sessions, sessions_path.name, errors)
    source, origin = V.check_meta(sessions, sessions_path.name, errors)
    if source != SOURCE or origin != ORIGIN:
        errors.append(f"source {source!r}, origin {origin!r}; expected {SOURCE}, {ORIGIN}")
    check_meta(sessions, errors)
    spans = V.check_gold(gold, texts, gold_path.name, errors)
    V.check_labels(spans, texts, errors)
    V.check_coverage(spans, texts, errors, V.excluded_on_purpose(sessions_path))
    check_masks(sessions, spans, labels, texts, errors)
    reproduction = "skipped (pass --privesc to rebuild)"
    if root is not None and sessions:
        rows = build(root, sessions[0]["meta"]["sample"])
        with tempfile.TemporaryDirectory() as directory:
            for path, new_rows in zip((sessions_path, gold_path, labels_path), rows):
                fresh = Path(directory) / path.name
                write_jsonl(fresh, new_rows)
                if fresh.read_bytes() != path.read_bytes():
                    errors.append(f"{path.name}: differs from a fresh build (edited or stale)")
        reproduction = "passed"
    if errors:
        raise ValueError(f"{len(errors)} problem(s)\n  " + "\n  ".join(errors[:50]))
    result = {"files": [p.name for p in (sessions_path, gold_path, labels_path)], **summary(sessions, gold, labels),
              "values_in_both_splits": len(shared_values(sessions, spans, texts))}
    train_gold = result["gold_by_split"].get("train", 0)
    if synthetic_train_gold is not None:
        share = train_gold / (train_gold + synthetic_train_gold)
        result["train_gold_share"] = round(share, 4)
        if share > TRAIN_SHARE:
            raise ValueError(f"privesc is {share:.1%} of train gold ({train_gold} of {train_gold + synthetic_train_gold}), "
                             f"over {TRAIN_SHARE:.0%}; build with a smaller target")
    return {**result, "labeling": "passed", "masks": "passed", "reproduction": reproduction}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="write sessions, gold and labels")
    p.add_argument("--privesc", type=Path, default=REPO_ROOT.parent / NAME, help=f"local copy of {NAME}")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "ml_build")
    size = p.add_mutually_exclusive_group(required=True)
    size.add_argument("--target-gold", type=int, help="at most this many train gold spans")
    size.add_argument("--synthetic-train-gold", type=int,
                      help=f"train gold of the synthetic set; privesc takes at most {TRAIN_SHARE * 100:.0f}%% of the total")
    size.add_argument("--sessions", type=int, help="this many train sessions")
    p = sub.add_parser("verify", help="check built files (LABELING.md, masks, splits, reproduction)")
    p.add_argument("--privesc", type=Path, help=f"local copy of {NAME}, to rebuild byte for byte")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "ml_build")
    p.add_argument("--synthetic-train-gold", type=int, help=f"fail if privesc is over {TRAIN_SHARE * 100:.0f}%% of train gold")
    args = parser.parse_args()

    if args.command == "build":
        if args.synthetic_train_gold is not None:
            sample = {"target_gold": int(args.synthetic_train_gold * TRAIN_SHARE / (1 - TRAIN_SHARE))}
        elif args.target_gold is not None:
            sample = {"target_gold": args.target_gold}
        else:
            sample = {"sessions": args.sessions}
        rows = build(args.privesc, sample)
        for path, new_rows in zip(paths(args.out), rows):
            path.parent.mkdir(parents=True, exist_ok=True)
            write_jsonl(path, new_rows)
        print(json.dumps({"sample": sample, **summary(*rows)}, indent=2))
    else:
        try:
            print(json.dumps(verify(args.out, args.privesc, args.synthetic_train_gold), indent=2))
        except ValueError as e:
            print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
