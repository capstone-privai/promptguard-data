"""Summarize an ML export for the model side and check that a rebuild gives the same bytes ("0단계" handoff).

ml_train_export.py writes train and val to metric-detection/ml_handoff/ and test and test_ood to
data_test/ and data_answer/ (sessions_mleval_*). None of it is in git: the values are fake credentials in real
formats and privesc holds SSH keys, which push protection blocks. The build is byte for byte reproducible, so this
script records what a run should give in a committed file (counts and the sha256 of every data file) and checks a
fresh run against it.

Run from the repository root, after ml_train_export.py:
  python metric-detection/scripts/ml_train_handoff.py write   # record: templates/ml_train/handoff_step0.json, .md
  python metric-detection/scripts/ml_train_handoff.py check   # compare with the recorded file; exit 1 if different
Both write ml_handoff/README.md (Korean): this run's counts and known limits, then the export's file guide.
The export manifests (manifest.json, manifest_mleval.json) hold the sha256 of the code that wrote them, so a later
code change moves their hash without changing the data; check compares the data files only and reports the rest.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import ml_train_export as E

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
HANDOFF = ROOT / "ml_handoff"
RECORD = ROOT / "templates" / "ml_train" / "handoff_step0.json"
RECORD_MD = RECORD.with_suffix(".md")  # a committed copy of the README, readable without a build
SPLITS = ("train", "val", "test", "test_ood")
SOURCES = ("hand", "llm", "privesc")
SOURCE_KO = {"hand": "손 템플릿", "llm": "LLM 템플릿", "privesc": "privesc"}
TYPES = ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY")
CONTEXTS = ("config", "command_output", "log", "stacktrace", "diff", "http", "source_code", "natural_language",
            "document", "key_file", "jupyter_output", "terraform_output")
MISSING = ["templates/ml_train/raw/v1_local.jsonl (Twilio SID가 든 LLM 템플릿, git 제외라 이 저장소에 없음)"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_of(meta: dict) -> str:
    group = meta["group_id"]
    return "hand" if group.startswith("hand-") else "privesc" if group.startswith("privesc-") else "llm"


def data_files() -> dict[str, tuple[Path, Path, Path]]:
    """(sessions, gold, labels) per output, keyed by split for the handoff and NAME/split for evaluation."""
    files = {split: tuple(HANDOFF / f"{kind}_{split}.jsonl" for kind in ("sessions", "gold", "labels"))
             for split in E.TRAIN_SIDE}
    for path in sorted((ROOT / "data_test").glob(f"sessions_{E.EVAL_PREFIX}_*.jsonl")):
        stem = path.name[len(f"sessions_{E.EVAL_PREFIX}_"):-len(".jsonl")]
        name, split = (stem[:-len("_test_ood")], "test_ood") if stem.endswith("_test_ood") else stem.rsplit("_", 1)
        files[f"{name}/{split}"] = tuple(E.eval_paths(ROOT, name, split))
    return files


def summarize() -> dict:
    files = data_files()
    sessions_n, gold_n, neg_n, mask_n, items_n = (Counter() for _ in range(5))
    gold_type = defaultdict(Counter)
    cell = defaultdict(Counter)        # (side) -> (context, primary type) sessions, LLM only
    bundle = defaultdict(Counter)      # split -> LLM card bundle letter
    scenario = defaultdict(Counter)    # split -> privesc scenario sessions
    scenario_gold = defaultdict(Counter)
    moved = Counter()
    for key, (s_path, g_path, l_path) in files.items():
        split = key.split("/")[-1]
        src_of = {}
        for s in read_jsonl(s_path):
            meta, src = s["meta"], source_of(s["meta"])
            src_of[s["session_id"]] = src
            sessions_n[split, src] += 1
            items_n[split, src] += len(s["items"])
            if meta.get("split_moved_from"):
                moved[f"{meta['split_moved_from']}->{split}"] += 1
            if src == "llm":
                card = meta["card"]
                cell[split][card["context"], card["primary_type"]] += 1
                bundle[split][meta["group_id"][0]] += 1
            if src == "privesc":
                scenario[split][meta["scenario"]] += 1
        for g in read_jsonl(g_path):
            src = src_of[g["session_id"]]
            gold_n[split, src] += 1
            gold_type[split, src][g["span"]["type"]] += 1
            if src == "privesc":
                scenario_gold[split][g["session_id"].split("-")[2]] += 1
        for r in read_jsonl(l_path):
            (mask_n if r["kind"] == "mask" else neg_n)[split, src_of[r["session_id"]]] += 1

    def table(counter):
        return {split: {src: counter[split, src] for src in SOURCES} for split in SPLITS}

    manifests = {"ml_handoff/manifest.json": HANDOFF / "manifest.json", "manifest_mleval.json": ROOT / "manifest_mleval.json"}
    export = json.loads((HANDOFF / "manifest.json").read_text(encoding="utf-8"))
    return {
        "inputs": {i["name"]: {kind: i[kind]["sha256"] for kind in ("sessions", "gold", "labels")}
                   for i in export["inputs"]},
        "missing_inputs": MISSING,
        "sessions": table(sessions_n), "gold": table(gold_n), "negatives": table(neg_n), "masks": table(mask_n),
        "items": table(items_n),
        "gold_by_type": {split: {src: dict(sorted(gold_type[split, src].items())) for src in SOURCES}
                         for split in SPLITS},
        "llm_context_by_primary_type": {split: {f"{c}|{t}": n for (c, t), n in sorted(cell[split].items())}
                                        for split in SPLITS},
        "llm_bundles": {split: dict(sorted(bundle[split].items())) for split in SPLITS},
        "privesc_scenarios": {split: dict(sorted(scenario[split].items())) for split in SPLITS if scenario[split]},
        "privesc_gold_by_scenario": {split: dict(sorted(scenario_gold[split].items())) for split in SPLITS
                                     if scenario_gold[split]},
        "privesc_sample_target_gold": privesc_target(),
        "moved_by_near_duplicates": dict(moved),
        "recorded_values_on_both_sides": len(export["recorded_values_on_both_sides"]),
        "near_duplicate_pairs": dict(Counter(p["rule"] for p in export["near_duplicates"]["pairs"])),
        "sha256": {(p.relative_to(ROOT).as_posix()): sha256(p) for key in files for p in files[key]},
        "sha256_manifests": {name: sha256(p) for name, p in manifests.items()},
    }


def privesc_target() -> int | None:
    for line in (HANDOFF / "sessions_train.jsonl").read_text(encoding="utf-8").splitlines():
        meta = json.loads(line)["meta"]
        if "sample" in meta:
            return meta["sample"]["target_gold"]
    return None


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def readme(s: dict) -> str:
    out = ["# PromptGuard ML 학습 데이터 — 0단계 묶음", "",
           "API를 새로 부르지 않고 **지금 저장소에 있는 템플릿과 privesc만으로** 만든 첫 묶음이다. 목적은 두 가지다.",
           "(1) 학습 → 평가 파이프라인이 끝까지 도는지 확인한다. (2) 이 데이터만으로도 ML이 규칙 탐지기보다 나은 점이 있는지 본다.",
           "본 생성(LLM 카드 약 2,150장 추가)은 이 결과를 보고 정한다. 그래서 **양과 분포가 계획(약 8,000세션)보다 훨씬 작고 치우쳐 있다**(아래 한계).",
           "", "이 폴더는 `ml_train_export.py`가 쓰고 `ml_train_handoff.py`가 이 README를 덧쓴다. 같은 커밋에서 다시 빌드하면 바이트 단위로 같은 파일이 나온다",
           "(기대 sha256은 저장소의 `metric-detection/templates/ml_train/handoff_step0.json`). 재현 방법은 `metric-detection/colab/build_ml_handoff.ipynb` 또는",
           "`metric-detection/scripts/build_ml_handoff.sh`.", "",
           "## 무엇이 어디에 있나", "",
           "| 위치 | split | 쓰는 곳 |", "|---|---|---|",
           "| `ml_handoff/sessions_*.jsonl`, `gold_*.jsonl`, `labels_*.jsonl` | train, val | 학습과 모델 선택(조기 종료) |",
           "| `data_test/sessions_mleval_<입력>_<split>.jsonl`, `data_answer/gold_mleval_…`, `labels_mleval_…` | test, test_ood | 평가 전용. 학습에 쓰지 않는다 |",
           "", "형식(필드 설명)은 아래 \"파일 형식\" 절에 있다. 출처는 세 가지다.", "",
           "- **손 템플릿**(`group_id`가 `hand-`): 사람이 직접 쓴 경계 규칙 세션 160개 × 값 변형 5.",
           "- **LLM 템플릿**(`c`, `o`, `a`, `b`, `p`로 시작): Claude가 카드대로 쓴 템플릿 × 값 변형 3(분포 이동 `o`는 2). `c`는 파일럿, `o`는 분포 이동 test,",
           "  `a`는 자연어·문서 칸 보강, `b`는 설정 파일의 일반 값 음성, `p`는 개인정보 음성 묶음이다.",
           "- **privesc**(`privesc-<시나리오>`): 비밀을 심어 둔 리눅스 VM에서 실제 에이전트가 권한 상승을 푼 기록. train 정답의 30% 이하로 표본 추출했다.",
           "", "## 수", "", "### split × 출처별 세션 / 정답 span", "",
           "| split | " + " | ".join(f"{SOURCE_KO[x]} 세션" for x in SOURCES) + " | " +
           " | ".join(f"{SOURCE_KO[x]} 정답" for x in SOURCES) + " | 합계 세션 | 합계 정답 |",
           "|---|" + "---|" * (2 * len(SOURCES) + 2)]
    for split in SPLITS:
        ss, gg = s["sessions"][split], s["gold"][split]
        out.append(f"| {split} | " + " | ".join(f"{ss[x]:,}" for x in SOURCES) + " | " +
                   " | ".join(f"{gg[x]:,}" for x in SOURCES) + f" | {sum(ss.values()):,} | {sum(gg.values()):,} |")
    train_gold = s["gold"]["train"]
    out += ["", f"train 정답 중 privesc 비율: {100 * train_gold['privesc'] / sum(train_gold.values()):.2f}% "
                f"(목표 30% 이하, privesc 표본 목표 정답 수 {s['privesc_sample_target_gold']:,}).", ""]

    out += ["### 정답 대비 음성", "",
            "음성 = labels의 이름 붙은 비정답 구간(어려운 음성, 식별자 등). privesc의 `mask`(tool_input의 `[PASSWORD_1]` 같은 가림 표시)는 따로 센다.", "",
            "| split | 출처 | 정답 | 음성 | 음성 / 정답 | mask |", "|---|---|---|---|---|---|"]
    for split in SPLITS:
        for x in SOURCES:
            g, n, m = s["gold"][split][x], s["negatives"][split][x], s["masks"][split][x]
            if s["sessions"][split][x]:
                out.append(f"| {split} | {SOURCE_KO[x]} | {g:,} | {n:,} | {n / g:.2f} |" if g else
                           f"| {split} | {SOURCE_KO[x]} | 0 | {n:,} | - |")
                out[-1] += f" {m:,} |"
    out += ["", "privesc 음성의 대부분은 `identifier`(`ls -l` 소유자 칸의 `root` 등)라 다른 출처와 비율을 섞어 보지 않는다.", ""]

    out += ["### 정답 유형별 (train)", "", "| 출처 | " + " | ".join(TYPES) + " |", "|---|" + "---|" * len(TYPES)]
    for x in SOURCES:
        t = s["gold_by_type"]["train"][x]
        out.append(f"| {SOURCE_KO[x]} | " + " | ".join(f"{t.get(k, 0):,}" for k in TYPES) + " |")
    total = Counter()
    for x in SOURCES:
        total.update(s["gold_by_type"]["train"][x])
    all_n = sum(total.values())
    out.append("| 비율 | " + " | ".join(pct(total[k], all_n) for k in TYPES) + " |")

    out += ["", "### LLM 템플릿의 문맥 × 주 비밀 유형 (train + val 세션)", "",
            "손 템플릿과 privesc에는 카드가 없어 이 표에 없다. `none`은 비밀이 없는 세션(음성 세션)이다.", ""]
    cells = Counter()
    for split in ("train", "val"):
        for k, n in s["llm_context_by_primary_type"][split].items():
            cells[tuple(k.split("|"))] += n
    cols = [*TYPES, "none"]
    ctxs = [c for c in CONTEXTS if any(cells[c, t] for t in cols)]
    n_all = sum(cells.values())
    out += ["| 문맥 | " + " | ".join(cols) + " | 합계 | 비율 |", "|---|" + "---|" * (len(cols) + 2)]
    for c in ctxs:
        row = sum(cells[c, t] for t in cols)
        out.append(f"| {c} | " + " | ".join(str(cells[c, t]) for t in cols) + f" | {row} | {pct(row, n_all)} |")
    out.append("| 합계 | " + " | ".join(str(sum(cells[c, t] for c in ctxs)) for t in cols) + f" | {n_all} | |")
    out += ["", "LLM 묶음별 세션: " + "; ".join(f"{split} " + ", ".join(f"{k} {v}" for k, v in b.items())
                                          for split, b in s["llm_bundles"].items() if b), ""]

    out += ["### privesc 표본", "", "| split | 시나리오별 세션 |", "|---|---|"]
    for split, sc in s["privesc_scenarios"].items():
        out.append(f"| {split} | " + ", ".join(f"{k} {v}" for k, v in sc.items()) + f" (합 {sum(sc.values())}) |")
    out += ["", "거의 같은 문맥(값·숫자를 가린 단어 3-gram 유사도 0.8 이상) 쌍: " +
            (", ".join(f"{k} {v}" for k, v in s["near_duplicate_pairs"].items()) or "없음") +
            " (`reported`는 privesc끼리라 옮기지 않고 기록만 한 쌍). 평가 쪽에서 train으로 옮긴 세션: " +
            (", ".join(f"{k} {v}" for k, v in s["moved_by_near_duplicates"].items()) or "없음") + ".",
            f"train과 평가 쪽에 함께 나오는 정답 값(값 없이 manifest에 기록): {s['recorded_values_on_both_sides']}개. 모두 privesc 기록이거나",
            "`value_gen.WEAK`의 약한 비밀번호(`toor`류 고정 목록, `weak_list: true`)다.", ""]

    out += ["## 알려진 한계 — 점수를 읽을 때", "",
            "1. **LLM 템플릿이 설정·자연어·문서 문맥으로 쏠려 있다.** 본 생성 전이라 파일럿 80장에 보강 묶음(a·b·p)만 더해졌기 때문이다.",
            "   로그, 스택트레이스, diff, HTTP, 키 파일 문맥은 아주 적다. 문맥별 점수는 표본이 작다는 점을 감안한다.",
            "2. **ACCESS_KEY 정답이 적다**(위 유형 표). 이 유형의 재현율은 신뢰구간이 넓다.",
            "3. **privesc는 한 분야(리눅스 권한 상승)에 치우치고, test_ood가 train과 같은 VM이다.** OOD 시나리오 2개가 train 시나리오와",
            "   수천 item이 사실상 같고(manifest `near_duplicates`, rule `reported`), 에이전트의 추측 비밀번호가 양쪽에 나온다. privesc test_ood 점수는 낙관적이다.",
            "4. **CredData·Nemotron-PII 평가는 낙관적이다.** 보강 카드(a·b·p)를 이 두 평가의 오탐·미탐 분석으로 설계했기 때문이다(텍스트와 값은 쓰지 않았다).",
            "   ML이 규칙보다 나은지 판단할 때는 **authored test(`sessions_mleval_v1_test`, `sessions_mleval_hand_v1_test`), 분포 이동 test(`sessions_mleval_v1_test_ood`), privesc test_ood**를 우선 본다.",
            "   단, `v1_test_ood`는 10세션뿐이다.",
            "5. **손 템플릿이 정답의 다수를 차지한다.** 경계 규칙을 일부러 몰아 넣은 세션이라 실제 트래픽보다 정답 밀도가 높다.",
            "6. **빠진 입력:** " + "; ".join(s["missing_inputs"]) + ". 이 템플릿들은 빌드에 들어가지 않았다.",
            "7. 사람 검토(계획 6절)를 아직 하지 않은 템플릿이다.", ""]

    out += ["## 파일 sha256", "", "| 파일 | sha256 |", "|---|---|"]
    out += [f"| `{k}` | `{v}` |" for k, v in s["sha256"].items()]
    out += ["", "manifest 두 개는 쓴 코드의 sha256을 담고 있어 코드만 바뀌어도 값이 바뀐다(데이터 대조에는 쓰지 않는다): " +
            ", ".join(f"`{k}` `{v[:16]}…`" for k, v in s["sha256_manifests"].items()), "", "---", ""]
    guide = E.HANDOFF_README.split("\n", 1)[1].replace("\n## ", "\n### ")
    return "\n".join(out) + "\n## 파일 형식 (ml_train_export.py 안내)\n" + guide


def compare(new: dict, old: dict) -> list[str]:
    diffs = []
    for key in sorted(set(new) | set(old)):
        if key == "sha256_manifests":
            continue
        if key == "sha256":
            for f in sorted(set(new[key]) | set(old.get(key, {}))):
                if new[key].get(f) != old.get(key, {}).get(f):
                    diffs.append(f"sha256 {f}: expected {old.get(key, {}).get(f)}, got {new[key].get(f)}")
        elif new.get(key) != old.get(key):
            diffs.append(f"{key} differs")
    return diffs


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=("write", "check"))
    args = parser.parse_args()
    summary = summarize()
    (HANDOFF / "README.md").write_text(readme(summary), encoding="utf-8")
    if args.mode == "write":
        RECORD.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        RECORD_MD.write_text((HANDOFF / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {RECORD.relative_to(REPO)}, {RECORD_MD.relative_to(REPO)} and {(HANDOFF / 'README.md').relative_to(REPO)}")
        return
    diffs = compare(summary, json.loads(RECORD.read_text(encoding="utf-8")))
    for name, value in summary["sha256_manifests"].items():
        print(f"manifest {name}: {value}")
    if diffs:
        print("MISMATCH:\n  " + "\n  ".join(diffs))
        sys.exit(1)
    print(f"OK: {len(summary['sha256'])} data files match {RECORD.relative_to(REPO)}")


if __name__ == "__main__":
    main()
