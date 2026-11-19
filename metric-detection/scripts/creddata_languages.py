"""Language adapters for secret string literals; parses source, never executes it."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
PARSER_DIR = ROOT / "runs/tools/creddata-parsers"
EXTENSIONS = {".py": "python", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
              ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx",
              ".go": "go", ".java": "java", ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c",
              ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".cs": "csharp",
              ".kt": "kotlin", ".scala": "scala", ".sh": "bash"}
CONFIG_LANGUAGES = {"json", "yaml", "toml"}
LABELS = {"python": "Python", "json": "JSON", "yaml": "YAML", "toml": "TOML", "javascript": "JavaScript",
          "typescript": "TypeScript", "tsx": "TypeScript/TSX", "go": "Go", "java": "Java", "ruby": "Ruby",
          "php": "PHP", "c": "C", "cpp": "C++", "csharp": "C#", "kotlin": "Kotlin", "scala": "Scala", "bash": "Shell"}
STRING_NODES = {"string", "string_literal", "interpreted_string_literal", "raw_string_literal", "encapsed_string", "raw_string"}
FUNCTION_NODES = {"function_declaration", "function_definition", "method_declaration", "method", "singleton_method"}


def language_for(path: str) -> str:
    try:
        return EXTENSIONS[Path(path).suffix.lower()]
    except KeyError:
        raise ValueError("unsupported source language") from None


@lru_cache(maxsize=32)
def parser(language: str):
    if PARSER_DIR.is_dir() and str(PARSER_DIR) not in sys.path:
        sys.path.insert(0, str(PARSER_DIR))
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        raise RuntimeError("install templates/creddata_tasks/parser_requirements.txt into runs/tools/creddata-parsers") from None
    return get_parser(language)


def walk(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def char_index(data: bytes, position: int) -> int:
    return len(data[:position].decode("utf-8"))


def config_data(text: str, language: str):
    if language == "json":
        return json.loads(text)
    if language == "toml":
        return tomllib.loads(text)
    if language == "yaml":
        import yaml
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            raise ValueError("invalid YAML document") from None
    raise ValueError("not a configuration language")


def source_facts(text: str, language: str) -> dict:
    if language in CONFIG_LANGUAGES:
        config_data(text, language)
        return {"syntax_mode": "complete", "functions": []}
    data = text.encode()
    tree = parser(language).parse(data)
    functions = []
    for node in walk(tree.root_node):
        if node.type not in FUNCTION_NODES or node.has_error:
            continue
        name = node.child_by_field_name("name")
        if name is None:
            declarator = node.child_by_field_name("declarator")
            while declarator is not None and declarator.type != "identifier":
                declarator = declarator.child_by_field_name("declarator")
            name = declarator
        if name is None:
            continue
        function = {"name": name.text.decode(), "start": char_index(data, node.start_byte),
                    "end": char_index(data, node.end_byte), "node_type": node.type}
        function["standalone_javascript"] = language == "javascript" and node.type == "function_declaration" and \
            node.parent.type in {"program", "export_statement"} and not node.text.lstrip().startswith(b"async")
        functions.append(function)
    return {"syntax_mode": "fragment" if tree.root_node.has_error else "complete", "functions": functions}


def validate(text: str, language: str, allow_fragment: bool = False):
    if language in CONFIG_LANGUAGES:
        config_data(text, language)
    elif not allow_fragment and parser(language).parse(text.encode()).root_node.has_error:
        raise ValueError("rendered source has syntax errors")


def yaml_regions(text: str):
    import yaml
    from yaml.nodes import MappingNode, ScalarNode, SequenceNode
    try:
        config_data(text, "yaml")
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        raise ValueError("invalid YAML document") from None
    result, seen = [], set()
    def visit(node):
        if node is None or id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, MappingNode):
            keys = set()
            for key, value in node.value:
                if isinstance(key, ScalarNode):
                    if key.value in keys:
                        raise ValueError("duplicate YAML key")
                    keys.add(key.value)
                visit(value)  # keys are not credential values
        elif isinstance(node, SequenceNode):
            for value in node.value:
                visit(value)
        elif isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:str":
            start, end = node.start_mark.index, node.end_mark.index
            if node.style in {"'", '"'}:
                result.append((start + 1, end - 1, "yaml_single" if node.style == "'" else "json"))
            elif node.style is None:
                result.append((start, end, "yaml_plain"))
    visit(root)
    return result


def string_regions(text: str, language: str):
    if language == "yaml":
        return yaml_regions(text)
    if language == "toml":
        config_data(text, language)
    data = text.encode()
    tree = parser(language).parse(data)
    result = []
    for node in walk(tree.root_node):
        if node.type not in STRING_NODES or node.has_error:
            continue
        raw = node.text.decode()
        if len(raw) < 2 or raw[:3] in {'"""', "'''"}:
            continue
        quote = raw[0]
        if quote not in {'"', "'", "`"} or raw[-1] != quote:
            continue
        if quote == "'" and language not in {"javascript", "typescript", "tsx", "ruby", "php", "bash", "toml"}:
            continue
        if quote == "`" and language != "go":
            continue
        if language == "bash" and quote != "'":
            continue  # shell double quotes have expansion/escape semantics unlike ordinary strings
        if any(any(word in child.type for word in ("interpolation", "expansion", "variable_name", "substitution"))
               for child in walk(node) if child is not node):
            continue
        start = char_index(data, node.start_byte)
        if language == "scala" and start and (text[start - 1].isalnum() or text[start - 1] == "_"):
            continue
        kind = "double" if quote == '"' else "single" if quote == "'" else "raw"
        codec = f"native:{language}:{kind}"
        try:
            decode_fragment(raw[1:-1], codec)
        except ValueError:
            continue
        result.append((start + 1, char_index(data, node.end_byte) - 1, codec))
    return sorted(set(result))


