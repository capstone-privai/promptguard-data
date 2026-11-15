"""Settlement batches for the payments partner ledger (signed with the ledger key)."""
import json
import urllib.error
import urllib.request

from auth import signer

BASE = "https://ledger.partner.test"


def post_settlement(batch_id, entries, *, created):
    """Receipt id. A batch that was already accepted (HTTP 409) returns the existing receipt."""
    path = "/v2/settlements"
    body = json.dumps({"batch_id": batch_id, "currency": "KRW",
                       "entries": [{"order": o, "amount": a} for o, a in entries]}, sort_keys=True).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST", headers={
        "Content-Type": "application/json", "Digest": signer.digest_header(body),
        "Signature": signer.signature_header("ledger", "POST", path, body, created)})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())["receipt_id"]
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return json.loads(exc.read())["existing_receipt_id"]
        raise
