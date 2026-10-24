"""Discord alerts: tell the team when an evaluation fails, the service loop breaks or recovers, or a job runs too long.

The webhook URL is a secret (anyone holding it can post to the channel), so no message or error here contains it.
Alerts may quote an error; credentials in URLs are cut out first. Sending is best effort: the caller logs a
NotifyError and goes on.
"""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

LIMIT = 2000  # Discord's content length limit
CREDENTIALS = re.compile(r"(?<=://)[^/@\s]+@")


class NotifyError(Exception):
    pass


def redact(text: str) -> str:
    """The text without user:password@ in its URLs (an authenticated --repo can show up in git errors)."""
    return CREDENTIALS.sub("", text)


def send(url: str, text: str, *, link: str | None = None, timeout: float = 10) -> None:
    """Post text to a Discord webhook, with link (the dashboard) on its own line."""
    tail = f"\n{link}" if link else ""
    content = redact(text)[:LIMIT - len(tail)] + tail
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode()
    # Discord refuses urllib's default User-Agent
    request = Request(url, data=body, method="POST",
                      headers={"Content-Type": "application/json", "User-Agent": "promptguard-dashboard"})
    try:
        with urlopen(request, timeout=timeout):
            pass
    except Exception as exc:  # noqa: BLE001 - name the failure without the URL
        raise NotifyError(f"{type(exc).__name__}: {exc}".replace(url, "<webhook>")) from None
