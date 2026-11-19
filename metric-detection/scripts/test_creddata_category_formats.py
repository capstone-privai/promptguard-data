"""Run with PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
-s metric-detection/scripts -p test_creddata_category_formats.py -v.

The optional train audit prints aggregates only and never writes artifacts.
Its pass shares are diagnostics, not assertions that obfuscated gold values
are all well-formed. Fidelity checks use the most specific selected atom, so
Azure/NTLM combinations do not distort JWT/Bearer target distributions.
For >=20 train values, length p10/p50/p90 allow max(3 characters, 25%);
per-value mean character fractions allow 8 percentage points. All observed
formats, including small samples, are checked for structure and span extent.
JWK whitespace is excluded because fragment layout belongs to callers.
"""
from __future__ import annotations

import base64
import binascii
import collections
from functools import lru_cache
import io
import itertools
import json
import math
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import creddata_category_formats as formats
from value_gen import Draw

ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = Path("metric-detection/source_splits/creddata-v1/train.txt")
SESSIONS_PATH = Path("runs/creddata-source-fullfile/data_test/sessions_from_CredData.jsonl")
CATEGORIES_PATH = Path("runs/creddata-source-fullfile/gold_category_train.jsonl")


@lru_cache(maxsize=2)
def load_train_values(root: Path = ROOT, selected_only=False):
    """Read only train gold into the audit; never inspect original meta CSVs."""
    required = [root / path for path in (TRAIN_PATH, SESSIONS_PATH, CATEGORIES_PATH)]
    if not all(path.is_file() for path in required):
        raise unittest.SkipTest("ignored CredData train inputs are not present")
    train_ids = {line.strip() for line in required[0].read_text().splitlines() if line.strip()}
    sessions = {}
    with required[1].open() as source:
        for line in source:
            session = json.loads(line)
            if session["session_id"] in train_ids:
                sessions[session["session_id"]] = {item["item_id"]: item["text"] for item in session["items"]}
    rows, jwk_forms, dropped = [], collections.defaultdict(collections.Counter), 0
    with required[2].open() as source:
        for line in source:
            row = json.loads(line)
            if row["session_id"] not in train_ids:
                continue
            if "dropped" in row:
                dropped += 1
                continue
            if not row.get("category"):
                raise ValueError("non-dropped train gold row has no category")
            text = sessions[row["session_id"]][row["item_id"]]
            start, end = row["start"], row["end"]
            if not 0 <= start < end <= len(text):
                raise ValueError("train gold span is outside its source item")
            value, category = text[start:end], row["category"]
            rows.append((category, value))
            if "JWK" in category.split(":"):
                for key, shape in jwk_span_forms(value, text[end:end + 1]).items():
                    jwk_forms[key][shape] += 1
    by_atom = collections.defaultdict(list)
    for category, value in rows:
        atoms = {formats._format_atom(category)} if selected_only else set(category.split(":"))
        for atom in atoms - {None}:
            by_atom[atom].append(value)
    return by_atom, {"train_sessions": len(sessions), "gold_rows": len(rows),
                     "dropped": dropped,
                     "jwk_forms": dict(jwk_forms)}


def jwk_span_forms(value, following=""):
    """Only syntax labels leave the ignored source inputs, never field values."""
    start = ("bare kty" if value.startswith("kty") else
             "double-quoted kty" if value.startswith('"kty') else
             "single-quoted kty" if value.startswith("'kty") else
             "leading private material / merged source")
    end = ("single quote" if value.endswith("'") else "double quote" if value.endswith('"') else
           "closing brace" if value.endswith("}") else "private value character")
    match = re.search(r'''(?<![A-Za-z_])(["']?)kty\1\s*:\s*(["'])''', value)
    quoting = ("quoted field" if match and match[1] else "bare field")
    quoting += ", " + ("double-quoted value" if match and match[2] == '"' else "single-quoted value")
    return {"start": start, "end": end, "quoting": quoting,
            "lines": "multiline" if "\n" in value or "\r" in value else "single line",
            "following": "closing quote" if following in ('"', "'") else "other"}


@lru_cache(maxsize=None)
def seeded_values(atom, count=200):
    generate = formats.FORMATS[atom]
    return [generate(Draw(f"creddata-category-formats:{atom}:{i}")) for i in range(count)]


def quantiles(numbers):
    values = sorted(numbers)
    return tuple(values[max(0, math.ceil(len(values) * p) - 1)] for p in (.1, .5, .9))


def character_composition(values, atom):
    # JWK rendering is explicitly single-line: source whitespace belongs to
    # the integrator. Compare its material/syntax, omitting whitespace in both.
    totals = collections.Counter()
    for value in values:
        if atom == "JWK":
            value = "".join(value.split())
        counts = collections.Counter()
        for char in value:
            name = ("unicode" if not char.isascii() else "lower" if char.islower() else
                    "upper" if char.isupper() else "digit" if char.isdigit() else
                    "whitespace" if char.isspace() else "symbol")
            counts[name] += 1
        for name, count in counts.items():
            totals[name] += count / len(value) / len(values)
    return totals


def basic_summary(values):
    """Decoded structural aggregates only; malformed train spans are counted."""
    pairs, invalid = [], 0
    for value in values:
        try:
            user, password = formats._decode64(value).decode("utf-8").split(":", 1)
            pairs.append((user, password))
        except (ValueError, UnicodeError):
            invalid += 1
    result = {"decodable": len(pairs), "invalid": invalid}
    for index, name in enumerate(("user", "password")):
        parts = [pair[index] for pair in pairs]
        separator = "_" if index == 0 else "-"
        result[name] = {
            "length_p10_p50_p90": quantiles(map(len, parts)),
            "groups": dict(sorted(collections.Counter(len(p.split(separator)) for p in parts).items())),
            "lower_grouped_share": sum(bool(re.fullmatch(r"[a-z]+(?:" + re.escape(separator) + r"[a-z]+)+", p))
                                        for p in parts) / len(parts),
            "composition": character_composition(parts, ""),
        }
    return result


