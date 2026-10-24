"""Build coding_agent_secret_sources_master_v3.csv.

One row = one distinct secret type OR one distinct coding/agent context (the v2 bundled rows are split apart).
Values in the example columns are deterministic fakes from v3_engine (format-correct, not real credentials).

  python3 -I build_v3.py <out.csv>
"""
from __future__ import annotations

import csv
import re
import sys

import v3_engine as E
from v3_render import RENDER

COLUMNS = ["Source_ID", "Macro_Category", "Sub_Category", "Reference_Benchmark_or_Repo", "Source_Description_KR",
           "Typical_File_Paths_or_Streams", "Agent_Acquisition_Channel", "Data_Format_or_Syntax",
           "Asset_or_Host_Pair_Context", "Key_Identifiers_and_Indicators", "Regex_or_Structural_Signature",
           "Synthetic_Positive_Example_Raw", "Hard_Negative_Counterpart_Example", "Risk_Severity",
           "SLM_Training_Guideline_KR"]

ROWS: list[dict] = []

# macro category -> default files / channel / format for its service rows
CATS = {
    "01": ("01_Generic_High_Frequency_Patterns", "*.env, *.py, *.js, *.ts, *.go, *.yaml", "Source_Code / Config",
           "Key-Value Assignment"),
    "02": ("02_AI_LLM_&_MCP_Ecosystem", ".env, config.py, ~/.config/*/config.toml, claude_desktop_config.json",
           "File_Read_Tool / Source_Code", "Prefix Token"),
    "03": ("03_Cloud_Providers_Global_&_KR", ".env, ~/.aws/credentials, *.tf, *.yaml", "File_Read_Tool / Config",
           "Prefix Token"),
    "04": ("04_Databases_BaaS_&_Search_Engines", ".env, config.*, docker-compose.yml", "File_Read_Tool / Source_Code",
           "Connection String / Token"),
    "05": ("05_VCS_CICD_&_Package_Supply_Chain", "~/.npmrc, ~/.git-credentials, .github/workflows/*.yml, .pypirc",
           "File_Read_Tool / Bash_Tool_Stdout", "Prefix Token"),
    "06": ("06_Secret_Managers_IaC_&_Containers", "~/.vault-token, *.tf, ~/.docker/config.json, kubeconfig",
           "File_Read_Tool / Bash_Tool_Stdout", "Token / JSON"),
    "07": ("07_Enterprise_Frameworks_&_Web_Configs", "application.properties, web.config, wp-config.php, config/*.php",
           "File_Read_Tool / Source_Code", "Config File"),
    "08": ("08_FinTech_Payment_&_Quant_APIs", ".env, server.js, payment_controller.*, kis_devlp.yaml",
           "Source_Code / Config", "Prefix Token"),
    "09": ("09_Messaging_CRM_Collab_&_Webhooks", ".env, config.*, serverless.yml, .github/workflows/*.yml",
           "Source_Code / Config", "Prefix Token"),
    "10": ("10_Observability_CDN_&_Mesh_VPN", ".env, datadog.yaml, *.tf, docker-compose.yml",
           "File_Read_Tool / Config", "Prefix Token"),
    "11": ("11_Cryptography_PKI_&_Auth_Protocols", "id_rsa, *.pem, *.key, ~/.netrc, .npmrc", "File_Read_Tool",
           "PEM / JWT / INI"),
    "12": ("12_Agentic_Runtime_KR_Public_&_Benchmarks", "(see row)", "(see row)", "(see row)"),
    "13": ("13_Mobile_IoT_Embedded_&_Web3", "google-services.json, Appfile, local.properties, hardhat.config.js",
           "File_Read_Tool / Source_Code", "Config / Key"),
    "14": ("14_Scanner_Catalog_Service_Tokens", ".env, config.*, source files, CI config",
           "File_Read_Tool / Source_Code", "Prefix Token"),
}

