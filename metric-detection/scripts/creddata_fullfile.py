"""Whole-file CredData sources for task catalog v3: category gold, placeholders wherever gold stands, category values.

No LLM calls, no network, no agent runs. The source of a task is one whole CredData file (the whole-file conversion
under runs/creddata-source-fullfile, git-ignored); its gold is gold_category_train.jsonl, where each span carries the
CredData Category (or {dropped: reason}: not gold, stays source text). Split, repository and component come from
metric-detection/source_splits/creddata-v1 (session ids are the same as the excerpt conversion's).

Where a placeholder stands, and how a value is written there:
  literal       the whole string literal of a parsed language: the existing escaping codec
  literal_part  inside a string literal: the same codec, the value avoids the delimiters around it
  raw_code      outside literals in a parsed language (comment, unquoted value): verbatim, value avoids its context
  raw_text      a file type that is not parsed (.md .txt .properties .pem ...): verbatim, value avoids its context
  pem_block     a PEM private key: the generated key re-laid into the source layout (indentation, comment prefixes,
                literal \\n escapes, quoted/concatenated lines, line width)
  jwk_fields    a JWK fragment: key material substituted field by field; field order, quoting and layout kept
Anything else is excluded per file with a counted reason. Values: creddata_category_formats.generator_for(category)
for fixed formats (used as generated, redrawn whole when they hit a context character), otherwise
creddata_category_profiles.generate(category, draw, avoid=...). The frozen catalog (tasks.json, templates/) never
depends on generated values: eligibility only uses source text and fixed probe strings.

  python3 -B metric-detection/scripts/creddata_fullfile.py manifest [--check]
  python3 -B metric-detection/scripts/creddata_fullfile.py build [--per-family 25] [--exclude ids.txt] [--out DIR]
"""
from __future__ import annotations

import argparse
import ast
import base64
from collections import Counter, defaultdict
import inspect
import io
import json
from pathlib import Path
import re
import tempfile
import tokenize
import warnings

import creddata_tasks as T
import creddata_languages as L
import creddata_tasks_auto as A
from creddata_tasks_bilingual import pair_tasks
import value_gen

# Source files and JWK fragments are parsed as data (ast.parse, literal_eval in conforms): their escapes are not ours.
warnings.filterwarnings("ignore", message=r".*invalid escape sequence", category=SyntaxWarning)
FULLFILE = T.ROOT / "runs/creddata-source-fullfile"
MANIFEST = "manifest_fullfile.json"
SPLITS = ("train", "val", "test")
DEFAULT_OUT = T.ROOT / "runs/creddata-auto-v3-fullfile"
VERSION = "creddata-auto-v3-fullfile"
INPUTS = {"sessions": "data_test/sessions_from_CredData.jsonl", "labels": "labels_from_CredData.jsonl",
          "gold": "data_answer/gold_from_CredData.jsonl", "gold_category": "gold_category_{split}.jsonl",
          "category_uncategorized": "category_llm/uncategorized_{split}.jsonl",
          "category_assigned": "category_llm/assigned_{split}.jsonl"}
COMMANDS = {"conversion": "python3 metric-detection/scripts/convert_creddata.py --creddata ../CredData "
                          "--context-lines 100000000 --out runs/creddata-source-fullfile",
            "gold_category": "python3 -B metric-detection/scripts/creddata_gold_categories.py"}
LIMITS = {"max_lines": 1000, "max_bytes": 100 * 1024, "max_gold_spans": 30}
MATERIAL = ("n", "x", "y", "d", "p", "q", "dp", "dq", "qi", "k")
JWK_CURVES = {"EC": ("P-256", "P-384", "P-521"), "OKP": ("Ed25519", "X25519", "Ed448", "X448")}
# Characters beyond letters and digits that each fixed format can produce (a superset, checked when values are made).
FORMAT_SYMBOLS = {
    "BASE64 encoded PEM Private Key": "+/=", "BASE64 Private Key": "+/=", "Azure Access Token": "-._=",
    "Grafana Provisioned API Key": "-_=", "NTLM Token": "+/=", "Slack Token": "-", "AWS Client ID": "",
    "AWS Multi": "+/", "Google API Key": "-_", "Github Classic Token": "-_", "Anthropic API Key": "-_",
    "Perplexity API Key": "-_", "Grafana Service Account Token": "-_", "WunderGraph API Key": "_",
    "Postman Credentials": "-", "Twilio Credentials": "", "Dropbox App secret": "", "PostHog Credentials": "_",
    "Google OAuth Access Token": "-._", "Google OAuth Refresh Token": "-/_", "Docker Swarm Token": "-",
    "NKEY Seed": "", "OTP / 2FA Secret": "", "UUID": "-", "PASETO Token": "-._", "PASERK Keys": "-._",
    "JSON Web Token": "-._=", "Basic Authorization": "+/="}
# A verbatim value never holds whitespace, quotes or a backslash (HARD_AVOID), nor its neighbours (context_avoid).
# Free-form values there also avoid characters that open markup, interpolation or comments (SOFT_AVOID); fixed formats
# are used as generated, so a fixed format whose characters meet the hard set of its position is excluded instead.
HARD_AVOID = " \t\r\n\f\v'\"`\\"
SOFT_AVOID = "<>&$%{}#;,|*"
URL_AVOID = ":/?#@%"
TEXT_LABELS = {
    ".md": "Markdown", ".markdown": "Markdown", ".mdx": "MDX", ".rst": "reStructuredText", ".asciidoc": "AsciiDoc",
    ".txt": "plain text", ".key": "private key file", ".pem": "PEM file", ".p8": "PKCS#8 key file",
    ".private": "private key file", ".html": "HTML", ".properties": "Java properties", ".conf": "configuration file",
    ".cnf": "configuration file", ".cf": "configuration file", ".config": "configuration file (.config)",
    ".ini": "INI", ".env": "environment file", ".gradle": "Gradle build script", ".groovy": "Groovy",
    ".example": "example configuration file", ".template": "template file", ".dist": "distribution template",
    ".j2": "Jinja2 template", ".erb": "ERB template", ".haml": "Haml template", ".stub": "template stub",
    ".tf": "Terraform", ".tfstate": "Terraform state (JSON)", ".sql": "SQL", ".ex": "Elixir", ".exs": "Elixir script",
    ".hs": "Haskell", ".r": "R", ".m": "Objective-C or MATLAB", ".rs": "Rust", ".pm": "Perl module", ".pl": "Perl",
    ".t": "Perl test", ".pod": "Perl POD", ".lua": "Lua", ".swift": "Swift", ".sbt": "sbt build definition",
    ".vue": "Vue component", ".libsonnet": "Jsonnet library", ".bat": "Windows batch", ".cmd": "Windows batch",
    ".bats": "Bats test script", ".rsp": "response file", ".ldif": "LDIF", ".ldiff": "LDIF", ".har": "HTTP archive (JSON)",
    ".in": "template input file", ".ext": "extension configuration", ".test": "test data file", ".travis": "Travis CI file"}

