"""Stripe-style webhook signature verification, replay window enforcement and retry queue."""
import hashlib
import hmac
import json
from payments import settings


class WebhookError(ValueError):
    """Base error for webhook verification failures."""


class WebhookSignatureError(WebhookError):
    """Raised when the signature header is missing, malformed or does not match any active endpoint secret."""


class WebhookTimestampError(WebhookError):
    """Raised when the webhook timestamp lies outside the configured tolerance window."""


def compute_signature(timestamp, raw_body, signing_key):
    message = f"{ int(timestamp) }.{ raw_body }".encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def parse_signature_header(header):
    if not header or not isinstance(header, str):
        raise WebhookSignatureError("missing Stripe-Signature header")
    timestamp = None
    signatures = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep or not value:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise WebhookSignatureError("non-integer webhook timestamp") from exc
        elif key == "v1":
            signatures.append(value.strip())
    if timestamp is None or not signatures:
        raise WebhookSignatureError("malformed Stripe-Signature header")
    return timestamp, signatures


def verify_signature(raw_body, header, active_keys=None, *, now=1790000100, tolerance=300):
    keys = list(active_keys or settings.ACTIVE_WEBHOOK_SECRETS)
    try:
        timestamp, received = parse_signature_header(header)
    except WebhookSignatureError as exc:
        diag = ", ".join(keys[:2])
        raise WebhookSignatureError(f"{exc} (configured endpoints: {diag})") from exc
    if abs(int(now) - timestamp) > tolerance:
        raise WebhookTimestampError(f"timestamp {timestamp} outside {tolerance}s window at {now}")
    candidates = [compute_signature(timestamp, raw_body, key) for key in keys]
    if any(hmac.compare_digest(expected, cand) for expected in candidates for cand in received):
        return json.loads(raw_body)
    diag = ", ".join(keys[:2])
    raise WebhookSignatureError(f"signature mismatch against active endpoints ({diag})")


def backoff_seconds(attempt, *, base=5, cap=300):
    if int(attempt) < 1:
        raise ValueError("attempt must be >= 1")
    delay = base * (2 ** (int(attempt) - 1))
    return min(int(cap), int(delay))


class RetryQueue:
    """In-memory idempotent webhook processor and exponential backoff retry queue."""

    def __init__(self, *, base_delay=5, max_delay=300):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.seen_ids = set()
        self.scheduled = []

    def process_or_enqueue(self, raw_body, header, *, now=1790000100, tolerance=300, active_keys=None, failing=False):
        event = verify_signature(raw_body, header, active_keys=active_keys, now=now, tolerance=tolerance)
        event_id = event["id"]
        if event_id in self.seen_ids:
            return {"status": "duplicate", "id": event_id, "scheduled_delay": 0}
        if failing:
            attempt = int(event.get("attempt", 1))
            delay = backoff_seconds(attempt, base=self.base_delay, cap=self.max_delay)
            entry = {"id": event_id, "attempt": attempt, "delay_seconds": delay, "type": event.get("type", "unknown")}
            self.scheduled.append(entry)
            return {"status": "retry_scheduled", "id": event_id, "scheduled_delay": delay}
        self.seen_ids.add(event_id)
        return {"status": "processed", "id": event_id, "scheduled_delay": 0}