def basic_joint_shapes(values):
    """Count decoded group-length pairs without retaining credential text."""
    pairs = collections.Counter()
    for value in values:
        try:
            user, password = formats._decode64(value).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeError):
            continue
        pairs[tuple(map(len, user.split("_"))), tuple(map(len, password.split("-")))] += 1
    return pairs


def jwt_summary(values):
    headers, payloads, largest, largest_strings = [], [], [], []
    for value in values:
        try:
            header, payload, _ = value.split(".")
            header = json.loads(formats._decode64(header))
            payload = json.loads(formats._decode64(payload))
            if not isinstance(header, dict) or not isinstance(payload, dict) or not payload:
                continue
        except (ValueError, UnicodeError):
            continue
        headers.append(header)
        payloads.append(payload)
        largest.append(max(len(json.dumps(v, separators=(",", ":"))) for v in payload.values())
                       / len(json.dumps(payload, separators=(",", ":"))))
        largest_strings.append(max((len(v) for v in payload.values() if isinstance(v, str)), default=0)
                               / len(json.dumps(payload, separators=(",", ":"))))
    return {"headers": headers, "payloads": payloads,
            "largest_claim_share": sum(largest) / len(largest),
            "largest_string_share": sum(largest_strings) / len(largest_strings)}


def decoded_layers(value):
    """Inspect plain text, compact base64 segments, and nested PEM/base64."""
    pending, seen = [(value.encode("ascii"), 0)], set()
    while pending:
        raw, depth = pending.pop()
        if raw in seen:
            continue
        seen.add(raw)
        yield raw
        if depth >= 4:
            continue
        candidates = re.findall(rb"[A-Za-z0-9_+/-]{8,}={0,2}", raw)
        if b"-----BEGIN " in raw:
            candidates.append(b"".join(line for line in raw.splitlines()
                                       if re.fullmatch(rb"[A-Za-z0-9+/=]+", line)))
        for candidate in candidates:
            try:
                decoded = base64.b64decode(candidate + b"=" * (-len(candidate) % 4),
                                           altchars=b"-_", validate=True)
            except (ValueError, binascii.Error):
                continue
            pending.append((decoded, depth + 1))


def structural_features(atom, values):
    """Rates describing public syntax, including the first/last character."""
    def char_class(c):
        # Boundary extent concerns syntax rather than an arbitrary final
        # random character's case. Base64 padding is part of the material;
        # JWK field/value quotes are supplied by the caller's source spelling.
        if c.isalnum() or c in "_-/+=" or (atom == "JWK" and c in "\"'"):
            return "material"
        return "space" if c.isspace() else "delimiter:" + c
    features = collections.Counter()
    for value in values:
        # The train's BASE64 spans often include source closing quotes. The
        # generator emits canonical bare material; braces are never stripped.
        boundary = value.rstrip("\"'") if atom.startswith("BASE64") else value
        features["first:" + char_class(boundary[0])] += 1
        features["last:" + char_class(boundary[-1])] += 1
        for name, predicate in (
            ("outer opening brace", value.startswith("{")),
            ("outer closing brace", value.endswith("}")),
            ("Basic scheme", value.lower().startswith("basic ")),
        ):
            features[name] += bool(predicate)
        if atom.startswith("AWS"):
            features["ASIA prefix"] += value.startswith("ASIA")
            features["access ID extent"] += bool(re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}", value))
        if atom == "JWK":
            fields = re.findall(r'''["']?([a-z]+)["']?\s*:\s*''', value)
            features["last field qi"] += bool(fields and fields[-1] == "qi")
        if atom == "Twilio Credentials":
            features["digits present"] += any(c.isdigit() for c in value)
        if atom == "UUID":
            features["uppercase UUID"] += any(c.isupper() for c in value)
    return {key: count / len(values) for key, count in features.items()}


def structure_gaps(atom, original, generated):
    observed = structural_features(atom, original)
    synthetic = structural_features(atom, generated)
    gaps = []
    for name in sorted(observed.keys() | synthetic.keys()):
        rate = observed.get(name, 0)
        # Small categories still check structure, with two observations and
        # three binomial standard errors allowed for uncertain source shares.
        tolerance = max(.08, 2 / len(original), 3 * math.sqrt(rate * (1 - rate) / len(original)))
        if abs(synthetic.get(name, 0) - rate) > tolerance:
            gaps.append(name)
    return gaps


def pem_summary(values):
    labels, widths, wrapping = collections.Counter(), collections.Counter(), collections.Counter()
    for value in values:
        match = re.search(r"-----BEGIN ([A-Z0-9 ]+)-----", value)
        labels[match[1] if match else "unknown"] += 1
        value = formats._unescape_lines(value)
        # Report physical base64 line widths separately from indentation and
        # comment/quote wrappers; short last lines do not define wrap width.
        lines = []
        for line in value.splitlines()[1:-1]:
            line = re.sub(r"^[ \t]*(?:\*|#|/{2,3})[ \t]+", "", line).strip()
            line = re.sub(r'''["']\s*\+?\s*$''', "", line).lstrip("\"'")
            if re.fullmatch(r"[A-Za-z0-9+/=]+", line):
                lines.append(line)
        width = max(map(len, lines), default=0)
        widths[str(width) if width in (64, 76, 70, 72, 68) else "short/other"] += 1
        full_width = max(map(len, lines[:-1]), default=0)
        wrapping[str(full_width) if full_width in (64, 76, 70, 72, 68) else "single line/other"] += 1
    return {"labels": dict(sorted(labels.items())), "length_p10_p50_p90": quantiles(map(len, values)),
            "line_widths": dict(sorted(widths.items())), "wrap_widths_excluding_last_line": dict(sorted(wrapping.items()))}


