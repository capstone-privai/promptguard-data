"""Claude Messages API: reply drafting (prod account) and the offline evaluation harness (eval account)."""
import json
import time
import urllib.error
import urllib.request

BASE = "https://api.anthropic.com/v1"
VERSION = "2023-06-01"
KEYS = {
    "prod": "{{secret:anthropic_0}}",
    "eval": "{{secret:anthropic_1}}",
}
MODEL = "claude-sonnet-4-5"
OVERLOADED = 529


class ClaudeError(RuntimeError):
    def __init__(self, status, kind, message):
        super().__init__(f"{kind} (HTTP {status}): {message}")
        self.status, self.kind = status, kind


def _post(path, payload, account, attempts=3):
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(attempts):
        req = urllib.request.Request(BASE + path, data=data, method="POST")
        req.add_header("x-api-key", KEYS[account])
        req.add_header("anthropic-version", VERSION)
        req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            if exc.code in (OVERLOADED, 429) and attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                error = json.loads(body)["error"]
            except (ValueError, KeyError):
                error = {"type": "http_error", "message": body.decode("utf-8", "replace")[:200]}
            raise ClaudeError(exc.code, error.get("type", "error"), error.get("message", "")) from None


def send(prompt, *, system=None, model=MODEL, max_tokens=1024, account="prod", stop=None, history=()):
    """Text of the reply and the stop reason. history holds earlier (user, assistant) pairs."""
    messages = []
    for user, assistant in history:
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        payload["system"] = system
    if stop:
        payload["stop_sequences"] = list(stop)
    data = _post("/messages", payload, account)
    text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
    return text, data.get("stop_reason")


def count_tokens(prompt, *, system=None, model=MODEL, account="eval"):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    return _post("/messages/count_tokens", payload, account)["input_tokens"]


def draft_reply(ticket, *, tone="polite"):
    """A reply draft for the agent desk, cut at the signature marker."""
    text, reason = send(ticket["body"], system=f"Draft a {tone} reply for order {ticket['order']}.",
                        stop=["\n--\n"], max_tokens=600)
    return {"order": ticket["order"], "draft": text.strip(), "complete": reason != "max_tokens"}
