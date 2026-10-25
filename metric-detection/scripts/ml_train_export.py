"""Split the built ML training corpus into the ML handoff folder (train, val) and evaluation data (test, test_ood).

docs/README_ml-train-plan.md 5절, 6절. Inputs are sessions_ml_<NAME>.jsonl files with their gold and labels files
beside them, as ml_train_build.py (LLM and hand templates) and ml_train_privesc.py write them. The training side
(train, val) goes to a folder handed to the model as it is; the evaluation side (test, test_ood) goes to
data_test/ and data_answer/ in the metric-detection format. Converting to a model's task format is the model's job.

Every check runs on all inputs before anything is written, and if one fails nothing is written:
  origin      authored or recorded (dataset_policy.require_use(..., "ml_train") on the training side), and
              meta.allowed_use as dataset_policy.allowed_use gives it for the split (a build from before the split
              rule must be built again)
  groups      a group_id (and a session_id) in one input file only, and a group in one split
  values      no gold value that is not common (label_rules.is_common) on both sides; one that only recorded
              sessions share is reported instead (the agent's guesses, the same in every privesc scenario)
  tool_input  no gold in a tool_input
  ood         nothing of the shifted test on the training side: card_config.toml [ood] contexts, tool output format
              and kinds (also as the |of= of a prefix negative), catalog.jsonl rows of status ood
Near duplicates: every item of 100+ characters is compared with its values (gold, negatives, masks) and digits
masked, by MinHash LSH (datasketch) and then the exact Jaccard of its word 3-grams. An evaluation group with an item
at 0.8 or more to a training-side item is moved: test to train, test_ood dropped (its feature must not reach the
training side). Two recorded groups (privesc scenarios, one environment) are only reported. values and ood are
checked on the splits after the moves.

Run from the repository root:
  python metric-detection/scripts/ml_train_export.py SESSIONS_ML.jsonl [...] [--handoff DIR] [--eval-out DIR]
Writes, replacing what an earlier run wrote:
  --handoff (default metric-detection/ml_handoff/)
      sessions_<split>.jsonl, gold_<split>.jsonl, labels_<split>.jsonl for train and val; manifest.json; README.md
  --eval-out (default metric-detection/), for test and test_ood of each input NAME
      data_test/sessions_mleval_<NAME>_<split>.jsonl, data_answer/gold_mleval_<NAME>_<split>.jsonl,
      labels_mleval_<NAME>_<split>.jsonl; manifest_mleval.json
The same inputs give the same bytes. Needs datasketch (pip install datasketch==2.0.0).
Afterwards it warns about any other data_test/ file that holds a training-side group (it would be scored) or a
session of the evaluation files (the full privesc conversion holds the same test_ood runs under the same ids).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib

from dataset_build import PLACEHOLDER, REPO_ROOT, write_jsonl
from dataset_policy import EVAL_SPLITS, TRAIN_SPLITS, allowed_use, require_use
import dataset_verify as V
from label_rules import is_common
import ml_train_build as B
import ml_train_write as W

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "templates" / "ml_train"
TRAIN_SIDE, EVAL_SIDE = TRAIN_SPLITS, EVAL_SPLITS
ORIGINS = ("authored", "recorded")
EVAL_PREFIX = "mleval"
# Near duplicates (plan 5절). The pinned datasketch keeps the LSH candidates, and so the moves, the same from run to
# run; the threshold itself is applied to the exact Jaccard of the candidates.
THRESHOLD, MIN_CHARS, NGRAM, NUM_PERM = 0.8, 100, 3, 128
DATASKETCH = "2.0.0"
MASKED = "█"  # what a value becomes before two contexts are compared
WORD = re.compile(rf"\w+|{MASKED}")
HANDOFF_FILE = re.compile(r"(?:sessions|gold|labels)_(?:train|val)\.jsonl|manifest\.json|README\.md")
PREFIX_OF = re.compile(r"\{\{neg:prefix_\w+\|of=(\w+)")


@dataclass
class Bundle:
    name: str
    paths: tuple[Path, Path, Path]
    sessions: list[dict]
    gold: list[dict]
    labels: list[dict]


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def side(split: str) -> str:
    return "train" if split in TRAIN_SIDE else "eval"


def load(sessions_path: Path, errors: list[str]) -> Bundle | None:
    try:
        paths = B.paths_of(sessions_path)
    except ValueError as e:
        errors.append(str(e))
        return None
    if missing := [p for p in paths if not p.is_file()]:
        errors.append(f"{sessions_path.name}: missing {', '.join(rel(p) for p in missing)}")
        return None
    sessions, gold, labels = (V.read_jsonl(p, errors) for p in paths)
    return Bundle(paths[0].name[len("sessions_ml_"):-len(".jsonl")], paths, sessions, gold, labels)


# ---- checks on the inputs -----------------------------------------------------------

@dataclass
class Corpus:
    texts: dict[tuple[str, int], str]
    channels: dict[tuple[str, int], str]
    spans: list[tuple]  # (session_id, item_id, start, end, type)
    masked: dict[tuple[str, int], list[tuple[int, int]]]  # gold and labels ranges per item
    split_of_group: dict[str, str]
    origin_of_group: dict[str, str]


def check_inputs(bundles: list[Bundle], errors: list[str]) -> Corpus:
    texts, channels, spans, masked = {}, {}, [], defaultdict(list)
    errors += [f"two inputs are named {n}: their output files would collide"
               for n, c in Counter(b.name for b in bundles).items() if c > 1]
    file_of_group, splits_of_group, origin_of_group, file_of_session = {}, defaultdict(set), {}, {}
    for b in bundles:
        if bad := sorted({str(s.get("meta", {}).get("origin")) for s in b.sessions} - set(ORIGINS)):
            errors.append(f"{b.name}: origin {bad}; only {list(ORIGINS)} are training data")
        try:
            require_use([s for s in b.sessions if side(s["meta"].get("split")) == "train"], "ml_train")
        except PermissionError as e:
            errors.append(f"{b.name}: {e}")
        stale = [s["session_id"] for s in b.sessions if s["meta"].get("origin") in ORIGINS
                 and s["meta"].get("allowed_use") != allowed_use(s["meta"]["origin"], s["meta"].get("split"))]
        if stale:
            errors.append(f"{b.name}: {len(stale)} session(s) whose meta.allowed_use is not dataset_policy's for their "
                          f"split ({stale[:3]}); build the file again")
        item_texts = V.check_sessions(b.sessions, b.name, errors)
        texts.update(item_texts)
        channels.update({(s["session_id"], i["item_id"]): i["channel"] for s in b.sessions for i in s["items"]})
        file_spans = V.check_gold(b.gold, item_texts, b.name, errors)
        spans += file_spans
        for sid, iid, start, end, _ in file_spans:
            masked[(sid, iid)].append((start, end))
        for row in b.labels:
            key = (row.get("session_id"), row.get("item_id"))
            if key not in item_texts or not 0 <= row.get("start", -1) <= row.get("end", -1) <= len(item_texts[key]):
                errors.append(f"{b.name}: labels row {str(row)[:120]} is outside its item")
                continue
            masked[key].append((row["start"], row["end"]))
        for s in b.sessions:
            sid, meta = s["session_id"], s["meta"]
            if file_of_session.setdefault(sid, b.name) != b.name:
                errors.append(f"session_id {sid} is in {file_of_session[sid]} and {b.name}")
            group, split = meta.get("group_id"), meta.get("split")
            if split not in B.SPLITS:
                errors.append(f"{b.name}: {sid} has split {split!r}, expected one of {list(B.SPLITS)}")
            if not group:
                errors.append(f"{b.name}: {sid} has no group_id")
                continue
            if file_of_group.setdefault(group, b.name) != b.name:
                errors.append(f"group {group} is in {file_of_group[group]} and {b.name}")
            splits_of_group[group].add(split)
            origin_of_group[group] = meta.get("origin")
    for group, splits in sorted(splits_of_group.items()):
        if len(splits) > 1:
            errors.append(f"group {group} is in splits {sorted(map(str, splits))}")
    for sid, iid, start, _, _ in spans:
        if channels[(sid, iid)] == "tool_input":
            errors.append(f"gold in tool_input {sid}/{iid} at {start}: the agent writes masks there, not secrets")
    return Corpus(texts, channels, spans, masked, {g: min(map(str, s)) for g, s in splits_of_group.items()},
                  origin_of_group)


def check_values(c: Corpus, split_of_session: dict[str, str], origin_of_session: dict[str, str],
                 errors: list[str]) -> list[dict]:
    """No value that is not common on both sides (LABELING.md: common values are shared on purpose). A value only
    recorded sessions share is reported, without the value: one agent tries the same guesses (toor, changeme) in
    every privesc scenario."""
    where: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for sid, iid, start, end, _ in c.spans:
        if sid not in split_of_session:  # dropped
            continue
        value = c.texts[(sid, iid)][start:end]
        if not is_common(value) and sid not in where[value][side(split_of_session[sid])]:
            where[value][side(split_of_session[sid])].append(sid)
    reported = []
    for value, sides in where.items():
        if len(sides) < 2:
            continue
        if all(origin_of_session[sid] == "recorded" for sids in sides.values() for sid in sids):
            reported.append({"value_sha256": hashlib.sha256(value.encode()).hexdigest()[:16],
                             "train_sessions": len(sides["train"]), "eval_sessions": len(sides["eval"]),
                             "example": [sides["train"][0], sides["eval"][0]]})
        else:
            errors.append(f"gold {value[:20]!r}... is on both sides: {sides['train'][0]} and {sides['eval'][0]}")
    return sorted(reported, key=lambda r: (-r["eval_sessions"], r["value_sha256"]))


def ood_features() -> dict[str, set[str]]:
    with (ML_DIR / "card_config.toml").open("rb") as f:
        ood = tomllib.load(f)["ood"]
    rows = [json.loads(line) for line in (ML_DIR / "catalog.jsonl").read_text(encoding="utf-8").split("\n")
            if line.strip()]
    rows = [r for r in rows if r["status"] == "ood"]
    return {"context": set(ood["contexts"]), "tool_output_format": {ood["tool_output_format"]},
            "kind": set(ood["kinds"]) | {r["kind"] for r in rows if r["kind"] != "*"},
            "source_id": {r["source_id"] for r in rows}}


def template_texts(meta: dict, cache: dict) -> dict[str, str] | None:
    """Template session_id -> all its item texts, from the file meta.template names (None if it cannot be read)."""
    path = Path(meta["template"])
    path = path if path.is_absolute() else REPO_ROOT / path
    if path not in cache:
        cache[path] = None
        if path.is_file():
            cache[path] = {}
            for line in path.read_text(encoding="utf-8").split("\n"):
                if line.strip():
                    t = json.loads(line)
                    cache[path][t["session_id"]] = "\n".join(i["text"] for i in t["items"])
    return cache[path]


def check_ood(bundles: list[Bundle], split_of_session: dict[str, str], errors: list[str]):
    """The shifted test's features only in test_ood: never on the training side (plan 5.1절)."""
    feat, cache, seen = ood_features(), {}, set()
    for b in bundles:
        for s in b.sessions:
            sid, meta = s["session_id"], s["meta"]
            if side(split_of_session.get(sid, "test")) != "train":
                continue
            found = []
            if meta.get("source_id") in feat["source_id"]:
                found.append(f"catalog row {meta['source_id']}")
            card = meta.get("card") or {}
            if card.get("context") in feat["context"]:
                found.append(f"context {card['context']}")
            if card.get("tool_output_format") in feat["tool_output_format"]:
                found.append(f"tool output format {card['tool_output_format']}")
            if meta.get("template"):
                templates = template_texts(meta, cache)
                template_id = sid.rpartition("~")[0] if "variant" in meta else sid
                if templates is None or template_id not in templates:
                    found.append(f"template {meta['template']} (session {template_id}) cannot be read to check kinds")
                else:
                    text = templates[template_id]
                    kinds = {m.group("kind") for m in PLACEHOLDER.finditer(text) if m.group("kind")}
                    kinds |= set(PREFIX_OF.findall(text))
                    found += [f"kind {k}" for k in sorted(kinds & feat["kind"])]
            elif meta.get("origin") == "authored":
                found.append("no meta.template to check kinds against")
            group = meta.get("group_id")
            for f in found:
                if (group, f) not in seen:
                    seen.add((group, f))
                    errors.append(f"group {group} ({split_of_session[sid]}) has the shifted test's {f}")


