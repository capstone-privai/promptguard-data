"""Chat completions for the support-reply assistant and the nightly ticket summariser."""
import json
import time
import urllib.error
import urllib.request

API_URL = "https://api.openai.com/v1/chat/completions"
API_KEYS = {
    "default": "{{secret:openai_0}}",
    "batch": "{{secret:openai_1}}",
}
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_ATTEMPTS = 4
RETRY_STATUSES = (429, 500, 503)


class ChatError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"openai chat failed with HTTP {status}: {message}")
        self.status = status


def _messages(system, turns):
    out = [{"role": "system", "content": system}] if system else []
    for i, text in enumerate(turns):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": text})
    return out


def _error_message(raw):
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw.strip()[:200]


def complete(turns, *, system=None, model=DEFAULT_MODEL, temperature=0.2, max_tokens=400, account="default",
             tools=None):
    """(text, tool_calls, usage) for a conversation whose user and assistant turns alternate."""
    payload = {"model": model, "messages": _messages(system, turns), "temperature": temperature,
               "max_tokens": max_tokens}
    if tools:
        payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        req = urllib.request.Request(API_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + API_KEYS[account])
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            if exc.code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                time.sleep(float(exc.headers.get("Retry-After") or 2 ** attempt))
                continue
            raise ChatError(exc.code, _error_message(raw)) from None
    message = data["choices"][0]["message"]
    calls = [(c["function"]["name"], json.loads(c["function"]["arguments"] or "{}"))
             for c in message.get("tool_calls") or []]
    return message.get("content") or "", calls, data.get("usage", {})


def summarise_ticket(ticket_text, *, language="ko"):
    """Three bullet points for the ticket sidebar."""
    text, _, _ = complete([ticket_text], account="batch", max_tokens=200,
                          system=f"Summarise the support ticket in three bullet points, in {language}.")
    return [line.lstrip("-* ").strip() for line in text.splitlines() if line.strip()][:3]


def classify_intent(message, intents):
    """One of intents, or "other"; the model answers through a forced tool call."""
    tool = {"name": "set_intent", "parameters": {"type": "object", "properties": {
        "intent": {"type": "string", "enum": list(intents) + ["other"]}}, "required": ["intent"]}}
    _, calls, _ = complete([message], system="Classify the customer message.", tools=[tool], temperature=0)
    for name, args in calls:
        if name == "set_intent" and args.get("intent") in intents:
            return args["intent"]
    return "other"
