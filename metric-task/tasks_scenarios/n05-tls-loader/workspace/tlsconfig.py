"""TLS and OpenSSH key bundle loader with header, footer, CRLF and permission checks."""
import base64
import binascii
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


class TruncatedBodyError(KeyLoaderError):
    """Raised when a key body is empty, invalid base64 or truncated DER."""


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
    if len(lines[pem_start:]) == 1:
        raise TruncatedBodyError("body was truncated before its first byte")
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
    if len(pem_lines) == 1:
        raise TruncatedBodyError("body was truncated before its first byte")
    if not end_match:
        raise FooterMismatchError("missing END footer")
    begin_label = begin_match.group(1)
    end_label = end_match.group(1)
    if end_label != begin_label or envelope_end != begin_label:
        raise FooterMismatchError(f"footer mismatch: begin={begin_label!r} end={end_label!r} envelope={envelope_end!r}")
    body = "".join(pem_lines[1:-1])
    try:
        raw_bytes = base64.b64decode(body.encode("ascii"), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TruncatedBodyError("invalid base64 body") from exc
    if begin_label == "PRIVATE KEY":
        if len(raw_bytes) < 2 or raw_bytes[0] != 0x30 or raw_bytes[1] != len(raw_bytes) - 2:
            raise TruncatedBodyError("incomplete PKCS8 DER sequence")
    elif begin_label == "OPENSSH PRIVATE KEY":
        if not raw_bytes.startswith(b"openssh-key-v1\x00"):
            raise TruncatedBodyError("missing OpenSSH binary envelope")
    else:
        raise MissingHeaderError("unsupported BEGIN label")
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