# ---- near duplicates ----------------------------------------------------------------

def context_text(text: str, ranges: list[tuple[int, int]]) -> str:
    """The item text with its values and digits masked, lowercased, whitespace collapsed."""
    out, pos = [], 0
    for start, end in sorted(ranges):
        if end <= pos:
            continue
        out += [text[pos:max(start, pos)], MASKED]
        pos = end
    out.append(text[pos:])
    return re.sub(r"\s+", " ", re.sub(r"\d", "0", "".join(out))).strip().lower()


def shingles(text: str) -> set[str]:
    words = WORD.findall(text)
    return {" ".join(words[i:i + NGRAM]) for i in range(max(1, len(words) - NGRAM + 1))}


def near_duplicates(bundles: list[Bundle], c: Corpus) -> dict[tuple[str, str], dict]:
    """(eval group, training-side group) -> {similarity, items}: item pairs at THRESHOLD or more."""
    from datasketch import MinHash, MinHashLSH
    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    train, queries = [], []
    for b in bundles:
        for s in b.sessions:
            group, split = s["meta"]["group_id"], s["meta"]["split"]
            for item in s["items"]:
                key = (s["session_id"], item["item_id"])
                text = context_text(item["text"], c.masked.get(key, []))
                if len(text) >= MIN_CHARS:
                    (train if side(split) == "train" else queries).append((group, key, shingles(text)))

    def minhash(grams: set[str]) -> MinHash:
        m = MinHash(num_perm=NUM_PERM, seed=1)
        m.update_batch([g.encode("utf-8") for g in sorted(grams)])
        return m

    for n, (_, _, grams) in enumerate(train):
        lsh.insert(n, minhash(grams))
    pairs: dict[tuple[str, str], dict] = {}
    for group, key, grams in queries:
        for n in sorted(lsh.query(minhash(grams))):
            other, other_key, other_grams = train[n]
            similarity = len(grams & other_grams) / len(grams | other_grams)
            if similarity >= THRESHOLD:
                p = pairs.setdefault((group, other), {"similarity": 0.0, "items": set(), "example": None})
                p["items"].add(key)
                if similarity > p["similarity"]:
                    p["similarity"], p["example"] = similarity, [list(key), list(other_key)]
    return pairs


