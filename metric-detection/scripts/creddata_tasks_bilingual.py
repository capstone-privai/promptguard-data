"""Reissue task definitions as Korean/English pairs using shared, filename-templated instructions."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

import creddata_tasks as T

INSTRUCTIONS = T.BASE / "templates/creddata_tasks/instructions_v2.json"
README = ("한국어·영어 쌍. 원본·작업군·분할은 유지하고 지시문은 파일명 치환을 지원하는 공통 v2 템플릿으로 재생성했다. "
          "기존 실행 기록은 수정하지 않았다.\n")


def pair_tasks(tasks: list[dict], instructions: dict, languages=("ko", "en")):
    if set(languages) != {"ko", "en"} or len(languages) != 2:
        raise ValueError("both Korean and English instruction variants are required")
    if set(instructions) != {"ko", "en"} or any(set(i) != set(T.FAMILIES) for i in instructions.values()):
        raise ValueError("four shared instruction templates in each language are required")
    paired = []
    for spec in tasks:
        if spec.get("instruction_language"):
            raise ValueError("task definitions are already language variants")
        base_id = spec["task_id"]
        for language in languages:
            variant = {**spec, "task_id": base_id + "__" + language, "task_pair_id": base_id,
                       "instruction_language": language, "instruction": instructions[language][spec["family"]],
                       "instruction_template": instructions[language][spec["family"]]}
            # The new generic instruction lets the agent choose its own target within the same source/family.
            if "target_function" in variant:
                variant["legacy_target_function"] = variant.pop("target_function")
            paired.append(variant)
    return paired


def convert_config(config: dict, instruction_config: dict):
    result = {**config, "version": config["version"] + "-bilingual-v2",
              "tasks_per_family": config["tasks_per_family"] * 2,
              "tasks": pair_tasks(config["tasks"], instruction_config["instructions"]),
              "bilingual": {"languages": ["ko", "en"], "base_tasks": len(config["tasks"]),
                            "instruction_version": instruction_config["version"],
                            "note": "Sources and families preserved; old one-off instructions reissued with shared v2 templates."}}
    result["selection_note"] = "Korean/English variants share their source, split and task_pair_id. No LLM calls."
    if "automatic_generation" in result:
        result["source_selection_generation"] = result.pop("automatic_generation")
    return result


def catalog_files(config: dict, split_dir: Path) -> dict[str, bytes]:
    """Every file of a reissued catalog. The one-line README is the frozen text of the stored catalogs."""
    files = {"tasks.json": T.jb(config), "README.md": README.encode()}
    # A metadata-only temporary file allows the existing pack builder to be reused.
    with tempfile.TemporaryDirectory(prefix="creddata-bilingual-") as temporary:
        path = Path(temporary) / "tasks.json"
        path.write_bytes(files["tasks.json"])
        files.update({"templates/" + k: v for k, v in T.build_pack(path, split_dir).items()})
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path, default=T.DEFAULT_SPLIT)
    parser.add_argument("--instructions", type=Path, default=INSTRUCTIONS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = convert_config(json.loads(args.config.read_text()), json.loads(args.instructions.read_text()))
    T.write_catalog(args.out, catalog_files(config, args.split_dir))
    print(json.dumps({"out": str(args.out), "base_tasks": len(config["tasks"]) // 2,
                      "variants": len(config["tasks"]), "by_family": Counter(t["family"] for t in config["tasks"]),
                      "languages": Counter(t["instruction_language"] for t in config["tasks"]), "llm_calls": 0}))


if __name__ == "__main__":
    main()
