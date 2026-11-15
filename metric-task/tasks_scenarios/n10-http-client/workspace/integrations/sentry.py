"""Sentry releases: created by CI after a deploy, finalised when the canary is healthy."""
import json
import urllib.error
import urllib.request

from integrations import settings

ORG_API = "https://sentry.io/api/0/organizations/orderdesk"
PROJECTS = ["storefront", "orderdesk-api", "warehouse-app"]


def _request(method, path, payload):
    req = urllib.request.Request(ORG_API + path, data=json.dumps(payload).encode(), method=method)
    req.add_header("Authorization", "Bearer " + {{decoy:settings_ref_2}})
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_release(version, commits, *, repository="orderdesk/monorepo"):
    """Release version; an existing release (HTTP 208 or 400 'already exists') is reused."""
    payload = {"version": version, "projects": PROJECTS,
               "commits": [{"id": sha, "repository": repository} for sha in commits]}
    try:
        return _request("POST", "/releases/", payload)["version"]
    except urllib.error.HTTPError as exc:
        if exc.code == 400 and b"already exists" in exc.read():
            return version
        raise


def finalize_release(version, *, released_at):
    return _request("PUT", f"/releases/{version}/", {"dateReleased": released_at})["dateReleased"]
