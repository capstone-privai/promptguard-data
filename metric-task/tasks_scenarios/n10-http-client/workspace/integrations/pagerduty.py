"""PagerDuty incidents for the on-call rotation."""
import json
import urllib.request

API = "https://api.pagerduty.com"
SENDER = "oncall-bot@orderdesk.test"


def _call(method, path, payload, token):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode("utf-8"), method=method)
    req.add_header("Authorization", "Token token=" + token)
    req.add_header("From", SENDER)
    req.add_header("Accept", "application/vnd.pagerduty+json;version=2")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read() or b"{}")


def trigger(summary, *, service_id, urgency="high", dedup_key=None, details=None):
    """Incident id."""
    incident = {"type": "incident", "title": summary[:1024], "urgency": urgency,
                "service": {"id": service_id, "type": "service_reference"}}
    if dedup_key:
        incident["incident_key"] = dedup_key
    if details:
        incident["body"] = {"type": "incident_body", "details": details}
    data = _call("POST", "/incidents", {"incident": incident},
                 token="{{secret:token_0}}")
    return data["incident"]["id"]