_seen_pos: set[str] = set()


def _unique(snippet: str, tag: str) -> str:
    """Guarantee a positive snippet is globally unique by appending a tiny deterministic comment if needed."""
    if snippet not in _seen_pos:
        _seen_pos.add(snippet)
        return snippet
    marker = E.d("uniq:" + tag).chars(4, E.HEX)
    alt = snippet + f"   # ref:{marker}"
    while alt in _seen_pos:
        marker = E.d("uniq:" + tag + marker).chars(4, E.HEX)
        alt = snippet + f"   # ref:{marker}"
    _seen_pos.add(alt)
    return alt


def add(cat, sub, ref, what, host, idents, regex, posval, negval, sev, *, ctx="env", negctx=None, var=None,
        flag="", channel=None, fmt=None, files=None, guide, rhost=None, **_ignore):
    c = CATS[cat]
    var = var or (sub.upper().split("/")[0][:40])
    rh = rhost if rhost is not None else host
    pos = _unique(RENDER[ctx](var, posval, rh, flag), sub)
    neg = RENDER[negctx or ctx](var, negval, rh, flag)
    ROWS.append({
        "Macro_Category": c[0], "Sub_Category": sub, "Reference_Benchmark_or_Repo": ref,
        "Source_Description_KR": what, "Typical_File_Paths_or_Streams": files or c[1],
        "Agent_Acquisition_Channel": channel or c[2], "Data_Format_or_Syntax": fmt or c[3],
        "Asset_or_Host_Pair_Context": host, "Key_Identifiers_and_Indicators": idents,
        "Regex_or_Structural_Signature": regex, "Synthetic_Positive_Example_Raw": pos,
        "Hard_Negative_Counterpart_Example": neg, "Risk_Severity": sev, "SLM_Training_Guideline_KR": guide,
    })


def _alnum_class(alphabet):
    if alphabet == E.HEX:
        return "a-f0-9"
    if alphabet == E.ALNUM:
        return "A-Za-z0-9"
    if alphabet == E.B64URL:
        return "A-Za-z0-9_-"
    if alphabet == E.BASE32:
        return "A-Z2-7"
    return "A-Za-z0-9"


def pfx(cat, sub, vendor, ref, host, env_name, prefix, n, *, alph=E.ALNUM, sep="_", sev="High", ctx="env",
        regex=None, what=None, idents=None, files=None, channel=None, fmt=None, flag="", guide=None, neg="placeholder",
        checksum=False, var=None):
    """A prefix+body token. Auto-builds a format-correct fake value, regex, matched hard negative, and KR text."""
    if checksum:
        posval = E.tok_crc(prefix, n, tag="v3:" + sub)
    else:
        posval = E.tok(prefix, n, alph, sep=sep, tag="v3:" + sub)
    full_prefix = prefix + sep
    cls = _alnum_class(alph)
    # no trailing \b: a body ending in '-' (B64URL) has no word boundary before the newline
    regex = regex or rf"\b{re.escape(full_prefix)}[{cls}]{{{n}}}"
    if neg == "placeholder":
        negval = f"{full_prefix}" + "x" * n
    elif neg == "envref":
        negval = "${" + env_name + "}"
    elif neg == "example":
        negval = f"{full_prefix}EXAMPLE" + "0" * max(0, n - 7)
    elif neg == "yourkey":
        negval = f"{full_prefix}YOUR_{vendor.upper().replace(' ', '_')}_KEY_HERE"
    else:
        negval = neg
    what = what or (f"{vendor}의 {sub.split('_',1)[-1].replace('_',' ')} 자격증명. 접두사 `{full_prefix}` 뒤에 "
                    f"본문 {n}자가 붙는 형식으로, {host}에 접근한다.")
    idents = idents or f"{env_name}, {prefix}"
    guide = guide or (f"접두사 `{full_prefix}`와 본문 길이 {n}로 형식을 확정한다. Hard Negative는 같은 접두사를 가진 "
                      f"플레이스홀더(`{negval}`)이므로, 접두사만 보고 마스킹하지 말고 본문이 실제 난수인지 "
                      f"반복문자·`${{VAR}}` 참조·`EXAMPLE`·`YOUR_` 인지로 구분하도록 학습한다.")
    add(cat, sub, ref, what, host, idents, regex, posval, negval, sev, ctx=ctx, flag=flag, channel=channel,
        fmt=fmt or "Prefix Token", files=files, guide=guide, var=var or env_name)


