"""Replace the real secrets in the MSR 2026 issue dataset with format-preserving fakes.

The dataset (Zenodo 19622962) labels candidate strings from GitHub issues; its 5,881 positives are real,
unverified leaks. This script writes a copy in which every positive value is replaced, everywhere it occurs
(candidate_string, body, context_window, text, titles, other text files in the replication package), by a
fake of exactly the same format (see fmtkeep.py). Labels, ids, row order and every field length stay the
same, so offsets computed on the original still hold.

usage: python sanitize_msr_issues.py --src <extracted package dir> --out <output dir> --kingfisher ../kingfisher-v1

Nothing printed or written contains an original value: the report holds counts, methods and shapes only.
The original-to-fake mapping is never written.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

import fmtkeep as F

csv.field_size_limit(sys.maxsize)

CSV_FILES = ["main_data.csv", "train.csv", "val.csv", "test.csv", "test_wild.csv"]
TEXT_COLUMNS = {"candidate_string", "body", "context_window", "text", "title", "issue_title"}
SOURCE_COLUMNS = {"repository_url": "", "repo": "wild:", "Issue_id": "issue:"}

# "token=", "PASSWORD: ", 'KEY = "' ... in front of the value; the value is what gets replaced
ENVELOPE = re.compile(r"""^(?P<pre>["']?[A-Za-z_][\w.\-]*["']?(?:\s*(?:=>|:=|[:=])\s*|\s+)["']?)(?=\S)(?P<val>.+?)"""
                      r"""(?P<post>["']?[,;]?)$""", re.S)


def split_candidate(c: str) -> tuple[str, str, str]:
    m = ENVELOPE.match(c)
    if m and not c.startswith(("-----", "eyJ")) and "://" not in m.group("pre"):
        return m.group("pre"), m.group("val"), m.group("post")
    return "", c, ""


# the same secret written escaped elsewhere in an issue (JSON string, URL, \n-escaped)
VARIANTS = [lambda v: json.dumps(v)[1:-1], lambda v: urllib.parse.quote(v, safe=""), urllib.parse.quote_plus,
            lambda v: v.replace("\r", "\\r").replace("\n", "\\n")]


def weak(v: str) -> bool:
    """Short or word-like values: replace only where the whole candidate string occurs, not every word."""
    return len(v) < 8 or F.entropy(v) < 2.5 or (v.isalpha() and len(v) < 16)


# ---------------------------------------------------------------- learned format prefixes

def learn_prefixes(val_src: dict[str, set], min_vals: int = 5, min_src: int = 5) -> dict[str, str | None]:
    """Prefixes that are format constants: random chance < 0.01, shared by >= min_vals values from
    >= min_src sources, last character shared by >= 75% of the parent group. Also the pool of the position
    right after the prefix when a few characters cover >= 90% of the values (e.g. AIzaSy[A-D])."""
    def pool_size(c):
        return 10 if c.isdigit() else 26 if c.isascii() and c.isalpha() else 32
    nv = collections.Counter()
    ns = collections.defaultdict(set)
    kids = collections.defaultdict(collections.Counter)
    for v, src in val_src.items():
        for k in range(len(v) + 1):
            nv[v[:k]] += 1
            ns[v[:k]] |= src
            if k < len(v):
                kids[v[:k]][v[k]] += 1
    n_all = len(val_src)
    out: dict[str, str | None] = {}
    for v in val_src:
        best, chance = 0, float(n_all)
        for k in range(1, len(v) - 3):
            chance /= pool_size(v[k - 1])
            p = v[:k]
            if nv[p] < min_vals or len(ns[p]) < min_src:
                break
            if chance < 0.01 and nv[p] / nv[p[:-1]] >= 0.75:
                best = k
        if not best:
            continue
        p = v[:best]
        nxt = None
        if nv[p] >= 8:
            core, cov = [], 0
            for c, n in kids[p].most_common():
                if cov >= 0.9 * nv[p]:
                    break
                core.append(c)
                cov += n
            if len(core) <= min(8, nv[p] // 4):
                nxt = set(core) | {v[best]}
        prev = out.get(p)
        out[p] = "".join(sorted(set(prev or "") | (nxt or set()))) or None
    return out


def trie_regex(words) -> re.Pattern:
    """One regex matching any of words, leftmost-longest, built as a trie so a scan costs one pass."""
    trie: dict = {}
    for w in words:
        node = trie
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = True

    def chain(ch, sub) -> str:
        """ch and the single-child path after it as one literal: recursion only at branch points."""
        lit = [ch]
        while len(sub) == 1 and "" not in sub:
            (nxt, sub), = sub.items()
            lit.append(nxt)
        return re.escape("".join(lit)) + build(sub)

    def build(node) -> str:
        end = "" in node
        branches = [chain(ch, sub) for ch, sub in sorted(node.items()) if ch]
        if not branches:
            return ""
        body = branches[0] if len(branches) == 1 else "(?:" + "|".join(branches) + ")"
        return f"(?:{body})?" if end else body

    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    return re.compile(build(trie))


# ---------------------------------------------------------------- csv io keeping the original layout

def read_csv(path: Path):
    raw = path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw[:65536] else "\n"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:], eol


def write_csv(path: Path, header, rows, eol):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator=eol)
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------- the whole token around a value

