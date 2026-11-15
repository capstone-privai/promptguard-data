"""AWS Signature Version 4 for the two integrations that call AWS directly (SES, S3)."""
from __future__ import annotations
import hashlib
import hmac
import urllib.parse


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def sign(method, url, headers, body, *, access_key, secret_key, region, service, now):
    """Headers to add to the request: X-Amz-Date, X-Amz-Content-Sha256 and Authorization."""
    parts = urllib.parse.urlsplit(url)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    payload_hash = hashlib.sha256(body).hexdigest()
    signed = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    signed.update({"host": parts.netloc, "x-amz-date": stamp, "x-amz-content-sha256": payload_hash})
    names = ";".join(sorted(signed))
    query = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                     for k, v in sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    canonical = "\n".join([method, urllib.parse.quote(parts.path or "/", safe="/-_.~"), query,
                           "".join(f"{k}:{signed[k]}\n" for k in sorted(signed)), names, payload_hash])
    scope = f"{stamp[:8]}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), stamp[:8]), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    added = {"X-Amz-Date": stamp, "X-Amz-Content-Sha256": payload_hash}
    added["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={names}, " \
                             f"Signature={signature}"
    return added