def der_fields(data):
    """Independent, strict TLV reader for generated structural-key tests."""
    fields, offset = [], 0
    while offset < len(data):
        tag, size = data[offset:offset + 2]
        offset += 2
        if size & 128:
            count = size & 127
            if not 1 <= count <= 4:
                raise ValueError("invalid DER length")
            size = int.from_bytes(data[offset:offset + count], "big")
            offset += count
        if offset + size > len(data):
            raise ValueError("truncated DER field")
        fields.append((tag, data[offset:offset + size]))
        offset += size
    return fields


def audit_table(by_atom):
    """Return a Markdown table containing counts/lengths, never source values."""
    lines = ["| Format category | Train count | Passing conforms | Generator | Train / generated length p10/p50/p90 (2,000 draws) |",
             "| --- | ---: | ---: | --- | --- |"]
    for atom in sorted(formats.FORMATS):
        original = by_atom.get(atom, [])
        generated = seeded_values(atom, 2000)
        passed = sum(formats.conforms(atom, value) for value in original)
        share = f"{passed}/{len(original)} ({passed / len(original):.1%})" if original else "n/a"
        observed = "/".join(map(str, quantiles(map(len, original)))) if original else "n/a"
        lengths = f"{observed} / " + "/".join(map(str, quantiles(map(len, generated))))
        lines.append(f"| {atom} | {len(original)} | {share} | {formats.GENERATOR_NAMES[atom]} | {lengths} |")
    return "\n".join(lines)