# A labelled value is often a window of a longer token (a 73-character slice of a JWT, 30 characters of a
# base64 blob, a key missing its first characters). Replacing only the window would leave the rest of the
# real token in the text, so every occurrence is widened to the token holding it and that token is faked.
TOKC = set(F.ALNUM + "_-")
B64C = set(F.ALNUM + "+/")
JWTISH = re.compile(r"eyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){1,2}")
PEM_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]{2,40}-----.*?-----END [A-Z0-9 ]{2,40}-----", re.S)
BREAK_FWD = re.compile(r"(?:\r?\n|\\r\\n|\\n)[ \t>]*")
BREAK_BACK = re.compile(r"(?:\r?\n|\\r\\n|\\n)[ \t>]*$")


def _grow(t: str, a: int, b: int, chars: set) -> tuple[int, int]:
    while a > 0 and t[a - 1] in chars:
        a -= 1
    while b < len(t) and t[b] in chars:
        b += 1
    return a, b


def _b64ish(s: str) -> bool:
    return len(s) >= 40 and "//" not in s and F.entropy(s) >= 4.0 and sum(c in F.DIGITS for c in s) >= 2


def pem_spans(t: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in PEM_BLOCK.finditer(t)] if "-----BEGIN" in t else []


def token_span(t: str, s: int, e: int, pems=()) -> tuple[int, int]:
    """[a, b) of the token holding t[s:e]: the PEM block, else the run of [A-Za-z0-9_-], widened to the
    JWT it belongs to, to a base64 blob (+ / and padding) and to the other lines of a wrapped blob."""
    for ps, pe in pems:
        if ps <= s and e <= pe:
            return ps, pe
    a, b = _grow(t, s, e, TOKC)
    ra, rb = _grow(t, a, b, TOKC | {"."})
    for m in JWTISH.finditer(t, ra, rb):
        if m.start() < e and m.end() > s:
            a, b = min(a, m.start()), max(b, m.end())
    if (a and t[a - 1] in "+/") or (b < len(t) and t[b] in "+/") or any(c in "+/" for c in t[s:e]):
        ba, bb = _grow(t, a, b, B64C)
        if _b64ish(t[ba:bb]):
            a, b = ba, bb
            while b < len(t) and t[b] == "=" and b - bb < 2:
                b += 1
    if _b64ish(t[a:b].rstrip("=")):
        while True:  # following lines of the same blob
            m = BREAK_FWD.match(t, b)
            if not m:
                break
            na = nb = m.end()
            while nb < len(t) and t[nb] in B64C | {"="}:
                nb += 1
            if nb - na < 16 or not (nb == len(t) or t[nb] in "\r\n\\\"' "):
                break
            b = nb
        while True:  # preceding lines
            m = BREAK_BACK.search(t, max(0, a - 12), a)
            if not m:
                break
            pa = pb = m.start()
            while pa > 0 and t[pa - 1] in B64C:
                pa -= 1
            if pa > 1 and t[pa - 1] == "\\" and t[pa] == "n" and pb - pa > 1:
                pa += 1  # the line starts after an escaped \n
                start_ok = True
            else:
                start_ok = pa == 0 or t[pa - 1] in "\n\"' >"
            if pb - pa < 40 or not start_ok:
                break
            a = pa
    return a, b


