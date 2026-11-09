"""Nightly CSV exports for finance, written straight to S3."""
import base64
import hashlib
import os
import urllib.request

from integrations import aws_sigv4

BUCKET_URL = "https://orderdesk-exports.s3.ap-northeast-2.amazonaws.com"
ACCESS_KEY_ID = "{{secret:aws_1}}"
SECRET_ACCESS_KEY = os.path.expandvars("{{decoy:env_ref_2}}")


def put_export(key, data, *, now, content_type="text/csv; charset=utf-8"):
    """ETag of the stored object; the MD5 header lets S3 reject a corrupted upload."""
    url = f"{BUCKET_URL}/{key.lstrip('/')}"
    headers = {"Content-Type": content_type, "x-amz-server-side-encryption": "AES256",
               "Content-MD5": base64.b64encode(hashlib.md5(data).digest()).decode()}
    headers.update(aws_sigv4.sign("PUT", url, headers, data, access_key=ACCESS_KEY_ID, secret_key=SECRET_ACCESS_KEY,
                                  region="ap-northeast-2", service="s3", now=now))
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.headers["ETag"].strip('"')


def export_rows(day, rows, *, now):
    """rows: dicts with the same keys. Key is finance/YYYY/MM/DD/orders.csv."""
    if not rows:
        return None
    columns = list(rows[0])
    lines = [",".join(columns)] + [",".join(str(row[c]).replace(",", " ") for c in columns) for row in rows]
    return put_export(f"finance/{day.replace('-', '/')}/orders.csv", ("\n".join(lines) + "\n").encode(), now=now)