class FormatGeneratorsTest(unittest.TestCase):
    def test_200_draws_per_format_and_determinism(self):
        for atom, generate in formats.FORMATS.items():
            with self.subTest(atom=atom):
                first = seeded_values(atom)
                second = [generate(Draw(f"creddata-category-formats:{atom}:{i}")) for i in range(200)]
                self.assertEqual(first, second, "equal Draw seeds must produce equal values")
                for i, value in enumerate(first):
                    with self.subTest(atom=atom, draw=i):
                        # Never include a value in failure messages.
                        self.assertTrue(formats.conforms(atom, value), f"format failed at draw {i}")
                self.assertGreater(len(set(first)), 1, "generator must consume Draw")

    def test_every_format_in_combined_categories(self):
        for atom, generate in formats.FORMATS.items():
            for category in (f"Auth:{atom}:Token", f"Secret:Key:{atom}", f"{atom}:API:Password"):
                with self.subTest(category=category):
                    self.assertIs(formats.generator_for(category), generate)
                    self.assertTrue(formats.conforms(category, generate(Draw("combined-format"))))

    def test_specificity_is_independent_of_atom_order(self):
        cases = [
            (("NTLM Token", "Bearer Authorization", "Auth"), "NTLM Token"),
            (("Azure Access Token", "JSON Web Token", "Bearer Authorization", "Auth"), "Azure Access Token"),
            (("Slack Token", "Bearer Authorization", "Auth"), "Slack Token"),
            (("JSON Web Token", "Bearer Authorization", "Auth"), "JSON Web Token"),
            (("Grafana Provisioned API Key", "Bearer Authorization", "Key"), "Grafana Provisioned API Key"),
            (("Grafana Service Account Token", "Bearer Authorization", "Key"), "Grafana Service Account Token"),
            (("AWS Client ID", "AWS Multi", "Key"), "AWS Client ID"),
            (("UUID", "Password", "Secret"), "UUID"),
        ]
        for atoms, expected in cases:
            for order in itertools.permutations(atoms):
                category = ":".join(order)
                with self.subTest(category=category):
                    self.assertIs(formats.generator_for(category), formats.FORMATS[expected])
                    value = formats.generator_for(category)(Draw("specificity"))
                    self.assertTrue(formats.conforms(category, value))

    def test_free_form_and_unknown_categories(self):
        self.assertFalse(set(formats.FORMATS) & formats.FREE_FORM_ATOMS)
        for category in sorted(formats.FREE_FORM_ATOMS) + ["", "Unknown Category", "Key:Secret:Token", "API:Auth:Key"]:
            with self.subTest(category=category):
                self.assertIsNone(formats.generator_for(category))
                self.assertFalse(formats.conforms(category, "synthetic-value"))

    def test_rejects_structurally_wrong_values(self):
        for atom in formats.FORMATS:
            for value in ("", "not a credential", "\x00"):
                with self.subTest(atom=atom):
                    self.assertFalse(formats.conforms(atom, value))
        self.assertFalse(formats.conforms("Basic Authorization", base64.b64encode(b"no-colon").decode()))
        self.assertFalse(formats.conforms("JSON Web Token", "e30.e30.c2ln"))
        self.assertFalse(formats.conforms("JWK", '{"kty":"oct","use":"sig"}'))
        self.assertFalse(formats.conforms("JWK", 'kty: "oct"; arbitrary(code); k: "' + "A" * 32))
        self.assertFalse(formats.conforms("PEM Private Key", "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END RSA PRIVATE KEY-----"))

    def test_bearer_uses_profiles_and_specific_formats_still_win(self):
        self.assertIn("Bearer Authorization", formats.FREE_FORM_ATOMS)
        self.assertNotIn("Bearer Authorization", formats.FORMATS)
        self.assertIsNone(formats.generator_for("Auth:Bearer Authorization:Token"))

    def test_aws_multi_train_proportion_and_secret_shape(self):
        values = seeded_values("AWS Multi", 2000)
        access_ids = sum(bool(re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}", v)) for v in values)
        self.assertAlmostEqual(access_ids / len(values), 16 / 18, delta=.025)
        for value in values:
            self.assertTrue(re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}|[A-Za-z0-9+/]{40}", value) is not None)
        for atom, expected in (("AWS Client ID", 2 / 73), ("AWS Multi", 2 / 18)):
            values = seeded_values(atom, 2000)
            self.assertAlmostEqual(sum(v.startswith("ASIA") for v in values) / len(values), expected, delta=.02)

    def test_basic_decoded_structure_and_surface_case(self):
        values = seeded_values("Basic Authorization", 2000)
        summary = basic_summary(values)
        self.assertEqual(summary["invalid"], 0)
        self.assertAlmostEqual(summary["password"]["lower_grouped_share"], 445 / 676, delta=.06)
        for name, target in (("user", (3, 9, 16)), ("password", (8, 20, 20))):
            for observed, expected in zip(summary[name]["length_p10_p50_p90"], target):
                self.assertAlmostEqual(observed, expected, delta=3)
        self.assertAlmostEqual(character_composition(values, "")["upper"], .318, delta=.04)

    def test_basic_joint_group_shapes_keep_group_order(self):
        shapes = basic_joint_shapes(seeded_values("Basic Authorization", 2000))
        self.assertEqual(sum(shapes.values()), 2000)
        self.assertAlmostEqual(shapes[((1, 4, 4, 4), (1, 4, 4, 8))] / 2000, 218 / 676, delta=.03)
        self.assertAlmostEqual(shapes[((3,), (6, 8))] / 2000, 52 / 676, delta=.02)
        self.assertFalse(any(user == (4, 4, 4, 1) or password in ((4, 4, 8, 1), (8, 6))
                             for user, password in shapes))

    def test_jwt_payload_is_not_uniformly_oversized(self):
        values = seeded_values("JSON Web Token", 2000)
        p10, p50, p90 = quantiles(map(len, values))
        self.assertTrue(85 <= p10 <= 130)
        self.assertTrue(190 <= p50 <= 275)
        self.assertTrue(550 <= p90 <= 800)
        self.assertLess(max(len(formats._decode64(v.split(".")[1])) for v in values), 900)

    def test_jwt_has_varied_public_claims_order_and_count(self):
        values = seeded_values("JSON Web Token", 2000)
        payloads = [json.loads(formats._decode64(v.split(".")[1])) for v in values]
        self.assertGreaterEqual(len({v.split(".")[1][:8] for v in values}), 30)
        self.assertLess(sum(v.split(".")[1].startswith("eyJzdWIi") for v in values) / len(values), .18)
        self.assertGreaterEqual(len({tuple(p) for p in payloads}), 100)
        self.assertEqual(quantiles(map(len, payloads))[1], 4)
        self.assertGreaterEqual(quantiles(map(len, payloads))[2], 7)
        for payload in payloads:
            self.assertTrue(set(payload) <= set(formats._JWT_CLAIMS))
            for name in set(payload) & formats._JWT_DATES:
                self.assertIs(type(payload[name]), int)

    def test_jwt_header_variation_and_distributed_claim_lengths(self):
        summary = jwt_summary(seeded_values("JSON Web Token", 2000))
        headers = summary["headers"]
        self.assertGreaterEqual(len({h["alg"] for h in headers}), 10)
        self.assertGreaterEqual(len({h.get("typ") for h in headers}), 3)
        self.assertAlmostEqual(sum("typ" in h for h in headers) / len(headers), 121 / 129, delta=.025)
        self.assertAlmostEqual(sum(next(iter(h)) == "typ" for h in headers) / len(headers),
                               40 / 129, delta=.035)
        self.assertFalse(any("kid" in h for h in headers))
        self.assertLess(summary["largest_claim_share"], .30)
        self.assertLess(summary["largest_string_share"], .25)
        for seed in range(100):
            payload = formats._jwt_payload(Draw(f"jwt-claim-lengths:{seed}"), 600)
            lengths = sorted((len(v) for v in payload.values() if isinstance(v, str)), reverse=True)
            self.assertGreaterEqual(len(lengths), 3)
            self.assertGreater(lengths[2], 20)
            self.assertLess(lengths[0] / 600, .30)

    def test_azure_payload_and_headers_have_public_variation(self):
        values = seeded_values("Azure Access Token", 2000)
        summary = jwt_summary(values)
        payloads, headers = summary["payloads"], summary["headers"]
        self.assertGreater(sum(14 <= len(p) <= 20 for p in payloads) / len(payloads), .70)
        self.assertAlmostEqual(sum(next(iter(p)) == "jti" for p in payloads) / len(payloads),
                               16 / 24, delta=.04)
        self.assertLess(summary["largest_claim_share"], .20)
        self.assertGreater(len({v.split(".")[0][:32] for v in values}), 500)
        self.assertGreaterEqual(len({h["alg"] for h in headers}), 8)
        self.assertAlmostEqual(sum("typ" in h for h in headers) / len(headers), 18 / 24, delta=.04)
        self.assertAlmostEqual(sum("kid" in h for h in headers) / len(headers), 18 / 24, delta=.04)
        for header in headers:
            self.assertTrue(set(header) <= {"alg", "typ", "x5t", "kid"})
            self.assertTrue("kid" in header or "x5t" in header)
        for payload in payloads:
            self.assertTrue(set(payload) <= set(formats._AZURE_CLAIMS))
            for name in set(payload) & formats._JWT_DATES:
                self.assertIs(type(payload[name]), int)
            if "ver" in payload:
                self.assertIn(payload["ver"], ("1.0", "2.0"))
            if "appidacr" in payload:
                self.assertIn(payload["appidacr"], ("0", "1", "2"))
        self.assertEqual(set().union(*payloads), set(formats._AZURE_CLAIMS))

    def test_every_format_omits_generation_marker_including_decoded_base64(self):
        # A whole-format sweep reaches both rare PGP and RSA OpenSSH branches;
        # nested decoding also covers base64-wrapped PEM and compact JWT/JWK.
        labels = collections.Counter()
        versions, comments = set(), set()
        for atom in formats.FORMATS:
            for index, value in enumerate(seeded_values(atom, 2000)):
                for raw in decoded_layers(value):
                    self.assertTrue(b"synthetic" not in raw.lower(), f"{atom}, draw {index}: marker present")
                    if raw.startswith(b"openssh-key-v1\x00"):
                        comments.update(re.findall(rb"(?:deploy|ci|dev|backup)@[a-z0-9-]+", raw))
                if atom == "PEM Private Key":
                    labels[value.splitlines()[0]] += 1
                    if "\nVersion: " in value:
                        versions.add(value.split("\nVersion: ", 1)[1].splitlines()[0])
        self.assertGreater(labels["-----BEGIN PGP PRIVATE KEY BLOCK-----"], 0)
        self.assertGreater(labels["-----BEGIN OPENSSH PRIVATE KEY-----"], 0)
        self.assertGreater(len(versions), 1)
        self.assertGreater(len(comments), 1)
        # Demonstrate detection through nested armor and mixed-case content.
        marker = base64.b64encode(b"SyNtHeTiC").decode("ascii")
        wrapped = base64.b64encode(f"-----BEGIN PRIVATE KEY-----\n{marker}\n-----END PRIVATE KEY-----".encode()).decode()
        self.assertTrue(any(b"synthetic" in raw.lower() for raw in decoded_layers(wrapped)))

    def test_small_format_lengths_case_and_digits(self):
        for atom, expected in (("BASE64 encoded PEM Private Key", (324, 2236, 2273)),
                               ("BASE64 Private Key", (461, 849, 2125)),
                               ("Slack Token", (30, 56, 97))):
            for observed, target in zip(quantiles(map(len, seeded_values(atom, 2000))), expected):
                with self.subTest(atom=atom, target=target):
                    self.assertAlmostEqual(observed, target, delta=max(3, .25 * target))
        self.assertTrue(all(re.fullmatch(r"SK[a-f]{32}", v) for v in seeded_values("Twilio Credentials")))
        uuids = seeded_values("UUID", 2000)
        self.assertAlmostEqual(sum(v.isupper() for v in uuids) / len(uuids), 12 / 110, delta=.025)

    def test_pem_is_canonical_and_encoded_formats_decode(self):
        for i in range(200):
            pem = formats.FORMATS["PEM Private Key"](Draw(f"pem-canonical:{i}"))
            self.assertTrue(pem.startswith("-----BEGIN "))
            self.assertTrue(all(line == line.strip() for line in pem.splitlines()))
            self.assertNotIn("\\n", pem)
            self.assertFalse(pem.endswith("\n"))
            encoded = formats.FORMATS["BASE64 encoded PEM Private Key"](Draw(f"pem-encoded:{i}"))
            decoded = base64.b64decode(encoded, validate=True).decode("ascii")
            self.assertTrue(formats.conforms("PEM Private Key", decoded))
        # Auth VALUE omits its scheme, including after format selection.
        basic = formats.FORMATS["Basic Authorization"](Draw("basic-scheme"))
        self.assertFalse(basic.lower().startswith("basic "))
        self.assertIn(b":", base64.b64decode(basic, validate=True))

    def test_nkey_generation_has_packed_prefix_and_checksum(self):
        for i in range(200):
            value = formats.FORMATS["NKEY Seed"](Draw(f"nkey-checksum:{i}"))
            raw = base64.b32decode(value + "=" * (-len(value) % 8))
            self.assertEqual(len(raw), 36)
            self.assertEqual(raw[0] & 248, 144)
            self.assertEqual(int.from_bytes(raw[-2:], "little"), binascii.crc_hqx(raw[:-2], 0))

    def test_jwk_canonical_and_clean_source_fragments(self):
        material = formats.FORMATS["JWK"](Draw("jwk-fragment"))
        obj = formats._jwk_object(material)
        self.assertIn(obj["kty"], ("oct", "RSA", "EC"))
        key = formats.FORMATS["OTP / 2FA Secret"](Draw("jwk-private-material")) * 2
        self.assertTrue(formats.conforms("JWK", f'"kty": "oct", "k": "{key}'))
        self.assertTrue(formats.conforms("JWK", f"kty: 'oct', k: '{key}"))
        self.assertTrue(formats.conforms("JWK", f"kty: 'oct', ext: false, k: '{key}"))

    def test_jwk_fragment_extent_and_material_helper(self):
        for value in seeded_values("JWK"):
            self.assertTrue(value.startswith("kty: '"))
            self.assertFalse(any(c in value for c in "{}\r\n"))
            self.assertTrue(value[-1] in formats.vg.B64URL)
            # A caller can supply exactly the omitted closing quote and braces.
            self.assertIsInstance(formats._literal_object("{" + re.sub(
                r"(^|, )([a-z]+):", r'\1"\2":', value) + "'}"), dict)
            obj = formats._jwk_object(value)
            self.assertIn(next(reversed(obj)), ("d", "k"))
        for kty, expected in (("oct", {"k"}), ("RSA", {"d", "p", "q", "dp", "dq", "qi"}),
                              ("EC", {"d"}), ("OKP", {"d"})):
            for i in range(20):
                key = f"jwk-material:{kty}:{i}"
                fields = formats.jwk_private_fields(Draw(key), kty)
                self.assertEqual(set(fields), expected)
                self.assertEqual(fields, formats.jwk_private_fields(Draw(key), kty))
                self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_-]{22,}", v) for v in fields.values()))
                self.assertTrue(all(formats._decode64(v) for v in fields.values()))
        with self.assertRaises(ValueError):
            formats.jwk_private_fields(Draw("unsupported-key-type"), "unknown")

    def test_jwk_public_private_helpers_preserve_curve_and_modulus_sizes(self):
        for curve, size in (("P-256", 32), ("P-384", 48), ("P-521", 66),
                            ("Ed25519", 32), ("X25519", 32), ("Ed448", 57), ("X448", 56)):
            kty = "EC" if curve.startswith("P-") else "OKP"
            private = formats.jwk_private_fields(Draw("private:" + curve), kty, curve=curve)
            public = formats.jwk_public_fields(Draw("public:" + curve), kty, curve=curve)
            self.assertEqual(public, formats.jwk_public_fields(Draw("public:" + curve), kty, curve=curve))
            self.assertEqual(set(public), {"x", "y", "kid"} if kty == "EC" else {"x", "kid"})
            for name, value in {**private, **public}.items():
                if name != "kid":
                    self.assertEqual(len(formats._decode64(value)), size)
            complete = {"kty": kty, "crv": curve, **public, **private}
            self.assertTrue(formats.conforms("JWK", json.dumps(complete)))
        for bits in (1024, 2048, 3072, 4096):
            private = formats.jwk_private_fields(Draw(f"private:{bits}"), "RSA", modulus_bits=bits)
            public = formats.jwk_public_fields(Draw(f"public:{bits}"), "RSA", modulus_bits=bits)
            self.assertEqual(set(public), {"n", "e", "kid"})
            self.assertEqual(int.from_bytes(formats._decode64(public["e"]), "big"), 65537)
            self.assertEqual(int.from_bytes(formats._decode64(public["n"]), "big").bit_length(), bits)
            for name, value in private.items():
                self.assertEqual(len(formats._decode64(value)), bits // (8 if name == "d" else 16))
        self.assertEqual(set(formats.jwk_public_fields(Draw("oct-public"), "oct")), {"kid"})
        for helper in (formats.jwk_public_fields, formats.jwk_private_fields):
            for kty, parameters in (("unknown", {}), ("EC", {"curve": "P-999"}),
                                    ("EC", {"modulus_bits": 2048}), ("RSA", {"curve": "P-256"}),
                                    ("RSA", {"modulus_bits": 513})):
                with self.assertRaises(ValueError):
                    helper(Draw("invalid-jwk-size"), kty, **parameters)

    def test_pem_structures_sizes_labels_and_wrapping(self):
        values = seeded_values("PEM Private Key", 2000)
        summary = pem_summary(values)
        counts = summary["labels"]
        expected = {"PRIVATE KEY": 853, "RSA PRIVATE KEY": 129, "EC PRIVATE KEY": 25,
                    "DSA PRIVATE KEY": 15, "OPENSSH PRIVATE KEY": 13,
                    "ENCRYPTED PRIVATE KEY": 11, "PGP PRIVATE KEY BLOCK": 4}
        self.assertEqual(set(counts), set(expected))
        for label, count in expected.items():
            self.assertAlmostEqual(counts[label] / len(values), count / 1050, delta=.025)
        widths, ec8, legacy, ssh, pgp = collections.Counter(), 0, 0, 0, 0
        for value in values:
            lines = value.splitlines()
            label = re.search(r"BEGIN ([A-Z0-9 ]+)-----", lines[0])[1]
            body = [line for line in lines[1:-1] if re.fullmatch(r"[A-Za-z0-9+/=]+", line)]
            if len(body) > 1:
                width = len(body[0])
                self.assertIn(width, (64, 70, 76))
                if label == "OPENSSH PRIVATE KEY":
                    self.assertEqual(width, 70)
                elif width == 76:
                    self.assertIn(label, ("PRIVATE KEY", "RSA PRIVATE KEY"))
                else:
                    self.assertEqual(width, 64)
                self.assertTrue(all(len(line) == width for line in body[:-1]))
                self.assertLessEqual(len(body[-1]), width)
                widths[width] += 1
            raw = base64.b64decode("".join(body), validate=True)
            if "Proc-Type:" in value:
                legacy += 1
                self.assertIn(label, ("RSA PRIVATE KEY", "EC PRIVATE KEY", "DSA PRIVATE KEY"))
                self.assertIn("Proc-Type: 4,ENCRYPTED\nDEK-Info:", value)
                cipher, iv = re.search(r"DEK-Info: ([A-Z0-9-]+),([0-9A-F]+)\n\n", value).groups()
                block = 8 if cipher == "DES-EDE3-CBC" else 16
                self.assertEqual(len(iv), block * 2)
                self.assertEqual(len(raw) % block, 0)
                continue
            if label in ("OPENSSH PRIVATE KEY", "PGP PRIVATE KEY BLOCK"):
                if label.startswith("OPENSSH"):
                    ssh += 1
                else:
                    pgp += 1
                    self.assertIn("\nVersion: ", value)
                    self.assertIn("\n\n", value)
                self.assertTrue(raw.startswith(b"openssh-key-v1\x00") if label.startswith("OPENSSH") else raw.startswith(b"\xc5\xff"))
                continue
            outer = der_fields(raw)
            self.assertEqual([tag for tag, _ in outer], [0x30])
            fields = der_fields(outer[0][1])
            if label == "PRIVATE KEY":
                self.assertEqual([tag for tag, _ in fields], [2, 0x30, 4])
                if bytes.fromhex("06072a8648ce3d0201") in fields[1][1]:
                    ec8 += 1
                    inner = der_fields(der_fields(fields[2][1])[0][1])
                    self.assertEqual([tag for tag, _ in inner[:2]], [2, 4])
                    self.assertIn(len(inner[1][1]), {size for (_, size), _ in formats._EC_CURVES})
                elif fields[1][1] == formats._RSA_ALGORITHM[2:]:
                    integers = der_fields(der_fields(fields[2][1])[0][1])
                    self.assertEqual([tag for tag, _ in integers], [2] * 9)
            elif label == "RSA PRIVATE KEY":
                self.assertEqual([tag for tag, _ in fields], [2] * 9)
                self.assertIn(len(fields[1][1]), (65, 129, 257, 513))
            elif label == "EC PRIVATE KEY":
                self.assertEqual([tag for tag, _ in fields[:3]], [2, 4, 0xa0])
            elif label == "DSA PRIVATE KEY":
                self.assertEqual([tag for tag, _ in fields], [2] * 6)
            elif label == "ENCRYPTED PRIVATE KEY":
                self.assertEqual([tag for tag, _ in fields], [0x30, 4])
                self.assertEqual(len(fields[1][1]) % 8, 0)
        self.assertAlmostEqual(ec8 / len(values), 749 / 1050, delta=.025)
        self.assertAlmostEqual(widths[76] / sum(widths.values()), 132 / 1050, delta=.025)
        self.assertGreater(ssh, 0)
        self.assertGreater(pgp, 0)
        self.assertGreater(legacy, 0)
        self.assertAlmostEqual(legacy / len(values), 12 / 1050, delta=.008)
        p10, p50, p90 = quantiles(map(len, values))
        self.assertTrue(110 <= p10 <= 165)
        self.assertTrue(190 <= p50 <= 290)
        self.assertTrue(1400 <= p90 <= 1950)

    def test_rule_variants_and_comment_wrapped_pem(self):
        # The CredSweeper name covers OAuth/app prefixes as well as ghp_.
        github = formats.FORMATS["Github Classic Token"](Draw("github-rule-variants"))
        for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"):
            self.assertTrue(formats.conforms("Github Classic Token", prefix + github[4:]))
        pem = formats.FORMATS["PEM Private Key"](Draw("pem-comment"))
        lines = pem.splitlines()
        commented = lines[0] + "\n" + "\n".join(" * " + line for line in lines[1:])
        self.assertTrue(formats.conforms("PEM Private Key", commented))

    def test_audit_reads_categorized_train_gold_without_inference(self):
        root = Path("artificial-format-audit")
        sessions = [{"session_id": session, "items": [{"item_id": 0, "text": "synthetic"} ]}
                    for session in ("train", "validation", "test")]
        def row(session, category, **extra):
            return dict(session_id=session, item_id=0, start=0, end=9, category=category, **extra)
        rows = [row("train", "Key:UUID"), row("train", "Password", dropped=True),
                row("train", "Password", dropped=False), row("validation", "Secret"),
                row("test", "Token")]
        files = {str(root / SESSIONS_PATH): sessions, str(root / CATEGORIES_PATH): rows}
        def opened(path):
            return io.StringIO("".join(json.dumps(r) + "\n" for r in files[str(path)]))
        with patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "read_text", return_value="train\n"), \
                patch.object(Path, "open", opened):
            data, stats = load_train_values(root, selected_only=True)
            self.assertEqual(dict(data), {"UUID": ["synthetic"]})
            self.assertEqual((stats["gold_rows"], stats["dropped"]), (1, 2))
            rows[0]["category"] = None
            load_train_values.cache_clear()
            with self.assertRaisesRegex(ValueError, "no category"):
                load_train_values(root, selected_only=True)
        load_train_values.cache_clear()


