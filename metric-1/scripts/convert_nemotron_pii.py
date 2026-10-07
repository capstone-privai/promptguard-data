"""Convert nvidia/Nemotron-PII (synthetic business documents with PII span labels) into our session format.

Run from the repository root, after downloading the dataset (see metric-1/README_Nemotron-PII.md):
  python metric-1/scripts/convert_nemotron_pii.py --nemotron ../Nemotron-PII

Third-party benchmark: origin=external, allowed_use=[rule_eval, ml_eval]. Needs pyarrow.

Writes, under --out (default metric-1/):
  data_test/sessions_from_Nemotron-PII.jsonl  one session per document, one item per session
  data_answer/gold_from_Nemotron-PII.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_Nemotron-PII.jsonl              every source span (credential or not) mapped to item offsets,
                                              with our verdict, for analysis (no values)

Only the test split is used, sampled deterministically (sha256 of uid and locale): --positives documents that hold at least
one gold span and --negatives documents that hold none. The channel follows the document's format: structured
documents (configuration files, forms, scripts) -> tool_output, a file the agent read; unstructured ones
(emails, letters, notes, policies) -> prompt, text the user pasted in. --channel overrides it.

Gold, with the criteria of the privesc-llm-data and CredData conversions:
  - password spans -> PASSWORD if at least MIN_VALUE_LEN characters. Shorter ones are common passwords
    ("River45#", "welcome"); like privesc and CredData they are not gold (short_password), and neither are longer
    ones from the common-password list below (common_password).
  - api_key spans -> SECRET if at least MIN_VALUE_LEN characters (short_api_key) and not a public
    documentation example such as the jwt.io sample token (known_example).
  - http_cookie spans -> TOKEN on the cookie value, only for authentication cookies (session, auth, token, jwt,
    api key ...) of at least MIN_VALUE_LEN characters. Name and attributes are not the secret. CSRF, tracking,
    consent and preference cookies are not credentials (non_auth_cookie, short_cookie).
  - Placeholders and partly masked values (********, 732****, YOUR_API_KEY_HERE) are not gold (placeholder).
  - pin and cvv spans are not gold (pin, cvv): short card and account codes, outside metric 1's credentials.
  - Every other occurrence of a gold value in the same document is gold too, as in privesc.
  - The dataset's offsets are authoritative; its span text is sometimes lower-cased (a sentence-initial capital
    in the document). A span whose text differs beyond case is dropped (offset_mismatch).
  - Overlapping gold spans are merged; the type of the longest wins.
"""
from __future__ import annotations

import argparse
import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "Nemotron-PII"
SOURCE = "nemotron-pii"
HF_REPO = "nvidia/Nemotron-PII"
REVISION = "b70ffaf5ff39e079776134c5bf4381f00a9fd1ed"
SPLIT_FILE = "data/test-00000-of-00001.parquet"
MIN_VALUE_LEN = 9
CREDENTIAL_LABELS = {"password", "api_key", "http_cookie", "pin", "cvv"}
# Most common passwords of public breach lists that are MIN_VALUE_LEN or longer (shorter ones fail the length rule
# anyway). privesc and CredData leave common passwords out of gold; the length rule alone keeps these.
COMMON_PASSWORDS = {
    "123456789", "1234567890", "987654321", "123123123", "111111111", "1111111111", "000000000", "123456789a",
    "qwerty123", "qwertyuiop", "asdfghjkl", "zxcvbnm123", "1q2w3e4r5t", "1qaz2wsx3edc", "password1", "password12",
    "password123", "passw0rd1", "iloveyou1", "iloveyou123", "welcome123", "welcome01", "admin1234", "administrator",
    "letmein123", "trustno1!", "sunshine1", "princess1", "football1", "baseball1", "superman1", "starwars1",
    "changeme123", "qwerty1234", "abcd12345", "abc123456",
}

PLACEHOLDER = re.compile(r"\*{3}|x{4}|X{4}|<[^>]*>|\{\{|\$\{|redacted|your[_-]|_here\b|example", re.I)
# The jwt.io sample token, reused by the generator with edited payloads: its signature or its payload marks it.
# (AWS's documented ...EXAMPLE keys need no entry: PLACEHOLDER already catches "example".)
JWT_IO_SIGNATURE = "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
JWT_IO_PAYLOAD = {"sub": "1234567890", "name": "John Doe", "iat": 1516239022}
AUTH_COOKIE = re.compile(r"sess|^sid$|auth|jwt|token|api_?key|access|refresh|remember|login|credential")
NOT_AUTH_COOKIE = re.compile(r"csrf|xsrf|xss|cart|consent|pref|track|utm|^_?ga|feature|order|timezone|lang|font|theme")


