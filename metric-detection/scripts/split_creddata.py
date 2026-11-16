"""Freeze source membership for future CredData-derived tasks, before writing tasks or running agents.

Only IDs, counts and hashes are written. Existing sessions/gold and dataset_policy are not changed.
Repositories sharing an informative identical context (after gold masking/whitespace normalization)
are assigned together. This is not a complete near-duplicate/fork audit or a training-data export.

Run from the repository root:
  python3 metric-detection/scripts/split_creddata.py build
  python3 metric-detection/scripts/split_creddata.py verify
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "metric-detection"
SPLITS = ("train", "val", "test")
TYPES = ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY")
SEED = "creddata-v1-20261115"
MIN_CONTEXT = 160  # non-secret, non-whitespace characters remaining after gold masking
MARKER = "\x00SECRET\x00"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


@dataclass
class Repository:
    sessions: list[str] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    extensions: Counter = field(default_factory=Counter)


@dataclass
class Corpus:
    repos: dict[str, Repository]
    contexts: dict[str, set[str]]
    values: dict[str, set[str]]
    commits: list[str]
    versions: list[str]
    context_items: int


def context_hash(text: str, spans: list[dict]) -> str | None:
    pieces, cursor = [], 0
    for span in sorted(spans, key=lambda s: (s["start"], s["end"])):
        start, end = span["start"], span["end"]
        if not isinstance(start, int) or not isinstance(end, int) or not cursor <= start < end <= len(text):
            raise ValueError("invalid or overlapping gold offsets")
        pieces.extend((text[cursor:start], MARKER))
        cursor = end
    pieces.append(text[cursor:])
    normalized = " ".join("".join(pieces).split())
    residual = re.sub(r"\s+", "", normalized.replace(MARKER, ""))
    if len(residual) < MIN_CONTEXT:
        return None
    return digest(normalized.encode())


def load_corpus(sessions_path: Path, gold_path: Path) -> Corpus:
    gold, span_ids = defaultdict(list), set()
    for row in read_rows(gold_path):
        identity = (row["session_id"], row["item_id"], row["span_id"])
        if identity in span_ids:
            raise ValueError("duplicate gold span ID")
        span_ids.add(identity)
        if row["span"]["type"] not in TYPES:
            raise ValueError("unknown gold type")
        gold[identity[:2]].append(row["span"])
    repos, contexts, values = {}, defaultdict(set), defaultdict(set)
    seen_sessions, seen_items, commits, versions = set(), set(), set(), set()
    context_items = 0
    for session in read_rows(sessions_path):
        sid, meta = session["session_id"], session["meta"]
        source = PurePosixPath(meta["creddata_file"])
        if len(source.parts) < 3 or source.parts[0] != "data" or source.is_absolute() or ".." in source.parts:
            raise ValueError("invalid CredData source path")
        repo_id = source.parts[1]
        if meta["group_id"] != "creddata-" + repo_id:
            raise ValueError("source repository and group_id disagree")
        if sid in seen_sessions:
            raise ValueError("duplicate session ID")
        if meta["origin"] != "external" or "ml_train" in meta["allowed_use"]:
            raise ValueError("expected unchanged evaluation-only CredData inputs")
        seen_sessions.add(sid)
        commits.add(meta["creddata_commit"])
        versions.add(meta["dataset_version"])
        repo = repos.setdefault(repo_id, Repository())
        repo.sessions.append(sid)
        repo.counts["sessions"] += 1
        repo.extensions[source.suffix.lower() or "(none)"] += 1
        for item in session["items"]:
            key = (sid, item["item_id"])
            if key in seen_items:
                raise ValueError("duplicate item ID")
            seen_items.add(key)
            spans, text = gold.get(key, []), item["text"]
            hashed = context_hash(text, spans)
            if hashed is not None:
                contexts[hashed].add(repo_id)
                context_items += 1
            repo.counts["items"] += 1
            repo.counts["positive_items" if spans else "negative_items"] += 1
            repo.counts["gold_spans"] += len(spans)
            for span in spans:
                repo.counts[span["type"]] += 1
                value = text[span["start"]:span["end"]]
                # Audit only: these values MUST be replaced before any future training run.
                if len(value) >= 12:
                    values[digest(value.encode())].add(repo_id)
    if set(gold) - seen_items:
        raise ValueError("orphan gold rows")
    if len(commits) != 1 or len(versions) != 1 or not repos:
        raise ValueError("expected one nonempty, pinned CredData conversion")
    return Corpus(repos, dict(contexts), dict(values), sorted(commits), sorted(versions), context_items)


def components(corpus: Corpus) -> list[list[str]]:
    parent = {repo: repo for repo in corpus.repos}

    def find(repo):
        while repo != parent[repo]:
            parent[repo] = parent[parent[repo]]
            repo = parent[repo]
        return repo

    for group in corpus.contexts.values():
        group = sorted(group)
        for repo in group[1:]:
            parent[find(repo)] = find(group[0])
    groups = defaultdict(list)
    for repo in sorted(parent):
        groups[find(repo)].append(repo)
    return sorted(groups.values())


def component_id(group: list[str]) -> str:
    return "creddata-component-" + digest("\n".join(group).encode())[:16]


def partition(corpus: Corpus, groups: list[list[str]], ratios: list[float], seed: str) -> dict[str, str]:
    """Deterministic group allocation balancing source size, positive/negative items and gold types."""
    if len(groups) < len(SPLITS):
        raise ValueError("fewer independent repository components than splits")
    if len(ratios) != 3 or any(not math.isfinite(r) or r <= 0 for r in ratios) or not math.isclose(sum(ratios), 1):
        raise ValueError("three positive split ratios must sum to one")
    features = ("repos", "sessions", "items", "positive_items", "negative_items", *TYPES)
    vectors = []
    for group in groups:
        counts = sum((corpus.repos[r].counts for r in group), Counter())
        counts["repos"] = len(group)
        vectors.append([counts[f] for f in features])
    totals = [sum(v[j] for v in vectors) or 1 for j in range(len(features))]
    normalized = [[n / total for n, total in zip(v, totals)] for v in vectors]
    order = sorted(range(len(groups)), key=lambda i: (
        -max(normalized[i]), digest((seed + ":" + component_id(groups[i])).encode())))
    sums = [[0.0] * len(features) for _ in SPLITS]
    assigned = {}

    def delta(i, target, sign):
        ratio = ratios[target]
        return sum(((s + sign * n - ratio) ** 2 - (s - ratio) ** 2) / ratio
                   for s, n in zip(sums[target], normalized[i]))

    for i in order:
        target = min(range(3), key=lambda t: (delta(i, t, 1), t))
        assigned[i] = target
        sums[target] = [a + b for a, b in zip(sums[target], normalized[i])]
    # Improve the balance without separating a repository or a duplicate component.
    for _ in range(100):
        changed = False
        for i in order:
            old = assigned[i]
            if sum(t == old for t in assigned.values()) <= 1:
                continue
            gains = [(delta(i, old, -1) + delta(i, t, 1), t) for t in range(3) if t != old]
            gain, target = min(gains)
            if gain < -1e-12:
                sums[old] = [a - b for a, b in zip(sums[old], normalized[i])]
                sums[target] = [a + b for a, b in zip(sums[target], normalized[i])]
                assigned[i] = target
                changed = True
        if not changed:
            break
    if set(assigned.values()) != {0, 1, 2}:
        raise ValueError("allocation produced an empty split")
    return {repo: SPLITS[assigned[i]] for i, group in enumerate(groups) for repo in group}


def path_record(path: Path) -> dict:
    resolved = path.resolve()
    return {"path": str(resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved),
            "sha256": digest(path.read_bytes())}


def build_outputs(sessions_path: Path, gold_path: Path, ratios: list[float], seed: str) -> dict[str, bytes]:
    corpus = load_corpus(sessions_path, gold_path)
    groups = components(corpus)
    assignment = partition(corpus, groups, ratios, seed)
    group_of = {r: component_id(g) for g in groups for r in g}
    counts, ids = {}, {}
    for split in SPLITS:
        members = [r for r in sorted(corpus.repos) if assignment[r] == split]
        count = sum((corpus.repos[r].counts for r in members), Counter())
        counts[split] = {"repositories": len(members), "components": len({group_of[r] for r in members}),
                         **{f: count[f] for f in ("sessions", "items", "positive_items", "negative_items", "gold_spans")},
                         "gold_by_type": {t: count[t] for t in TYPES}}
        ids[split] = sorted(sid for r in members for sid in corpus.repos[r].sessions)
    cross_contexts = sum(len({assignment[r] for r in repos}) > 1 for repos in corpus.contexts.values())
    if cross_contexts:
        raise ValueError("identical informative contexts cross split boundaries")
    shared_values = sum(len({assignment[r] for r in repos}) > 1 for repos in corpus.values.values())
    output = {f"{split}.txt": ("\n".join(ids[split]) + "\n").encode() for split in SPLITS}
    rows = [{"repo_id": r, "group_id": "creddata-" + r, "component_id": group_of[r],
             "split": assignment[r], "counts": dict(sorted(corpus.repos[r].counts.items())),
             "source_file_extensions": dict(sorted(corpus.repos[r].extensions.items()))}
            for r in sorted(corpus.repos)]
    output["repositories.jsonl"] = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in rows)
    output["duplicate_components.json"] = json_bytes([
        {"component_id": component_id(g), "repositories": g, "split": assignment[g[0]]}
        for g in groups if len(g) > 1])
    manifest = {
        "schema_version": 1, "stage": "source_partition_only", "ready_for_training": False,
        "inputs": {"sessions": path_record(sessions_path), "gold": path_record(gold_path)},
        "source": {"creddata_commits": corpus.commits, "dataset_versions": corpus.versions},
        "configuration": {"seed": seed, "target_ratios": dict(zip(SPLITS, ratios)),
                          "minimum_nonsecret_context_chars": MIN_CONTEXT},
        "assignment_unit": "repository components linked by identical gold-masked, whitespace-normalized items",
        "balancing_features": ["repositories", "sessions", "items", "positive_items", "negative_items", *TYPES],
        "counts": counts,
        "checks": {"source_ids_and_gold_offsets_valid": True, "all_sessions_assigned_once": True,
                   "repositories_in_multiple_splits": 0,
                   "informative_context_items": corpus.context_items,
                   "cross_repository_duplicate_context_hashes": sum(len(r) > 1 for r in corpus.contexts.values()),
                   "informative_context_hashes_in_multiple_splits": cross_contexts,
                   "gold_value_hashes_12plus_chars_in_multiple_splits": shared_values},
        "limitations": [
            "Only converted file windows are available locally; this is not a split of runnable complete repositories.",
            "Only known gold spans are masked for duplicate checks; labels are not guaranteed exhaustive.",
            "Short contexts and approximate duplicates/forks have not been excluded by this check.",
            "Gold values may recur across splits. Replace values with split-specific synthetic values before agent runs.",
            "Task-template families and any new code imports must be checked for cross-split reuse later.",
            "Existing evaluation-only inputs and dataset_policy are unchanged. No model may train from this manifest directly.",
            "The full existing CredData benchmark is not independent once any of these sources trains a model.",
            "Existing holdout benchmarks have already been inspected; this is not a pristine blind evaluation.",
        ],
        "artifacts": {name: {"sha256": digest(content)} for name, content in sorted(output.items())},
    }
    output["manifest.json"] = json_bytes(manifest)
    output["README.md"] = readme(manifest).encode()
    return output


def readme(manifest: dict) -> str:
    lines = ["# CredData 원본 분할 v1", "", "작업 지시문을 작성하기 전에 고정한 원본 저장소·세션 분할이다. "
             "코드 본문과 비밀값은 포함하지 않으며 기존 평가 파일·학습 허용 정책은 바꾸지 않는다.", "",
             "| split | 저장소 | 파일/세션 | item | 양성 item | 정답 span |",
             "|---|---:|---:|---:|---:|---:|"]
    for split, count in manifest["counts"].items():
        lines.append(f"| {split} | {count['repositories']} | {count['sessions']} | {count['items']} | "
                     f"{count['positive_items']} | {count['gold_spans']} |")
    lines += ["", "## 사용 순서", "",
              "1. `repositories.jsonl`에서 원본 저장소의 split과 component_id를 찾는다. "
              "각 `train.txt`, `val.txt`, `test.txt`는 현재 변환본의 session_id 목록이다.",
              "2. 해당 원본으로 작업 환경과 지시문을 작성한다. 원본 저장소→작업→실행→증강본에 "
              "source_repo_id, source_session_id, component_id, split을 전달한다.",
              "3. 새로 구성한 실행 가능한 환경은 코드 조각 기반 합성 환경임을 표시한다. "
              "원본 전체 저장소를 복구하면 같은 RepoID를 유지하고 중복 검사를 다시 한다.",
              "4. 실행 전 비밀값을 split별 시드로 치환한다. 궤적·증강을 만든 뒤 임의로 다시 분할하지 않는다.",
              "5. 근접 중복 코드·공유 작업 원형, 미라벨 비밀, 라이선스를 검토하고 "
              "원본 출처별 용도 정책을 명시한 별도 학습 데이터 export를 만든다. "
              "이 목록 자체는 학습용 데이터가 아니다.", "", "## 분할 방식", "",
              "목표는 train/val/test 80/10/10이다. 저장소를 쪼개지 않고 파일 수·item 수·양성/음성·"
              "5개 정답 유형의 분포를 함께 고려하므로 실제 비율은 달라진다. "
              "정답을 가린 뒤 남은 비공백 문맥이 160자 이상인 item이 공백 정규화 후 같으면 "
              "관련 저장소를 하나의 component로 묶는다. 짧은 코드·근접 중복까지 없다는 뜻은 아니다.",
              "", "## 검증과 재현", "", "저장소 루트에서 실행한다.", "", "```bash",
              "python3 metric-detection/scripts/split_creddata.py build",
              "python3 metric-detection/scripts/split_creddata.py verify", "```", "",
              "입력 파일 SHA-256, 고정 시드, 분할·검사 통계는 manifest.json에 있다. "
              "같은 입력은 바이트 단위로 같은 결과를 만든다. 다른 입력으로 기존 분할을 덮어쓰지 않는다.",
              "", "## 해석 제한", ""]
    lines += ["- " + note for note in [
        "현재 원본은 파일 주변 창이다. 작업 가능한 전체 저장소는 현재 로컬에 없다.",
        "현재 정답은 원래 CredData T/F/X가 아니라 프로젝트 LABELING.md로 변환한 라벨이다. "
        "미라벨 비밀까지 완전하게 주석 처리됐다는 보장은 없다.",
        "정답 값 자체의 분할 간 재등장이 남아 있으므로 실행 전 split별 값 치환이 필수다.",
        "기존 CredData 전체 평가는 보존됐지만 이 원본으로 학습한 모델의 독립 평가로 사용할 수 없다. "
        "후속 평가는 고정 test 원본과 별도 외부 평가에서 수행한다.",
        "기존 평가 데이터는 이미 조사·사용된 자료다. 이 분할을 완전히 미공개인 blind test로 주장하지 않는다.",
    ]]
    return "\n".join(lines) + "\n"


def check_outputs(out: Path, expected: dict[str, bytes]):
    if not out.is_dir() or {p.name for p in out.iterdir()} != set(expected):
        raise ValueError("partition artifacts missing or unexpected; use a new output version")
    for name, data in expected.items():
        if (out / name).read_bytes() != data:
            raise ValueError(f"partition/input mismatch: {name}; use a new output version")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--sessions", type=Path, default=BASE / "data_test/sessions_from_CredData.jsonl")
    parser.add_argument("--gold", type=Path, default=BASE / "data_answer/gold_from_CredData.jsonl")
    parser.add_argument("--out", type=Path, default=BASE / "source_splits/creddata-v1")
    parser.add_argument("--seed", default=SEED)
    parser.add_argument("--ratios", type=float, nargs=3, default=[0.8, 0.1, 0.1])
    args = parser.parse_args()
    expected = build_outputs(args.sessions, args.gold, args.ratios, args.seed)
    if args.command == "verify" or args.out.exists():
        check_outputs(args.out, expected)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".creddata-split-", dir=args.out.parent))
        try:
            for name, data in expected.items():
                (temporary / name).write_bytes(data)
            temporary.rename(args.out)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    manifest = json.loads(expected["manifest.json"])
    print(json.dumps({"out": str(args.out), "counts": manifest["counts"], "checks": manifest["checks"]}, indent=2))


if __name__ == "__main__":
    main()