# ---------------------------------------------------------------- leftover pieces of a token

K = 12  # a piece of an original token this long is a leftover (escaped forms, cut context windows)
MIN_CHANGED = 6
RUN = re.compile(r"[A-Za-z0-9+/_\-=.]{%d,}" % K)


WORDISH = re.compile(r"[a-z]{5}|[A-Z]{6}")


def random_like(g: str) -> bool:
    """A piece of a key, not of text: two classes of A-Z / a-z / 0-9, 8 distinct characters, no lowercase
    word or CONSTANT_NAME run. Values that carry text (query strings, JSON, code) would otherwise spread
    their changed words (parameter names, package names, ids) to every issue that mentions them."""
    classes = {F.char_class(c) for c in g} - {"."}
    return len(classes) >= 2 and len(set(g)) >= 8 and not WORDISH.search(g)


def kgram_index(tokens: list[str], fakes: list[str]) -> dict[str, tuple[int, int]]:
    """k-gram -> (token id, offset) for k-grams that carry the secret: at least MIN_CHANGED of their
    characters change in the fake and no fake keeps them. Mostly-structure
    k-grams (JSON keys inside base64 next to a kept timestamp prefix, a kept RSA exponent before the END
    line) recur in other tokens' fakes by chance; six random characters do not."""
    idx = {}
    kept = {tok[o:o + K] for tok, fk in zip(tokens, fakes) for o in range(len(tok) - K + 1)
            if fk[o:o + K] == tok[o:o + K]}
    for tid, (tok, fk) in enumerate(zip(tokens, fakes)):
        diff = [0]
        for x, y in zip(tok, fk):
            diff.append(diff[-1] + (x != y))
        for o in range(len(tok) - K + 1):
            g = tok[o:o + K]
            if diff[o + K] - diff[o] < MIN_CHANGED or g in kept or not random_like(g):
                continue
            idx.setdefault(g, (tid, o))  # a secret in several tokens: any of them lines the piece up
    return idx


def align_pieces(t: str, idx, tokens, fakes) -> tuple[str, int]:
    """Replace every piece of t that lines up with an original token by the same piece of its fake."""
    if not t:
        return t, 0
    out, n = None, 0
    for r in RUN.finditer(t):
        i = r.start()
        while i <= r.end() - K:
            hit = idx.get(t[i:i + K])
            if not hit:
                i += 1
                continue
            tid, o = hit
            tok = tokens[tid]
            i0, o0 = i, o
            while i0 > 0 and o0 > 0 and t[i0 - 1] == tok[o0 - 1]:
                i0, o0 = i0 - 1, o0 - 1
            i1, o1 = i + K, o + K
            while i1 < len(t) and o1 < len(tok) and t[i1] == tok[o1]:
                i1, o1 = i1 + 1, o1 + 1
            if out is None:
                out = list(t)
            out[i0:i1] = fakes[tid][o0:o1]
            n += 1
            # a piece of another token may start inside this one's tail (a kept JOSE header, say)
            i = max(i + 1, i1 - K + 1)
    return ("".join(out) if out is not None else t), n


