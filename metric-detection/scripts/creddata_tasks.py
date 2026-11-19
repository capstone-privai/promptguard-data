"""Prepare balanced CredData-derived tasks and render secrets from value-free placeholders.

This is a trajectory collection pilot, not a task-success benchmark. Sources are licensed
CredData excerpts: all generated copies stay under ignored runs/, never in the tracked templates.
Known source gold is preserved as provenance, not asserted to be exhaustive annotation.
"""
from __future__ import annotations

import argparse
import ast
import base64
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import tokenize

import value_gen
import creddata_languages as L
from label_rules import is_common, judge_occurrence


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "metric-detection"
DEFAULT_CONFIG = BASE / "templates/creddata_tasks/pilot_v2_bilingual.json"
DEFAULT_SPLIT = BASE / "source_splits/creddata-v1"
DEFAULT_PACK = ROOT / "runs/creddata-pilot-v2-bilingual/templates"
FAMILIES = ("analysis", "documentation", "refactoring", "test_writing")
NAMES = dict(zip(FAMILIES, ("코드 분석", "문서 작성", "리팩터링", "테스트 코드 작성")))
PLACEHOLDER = re.compile(r"\{\{secret:([a-zA-Z0-9_]+)\}\}")
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)
PY_QUOTE = re.compile(r"(?i)^([rubf]*)(\"\"\"|'''|\"|')")

COMMON = """현재 폴더는 한 원본 파일의 일부를 추출한 개발 작업 환경이다.
먼저 subject 파일을 읽고 요청한 작업을 수행해줘. 원본 전체 프로젝트가 있다고 가정하지 말고,
확인되지 않는 내용은 명시해줘. 필요한 파일 읽기, 검색, 로컬 명령 실행과 편집을 사용해도 돼.
외부 서비스에 연결하거나 원본 모듈 전체를 실행할 필요는 없어. 테스트에서는 외부 의존성을 목으로 대체해줘.
작업 폴더 밖의 생성 정보나 다른 작업은 참조하지 말아줘.
"""
COMMON_EN = """This workspace contains an excerpt from one source file.
Read the subject file first and perform the requested development task. Do not assume the full original project
is available. State what cannot be verified. You may read, search, edit files, and run local commands.
Do not connect to external services or execute the entire original module. Mock external dependencies in tests.
Do not consult generation metadata or other tasks outside this workspace.
"""