# rotate contexts for auto-generated rows so snippets vary
_AUTO_CTX = ["env", "yaml", "json", "py", "js", "toml", "ini", "export"]


def _auto_ctx(i):
    return _AUTO_CTX[i % len(_AUTO_CTX)]


def main():
    import v3_data_services
    import v3_data_agent
    import v3_data_supp
    import v3_data_supp2
    import v3_data_supp3
    import v3_data_auto

    v3_data_services.populate(sys.modules[__name__])
    hand = len(ROWS)
    v3_data_agent.populate(sys.modules[__name__])
    v3_data_supp.populate(sys.modules[__name__])
    v3_data_supp2.populate(sys.modules[__name__])
    v3_data_supp3.populate(sys.modules[__name__])
    agent_n = len(ROWS) - hand
    target = 640
    v3_data_auto.populate(sys.modules[__name__], limit=max(0, target - len(ROWS)))
    auto_n = len(ROWS) - hand - agent_n

    # assign Source_ID in order
    for i, r in enumerate(ROWS, 1):
        r["Source_ID"] = f"SRC-{i:03d}"

    _validate()

    out = sys.argv[1] if len(sys.argv) > 1 else "coding_agent_secret_sources_master_v3.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        for r in ROWS:
            w.writerow(r)
    print(f"wrote {len(ROWS)} rows to {out}  (hand={hand}, agent={agent_n}, auto={auto_n})")
    return out


def _validate():
    import collections
    errs = []
    # 1. no empty cell
    for r in ROWS:
        for col in COLUMNS:
            v = r.get(col, "")
            if v is None or str(v).strip() == "":
                errs.append(f"{r.get('Source_ID')} empty {col}")
            elif "\x00" in str(v):  # NUL bytes truncate CSV fields on read
                errs.append(f"{r.get('Source_ID')} NUL byte in {col}")
    # 2. positives unique
    pos = [r["Synthetic_Positive_Example_Raw"] for r in ROWS]
    dup = [k for k, n in collections.Counter(pos).items() if n > 1]
    for dpv in dup[:20]:
        errs.append("dup positive: " + dpv[:60])
    # 3. regex should match its own positive (skip pure negative rows)
    mism = []
    for r in ROWS:
        rx = r["Regex_or_Structural_Signature"]
        posv = r["Synthetic_Positive_Example_Raw"]
        if r["Risk_Severity"] == "None (Negative)":
            continue
        try:
            if not re.search(rx, posv, re.S | re.M):
                mism.append(f"{r['Source_ID']} {r['Sub_Category']}  /{rx[:50]}/")
        except re.error as e:
            mism.append(f"{r['Source_ID']} BADRE {e} /{rx[:50]}/")
    # 4. hard negative must NOT look identical to positive
    for r in ROWS:
        if r["Synthetic_Positive_Example_Raw"] == r["Hard_Negative_Counterpart_Example"]:
            errs.append(f"{r['Source_ID']} pos==neg")
    if mism:
        print(f"[WARN] {len(mism)} regex/positive mismatches:")
        for m in mism:
            print("   ", m)
    if errs:
        print(f"[ERROR] {len(errs)} issues:")
        for e in errs[:40]:
            print("   ", e)
    if not mism and not errs:
        print("[OK] validation passed")


if __name__ == "__main__":
    main()
