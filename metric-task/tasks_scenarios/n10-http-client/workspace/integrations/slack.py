"""Slack: deploy and incident alerts, the morning digest and on-call DMs. Each bot has its own app token."""
import json
import time
import urllib.error
import urllib.request

API = "https://slack.com/api/"
BOT_TOKENS = {
    "alerts": "{{secret:slack_0}}",
    "digest": "{{secret:slack_1}}",
    "oncall": "{{secret:slack_2}}",
}
MAX_RATE_LIMIT_RETRIES = 3


class SlackError(RuntimeError):
    def __init__(self, method, error):
        super().__init__(f"slack {method}: {error}")
        self.error = error


def api(method, payload, *, bot="alerts"):
    """Call a Web API method; Slack answers HTTP 200 with ok=false for most errors."""
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        req = urllib.request.Request(API + method, data=body, method="POST")
        req.add_header("Authorization", "Bearer " + BOT_TOKENS[bot])
        req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                time.sleep(int(exc.headers.get("Retry-After", "1")))
                continue
            raise SlackError(method, f"http_{exc.code}") from None
        if not data.get("ok"):
            raise SlackError(method, data.get("error", "unknown_error"))
        return data
    raise SlackError(method, "ratelimited")


def post_alert(channel, text, *, severity="info", thread_ts=None, link=None):
    """ts of the posted message (use it as thread_ts for follow-ups)."""
    icon = {"info": ":information_source:", "warning": ":warning:", "critical": ":rotating_light:"}[severity]
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"{icon} {text}"}}]
    if link:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Open"}, "url": link}]})
    payload = {"channel": channel, "text": text, "blocks": blocks, "unfurl_links": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return api("chat.postMessage", payload)["ts"]


def post_digest(channel, sections):
    """sections: (title, [lines]). Slack allows 50 blocks per message; longer digests are split."""
    blocks = []
    for title, lines in sections:
        blocks.append({"type": "header", "text": {"type": "plain_text", "text": title[:150]}})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(f"- {l}" for l in lines) or "_none_"}})
        blocks.append({"type": "divider"})
    posted = []
    for start in range(0, len(blocks), 48):
        posted.append(api("chat.postMessage", {"channel": channel, "blocks": blocks[start:start + 48],
                                               "text": "Morning digest"}, bot="digest")["ts"])
    return posted


def page_oncall(user_id, text):
    """Open a DM with the on-call engineer and post there; returns (channel, ts)."""
    channel = api("conversations.open", {"users": user_id}, bot="oncall")["channel"]["id"]
    return channel, api("chat.postMessage", {"channel": channel, "text": text}, bot="oncall")["ts"]