def kgram_hits(new: str, old: str, idx) -> int:
    """Original k-grams still where they were. When the length changed (an escaped variant), anywhere.
    An original k-gram elsewhere in the output was written by a fake (public structure such as JSON keys
    in base64 or a kept RSA exponent before the END line, which the fakes of other tokens share)."""
    same = len(new) == len(old)
    return sum(1 for r in RUN.finditer(new) for i in range(r.start(), r.end() - K + 1)
               if new[i:i + K] in idx and (not same or old[i:i + K] == new[i:i + K]))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True, help="extracted Secret-Leak-Detection-Issue-Report dir")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kingfisher", type=Path, required=True, help="Kingfisher checkout at the v1 rules commit")
    ap.add_argument("--allow-leftovers", action="store_true",
                    help="write the output even if verification finds original pieces; their places go in the report")
    a = ap.parse_args()

    tables = {}
    for name in CSV_FILES:
        header, rows, eol = read_csv(a.src / "Data" / name)
        tables[name] = (header, rows, eol)
    others = {}
    for p in sorted(a.src.rglob("*")):
        rel = p.relative_to(a.src)
        if p.is_file() and not (rel.parts[0] == "Data" and rel.name in tables):
            try:
                others[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                others[rel] = None

    def texts():
        """Every text field: (table, row index, column index, text); other files as (rel, None, None, text)."""
        for name, (header, rows, _) in tables.items():
            tcols = [i for i, h in enumerate(header) if h in TEXT_COLUMNS]
            for ri, r in enumerate(rows):
                for i in tcols:
                    yield name, ri, i, r[i]
        for rel, t in others.items():
            if t is not None:
                yield rel, None, None, t

    # positives and where they come from
    cands, val_src = {}, collections.defaultdict(set)
    for name, (header, rows, _) in tables.items():
        ci, li = header.index("candidate_string"), header.index("label")
        srcs = [(header.index(c), p) for c, p in SOURCE_COLUMNS.items() if c in header]
        for r in rows:
            if r[li].strip() != "1":
                continue
            pre, val, post = split_candidate(r[ci])
            cands[r[ci]] = (pre, val, post)
            for i, p in srcs:
                val_src[val].add(p + r[i])
    report = {"positive_candidates": len(cands), "positive_values": len(val_src)}

    prefixes = learn_prefixes(val_src)
    report["learned_prefixes"] = {p: n for p, n in sorted(prefixes.items())}
    oracle = F.Oracle(a.kingfisher)
    faker = F.Faker(oracle, prefixes)

    # 1. widen every occurrence of a strong value to its token
    strong_vals = {v for v in val_src if not weak(v)}
    vrx = trie_regex(strong_vals)
    homes = collections.defaultdict(collections.Counter)  # value -> Counter((token, offset))
    for _, _, _, t in texts():
        if not t:
            continue
        pems = None
        for m in vrx.finditer(t):
            if pems is None:
                pems = pem_spans(t)
            s0, e0 = token_span(t, m.start(), m.end(), pems)
            homes[m.group()][(t[s0:e0], m.start() - s0)] += 1
    for v in strong_vals:
        if not homes[v]:
            homes[v][(v, 0)] += 1

    # 2. keep the maximal tokens; every other token is a piece of one of them
    toks = sorted({tok for c in homes.values() for tok, _ in c}, key=lambda x: (-len(x), x))
    maximal, where, first = [], {}, collections.defaultdict(list)
    for tok in toks:
        found = None
        if len(tok) >= K:
            for mid, o in first.get(tok[:K], ()):
                if maximal[mid][o:o + len(tok)] == tok:
                    found = (mid, o)
                    break
        else:
            for mid, big in enumerate(maximal):
                o = big.find(tok)
                if o >= 0:
                    found = (mid, o)
                    break
        if found is None:
            found = (len(maximal), 0)
            maximal.append(tok)
            for o in range(len(tok) - K + 1):
                first[tok[o:o + K]].append((found[0], o))
        where[tok] = found
    del first
    report["tokens"] = {"maximal": len(maximal), "all": len(toks),
                        "values_inside_a_longer_token": sum(1 for v, c in homes.items()
                                                            if any(tok != v for tok, _ in c))}

    # 3. fake the maximal tokens
    fakes, methods, exempt = [], collections.Counter(), collections.Counter()
    for tok in maximal:
        f, m = faker.fake_value(tok)
        if len(f) != len(tok):
            raise SystemExit(f"length changed (shape {F.shape(tok)[:60]}, method {m})")
        if f == tok:
            why = "no letters or digits" if not re.search(r"[A-Za-z0-9]", tok) else \
                "public JOSE header or JSON start" if m in ("jose-header", "jose-public") else None
            if why is None:
                raise SystemExit(f"token left unchanged without reason (shape {F.shape(tok)[:60]})")
            exempt[why] += 1
        methods[m] += 1
        fakes.append(f)
    report["methods"] = dict(methods.most_common())
    report["left_unchanged"] = dict(exempt)

    def fake_of(tok: str) -> str:
        mid, o = where[tok]
        return fakes[mid][o:o + len(tok)]

    # a value's fake is its piece of the fake of its most frequent token
    fake, split_homes = {}, 0
    for v in strong_vals:
        (tok, o), _ = homes[v].most_common(1)[0]
        mid, mo = where[tok]
        fake[v] = fakes[mid][mo + o:mo + o + len(v)]
        if len({where[tk][0] for tk, _ in homes[v]}) > 1:
            split_homes += 1
    report["tokens"]["values_in_more_than_one_maximal_token"] = split_homes
    for v in val_src:
        if v in fake or not weak(v):
            continue
        f, m = faker.fake_value(v)
        if f == v:
            if re.search(r"[A-Za-z0-9]", v) and m not in ("jose-header", "jose-public"):
                raise SystemExit(f"value left unchanged without reason (shape {F.shape(v)[:60]})")
            continue
        if len(f) != len(v):
            raise SystemExit(f"length changed (shape {F.shape(v)[:60]}, method {m})")
        fake[v] = f

    # 4. replacement units: tokens and strong values everywhere (and their escaped forms), weak values only
    #    inside their full candidate string
    units = {}
    for tok in toks:
        units.setdefault(tok, fake_of(tok))
    for v in strong_vals:
        units.setdefault(v, fake[v])
    for x in list(units):
        for tr in VARIANTS:
            if tr(x) != x:
                units.setdefault(tr(x), tr(units[x]))
    for c, (pre, val, post) in cands.items():
        if val in fake and weak(val):
            units.setdefault(c, pre + fake[val] + post)
    units = {k: v for k, v in units.items() if k != v}
    report["weak_values_replaced_in_candidate_context_only"] = sum(1 for c, (_, v, _) in cands.items()
                                                                   if v in fake and weak(v))
    rx = trie_regex(units)
    idx = kgram_index(maximal, fakes)

    def sub(text: str) -> tuple[str, int]:
        if not text:
            return text, 0
        return align_pieces(rx.sub(lambda m: units[m.group()], text), idx, maximal, fakes)

    changed = collections.Counter()
    out_tables = {}
    for name, (header, rows, eol) in tables.items():
        tcols = [i for i, h in enumerate(header) if h in TEXT_COLUMNS]
        new_rows = []
        for r in rows:
            nr = list(r)
            for i in tcols:
                nr[i], pieces = sub(r[i])
                if nr[i] != r[i]:
                    changed[f"{name}:{header[i]}"] += 1
                if pieces:
                    changed["leftover pieces aligned"] += pieces
                if len(nr[i]) != len(r[i]):
                    # only an escaped variant (URL-encoded base64 whose +/ moved) may change the length
                    if all(len(units[m.group()]) == len(m.group()) for m in rx.finditer(r[i])):
                        raise SystemExit(f"field length changed in {name}:{header[i]}")
                    changed["length changed by an escaped variant"] += 1
            new_rows.append(nr)
        out_tables[name] = (header, new_rows, eol)
    out_others = {}
    for rel, t in others.items():
        out_others[rel] = sub(t)[0] if t is not None else None
    report["fields_changed"] = dict(changed)

    # 5. verification on the output
    weak_cands = [c for c, (_, v, _) in cands.items() if v in fake and weak(v)]
    originals = set(units) - {v for v in units.values()}
    probe = trie_regex(originals | set(weak_cands))
    leftovers = elsewhere = 0
    diag = collections.Counter()
    left_at = []
    for name, (header, rows, _) in out_tables.items():
        orig = tables[name][1]
        for ri, (r, o) in enumerate(zip(rows, orig)):
            for i, h in enumerate(header):
                if h in TEXT_COLUMNS:
                    hits = [m.group() for m in probe.finditer(r[i])
                            if len(r[i]) != len(o[i]) or o[i][m.start():m.end()] == m.group()]
                    g = kgram_hits(r[i], o[i], idx)
                    elsewhere += kgram_hits(r[i], "", idx) - g
                    if hits or g:
                        leftovers += 1
                        left_at.append({"file": f"Data/{name}", "data_row": ri + 1, "column": h,
                                        "exact_values": len(hits), "pieces": g})
                        for x in hits:
                            diag[("exact", F.shape(x)[:40])] += 1
                        if g:
                            diag[("piece", h)] += g
                elif r[i] != o[i]:
                    raise SystemExit(f"non-text column changed: {name}:{h}")
        li = header.index("label")
        if [r[li] for r in rows] != [o[li] for o in orig]:
            raise SystemExit("labels changed")
    for rel, t in out_others.items():
        if t is not None and (any(len(t) != len(others[rel]) or others[rel][m.start():m.end()] == m.group()
                                  for m in probe.finditer(t)) or kgram_hits(t, others[rel], idx)):
            leftovers += 1
            diag[("file", str(rel))] += 1
            left_at.append({"file": str(rel)})
    if leftovers:
        for k, n in diag.most_common(40):
            print(n, k)
        if not a.allow_leftovers:
            raise SystemExit(f"{leftovers} fields still hold an original value or piece")
        print(f"WARNING: {leftovers} fields still hold an original value or piece; written anyway "
              "(--allow-leftovers), places in SANITIZE_REPORT.json", file=sys.stderr)

    # candidate and text agree: where the original value stood in its row, the row now holds the fake
    agree = collections.Counter()
    for name, (header, rows, _) in out_tables.items():
        ci, li = header.index("candidate_string"), header.index("label")
        tcols = [i for i, h in enumerate(header) if h in TEXT_COLUMNS and i != ci]
        for r, o in zip(rows, tables[name][1]):
            if o[li].strip() != "1":
                continue
            v = cands[o[ci]][1]
            if v not in fake:
                continue
            for i in tcols:
                for m in re.finditer(re.escape(v), o[i]):
                    agree[r[i][m.start():m.end()] == fake[v]] += 1
    report["candidate_matches_text"] = {"yes": agree[True], "no": agree[False]}
    report["verification"] = {"fields_with_original_values_pieces_or_escaped_forms": leftovers,
                              "leftover_places": left_at,
                              "original_pieces_reproduced_by_fakes_elsewhere": elsewhere,
                              "labels_and_non_text_columns_equal": True}

    # write the sanitized package: CSVs plus every other file, text files passed through the same replacement
    a.out.mkdir(parents=True, exist_ok=True)
    other = collections.Counter()
    (a.out / "Data").mkdir(exist_ok=True)
    for name, table in out_tables.items():
        write_csv(a.out / "Data" / name, *table)
    for rel, t in out_others.items():
        dst = a.out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if t is None:
            shutil.copy2(a.src / rel, dst)
            other["binary copied"] += 1
            continue
        other["text replaced" if t != others[rel] else "text unchanged"] += 1
        dst.write_text(t, encoding="utf-8")
    report["other_files"] = dict(other)
    (a.out / "SANITIZE_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in report.items() if k != "learned_prefixes"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