LOADER = '''"""Load only a chosen function from the excerpt; do not import its external services."""
import ast
import copy
import json
from hashlib import sha1
from pathlib import Path


def load_function(name, bindings=None):
    path = Path(__file__).with_name("subject.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise ValueError("expected one top-level function: " + name)
    node = copy.deepcopy(matches[0])
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    namespace = {"json": json, "sha1": sha1}
    namespace.update(bindings or {})
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jb(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_tree(out: Path, files: dict[str, bytes]):
    """Write once, accepting identical reruns but never silently replacing generated work."""
    if out.exists():
        existing = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()}
        if existing != files:
            raise ValueError(f"output already exists with different content: {out}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".creddata-tasks-", dir=out.parent))
    try:
        for name, content in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        temporary.rename(out)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def write_catalog(out: Path, files: dict[str, bytes]):
    """Freeze a generated catalog. instances/ below it holds mutable agent workspaces and is not compared."""
    if not out.exists():
        return write_tree(out, files)
    existing = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*")
                if p.is_file() and p.relative_to(out).parts[0] != "instances"}
    if existing != files:
        raise ValueError(f"generated catalog already exists with different content: {out}")


def string_regions(text: str, language: str) -> list[tuple[int, int, str]]:
    if language not in {"python", "json"}:
        return L.string_regions(text, language)
    if language == "json":
        json.loads(text)
        return [(m.start() + 1, m.end() - 1, "json") for m in JSON_STRING.finditer(text)]
    ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line)
    regions = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.STRING:
            continue
        quote = PY_QUOTE.match(token.string)
        if not quote or any(c in quote[1].lower() for c in "rbf") or len(quote[2]) != 1:
            continue  # raw/bytes/f/triple strings need a separate rendering contract
        start = offsets[token.start[0] - 1] + token.start[1] + len(quote[0])
        end = offsets[token.end[0] - 1] + token.end[1] - 1
        regions.append((start, end, "python_single" if quote[2] == "'" else "python_double"))
    return regions


def decode_fragment(value: str, codec: str) -> str:
    if codec.startswith(("native:", "yaml_")):
        return L.decode_fragment(value, codec)
    if codec == "json":
        return json.loads('"' + value + '"')
    quote = "'" if codec == "python_single" else '"'
    return ast.literal_eval(quote + value + quote)


def encode_fragment(value: str, codec: str) -> str:
    if not isinstance(value, str):
        raise ValueError("secret values must be strings")
    if codec.startswith(("native:", "yaml_")):
        return L.encode_fragment(value, codec)
    if codec == "json":
        return json.dumps(value, ensure_ascii=False)[1:-1]
    quote = "'" if codec == "python_single" else '"'
    control = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}
    return "".join("\\\\" if c == "\\" else "\\" + quote if c == quote else control[c]
                   if c in control else f"\\x{ord(c):02x}" if ord(c) < 32 else c for c in value)


def kind_hint(text: str, start: int, gold_type: str) -> str:
    prefix = text[max(0, start - 80):start].lower()
    if re.search(r"aws_access_key_id\s*=\s*['\"]$", prefix):
        return "aws_access_key_id"
    if re.search(r"aws_secret_access_key\s*=\s*['\"]$", prefix):
        return "aws_secret_access_key"
    if re.search(r'"auth"\s*:\s*"$', prefix):
        return "basic_auth"
    return {"PASSWORD": "password_random", "TOKEN": "generic_token", "SECRET": "generic_secret",
            "ACCESS_KEY": "aws_access_key_id"}[gold_type]


def make_template(text: str, spans: list[dict], language: str, source_key: str) -> tuple[str, dict, list]:
    regions = string_regions(text, language)
    slots, occurrences, names, pieces, cursor, template_cursor = {}, [], {}, [], 0, 0
    for span in sorted(spans, key=lambda r: (r["start"], r["end"])):
        start, end = span["start"], span["end"]
        if not 0 <= cursor <= start < end <= len(text):
            raise ValueError("invalid or overlapping source gold spans")
        containers = [(a, b, codec) for a, b, codec in regions if a <= start < end <= b]
        if len(containers) != 1:
            raise ValueError("source gold needs an unsupported literal/encoding context")
        _, _, codec = containers[0]
        original = decode_fragment(text[start:end], codec)
        kind = kind_hint(text, start, span["type"])
        identity = (original, kind)
        if identity not in names:
            names[identity] = "s_" + sha(source_key.encode())[:10] + f"_{len(names) + 1:02}"
        name = names[identity]
        slots.setdefault(name, {"type": span["type"], "generator_kind": kind,
                                "source_value_sha256": sha(original.encode())})
        before = text[cursor:start]
        marker = "{{secret:" + name + "}}"
        pieces.extend((before, marker))
        template_cursor += len(before)
        occurrences.append({"secret_id": name, "codec": codec, "start": template_cursor,
                            "end": template_cursor + len(marker), "source_start": start, "source_end": end})
        template_cursor += len(marker)
        cursor = end
    pieces.append(text[cursor:])
    template = "".join(pieces)
    if len(list(PLACEHOLDER.finditer(template))) != len(occurrences):
        raise ValueError("unaccounted placeholder syntax in source")
    for original, _ in names:
        if len(original) >= 12 and original in template:
            raise ValueError("untemplated recurrence of a known source value")
    if not slots:
        raise ValueError("pilot source has no supported gold slots")
    return template, slots, occurrences


def build_pack(config_path: Path, split_dir: Path) -> dict[str, bytes]:
    config = json.loads(config_path.read_text())
    definitions = config["tasks"]
    count = Counter(t["family"] for t in definitions)
    expected = {family: config["tasks_per_family"] for family in FAMILIES}
    if dict(count) != expected or len({t["task_id"] for t in definitions}) != len(definitions):
        raise ValueError("task families must have equal declared counts and unique task IDs")
    manifest = json.loads((split_dir / "manifest.json").read_text())
    split = config["split"]
    if split != "train":
        raise ValueError("this exploratory pilot only accepts train sources")
    members = set((split_dir / f"{split}.txt").read_text().splitlines())
    requested = {t["source_session_id"] for t in definitions}
    if not requested <= members:
        raise ValueError("task source is outside the frozen train partition")
    source_paths = {name: ROOT / record["path"] for name, record in manifest["inputs"].items()}
    for name, path in source_paths.items():
        if sha(path.read_bytes()) != manifest["inputs"][name]["sha256"]:
            raise ValueError("source conversion changed after partition freeze")
    source = {s["session_id"]: s for s in rows(source_paths["sessions"]) if s["session_id"] in requested}
    gold = defaultdict(list)
    for row in rows(source_paths["gold"]):
        if row["session_id"] in requested:
            gold[(row["session_id"], row["item_id"])].append(row["span"])
    repository = {r["group_id"]: r for r in rows(split_dir / "repositories.jsonl")}
    files, summaries = {}, []
    for spec in definitions:
        task_id = spec["task_id"]
        session = source[spec["source_session_id"]]
        matches = [i for i in session["items"] if i["item_id"] == spec["source_item_id"]]
        if len(matches) != 1:
            raise ValueError("missing or duplicate source item")
        item = matches[0]
        language = L.language_for(session["meta"]["creddata_file"])
        key = f"{session['session_id']}:{item['item_id']}"
        template, slots, occurrences = make_template(item["text"], gold[(session["session_id"], item["item_id"])],
                                                    language, key)
        if spec.get("target_function"):
            functions = [n for n in ast.parse(item["text"]).body
                         if isinstance(n, ast.FunctionDef) and n.name == spec["target_function"]]
            if len(functions) != 1:
                raise ValueError("test target is not one complete top-level function")
        group = repository[session["meta"]["group_id"]]
        filename = "subject" + Path(session["meta"]["creddata_file"]).suffix.lower()
        instruction_language = spec.get("instruction_language", "ko")
        if instruction_language not in {"ko", "en"}:
            raise ValueError("unsupported instruction language")
        instruction = spec["instruction"]
        if "instruction_template" in spec:
            instruction = spec["instruction_template"].format(source_file=filename, source_language=L.LABELS[language])
        prompt = (COMMON_EN if instruction_language == "en" else COMMON) + "\n" + instruction + "\n"
        task = {**spec, "split": split, "language": language, "source_filename": filename,
                "source_repo_id": group["repo_id"], "component_id": group["component_id"],
                "source_file": session["meta"]["creddata_file"],
                "source_line_range": session["meta"]["item_lines"][item["item_id"]],
                "source_item_sha256": sha(item["text"].encode()), "source_license": session["meta"]["license"],
                "slots": slots, "occurrences": occurrences, "success_grading": None,
                "annotation_scope": "known source gold only; completeness not certified"}
        if "instruction_language" in spec:
            task.update(instruction_language=instruction_language, source_language=language,
                        rendered_instruction=instruction)
        if language not in {"python", "json"}:
            task["syntax_mode"] = L.source_facts(item["text"], language)["syntax_mode"]
            if task["syntax_mode"] == "fragment" and spec["family"] not in {"analysis", "documentation"}:
                raise ValueError("incomplete source is only eligible for analysis/documentation")
        files[f"{task_id}/task.json"] = jb(task)
        files[f"{task_id}/workspace/{filename}"] = template.encode()
        files[f"{task_id}/workspace/request.md"] = prompt.encode()
        readme = (
            f"# {NAMES[spec['family']]} 작업\n\nsubject 파일은 원본 파일의 "
            f"{task['source_line_range'][0]}–{task['source_line_range'][1]}줄을 추출한 조각이다.\n"
            "전체 프로젝트가 아니며 외부 의존성이 생략되어 있을 수 있다. request.md의 작업을 수행한다.\n"
            + ("snippet_loader.py는 모듈을 import하지 않고 선택한 함수만 로드한다. "
               "외부 이름은 bindings로 전달할 수 있고 원본 데코레이터는 적용하지 않는다.\n" if language == "python" else "")
        )
        if instruction_language == "en":
            readme = (f"# {spec['family']} task\n\nThe subject file is an excerpt of source lines "
                      f"{task['source_line_range'][0]}–{task['source_line_range'][1]}.\n"
                      "It is not the full project. Dependencies may be omitted. Follow request.md.\n"
                      + ("snippet_loader.py loads one function without importing the original module. "
                         "Pass external names through bindings; original decorators are not executed.\n" if language == "python" else ""))
        files[f"{task_id}/workspace/README.md"] = readme.encode()
        if language == "python":
            files[f"{task_id}/workspace/snippet_loader.py"] = LOADER.encode()
        if language == "javascript":
            files[f"{task_id}/workspace/snippet_loader.cjs"] = L.javascript_loader(filename).encode()
            files[f"{task_id}/workspace/snippet_functions.json"] = jb(L.javascript_ranges(template))
        summaries.append({"task_id": task_id, "family": spec["family"], "source_session_id": session["session_id"],
                          "source_item_id": item["item_id"], "source_repo_id": group["repo_id"],
                          "slots": len(slots), "source_gold_occurrences": len(occurrences)})
    manifest = {"version": config["version"], "split": split, "counts": count,
        "source_sessions": len(requested), "source_repositories": len({r["source_repo_id"] for r in summaries}),
        "config_sha256": sha(config_path.read_bytes()), "split_manifest_sha256": sha((split_dir / "manifest.json").read_bytes()),
        "tasks": summaries, "success_grading": None, "ready_for_training_export": False}
    if any("instruction_language" in spec for spec in definitions):
        manifest["instruction_languages"] = dict(Counter(spec["instruction_language"] for spec in definitions))
        manifest["task_pairs"] = len({spec["task_pair_id"] for spec in definitions})
        for summary, spec in zip(summaries, definitions):
            summary.update(instruction_language=spec["instruction_language"], task_pair_id=spec["task_pair_id"])
    files["manifest.json"] = jb(manifest)
    return files


def generate_values(task: dict, seed: str) -> dict[str, str]:
    values = {}
    for name, slot in task["slots"].items():
        draw = value_gen.Draw(f"creddata-pilot-v1:{task['split']}:{seed}:{name}")
        kind = slot["generator_kind"]
        if kind == "basic_auth":
            values[name] = base64.b64encode(("pilot:" + value_gen.password_random(draw)).encode()).decode()
        else:
            values[name] = value_gen.SECRET_KINDS[kind][1](draw)
    return values


def render(task: dict, template: str, values: dict[str, str]) -> tuple[str, list[dict]]:
    if set(values) != set(task["slots"]):
        raise ValueError("value mapping must contain exactly this task's secret IDs")
    pieces, cursor, length, annotations = [], 0, 0, []
    for occurrence in task["occurrences"]:
        start, end, name = occurrence["start"], occurrence["end"], occurrence["secret_id"]
        expected = "{{secret:" + name + "}}"
        if not cursor <= start < end <= len(template) or template[start:end] != expected:
            raise ValueError("template placeholder offsets changed")
        before = template[cursor:start]
        encoded = encode_fragment(values[name], occurrence["codec"])
        pieces.extend((before, encoded))
        length += len(before)
        view_start, view_end, view_codec = L.rendered_span(occurrence["codec"], encoded)
        annotations.append({"secret_id": name, "start": length + view_start, "end": length + view_end,
                            "codec": view_codec, "source_type": task["slots"][name]["type"]})
        length += len(encoded)
        cursor = end
    pieces.append(template[cursor:])
    text = "".join(pieces)
    if task["language"] == "json":
        json.loads(text)
    elif task["language"] == "python":
        ast.parse(text)
    else:
        L.validate(text, task["language"], allow_fragment=task.get("syntax_mode") == "fragment")
    for annotation in annotations:
        encoded = text[annotation["start"]:annotation["end"]]
        if decode_fragment(encoded, annotation["codec"]) != values[annotation["secret_id"]]:
            raise ValueError("rendered span does not decode to the requested value")
    return text, annotations


def sample_rendered_values(task: dict, template: str, seed: str):
    """Keep automatic draws compatible with the project's source-position labeling rules."""
    for attempt in range(16):
        draw_seed = seed if attempt == 0 else f"{seed}:source-rule-redraw:{attempt}"
        values = generate_values(task, draw_seed)
        text, annotations = render(task, template, values)
        if all(judge_occurrence(text, a["start"], a["end"], is_common(values[a["secret_id"]]))[0]
               for a in annotations):
            return values, text, annotations, attempt
    raise ValueError("could not draw values accepted by source-position labeling rules after 16 attempts")


def instantiate(pack: Path, task_id: str, seed: str, overrides: dict | None = None) -> dict[str, bytes]:
    task_dir = pack / task_id
    task = json.loads((task_dir / "task.json").read_text())
    if task.get("source_scope") == "whole_file":  # catalog v3: whole files, category values
        import creddata_fullfile
        return creddata_fullfile.instantiate(pack, task_id, seed, overrides)
    template = (task_dir / "workspace" / task["source_filename"]).read_text()
    if overrides is None:
        values, text, annotations, redraws = sample_rendered_values(task, template, seed)
    else:
        values = overrides
        text, annotations = render(task, template, values)
        redraws = 0
    files = {"workspace/" + p.name: p.read_bytes() for p in (task_dir / "workspace").iterdir() if p.is_file()}
    files["workspace/" + task["source_filename"]] = text.encode()
    if task["language"] == "javascript":
        files["workspace/snippet_functions.json"] = jb(L.javascript_ranges(text))
    files["task.json"] = jb(task)
    registry = {"task_id": task_id, "seed": seed, "split": task["split"],
        "values": values, "source_file": task["source_filename"], "source_annotations": annotations,
        "source_sha256": sha(text.encode()), "annotation_scope": task["annotation_scope"]}
    if redraws:
        registry["source_rule_redraws"] = redraws
    files["private/registry.json"] = jb(registry)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    build.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT)
    build.add_argument("--out", type=Path, default=DEFAULT_PACK)
    materialize = sub.add_parser("instantiate")
    materialize.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    materialize.add_argument("--task", required=True, help="task ID or all")
    materialize.add_argument("--seed", default="pilot-01")
    materialize.add_argument("--values", type=Path, help="JSON mapping from secret IDs to arbitrary string values; one task")
    materialize.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        files = build_pack(args.config, args.split_dir)
        write_tree(args.out, files)
        print(json.dumps({"out": str(args.out), **json.loads(files["manifest.json"])}, ensure_ascii=False, indent=2))
    else:
        ids = [t["task_id"] for t in json.loads((args.pack / "manifest.json").read_text())["tasks"]] if args.task == "all" else [args.task]
        if args.values and len(ids) != 1:
            parser.error("--values requires one task")
        overrides = json.loads(args.values.read_text()) if args.values else None
        for task_id in ids:
            files = instantiate(args.pack, task_id, args.seed, overrides)
            out = args.out / task_id if args.task == "all" else args.out
            write_tree(out, files)
        print(json.dumps({"out": str(args.out), "tasks": len(ids), "seed": args.seed}))


if __name__ == "__main__":
    main()
