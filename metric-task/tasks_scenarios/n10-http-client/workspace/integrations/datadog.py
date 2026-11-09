"""Datadog metrics and events for the two Datadog organisations (us1: storefront, eu1: EU warehouse)."""
import json
import urllib.error
import urllib.request

SITES = {
    "us1": ("https://api.datadoghq.com", "{{secret:datadog_0}}"),
    "eu1": ("https://api.datadoghq.eu", "{{secret:datadog_1}}"),
}
MAX_SERIES = 100
GAUGE, COUNT, RATE = 3, 1, 2


class DatadogError(RuntimeError):
    pass


def _send(site, path, payload):
    base, key = SITES[site]
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("DD-API-KEY", key)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        errors = json.loads(exc.read() or b"{}").get("errors") or [exc.reason]
        raise DatadogError(f"{path} on {site}: HTTP {exc.code}: {'; '.join(map(str, errors))}") from None


def _series(name, points, tags, kind):
    return {"metric": name, "type": kind, "points": [{"timestamp": int(ts), "value": float(v)} for ts, v in points],
            "tags": sorted(tags)}


def submit_metrics(metrics, *, site="us1"):
    """metrics: (name, [(ts, value), ...], tags, kind). Sent in chunks of MAX_SERIES; returns the request count."""
    series = [_series(*m) for m in metrics]
    sent = 0
    for start in range(0, len(series), MAX_SERIES):
        status, _ = _send(site, "/api/v2/series", {"series": series[start:start + MAX_SERIES]})
        if status != 202:
            raise DatadogError(f"series rejected with HTTP {status}")
        sent += 1
    return sent


def gauge(name, value, *, ts, tags=(), site="us1"):
    return submit_metrics([(name, [(ts, value)], list(tags), GAUGE)], site=site)


def send_event(title, text, *, alert_type="info", tags=(), aggregation_key=None, site="us1"):
    """Event id. Text longer than 4000 characters is cut, as the API would reject it."""
    payload = {"title": title[:100], "text": text if len(text) <= 4000 else text[:3990] + " [cut]",
               "alert_type": alert_type, "tags": sorted(tags), "source_type_name": "orderdesk"}
    if aggregation_key:
        payload["aggregation_key"] = aggregation_key
    _, data = _send(site, "/api/v1/events", payload)
    return data["event"]["id"]
