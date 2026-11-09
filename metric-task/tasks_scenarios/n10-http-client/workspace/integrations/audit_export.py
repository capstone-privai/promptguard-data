"""Daily audit trail upload to the compliance archive (append-only, signed with the audit key)."""
import json
import urllib.request

from auth import signer

ARCHIVE = "https://audit-archive.partner.test"


def upload_day(day, events, *, created):
    """Stored byte count reported by the archive. One JSON object per line, sorted by event time."""
    path = f"/v1/days/{day}.jsonl"
    lines = [json.dumps(e, sort_keys=True, ensure_ascii=False) for e in sorted(events, key=lambda e: e["at"])]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    req = urllib.request.Request(ARCHIVE + path, data=body, method="PUT")
    req.add_header("Content-Type", "application/x-ndjson")
    req.add_header("Digest", signer.digest_header(body))
    req.add_header("Signature", signer.signature_header("audit", "PUT", path, body, created))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(json.loads(resp.read())["stored_bytes"])
