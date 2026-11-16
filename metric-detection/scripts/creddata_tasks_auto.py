"""Expand CredData tasks with parser-based eligibility and shared per-family instructions. No LLM calls.

The default v2 instructions give Korean/English pairs over all supported source languages (rules v2).
instructions_v1.json reproduces the earlier Korean-only Python/JSON catalog (rules v1) unchanged.

Sources may qualify for several families. Select the requested equal count without duplicating
the same file or gold-masked context within a family. All generated source copies stay in runs/.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import tokenize

import creddata_tasks as T
import creddata_languages as L
from creddata_tasks_bilingual import pair_tasks


INSTRUCTIONS = T.BASE / "templates/creddata_tasks/instructions_v2.json"
DEFAULT_OUT = T.ROOT / "runs/creddata-auto-v2-bilingual-r2"
MIN_CONTEXT_CHARS = 80


class Ineligible(ValueError):
    pass


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Ineligible("duplicate_json_key")
        result[key] = value
    return result


def toml_compatible(value):
    if value is None:
        return False
    if isinstance(value, dict):
        return all(toml_compatible(v) for v in value.values())
    if isinstance(value, list):
        return all(toml_compatible(v) for v in value)
    return not isinstance(value, float) or math.isfinite(value)


def testable_functions(tree):
    names = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name == "main" or node.name.startswith("test"):
            continue
        body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                             and isinstance(s.value.value, str))]
        if not body or all(isinstance(s, ast.Pass) or
                           isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis
                           for s in body):
            continue
        if any(isinstance(n, (ast.AsyncFunctionDef, ast.Yield, ast.YieldFrom)) for n in ast.walk(node)):
            continue
        # A window ending inside a factory can parse, while its outer return is missing.
        if any(isinstance(n, ast.FunctionDef) and n is not node for n in ast.walk(node)):
            continue
        names.append(node.name)
    return names


def inspect_item(session: dict, item: dict, spans: list[dict], repo: dict, general_config_refactor: bool = False) -> dict:
    if not spans:
        raise Ineligible("no_source_gold")
    try:
        language = L.language_for(session["meta"]["creddata_file"])
    except ValueError:
        raise Ineligible("unsupported_language")
    text = item["text"]
    try:
        if language == "python":
            parsed = ast.parse(text)
            source_facts = {"syntax_mode": "complete"}
        elif language == "json":
            parsed = json.loads(text, object_pairs_hook=json_object)
            source_facts = {"syntax_mode": "complete"}
        elif language in L.CONFIG_LANGUAGES:
            parsed = L.config_data(text, language)
            source_facts = {"syntax_mode": "complete"}
        else:
            parsed = None
            source_facts = L.source_facts(text, language)
        regions = T.string_regions(text, language)
    except Ineligible:
        raise
    except (ValueError, SyntaxError, tokenize.TokenError):
        raise Ineligible("invalid_" + language + "_syntax") from None
    for span in spans:
        start, end = span["start"], span["end"]
        if not any(start == a and end == b for a, b, _ in regions):
            raise Ineligible("gold_is_not_a_whole_supported_string_literal")
        if language == "json" and text[end + 1:].lstrip().startswith(":"):
            raise Ineligible("gold_in_json_key")
        if span["type"] not in {"PASSWORD", "TOKEN", "SECRET", "ACCESS_KEY"}:
            raise Ineligible("unsupported_gold_type")
    key = f"{session['session_id']}:{item['item_id']}"
    try:
        template, slots, occurrences = T.make_template(text, spans, language, key)
        task = {"language": language, "slots": slots, "occurrences": occurrences, "split": "train",
                "syntax_mode": source_facts["syntax_mode"]}
        T.sample_rendered_values(task, template, "automatic-task-preflight")
    except (ValueError, SyntaxError, tokenize.TokenError):
        raise Ineligible("placeholder_or_render_check_failed") from None
    normalized = " ".join(T.PLACEHOLDER.sub("<SECRET>", template).split())
    if len("".join(normalized.replace("<SECRET>", "").split())) < MIN_CONTEXT_CHARS:
        raise Ineligible("too_little_nonsecret_context")
    families = ["analysis", "documentation"]
    facts = {"language": language, "source_characters": len(text), "secret_slots": len(slots)}
    if language == "python":
        functions = testable_functions(parsed)
        facts["testable_top_level_functions"] = functions
        if functions:
            families.extend(("refactoring", "test_writing"))
    elif language in L.CONFIG_LANGUAGES:
        if not isinstance(parsed, dict) or len(parsed) < 2:
            raise Ineligible("json_is_not_a_multifield_object" if language == "json" else "config_is_not_a_multifield_object")
        facts["top_level_keys"] = list(parsed)
        families.append("test_writing")
        if general_config_refactor or toml_compatible(parsed):
            families.append("refactoring")
    else:
        facts["syntax_mode"] = source_facts["syntax_mode"]
        facts["functions"] = [f["name"] for f in source_facts["functions"]]
        standalone = [f["name"] for f in source_facts["functions"]
                      if f["standalone_javascript"] and f["name"] != "main" and not f["name"].startswith("test")]
        if source_facts["syntax_mode"] == "complete" and source_facts["functions"]:
            families.append("refactoring")
        if source_facts["syntax_mode"] == "complete" and standalone:
            facts["testable_javascript_functions"] = standalone
            families.append("test_writing")
    return {"source_session_id": session["session_id"], "source_item_id": item["item_id"],
            "source_repo_id": repo["repo_id"], "component_id": repo["component_id"],
            "source_item_sha256": T.sha(text.encode()), "context_sha256": T.sha(normalized.encode()),
            "eligible_families": families, "facts": facts}


def discover(split_dir: Path, allowed_languages=None, general_config_refactor: bool = False):
    manifest = json.loads((split_dir / "manifest.json").read_text())
    inputs = {name: T.ROOT / record["path"] for name, record in manifest["inputs"].items()}
    for name, path in inputs.items():
        if T.sha(path.read_bytes()) != manifest["inputs"][name]["sha256"]:
            raise ValueError("source conversion changed after partition freeze")
    train = set((split_dir / "train.txt").read_text().splitlines())
    repos = {r["group_id"]: r for r in T.rows(split_dir / "repositories.jsonl")}
    gold = defaultdict(list)
    for row in T.rows(inputs["gold"]):
        if row["session_id"] in train:
            gold[(row["session_id"], row["item_id"])].append(row["span"])
    candidates, rejected, scanned = [], Counter(), Counter()
    for session in T.rows(inputs["sessions"]):
        if session["session_id"] not in train:
            continue
        for item in session["items"]:
            scanned["train_items"] += 1
            spans = gold[(session["session_id"], item["item_id"])]
            if not spans:
                rejected["no_source_gold"] += 1
                continue
            scanned["gold_bearing_train_items"] += 1
            repo = repos[session["meta"]["group_id"]]
            if repo["split"] != "train":
                raise ValueError("session/repository split mismatch")
            try:
                if allowed_languages is not None:
                    try:
                        language = L.language_for(session["meta"]["creddata_file"])
                    except ValueError:
                        raise Ineligible("unsupported_language") from None
                    if language not in allowed_languages:
                        raise Ineligible("unsupported_language")
                candidates.append(inspect_item(session, item, spans, repo, general_config_refactor))
            except Ineligible as reason:
                rejected[str(reason)] += 1
    return candidates, {"scanned": dict(scanned), "excluded_items": dict(sorted(rejected.items())),
                        "eligible_items": len(candidates),
                        "eligible_source_files": len({c["source_session_id"] for c in candidates}),
                        "eligible_repositories": len({c["source_repo_id"] for c in candidates}),
                        "eligible_by_language": dict(Counter(c["facts"]["language"] for c in candidates)),
                        "eligible_by_family": {f: sum(f in c["eligible_families"] for c in candidates) for f in T.FAMILIES}}


def select_tasks(candidates: list[dict], per_family: int, seed: str, max_per_repo: int, instructions: dict,
                 balance_languages: bool = False, method: str = "parser_rules_v1"):
    if per_family <= 0 or max_per_repo <= 0:
        raise ValueError("task count and repository cap must be positive")
    if set(instructions) != set(T.FAMILIES) or any(not isinstance(v, str) or not v.strip() for v in instructions.values()):
        raise ValueError("exactly four nonempty shared instructions are required")
    pools = {f: [c for c in candidates if f in c["eligible_families"]] for f in T.FAMILIES}
    family_order = sorted(T.FAMILIES, key=lambda f: (len({c["context_sha256"] for c in pools[f]}), T.FAMILIES.index(f)))
    global_context_uses, chosen = Counter(), {}
    for family in family_order:
        used_files, used_contexts, repo_counts, selected = set(), set(), Counter(), []
        language_counts = Counter()
        while len(selected) < per_family:
            available = [c for c in pools[family]
                         if c["source_session_id"] not in used_files and c["context_sha256"] not in used_contexts
                         and repo_counts[c["source_repo_id"]] < max_per_repo]
            if not available:
                raise ValueError(f"{family}: only {len(selected)} tasks under unique-file/context and repository-cap rules; "
                                 f"requested {per_family}. Reduce --per-family; no duplicates will be added to fill the quota.")
            def rank(c):
                identity = f"{seed}:{family}:{c['source_session_id']}:{c['source_item_id']}"
                return (global_context_uses[c["context_sha256"]],
                        language_counts[c["facts"]["language"]] if balance_languages else 0,
                        repo_counts[c["source_repo_id"]], T.sha(identity.encode()))
            candidate = min(available, key=rank)
            selected.append(candidate)
            used_files.add(candidate["source_session_id"])
            used_contexts.add(candidate["context_sha256"])
            repo_counts[candidate["source_repo_id"]] += 1
            global_context_uses[candidate["context_sha256"]] += 1
            language_counts[candidate["facts"]["language"]] += 1
        chosen[family] = selected
    tasks = []
    for family in T.FAMILIES:
        for n, candidate in enumerate(chosen[family], 1):
            tasks.append({"task_id": f"{family}-auto-{n:04}", "family": family,
                          "source_session_id": candidate["source_session_id"],
                          "source_item_id": candidate["source_item_id"], "instruction": instructions[family],
                          "eligibility": {"method": method, "context_sha256": candidate["context_sha256"],
                                          "eligible_families": candidate["eligible_families"], "facts": candidate["facts"]}})
    return tasks


def generate(split_dir: Path, instruction_path: Path, per_family: int, seed: str, max_per_repo: int):
    instruction_config = json.loads(instruction_path.read_text())
    bilingual = "ko" in instruction_config["instructions"]
    candidates, profile = discover(split_dir, None if bilingual else {"python", "json"}, bilingual)
    base_instructions = instruction_config["instructions"]["ko"] if bilingual else instruction_config["instructions"]
    base_tasks = select_tasks(candidates, per_family, seed, max_per_repo, base_instructions, bilingual,
                              "parser_rules_v2_multilanguage" if bilingual else "parser_rules_v1")
    tasks = pair_tasks(base_tasks, instruction_config["instructions"]) if bilingual else base_tasks
    # The v1 wording is frozen in runs/creddata-auto-v1; r2 only corrects the metadata of the unrun v2 catalog.
    config = {"version": "creddata-auto-v2-bilingual-r2" if bilingual else "creddata-auto-v1", "split": "train",
              "tasks_per_family": per_family * (2 if bilingual else 1),
              "selection_note": "Parser eligibility plus deterministic sampling. Four shared instruction templates in each "
                                "of two instruction languages (eight in total); no LLM generation." if bilingual else
                                "Parser eligibility plus deterministic sampling. Four shared instructions; no LLM generation.",
              "automatic_generation": {"seed": seed, "max_per_repository_per_family": max_per_repo,
                                       "minimum_nonsecret_context_characters": MIN_CONTEXT_CHARS,
                                       "instruction_version": instruction_config["version"],
                                       "instruction_sha256": T.sha(instruction_path.read_bytes()),
                                       "split_manifest_sha256": T.sha((split_dir / "manifest.json").read_bytes())},
              "tasks": tasks}
    if bilingual:
        config["bilingual"] = {"languages": ["ko", "en"], "base_tasks": len(base_tasks),
                               "tasks_per_family_per_language": per_family}
    stats = {**profile, "selected_tasks": len(tasks), "selected_by_family": dict(Counter(t["family"] for t in tasks)),
             "selected_source_files": len({t["source_session_id"] for t in tasks}),
             "selected_repositories": len({t["source_session_id"].split("-")[1] for t in tasks}),
             "distinct_instruction_count": len({t["instruction"] for t in tasks}), "llm_calls": 0,
             "checks": {"all_train_sources": True, "same_count_per_family": True,
                        "one_instruction_per_family": True, "no_duplicate_file_or_context_within_family": True},
             "limitations": ["Eligibility is structural, not a semantic guarantee that a task is worthwhile.",
                             "Only supported string literals and configuration scalars are considered." if bilingual else
                             "Only Python and JSON with supported whole-string gold slots are considered.",
                             "Test writing on JSON means configuration structure/type tests, not testing an original application.",
                             "Known gold only; this pilot does not establish exhaustive secret annotation."]}
    if bilingual:
        stats.update(base_tasks=len(base_tasks), selected_by_instruction_language=dict(Counter(t["instruction_language"] for t in tasks)),
                     selected_by_source_language=dict(Counter(t["eligibility"]["facts"]["language"] for t in base_tasks)))
        stats["checks"].pop("one_instruction_per_family")
        stats["checks"].pop("no_duplicate_file_or_context_within_family")
        stats["checks"].update(one_instruction_template_per_family_and_language=True,
                               no_duplicate_base_file_or_context_within_family=True,
                               paired_languages_share_source_and_split=True)
    return config, candidates, stats


def write_expansion(out: Path, config: dict, candidates: list[dict], stats: dict, split_dir: Path):
    # Build everything before committing the output directory, so a bad candidate cannot leave a partial pack.
    with tempfile_config(config) as config_path:
        templates = T.build_pack(config_path, split_dir)
    files = {"tasks.json": T.jb(config), "selection.json": T.jb(stats),
             "eligibility.jsonl": b"".join((json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n").encode()
                                            for c in sorted(candidates, key=lambda c: (c["source_session_id"], c["source_item_id"]))) }
    files.update({"templates/" + name: value for name, value in templates.items()})
    files["README.md"] = readme(config, stats).encode()
    T.write_catalog(out, files)


def readme(config: dict, stats: dict) -> str:
    counts = f"작업군별 {config['tasks_per_family']}개, 총 {len(config['tasks'])}개다. "
    selected = f"선택한 원본 파일은 {stats['selected_source_files']}개, 저장소는 {stats['selected_repositories']}개다. "
    files = ("tasks.json은 지시문과 원본 매핑, eligibility.jsonl은 후보별 판정, selection.json은 후보·제외·선택 통계다. "
             "templates/에는 placeholder 환경이 있다. 실제 에이전트 실행과 사후 궤적 증강은 하지 않았다.\n\n")
    limits = ("원본 애플리케이션의 단위 테스트가 아니다. 구조 규칙만으로 의미상 좋은 과제나 라벨 완전성을 보장하지 않는다.\n")
    if "bilingual" not in config:  # frozen wording of the Korean-only Python/JSON catalog
        return ("# 공통 지시문 기반 자동 작업 확장\n\n" + counts +
                "지시문은 작업군별 공통 문구 4개이며 분류·지시문 작성용 LLM 호출은 없다.\n\n"
                "원본별 수행 가능한 작업군을 여러 개 판정하고 그 후보에서 같은 수를 선택한다. "
                "Python은 AST, JSON은 파서로 구조를 확인한다. 구문이 불완전하거나 지원하지 않는 비밀값 자리는 제외한다.\n\n"
                + selected + "한 작업군 안에서 같은 파일·동일한 비밀값 제거 문맥을 중복 사용하지 않으며, "
                "서로 다른 작업군이 같은 원본을 사용하는 경우는 있다. 모든 원본은 고정 train 분할이다.\n\n" + files +
                "테스트 작성용 JSON 과제는 설정의 구조·자료형 테스트를 뜻한다. " + limits)
    return ("# 공통 지시문 기반 자동 작업 확장 (한국어·영어 쌍)\n\n" + counts +
            f"기본 작업 {config['bilingual']['base_tasks']}개를 한국어·영어 지시문 쌍으로 발급했다. "
            "지시문은 작업군·지시문 언어별 공통 템플릿 8개이며 파일명·코드 언어를 치환한다. "
            "분류·지시문 작성용 LLM 호출은 없다.\n\n"
            "원본별 수행 가능한 작업군을 여러 개 판정하고 그 후보에서 같은 수를 선택한다. "
            "Python은 AST, 설정은 해당 파서, 다른 코드는 Tree-sitter로 구조를 확인한다. "
            "일부 코드 조각은 분석·문서 작성에만 사용하고, 지원하지 않는 비밀값 자리는 제외한다.\n\n"
            + selected + "한 작업군·지시문 언어 안에서 같은 파일·동일한 비밀값 제거 문맥을 중복 사용하지 않으며, "
            "서로 다른 작업군이 같은 원본을 사용하는 경우는 있다. 모든 원본은 고정 train 분할이다.\n\n" + files +
            "한영 버전은 task_pair_id로 묶어 같은 원본·분할을 공유하고, 같은 seed로 만들면 코드와 주입값도 같다. "
            "설정 파일의 테스트 과제는 설정의 구조·자료형 테스트를 뜻한다. " + limits)


class tempfile_config:
    """A temporary metadata-only config; source text and values never enter this file."""
    def __init__(self, config):
        self.config = config

    def __enter__(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory(prefix="creddata-auto-config-")
        self.path = Path(self.temporary.name) / "tasks.json"
        self.path.write_bytes(T.jb(self.config))
        return self.path

    def __exit__(self, *args):
        self.temporary.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-dir", type=Path, default=T.DEFAULT_SPLIT)
    parser.add_argument("--instructions", type=Path, default=INSTRUCTIONS)
    parser.add_argument("--per-family", type=int, default=25)
    parser.add_argument("--seed", default="creddata-auto-v2")
    parser.add_argument("--max-per-repo", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    config, candidates, stats = generate(args.split_dir, args.instructions, args.per_family, args.seed, args.max_per_repo)
    write_expansion(args.out, config, candidates, stats, args.split_dir)
    print(json.dumps({"out": str(args.out), **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