def resolve(pairs: dict, c: Corpus) -> tuple[dict[str, str], list[dict]]:
    """What happens to each evaluation group with a near duplicate: (group -> "train" or "drop", report rows)."""
    action, rows = {}, []
    for (group, other), p in sorted(pairs.items()):
        both_recorded = c.origin_of_group[group] == c.origin_of_group[other] == "recorded"
        split = c.split_of_group[group]
        rule = "reported" if both_recorded else ("moved_to_train" if split == "test" else "dropped")
        rows.append({"group": group, "split": split, "partner": other, "partner_split": c.split_of_group[other],
                     "similarity": round(p["similarity"], 4), "items": len(p["items"]), "example": p["example"],
                     "rule": rule})
        if not both_recorded:
            action[group] = "train" if split == "test" else "drop"
    return action, rows


# ---- writing ------------------------------------------------------------------------

def count(rows_by_file: dict[str, tuple[list[dict], list[dict], list[dict]]], channels) -> dict:
    """Sessions, items, gold and negatives of each output file, and the breakdowns of the manifest."""
    out = {}
    for name, (sessions, gold, labels) in rows_by_file.items():
        negatives = [r for r in labels if not r.get("gold")]
        out[name] = {
            "sessions": len(sessions), "items": sum(len(s["items"]) for s in sessions), "gold": len(gold),
            "negatives": len(negatives),
            "items_by_channel": dict(sorted(Counter(i["channel"] for s in sessions for i in s["items"]).items())),
            "gold_by_type": dict(sorted(Counter(g["span"]["type"] for g in gold).items())),
            "gold_by_channel": dict(sorted(Counter(channels[(g["session_id"], g["item_id"])] for g in gold).items())),
            "negatives_by_kind": dict(sorted(Counter(r["kind"] for r in negatives).items())),
            "sessions_by_origin": dict(sorted(Counter(s["meta"]["origin"] for s in sessions).items())),
            # a card is a group; hand templates and privesc have no catalog row
            "cards_by_source_id": dict(sorted(Counter(
                src for _, src in {(s["meta"]["group_id"], s["meta"].get("source_id")) for s in sessions} if src).items())),
        }
    return out