class OptionalTrainAuditTest(unittest.TestCase):
    def test_every_observed_format_structure_and_extent_including_small_samples(self):
        by_atom, _ = load_train_values(selected_only=True)
        checked = small = 0
        for atom, original in sorted(by_atom.items()):
            generated = seeded_values(atom, 2000)
            checked += 1
            small += len(original) < 20
            with self.subTest(atom=atom):
                self.assertEqual(structure_gaps(atom, original, generated), [],
                                 f"{atom} syntax or first/last character rates differ")
                self.assertTrue(all(formats.conforms(atom, v) for v in generated))
        self.assertGreater(checked, 0)
        self.assertGreater(small, 0)

    def test_every_supported_train_format_length_and_composition(self):
        by_atom, _ = load_train_values(selected_only=True)
        checked = 0
        for atom, generate in formats.FORMATS.items():
            original = by_atom.get(atom, [])
            if len(original) < 20:
                continue
            checked += 1
            generated = seeded_values(atom, 2000)
            for percentile, observed, synthetic in zip((10, 50, 90), quantiles(map(len, original)), quantiles(map(len, generated))):
                with self.subTest(atom=atom, percentile=percentile):
                    self.assertAlmostEqual(synthetic, observed, delta=max(3, .25 * observed),
                                           msg=f"{atom} p{percentile}: train={observed}, generated={synthetic}")
            observed = character_composition(original, atom)
            synthetic = character_composition(generated, atom)
            for name in ("lower", "upper", "digit", "symbol", "whitespace", "unicode"):
                with self.subTest(atom=atom, character_class=name):
                    self.assertAlmostEqual(synthetic[name], observed[name],
                                           delta=.08,
                                           msg=f"{atom} {name} composition differs")
        self.assertGreater(checked, 0)

    def test_regression_audit_detects_original_extent_prefix_and_basic_case_defects(self):
        by_atom, _ = load_train_values(selected_only=True)
        jwk = ["{" + v + "'}" for v in seeded_values("JWK", 2000)]
        self.assertIn("outer opening brace", structure_gaps("JWK", by_atom["JWK"], jwk))
        self.assertIn("outer closing brace", structure_gaps("JWK", by_atom["JWK"], jwk))
        secrets = [formats.vg.SECRET_KINDS["aws_secret_access_key"][1](Draw(f"old-aws-multi:{i}"))
                   for i in range(2000)]
        self.assertIn("access ID extent", structure_gaps("AWS Multi", by_atom["AWS Multi"], secrets))
        old_ids = [formats.vg.SECRET_KINDS["aws_access_key_id"][1](Draw(f"old-aws-id:{i}"))
                   for i in range(2000)]
        self.assertIn("ASIA prefix", structure_gaps("AWS Client ID", by_atom["AWS Client ID"], old_ids))
        mixed = []
        for i in range(2000):
            d = Draw(f"old-basic:{i}")
            raw = d.chars(d.between(1, 12), formats.vg.ALNUM) + ":"
            raw += d.chars(d.between(3, 40), formats.vg.ALNUM + "!@#$%&*+-_.:")
            mixed.append(base64.b64encode(raw.encode("ascii")).decode("ascii"))
        original = character_composition(by_atom["Basic Authorization"], "")
        synthetic = character_composition(mixed, "")
        self.assertGreater(abs(original["upper"] - synthetic["upper"]), .08)

    def test_basic_train_decoded_aggregates(self):
        by_atom, _ = load_train_values(selected_only=True)
        observed = basic_summary(by_atom["Basic Authorization"])
        generated = basic_summary(seeded_values("Basic Authorization", 2000))
        for name in ("user", "password"):
            self.assertAlmostEqual(generated[name]["lower_grouped_share"],
                                   observed[name]["lower_grouped_share"], delta=.06)
            for actual, target in zip(generated[name]["length_p10_p50_p90"],
                                      observed[name]["length_p10_p50_p90"]):
                self.assertAlmostEqual(actual, target, delta=max(3, .2 * target))

    def test_basic_joint_shape_distribution_matches_train(self):
        by_atom, _ = load_train_values(selected_only=True)
        observed = basic_joint_shapes(by_atom["Basic Authorization"])
        generated = basic_joint_shapes(seeded_values("Basic Authorization", 2000))
        n, m = sum(observed.values()), sum(generated.values())
        unseen = sum(count for pair, count in generated.items() if pair not in observed) / m
        distance = sum(abs(observed[pair] / n - generated[pair] / m)
                       for pair in observed.keys() | generated.keys()) / 2
        self.assertLess(unseen, .02, "decoded username/password pairs unseen in train")
        self.assertLess(distance, .10, "joint group-shape total variation distance")
        for pair, count in observed.items():
            if count / n >= .05:
                self.assertAlmostEqual(generated[pair] / m, count / n, delta=.035)
        # Regression controls: reversing groups or drawing independent
        # marginals must fail even when marginal lengths/counts still match.
        reversed_pairs = collections.Counter()
        for (user, password), count in generated.items():
            reversed_pairs[tuple(reversed(user)), tuple(reversed(password))] += count
        self.assertGreater(sum(c for pair, c in reversed_pairs.items() if pair not in observed) / m, .65)
        users, passwords = collections.Counter(), collections.Counter()
        for (user, password), count in observed.items():
            users[user] += count
            passwords[password] += count
        independent_distance = sum(abs(observed[user, password] / n - uc * pc / n ** 2)
                                   for user, uc in users.items() for password, pc in passwords.items()) / 2
        self.assertGreater(independent_distance, .20)

    def test_jwt_header_layout_and_claim_concentration_against_train(self):
        by_atom, _ = load_train_values(selected_only=True)
        for atom in ("JSON Web Token", "Azure Access Token"):
            observed = jwt_summary(by_atom[atom])
            generated = jwt_summary(seeded_values(atom, 2000))
            with self.subTest(atom=atom):
                for field in ("typ", "kid"):
                    actual = sum(field in h for h in generated["headers"]) / len(generated["headers"])
                    target = sum(field in h for h in observed["headers"]) / len(observed["headers"])
                    self.assertAlmostEqual(actual, target, delta=.06)
                self.assertAlmostEqual(generated["largest_claim_share"],
                                       observed["largest_claim_share"], delta=.10)
                self.assertAlmostEqual(generated["largest_string_share"],
                                       observed["largest_string_share"], delta=.06)
                if atom == "Azure Access Token":
                    for summary in (observed, generated):
                        payloads = summary["payloads"]
                        summary["large_payload_share"] = sum(14 <= len(p) <= 20 for p in payloads) / len(payloads)
                        summary["jti_first_share"] = sum(next(iter(p)) == "jti" for p in payloads) / len(payloads)
                    self.assertAlmostEqual(generated["large_payload_share"], observed["large_payload_share"], delta=.10)
                    self.assertAlmostEqual(generated["jti_first_share"], observed["jti_first_share"], delta=.06)

    def test_train_format_report(self):
        by_atom, stats = load_train_values()
        self.assertGreater(stats["train_sessions"], 0)
        unknown = set(by_atom) - formats.FORMATS.keys() - formats.FREE_FORM_ATOMS
        self.assertEqual(unknown, set(), "every observed atomic category must be classified")
        print("\nTrain-only format audit: " + ", ".join(f"{key}={value}" for key, value in stats.items() if key != "jwk_forms"))
        selected, _ = load_train_values(selected_only=True)
        print(audit_table(selected))
        print("JWK span syntax counts: " + json.dumps(stats["jwk_forms"], sort_keys=True))
        print("PEM train: " + json.dumps(pem_summary(by_atom["PEM Private Key"]), sort_keys=True))
        print("PEM generated (2,000): " + json.dumps(pem_summary(seeded_values("PEM Private Key", 2000)), sort_keys=True))
        print("Basic decoded train (aggregates only): " + json.dumps(basic_summary(selected["Basic Authorization"]), sort_keys=True))
        print("Basic decoded generated (2,000): " + json.dumps(basic_summary(seeded_values("Basic Authorization", 2000)), sort_keys=True))
        print("Free-form atoms: " + "; ".join(sorted(formats.FREE_FORM_ATOMS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
