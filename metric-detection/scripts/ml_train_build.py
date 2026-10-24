"""Build and verify the ML training corpus from session templates (docs/README_ml-train-plan.md).

Kept apart from dataset_build.py so the evaluation corpora keep their generator as it is. Templates use the
dataset_build placeholder syntax and generators (metric-detection/templates/README.md), plus:
  {{kind:name}} with a value_gen.SECRET_KINDS kind      service formats, password families, private keys
  {{neg:kind}}                                          a value that is not gold (value_gen.NEGATIVE_KINDS),
                                                        recorded in the labels file
  |wrap=N, |truncate=N                                  terminal wrapping; a key block cut after N body lines
  meta.split (required)        train, val, test or test_ood; part of every value seed. A group stays in one split
  meta.variants                build the session N times with different values (session_id~k)
  meta.value_profile           mltrain: the base kinds (password, token, ...) drawn from varied families
A generated value that does not stand as gold where it landed is drawn again (render_session).

Run from the repository root:
  python metric-detection/scripts/ml_train_build.py build T.jsonl [T2.jsonl ...] [--out DIR]
  python metric-detection/scripts/ml_train_build.py verify DIR/data_test/sessions_ml_T.jsonl [...]
  python metric-detection/scripts/ml_train_build.py report DIR/data_test/sessions_ml_T.jsonl [...]
build writes, under --out (default metric-detection/), data_test/sessions_ml_<T>.jsonl,
data_answer/gold_ml_<T>.jsonl and labels_ml_<T>.jsonl. Every session is origin authored (ml_train).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys
import tempfile

from dataset_build import (CHANNELS, GENERATORS, PLACEHOLDER, REPO_ROOT, SUSPICIOUS, TYPES, VERSION, transform,
                           uri_parts, write_jsonl)
from dataset_policy import ALLOWED_USE
import dataset_verify as V
from label_rules import classify, exclusion_kind, is_common, normalize_span
import value_gen

SOURCE = "ml_train_template"
ORIGIN = "authored"
SPLITS = ("train", "val", "test", "test_ood")
REDRAWS = 8
NEG = "neg:"  # Slot.kind prefix of a {{neg:kind}} value: recorded in labels, never gold
KINDS = {**GENERATORS, **{kind: (kind_type, lambda seed, gen=gen: gen(value_gen.Draw(seed)))
                          for kind, (kind_type, gen) in value_gen.SECRET_KINDS.items()}}
assert len(KINDS) == len(GENERATORS) + len(value_gen.SECRET_KINDS)


@dataclass(frozen=True)
class Slot:
    value: str
    kind: str  # gold type, or NEG + negative kind
    key: str | None = None  # the placeholder's kind:name, to draw it again


def extra_transform(text: str, name: str, arg: str | None) -> tuple[str, str | None]:
    if name == "wrap":
        # Terminal wrapping: a line break every N characters, inside the one gold span (LABELING.md 경계).
        n = int(arg or 80)
        return "\n".join(text[i:i + n] for i in range(0, len(text), n)), None
    if name == "truncate":
        # A private key block cut after N body lines, as `head` prints it; gold runs to the last body line.
        lines = text.split("\n")
        if not lines[0].startswith("-----BEGIN") or not arg or int(arg) < 1:
            raise ValueError("truncate=N needs a PEM block and N >= 1 body lines (a BEGIN line alone is not gold)")
        return "\n".join(lines[:1 + int(arg)]), None
    return transform(text, name, arg)


def apply_transforms(out: str, kind_type: str, transforms: list[str]) -> tuple[str, str]:
    for t in transforms:
        t_name, _, t_arg = t.partition("=")
        out, new_type = extra_transform(out, t_name, t_arg or None)
        kind_type = new_type or kind_type
    return out, kind_type


def parse_text(text: str, seed: str, unnamed: list[int], profile: str | None,
               redraw: dict[str, int]) -> list[str | Slot]:
    """Template text as literal strings and Slots. redraw[kind:name] = n draws that value for the n-th time, from
    a seed of its own and a family without common strings (value_gen.NOT_COMMON)."""
    parts, pos = [], 0
    for m in PLACEHOLDER.finditer(text):
        parts.append(text[pos:m.start()])
        pos = m.end()
        if m.group(0) == "\\{{":
            parts.append("{{")
            continue
        if m.group("type"):
            if m.group("type") not in TYPES:
                raise ValueError(f"unknown gold type in {m.group(0)!r}, expected one of {sorted(TYPES)}")
            parts.append(Slot(m.group("literal"), m.group("type")))
            continue
        kind, name = m.group("kind"), m.group("name")
        transforms = list(filter(None, m.group("transforms").split("|")))
        if kind == "neg":
            if name not in value_gen.NEGATIVE_KINDS:
                raise ValueError(f"{m.group(0)!r}: expected {{{{neg:KIND}}}}, KIND one of {sorted(value_gen.NEGATIVE_KINDS)}")
            unnamed[0] += 1  # every negative is a new value
            out = value_gen.NEGATIVE_KINDS[name][0](value_gen.Draw(f"{seed}:neg:{name}:#{unnamed[0]}"))
            parts.append(Slot(apply_transforms(out, "", transforms)[0], NEG + name))
            continue
        if kind not in KINDS:
            raise ValueError(f"unknown kind in {m.group(0)!r}, expected one of {sorted(KINDS)} or neg")
        if name is None:  # each unnamed placeholder gets its own value
            unnamed[0] += 1
            name = f"#{unnamed[0]}"
        key = f"{kind}:{name}"
        source = value_gen.PROFILE[profile].get(kind, kind) if profile else kind
        if key in redraw:
            source = value_gen.NOT_COMMON.get(source, source)
        kind_type, generate = KINDS[source]
        out = generate(f"{seed}:{kind}:{name}" + (f":redraw{redraw[key]}" if key in redraw else ""))
        if kind == "db_uri":
            if any(t != "url" for t in transforms):
                raise ValueError(f"{m.group(0)!r}: db_uri supports only the url transform")
            before, password, after = uri_parts(out, encoded=bool(transforms))
            parts.extend((before, Slot(password.value, "PASSWORD", key), after))
            continue
        out, kind_type = apply_transforms(out, kind_type, transforms)
        parts.append(Slot(out, kind_type, key))
    parts.append(text[pos:])
    for part in parts:
        if isinstance(part, str) and (m := SUSPICIOUS.search(part)):
            raise ValueError(f"{m.group(0)!r} looks like a placeholder but is not one; escape it as \\{{{{ if it is literal text")
    return [p for p in parts if p != ""]


def render(parts) -> tuple[str, list[dict], list[dict]]:
    """Item text with its gold spans and {{neg:kind}} ranges."""
    text, spans, negs = "", [], []
    for part in parts:
        if isinstance(part, str):
            text += part
            continue
        start = len(text)
        text += part.value
        if part.kind.startswith(NEG):
            negs.append({"start": start, "end": len(text), "kind": part.kind[len(NEG):]})
        else:
            spans.append({"start": start, "end": len(text), "type": part.kind, "key": part.key})
    return text, spans, negs


def unfit(text: str, start: int, end: int) -> str | None:
    """Why a generated value does not stand as gold where it landed, if a new draw could fix it: a common string
    outside a credential position (LABELING.md 퍼뜨림 기준), or a value label_rules reads as an excluded kind or whose
    edge characters fall outside the 경계 rules there (a final "." with no quote after it)."""
    value = text[start:end]
    if value.startswith("-----BEGIN"):
        return None
    if is_common(value) and classify(text, start, end)[0] != "slot":
        return "common"
    if exclusion_kind(text, start, end) or normalize_span(text, start, end) != (start, end):
        return "shape"
    return None


def render_session(items: list[dict], seed: str, profile: str | None) -> list[tuple[str, list[dict], list[dict]]]:
    redraw: dict[str, int] = {}
    while True:
        unnamed, rendered, bad = [0], [], set()
        for i, item in enumerate(items):
            try:
                rendered.append(render(parse_text(item["text"], seed, unnamed, profile, redraw)))
            except ValueError as e:
                raise ValueError(f"item {i}: {e}") from None
            text, spans, _ = rendered[-1]
            bad |= {sp["key"] for sp in spans if sp["key"] and unfit(text, sp["start"], sp["end"])}
        retry = {key for key in bad if redraw.get(key, 0) < REDRAWS}
        if not retry:
            return rendered  # verify reports what a redraw could not fix
        for key in retry:
            redraw[key] = redraw.get(key, 0) + 1


def template_name(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def build(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """(sessions, gold, labels) of one template file."""
    sessions, gold, labels = [], [], []
    seen, splits = set(), {}
    template = template_name(path)
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        s = json.loads(line)
        if set(s) - {"session_id", "items", "meta"} or not {"session_id", "items", "meta"} <= set(s):
            raise ValueError(f"{where}: a session needs session_id, items and meta; got {sorted(s)}")
        sid, meta = s["session_id"], dict(s["meta"])
        owned = {"dataset_version": VERSION, "source": SOURCE, "template": template, "origin": ORIGIN,
                 "allowed_use": ALLOWED_USE[ORIGIN]}
        for key in (*owned, "variant"):
            if key in meta:
                raise ValueError(f"{where}: meta.{key} is set by the builder; remove it from the template")
        meta = {**owned, "group_id": sid, **meta}
        split, profile, variants = meta.get("split"), meta.get("value_profile"), meta.get("variants")
        if split not in SPLITS:
            raise ValueError(f"{where}: meta.split {split!r}, expected one of {list(SPLITS)}")
        if profile is not None and profile not in value_gen.PROFILE:
            raise ValueError(f"{where}: meta.value_profile {profile!r}, expected one of {sorted(value_gen.PROFILE)}")
        if variants is not None and not (isinstance(variants, int) and variants >= 1):
            raise ValueError(f"{where}: meta.variants must be an integer >= 1")
        # A group shares its context, so all of it goes to one split (no train/test leak).
        if splits.setdefault(meta["group_id"], split) != split:
            raise ValueError(f"{where}: group {meta['group_id']} is in splits {splits[meta['group_id']]!r} and {split!r}")
        for i, item in enumerate(s["items"]):
            if set(item) - {"item_id", "turn_id", "channel", "text"} or not {"channel", "text"} <= set(item):
                raise ValueError(f"{where}: item {i} needs channel and text, and may have item_id and turn_id")
            if item.get("item_id", i) != i:
                raise ValueError(f"{where}: item at index {i} has item_id {item['item_id']!r}")
            if item["channel"] not in CHANNELS:
                raise ValueError(f"{where}: item {i} unknown channel {item['channel']!r}")
        for k in range(variants or 1):
            session_id = f"{sid}~{k}" if variants else sid
            if session_id in seen:
                raise ValueError(f"{where}: duplicate session_id {session_id}")
            seen.add(session_id)
            seed = f"{split}:{path.stem}:{sid}" + (f"~{k}" if variants else "")
            try:
                rendered = render_session(s["items"], seed, profile)
            except ValueError as e:
                raise ValueError(f"{where}: {e}") from None
            out_items = []
            for item_id, (item, (text, spans, negs)) in enumerate(zip(s["items"], rendered)):
                out_items.append({"item_id": item_id, "turn_id": item.get("turn_id", "t0"),
                                  "channel": item["channel"], "text": text})
                gold += [{"session_id": session_id, "item_id": item_id, "span_id": j,
                          "span": {"start": sp["start"], "end": sp["end"], "type": sp["type"]}}
                         for j, sp in enumerate(spans)]
                labels += [{"session_id": session_id, "item_id": item_id, "start": ng["start"], "end": ng["end"],
                            "gold": False, "kind": ng["kind"]} for ng in negs]
            sessions.append({"session_id": session_id, "items": out_items,
                             "meta": {**meta, "variant": k} if variants else meta})
    return sessions, gold, labels


def paths(out: Path, stem: str) -> tuple[Path, Path, Path]:
    return (out / "data_test" / f"sessions_ml_{stem}.jsonl", out / "data_answer" / f"gold_ml_{stem}.jsonl",
            out / f"labels_ml_{stem}.jsonl")


def paths_of(sessions_path: Path) -> tuple[Path, Path, Path]:
    stem = re.fullmatch(r"sessions_ml_(.+)\.jsonl", sessions_path.name)
    if not stem:
        raise ValueError(f"{sessions_path.name} is not a sessions_ml_*.jsonl file")
    return paths(sessions_path.parents[1], stem.group(1))


# ---- verify -----------------------------------------------------------------------

def check_positions(spans, texts, errors):
    """LABELING.md 퍼뜨림 기준 at the inserted positions: never gold in an identifier position, and a common value
    only in a credential one. Stricter than dataset_verify, which checks only the occurrences outside gold."""
    for sid, iid, start, end, kind in spans:
        if kind == "PRIVATE_KEY":  # a key block is gold by its format alone
            continue
        text = texts[(sid, iid)]
        verdict, rule = classify(text, start, end)
        if verdict == "ident" or (is_common(text[start:end]) and verdict != "slot"):
            errors.append(f"gold {text[start:end][:20]!r}... in {sid}/{iid} at {start} is in a {verdict} position "
                          f"({rule}): LABELING.md does not count it as gold; rewrite the template there")


def check_negatives(labels, texts, errors):
    for row in labels:
        key = (row["session_id"], row["item_id"])
        if key not in texts or not 0 <= row["start"] <= row["end"] <= len(texts[key]):
            errors.append(f"labels: bad row {row}")
            continue
        want = value_gen.NEGATIVE_KINDS[row["kind"]][1]
        got = exclusion_kind(texts[key], row["start"], row["end"])
        if want and got != want:
            errors.append(f"neg:{row['kind']} in {key[0]}/{key[1]} at {row['start']} reads as {got or 'a credential'} "
                          f"to label_rules, not {want}")


def check_splits(sessions, spans, texts, errors) -> Counter:
    """Every group in one split, and no distinct gold value shared by two splits."""
    split_of, group_split = {}, {}
    for s in sessions:
        split, group = s["meta"].get("split"), s["meta"].get("group_id")
        split_of[s["session_id"]] = split
        if group_split.setdefault(group, split) != split:
            errors.append(f"group {group} is in splits {group_split[group]!r} and {split!r}")
    seen: dict[str, str] = {}
    for sid, iid, start, end, _ in spans:
        value = texts[(sid, iid)][start:end]
        if is_common(value):
            continue  # common values are shared on purpose (LABELING.md: the same word in any session)
        if seen.setdefault(value, split_of[sid]) != split_of[sid]:
            errors.append(f"gold {value[:20]!r}... appears in splits {seen[value]!r} and {split_of[sid]!r}")
    return Counter(split_of.values())


def verify(sessions_path: Path, rebuild: bool = True) -> dict:
    sessions_path, gold_path, labels_path = paths_of(sessions_path)
    errors: list[str] = []
    sessions = V.read_jsonl(sessions_path, errors)
    gold = V.read_jsonl(gold_path, errors)
    labels = V.read_jsonl(labels_path, errors) if labels_path.is_file() else []
    texts = V.check_sessions(sessions, sessions_path.name, errors)
    source, origin = V.check_meta(sessions, sessions_path.name, errors)
    if source != SOURCE or origin != ORIGIN:
        errors.append(f"{sessions_path.name}: source {source!r}, origin {origin!r}; expected {SOURCE}, {ORIGIN}")
    spans = V.check_gold(gold, texts, gold_path.name, errors)
    V.check_labels(spans, texts, errors)
    V.check_coverage(spans, texts, errors)
    check_positions(spans, texts, errors)
    check_negatives(labels, texts, errors)
    splits = check_splits(sessions, spans, texts, errors)
    reproduction = "skipped"
    if rebuild and sessions:
        template = Path(sessions[0]["meta"]["template"])
        rows = build(template if template.is_absolute() else REPO_ROOT / template)
        with tempfile.TemporaryDirectory() as directory:
            for path, new_rows in zip((sessions_path, gold_path, labels_path), rows):
                fresh = Path(directory) / path.name
                write_jsonl(fresh, new_rows)
                old = path.read_bytes() if path.is_file() else b""
                if fresh.read_bytes() != old:
                    errors.append(f"{path.name}: differs from a fresh build (edited or stale)")
        reproduction = "passed"
    if errors:
        raise ValueError(f"{sessions_path.name}: {len(errors)} problem(s)\n  " + "\n  ".join(errors[:50]))
    return {"files": [sessions_path.name, gold_path.name, labels_path.name], "sessions": len(sessions),
            "items": len(texts), "items_with_spans": len({(s[0], s[1]) for s in spans}), "spans": len(spans),
            "spans_by_type": dict(sorted(Counter(s[4] for s in spans).items())),
            "negatives_by_kind": dict(sorted(Counter(r["kind"] for r in labels).items())),
            "sessions_by_split": dict(sorted(splits.items())), "labeling": "passed", "reproduction": reproduction}


# ---- report -----------------------------------------------------------------------

def shape_features(value: str) -> list[float]:
    counts = Counter(value)
    entropy = -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())
    classes = [any(ch.islower() for ch in value), any(ch.isupper() for ch in value),
               any(ch.isdigit() for ch in value), any(not ch.isalnum() for ch in value)]
    return [len(value), math.log(len(value)), entropy, *map(float, classes), sum(classes),
            sum(ch in "0123456789abcdef" for ch in value) / len(value)]


def report(sessions_paths: list[Path]) -> dict:
    """Shape of the values (docs/README_ml-train-plan.md 4.3): how well length, character classes and entropy
    alone tell gold from the hard negatives, and how concentrated each type is on one (length, classes) cell."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    values, by_type = [], defaultdict(Counter)
    for sessions_path in sessions_paths:
        s_path, g_path, l_path = paths_of(sessions_path)
        texts = {(s["session_id"], i["item_id"]): i["text"] for s in V.read_jsonl(s_path, []) for i in s["items"]}
        for g in V.read_jsonl(g_path, []):
            v = texts[(g["session_id"], g["item_id"])][g["span"]["start"]:g["span"]["end"]]
            values.append((v, 1))
            by_type[g["span"]["type"]][(len(v), tuple(shape_features(v)[3:7]))] += 1
        if l_path.is_file():
            values += [(texts[(r["session_id"], r["item_id"])][r["start"]:r["end"]], 0)
                       for r in V.read_jsonl(l_path, []) if r["end"] > r["start"]]
    out = {"gold": sum(y for _, y in values), "negatives": sum(1 - y for _, y in values)}
    if out["gold"] >= 10 and out["negatives"] >= 10:
        X, y = [shape_features(v) for v, _ in values], [y for _, y in values]
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        out["shape_only_auroc"] = round(float(cross_val_score(model, X, y, cv=5, scoring="roc_auc").mean()), 3)
    out["top_cell_share_by_type"] = {t: round(c.most_common(1)[0][1] / sum(c.values()), 3) for t, c in sorted(by_type.items())}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="build sessions, gold and labels from templates")
    p.add_argument("templates", type=Path, nargs="+")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    p = sub.add_parser("verify", help="check built files (LABELING.md, positions, negatives, splits, reproduction)")
    p.add_argument("sessions", type=Path, nargs="+")
    p.add_argument("--skip-rebuild", action="store_true", help="skip the byte-reproduction check")
    p = sub.add_parser("report", help="value shape statistics over built files")
    p.add_argument("sessions", type=Path, nargs="+")
    args = parser.parse_args()

    if args.command == "build":
        for template in args.templates:
            sessions, gold, labels = build(template)
            for path, rows in zip(paths(args.out, template.stem), (sessions, gold, labels)):
                path.parent.mkdir(parents=True, exist_ok=True)
                write_jsonl(path, rows)
            print(f"{template.name}: {len(sessions)} sessions, {sum(len(s['items']) for s in sessions)} items, "
                  f"{len(gold)} gold spans, {len(labels)} negatives")
    elif args.command == "verify":
        failed = False
        for sessions_path in args.sessions:
            try:
                print(json.dumps(verify(sessions_path, not args.skip_rebuild), ensure_ascii=False, indent=2))
            except ValueError as e:
                failed = True
                print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1 if failed else 0)
    else:
        print(json.dumps(report(args.sessions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