def versions(bundles: list[Bundle]) -> dict:
    def toml_version(name: str) -> str:
        with (ML_DIR / name).open("rb") as f:
            return tomllib.load(f)["version"]

    metas = [s["meta"] for b in bundles for s in b.sessions]
    # LLM templates: model and prompt (batch and message ids differ per template); hand templates: method, version
    generators = Counter(" ".join(f"{k}={v}" for k, v in sorted(m["generator"].items())
                                  if k not in ("batch_id", "custom_id", "message_id"))
                         for m in metas if isinstance(m.get("generator"), dict))
    scripts = ROOT / "scripts"
    from datasketch import __version__ as datasketch
    return {
        "dataset_version": dict(sorted(Counter(str(m.get("dataset_version")) for m in metas).items())),
        "generator": dict(sorted(generators.items())),
        "prompt": f"{W.PROMPT_VERSION} {W.prompt()[1]}",
        "cards": toml_version("card_config.toml"), "catalog": toml_version("catalog_decisions.toml"),
        "labeling_sha256": sha256(ROOT / "LABELING.md"),
        "code_sha256": {rel(p): sha256(p) for p in (scripts / "ml_train_export.py", scripts / "ml_train_build.py",
                                                     scripts / "label_rules.py", scripts / "value_gen.py",
                                                     scripts / "value_gen_catalog.py", scripts / "dataset_policy.py")},
        "datasketch": datasketch,
    }


