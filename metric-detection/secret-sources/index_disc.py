"""Index the discovery-phase sources (not in the seed list) into rules_disc.json. Run with python3 -I."""
import glob
import json
import os
import re
import sys
import tomllib

import yaml

D = sys.argv[1]
OUT = sys.argv[2]
rules = []


def add(source, path, rid, name, regex, keywords=(), examples=(), negatives=()):
    rules.append({"source": source, "path": path, "id": rid, "name": name, "regex": regex,
                  "keywords": list(keywords or ()), "examples": [e for e in (examples or ()) if isinstance(e, str)],
                  "negatives": list(negatives or ())})


# secretlint: regex literals in rule sources
root = f"{D}/secretlint/repo"
lit = re.compile(r"(?<![\w)\]])/((?:\\/|[^/\n])+?)/([dgimsuy]*)(?=\s*[;,)\]}]|\s*$)", re.M)
for p in sorted(glob.glob(f"{root}/packages/@secretlint/secretlint-rule-*/src/*.ts")):
    pkg = p.split("/packages/")[1].split("/src/")[0]
    text = open(p).read()
    for m in lit.finditer(text):
        pat = m.group(1)
        if len(pat) < 8 or pat.startswith("*") or "//" in pat[:2]:
            continue
        if not any(c in pat for c in "[\\(?"):
            continue
        add("secretlint/secretlint", os.path.relpath(p, root), pkg, pkg, pat)

# GitHub docs: partner patterns table (no regex; provider + secret type)
root = f"{D}/github-docs/repo"
p = f"{root}/src/secret-scanning/data/pattern-docs/fpt/public-docs.yml"
for r in yaml.safe_load(open(p)):
    add("github/docs (secret scanning supported patterns)", os.path.relpath(p, root), r.get("secretType"),
        f"{r.get('provider')} | {r.get('supportedSecret')} | push_protection={r.get('hasPushProtection')}", "")

# betterleaks
root = f"{D}/betterleaks/repo"
cfg = tomllib.load(open(f"{root}/config/betterleaks.toml", "rb"))
for r in cfg.get("rules", []):
    add("betterleaks/betterleaks", "config/betterleaks.toml", r["id"], r.get("description", ""), r.get("regex", ""),
        r.get("keywords"))

# osv-scalibr veles: regexp.MustCompile in detector.go
root = f"{D}/osv-scalibr/repo"
mc = re.compile(r'regexp\.MustCompile\(\s*`([^`]*)`\s*\)|regexp\.MustCompile\(\s*"((?:[^"\\]|\\.)*)"\s*\)')
for p in sorted(glob.glob(f"{root}/veles/secrets/**/*.go", recursive=True)):
    if p.endswith("_test.go"):
        continue
    for a, b in mc.findall(open(p).read()):
        add("google/osv-scalibr (veles)", os.path.relpath(p, root), os.path.basename(os.path.dirname(p)),
            os.path.basename(os.path.dirname(p)), a or b.encode().decode("unicode_escape"))

# microsoft/security-utilities
root = f"{D}/ms-security-utilities/repo"
for p in sorted(glob.glob(f"{root}/GeneratedRegexPatterns/*.json")):
    for r in json.load(open(p)):
        add("microsoft/security-utilities", os.path.relpath(p, root), r.get("Id"), r.get("Name"), r.get("Pattern", ""),
            r.get("Signatures"))

# awslabs/git-secrets
root = f"{D}/git-secrets/repo"
for pat in re.findall(r"add_config 'secrets\.(?:patterns|allowed)' \"?'?(.+?)'?\"?$", open(f"{root}/git-secrets").read(), re.M):
    add("awslabs/git-secrets", "git-secrets", "register_aws", "AWS provider pattern", pat)

# checkov
root = f"{D}/checkov/repo"
for p in sorted(glob.glob(f"{root}/checkov/secrets/plugins/*.py")):
    for pat in re.findall(r"re\.compile\(\s*r?(['\"])(.+?)\1", open(p).read(), re.S):
        add("bridgecrewio/checkov", os.path.relpath(p, root), os.path.basename(p)[:-3], "", pat[1])

# avito-tech/deepsecrets
root = f"{D}/deepsecrets/repo"
for r in json.load(open(f"{root}/deepsecrets/rules/regexes.json")):
    add("avito-tech/deepsecrets", "deepsecrets/rules/regexes.json", r.get("id"), r.get("name"), r.get("pattern", ""))

# GitLab secret-detection-rules
root = f"{D}/gitlab-rules/repo"
for p in sorted(glob.glob(f"{root}/rules/**/*.toml", recursive=True)):
    cfg = tomllib.load(open(p, "rb"))
    for r in cfg.get("rules", []):
        add("gitlab-org/security-products/secret-detection/secret-detection-rules (gitlab.com)",
            os.path.relpath(p, root), r.get("id"), (r.get("vendor") or {}).get("name", ""), r.get("regex", ""),
            r.get("keywords"), r.get("examples"))

json.dump(rules, open(OUT, "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(len(rules))
for k, v in Counter(r["source"] for r in rules).items():
    print(v, k)