def jwt_payload(value: str):
    parts = value.split(".")
    if len(parts) != 3 or not value.startswith("eyJ"):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None


def known_example(value: str) -> bool:
    if value.endswith(JWT_IO_SIGNATURE):
        return True
    payload = jwt_payload(value)
    return isinstance(payload, dict) and all(payload.get(k) == v for k, v in JWT_IO_PAYLOAD.items())


def cookie_value(text: str, start: int, end: int) -> tuple[str | None, int, int]:
    """(cookie name, value start, value end) of the first name=value pair in text[start:end]."""
    m = re.match(r"\s*([^=;\s]+)\s*=\s*\"?([^;\"\s]*)", text[start:end])
    if not m:
        return None, start, start
    return m.group(1).lower().lstrip("_"), start + m.start(2), start + m.end(2)


def judge(label: str, text: str, start: int, end: int) -> tuple[str, str | None, int, int]:
    """(kind, gold type or None, start, end) for one credential-label span."""
    value = text[start:end]
    if label in ("pin", "cvv"):
        return label, None, start, end
    if label == "http_cookie":
        name, start, end = cookie_value(text, start, end)
        if name is None:
            return "cookie_name_only", None, start, end
        if NOT_AUTH_COOKIE.search(name) or not AUTH_COOKIE.search(name):
            return "non_auth_cookie", None, start, end
        value = text[start:end]
        if len(value) < MIN_VALUE_LEN:
            return "short_cookie", None, start, end
        if PLACEHOLDER.search(value):
            return "placeholder", None, start, end
        if known_example(value):
            return "known_example", None, start, end
        return "auth_cookie", "TOKEN", start, end
    if PLACEHOLDER.search(value):
        return "placeholder", None, start, end
    if label == "password":
        if len(value) < MIN_VALUE_LEN:
            return "short_password", None, start, end
        if value.lower() in COMMON_PASSWORDS:
            return "common_password", None, start, end
        return "password", "PASSWORD", start, end
    if label == "api_key":
        if known_example(value):
            return "known_example", None, start, end
        if len(value) < MIN_VALUE_LEN:
            return "short_api_key", None, start, end
        return "api_key", "SECRET", start, end
    raise ValueError(label)


def trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def merge(spans: list[dict], stats: Counter) -> list[dict]:
    spans = sorted(spans, key=lambda s: (s["start"], -s["end"]))
    merged: list[dict] = []
    for s in spans:
        if merged and s["start"] < merged[-1]["end"]:
            m = merged[-1]
            stats["merged_overlapping"] += 1
            longest = max((m, s), key=lambda x: x["end"] - x["start"])
            merged[-1] = {**longest, "start": m["start"], "end": max(m["end"], s["end"])}
        else:
            merged.append(s)
    return merged


def document_spans(text: str, spans: list[dict], stats: Counter) -> tuple[list[dict], list[dict]]:
    """(gold spans, label rows) for one document."""
    gold, labels = [], []
    for s in spans:
        start, end, label = int(s["start"]), int(s["end"]), s["label"]
        if not (0 <= start < end <= len(text)) or text[start:end].lower() != str(s["text"]).lower():
            stats["offset_mismatch"] += 1
            if label in CREDENTIAL_LABELS:
                labels.append({"start": start, "end": end, "source_label": label, "gold": False,
                               "kind": "offset_mismatch"})
            continue
        if label not in CREDENTIAL_LABELS:
            labels.append({"start": start, "end": end, "source_label": label, "gold": False, "kind": "pii_other"})
            continue
        kind, kind_type, a, b = judge(label, text, start, end)
        a, b = trim(text, a, b)
        stats[f"{label}:{kind}"] += 1
        if kind_type and a < b:
            gold.append({"start": a, "end": b, "type": kind_type, "kind": kind})
        labels.append({"start": a if kind_type else start, "end": b if kind_type else end, "source_label": label,
                       "gold": bool(kind_type), "kind": kind, **({"type": kind_type} if kind_type else {})})
    # Every occurrence of a gold value counts, as in the privesc conversion.
    extra = []
    for value, kind_type in {(text[g["start"]:g["end"]], g["type"]) for g in gold}:
        for m in re.finditer(re.escape(value), text):
            if not any(g["start"] <= m.start() and m.end() <= g["end"] for g in gold + extra):
                extra.append({"start": m.start(), "end": m.end(), "type": kind_type, "kind": "repeated_value"})
                stats["gold_repeated_value"] += 1
    labels += [{"start": e["start"], "end": e["end"], "source_label": None, "gold": True, "kind": e["kind"],
                "type": e["type"]} for e in extra]
    return merge(gold + extra, stats), labels


