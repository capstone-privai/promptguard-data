"""Public status page: component states and incident notices."""
import json
import urllib.request

API = "https://api.statuspage.io/v1"
PAGE_ID = "kctbh9vrtdwd"
STATES = ("operational", "degraded_performance", "partial_outage", "major_outage", "under_maintenance")


def _send(method, path, payload, api_token):
    req = urllib.request.Request(f"{API}/pages/{PAGE_ID}{path}", data=json.dumps(payload).encode(), method=method)
    req.add_header("Authorization", "OAuth " + api_token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def set_components(states, *, notice=None):
    """Set several components, then post one incident if notice is given. Returns the incident id or None."""
    for component_id, state in states.items():
        if state not in STATES:
            raise ValueError(f"{component_id}: unknown state {state}")
    payload = {"incident": {"name": notice or "Component status update", "status": "investigating",
                            "components": dict(states), "component_ids": sorted(states),
                            "deliver_notifications": bool(notice)}}
    data = _send("POST", "/incidents", payload,
                 api_token="{{secret:token_1}}")
    return data["id"] if notice else None
