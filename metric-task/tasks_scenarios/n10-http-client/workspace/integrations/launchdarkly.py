"""Feature flags for the storefront, read from LaunchDarkly's REST API at deploy time."""
import json
import urllib.request

from integrations import settings

API = "https://app.launchdarkly.com/api/v2"
PROJECT = "orderdesk"


def flag_states(environment="production", *, tag=None):
    """{flag_key: on} for the environment; archived flags are skipped."""
    query = f"env={environment}&summary=true" + (f"&tag={tag}" if tag else "")
    req = urllib.request.Request(f"{API}/flags/{PROJECT}?{query}")
    req.add_header("Authorization", {{decoy:settings_ref_0}})
    with urllib.request.urlopen(req, timeout=10) as resp:
        items = json.loads(resp.read())["items"]
    return {f["key"]: f["environments"][environment]["on"] for f in items if not f.get("archived")}