COMMON = """현재 폴더는 원본 파일 하나 전체를 담은 개발 작업 환경이다.
먼저 subject 파일을 읽고 요청한 작업을 수행해줘. 원본 전체 프로젝트가 있다고 가정하지 말고,
확인되지 않는 내용은 명시해줘. 필요한 파일 읽기, 검색, 로컬 명령 실행과 편집을 사용해도 돼.
외부 서비스에 연결하거나 원본 모듈 전체를 실행할 필요는 없어. 테스트에서는 외부 의존성을 목으로 대체해줘.
작업 폴더 밖의 생성 정보나 다른 작업은 참조하지 말아줘.
"""
COMMON_EN = """This workspace contains one whole source file.
Read the subject file first and perform the requested development task. Do not assume the full original project
is available. State what cannot be verified. You may read, search, edit files, and run local commands.
Do not connect to external services or execute the entire original module. Mock external dependencies in tests.
Do not consult generation metadata or other tasks outside this workspace.
"""
LOADER = T.LOADER.replace("from the excerpt", "from the subject file")


class Ineligible(ValueError):
    pass


# ---- inputs --------------------------------------------------------------------------------------------------------

def manifest_name(split: str = "train") -> str:
    return MANIFEST if split == "train" else f"manifest_fullfile_{split}.json"


def input_paths(fullfile: Path = FULLFILE, split: str = "train") -> dict[str, Path]:
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    return {name: fullfile / relative.format(split=split) for name, relative in INPUTS.items()}


def manifest_document(fullfile: Path = FULLFILE, split: str = "train") -> dict:
    sessions = input_paths(fullfile, split)["sessions"]
    with sessions.open(encoding="utf-8") as stream:
        meta = json.loads(stream.readline())["meta"]
    return {"schema_version": 1, "purpose": "whole-file CredData inputs of the v3 task catalog",
            "creddata_commit": meta["creddata_commit"], "context_lines": meta["context_lines"],
            "commands": COMMANDS if split == "train" else
            {**COMMANDS, "gold_category": COMMANDS["gold_category"] + f" --split {split}"},
            "inputs": {name: {"path": str(path.relative_to(T.ROOT)), "sha256": T.sha(path.read_bytes()),
                              "bytes": path.stat().st_size} for name, path in input_paths(fullfile, split).items()},
            "note": "category_llm/*.jsonl are stored model assignments (inputs, not regenerated). "
                    "Split, repository and component come from metric-detection/source_splits/creddata-v1."}


def check_manifest(fullfile: Path = FULLFILE, split: str = "train") -> dict:
    stored = json.loads((fullfile / manifest_name(split)).read_text())
    for name, record in stored["inputs"].items():
        if T.sha((T.ROOT / record["path"]).read_bytes()) != record["sha256"]:
            raise ValueError(f"whole-file input changed after the catalog manifest was recorded: {name}")
    return stored


def load_sources(fullfile: Path, wanted: set[str] | None = None, split: str = "train"):
    """(sessions by id, non-dropped gold rows by session id, dropped counts) of the whole-file inputs of a split."""
    paths = input_paths(fullfile, split)
    gold, dropped = defaultdict(list), Counter()
    for row in T.rows(paths["gold_category"]):
        if wanted is not None and row["session_id"] not in wanted:
            continue
        if "dropped" in row:
            dropped[row["dropped"]] += 1
            continue
        gold[row["session_id"]].append(row)
    keep = set(gold) if wanted is None else wanted
    sessions = {}
    for session in T.rows(paths["sessions"]):
        if session["session_id"] in keep:
            sessions[session["session_id"]] = session
    return sessions, gold, dropped


# ---- language and syntax -------------------------------------------------------------------------------------------

def file_language(path: str) -> tuple[str, str, bool]:
    """(slug, human-readable label, parsed) for a CredData file name."""
    try:
        language = L.language_for(path)
        return language, L.LABELS[language], True
    except ValueError:
        suffix = Path(path).suffix.lower()
        return "text" + suffix, TEXT_LABELS.get(suffix, f"plain text ({suffix})" if suffix else "plain text"), False


def syntax_mode(text: str, language: str, parsed: bool) -> str:
    """complete, fragment (Tree-sitter errors), invalid (a Python/config parse failure) or unparsed."""
    if not parsed:
        return "unparsed"
    try:
        if language == "python":
            parse_python(text)
        elif language in L.CONFIG_LANGUAGES:
            L.config_data(text, language)
        else:
            return L.source_facts(text, language)["syntax_mode"]
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return "invalid"
    return "complete"


def parse_python(text: str):
    with warnings.catch_warnings():  # source files are data: their invalid escapes are not our warnings
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(text)


def string_regions(text: str, language: str, mode: str):
    if mode in ("invalid", "unparsed"):
        return []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return T.string_regions(text, language)
    except (ValueError, SyntaxError, tokenize.TokenError):
        return []


def still_valid(text: str, language: str, mode: str) -> bool:
    """Rendered source keeps the syntax state it had: only a complete source is required to stay complete."""
    return mode != "complete" or syntax_mode(text, language, True) == "complete"


# ---- positions ------------------------------------------------------------------------------------------------------

def format_atom(category: str) -> str | None:
    import creddata_category_formats as F
    generator = F.generator_for(category)
    if generator is None:
        return None
    return next(name for name, function in F.FORMATS.items() if function is generator)


def codec_avoid(codec: str) -> str:
    """Characters a literal codec cannot write."""
    if codec == "yaml_single":
        return "".join(map(chr, range(32)))
    if codec.startswith("native:"):
        _, language, kind = codec.split(":")
        if kind == "raw":
            return "`\r\x00"
        if kind == "single" and language in {"bash", "toml"}:
            return "'\n\x00"
    return ""


def context_avoid(text: str, start: int, end: int) -> str:
    """Hard characters for a verbatim value: whitespace, quotes, backslash, its two neighbours, URL syntax in a URL."""
    chars = set(HARD_AVOID)
    for position in (start - 1, end):
        if 0 <= position < len(text) and not text[position].isalnum():
            chars.add(text[position])
    left, right = start, end
    while left > max(0, start - 200) and not text[left - 1].isspace():
        left -= 1
    while right < min(len(text), end + 200) and not text[right].isspace():
        right += 1
    if "://" in text[left:right]:
        chars.update(URL_AVOID)
    return "".join(sorted(chars))


ARMOR_BEGIN = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----")
ARMOR_END = re.compile(r"-----END ([A-Z0-9 ]+)-----\Z")
# A "+" between quotes/whitespace is a concatenation operator, not base64.
PEM_PIECE = re.compile(r"(?P<esc>\\+[nrt])|(?P<op>(?<=[\s\"'])\+(?=[\s\"']|\Z))|(?P<body>[A-Za-z0-9+/]+=*)"
                       r"|(?P<other>[^A-Za-z0-9+/=\\]+|\\|=)")
LINE_BREAK = re.compile(r"\\+[nr]|\n")


def pem_parts(surface: str) -> tuple[str, list[str], list[str]]:
    """(label, separators, body lines) of an armored key written in any layout; separators[0] follows BEGIN."""
    begin, end = ARMOR_BEGIN.match(surface), ARMOR_END.search(surface)
    if not begin or not end or end.start() < begin.end():
        raise Ineligible("pem_span_not_armored")
    if begin[1] != end[1]:
        raise Ineligible("pem_armor_labels_differ")
    middle = surface[begin.end():end.start()]
    if re.search(r"Proc-Type:|DEK-Info:|Version:|Comment:", middle):
        raise Ineligible("pem_headers_unsupported")
    first = LINE_BREAK.search(middle)
    if first is None:
        raise Ineligible("pem_without_line_breaks")
    separators, bodies, current = [], [], middle[:first.end()]
    for m in PEM_PIECE.finditer(middle, first.end()):
        if m["body"]:
            separators.append(current)
            bodies.append(m["body"])
            current = ""
        else:
            current += m.group()
    separators.append(current)
    return begin[1], separators, bodies


