"""Parse every downloaded secret-scanner catalog into one index (rules.json).

Each entry: source, path (repo-relative), id, name, regex, keywords, examples, negatives.
Run with python3 -I; the downloaded trees are data only.
"""
import glob
import json
import os
import re
import sys
import tomllib

import yaml

SRC = sys.argv[1]
OUT = sys.argv[2]
rules = []


def add(source, path, rid, name, regex, keywords=(), examples=(), negatives=()):
    rules.append({"source": source, "path": path, "id": rid, "name": name, "regex": regex,
                  "keywords": list(keywords or ()), "examples": list(examples or ()),
                  "negatives": list(negatives or ())})


def rel(p, root):
    return os.path.relpath(p, root)


# gitleaks
root = f"{SRC}/gitleaks/repo"
cfg = tomllib.load(open(f"{root}/config/gitleaks.toml", "rb"))
for r in cfg.get("rules", []):
    add("gitleaks/gitleaks", "config/gitleaks.toml", r["id"], r.get("description", ""), r.get("regex", ""),
        r.get("keywords"))

# betterleaks (as imported by kingfisher) and veles
kroot = f"{SRC}/kingfisher/repo"
for fname, source in (("betterleaks.yml", "betterleaks/betterleaks (via mongodb/kingfisher)"),
                      ("veles.yml", "google/osv-scalibr veles (via mongodb/kingfisher)")):
    p = f"{kroot}/crates/kingfisher-rules/generated/rules/{fname}"
    data = yaml.safe_load(open(p))
    for r in data.get("rules", []):
        add(source, rel(p, kroot), r.get("id"), r.get("name"), r.get("pattern", ""), r.get("keywords"),
            r.get("examples"), r.get("negative_examples"))

# noseyparker
nroot = f"{SRC}/noseyparker/repo"
for p in sorted(glob.glob(f"{nroot}/crates/noseyparker/data/default/builtin/rules/*.yml")):
    data = yaml.safe_load(open(p))
    for r in data.get("rules", []):
        add("praetorian-inc/noseyparker", rel(p, nroot), r.get("id"), r.get("name"), r.get("pattern", ""), (),
            r.get("examples"), r.get("negative_examples"))

# trufflehog: regexp.MustCompile + Keywords
troot = f"{SRC}/trufflehog/repo"
mc = re.compile(r'(\w+)\s*=\s*regexp\.MustCompile\((?:detectors\.PrefixRegex\((\[\]string\{[^}]*\})\)\s*\+\s*)?`([^`]*)`\)')
kw = re.compile(r'func \(s Scanner\) Keywords\(\) \[\]string \{\s*return \[\]string\{([^}]*)\}', re.S)
for p in sorted(glob.glob(f"{troot}/pkg/detectors/*/*.go") + glob.glob(f"{troot}/pkg/detectors/*/*/*.go")):
    if p.endswith("_test.go"):
        continue
    text = open(p, errors="replace").read()
    pats = mc.findall(text)
    if not pats:
        continue
    k = kw.search(text)
    keywords = re.findall(r'"([^"]+)"', k.group(1)) if k else []
    name = os.path.basename(os.path.dirname(p))
    for var, prefix, pat in pats:
        add("trufflesecurity/trufflehog", rel(p, troot), f"{name}:{var}", name,
            (f"PrefixRegex({prefix}) + " if prefix else "") + pat, keywords)

# credsweeper
croot = f"{SRC}/credsweeper/repo"
for r in yaml.safe_load(open(f"{croot}/credsweeper/rules/config.yaml")):
    for v in r.get("values", []):
        add("Samsung/CredSweeper", "credsweeper/rules/config.yaml", r["name"], r["name"], v,
            r.get("required_substrings"))

# nuclei
uroot = f"{SRC}/nuclei/repo"
for p in sorted(glob.glob(f"{uroot}/file/keys/**/*.yaml", recursive=True)
                + glob.glob(f"{uroot}/http/exposures/tokens/**/*.yaml", recursive=True)
                + glob.glob(f"{uroot}/http/exposures/configs/**/*.yaml", recursive=True)):
    try:
        data = yaml.safe_load(open(p))
    except Exception:
        continue
    if not isinstance(data, dict):
        continue
    regs = []
    for block in (data.get("file") or []) + (data.get("http") or []):
        for key in ("extractors", "matchers"):
            for m in block.get(key) or []:
                if m.get("type") == "regex":
                    regs += m.get("regex") or []
                elif m.get("type") == "word":
                    regs += [re.escape(w) for w in m.get("words") or []]
    add("projectdiscovery/nuclei-templates", rel(p, uroot), data.get("id"), (data.get("info") or {}).get("name"),
        " | ".join(regs[:4]))

