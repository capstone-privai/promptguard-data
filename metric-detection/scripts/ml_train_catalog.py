"""Turn the secret-source catalog into scenes for the ML training cards (docs/README_ml-train-plan.md 3절).

The catalog (metric-detection/secret-sources: one row per way a secret reaches a coding agent) is rebuilt by
build_v3.py and stays out of git, because its example columns hold format-correct fake secrets. This script reads
it with templates/ml_train/catalog_decisions.toml and writes two committed files that hold no example value:
  templates/ml_train/catalog.jsonl   one line per row: status (train, ood, excluded), service, gold types, kind,
                                     contexts, scene hints and the contrast (the hard negative the row pairs with)
  scripts/value_gen_catalog.py       the service formats the rows need beyond value_gen's own kinds, taken from
                                     the row's structural signature (column 11) or its decision
Columns 12 and 13 (the example values) are never copied: the contrast is a {{neg:KIND}} placeholder chosen from
the shape of column 13. Rows from an evaluation-only source keep only their service and value format.

Run from the repository root (build the CSV first: cd metric-detection/secret-sources && python3 -I build_v3.py frame.csv):
  python metric-detection/scripts/ml_train_catalog.py [--csv PATH] [--check]
--check fails when either output differs from a fresh run.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
import tomllib

from label_rules import exclusion_kind, expected_type, is_common
import value_gen

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "secret-sources" / "frame.csv"
DECISIONS = ROOT / "templates" / "ml_train" / "catalog_decisions.toml"
CATALOG = ROOT / "templates" / "ml_train" / "catalog.jsonl"
KINDS_MODULE = Path(__file__).resolve().parent / "value_gen_catalog.py"
TYPES = ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY")
CONTEXTS = ("config", "command_output", "log", "stacktrace", "diff", "http", "code", "natural_language", "document",
            "key_file")
# contexts a row fits by default, and names the decisions may use for groups of them
CONTEXT_GROUPS = {
    "any": [c for c in CONTEXTS if c != "key_file"],
    "key": ["key_file", "config", "command_output", "diff", "code", "natural_language", "document"],
    "files": ["config", "command_output", "diff", "code", "document"],
    "terminal": ["command_output", "log"],
    "source": ["code", "diff"],
}
EXISTING_KINDS = set(value_gen.SECRET_KINDS) - set(value_gen.CATALOG_KINDS)
BASE_KINDS = {"password", "token", "api_key", "secret", "hex_secret", "uuid_key", "jwt", "db_uri"}
ALPHA_UNIVERSE = "".join(chr(c) for c in range(33, 127))
SAMPLES = 200


# ---- structural signature (column 11) -> value_gen parts --------------------------------------------------

class Unparsed(ValueError):
    pass


class Regex:
    """A small parser for the literal-and-class shapes of column 11 (prefix + [class]{n} segments)."""

    def __init__(self, src: str):
        self.s, self.i = src, 0

    def peek(self, n: int = 1) -> str:
        return self.s[self.i:self.i + n]

    def seq(self, stop: str) -> list:
        out = []
        while self.i < len(self.s) and self.s[self.i] not in stop:
            atom = self.atom()
            out.extend(self.quantify(atom))
        return out

    def atom(self):
        c = self.s[self.i]
        self.i += 1
        if c == "\\":
            e = self.s[self.i]
            self.i += 1
            if e == "b":
                return ("skip",)
            if e == "d":
                return ("cls", value_gen.DIGITS)
            if e == "w":
                return ("cls", value_gen.ALNUM + "_")
            if e.isalnum():
                raise Unparsed(f"\\{e}")
            return ("lit", e)
        if c in "^$":
            return ("skip",)
        if c == "[":
            j = self.i
            while self.s[j] != "]" or self.s[j - 1] == "\\" or j == self.i:
                j += 1
            cls = "[" + self.s[self.i:j] + "]"
            self.i = j + 1
            chars = "".join(ch for ch in ALPHA_UNIVERSE if re.fullmatch(cls, ch))
            if not chars:
                raise Unparsed(cls)
            return ("cls", chars)
        if c == "(":
            if self.peek(2) == "?:":
                self.i += 2
            elif self.peek() == "?":
                raise Unparsed("lookaround")
            alts = [self.seq("|)")]
            while self.peek() == "|":
                self.i += 1
                alts.append(self.seq("|)"))
            if self.peek() != ")":
                raise Unparsed("group")
            self.i += 1
            if len(alts) == 1:
                return ("seq", alts[0])
            if all(all(isinstance(p, str) for p in a) for a in alts):
                return ("alt", ["".join(a) for a in alts])
            raise Unparsed("alternation")
        if c in ".*+?{|)":
            raise Unparsed(c)
        return ("lit", c)

    def quantify(self, atom) -> list:
        m = re.match(r"\{(\d+)(?:(,)(\d*))?\}|[?+*]", self.s[self.i:])
        q = None
        if m:
            q = m.group(0)
            self.i += len(q)
        kind = atom[0]
        if kind == "skip":
            return []
        if q == "?":
            literal = kind == "lit" or (kind == "seq" and all(isinstance(p, str) for p in atom[1]))
            if not literal:
                return []  # an optional class part: leave it out
            text = atom[1] if kind == "lit" else "".join(atom[1])
            return [["", text]]
        lo = hi = 1
        if q and q[0] == "{":
            lo = int(m.group(1))
            hi = lo if not m.group(2) else int(m.group(3)) if m.group(3) else lo + max(8, lo // 2)
        elif q == "+":
            lo, hi = 8, 24
        elif q == "*":
            lo, hi = 0, 8
        if kind == "lit":
            if lo != hi:
                raise Unparsed("variable literal")
            return [atom[1] * lo]
        if kind == "cls":
            return [(alpha_name(atom[1]), lo, hi)]
        if kind == "alt":
            if q:
                raise Unparsed("quantified alternation")
            return [atom[1]]
        if q:
            raise Unparsed("quantified group")
        return atom[1]


def alpha_name(chars: str) -> str:
    for name, alphabet in value_gen.ALPHABETS.items():
        if set(alphabet) == set(chars):
            return name
    return "=" + chars


def merge(parts: list) -> list:
    out = []
    for p in parts:
        if isinstance(p, str) and out and isinstance(out[-1], str):
            out[-1] += p
        elif p != "":
            out.append(p)
    return out


def split_top(src: str) -> list[str]:
    depth, cls, out, start = 0, False, [], 0
    for i, c in enumerate(src):
        if src[i - 1:i] == "\\" and src[i - 2:i] != "\\\\":
            continue
        if c == "[":
            cls = True
        elif c == "]":
            cls = False
        elif not cls and c == "(":
            depth += 1
        elif not cls and c == ")":
            depth -= 1
        elif not cls and depth == 0 and c == "|":
            out.append(src[start:i])
            start = i + 1
    return out + [src[start:]]


def parse_parts(src: str) -> tuple[list, str] | None:
    """(parts, the sub-pattern they came from) of a structural signature, or None."""
    src = re.sub(r"^\(\?[a-z]+\)", "", src)
    first = split_top(src)[0]
    candidates = []
    # a contextual signature (key name, separators, then the value): its capture groups first, last first
    starts = [m.start() for m in re.finditer(r"(?<!\\)\((?!\?)", first)]
    for s in reversed(starts):
        depth = 0
        for j in range(s, len(first)):
            if first[j] == "(" and first[j - 1:j] != "\\":
                depth += 1
            elif first[j] == ")" and first[j - 1:j] != "\\":
                depth -= 1
                if depth == 0:
                    candidates.append(first[s + 1:j])
                    break
    for cand in candidates + [first]:
        try:
            p = Regex(cand)
            parts = merge(p.seq(""))
        except (Unparsed, IndexError):
            continue
        if any(isinstance(x, tuple) for x in parts) and sum(x[1] for x in parts if isinstance(x, tuple)) >= 8:
            return parts, cand
    return None


def parts_from_toml(spec: list) -> list:
    """A spec from the decisions: strings, [choices] and ["ALPHABET", lo, hi] (a list whose 2nd item is a number)."""
    out = []
    for p in spec:
        if isinstance(p, list) and len(p) in (2, 3) and isinstance(p[1], int):
            out.append((p[0], p[1], p[-1]))
        elif isinstance(p, list):
            out.append(list(p))
        else:
            out.append(p)
    return merge(out)


# ---- one catalog row -> record ------------------------------------------------------------------------------

def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return ("x" + s) if s[:1].isdigit() else s


def default_type(service: str, sample: str) -> str:
    if expected_type(sample):
        return expected_type(sample)
    s = service.lower()
    if re.search(r"(?<!1)password|passphrase|\bpw\b", s):
        return "PASSWORD"
    if re.search(r"private.key|secret.key.1|mnemonic", s):
        return "PRIVATE_KEY"
    if re.search(r"access.?key.?id|secret.id|client.key|publishable|javascript.key|anon", s):
        return "ACCESS_KEY"
    if re.search(r"token|\bpat\b|jwt|session", s):
        return "TOKEN"
    return "SECRET"


def mask_of(kind: str, kind_type: str, sample: str) -> str:
    if kind_type in ("PRIVATE_KEY", "PASSWORD"):
        return kind_type
    if sample.startswith("eyJ"):
        return "JWT"
    for word, mask in (("github", "GITHUB_TOKEN"), ("slack", "SLACK_TOKEN"), ("aws", "AWS_KEY")):
        if word in kind:
            return mask
    if kind_type == "TOKEN":
        return "TOKEN"
    return "SECRET" if kind_type == "SECRET" and "secret" in kind else "API_KEY"


def changed_lines(pos: str, neg: str) -> str:
    """The lines of column 13 that column 12 does not share: the value, without a frame such as a js `${x}`."""
    shared = set(pos.split("\n"))
    return "\n".join(line for line in neg.split("\n") if line not in shared) or neg


def default_contrast(neg: str, prefix: tuple[str, ...]) -> str | None:
    """The {{neg:KIND}} that plays the part of column 13, from its shape (the value itself is never copied)."""
    p = any(x in neg for x in prefix)
    if re.search(r"\$\{\{\s*secrets", neg):
        return "template"
    if re.search(r"\$\{|\$[A-Z_]{3,}\b|process\.env|os\.environ|getenv|%[A-Z_]+%|\$env:", neg):
        return "reference"
    if re.search(r"x{4}|X{4}|\*{3}", neg):
        return "prefix_redaction" if p else "redaction"
    if "EXAMPLE" in neg:
        return "prefix_example" if p else "doc_example"
    if re.search(r"YOUR_|your-|<[^>]+>|_HERE", neg):
        return "prefix_template" if p else "template"
    if re.search(r"BEGIN (?:RSA |EC |)PUBLIC KEY|BEGIN CERTIFICATE|ssh-(?:ed25519|rsa) AAAA", neg):
        return "public_key"
    if re.search(r"\$(?:6|2[aby]|apr1|y)\$", neg):
        return "hash"
    if re.search(r"[가-힣]", neg):
        return "template_ko"
    return None


def hints(row: dict, ood: bool, prefix: tuple[str, ...]) -> dict:
    paths = [p.strip() for p in row["Typical_File_Paths_or_Streams"].split(",") if p.strip()]
    paths = [p for p in paths if p != "(see row)" and (ood or "datadog" not in p.lower())]
    fmt = row["Data_Format_or_Syntax"].strip()
    asset = row["Asset_or_Host_Pair_Context"].strip()
    ids = []
    for x in (i.strip() for i in row["Key_Identifiers_and_Indicators"].split(",")):
        if (re.fullmatch(r"[A-Za-z_][\w.\-]*", x) and not x.startswith("AUTO_") and not expected_type(x)
                and not any(p.startswith(x) or x.startswith(p.rstrip("_-.")) for p in prefix) and x not in ids):
            ids.append(x)
    lp = row["SLM_Training_Guideline_KR"].strip()
    if lp.startswith("접두사 `") or any(expected_type(t) for t in re.findall(r"[\w\-./+=:]{12,}", lp)):
        lp = None
    return {"paths": paths, "format": None if fmt in ("Prefix Token", "(see row)") else fmt,
            "asset": asset if re.fullmatch(r"[\x21-\x7e ]+", asset) and re.search(r"[./:]", asset) else None,
            "identifiers": ids, "learning_point": lp}


def contexts_of(spec, kind_type: str) -> list[str]:
    if spec is None:
        spec = ["key"] if kind_type == "PRIVATE_KEY" else ["any"]
    out = []
    for name in spec:
        for c in CONTEXT_GROUPS.get(name, [name]):
            if c not in CONTEXTS:
                raise ValueError(f"unknown context {c!r}")
            if c not in out:
                out.append(c)
    return [c for c in CONTEXTS if c in out]


def record(row: dict, dec: dict, new_kinds: dict, problems: list[str]) -> dict:
    sid = row["Source_ID"]
    over = dec.get("rows", {}).get(sid, {})
    service = over.get("service") or re.sub(r"^(?:Auto_(?:Found_a_)?|GG_)", "", row["Sub_Category"]).replace("_", " ")
    base = {"source_id": sid, "service": service}
    if sid in dec.get("exclude", {}):
        return {**base, "status": "excluded", "reason": dec["exclude"][sid]}
    ood = dec.get("ood", {}).get(sid)
    eval_only = sid in dec.get("eval_only", [])
    kind = over.get("kind")
    prefix: tuple[str, ...] = ()
    if kind == "*":  # a context row: the card draws the kind of its type ([kinds])
        types = over.get("types")
        if not types:
            problems.append(f"{sid}: a row with kind '*' needs types")
            types = []
        sample = ""
    elif kind in EXISTING_KINDS or kind in BASE_KINDS:
        kind_type = value_gen.SECRET_KINDS[kind][0] if kind in value_gen.SECRET_KINDS else \
            {"password": "PASSWORD", "db_uri": "PASSWORD", "token": "TOKEN", "jwt": "TOKEN"}.get(kind, "SECRET")
        types = over.get("types", [kind_type])
        prefix = value_gen.prefixes_of(kind)
    elif kind and "spec" not in over and kind in new_kinds:  # a kind another row makes
        _, kind_type, _, parts = new_kinds[kind]
        types = [kind_type]
        prefix = value_gen.literal_prefix(parts)
    else:
        kind = kind or slug(service)
        if "spec" in over:
            parts, pattern = parts_from_toml(over["spec"]), None
        else:
            parsed = parse_parts(row["Regex_or_Structural_Signature"])
            if parsed is None:
                problems.append(f"{sid} {service}: no spec for its signature {row['Regex_or_Structural_Signature'][:60]!r}")
                return {**base, "status": "excluded", "reason": "no spec"}
            parts, pattern = parsed
        gen = value_gen.from_parts(parts)
        samples = [gen(value_gen.Draw(f"catalog:{kind}:{i}")) for i in range(SAMPLES)]
        kind_type = over.get("type") or default_type(service, samples[0])
        types = [kind_type]
        if kind in new_kinds and new_kinds[kind][0] != sid:
            problems.append(f"{sid}: kind {kind} is also made by {new_kinds[kind][0]}")
        new_kinds[kind] = (sid, kind_type, over.get("mask") or mask_of(kind, kind_type, samples[0]), parts)
        check_samples(sid, kind, kind_type, samples, pattern, problems)
        prefix = value_gen.literal_prefix(parts)
    if over.get("types"):
        types = over["types"]
    ctx = contexts_of(over.get("contexts"), types[0] if types else "SECRET")
    rec = {**base, "status": "ood" if ood else "train", "types": types, "kind": kind,
           "transform": over.get("transform"), "contexts": ctx, "eval_only": eval_only}
    if ood:
        rec["ood"] = ood
    if eval_only:  # 평가 전용 출처: service and value format only (README_ml-train-plan.md 5절)
        rec["hints"], rec["contrast"] = None, None
        return rec
    h = hints(row, bool(ood), prefix)
    for key in ("paths", "format", "asset", "identifiers", "learning_point"):
        if key in over:
            h[key] = over[key] or (None if key in ("format", "asset", "learning_point") else [])
    rec["hints"] = h
    contrast = over.get("contrast", default_contrast(changed_lines(row["Synthetic_Positive_Example_Raw"],
                                                                  row["Hard_Negative_Counterpart_Example"]), prefix))
    if contrast in (None, "none", False):
        rec["contrast"] = None
    else:
        name, _, args = contrast.partition("|")
        if name.startswith("prefix_") and not prefix:
            name = {"prefix_redaction": "redaction", "prefix_example": "doc_example",
                    "prefix_template": "template"}[name]
        if name not in value_gen.NEGATIVE_KINDS:
            problems.append(f"{sid}: contrast {name!r} is not a negative kind")
        of = kind if name in value_gen.PREFIX_NEGATIVES else None
        rec["contrast"] = {"kind": name, "of": of, "args": ("|" + args) if args else "",
                           "position": over.get("contrast_position", "credential"),
                           "note": over.get("contrast_note")}
    return rec


def check_samples(sid: str, kind: str, kind_type: str, samples: list[str], pattern: str | None, problems: list[str]):
    """The format gives the type label_rules expects, the value reads as a credential, and it matches its signature."""
    key = "password" if kind_type == "PASSWORD" else "api_key"
    bad = Counter()
    for v in samples:
        if expected_type(v) not in (None, kind_type):
            bad[f"type {expected_type(v)}"] += 1
        text = f'{key} = "{v}"'
        if exclusion_kind(text, len(key) + 4, len(key) + 4 + len(v)):
            bad["excluded"] += 1
        if is_common(v):
            bad["common"] += 1
        if pattern and not re.fullmatch(pattern.replace(r"\b", ""), v):
            bad["signature"] += 1
    for why, n in bad.items():
        if why.startswith("type") or why == "signature" or n > SAMPLES // 20:
            problems.append(f"{sid} {kind}: {n}/{SAMPLES} samples fail ({why})")


# ---- outputs ----------------------------------------------------------------------------------------------------

def kinds_module(new_kinds: dict) -> str:
    lines = ['"""Service formats from the secret-source catalog (templates/ml_train/catalog.jsonl).',
             "",
             "Generated by ml_train_catalog.py from catalog_decisions.toml and each row's structural signature; do not",
             "edit by hand. kind -> (gold type, PromptGuard mask kind, parts). A part is a literal string, a list of",
             "literal choices, or (alphabet, min length, max length): a value_gen.ALPHABETS name, or '=' + the characters.",
             '"""', "", "CATALOG_KINDS = {"]
    for kind in sorted(new_kinds):
        sid, kind_type, mask, parts = new_kinds[kind]
        lines.append(f"    {kind!r}: ({kind_type!r}, {mask!r}, {tuple(parts)!r}),  # {sid}")
    return "\n".join(lines) + "\n}\n"