def doc_key(doc: dict) -> str:
    """Each uid appears twice in a split, once per locale (us, intl), with different text."""
    return f"{doc['uid']}-{doc['locale']}"


def sample_key(doc: dict) -> str:
    return hashlib.sha256(doc_key(doc).encode()).hexdigest()


def convert(root: Path, positives: int, negatives: int, channel: str):
    import pyarrow.parquet as pq  # only this converter needs it

    path = root / SPLIT_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; download {HF_REPO} first (README_Nemotron-PII.md)")
    columns = ["uid", "domain", "document_type", "document_format", "locale", "text", "spans"]
    docs = sorted(pq.read_table(path, columns=columns).to_pylist(), key=sample_key)
    stats = Counter()
    picked = {"positive": [], "negative": []}
    for doc in docs:
        spans = ast.literal_eval(doc["spans"])
        gold, labels = document_spans(doc["text"], spans, Counter())
        bucket = "positive" if gold else "negative"
        if len(picked[bucket]) < (positives if gold else negatives):
            picked[bucket].append(doc)
        if len(picked["positive"]) >= positives and len(picked["negative"]) >= negatives:
            break
    chosen = sorted(picked["positive"] + picked["negative"], key=sample_key)

    sessions, gold_rows, label_rows = [], [], []
    for doc in chosen:
        text = doc["text"]
        session_id = f"nemotron-{doc_key(doc)}"
        item_channel = channel if channel != "by-format" else (
            "tool_output" if doc["document_format"] == "structured" else "prompt")
        gold, labels = document_spans(text, ast.literal_eval(doc["spans"]), stats)
        for span_id, g in enumerate(gold):
            gold_rows.append({"session_id": session_id, "item_id": 0, "span_id": span_id,
                              "span": {"start": g["start"], "end": g["end"], "type": g["type"]}})
        for row in sorted(labels, key=lambda r: (r["start"], r["end"])):
            label_rows.append({"session_id": session_id, "item_id": 0, **row})
        stats[f"sessions_{item_channel}"] += 1
        stats["sessions_with_gold"] += bool(gold)
        sessions.append({"session_id": session_id,
                         "items": [{"item_id": 0, "turn_id": "t0", "channel": item_channel, "text": text}],
                         "meta": {
                             "dataset_version": f"{SOURCE}@{REVISION[:12]}", "source": SOURCE,
                             "origin": "external", "allowed_use": ALLOWED_USE["external"],
                             "group_id": f"nemotron-{doc['domain']}",
                             "uid": doc["uid"], "domain": doc["domain"], "document_type": doc["document_type"],
                             "document_format": doc["document_format"], "locale": doc["locale"], "split": "test",
                             "sample": {"positives": positives, "negatives": negatives, "channel": channel},
                             "license": f"CC BY 4.0 ({HF_REPO})",
                         }})
    return sessions, gold_rows, label_rows, stats


def write_outputs(root: Path, positives: int, negatives: int, channel: str, out: Path) -> dict:
    sessions, gold, labels, stats = convert(root, positives, negatives, channel)
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{NAME}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{NAME}.jsonl", gold)
    write_jsonl(out / f"labels_from_{NAME}.jsonl", labels)
    return {"sessions": len(sessions), "gold_spans": len(gold),
            "gold_by_type": dict(Counter(g["span"]["type"] for g in gold)), **dict(sorted(stats.items()))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nemotron", type=Path, default=REPO_ROOT.parent / NAME,
                        help=f"local copy of {HF_REPO} at revision {REVISION[:12]}")
    parser.add_argument("--positives", type=int, default=3000, help="documents with at least one gold span")
    parser.add_argument("--negatives", type=int, default=3000, help="documents without gold spans")
    parser.add_argument("--channel", choices=["by-format", "prompt", "tool_output"], default="by-format")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.nemotron, args.positives, args.negatives, args.channel, args.out), indent=2))


if __name__ == "__main__":
    main()
