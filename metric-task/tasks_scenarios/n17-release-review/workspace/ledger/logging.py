"""Logger setup and the access line written for every request."""
import logging

REDACTED_FIELDS = ("authorization", "cookie", "password", "token")


def configure(level):
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("ledger")


def redact(name, value):
    return f"[REDACTED:{name}]" if name in REDACTED_FIELDS else value


def access_line(method, path, status, millis, fields):
    extra = " ".join(f"{name}={redact(name, value)}" for name, value in sorted(fields.items()))
    return f"{method} {path} {status} {millis}ms {extra}".rstrip()