def build(csv_path: Path) -> tuple[str, str, list[str], Counter]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with DECISIONS.open("rb") as f:
        dec = tomllib.load(f)
    ids = {r["Source_ID"] for r in rows}
    problems = [f"decision for unknown row {sid}" for table in ("exclude", "ood", "rows") for sid in dec.get(table, {})
                if sid not in ids]
    new_kinds: dict = {}
    over = dec.get("rows", {})

    def refers(r):  # names a kind another row makes: decide it after the rows that make kinds
        k = over.get(r["Source_ID"], {}).get("kind")
        return bool(k) and k != "*" and k not in EXISTING_KINDS | BASE_KINDS and "spec" not in over[r["Source_ID"]]
    by_id = {r["Source_ID"]: record(r, dec, new_kinds, problems) for r in rows if not refers(r)}
    by_id.update({r["Source_ID"]: record(r, dec, new_kinds, problems) for r in rows if refers(r)})
    records = [by_id[r["Source_ID"]] for r in rows]
    ood_kinds = {k for r in records if r["status"] == "ood" for k in r["ood"].get("values", [])}
    for r in records:
        if r["status"] == "train" and r["kind"] in ood_kinds:
            problems.append(f"{r['source_id']}: kind {r['kind']} belongs to the shifted test only")
    for kind in new_kinds:
        if kind in EXISTING_KINDS or kind in BASE_KINDS:
            problems.append(f"new kind {kind} shadows an existing kind")
    catalog = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    return catalog, kinds_module(new_kinds), problems, Counter(r["status"] for r in records)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, default=CSV)
    parser.add_argument("--check", action="store_true", help="fail when the committed outputs differ from a fresh run")
    args = parser.parse_args()
    catalog, module, problems, status = build(args.csv)
    if problems:
        print(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems), file=sys.stderr)
        sys.exit(1)
    if args.check:
        stale = [p.name for p, text in ((CATALOG, catalog), (KINDS_MODULE, module))
                 if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"stale: {', '.join(stale)}; run ml_train_catalog.py", file=sys.stderr)
            sys.exit(1)
    else:
        CATALOG.write_text(catalog, encoding="utf-8")
        KINDS_MODULE.write_text(module, encoding="utf-8")
    print(json.dumps({"rows": sum(status.values()), "by_status": dict(sorted(status.items())),
                      "new_kinds": module.count("),  # SRC-")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
