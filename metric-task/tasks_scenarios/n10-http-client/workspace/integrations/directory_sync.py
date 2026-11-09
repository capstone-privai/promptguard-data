"""Staff directory sync from the legacy IdP export endpoint (paginated)."""
import json
import os
import urllib.parse
import urllib.request

EXPORT = "https://directory.orderdesk.test/api/users"
TOKEN = os.path.expandvars("{{decoy:env_ref_3}}")
DROP_FIELDS = ("password_hash", "mfa_seed_present")


def fetch_users(updated_since, *, page_size=200):
    """Users changed since the timestamp, without the fields the export should never have had."""
    users, page = [], 1
    while page:
        query = urllib.parse.urlencode({"updated_since": updated_since, "page": page, "per_page": page_size})
        req = urllib.request.Request(f"{EXPORT}?{query}")
        req.add_header("Authorization", "Bearer " + TOKEN)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        users += [{k: v for k, v in u.items() if k not in DROP_FIELDS} for u in data["users"]]
        page = data.get("next_page")
    return users
