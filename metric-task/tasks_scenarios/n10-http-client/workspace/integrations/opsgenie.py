"""Opsgenie alerts for the warehouse floor team (they are not on PagerDuty)."""
import json
import urllib.request

ALERTS = "https://api.opsgenie.com/v2/alerts"
PRIORITIES = ("P1", "P2", "P3", "P4", "P5")


def create_alert(message, *, alias, priority="P3", tags=(), team="warehouse-floor", note=None):
    """Request id; Opsgenie creates the alert asynchronously (HTTP 202)."""
    if priority not in PRIORITIES:
        raise ValueError(priority)
    payload = {"message": message[:130], "alias": alias, "priority": priority, "tags": list(tags),
               "responders": [{"name": team, "type": "team"}]}
    if note:
        payload["note"] = note
    return _post(payload,
                 genie_key="{{secret:token_2}}")["requestId"]


def _post(payload, genie_key):
    req = urllib.request.Request(ALERTS, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "GenieKey " + genie_key)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())
