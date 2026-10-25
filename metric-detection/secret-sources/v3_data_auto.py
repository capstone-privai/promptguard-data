"""Auto-expansion: mine the parsed scanner catalogs (rules_slim.json + rules_disc_slim.json) for additional distinct
prefix-token services not already hand-authored, and emit one row each via B.pfx. This turns the long tail of
service formats the discovery phase collected into coverage, with catalog-accurate prefixes and a templated
(but accurate) KR description / guideline.

Only rules whose regex is a clean `PREFIX<charclass>{N}` shape are used, so a format-correct fake value and a
matched placeholder negative can be synthesized deterministically.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# find a literal prefix (ending in a separator, OR a distinctive alnum run with a digit) followed by one
# char-class and a length, ANYWHERE in the regex (inside capture groups / (?:...), etc.)
_PAT = re.compile(
    r"(?P<prefix>(?:[A-Za-z0-9]{2,20}[._-]|[A-Za-z]{2,10}[0-9][A-Za-z0-9]{0,6}))"
    r"\[(?P<cls>[^\]]{1,50})\]"
    r"\{(?P<lo>\d{1,3})(?:,(?P<hi>\d{1,3}))?\}")

# escapes like \b and \s are not literal letters: without this, `\bAVNS_` reads as the prefix `bAVNS_`
def _unescape(rx):
    return re.sub(r"\\[A-Za-z]", " ", rx)

# fragments that are mid-pattern pieces, not real token prefixes
_FRAGMENTS = {"api03-", "admin01-", "v1_", "v2_", "fo1_", "ba3-", "ico-", "pub_", "key-", "pubkey-", "api-",
              "oauth_", "bglpat-", "bearer", "token", "secret", "x-", "0x"}

def _clsname(cls):
    c = cls.replace("\\", "")
    has = lambda *xs: all(x in c for x in xs)
    if has("a-f", "0-9") and "g-z" not in c and "a-z0-9" not in c.replace("a-f0-9", ""):
        # hex-ish: a-f + 0-9 (+ maybe A-F) and nothing else alphabetic beyond f
        if not any(ch in c for ch in ("g", "h", "i", "z")) or has("a-fA-F"):
            return "HEX"
    if ("_" in c or "-" in c) and has("A-Za-z0-9") or ("a-zA-Z0-9" in c and ("_" in c or "-" in c)):
        return "B64URL"
    if "A-Za-z0-9" in c or "a-zA-Z0-9" in c or "0-9A-Za-z" in c or "0-9a-zA-Z" in c:
        return "ALNUM"
    if "A-Z0-9" in c and "a-z" not in c:
        return "ALNUM"
    if "a-z0-9" in c and "A-Z" not in c:
        return "ALNUM"
    return None

# category routing by keyword in the service name / id
_ROUTE = [
    (("ai", "gpt", "llm", "openai", "anthropic", "cohere", "mistral", "replicate", "huggingface", "groq",
      "perplexity", "stability", "elevenlabs", "together", "nvidia", "clarifai", "pinecone", "llm"), "02"),
    (("aws", "gcp", "google", "azure", "alibaba", "tencent", "oracle", "ibm", "cloud", "digitalocean", "linode",
      "scaleway", "vultr", "hetzner", "yandex"), "03"),
    (("db", "database", "mongo", "postgres", "mysql", "redis", "snowflake", "databricks", "planetscale", "neon",
      "turso", "supabase", "algolia", "elastic", "clickhouse", "fauna", "cockroach", "influx", "search"), "04"),
    (("github", "gitlab", "bitbucket", "npm", "pypi", "cargo", "rubygems", "nuget", "packagist", "jfrog",
      "circleci", "travis", "buildkite", "drone", "codecov", "jenkins", "netlify", "vercel", "render", "heroku",
      "railway", "fly", "cloudsmith", "gitea", "artifactory", "sonar"), "05"),
    (("vault", "doppler", "infisical", "pulumi", "1password", "bitwarden", "akeyless", "docker", "harbor", "quay",
      "kubernetes", "k8s", "terraform", "consul", "nomad"), "06"),
    (("stripe", "paypal", "square", "adyen", "braintree", "shopify", "plaid", "paystack", "flutterwave", "razorpay",
      "mercado", "coinbase", "binance", "kraken", "finnhub", "polygon", "alpaca", "dwolla", "checkout"), "08"),
    (("slack", "discord", "telegram", "twilio", "sendgrid", "mailgun", "mailchimp", "notion", "airtable", "linear",
      "asana", "atlassian", "hubspot", "zendesk", "intercom", "front", "mattermost", "line", "pusher", "ably",
      "agora", "messagebird", "vonage", "nexmo", "postmark", "resend", "webhook", "clickup", "monday"), "09"),
    (("datadog", "newrelic", "sentry", "grafana", "dynatrace", "honeycomb", "cloudflare", "fastly", "akamai",
      "mapbox", "tailscale", "ngrok", "logdna", "loggly", "rollbar", "bugsnag", "pagerduty", "opsgenie",
      "sumologic", "splunk"), "10"),
]


def _route(name):
    low = name.lower()
    for keys, cat in _ROUTE:
        if any(k in low for k in keys):
            return cat
    return "14"  # scanner-catalog service tokens (fallback bucket)


def populate(B, limit=400):
    E = B.E
    try:
        rules = json.load(open(os.path.join(HERE, "rules_slim.json"))) + json.load(open(os.path.join(HERE, "rules_disc_slim.json")))
    except FileNotFoundError:
        return 0
    covered = set()  # prefixes already hand-authored
    for r in B.ROWS:
        for m in re.findall(r"\b([A-Za-z][A-Za-z0-9]{1,14}[._-])", _unescape(r["Regex_or_Structural_Signature"] or "")):
            covered.add(m.lower())
    seen_prefix = set(covered)
    added = 0
    for rule in rules:
        if added >= limit:
            break
        rx = (rule.get("regex") or "").strip()
        name = rule.get("name") or rule.get("id") or ""
        if not rx or not name or len(name) > 60:
            continue
        m = _PAT.search(_unescape(rx))
        if not m:
            continue
        prefix_full = m.group("prefix")
        pl = prefix_full.lower()
        if pl in seen_prefix or len(prefix_full) < 3 or pl in _FRAGMENTS:
            continue
        clsname = _clsname(m.group("cls"))
        if not clsname:
            continue
        cat = _route(name + " " + (rule.get("id") or "") + " " + (rule.get("path") or ""))
        lo = int(m.group("lo"))
        if lo < 10 or lo > 200:
            continue
        sep = prefix_full[-1]
        prefix = prefix_full[:-1]
        alph = {"B64URL": E.B64URL, "ALNUM": E.ALNUM, "HEX": E.HEX}[clsname]
        vendor = re.split(r"[ _/|]", name.strip())[0][:24] or prefix
        sub = "Auto_" + re.sub(r"[^A-Za-z0-9]+", "_", name.strip())[:44].strip("_") + "_" + prefix
        src = rule.get("source", "catalog")
        path = rule.get("path", "")
        ref = f"{src}" + (f" ({path}:{rule.get('id')})" if path else f" ({rule.get('id')})")
        try:
            B.pfx(cat, sub, vendor, ref, f"{vendor} API", sub.upper()[:40], prefix, lo, alph=alph, sep=sep,
                  sev="High", ctx=B._auto_ctx(added), var=re.sub(r"[^A-Za-z0-9_]", "_", sub.upper())[:40],
                  what=f"{vendor} 자격증명(스캐너 카탈로그 `{src}`에서 수집). 접두사 `{prefix}{sep}` 뒤 본문 {lo}자 형식이다.",
                  guide=f"접두사 `{prefix}{sep}`와 본문 길이({lo}자 내외)로 형식을 확정한다. 같은 접두사의 플레이스홀더·`${{VAR}}` 참조는 "
                        f"본문이 실제 난수가 아니므로 마스킹하지 않도록 학습한다.")
            seen_prefix.add(prefix_full.lower())
            added += 1
        except Exception:
            continue
    return added