def pem_layout(surface: str) -> tuple[dict, str]:
    """The re-layable shape of a source key, and its logical value (armor and body lines joined by newlines)."""
    label, separators, bodies = pem_parts(surface)
    if not bodies:
        raise Ineligible("pem_without_body")
    joins = separators[1:-1]
    if any("..." in x or "\u2026" in x for x in separators):
        raise Ineligible("pem_body_elided")
    if len(set(joins)) > 1 or any("=" in b for b in bodies[:-1]):
        raise Ineligible("pem_irregular_layout")
    widths = [len(b) for b in bodies]
    if len(bodies) > 1 and (len(set(widths[:-1])) != 1 or widths[-1] > widths[0]):
        raise Ineligible("pem_irregular_line_width")
    body = "".join(bodies)
    if len(body) < 64:
        raise Ineligible("pem_body_too_short")
    try:
        base64.b64decode(body, validate=True)
    except ValueError:
        raise Ineligible("pem_body_not_base64") from None
    layout = {"first": separators[0], "join": joins[0] if joins else None, "last": separators[-1],
              "width": widths[0] if len(bodies) > 1 else None}
    return layout, pem_value(label, bodies)


def pem_value(label: str, lines: list[str]) -> str:
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----"


def pem_lines(value: str, width: int | None) -> tuple[str, list[str]]:
    """(label, body lines at width) of a canonical generated or given PEM; ValueError when it has headers."""
    try:
        label, separators, bodies = pem_parts(value)
    except Ineligible as reason:
        raise ValueError(str(reason)) from None
    if not bodies or any(s not in ("\n", "") for s in separators):
        raise ValueError("PEM value is not a plain armored block")
    body = "".join(bodies)
    return label, [body] if width is None else [body[i:i + width] for i in range(0, len(body), width)]


def pem_surface(value: str, layout: dict) -> str:
    label, lines = pem_lines(value, layout["width"])
    if pem_value(label, lines) != value:
        raise ValueError("PEM value is not wrapped at the source line width")
    joined = lines[0] if layout["join"] is None else layout["join"].join(lines)
    return f"-----BEGIN {label}-----" + layout["first"] + joined + layout["last"] + f"-----END {label}-----"


def pem_decode(surface: str) -> str:
    label, _, bodies = pem_parts(surface)
    return pem_value(label, bodies)


JWK_FIELD = re.compile(r"""(?P<key>["']?(?P<name>[A-Za-z_]\w*)["']?)\s*:\s*(?P<q>["'])(?P<value>[^"'\\\n]*)""")
JWK_GAP = re.compile(r"""["']?\s*,?\s*(?:["']?\w+["']?\s*:\s*(?:true|false|null|-?\d+|\[\s*\])\s*,?\s*)*""")
JWK_LEAD = re.compile(r"""["']?([A-Za-z_]\w*)["']?\s*:\s*["']\Z""")


def b64url_bytes(value: str) -> int:
    return len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def jwk_layout(text: str, start: int, end: int) -> dict:
    """Field-by-field substitution plan of a JWK fragment span: pieces of kept source text and material fields."""
    if re.search(r"[{}\[\]();]", text[start:end].replace("[]", "")):
        raise Ineligible("jwk_span_crosses_objects")
    lead = JWK_LEAD.search(text, max(0, start - 40), start)
    origin = lead.start() if lead else start
    stop = end + 1 if text[end:end + 1] in ("'", '"') else end
    fields, pieces, cursor, gap_from = {}, [], start, origin
    for m in JWK_FIELD.finditer(text, origin, stop):
        if not JWK_GAP.fullmatch(text, gap_from, m.start()):
            raise Ineligible("jwk_unexpected_syntax")
        gap_from = m.end()
        name, value = m["name"], m["value"]
        if name in fields:
            raise Ineligible("jwk_duplicate_field")
        fields[name] = value
        if name not in MATERIAL:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", value) or m.start("value") < start or m.end("value") > end:
            raise Ineligible("jwk_material_not_base64url")
        pieces += [["text", text[cursor:m.start("value")]], ["field", name]]
        cursor = m.end("value")
    if not JWK_GAP.fullmatch(text, gap_from, stop):
        raise Ineligible("jwk_unexpected_syntax")
    pieces.append(["text", text[cursor:end]])
    kty = fields.get("kty")
    if kty not in ("RSA", "EC", "OKP", "oct"):
        raise Ineligible("jwk_kty_missing_or_unsupported")
    material = [p[1] for p in pieces if p[0] == "field"]
    allowed = {"RSA": {"n", "d", "p", "q", "dp", "dq", "qi"}, "EC": {"x", "y", "d"}, "OKP": {"x", "d"}, "oct": {"k"}}[kty]
    if not material or not set(material) <= allowed:
        raise Ineligible("jwk_field_not_generated")
    spec = {"kty": kty, "curve": None, "modulus_bits": None, "oct_bytes": None, "pieces": pieces}
    if kty == "RSA":
        bits = b64url_bytes(fields["n"] if "n" in fields else fields["d"]) * 8
        if not 512 <= bits <= 16384 or bits % 16:
            raise Ineligible("jwk_rsa_size_unsupported")
        spec["modulus_bits"] = bits
    elif kty in JWK_CURVES:
        if fields.get("crv") not in JWK_CURVES[kty]:
            raise Ineligible("jwk_curve_unsupported")
        spec["curve"] = fields["crv"]
    else:
        spec["oct_bytes"] = b64url_bytes(fields["k"])
        if spec["oct_bytes"] not in (16, 24, 32):
            raise Ineligible("jwk_oct_size_unsupported")
    return spec


def jwk_render(spec: dict, material: dict[str, str]) -> str:
    return "".join(piece[1] if piece[0] == "text" else material[piece[1]] for piece in spec["pieces"])


