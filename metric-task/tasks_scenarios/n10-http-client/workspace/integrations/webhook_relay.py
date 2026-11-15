"""Forward order events to the partner relay, which fans them out to marketplace webhooks."""
import json
import urllib.error
import urllib.request

from auth import signer

RELAY = "https://relay.orderdesk.test"
TOPICS = {"order.created", "order.cancelled", "shipment.updated"}


def forward(event, *, created):
    """Delivery id, or None when the relay no longer routes the topic (HTTP 410)."""
    if event["type"] not in TOPICS:
        raise ValueError(f"unknown topic {event['type']}")
    path = "/hooks/" + event["type"].replace(".", "/")
    body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json", "Digest": signer.digest_header(body),
               "Signature": signer.signature_header("relay", "POST", path, body, created),
               "X-Event-Id": str(event["id"])}
    try:
        with urllib.request.urlopen(urllib.request.Request(RELAY + path, body, headers, method="POST"), timeout=5) as resp:
            return json.loads(resp.read())["delivery_id"]
    except urllib.error.HTTPError as exc:
        if exc.code == 410:
            return None
        raise