# semgrep generic/secrets
sroot = f"{SRC}/semgrep/repo"
for p in sorted(glob.glob(f"{sroot}/generic/secrets/**/*.yaml", recursive=True)):
    try:
        data = yaml.safe_load(open(p))
    except Exception:
        continue
    for r in (data or {}).get("rules", []):
        pat = r.get("pattern-regex") or ""
        if not pat:
            for item in r.get("patterns", []) or []:
                if isinstance(item, dict) and "pattern-regex" in item:
                    pat = item["pattern-regex"]
                    break
        if not pat:
            for item in r.get("pattern-either", []) or []:
                if isinstance(item, dict) and "pattern-regex" in item:
                    pat = item["pattern-regex"]
                    break
        add("semgrep/semgrep-rules", rel(p, sroot), r.get("id"), r.get("message", "")[:80], pat)

# whispers
wroot = f"{SRC}/whispers/repo"
for p in sorted(glob.glob(f"{wroot}/whispers/rules/*.yml")):
    data = yaml.safe_load(open(p)) or {}
    for rid, r in data.items():
        if not isinstance(r, dict):
            continue
        val = (r.get("value") or {}).get("regex") or (r.get("key") or {}).get("regex") or ""
        add("Skyscanner/whispers", rel(p, wroot), rid, r.get("description", ""), val)

# detect-secrets
droot = f"{SRC}/detect-secrets/repo"
for p in sorted(glob.glob(f"{droot}/detect_secrets/plugins/*.py")):
    text = open(p).read()
    m = re.search(r"secret_type = '([^']+)'", text)
    pats = re.findall(r"re\.compile\(\s*r?(['\"])(.+?)\1", text, re.S)
    for _, pat in pats[:6]:
        add("Yelp/detect-secrets", rel(p, droot), os.path.basename(p)[:-3], m.group(1) if m else "", pat)

# secrets-patterns-db
proot = f"{SRC}/secrets-patterns-db/repo"
data = yaml.safe_load(open(f"{proot}/db/rules-stable.yml"))
for item in data.get("patterns", []):
    pt = item.get("pattern", {})
    add("mazen160/secrets-patterns-db", "db/rules-stable.yml", pt.get("name"), pt.get("name"), pt.get("regex", ""))

# talisman
aroot = f"{SRC}/talisman/repo"
for p in sorted(glob.glob(f"{aroot}/detector/pattern/*.go")):
    if p.endswith("_test.go"):
        continue
    for pat in re.findall(r'regexp\.MustCompile\(`([^`]*)`\)', open(p).read()):
        add("thoughtworks/talisman", rel(p, aroot), "pattern", "", pat)
    for pat in re.findall(r'regexp\.MustCompile\("((?:[^"\\]|\\.)*)"\)', open(p).read()):
        add("thoughtworks/talisman", rel(p, aroot), "pattern", "", pat)

# shhgit
hroot = f"{SRC}/shhgit/repo"
cfgp = f"{hroot}/config.yaml"
if os.path.exists(cfgp):
    data = yaml.safe_load(open(cfgp))
    for s in data.get("signatures", []):
        add("eth0izzle/shhgit", "config.yaml", s.get("name"), s.get("name"), s.get("regex") or s.get("match") or "",
            [s.get("part", "")])

# ripsecrets
rroot = f"{SRC}/ripsecrets/repo"
for p in glob.glob(f"{rroot}/src/**/*.rs", recursive=True):
    text = open(p).read()
    for pat in re.findall(r'r#?"((?:[^"\\]|\\.){8,})"#?', text):
        if any(t in pat for t in ("[", "\\b", "(")):
            add("sirwart/ripsecrets", rel(p, rroot), "predefined", "", pat)

json.dump(rules, open(OUT, "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(len(rules))
print(Counter(r["source"] for r in rules))
