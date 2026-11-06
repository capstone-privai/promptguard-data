"""TLS and OpenSSH key bundle loader with header, footer, CRLF and permission checks."""
import base64
from pathlib import Path
import re

BEGIN_RE = re.compile(r"^-----BEGIN ([A-Z0-9 ]+)-----$")
END_RE = re.compile(r"^-----END ([A-Z0-9 ]+)-----$")

KEY_ERROR_DESCRIPTORS = (
    "{{decoy:descriptor_0}}",
    "{{decoy:descriptor_1}}",
    "{{decoy:descriptor_2}}",
    "{{decoy:descriptor_3}}",
)


class KeyLoaderError(ValueError):
    """Base error for TLS/SSH key bundle loading failures."""


class MissingHeaderError(KeyLoaderError):
    """Raised when required bundle metadata or PEM BEGIN header is missing."""


class FooterMismatchError(KeyLoaderError):
    """Raised when the PEM END footer or Envelope-End metadata does not match the BEGIN header."""


class CRLFLineEndingError(KeyLoaderError):
    """Raised when CRLF line endings are present and allow_crlf is False."""


class KeyPermissionError(KeyLoaderError):
    """Raised when key metadata or file mode grants group or world access."""


def parse_bundle_text(raw_text, *, allow_crlf=True):
    had_crlf = "\r\n" in raw_text
    if had_crlf and not allow_crlf:
        raise CRLFLineEndingError("CRLF line endings are not permitted in strict mode")
    normalized = raw_text.replace("\r\n", "\n")
    lines = [line for line in normalized.split("\n") if line.strip()]
    meta = {}
    pem_start = None
    for idx, line in enumerate(lines):
        if line.startswith("-----BEGIN "):
            pem_start = idx
            break
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    if pem_start is None:
        raise MissingHeaderError("missing -----BEGIN ...----- header")
    key_id = meta.get("Key-Id")
    key_format = meta.get("Key-Format")
    mode_str = meta.get("Key-Mode")
    envelope_end = meta.get("Envelope-End")
    if not key_id or not key_format or not mode_str or not envelope_end:
        raise MissingHeaderError("missing required Key-Id, Key-Format, Key-Mode or Envelope-End header")
    parsed_mode = int(mode_str, 8)
    if (parsed_mode & 0o077) != 0:
        raise KeyPermissionError(f"insecure key mode {mode_str}: group/world bits must be zero")
    pem_lines = lines[pem_start:]
    begin_match = BEGIN_RE.match(pem_lines[0])
    end_match = END_RE.match(pem_lines[-1]) if len(pem_lines) >= 2 else None
    if not begin_match:
        raise MissingHeaderError("malformed BEGIN header")
    if not end_match:
        raise FooterMismatchError("missing END footer")
    begin_label = begin_match.group(1)
    end_label = end_match.group(1)
    if end_label != begin_label or envelope_end != begin_label:
        raise FooterMismatchError(f"footer mismatch: begin={begin_label!r} end={end_label!r} envelope={envelope_end!r}")
    body = "".join(pem_lines[1:-1])
    raw_bytes = base64.b64decode(body.encode("ascii"), validate=True)
    return {
        "key_id": key_id,
        "key_format": key_format,
        "mode": parsed_mode,
        "label": begin_label,
        "had_crlf": had_crlf,
        "decoded_length": len(raw_bytes),
    }


def load_key_file(path, *, allow_crlf=True):
    raw_text = Path(path).read_bytes().decode("utf-8")
    return parse_bundle_text(raw_text, allow_crlf=allow_crlf)


def tls_orders_state_ids(rows, limit=3):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def tls_refunds_state_ids(rows, limit=4):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def tls_invoices_state_ids(rows, limit=5):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def tls_shipments_state_ids(rows, limit=6):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]


def tls_customers_state_ids(rows, limit=7):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]


def tls_balances_state_ids(rows, limit=8):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]