def write_rows(paths: tuple[Path, Path, Path], rows: tuple[list[dict], list[dict], list[dict]]):
    for path, part in zip(paths, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(path, part)


def json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def clear_handoff(folder: Path, errors: list[str]):
    if not folder.exists():
        return
    stray = sorted(p.name for p in folder.iterdir() if not HANDOFF_FILE.fullmatch(p.name))
    if stray:
        errors.append(f"{folder} holds files this script did not write ({stray[:5]}); pick an empty folder")


def eval_paths(out: Path, name: str, split: str) -> tuple[Path, Path, Path]:
    stem = f"{EVAL_PREFIX}_{name}_{split}"
    return (out / "data_test" / f"sessions_{stem}.jsonl", out / "data_answer" / f"gold_{stem}.jsonl",
            out / f"labels_{stem}.jsonl")


def old_eval_outputs(out: Path) -> list[Path]:
    return sorted([*(out / "data_test").glob(f"sessions_{EVAL_PREFIX}_*.jsonl"),
                   *(out / "data_answer").glob(f"gold_{EVAL_PREFIX}_*.jsonl"),
                   *out.glob(f"labels_{EVAL_PREFIX}_*.jsonl"), *out.glob(f"manifest_{EVAL_PREFIX}.json")])


def stray_in_data_test(out: Path, written: set[Path], train_groups: set[str], eval_ids: set[str]) -> list[str]:
    """data_test/ files besides this run's that hold a training-side group, which an evaluation would score, or a
    session of the evaluation files, which a total over datasets would count twice."""
    warnings = []
    for path in sorted((out / "data_test").glob("sessions*.jsonl")):
        if path.resolve() in written:
            continue
        with path.open(encoding="utf-8") as f:
            sessions = [json.loads(line) for line in f if line.strip()]
        groups = {s.get("meta", {}).get("group_id") for s in sessions}
        if hit := sorted(g for g in groups & train_groups if g):
            warnings.append(f"{rel(path)} holds {len(hit)} training-side group(s) ({', '.join(hit[:3])}); "
                            "move it out of data_test/ so no evaluation scores it")
        if hit := sorted({s.get("session_id") for s in sessions} & eval_ids):
            warnings.append(f"{rel(path)} holds {len(hit)} session(s) of the evaluation files under the same ids "
                            f"({', '.join(hit[:3])}); keep one of the two in data_test/")
    return warnings


def export(inputs: list[Path], handoff: Path, eval_out: Path) -> dict:
    errors: list[str] = []
    try:
        import datasketch
        if datasketch.__version__ != DATASKETCH:
            errors.append(f"datasketch {datasketch.__version__}; pin {DATASKETCH} so the same inputs give the same "
                          f"moves (pip install datasketch=={DATASKETCH})")
    except ImportError:
        errors.append(f"datasketch is not installed (pip install datasketch=={DATASKETCH})")
    bundles = sorted((b for p in inputs if (b := load(p, errors))), key=lambda b: b.name)
    clear_handoff(handoff, errors)
    if errors:
        raise ValueError("\n  ".join(errors))
    corpus = check_inputs(bundles, errors)
    if errors:
        raise ValueError("\n  ".join(errors))

    pairs = near_duplicates(bundles, corpus)
    action, near = resolve(pairs, corpus)
    split_of_session, origin_of_session = {}, {}
    for b in bundles:
        for s in b.sessions:
            origin_of_session[s["session_id"]] = s["meta"]["origin"]
            act = action.get(s["meta"]["group_id"])
            if act != "drop":
                split_of_session[s["session_id"]] = "train" if act == "train" else s["meta"]["split"]
    shared_values = check_values(corpus, split_of_session, origin_of_session, errors)
    check_ood(bundles, split_of_session, errors)
    if errors:
        raise ValueError("\n  ".join(errors))

    # rows per output: training side merged per split, evaluation side per input and split
    handoff_rows: dict[str, tuple[list, list, list]] = {split: ([], [], []) for split in TRAIN_SIDE}
    eval_rows: dict[tuple[str, str], tuple[list, list, list]] = {}
    for b in bundles:
        gold_of, labels_of = defaultdict(list), defaultdict(list)
        for g in b.gold:
            gold_of[g["session_id"]].append(g)
        for r in b.labels:
            labels_of[r["session_id"]].append(r)
        for s in b.sessions:
            sid = s["session_id"]
            if sid not in split_of_session:
                continue
            split = split_of_session[sid]
            if split != s["meta"]["split"]:
                s = {**s, "meta": {**s["meta"], "split": split, "split_moved_from": s["meta"]["split"],
                                   "allowed_use": allowed_use(s["meta"]["origin"], split)}}
            target = handoff_rows[split] if split in TRAIN_SIDE else eval_rows.setdefault((b.name, split), ([], [], []))
            target[0].append(s)
            target[1].extend(gold_of[sid])
            target[2].extend(labels_of[sid])

    # write: the handoff folder anew, the evaluation files after removing an earlier run's
    if handoff.exists():
        shutil.rmtree(handoff)
    for path in old_eval_outputs(eval_out):
        path.unlink()
    files = {}
    for split, rows in handoff_rows.items():
        paths = tuple(handoff / f"{kind}_{split}.jsonl" for kind in ("sessions", "gold", "labels"))
        write_rows(paths, rows)
        files.update({p.name: sha256(p) for p in paths})
    eval_files, written = {}, set()
    for (name, split), rows in sorted(eval_rows.items()):
        paths = eval_paths(eval_out, name, split)
        write_rows(paths, rows)
        eval_files.update({p.relative_to(eval_out).as_posix(): sha256(p) for p in paths})
        written.add(paths[0].resolve())

    train_groups = sorted({s["meta"]["group_id"] for rows in handoff_rows.values() for s in rows[0]})
    common = {
        "inputs": [{"name": b.name, **{kind: {"path": rel(p), "sha256": sha256(p)}
                                       for kind, p in zip(("sessions", "gold", "labels"), b.paths)}} for b in bundles],
        "versions": versions(bundles),
        "near_duplicates": {"threshold": THRESHOLD, "min_chars": MIN_CHARS, "shingle": f"word {NGRAM}-gram",
                            "num_perm": NUM_PERM, "masked": "gold, labels ranges and digits",
                            "rule": "test -> train, test_ood dropped, recorded with recorded reported only",
                            "pairs": near},
        "recorded_values_on_both_sides": shared_values,
    }
    by_input = {}
    for b in bundles:
        ids = {s["session_id"] for s in b.sessions}
        for split in TRAIN_SIDE:
            by_input[f"{split}/{b.name}"] = tuple([r for r in part if r["session_id"] in ids]
                                                  for part in handoff_rows[split])
    handoff_manifest = {**common, "files": files, "counts": count(handoff_rows, corpus.channels),
                        "counts_by_input": count(by_input, corpus.channels)}
    (handoff / "manifest.json").write_text(json_text(handoff_manifest), encoding="utf-8")
    (handoff / "README.md").write_text(HANDOFF_README, encoding="utf-8")
    eval_manifest = {**common, "files": eval_files,
                     "counts": count({f"{name}/{split}": rows for (name, split), rows in sorted(eval_rows.items())},
                                     corpus.channels),
                     "training_side_groups": train_groups}
    (eval_out / f"manifest_{EVAL_PREFIX}.json").write_text(json_text(eval_manifest), encoding="utf-8")

    return {"handoff": rel(handoff), "eval": sorted(eval_files),
            "sessions": {"train": len(handoff_rows["train"][0]), "val": len(handoff_rows["val"][0]),
                         **{f"{n}/{s}": len(r[0]) for (n, s), r in sorted(eval_rows.items())}},
            "near_duplicates": dict(Counter(row["rule"] for row in near)),
            "recorded_values_on_both_sides": len(shared_values),
            "warnings": stray_in_data_test(eval_out, written, set(train_groups),
                                           {s["session_id"] for rows in eval_rows.values() for s in rows[0]})}


HANDOFF_README = """\
# PromptGuard ML 학습 데이터 (train, val)

코딩 에이전트가 주고받는 텍스트에서 자격증명을 찾는 모델의 학습 데이터다. metric-detection의 형식 그대로이며, 모델의
과제 형식(토큰 태그 등)으로는 바꾸지 않았다. 바꾸는 것은 모델 쪽이 한다. 평가용(test, test_ood)은 이 폴더에 없다.

promptguard-data 저장소의 `metric-detection/scripts/ml_train_export.py`가 만들었다. 같은 입력이면 바이트 단위로 같은
파일이 나온다. 입력, 버전, 수, 파일 sha256은 `manifest.json`에 있다.

**값은 모두 실제 형식을 따르는 가짜 값이다.** 실제 인증에 쓰지 말고, git에 올리지 않는다(GitHub push protection이
진짜 비밀로 보고 막는다).

## 파일

| 파일 | 한 줄 | 내용 |
|---|---|---|
| `sessions_train.jsonl`, `sessions_val.jsonl` | 세션 하나 | `session_id`, `items`, `meta` |
| `gold_train.jsonl`, `gold_val.jsonl` | 정답 span 하나 | `session_id`, `item_id`, `span_id`, `span` (`start`, `end`, `type`) |
| `labels_train.jsonl`, `labels_val.jsonl` | 정답이 아닌 구간 하나 | `session_id`, `item_id`, `start`, `end`, `gold` (false), `kind` |
| `manifest.json` | | 입력 파일과 sha256, split·출처·유형·채널·음성 kind별 수, 카탈로그 행별 카드 수, 버전, 거의 같은 문맥 처리 |

세 파일의 줄은 sessions 순서, 그 안에서 item 순서를 따른다. span이 없는 item은 gold에 나오지 않는다.

## 형식

```json
{"session_id": "c0001~0",
 "items": [{"item_id": 0, "turn_id": "t0", "channel": "prompt", "text": "..."},
           {"item_id": 1, "turn_id": "t0", "channel": "tool_output", "text": "DB_PASSWORD=..."}],
 "meta": {"split": "train", "group_id": "c0001", "origin": "authored", "...": "..."}}
{"session_id": "c0001~0", "item_id": 1, "span_id": 0, "span": {"start": 12, "end": 28, "type": "PASSWORD"}}
{"session_id": "c0001~0", "item_id": 1, "start": 40, "end": 52, "gold": false, "kind": "reference"}
```

- `start`, `end`: item `text` 안의 위치. Python 문자열 인덱스(코드 포인트)이고 `end`는 포함하지 않는다.
- `type`: `PASSWORD`, `SECRET`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY`. 한 item 안의 정답 span은 겹치지 않는다.
- `channel`: `prompt`(사용자 메시지), `instructions`(시스템 프롬프트에 들어가는 지침), `tool_input`(모델이 쓴 도구
  인자), `tool_output`(도구 결과).
- 정답 기준은 저장소의 `metric-detection/LABELING.md` 하나다. 정답은 "텍스트를 읽는 사람이 자격증명 자리에 들어간 값이라고
  판정할 수 있는 리터럴 값"이고, span은 값 그 자체다(따옴표 안쪽, `Bearer ` 뒤, URL은 비밀번호 부분만, 개인키는 BEGIN 줄부터
  END 줄까지). 같은 세션에서 고유한 정답 값이 다른 곳에 다시 나오면 그곳도 정답이다(흔한 값은 자격증명 자리에서만).
- **`tool_input`에는 정답이 없다.** 배포 환경에서 에이전트는 PromptGuard가 가린 표시만 보므로, 비밀을 다시 쓰는 명령에는
  값 대신 그 표시 `[KIND_n]`(예: `[PASSWORD_1]`)이 들어 있다. labels에 `mask`로 남는다.

## meta

| 필드 | 뜻 |
|---|---|
| `split` | `train` 또는 `val`. 모델 선택과 조기 종료는 val로 한다 |
| `split_moved_from` | 있으면 `test`: 학습 쪽과 거의 같은 문맥이라 평가 쪽에서 옮겨 온 group(manifest의 `near_duplicates`) |
| `group_id` | 맥락 원형 하나(LLM 템플릿 카드 `c0001`, 손 템플릿 `hand-…`, privesc 시나리오 `privesc-…`). 한 group은 한 split에만 있다. 교차 검증으로 나눌 때도 group 단위로 나눈다 |
| `variant` | 같은 템플릿에서 값만 바꿔 만든 몇 번째 세션인지 (`session_id`의 `~k`) |
| `origin` | `authored`(맥락에 맞게 직접 쓴 합성) 또는 `recorded`(비밀을 심은 환경에서 실제로 돌린 에이전트 기록, privesc) |
| `source`, `template` | 만든 생성기와 템플릿 파일 |
| `source_id`, `card`, `negatives`, `boundary_rule`, `generator` | LLM 템플릿의 비밀 출처 카탈로그 행, 카드(문맥, 서식, 도구 형식, 언어), 넣은 어려운 음성, 경계 규칙, 생성 모델·프롬프트·batch |

## labels의 kind

labels는 정답이 아닌 구간이다. 대부분 일부러 넣은 어려운 음성이라, 키 이름만 보고 판정하면 틀리게 되어 있다.

| kind | 뜻 | 예 |
|---|---|---|
| `redaction`, `prefix_redaction` | 지우거나 가린 흔적 | `********`, `[REDACTED]`, `ghp_xxxx…` |
| `template`, `prefix_template`, `template_ko` | 채워 넣을 자리 표시, 안내문 | `<your-token>`, `YOUR_API_KEY`, `glpat-YOUR_TOKEN_HERE` |
| `reference`, `secret_ref` | 변수·환경변수·비밀 저장소 참조 | `${DB_PASS}`, `os.environ["KEY"]` |
| `code` | 값이 아닌 코드 표현식 | `kwargs.get(`, `password: string;` |
| `doc_example`, `prefix_example` | 문서의 예시 값 | `AKIAIOSFODNN7EXAMPLE` |
| `descriptor` | 값이 아니라 값을 가리키는 말 | `new password` |
| `empty` | 빈 값 (start = end) | `DB_PASSWORD=` |
| `hash` | 단방향 해시 | `$6$…`, bcrypt |
| `identifier` | 사용자명, id, 커밋 해시, request id 등. 정답 값과 같은 문자열이 식별자 자리에 다시 나온 곳도 이 kind다 | UUID(`"id"` 자리), ARN |
| `not_propagated` | 정답 값과 같은 흔한 문자열이 자격증명 자리 밖에 나온 곳(정답 아님) | 비밀번호가 `root`일 때 `/root` |
| `non_credential` | 자격증명이 아닌 비밀·개인정보 | CSRF 토큰, PIN |
| `setting`, `auth_setting` | 자격증명 단어가 든 설정값 | `max_tokens = 4096`, `password_min_length = 12` |
| `public_key`, `public_key_raw`, `pem_header`, `wallet_address` | 공개키, 인증서, 본문 없는 PEM 머리글, 지갑 주소 | `ssh-ed25519 AAAA…` |
| `mask` | tool_input에서 에이전트가 쓴 PromptGuard 표시 | `[PASSWORD_1]` |

privesc의 labels는 거의 다 `identifier`(`ls -l` 소유자 칸의 `root` 같은 것)와 `not_propagated`, `mask`다. 음성 kind별
비율이나 가중치는 출처를 섞지 말고 manifest의 `counts_by_input`으로 출처마다 본다.

labels에 없는 구간이 모두 평범한 텍스트라는 뜻은 아니다. 정답이 아닌 것은 gold에 없는 모든 구간이고, labels는 그중
이름을 붙여 둔 것이다.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sessions", type=Path, nargs="+", help="sessions_ml_<NAME>.jsonl files")
    parser.add_argument("--handoff", type=Path, default=ROOT / "ml_handoff", help="training-side folder")
    parser.add_argument("--eval-out", type=Path, default=ROOT, help="folder holding data_test/ and data_answer/")
    args = parser.parse_args()
    try:
        report = export(args.sessions, args.handoff, args.eval_out)
    except ValueError as e:
        print(f"FAILED, nothing written:\n  {e}", file=sys.stderr)
        sys.exit(1)
    for warning in report["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