def analyse_span(text: str, span: dict, regions: list, language: str, mode: str) -> dict:
    """Where one gold span stands and how a value is written there; Ineligible(reason) when not supported."""
    start, end, category = span["start"], span["end"], span["category"]
    surface = text[start:end]
    atom = format_atom(category)
    base = {"category": category, "coarse_type": span["type"], "category_source": span["category_source"],
            "format_atom": atom}
    if atom == "PEM Private Key" or surface.startswith("-----BEGIN"):
        if atom != "PEM Private Key":
            raise Ineligible("armored_key_with_non_pem_category")
        layout, original = pem_layout(surface)
        return {**base, "position": "pem_block", "codec": "pem", "layout": layout, "original": original, "avoid": ""}
    if atom == "JWK":
        return {**base, "position": "jwk_fields", "codec": "jwk", "jwk": jwk_layout(text, start, end),
                "original": surface, "avoid": ""}
    if "\n" in surface or "\r" in surface:
        raise Ineligible("multiline_span_not_pem_or_jwk")
    containers = [(a, b, c) for a, b, c in regions if a <= start and end <= b]
    if any(a < end and start < b and (a, b, c) not in containers for a, b, c in regions):
        raise Ineligible("gold_crosses_string_literal_boundary")
    if len(containers) > 1:
        raise Ineligible("ambiguous_string_literal")
    if containers:
        a, b, codec = containers[0]
        if language == "json" and text[b + 1:].lstrip().startswith(":"):
            raise Ineligible("gold_in_json_key")
        try:
            original = T.decode_fragment(surface, codec)
        except (ValueError, SyntaxError):
            raise Ineligible("gold_cuts_escape_sequence") from None
        if (a, b) == (start, end):
            occurrence = {"position": "literal", "codec": codec}
            hard = set(codec_avoid(codec))
        else:  # a plain YAML scalar's codec quotes the whole scalar, so part of one is written verbatim
            occurrence = {"position": "literal_part", "codec": "raw" if codec == "yaml_plain" else codec}
            hard = set(context_avoid(text, start, end) + codec_avoid(codec))
    else:
        original = surface
        occurrence = {"position": "raw_code" if mode != "unparsed" else "raw_text", "codec": "raw"}
        hard = set(context_avoid(text, start, end))
    if atom is None:
        occurrence["avoid"] = "".join(sorted(hard | (set(SOFT_AVOID) if occurrence["position"] != "literal" else set())))
    else:
        symbols = FORMAT_SYMBOLS.get(atom)
        if symbols is None:
            raise Ineligible("fixed_format_symbols_unknown")
        if set(symbols) & hard:
            raise Ineligible("fixed_format_conflicts_with_context")
        occurrence["avoid"] = "".join(sorted(hard))
    return {**base, **occurrence, "original": original}


# ---- templates ------------------------------------------------------------------------------------------------------

def make_template(text: str, spans: list[dict], language: str, mode: str, key: str):
    """(template, slots, occurrences); Ineligible with the first reason, spans analysed in order."""
    regions = string_regions(text, language, mode)
    analysed = []
    previous = 0
    unique = {(r["start"], r["end"], r["category"]): r for r in reversed(spans)}  # a repeated row counts once
    for span in sorted(unique.values(), key=lambda r: (r["start"], r["end"])):
        if not 0 <= previous <= span["start"] < span["end"] <= len(text):
            raise Ineligible("overlapping_gold_spans")
        previous = span["end"]
        analysed.append((span, analyse_span(text, span, regions, language, mode)))
    slots, occurrences, names, pieces, cursor, template_cursor = {}, [], {}, [], 0, 0
    for span, info in analysed:
        identity = (info["original"], info["category"])
        if identity not in names:
            names[identity] = "s_" + T.sha(key.encode())[:10] + f"_{len(names) + 1:02}"
        name = names[identity]
        slot = slots.setdefault(name, {
            "type": info["category"], "coarse_type": info["coarse_type"], "category_source": info["category_source"],
            "generator": "category_format" if info["format_atom"] else "category_profile",
            "format_atom": info["format_atom"], "avoid": "", "structure": None,
            "source_value_sha256": T.sha(info["original"].encode())})
        slot["avoid"] = "".join(sorted(set(slot["avoid"] + info["avoid"])))
        if info["position"] == "pem_block":
            if slot["structure"] == "pem" and slot["pem_width"] != info["layout"]["width"]:
                raise Ineligible("pem_slot_layouts_disagree")
            slot.update(structure="pem", pem_width=info["layout"]["width"])
        elif info["position"] == "jwk_fields":
            if slot["structure"] == "jwk" and slot["jwk"] != info["jwk"]:
                raise Ineligible("jwk_slot_layouts_disagree")
            slot.update(structure="jwk", jwk=info["jwk"])
        before = text[cursor:span["start"]]
        marker = "{{secret:" + name + "}}"
        pieces.extend((before, marker))
        template_cursor += len(before)
        occurrence = {"secret_id": name, "codec": info["codec"], "position": info["position"],
                      "category_source": info["category_source"], "start": template_cursor,
                      "end": template_cursor + len(marker), "source_start": span["start"], "source_end": span["end"]}
        if info["position"] == "pem_block":
            occurrence["layout"] = info["layout"]
        occurrences.append(occurrence)
        template_cursor += len(marker)
        cursor = span["end"]
    pieces.append(text[cursor:])
    template = "".join(pieces)
    if len(list(T.PLACEHOLDER.finditer(template))) != len(occurrences):
        raise Ineligible("placeholder_syntax_in_source")
    for (original, _), name in names.items():
        surfaces = {original} | {text[o["source_start"]:o["source_end"]] for o in occurrences if o["secret_id"] == name}
        if any(len(s) >= 12 and s in template for s in surfaces):
            raise Ineligible("untemplated_recurrence_of_gold_value")
    if not slots:
        raise Ineligible("no_gold")
    return template, slots, occurrences


LETTER_PROBES = ("qzkpxwrmtbvn", "hjqzkwxprtmv", "wqzrtpkmvxbn", "zxqvkrtwpmhj")


