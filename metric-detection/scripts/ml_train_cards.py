"""Draw the cards the LLM writes ML training templates from (docs/README_ml-train-plan.md 2절, 3절).

A card is the work order for one template: context and format, the secrets as the exact placeholders to use, the
channel and repetition of each, hard negatives, a boundary rule to exercise, language, tool formats and size. The
context x secret type cells are allocated to match card_config.toml exactly; everything else is drawn per card
from a seed, so the same config always yields the same cards.

Each card also takes one row of the secret-source catalog (catalog.jsonl, ml_train_catalog.py) as its scene: within
a cell the rows that fit its context and type take turns. The row gives the primary secret's kind, scene hints and
a contrast, the hard negative the row pairs with its secret. Rows for the shifted test appear only in test_ood cards.

Run from the repository root:
  python metric-detection/scripts/ml_train_cards.py [--config C.toml] [--out cards.jsonl] [--limit N] [--by-source]
--limit N keeps a stratified subset of N cards (a pilot), in the same proportions of split and context.
--by-source adds the number of cards per catalog row to the summary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tomllib

from label_rules import is_common
import value_gen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "templates" / "ml_train" / "card_config.toml"
TYPES = ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY")
TYPE_OF_BASE = {"password": "PASSWORD", "db_uri": "PASSWORD", "token": "TOKEN", "jwt": "TOKEN", "api_key": "SECRET",
                "secret": "SECRET", "hex_secret": "SECRET", "uuid_key": "SECRET"}
COMMON_WORDS = tuple(w for w in value_gen.WEAK if is_common(w))  # for common_value_both_positions

# boundary rule -> (secret type it needs or None, transform on that secret's placeholder or None, instruction)
BOUNDARY = {
    "quoted": (None, None, "Put {p} inside quotes (single, double or backticks) in at least one place."),
    "trailing_punct": (None, None, "In a sentence or log line, put {p} directly before a period, comma or closing "
                                   "parenthesis, with no quote around it."),
    "value_ends_punct": ("PASSWORD", None, "Use {{PASSWORD=LITERAL}} where LITERAL is a password you invent that ends "
                                           "with '.', '!' or ')', and always write it inside quotes."),
    "bearer": ("TOKEN", None, "Send {p} in an `Authorization: Bearer {p}` header."),
    "basic": ("PASSWORD", "basic=<USER>", "Use {p} as the value of an `Authorization: Basic {p}` header; it is the "
                                          "base64 of <USER>:password, so mention the user name <USER> elsewhere."),
    "token_scheme": ("TOKEN", None, "Send {p} as `Authorization: token {p}` (GitHub style)."),
    "url_password": ("PASSWORD", None, "Put {p} in the password part of a URL: scheme://user:{p}@host:port/path. "
                                       "Use a scheme that fits the context (postgresql, mysql, mongodb+srv, redis, "
                                       "amqp, https, ftp)."),
    "user_colon_password": ("PASSWORD", None, "Write a `user:{p}` pair (htpasswd-style line, curl -u, or a "
                                              "`username:password` note)."),
    "connection_string": ("PASSWORD", None, "Put {p} in a connection string such as `Server=...;User Id=...;"
                                            "Password={p};` or a JDBC/ODBC string."),
    "cookie": ("TOKEN", None, "Send {p} as a session cookie: `Cookie: session={p}` or `Set-Cookie: sid={p}; Path=/; "
                             "HttpOnly`."),
    "pem_full": ("PRIVATE_KEY", None, "Print {p} whole, on its own lines, as `cat` shows a key file."),
    "pem_truncated": ("PRIVATE_KEY", "truncate=<N>", "Show {p} as the output of `head -n <N+1> key.pem`: the key is "
                                                     "cut off and has no END line."),
    "pem_json_escaped": ("PRIVATE_KEY", "json", "Put {p} as the \"private_key\" string of a JSON document (a service "
                                                "account file or API response); it is already JSON-escaped."),
    "wrapped": ("TOKEN", "wrap=<N>", "Show {p} in narrow terminal output; it is already broken onto new lines every "
                                     "<N> characters, so print it at the start of a line."),
    "base64": (None, "base64", "{p} is base64-encoded: use it where an encoded secret belongs (a Kubernetes Secret "
                               "`data:` field, an encoded env value)."),
    "url_encoded": (None, "url", "{p} is percent-encoded: use it in a URL query string or a form body."),
    "json_escaped": (None, "json", "Put {p} inside a JSON string value (it is already JSON-escaped)."),
    "common_value_both_positions": ("PASSWORD", None, "The password is the common word <WORD>: write "
                                                      "{{PASSWORD=<WORD>}} in every credential position, and also "
                                                      "write <WORD> as plain text where it is NOT a credential (a user "
                                                      "name, home path, host or service name)."),
    "distinct_value_repeated_in_logs": (None, None, "Besides its credential position, repeat {p} in a later log or "
                                                    "error line that is not a key=value field (e.g. `auth failed "
                                                    "with {p}`). Do not put it right after 'for', 'user', 'as', "
                                                    "'-u' or a '/'."),
}


def load(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_catalog(cfg: dict, config_path: Path = CONFIG) -> list[dict]:
    path = config_path.parent / cfg["catalog"]["path"]
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def pairs(table: dict) -> list[tuple[str, int]]:
    return [(k, int(v)) for k, v in table.items() if int(v) > 0]


def span(d: value_gen.Draw, key: str) -> int:
    lo, _, hi = key.partition("-")
    return d.between(int(lo), int(hi or lo))


def allocate(cells: list[tuple[object, int]], total: int) -> list[object]:
    """total cells in proportion to the weights, by largest remainder."""
    weight = sum(w for _, w in cells)
    exact = [(c, total * w / weight) for c, w in cells]
    counts = {i: int(x) for i, (_, x) in enumerate(exact)}
    rest = total - sum(counts.values())
    for i in sorted(range(len(exact)), key=lambda i: (-(exact[i][1] - int(exact[i][1])), i))[:rest]:
        counts[i] += 1
    return [exact[i][0] for i in range(len(exact)) for _ in range(counts[i])]


def stratified_splits(slots: list, split_weights: list[tuple[str, int]]) -> list[str]:
    """A split for every slot: each cell (context, type) is divided in the split proportions, and the split totals
    are exactly those of allocate() over all slots. Within a cell, slots take the splits in their (shuffled) order."""
    totals = Counter(allocate(split_weights, len(slots)))
    names, weight = [s for s, _ in split_weights], sum(w for _, w in split_weights)
    size = Counter(slots)
    cells = sorted(size, key=str)
    quota = {(c, s): size[c] * w / weight for c in cells for s, w in split_weights}
    take = {k: int(v) for k, v in quota.items()}
    room = {c: size[c] - sum(take[(c, s)] for s in names) for c in cells}
    need = {s: totals[s] - sum(take[(c, s)] for c in cells) for s in names}
    # the remaining slots go to the largest fractional parts, within each cell's and split's room
    for c, s in sorted(quota, key=lambda k: (-(quota[k] - int(quota[k])), str(k))):
        if room[c] and need[s]:
            take[(c, s)] += 1
            room[c] -= 1
            need[s] -= 1
    for c, s in [(c, s) for c in cells for s in names]:  # anything left: wherever both still have room
        while room[c] and need[s]:
            take[(c, s)] += 1
            room[c] -= 1
            need[s] -= 1
    order = {c: [s for s in names for _ in range(take[(c, s)])] for c in cells}
    seen: Counter = Counter()
    out = []
    for c in slots:
        out.append(order[c][seen[c]])
        seen[c] += 1
    return out


def shuffle(items: list, d: value_gen.Draw) -> list:
    items = list(items)
    for i in range(len(items) - 1, 0, -1):
        j = d.int(i + 1)
        items[i], items[j] = items[j], items[i]
    return items


def secret(d: value_gen.Draw, cfg: dict, kind_type: str, index: int, kinds: dict | None = None) -> dict:
    kind = d.weighted(pairs(kinds or cfg["kinds"][kind_type]))
    return {"placeholder": f"{{{{{kind}:s{index}}}}}", "kind": kind, "type": kind_type,
            "channel": d.weighted(pairs(cfg["channel"]["weights"])),
            "repeat": d.weighted(pairs(cfg["repeat"]["weights"]))}


def with_transform(s: dict, transform: str, d: value_gen.Draw) -> tuple[dict, dict[str, str]]:
    """The secret with the transform on its placeholder, and the values filled into <...> of the instruction."""
    name, _, arg = transform.partition("=")
    fill = {}
    if arg == "<USER>":
        fill["<USER>"] = arg = d.choice(("deploy", "admin", "ci", "svc-backup", "api"))
    elif arg == "<N>":
        n = d.between(2, 6) if name == "truncate" else d.choice((16, 20, 24, 32))
        arg, fill["<N>"], fill["<N+1>"] = str(n), str(n), str(n + 1)
    s = {**s, "placeholder": s["placeholder"][:-2] + "|" + name + (f"={arg}" if arg else "") + "}}"}
    if name == "basic":
        s["type"] = "TOKEN"
    return s, fill


def boundary_rule(d: value_gen.Draw, cfg: dict, secrets: list[dict]) -> dict:
    rule = d.weighted(pairs(cfg["boundary"]["rules"]))
    need, transform, text = BOUNDARY[rule]
    # db_uri expands to a whole URI and takes no transform, so it cannot carry a rule; nor can a secret already
    # transformed by its catalog row
    target = next((i for i, s in enumerate(secrets)
                   if (need is None or s["type"] == need) and s["kind"] != "db_uri" and "|" not in s["placeholder"]),
                  None)
    if target is None:  # add a secret of the type the rule needs (a plain password when any type will do)
        kinds = {"password": 1} if need in ("PASSWORD", None) else None
        secrets.append(secret(d, cfg, need or "PASSWORD", len(secrets) + 1, kinds))
        target = len(secrets) - 1
    if rule == "common_value_both_positions":
        word = d.choice(COMMON_WORDS)
        secrets[target] = {**secrets[target], "placeholder": f"{{{{PASSWORD={word}}}}}", "kind": "literal",
                           "type": "PASSWORD"}
        text = text.replace("<WORD>", word)
    elif rule == "value_ends_punct":
        secrets[target] = {**secrets[target], "placeholder": "{{PASSWORD=LITERAL}}", "kind": "literal",
                           "type": "PASSWORD"}
    elif transform:
        secrets[target], fill = with_transform(secrets[target], transform, d)
        for marker, value in fill.items():
            text = text.replace(marker, value)
    return {"rule": rule, "secret": target + 1, "instruction": text.replace("{p}", secrets[target]["placeholder"])}


def scene(row: dict, fill: dict[str, str]) -> dict:
    """What the card tells the writer about its catalog row: the service, and the hints unless the row comes from an
    evaluation-only source (then only the service and the value format)."""
    out = {"service": row["service"]}
    out.update({k: v for k, v in (row["hints"] or {}).items() if v})
    if "<USER>" in fill:
        out["basic_auth_user"] = fill["<USER>"]
    return out


def contrast(row: dict) -> dict:
    c = row["contrast"]
    placeholder = "{{neg:" + c["kind"] + (f"|of={c['of']}" if c["of"] else "") + c["args"] + "}}"
    return {"placeholder": placeholder, "kind": c["kind"], "position": c["position"], "contrast": True}


def card(d: value_gen.Draw, cfg: dict, card_id: str, split: str, context: str, primary: str, ood: dict | None,
         row: dict | None = None) -> dict:
    ctx = cfg["contexts"].get(context)
    fmt = d.choice(ctx["formats"]) if ctx else cfg["ood"]["contexts"][context]
    secrets: list[dict] = []
    fill: dict[str, str] = {}
    if primary != "none":
        if ood and ood.get("kind"):
            kinds = {ood["kind"]: 1}
        elif row and row["kind"] != "*":  # the row's own format; "*" leaves the kind to [kinds]
            kinds = {row["kind"]: 1}
        else:
            kinds = None
        secrets.append(secret(d, cfg, primary, 1, kinds))
        if row and row["transform"] and kinds and row["kind"] in kinds:
            secrets[0], fill = with_transform(secrets[0], row["transform"], d)
        extra_types = pairs(cfg["extra_secrets"]["types"])
        for _ in range(int(d.weighted(pairs(cfg["extra_secrets"]["weights"])))):
            secrets.append(secret(d, cfg, d.weighted(extra_types), len(secrets) + 1))
    boundary = None
    if secrets and d.int(1000) < cfg["boundary"]["share"] * 1000:
        boundary = boundary_rule(d, cfg, secrets)
    share = cfg["negatives"]["share_none" if not secrets else "share_positive"]
    negatives = []
    if d.int(1000) < share * 1000:
        for _ in range(int(d.weighted(pairs(cfg["negatives"]["count"])))):
            kind = d.weighted(pairs(cfg["negatives"]["kinds"]))
            negatives.append({"placeholder": f"{{{{neg:{kind}}}}}", "kind": kind,
                              "position": d.weighted([("credential", 1), ("anywhere", 1)])})
    if row and row["contrast"] and d.int(1000) < cfg["catalog"]["contrast_share"] * 1000:
        negatives.append(contrast(row))
    items = span(d, d.weighted(pairs(cfg["session"]["items"])))
    turns = min(span(d, d.weighted(pairs(cfg["session"]["turns"]))), max(1, items // 2))
    tool_output = ood["tool_output_format"] if ood and ood.get("tool_output_format") else \
        d.weighted(pairs(cfg["tool_output_format"]["weights"]))
    for s in secrets:  # a fixed value with punctuation cannot be named in {{mask:...}}
        ref = s["placeholder"][2:-2].split("|")[0].split(":")[-1].partition("=")[2] if s["kind"] == "literal" else \
            s["placeholder"][2:-2].split("|")[0].split(":")[1]
        s["mask"] = f"{{{{mask:{ref}}}}}" if (re.fullmatch(r"[\w.-]+", ref) and ref != "LITERAL"
                                              and d.int(1000) < cfg["mask"]["share"] * 1000) else None
    # room for what the secrets ask: a value first read in a tool_output and then reused needs a second
    # tool_input/tool_output pair; one the developer repeats needs a second developer message
    if any(s["channel"] == "tool_output" and (s["mask"] or s["repeat"] == "multi_item") for s in secrets):
        items = max(items, 5)
    if any(s["channel"] == "prompt" and s["repeat"] != "once" for s in secrets):
        items, turns = max(items, 5), max(turns, 2)
    turns = min(turns, max(1, items // 2))
    return {"card_id": card_id, "group_id": card_id, "split": split,
            "model": cfg["templates"]["model_ood" if split == "test_ood" else "model"],
            "variants": cfg["templates"]["variants_ood" if split == "test_ood" else "variants"],
            "context": context, "format": fmt, "primary_type": primary,
            "source_id": row["source_id"] if row else None, "scene": scene(row, fill) if row else None,
            "secrets": secrets, "negatives": negatives,
            "boundary": boundary, "language": d.weighted(pairs(cfg["language"]["weights"])),
            "tool_output_format": tool_output, "tool_input_format": d.weighted(pairs(cfg["tool_input_format"]["weights"])),
            "items": items, "turns": turns,
            "longest_output_chars": span(d, d.weighted(pairs(cfg["session"]["longest_output"]))),
            "ood": ood}


def assign_rows(slots: list, rows: list[dict], base: str) -> list[dict]:
    """A catalog row for every slot. A cell (context, type) takes the rows whose types hold its type (any row for a
    session without secrets) and whose contexts hold its context, or, if none does, every row of its type. Each slot
    takes the fitting row used least so far, counted within the cell and then within the type, ties broken in a
    shuffled order: the rows of a cell take turns, and every row of a type gets cards before any gets many."""
    rank: dict[str, dict[str, int]] = {}
    fits: dict[tuple, list[dict]] = {}
    for ctx, t in sorted(set(slots), key=str):
        of_type = [r for r in rows if t == "none" or t in r["types"]]
        if not of_type:
            raise ValueError(f"no catalog row for type {t}")
        if t not in rank:
            order = shuffle(sorted(r["source_id"] for r in of_type), value_gen.Draw(f"{base}:rows:{t}"))
            rank[t] = {sid: i for i, sid in enumerate(order)}
        fits[(ctx, t)] = [r for r in of_type if ctx in r["contexts"]] or of_type
    in_cell: Counter = Counter()
    in_type: Counter = Counter()
    out = []
    for ctx, t in slots:
        row = min(fits[(ctx, t)], key=lambda r: (in_cell[(ctx, t, r["source_id"])], in_type[(t, r["source_id"])],
                                                 rank[t][r["source_id"]]))
        in_cell[(ctx, t, row["source_id"])] += 1
        in_type[(t, row["source_id"])] += 1
        out.append(row)
    return out


def draw(cfg: dict, catalog: list[dict] | None = None) -> list[dict]:
    base = f"{cfg['seed']}:{cfg['version']}"
    catalog = load_catalog(cfg) if catalog is None else catalog
    cells = [((ctx, t), int(w)) for ctx, c in cfg["contexts"].items() for t, w in c["weights"].items() if int(w) > 0]
    slots = shuffle(allocate(cells, cfg["templates"]["in_distribution"]), value_gen.Draw(base + ":order"))
    splits = stratified_splits(slots, pairs(cfg["split"]))
    rows = assign_rows(slots, [r for r in catalog if r["status"] == "train"], base)
    cards = [card(value_gen.Draw(f"{base}:c{i:04d}"), cfg, f"c{i:04d}", split, ctx, t, None, row)
             for i, ((ctx, t), split, row) in enumerate(zip(slots, splits, rows), 1)]
    # test_ood: each card carries one feature never drawn for the other splits, and the catalog row of that feature
    od = cfg["ood"]
    ood_row = {(r["ood"]["feature"], v): r for r in catalog if r["status"] == "ood" for v in r["ood"]["values"]}
    features = allocate([("context", 2), ("kind", 2), ("tool_output_format", 1)], cfg["templates"]["test_ood"])
    for i, feature in enumerate(shuffle(features, value_gen.Draw(base + ":ood")), 1):
        d = value_gen.Draw(f"{base}:o{i:04d}")
        if feature == "context":
            ctx = d.choice(sorted(od["contexts"]))
            primary = d.weighted([(t, 1) for t in TYPES[:4]] + [("none", 1)])
            ood, row = {"feature": "context"}, ood_row.get(("context", ctx))
        elif feature == "kind":
            kind = d.choice(sorted(od["kinds"]))
            ctx, primary = d.choice(sorted(cfg["contexts"])), od["kinds"][kind]
            ood, row = {"feature": "kind", "kind": kind}, ood_row.get(("kind", kind))
        else:
            ctx = d.choice(sorted(cfg["contexts"]))
            primary = d.weighted([(t, 1) for t in TYPES] + [("none", 1)])
            ood = {"feature": "tool_output_format", "tool_output_format": od["tool_output_format"]}
            row = ood_row.get(("tool_output_format", od["tool_output_format"]))
        cards.append(card(d, cfg, f"o{i:04d}", "test_ood", ctx, primary, ood, row))
    return cards


def stratified(cards: list[dict], n: int) -> list[dict]:
    """n cards keeping the share of each (split, context) group."""
    groups: dict[tuple, list[dict]] = {}
    for c in cards:
        groups.setdefault((c["split"], c["context"]), []).append(c)
    keys = sorted(groups)
    take = Counter(allocate([(k, len(groups[k])) for k in keys], n))
    return [c for k in keys for c in groups[k][:take[k]]]


def summary(cards: list[dict], catalog: list[dict], by_source: bool = False) -> dict:
    secrets = [s for c in cards for s in c["secrets"]]
    in_dist = [c for c in cards if c["split"] != "test_ood"]
    per_row = Counter(c["source_id"] for c in in_dist)
    ood_ids = {r["source_id"] for r in catalog if r["status"] == "ood"}
    eval_ids = {r["source_id"] for r in catalog if r.get("eval_only")}
    out = {"cards": len(cards), "sessions": sum(c["variants"] for c in cards),
           "by_split": dict(sorted(Counter(c["split"] for c in cards).items())),
           "by_primary_type": dict(sorted(Counter(c["primary_type"] for c in cards).items())),
           "by_cell": dict(sorted(Counter(f"{c['context']}:{c['primary_type']}" for c in in_dist).items())),
           "by_cell_split": dict(sorted(Counter(f"{c['context']}:{c['primary_type']}:{c['split']}"
                                                for c in in_dist).items())),
           "secrets": len(secrets), "secrets_by_channel": dict(sorted(Counter(s["channel"] for s in secrets).items())),
           "secrets_masked_in_tool_input": sum(bool(s["mask"]) for s in secrets),
           "with_negatives": sum(bool(c["negatives"]) for c in cards),
           "negatives": sum(len(c["negatives"]) for c in cards),
           "contrasts": sum(n.get("contrast", False) for c in cards for n in c["negatives"]),
           "with_boundary_rule": sum(bool(c["boundary"]) for c in cards),
           "by_language": dict(sorted(Counter(c["language"] for c in cards).items())),
           "catalog": {"train_rows": sum(r["status"] == "train" for r in catalog),
                       "rows_used": len(per_row),
                       "cards_per_row": {"min": min(per_row.values(), default=0), "max": max(per_row.values(), default=0)},
                       "ood_rows_used_in_test_ood": len({c["source_id"] for c in cards if c["split"] == "test_ood"}
                                                        & ood_ids),
                       "ood_rows_outside_test_ood": sum(c["source_id"] in ood_ids for c in in_dist),
                       "eval_only_cards": sum(c["source_id"] in eval_ids for c in cards),
                       "eval_only_cards_with_hints": sum(c["source_id"] in eval_ids and set(c["scene"]) != {"service"}
                                                         for c in cards)}}
    if by_source:
        out["cards_by_source"] = dict(sorted(per_row.items()))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--out", type=Path, default=CONFIG.parent / "cards.jsonl")
    parser.add_argument("--limit", type=int, help="keep a stratified subset of this many cards")
    parser.add_argument("--by-source", action="store_true", help="also count the cards of every catalog row")
    args = parser.parse_args()
    cfg = load(args.config)
    catalog = load_catalog(cfg, args.config)
    cards = draw(cfg, catalog)
    if args.limit:
        cards = stratified(cards, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")
    print(json.dumps({"out": str(args.out), **summary(cards, catalog, args.by_source)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