def decode_fragment(value: str, codec: str) -> str:
    if codec == "yaml_plain":
        parsed = config_data(value, "yaml")
        if not isinstance(parsed, str):
            raise ValueError("YAML scalar is not a string")
        return parsed
    if codec == "yaml_single":
        parsed = config_data("'" + value + "'", "yaml")
        if not isinstance(parsed, str):
            raise ValueError("YAML quoted scalar is not a string")
        return parsed
    _, language, kind = codec.split(":")
    if kind == "raw" or kind == "single" and language in {"bash", "toml"}:
        return value
    if kind == "single" and language in {"php", "ruby"}:
        return re.sub(r"\\(['\\])", lambda m: m[1], value)
    out, i = [], 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "a": "\a",
               "\\": "\\", '"': '"', "'": "'", "/": "/"}
    while i < len(value):
        c = value[i]
        if c != "\\":
            if language in {"php", "kotlin", "bash"} and kind == "double" and c in "$`":
                raise ValueError("interpolated string")
            if language == "ruby" and value[i:i + 2] == "#{":
                raise ValueError("interpolated string")
            out.append(c); i += 1; continue
        i += 1
        if i == len(value):
            raise ValueError("trailing escape")
        c = value[i]
        if c in escapes:
            out.append(escapes[c]); i += 1
        elif c in "$#`" and language in {"php", "kotlin", "ruby", "bash"}:
            out.append(c); i += 1
        elif c in "xuU":
            count = {"x": 2, "u": 4, "U": 8}[c]
            digits = value[i + 1:i + 1 + count]
            if len(digits) != count or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                raise ValueError("unsupported Unicode escape")
            out.append(chr(int(digits, 16))); i += count + 1
        elif c in "01234567":
            match = re.match(r"[0-7]{1,3}", value[i:])
            out.append(chr(int(match[0], 8))); i += len(match[0])
        elif c in "\r\n" and language in {"javascript", "typescript", "tsx", "c", "cpp", "ruby"}:
            i += 2 if value[i:i + 2] == "\r\n" else 1
        else:
            raise ValueError("unsupported string escape")
    result = "".join(out)
    try:
        return result.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeError:
        raise ValueError("unpaired Unicode surrogate") from None


def encode_fragment(value: str, codec: str) -> str:
    if codec == "yaml_plain":
        return json.dumps(value, ensure_ascii=False)
    if codec == "yaml_single":
        if any(ord(c) < 32 for c in value):
            raise ValueError("control characters cannot be injected into a YAML single-quoted scalar")
        return value.replace("'", "''")
    _, language, kind = codec.split(":")
    if kind == "raw" or kind == "single" and language in {"bash", "toml"}:
        delimiter = "`" if kind == "raw" else "'"
        if delimiter in value or "\x00" in value or language in {"bash", "toml"} and "\n" in value or language == "go" and "\r" in value:
            raise ValueError("value cannot be represented in this raw literal")
        return value
    if kind == "single" and language in {"php", "ruby"}:
        return value.replace("\\", "\\\\").replace("'", "\\'")
    quote = "'" if kind == "single" else '"'
    escapes = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}
    out = []
    for c in value:
        if c == "\\" or c == quote:
            out.append("\\" + c)
        elif c == "$" and language in {"php", "kotlin", "bash"} or c == "`" and language == "bash":
            out.append("\\" + c)
        elif c in escapes:
            out.append(escapes[c])
        elif ord(c) < 32:
            out.append(f"\\{ord(c):03o}" if language in {"c", "cpp", "php"} else f"\\u{ord(c):04x}")
        else:
            out.append(c)
    result = "".join(out)
    return result.replace("#{", "\\#{") if language == "ruby" else result


def rendered_span(codec: str, encoded: str):
    return (1, len(encoded) - 1, "json") if codec == "yaml_plain" else (0, len(encoded), codec)


def javascript_loader(filename: str) -> str:
    return '''const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
exports.loadFunction = function(name, bindings = {}) {
  const source = fs.readFileSync(path.join(__dirname, SOURCE_FILE), 'utf8');
  const functions = JSON.parse(fs.readFileSync(path.join(__dirname, 'snippet_functions.json'), 'utf8'));
  const range = functions[name];
  if (!range) throw new Error('Unknown standalone function: ' + name);
  return new vm.Script('(' + source.slice(range[0], range[1]) + ')')
    .runInNewContext({...bindings});
};
'''.replace("SOURCE_FILE", json.dumps(filename))


def javascript_ranges(text: str) -> dict:
    result = {}
    for f in source_facts(text, "javascript")["functions"]:
        if f["standalone_javascript"]:
            result[f["name"]] = [len(text[:f["start"]].encode("utf-16-le")) // 2,
                                  len(text[:f["end"]].encode("utf-16-le")) // 2]
    return result
