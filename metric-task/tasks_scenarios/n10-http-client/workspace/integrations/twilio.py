"""SMS through Twilio: order notifications (main), warehouse alerts (ops) and campaigns (marketing)."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.twilio.com/2010-04-01"
AUTH_TOKENS = {
    "{{decoy:twilio_sid_0}}": "{{secret:twilio_0}}",
    "{{decoy:twilio_sid_1}}": "{{secret:twilio_1}}",
    "{{decoy:twilio_sid_2}}": os.path.expandvars("{{decoy:env_ref_0}}"),
}
SENDERS = {"main": "+15005550006", "ops": "+15005550007", "marketing": "+15005550008"}
ACCOUNTS = dict(zip(SENDERS, AUTH_TOKENS))
UNREACHABLE = {21211, 21610, 21614}


class SmsError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"twilio error {code}: {message}")
        self.code = code


def _call(method, account, path, fields=None):
    sid = ACCOUNTS[account]
    pair = base64.b64encode(f"{sid}:{AUTH_TOKENS[sid]}".encode()).decode()
    url = f"{API}/Accounts/{sid}{path}"
    data = urllib.parse.urlencode(fields).encode() if fields else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Basic " + pair)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = json.loads(exc.read() or b"{}")
        raise SmsError(detail.get("code", exc.code), detail.get("message", exc.reason)) from None


def normalise_kr(number):
    digits = "".join(ch for ch in number if ch.isdigit())
    if digits.startswith("010") and len(digits) == 11:
        return "+82" + digits[1:]
    if digits.startswith("82"):
        return "+" + digits
    raise ValueError(f"not a Korean mobile number: {number}")


def send_sms(to, body, *, account="main", status_callback=None):
    """Message SID, or None when Twilio reports the number as unreachable (the customer is not retried)."""
    fields = {"To": normalise_kr(to), "From": SENDERS[account], "Body": body}
    if status_callback:
        fields["StatusCallback"] = status_callback
    try:
        return _call("POST", account, "/Messages.json", fields)["sid"]
    except SmsError as exc:
        if exc.code in UNREACHABLE:
            return None
        raise


def message_status(message_sid, *, account="main"):
    data = _call("GET", account, f"/Messages/{message_sid}.json")
    return data["status"], data.get("error_code")


def recent_failures(*, account="ops", page_size=50):
    """(to, error_code) of failed or undelivered messages on the first page."""
    query = urllib.parse.urlencode({"PageSize": page_size, "Status": "failed"})
    data = _call("GET", account, "/Messages.json?" + query)
    return [(m["to"], m.get("error_code")) for m in data["messages"] if m["status"] in ("failed", "undelivered")]