def probe_values(slots: dict, occurrences: list, text: str, letters: bool = False) -> dict:
    """Fixed probe strings (not generated) for the label-rule position check; key blocks keep their source text.
    letters=True gives free-form slots a letters-only probe: profiles often draw such values, and some unquoted
    positions (an enum member, a variable-like word) read them as code."""
    values = {}
    for n, (name, slot) in enumerate(sorted(slots.items()), 1):
        source = next(o for o in occurrences if o["secret_id"] == name)
        surface = text[source["source_start"]:source["source_end"]]
        if slot["structure"] == "pem":
            values[name] = pem_decode(surface)
        elif slot["structure"] == "jwk":
            values[name] = surface
        elif slot["format_atom"] == "UUID":
            values[name] = f"5c1b7e2a-90d4-4f6e-8a3b-{n:012d}"
        elif letters and slot["format_atom"] is None:
            values[name] = LETTER_PROBES[n % 4] + "qz" * (n // 4)
        else:
            values[name] = f"Qz7Kp{n:03d}Xw4Rm9Tb"
    return values


# ---- values ---------------------------------------------------------------------------------------------------------

def _profile_generate(category: str, draw, avoid: str) -> str:
    import creddata_category_profiles as P
    if "avoid" in inspect.signature(P.generate).parameters:
        return P.generate(category, draw, avoid=avoid)
    for attempt in range(128):  # the profile module without avoid: redraw here
        value = P.generate(category, draw)
        if not set(value) & set(avoid):
            return value
    raise ValueError("cannot generate a profile value outside the avoided characters")


def generate_slot(slot: dict, seed: str) -> str:
    import creddata_category_formats as F
    if slot["structure"] == "jwk":
        spec = slot["jwk"]
        for attempt in range(64):
            draw = value_gen.Draw(seed if attempt == 0 else f"{seed}:jwk-size-redraw:{attempt}")
            options = {"curve": spec["curve"]} if spec["curve"] else \
                {"modulus_bits": spec["modulus_bits"]} if spec["modulus_bits"] else {}
            material = {**F.jwk_public_fields(draw, spec["kty"], **options),
                        **F.jwk_private_fields(draw, spec["kty"], **options)}
            if spec["oct_bytes"] is None or b64url_bytes(material["k"]) == spec["oct_bytes"]:
                return jwk_render(spec, material)
        raise ValueError("cannot draw a JWK of the source size")
    generator = F.generator_for(slot["type"])
    if generator is None:
        return _profile_generate(slot["type"], value_gen.Draw(seed), slot["avoid"])
    for attempt in range(16):
        value = generator(value_gen.Draw(seed if attempt == 0 else f"{seed}:format-redraw:{attempt}"))
        if slot["structure"] == "pem":
            try:
                label, lines = pem_lines(value, slot["pem_width"])
            except ValueError:
                continue  # headers (encrypted legacy or PGP armor) do not fit a source layout without them
            return pem_value(label, lines)
        if not set(value) & set(slot["avoid"]):
            return value
    raise ValueError("cannot draw a fixed-format value that fits its source position")


def generate_values(task: dict, seed: str, redraws: dict[str, int] | None = None) -> dict[str, str]:
    """One value per slot (distinct source value and category); a slot redrawn k times uses its k-th redraw seed."""
    values = {}
    for name, slot in task["slots"].items():
        base, k = f"creddata-fullfile-v3:{task['split']}:{seed}:{name}", (redraws or {}).get(name, 0)
        values[name] = generate_slot(slot, base if k == 0 else f"{base}:source-rule-redraw:{k}")
    return values


def encode(value: str, occurrence: dict, slot: dict) -> str:
    codec = occurrence["codec"]
    if codec == "pem":
        return pem_surface(value, occurrence["layout"])
    if codec in ("raw", "jwk"):
        if set(value) & set(slot["avoid"]):
            raise ValueError("value contains a character its source position cannot hold")
        return value
    if set(value) & set(slot["avoid"]):
        raise ValueError("value contains a character its source position cannot hold")
    return T.encode_fragment(value, codec)


def decode(surface: str, codec: str) -> str:
    if codec == "pem":
        return pem_decode(surface)
    if codec in ("raw", "jwk"):
        return surface
    return T.decode_fragment(surface, codec)


def render(task: dict, template: str, values: dict[str, str]) -> tuple[str, list[dict]]:
    if set(values) != set(task["slots"]):
        raise ValueError("value mapping must contain exactly this task's secret IDs")
    pieces, cursor, length, annotations = [], 0, 0, []
    for occurrence in task["occurrences"]:
        start, end, name = occurrence["start"], occurrence["end"], occurrence["secret_id"]
        if not cursor <= start < end <= len(template) or template[start:end] != "{{secret:" + name + "}}":
            raise ValueError("template placeholder offsets changed")
        slot = task["slots"][name]
        before = template[cursor:start]
        encoded = encode(values[name], occurrence, slot)
        pieces.extend((before, encoded))
        length += len(before)
        view_start, view_end, view_codec = L.rendered_span(occurrence["codec"], encoded)
        annotations.append({"secret_id": name, "start": length + view_start, "end": length + view_end,
                            "codec": view_codec, "position": occurrence["position"], "source_type": slot["type"],
                            "coarse_type": slot["coarse_type"]})
        length += len(encoded)
        cursor = end
    pieces.append(template[cursor:])
    text = "".join(pieces)
    for annotation in annotations:
        if decode(text[annotation["start"]:annotation["end"]], annotation["codec"]) != values[annotation["secret_id"]]:
            raise ValueError("rendered span does not decode to the requested value")
    return text, annotations


def projection_misses(task: dict, text: str, annotations: list[dict], values: dict[str, str]) -> list[dict]:
    """Annotations the rollout labeler does not label at exactly their extent, the file read as one tool output."""
    import creddata_rollout as R
    import convert_trajectory as C
    registry = {"values": values, "source_annotations": annotations}
    _, gold, _, _ = R.label_items(task, registry, [C.Item("t0", "tool_output", text, "Read", {})], "probe")
    found = {(g["span"]["start"], g["span"]["end"]) for g in gold}
    return [a for a in annotations if (a["start"], a["end"]) not in found]


def judge_misses(text: str, annotations: list[dict], values: dict[str, str]) -> list[dict]:
    """The earlier draw check (label_rules.judge_occurrence) on single-value positions; key blocks are skipped."""
    from label_rules import is_common, judge_occurrence
    return [a for a in annotations if a["codec"] not in ("pem", "jwk")
            and not judge_occurrence(text, a["start"], a["end"], is_common(values[a["secret_id"]]))[0]]


def sample_rendered_values(task: dict, template: str, seed: str):
    """Redraw a slot (up to 16 times) while label rules reject one of its values, the labeler does not project it,
    or the rendered file loses its syntax (then every slot is redrawn). Accepted slots keep their values."""
    redraws, log = {name: 0 for name in task["slots"]}, []
    while max(redraws.values()) < 16:
        values = generate_values(task, seed, redraws)
        text, annotations = render(task, template, values)
        rejected = [(a, "judge_occurrence") for a in judge_misses(text, annotations, values)]
        if not rejected:
            rejected = [(a, "label_projection") for a in projection_misses(task, text, annotations, values)]
        if not rejected and not still_valid(text, task["language"], task["syntax_mode"]):
            rejected = [({"secret_id": None, "position": "*", "source_type": "*"}, "syntax")]
        if not rejected:
            return values, text, annotations, {k: v for k, v in redraws.items() if v}, log
        for name in {a["secret_id"] for a, _ in rejected if a["secret_id"]} or set(redraws):
            redraws[name] += 1
        log += [{"attempt": max(redraws.values()) - 1, "secret_id": a["secret_id"], "check": check,
                 "position": a["position"], "category": a["source_type"],
                 **({"language": task["language"]} if check == "syntax" else {})} for a, check in rejected]
    raise ValueError("could not draw values accepted by label rules, projection and syntax after 16 redraws "
                     "of a slot: " + json.dumps(Counter((r["check"], r["category"]) for r in log).most_common(3)))


def generator_inputs() -> dict:
    scripts = Path(__file__).resolve().parent
    profile = FULLFILE / "category_profiles_v2.json"
    return {"creddata_category_formats.py": T.sha((scripts / "creddata_category_formats.py").read_bytes()),
            "creddata_category_profiles.py": T.sha((scripts / "creddata_category_profiles.py").read_bytes()),
            "category_profiles_v2.json": T.sha(profile.read_bytes()) if profile.is_file() else None}


def instantiate(pack: Path, task_id: str, seed: str, overrides: dict | None = None) -> dict[str, bytes]:
    task_dir = pack / task_id
    task = json.loads((task_dir / "task.json").read_text())
    template = (task_dir / "workspace" / task["source_filename"]).read_text()
    log = []
    if overrides is None:
        values, text, annotations, redraws, log = sample_rendered_values(task, template, seed)
    else:
        if any(s["structure"] == "jwk" for s in task["slots"].values()):
            raise ValueError("--values is not supported for JWK slots; their layout comes from the source")
        values, redraws = overrides, {}
        text, annotations = render(task, template, values)
    files = {"workspace/" + p.name: p.read_bytes() for p in (task_dir / "workspace").iterdir() if p.is_file()}
    files["workspace/" + task["source_filename"]] = text.encode()
    if task["language"] == "javascript":
        files["workspace/snippet_functions.json"] = T.jb(L.javascript_ranges(text))
    files["task.json"] = T.jb(task)
    registry = {"task_id": task_id, "seed": seed, "split": task["split"], "values": values,
                "source_file": task["source_filename"], "source_annotations": annotations,
                "source_sha256": T.sha(text.encode()), "annotation_scope": task["annotation_scope"],
                "value_generation": {"method": "creddata_category_formats.generator_for, else "
                                               "creddata_category_profiles.generate(avoid=slot avoid)",
                                     "inputs_sha256": generator_inputs()}}
    if redraws:
        registry["source_rule_redraws"] = sum(redraws.values())
        registry["source_rule_redraws_by_slot"] = redraws
        registry["redraw_log"] = log
    files["private/registry.json"] = T.jb(registry)
    return files


# ---- candidates -----------------------------------------------------------------------------------------------------

def inspect_file(session: dict, spans: list[dict], repo: dict) -> dict:
    """Eligibility of one whole file; Ineligible(reason) when it is not a candidate."""
    text = session["items"][0]["text"]
    if len(session["items"]) != 1:
        raise Ineligible("not_one_whole_file_item")
    lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    if lines > LIMITS["max_lines"]:
        raise Ineligible("more_than_1000_lines")
    if len(text.encode()) > LIMITS["max_bytes"]:
        raise Ineligible("more_than_100_kb")
    if len(spans) > LIMITS["max_gold_spans"]:
        raise Ineligible("more_than_30_gold_spans")
    language, label, parsed = file_language(session["meta"]["creddata_file"])
    mode = syntax_mode(text, language, parsed)
    key = f"{session['session_id']}:0"
    template, slots, occurrences = make_template(text, spans, language, mode, key)
    task = {"task_id": "probe", "family": "analysis", "split": "train", "language": language, "syntax_mode": mode,
            "source_scope": "whole_file", "slots": slots, "occurrences": occurrences,
            "component_id": repo["component_id"], "source_repo_id": repo["repo_id"],
            "source_session_id": session["session_id"], "source_item_id": 0, "source_license": "probe"}
    for letters in (False, True):
        probes = probe_values(slots, occurrences, text, letters)
        try:
            rendered, annotations = render(task, template, probes)
        except ValueError:
            raise Ineligible("source_layout_does_not_render") from None
        if projection_misses(task, rendered, annotations, probes):
            raise Ineligible("label_rules_reject_source_position")
    normalized = " ".join(T.PLACEHOLDER.sub("<SECRET>", template).split())
    if len("".join(normalized.replace("<SECRET>", "").split())) < A.MIN_CONTEXT_CHARS:
        raise Ineligible("too_little_nonsecret_context")
    families = ["analysis", "documentation"]
    facts = {"language": language, "source_language_label": label, "parsed": parsed, "syntax_mode": mode,
             "source_lines": lines, "source_bytes": len(text.encode()), "gold_spans": len(occurrences),
             "secret_slots": len(slots), "positions": dict(sorted(Counter(o["position"] for o in occurrences).items())),
             "categories": dict(sorted(Counter(slots[o["secret_id"]]["type"] for o in occurrences).items())),
             "category_sources": dict(sorted(Counter(o["category_source"] for o in occurrences).items()))}
    if mode == "complete" and language == "python":
        functions = A.testable_functions(parse_python(text))
        facts["testable_top_level_functions"] = functions
        if functions:
            families += ["refactoring", "test_writing"]
    elif mode == "complete" and language in L.CONFIG_LANGUAGES:
        try:
            parsed_config = json.loads(text, object_pairs_hook=A.json_object) if language == "json" else \
                L.config_data(text, language)
        except A.Ineligible:
            parsed_config = None
        if isinstance(parsed_config, dict) and len(parsed_config) >= 2:
            facts["top_level_keys"] = len(parsed_config)
            families += ["refactoring", "test_writing"]
    elif mode in ("complete", "fragment"):
        source_facts = L.source_facts(text, language)
        facts["functions"] = len(source_facts["functions"])
        standalone = [f["name"] for f in source_facts["functions"]
                      if f["standalone_javascript"] and f["name"] != "main" and not f["name"].startswith("test")]
        if mode == "complete" and source_facts["functions"]:
            families.append("refactoring")
        if mode == "complete" and standalone:
            facts["testable_javascript_functions"] = standalone
            families.append("test_writing")
    return {"source_session_id": session["session_id"], "source_item_id": 0, "source_repo_id": repo["repo_id"],
            "component_id": repo["component_id"], "source_item_sha256": T.sha(text.encode()),
            "context_sha256": T.sha(normalized.encode()), "eligible_families": families, "facts": facts}


def span_reasons(session: dict, spans: list[dict]) -> list[tuple[str, str, str]]:
    """(position, category_source, reason or ok) per gold span of a file within limits, for the funnel report."""
    text = session["items"][0]["text"]
    language, _, parsed = file_language(session["meta"]["creddata_file"])
    mode = syntax_mode(text, language, parsed)
    regions = string_regions(text, language, mode)
    out = []
    for span in spans:
        start, end = span["start"], span["end"]
        atom = format_atom(span["category"])
        position = ("pem_block" if atom == "PEM Private Key" or text[start:end].startswith("-----BEGIN") else
                    "jwk_fields" if atom == "JWK" else
                    "literal" if any((a, b) == (start, end) for a, b, _ in regions) else
                    "literal_part" if any(a <= start and end <= b for a, b, _ in regions) else
                    "raw_code" if mode != "unparsed" else "raw_text")
        try:
            analyse_span(text, span, regions, language, mode)
            out.append((position, span["category_source"], "ok"))
        except Ineligible as reason:
            out.append((position, span["category_source"], str(reason)))
    return out


def discover(split_dir: Path, fullfile: Path, exclude: set[str], split: str = "train"):
    check_manifest(fullfile, split)
    train = set((split_dir / f"{split}.txt").read_text().splitlines())
    repos = {r["group_id"]: r for r in T.rows(split_dir / "repositories.jsonl")}
    sessions, gold, dropped = load_sources(fullfile, split=split)
    candidates, file_reasons, span_counts = [], Counter(), Counter()
    funnel = Counter()
    all_gold_files = {r["session_id"] for r in T.rows(input_paths(fullfile, split)["gold_category"])}
    funnel["files_with_gold_rows"] = len(all_gold_files & train)
    for session_id in sorted(gold):
        if session_id not in train:
            raise ValueError(f"gold_category_{split}.jsonl lists a session of another split")
        session, spans = sessions[session_id], gold[session_id]
        funnel["files_with_non_dropped_gold"] += 1
        repo = repos[session["meta"]["group_id"]]
        if repo["split"] != split:
            raise ValueError("session/repository split mismatch")
        try:
            if session_id in exclude:
                raise Ineligible("excluded_by_list")
            text = session["items"][0]["text"]
            lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
            within = lines <= LIMITS["max_lines"] and len(text.encode()) <= LIMITS["max_bytes"] and \
                len(spans) <= LIMITS["max_gold_spans"]
            if within:
                funnel["within_limits"] += 1
                for position, source, reason in span_reasons(session, spans):
                    span_counts[(position, source, reason)] += 1
            candidate = inspect_file(session, spans, repo)
            funnel["eligible_files"] += 1
            candidates.append(candidate)
        except Ineligible as reason:
            file_reasons[str(reason)] += 1
    files_all_dropped = len((all_gold_files & train) - set(gold))
    by_position = defaultdict(Counter)
    by_source = defaultdict(Counter)
    for (position, source, reason), n in span_counts.items():
        by_position[position][reason] += n
        by_source[source][reason] += n
    profile = {
        "funnel": {f"{split}_files_with_gold_rows": funnel["files_with_gold_rows"],
                   "files_with_only_dropped_gold": files_all_dropped,
                   f"{split}_files_with_non_dropped_gold": funnel["files_with_non_dropped_gold"],
                   "within_limits": funnel["within_limits"], "eligible_files": len(candidates)},
        "limits": LIMITS, "dropped_gold_spans": dict(sorted(dropped.items())),
        "excluded_files": dict(sorted(file_reasons.items())),
        "spans_in_files_within_limits_by_position": {p: dict(sorted(c.items())) for p, c in sorted(by_position.items())},
        "spans_in_files_within_limits_by_category_source": {s: dict(sorted(c.items())) for s, c in sorted(by_source.items())},
        "eligible_repositories": len({c["source_repo_id"] for c in candidates}),
        "eligible_by_language": dict(sorted(Counter(c["facts"]["language"] for c in candidates).items())),
        "eligible_by_family": {f: sum(f in c["eligible_families"] for c in candidates) for f in T.FAMILIES}}
    return candidates, profile


# ---- catalog --------------------------------------------------------------------------------------------------------

def readme_text(task: dict, language_label: str) -> str:
    lines = task["source_line_range"][1]
    loader_ko = ("snippet_loader.py는 모듈을 import하지 않고 선택한 함수만 로드한다. "
                 "외부 이름은 bindings로 전달할 수 있고 원본 데코레이터는 적용하지 않는다.\n")
    loader_en = ("snippet_loader.py loads one function without importing the original module. "
                 "Pass external names through bindings; original decorators are not executed.\n")
    python = task["language"] == "python"
    if task["instruction_language"] == "en":
        return (f"# {task['family']} task\n\nThe subject file is one whole source file ({language_label}, {lines} lines).\n"
                "It is not the full project. Other files of the project are absent. Follow request.md.\n"
                + (loader_en if python else ""))
    return (f"# {T.NAMES[task['family']]} 작업\n\nsubject 파일은 원본 파일 하나 전체다({language_label}, {lines}줄).\n"
            "전체 프로젝트가 아니며 같은 프로젝트의 다른 파일은 없다. request.md의 작업을 수행한다.\n"
            + (loader_ko if python else ""))


def build_pack(config_path: Path, split_dir: Path = T.DEFAULT_SPLIT, fullfile: Path = FULLFILE) -> dict[str, bytes]:
    config = json.loads(config_path.read_text())
    definitions = config["tasks"]
    count = Counter(t["family"] for t in definitions)
    if dict(count) != {f: config["tasks_per_family"] for f in T.FAMILIES} or \
            len({t["task_id"] for t in definitions}) != len(definitions):
        raise ValueError("task families must have equal declared counts and unique task IDs")
    split = config["split"]
    check_manifest(fullfile, split)
    members = set((split_dir / f"{split}.txt").read_text().splitlines())
    requested = {t["source_session_id"] for t in definitions}
    if not requested <= members:
        raise ValueError(f"task source is outside the frozen {split} partition")
    sessions, gold, _ = load_sources(fullfile, requested, split)
    repository = {r["group_id"]: r for r in T.rows(split_dir / "repositories.jsonl")}
    files, summaries = {}, []
    for spec in definitions:
        task_id, session = spec["task_id"], sessions[spec["source_session_id"]]
        text = session["items"][0]["text"]
        language, label, parsed = file_language(session["meta"]["creddata_file"])
        mode = syntax_mode(text, language, parsed)
        template, slots, occurrences = make_template(text, gold[session["session_id"]], language, mode,
                                                     f"{session['session_id']}:0")
        group = repository[session["meta"]["group_id"]]
        filename = "subject" + Path(session["meta"]["creddata_file"]).suffix.lower()
        instruction = spec["instruction_template"].format(source_file=filename, source_language=label)
        prompt = (COMMON_EN if spec["instruction_language"] == "en" else COMMON) + "\n" + instruction + "\n"
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        task = {**spec, "split": split, "source_scope": "whole_file", "language": language,
                "source_language": language, "source_language_label": label, "syntax_mode": mode,
                "source_filename": filename, "source_repo_id": group["repo_id"], "component_id": group["component_id"],
                "source_file": session["meta"]["creddata_file"], "source_line_range": [1, lines],
                "source_item_sha256": T.sha(text.encode()), "source_license": session["meta"]["license"],
                "slots": slots, "occurrences": occurrences, "success_grading": None,
                "annotation_scope": "known source gold only (non-dropped CredData categories); completeness not certified",
                "rendered_instruction": instruction}
        if mode == "fragment" and spec["family"] not in {"analysis", "documentation"}:
            raise ValueError("incomplete source is only eligible for analysis/documentation")
        files[f"{task_id}/task.json"] = T.jb(task)
        files[f"{task_id}/workspace/{filename}"] = template.encode()
        files[f"{task_id}/workspace/request.md"] = prompt.encode()
        files[f"{task_id}/workspace/README.md"] = readme_text(task, label).encode()
        if language == "python":
            files[f"{task_id}/workspace/snippet_loader.py"] = LOADER.encode()
        if language == "javascript":
            files[f"{task_id}/workspace/snippet_loader.cjs"] = L.javascript_loader(filename).encode()
            files[f"{task_id}/workspace/snippet_functions.json"] = T.jb(L.javascript_ranges(template))
        summaries.append({"task_id": task_id, "family": spec["family"], "source_session_id": session["session_id"],
                          "source_item_id": 0, "source_repo_id": group["repo_id"], "slots": len(slots),
                          "source_gold_occurrences": len(occurrences),
                          "instruction_language": spec["instruction_language"], "task_pair_id": spec["task_pair_id"]})
    manifest = {"version": config["version"], "split": split, "source_scope": "whole_file", "counts": count,
                "source_sessions": len(requested), "source_repositories": len({r["source_repo_id"] for r in summaries}),
                "config_sha256": T.sha(config_path.read_bytes()),
                "split_manifest_sha256": T.sha((split_dir / "manifest.json").read_bytes()),
                "fullfile_manifest_sha256": T.sha((fullfile / manifest_name(split)).read_bytes()),
                "instruction_languages": dict(Counter(t["instruction_language"] for t in definitions)),
                "task_pairs": len({t["task_pair_id"] for t in definitions}),
                "tasks": summaries, "success_grading": None, "ready_for_training_export": False}
    files["manifest.json"] = T.jb(manifest)
    return files


def generate(split_dir: Path, fullfile: Path, instruction_path: Path, per_family: int, seed: str,
             max_per_repo: int, exclude_path: Path | None, split: str = "train"):
    exclude = set(exclude_path.read_text().split()) if exclude_path else set()
    instruction_config = json.loads(instruction_path.read_text())
    candidates, profile = discover(split_dir, fullfile, exclude, split)
    base_tasks = A.select_tasks(candidates, per_family, seed, max_per_repo, instruction_config["instructions"]["ko"],
                                True, "parser_rules_v3_fullfile")
    tasks = pair_tasks(base_tasks, instruction_config["instructions"])
    config = {"version": VERSION, "split": split, "source_scope": "whole_file", "tasks_per_family": per_family * 2,
              "selection_note": "Whole CredData files with category gold. Structural eligibility plus deterministic "
                                "sampling; four shared instruction templates in each of two instruction languages. "
                                "No LLM generation.",
              "automatic_generation": {"seed": seed, "max_per_repository_per_family": max_per_repo,
                                       "minimum_nonsecret_context_characters": A.MIN_CONTEXT_CHARS, "limits": LIMITS,
                                       "instruction_version": instruction_config["version"],
                                       "instruction_sha256": T.sha(instruction_path.read_bytes()),
                                       "split_manifest_sha256": T.sha((split_dir / "manifest.json").read_bytes()),
                                       "fullfile_manifest_sha256": T.sha((fullfile / manifest_name(split)).read_bytes()),
                                       "exclusion_list": None if exclude_path is None else
                                       {"sha256": T.sha(exclude_path.read_bytes()), "session_ids": len(exclude)}},
              "bilingual": {"languages": ["ko", "en"], "base_tasks": len(base_tasks),
                            "tasks_per_family_per_language": per_family},
              "tasks": tasks}
    selected = [c for c in candidates if any(c["source_session_id"] == t["source_session_id"] for t in base_tasks)]
    by_id = {c["source_session_id"]: c for c in selected}
    category_spans, positions = Counter(), Counter()
    for session_id in sorted({t["source_session_id"] for t in base_tasks}):
        category_spans.update(by_id[session_id]["facts"]["categories"])
        positions.update(by_id[session_id]["facts"]["positions"])
    stats = {**profile, "selected_tasks": len(tasks), "base_tasks": len(base_tasks),
             "selected_by_family": dict(Counter(t["family"] for t in tasks)),
             "selected_by_instruction_language": dict(Counter(t["instruction_language"] for t in tasks)),
             "selected_by_source_language": {f: dict(sorted(Counter(t["eligibility"]["facts"]["language"]
                                                                    for t in base_tasks if t["family"] == f).items()))
                                             for f in T.FAMILIES},
             "selected_source_files": len({t["source_session_id"] for t in tasks}),
             "selected_repositories": len({t["source_session_id"].split("-")[1] for t in tasks}),
             "selected_files_gold_spans_by_category": dict(sorted(category_spans.items(), key=lambda kv: (-kv[1], kv[0]))),
             "selected_files_gold_spans_by_position": dict(sorted(positions.items())),
             "distinct_instruction_count": len({t["instruction"] for t in tasks}), "llm_calls": 0,
             "checks": {f"all_{split}_sources": True, "same_count_per_family": True,
                        "one_instruction_template_per_family_and_language": True,
                        "no_duplicate_base_file_or_context_within_family": True,
                        "paired_languages_share_source_and_split": True},
             "limitations": ["Eligibility is structural, not a semantic guarantee that a task is worthwhile.",
                             "Known non-dropped gold only; this catalog does not establish exhaustive secret annotation.",
                             "Values are new synthetic values by category; they do not keep the meaning of the source "
                             "application (PEM armor labels follow the category generator, JWK keys are synthetic).",
                             "The shared v2 instruction templates still mention an excerpt; the workspace text says "
                             "the subject file is a whole source file."]}
    return config, candidates, stats


def readme(config: dict, stats: dict) -> str:
    f, split = stats["funnel"], config["split"]
    return ("# CredData 원본 파일 전체 기반 작업 (한국어·영어 쌍, v3)\n\n"
            f"작업군별 {config['tasks_per_family']}개, 총 {len(config['tasks'])}개다. 기본 작업 "
            f"{config['bilingual']['base_tasks']}개를 한국어·영어 지시문 쌍으로 발급했다. 지시문은 공통 템플릿 8개다. "
            "분류·지시문 작성용 LLM 호출은 없다.\n\n"
            f"원본은 ±10줄 조각이 아니라 CredData 파일 하나 전체다(1,000줄·100KB·gold 30개 이하, {split}만). "
            "gold 유형은 CredData Category이고, 제외(dropped)된 span은 정답이 아니어서 원문 그대로 둔다. "
            "placeholder는 문자열 리터럴 전체·일부, 주석·따옴표 없는 값, 파싱하지 않는 형식의 본문, 여러 줄 PEM, "
            "JWK 조각에 둘 수 있고, 처리할 수 없는 gold가 하나라도 있으면 그 파일을 사유와 함께 제외한다.\n\n"
            f"{split}에서 gold가 있는 파일 {f[split + '_files_with_non_dropped_gold']}개 중 제한 이내 {f['within_limits']}개, "
            f"후보 {f['eligible_files']}개다. 선택한 원본 파일은 {stats['selected_source_files']}개, "
            f"저장소는 {stats['selected_repositories']}개다. 모든 원본은 고정 {split} 분할이다.\n\n"
            "tasks.json은 지시문과 원본 매핑, eligibility.jsonl은 후보별 판정, selection.json은 후보·제외·선택 통계다. "
            "templates/에는 placeholder 환경이 있다. 생성값은 instances/에서 seed로 만든다.\n\n"
            "원본 애플리케이션의 단위 테스트가 아니다. 구조 규칙만으로 의미상 좋은 과제나 라벨 완전성을 보장하지 않는다.\n")


def write_expansion(out: Path, config: dict, candidates: list[dict], stats: dict, split_dir: Path, fullfile: Path):
    with tempfile.TemporaryDirectory(prefix="creddata-fullfile-config-") as temporary:
        path = Path(temporary) / "tasks.json"
        path.write_bytes(T.jb(config))
        templates = build_pack(path, split_dir, fullfile)
    files = {"tasks.json": T.jb(config), "selection.json": T.jb(stats), "README.md": readme(config, stats).encode(),
             "eligibility.jsonl": b"".join((json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n").encode()
                                           for c in sorted(candidates, key=lambda c: c["source_session_id"]))}
    files.update({"templates/" + name: value for name, value in templates.items()})
    T.write_catalog(out, files)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("manifest", help="record (or --check) the whole-file input hashes")
    manifest.add_argument("--fullfile", type=Path, default=FULLFILE)
    manifest.add_argument("--check", action="store_true")
    manifest.add_argument("--split", default="train", choices=SPLITS)
    build = sub.add_parser("build")
    build.add_argument("--split-dir", type=Path, default=T.DEFAULT_SPLIT)
    build.add_argument("--fullfile", type=Path, default=FULLFILE)
    build.add_argument("--instructions", type=Path, default=A.INSTRUCTIONS)
    build.add_argument("--per-family", type=int, default=25)
    build.add_argument("--seed", default=VERSION)
    build.add_argument("--max-per-repo", type=int, default=3)
    build.add_argument("--exclude", type=Path, help="session ids to exclude, one per line")
    build.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build.add_argument("--version", default=VERSION, help="catalog version name; a reissue gets its own")
    build.add_argument("--split", default="train", choices=SPLITS, help="source partition of the catalog")
    args = parser.parse_args()
    if args.command == "manifest":
        path = args.fullfile / manifest_name(args.split)
        document = T.jb(manifest_document(args.fullfile, args.split))
        if args.check or path.exists():
            same = path.exists() and path.read_bytes() == document
            print(json.dumps({"manifest": str(path), "matches_inputs": same}))
            if not same:
                raise SystemExit(1)
            return
        path.write_bytes(document)
        print(json.dumps({"manifest": str(path), "written": True}))
        return
    config, candidates, stats = generate(args.split_dir, args.fullfile, args.instructions, args.per_family, args.seed,
                                         args.max_per_repo, args.exclude, args.split)
    config["version"] = args.version
    write_expansion(args.out, config, candidates, stats, args.split_dir, args.fullfile)
    print(json.dumps({"out": str(args.out), **{k: stats[k] for k in ("funnel", "excluded_files", "eligible_by_family",
                                                                     "selected_by_family", "selected_source_files",
                                                                     "selected_repositories")}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
