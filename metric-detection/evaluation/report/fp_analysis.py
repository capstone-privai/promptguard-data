"""Stage 0 false-positive analysis: per adapter and rule, from PromptGuard runs' per_finding.jsonl.

Run from metric-detection/:
  python -m evaluation.report.fp_analysis --config "ML off" results/all_X --config "ML on" results/stage0_mlon_Y/runs \
      --out results/stage0_fp_<ts>

Each --config names a configuration and the folders holding its run folders (searched recursively for run_meta.json
of system promptguard with per_finding.jsonl). A dataset split into session shards (sessions_X__part01of04.jsonl)
is put back together: counts are summed over its shards.

Per rule (adapter + rule id; ML rows also carry the model id from run_meta), over the findings of scored channels
with a valid span, each identical span counted once per rule:
  tp / over / fp  the finding lies inside one gold span / overlaps gold but spills / overlaps no gold (the scorer's
                  rule for an edit, so precision = tp / findings as metrics.json computes it for edits)
  solo_fp         an fp no finding of any other rule (any adapter) overlaps in the same item
  shared_fp       fp - solo_fp
  solo_gold       scored gold spans that this rule's findings overlap and no other rule's findings do
  solo_gold_exact of those, the ones the run masked exactly (per_span status)
Each adapter also gets an "(all rules)" row: its rules' spans together, solo against the other adapters.
Union: the run's own scoring (per_edit, per_span) and the same scored from the findings merged as pgdetector's
normalize merges overlapping spans (blocked items: one edit over the whole text, as the adapter scores them); the
difference is the mod's remask (known values re-masked without a detector finding) and is reported.

FP types: every distinct false-positive span (any rule) and every false-positive edit of the union are put in one
category by looking at the value and its line (classify_fp). The text is read from the dataset at analysis time;
only category names and counts are written. Datasets with a labels file (labels_from_<name>.jsonl) also get the
labels file's kind for an fp span that overlaps one of its non-gold rows.

Outputs (no text, only names, offsets-derived counts): rules.csv, union.csv, fp_types.csv, fp_label_kinds.csv,
report.md. Rows are per dataset and per purpose group (GROUPS); the report shows the groups.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

METRIC_ROOT = Path(__file__).resolve().parents[2]
DATA = METRIC_ROOT / "data_test"
ANSWER = METRIC_ROOT / "data_answer"
SHARD = re.compile(r"__part\d+of\d+$")
MAX_SPAN = 8192  # pgdetector core.MAX_SPAN (PG_DETECTOR_MAX_SPAN unset)

# Purpose groups (report by group, never one pooled score).
GROUPS = {
    "format detection": ("sessions_from_CredData", "sessions_from_noseyparker"),
    "natural-language secrets": ("sessions_from_Nemotron-PII",),
    "agent sessions": ("sessions", "sessions_from_example", "sessions_2"),
    "real agent trajectories": ("sessions_from_trajectory",),
    "real-traffic over-masking": ("sessions_from_openhands-feedback", "sessions_from_SWE-Gym"),
}
GROUP_OF = {dataset: group for group, datasets in GROUPS.items() for dataset in datasets}


# ---------------------------------------------------------------- loading

def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def dataset_of(meta: dict[str, Any]) -> str:
    return SHARD.sub("", Path(meta["dataset"]["sessions_path"]).stem)


def find_runs(folders: Iterable[Path]) -> list[Path]:
    runs = []
    for folder in folders:
        for meta in sorted(Path(folder).rglob("run_meta.json")):
            data = json.loads(meta.read_text(encoding="utf-8"))
            if data.get("system", {}).get("system") == "promptguard" and (meta.parent / "per_finding.jsonl").is_file():
                runs.append(meta.parent)
    return runs


def load_texts(dataset: str, keys: set[tuple[str, int]], data_dir: Path) -> dict[tuple[str, int], str]:
    texts = {}
    for record in _jsonl(data_dir / f"{dataset}.jsonl"):
        for item in record["items"]:
            key = (record["session_id"], item["item_id"])
            if key in keys:
                texts[key] = item["text"]
    return texts


def load_gold_values(dataset: str, data_dir: Path, answer_dir: Path) -> dict[str, set[str]]:
    """session_id → the gold values of that session (for the 'unlabelled repeat of a gold value' type)."""
    spans = defaultdict(list)
    for row in _jsonl(answer_dir / f"gold{dataset[len('sessions'):]}.jsonl"):
        spans[(row["session_id"], row["item_id"])].append((row["span"]["start"], row["span"]["end"]))
    values: dict[str, set[str]] = defaultdict(set)
    for record in _jsonl(data_dir / f"{dataset}.jsonl"):
        for item in record["items"]:
            for start, end in spans.get((record["session_id"], item["item_id"]), ()):
                values[record["session_id"]].add(item["text"][start:end])
    return values


def load_labels(dataset: str, labels_dir: Path) -> dict[tuple[str, int], list[tuple[int, int, str]]]:
    path = labels_dir / f"labels{dataset[len('sessions'):]}.jsonl"
    labels: dict[tuple[str, int], list[tuple[int, int, str]]] = defaultdict(list)
    if not path.is_file():
        return labels
    for row in _jsonl(path):
        if row.get("gold") is False:
            kind = row.get("kind") or row.get("reason") or row.get("verdict") or "unknown"
            labels[(row["session_id"], row["item_id"])].append((row["start"], row["end"], str(kind)))
    return labels


# ---------------------------------------------------------------- FP types

FP_TYPES = (
    "same value as a gold span in the session", "empty or whitespace", "redaction or mask mark",
    "template or placeholder", "variable or attribute reference", "code expression or type",
    "example, test or dummy value", "digits only", "number, date, version or IP", "UUID", "password hash",
    "hex digest (hash, commit id)", "public key or certificate material", "JWT-like", "URL or path",
    "email address", "identifier by key name (client id, user, account)", "word or identifier", "random-looking string (16+ chars)", "short mixed value (<16 chars)",
    "other",
)
_REDACTION = re.compile(r"(?i)^[*xX•#·.\-_ ]{3,}$|\*{3,}|redact|masked|<hidden>|removed|\bsanitized\b|^x{4,}")
_TEMPLATE = re.compile(r"(?i)<[^<>]{1,80}>|\{\{.*\}\}|\byour[_\- ]|^your|changeme|change[_\-]?me|placeholder|"
                       r"replace[_\-]?(?:me|with|this)|insert[_\-]|_here\b|-here\b|^\.\.\.$|^<|>$|xxx")
_REFERENCE = re.compile(r"^\$\{?[A-Za-z_]|^#\{|^%[A-Za-z_]\w*%$|^\{[A-Za-z_][\w.]*\}$|^\$\(|"
                        r"process\.env|os\.environ|getenv|ENV\[|^secrets\.|^vars\.|^env\.|^(?:self|this|cls)\.\w|"
                        r"^@[A-Za-z_]\w*$|^:[a-z_]+$|^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$|^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$|\$\{")
_REFERENCE_BEFORE = re.compile(r"(?:\$\{?|%|\{\{\s*)$")  # the span starts inside ${...}, $VAR, %VAR% or {{ }}
_CODE = re.compile(r"[()\[\];]|=>|->|::|\s=\s|\b(?:function|return|new|null|None|undefined|true|false|string|int|"
                   r"bool|str|const|let|var|def|import)\b|^[A-Za-z_]\w*\($")
_EXAMPLE = re.compile(r"(?i)example|sample|dummy|fake|\btest|test[_\-]|_test|mock|demo|^foo|foobar|lorem|"
                      r"^(?:secret|password|token|apikey|api_key|passwd|pass)\d*$|^1234|^abc|^qwerty")
_DIGITS = re.compile(r"^\d+$")
_NUMBERISH = re.compile(r"^[\d][\d .,:/+\-_Tvz]*$|^v?\d+(?:\.\d+)+[\w.\-]*$", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HASH = re.compile(r"^\$(?:1|2[abxy]?|5|6|y|argon2\w*|pbkdf2[\w-]*|scrypt)\$|^\{S?SHA\d*\}|^pbkdf2_|^sha\d+\$|^md5\$")
_HEX = re.compile(r"^(?:sha\d+[:\-])?[0-9a-fA-F]{16,}$")
_JWT = re.compile(r"^eyJ[\w\-]+\.[\w\-]+\.[\w\-]*$")
_URL_PATH = re.compile(r"://|^(?:/|\./|\.\./|~/|[A-Za-z]:\\)|^[\w.\-]+/[\w.\-/]+$|\\\\")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_WORD = re.compile(r"^[#.]?[A-Za-z][A-Za-z_\-. ]*$|^[A-Za-z_]+[A-Za-z]\d{0,2}$")
# The key the value is assigned to names an identifier, not a secret (LABELING.md `identifier`).
_ID_KEY = re.compile(r"(?i)(?:client[_\-.]?id|app[_\-.]?id|[_\-.]id|^id|user(?:name)?|login|account|e?mail|uuid|guid|"
                     r"license|publishable|public|request|session[_\-.]?id|tenant|project|org)$")
_ASSIGNED = re.compile(r"([A-Za-z_][\w.\-]*)[\"']?\s*[:=]\s*[\"']?\s*$")
_PUBLIC_BLOCK = re.compile(r"-----BEGIN ((?:[A-Z0-9]+ )*)(CERTIFICATE|PUBLIC KEY|CERTIFICATE REQUEST|PGP PUBLIC KEY BLOCK)-----")
_SSH_PUBLIC = re.compile(r"\b(?:ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-\S+) AAAA")


def classify_fp(text: str, start: int, end: int, gold_values: set[str]) -> str:
    """One category for a false-positive span text[start:end], from the value and its line only."""
    value = text[start:end]
    stripped = value.strip().strip("\"'`")
    if not stripped:
        return "empty or whitespace"
    if stripped in gold_values or any(len(gold) >= 6 and gold in stripped for gold in gold_values):
        return "same value as a gold span in the session"
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start:len(text) if line_end < 0 else line_end]
    begin = text.rfind("-----BEGIN ", 0, start)
    if (begin >= 0 and _PUBLIC_BLOCK.match(text, begin) and text.find("-----END", begin, start) < 0) \
            or _SSH_PUBLIC.search(line):
        return "public key or certificate material"
    if _REDACTION.search(stripped):
        return "redaction or mask mark"
    if _TEMPLATE.search(stripped):
        return "template or placeholder"
    if _HASH.search(stripped):
        return "password hash"
    if _JWT.match(stripped):
        return "JWT-like"
    if _REFERENCE.search(stripped) or _REFERENCE_BEFORE.search(text[max(line_start, start - 3):start]):
        return "variable or attribute reference"
    if _EXAMPLE.search(stripped):
        return "example, test or dummy value"
    if _DIGITS.match(stripped):
        return "digits only"
    if _UUID.match(stripped):
        return "UUID"
    if _HEX.match(stripped):
        return "hex digest (hash, commit id)"
    if _NUMBERISH.match(stripped):
        return "number, date, version or IP"
    if _EMAIL.match(stripped):
        return "email address"
    if _URL_PATH.search(stripped):
        return "URL or path"
    if _CODE.search(stripped):
        return "code expression or type"
    assigned = _ASSIGNED.search(text[max(line_start, start - 60):start])
    if assigned and _ID_KEY.search(assigned.group(1)):
        return "identifier by key name (client id, user, account)"
    if _WORD.match(stripped.rstrip(":;,.")):
        return "word or identifier"
    if len(stripped) >= 16:
        return "random-looking string (16+ chars)"
    return "short mixed value (<16 chars)"


# ---------------------------------------------------------------- per run

@dataclass
class RuleStats:
    findings: int = 0
    tp: int = 0
    over: int = 0
    fp: int = 0
    solo_fp: int = 0
    solo_gold: int = 0
    solo_gold_exact: int = 0
    invalid: int = 0

    def add(self, other: RuleStats) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class UnionStats:
    gold: int = 0
    exact: int = 0
    over: int = 0
    partial: int = 0
    missed: int = 0
    edits: int = 0
    edits_tp: int = 0
    edits_over: int = 0
    edits_fp: int = 0

    def add(self, other: UnionStats) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class Reproduction:
    items: int = 0
    blocked_items: int = 0
    adapter_failure_items: Counter = field(default_factory=Counter)
    edits_same: int = 0
    edits_only_in_run: int = 0  # the mod's remask (or a widened edit)
    edits_only_in_findings: int = 0
    remask_tp: int = 0
    remask_over: int = 0
    remask_fp: int = 0
    gold_status_differs: int = 0

    def add(self, other: Reproduction) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(other, name)
            setattr(self, name, getattr(self, name) + value)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(set(spans)):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _status(gold: tuple[int, int], edits: list[tuple[int, int]]) -> str:
    """span_scoring.score_item's judgement of one gold span."""
    start, end = gold
    union, covered = [], 0
    for left, right in sorted(edits):
        if union and left <= union[-1][1]:
            union[-1][1] = max(union[-1][1], right)
        else:
            union.append([left, right])
    covered = sum(max(0, min(end, right) - max(start, left)) for left, right in union)
    if covered == end - start:
        spills = any(left < end and start < right and (left < start or right > end) for left, right in edits)
        return "over" if spills else "exact"
    return "missed" if covered == 0 else "partial"


def _edit_class(span: tuple[int, int], gold: list[tuple[int, int]]) -> str:
    start, end = span
    if not any(start < right and left < end for left, right in gold):
        return "fp"
    return "tp" if any(left <= start and end <= right for left, right in gold) else "over"


@dataclass
class RunAnalysis:
    dataset: str
    rules: dict[tuple[str, str, str], RuleStats]
    union_run: UnionStats
    union_findings: UnionStats
    reproduction: Reproduction
    fp_spans: dict[tuple[str, int], set[tuple[int, int]]]  # distinct fp spans of any rule, per item
    fp_rules: dict[tuple[str, int, int, int], set[str]]  # (session, item, start, end) → rule labels
    fp_edits: dict[tuple[str, int], set[tuple[int, int]]]  # the union's own fp edits, per item
    describe: dict[str, Any]


ALL_RULES = "(all rules)"


def _score(per_label: dict[tuple[str, str, str], set[tuple[int, int]]], item_gold: list[tuple[int, int]],
           key: tuple[str, int], gold_status: dict[Any, str], rules: dict[tuple[str, str, str], RuleStats]) -> None:
    """Add one item's findings, grouped by label, to each label's counts (solo against the other labels)."""
    for label, spans in per_label.items():
        stats = rules[label]
        others = [span for other, other_spans in per_label.items() if other != label for span in other_spans]
        for span in spans:
            stats.findings += 1
            kind = _edit_class(span, item_gold)
            setattr(stats, kind, getattr(stats, kind) + 1)
            if kind == "fp" and not any(span[0] < right and left < span[1] for left, right in others):
                stats.solo_fp += 1
    for span in item_gold:
        hitters = {label for label, spans in per_label.items()
                   if any(span[0] < right and left < span[1] for left, right in spans)}
        if len(hitters) == 1:
            (label,) = hitters
            rules[label].solo_gold += 1
            rules[label].solo_gold_exact += gold_status[(key, *span)] == "exact"


def rule_label(adapter: str, rule_id: str, models: dict[str, str]) -> tuple[str, str, str]:
    return adapter, models.get(adapter, ""), rule_id


def analyse_run(run_dir: Path) -> RunAnalysis:
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    describe = meta["system"]["detector"]
    models = {a["name"]: a["version"] for a in describe.get("adapters", []) if str(a["name"]).startswith("ml-")}
    findings = defaultdict(list)
    for row in _jsonl(run_dir / "per_finding.jsonl"):
        if row["scored"]:
            findings[(row["session_id"], row["item_id"])].append(row)
    gold = defaultdict(list)
    gold_status = {}
    for row in _jsonl(run_dir / "per_span.jsonl"):
        if row["scored"]:
            key = (row["session_id"], row["item_id"])
            gold[key].append((row["start"], row["end"]))
            gold_status[(key, row["start"], row["end"])] = row["status"]
    edits = defaultdict(list)
    for row in _jsonl(run_dir / "per_edit.jsonl"):
        if row["scored"]:
            edits[(row["session_id"], row["item_id"])].append((row["start"], row["end"]))
    scans = {(row["session_id"], row["item_id"]): row for row in _jsonl(run_dir / "per_scan.jsonl") if row["scored"]}

    rules: dict[tuple[str, str, str], RuleStats] = defaultdict(RuleStats)
    union_run, union_findings, repro = UnionStats(), UnionStats(), Reproduction()
    fp_spans: dict[tuple[str, int], set[tuple[int, int]]] = defaultdict(set)
    fp_rules: dict[tuple[str, int, int, int], set[str]] = defaultdict(set)
    fp_edits: dict[tuple[str, int], set[tuple[int, int]]] = defaultdict(set)

    for key, scan in scans.items():
        item_gold = sorted(gold.get(key, []))
        repro.items += 1
        repro.blocked_items += bool(scan["blocked"])
        for error in scan["adapter_errors"]:
            repro.adapter_failure_items[error] += 1
        # distinct valid spans per rule
        per_rule: dict[tuple[str, str, str], set[tuple[int, int]]] = defaultdict(set)
        for row in findings.get(key, []):
            label = rule_label(row["adapter"], row["rule_id"], models)
            if not row["valid"]:
                rules[label].invalid += 1
                rules[(label[0], label[1], ALL_RULES)].invalid += 1
                continue
            per_rule[label].add((row["start"], row["end"]))
        for label, spans in per_rule.items():
            for span in spans:
                if _edit_class(span, item_gold) == "fp":
                    fp_spans[key].add(span)
                    fp_rules[(*key, *span)].add(" / ".join(part for part in label if part))
        _score(per_rule, item_gold, key, gold_status, rules)
        # The same per adapter (all its rules together): solo against the other adapters.
        per_adapter: dict[tuple[str, str, str], set[tuple[int, int]]] = defaultdict(set)
        for (adapter, model, _), spans in per_rule.items():
            per_adapter[(adapter, model, ALL_RULES)] |= spans
        _score(per_adapter, item_gold, key, gold_status, rules)

        # union as scored by the run
        run_edits = sorted(edits.get(key, []))
        for span in item_gold:
            status = gold_status[(key, *span)]
            union_run.gold += 1
            setattr(union_run, status, getattr(union_run, status) + 1)
        for span in run_edits:
            kind = _edit_class(span, item_gold)
            union_run.edits += 1
            setattr(union_run, f"edits_{kind}", getattr(union_run, f"edits_{kind}") + 1)
            if kind == "fp":
                fp_edits[key].add(span)

        # union rebuilt from the findings
        all_spans = [span for spans in per_rule.values() for span in spans]
        if scan["blocked"]:
            rebuilt = list(run_edits)  # the adapter's whole-text edit; nothing to rebuild
        else:
            rebuilt = [span for span in _merge(all_spans) if span[1] - span[0] <= MAX_SPAN]
        for span in item_gold:
            status = _status(span, rebuilt)
            union_findings.gold += 1
            setattr(union_findings, status, getattr(union_findings, status) + 1)
            repro.gold_status_differs += status != gold_status[(key, *span)]
        for span in rebuilt:
            kind = _edit_class(span, item_gold)
            union_findings.edits += 1
            setattr(union_findings, f"edits_{kind}", getattr(union_findings, f"edits_{kind}") + 1)
        same = set(rebuilt) & set(run_edits)
        repro.edits_same += len(same)
        repro.edits_only_in_findings += len(set(rebuilt) - same)
        for span in set(run_edits) - same:
            repro.edits_only_in_run += 1
            kind = _edit_class(span, item_gold)
            setattr(repro, f"remask_{kind}", getattr(repro, f"remask_{kind}") + 1)
    return RunAnalysis(dataset_of(meta), dict(rules), union_run, union_findings, repro, dict(fp_spans),
                       dict(fp_rules), dict(fp_edits), describe)


# ---------------------------------------------------------------- aggregation and output

def _precision(tp: int, total: int) -> float | None:
    return tp / total if total else None


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def analyse(configs: list[tuple[str, list[Path]]], data_dir: Path = DATA, answer_dir: Path = ANSWER,
            labels_dir: Path = METRIC_ROOT) -> dict[str, Any]:
    out: dict[str, Any] = {"configs": [], "rules": [], "union": [], "fp_types": [], "fp_label_kinds": [],
                           "runs": []}
    for name, folders in configs:
        runs = find_runs(folders)
        if not runs:
            raise SystemExit(f"{name}: no promptguard run folders with per_finding.jsonl under {folders}")
        by_dataset: dict[str, list[RunAnalysis]] = defaultdict(list)
        describes = set()
        for run in runs:
            analysis = analyse_run(run)
            by_dataset[analysis.dataset].append(analysis)
            describes.add(json.dumps(analysis.describe, sort_keys=True))
            out["runs"].append({"config": name, "dataset": analysis.dataset, "run_dir": str(run)})
        out["configs"].append({"config": name, "describe": [json.loads(d) for d in sorted(describes)],
                               "datasets": sorted(by_dataset)})
        group_rules: dict[str, dict[tuple, RuleStats]] = defaultdict(lambda: defaultdict(RuleStats))
        group_union: dict[str, dict[str, Any]] = defaultdict(lambda: {"run": UnionStats(), "findings": UnionStats(),
                                                                       "repro": Reproduction()})
        group_types: dict[str, Counter] = defaultdict(Counter)
        group_edit_types: dict[str, Counter] = defaultdict(Counter)
        group_type_rules: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        group_kinds: dict[str, Counter] = defaultdict(Counter)
        for dataset, analyses in sorted(by_dataset.items()):
            group = GROUP_OF.get(dataset, "other")
            rules: dict[tuple, RuleStats] = defaultdict(RuleStats)
            union = {"run": UnionStats(), "findings": UnionStats(), "repro": Reproduction()}
            fp_spans: dict[tuple[str, int], set] = defaultdict(set)
            fp_rules: dict[tuple, set] = defaultdict(set)
            fp_edits: dict[tuple[str, int], set] = defaultdict(set)
            for analysis in analyses:
                for label, stats in analysis.rules.items():
                    rules[label].add(stats)
                union["run"].add(analysis.union_run)
                union["findings"].add(analysis.union_findings)
                union["repro"].add(analysis.reproduction)
                for key, spans in analysis.fp_spans.items():
                    fp_spans[key] |= spans
                for key, labels in analysis.fp_rules.items():
                    fp_rules[key] |= labels
                for key, spans in analysis.fp_edits.items():
                    fp_edits[key] |= spans
            for label, stats in rules.items():
                group_rules[group][label].add(stats)
                out["rules"].append(_rule_row(name, group, dataset, label, stats))
            for part in ("run", "findings"):
                group_union[group][part].add(union[part])
            group_union[group]["repro"].add(union["repro"])
            out["union"].append(_union_row(name, group, dataset, union))
            # FP types: read the text now, write only categories
            texts = load_texts(dataset, set(fp_spans) | set(fp_edits), data_dir)
            gold_values = load_gold_values(dataset, data_dir, answer_dir)
            labels = load_labels(dataset, labels_dir)
            types, edit_types, kinds = Counter(), Counter(), Counter()
            type_rules: dict[str, Counter] = defaultdict(Counter)
            for key, spans in fp_spans.items():
                for start, end in spans:
                    category = classify_fp(texts[key], start, end, gold_values.get(key[0], set()))
                    types[category] += 1
                    for label in fp_rules[(*key, start, end)]:
                        type_rules[category][label] += 1
                    hit = [kind for left, right, kind in labels.get(key, []) if start < right and left < end]
                    kinds[hit[0] if hit else "(no labels row)" if labels else "(dataset has no labels file)"] += 1
            for key, spans in fp_edits.items():
                for start, end in spans:
                    edit_types[classify_fp(texts[key], start, end, gold_values.get(key[0], set()))] += 1
            for category in set(types) | set(edit_types):
                out["fp_types"].append({"config": name, "group": group, "dataset": dataset, "type": category,
                                        "fp_spans": types[category], "union_fp_edits": edit_types[category],
                                        "top_rules": "; ".join(f"{rule} ({count})" for rule, count
                                                               in type_rules[category].most_common(3))})
                group_types[group][category] += types[category]
                group_edit_types[group][category] += edit_types[category]
                for rule, count in type_rules[category].items():
                    group_type_rules[group][category][rule] += count
            for kind, count in kinds.items():
                out["fp_label_kinds"].append({"config": name, "group": group, "dataset": dataset, "kind": kind,
                                              "fp_spans": count})
                group_kinds[group][kind] += count
        for group, rules in group_rules.items():
            for label, stats in rules.items():
                out["rules"].append(_rule_row(name, group, "(group)", label, stats))
            out["union"].append(_union_row(name, group, "(group)", group_union[group]))
            for category in set(group_types[group]) | set(group_edit_types[group]):
                out["fp_types"].append({"config": name, "group": group, "dataset": "(group)", "type": category,
                                        "fp_spans": group_types[group][category],
                                        "union_fp_edits": group_edit_types[group][category],
                                        "top_rules": "; ".join(f"{rule} ({count})" for rule, count
                                                               in group_type_rules[group][category].most_common(3))})
            for kind, count in group_kinds[group].items():
                out["fp_label_kinds"].append({"config": name, "group": group, "dataset": "(group)", "kind": kind,
                                              "fp_spans": count})
        # every dataset together, for the FP type list only (counts, not a score)
        all_types, all_edit_types, all_rules = Counter(), Counter(), defaultdict(Counter)
        for group in group_types:
            all_types.update(group_types[group])
            all_edit_types.update(group_edit_types[group])
            for category, counter in group_type_rules[group].items():
                all_rules[category].update(counter)
        for category in set(all_types) | set(all_edit_types):
            out["fp_types"].append({"config": name, "group": "(all datasets)", "dataset": "(all)", "type": category,
                                    "fp_spans": all_types[category], "union_fp_edits": all_edit_types[category],
                                    "top_rules": "; ".join(f"{rule} ({count})" for rule, count
                                                           in all_rules[category].most_common(3))})
    return out


def _rule_row(config: str, group: str, dataset: str, label: tuple[str, str, str], stats: RuleStats) -> dict[str, Any]:
    adapter, model, rule_id = label
    return {"config": config, "group": group, "dataset": dataset, "adapter": adapter, "model": model,
            "rule_id": rule_id, "findings": stats.findings, "tp": stats.tp, "over": stats.over, "fp": stats.fp,
            "precision": _precision(stats.tp, stats.findings), "solo_fp": stats.solo_fp,
            "shared_fp": stats.fp - stats.solo_fp, "solo_gold": stats.solo_gold,
            "solo_gold_exact": stats.solo_gold_exact, "invalid_spans": stats.invalid}


def _union_row(config: str, group: str, dataset: str, union: dict[str, Any]) -> dict[str, Any]:
    run, rebuilt, repro = union["run"], union["findings"], union["repro"]
    return {"config": config, "group": group, "dataset": dataset,
            "gold": run.gold, "exact": run.exact, "over": run.over, "partial": run.partial, "missed": run.missed,
            "fn": run.gold - run.exact, "recall": _precision(run.exact, run.gold),
            "edits": run.edits, "edits_tp": run.edits_tp, "edits_over": run.edits_over, "edits_fp": run.edits_fp,
            "precision": _precision(run.edits_tp, run.edits),
            "findings_exact": rebuilt.exact, "findings_fn": rebuilt.gold - rebuilt.exact,
            "findings_edits": rebuilt.edits, "findings_edits_tp": rebuilt.edits_tp,
            "findings_edits_over": rebuilt.edits_over, "findings_edits_fp": rebuilt.edits_fp,
            "findings_precision": _precision(rebuilt.edits_tp, rebuilt.edits),
            "items": repro.items, "blocked_items": repro.blocked_items,
            "adapter_failure_items": json.dumps(dict(repro.adapter_failure_items), sort_keys=True),
            "edits_same": repro.edits_same, "edits_only_in_run": repro.edits_only_in_run,
            "edits_only_in_findings": repro.edits_only_in_findings, "remask_tp": repro.remask_tp,
            "remask_over": repro.remask_over, "remask_fp": repro.remask_fp,
            "gold_status_differs": repro.gold_status_differs}


ADAPTER_ORDER = ("credsweeper", "gitleaks", "promptguard-rules", "shell-aware", "ml-v9", "ml-span")


def render(out: dict[str, Any]) -> str:
    configs = [entry["config"] for entry in out["configs"]]
    lines = ["# Stage 0 false-positive analysis", ""]
    for entry in out["configs"]:
        adapters = [f"{a['name']} {a['version']}" for d in entry["describe"] for a in d.get("adapters", [])]
        skipped = [s for d in entry["describe"] for s in d.get("skipped", [])]
        lines += [f"- **{entry['config']}**: adapters {', '.join(dict.fromkeys(adapters))}; skipped {skipped or 'none'}; "
                  f"datasets {len(entry['datasets'])}"]
    lines += ["", "Precision = findings inside one gold span / findings (identical spans counted once per rule). "
              "Solo FP: no other rule's finding overlaps it. Solo gold: no other rule's finding overlaps that gold span. "
              "FN only for the union (gold not masked exactly). An adapter's **(all rules)** row counts its rules "
              "together, solo against the other adapters.", ""]
    for group in [*GROUPS, "other"]:
        union_rows = [r for r in out["union"] if r["group"] == group and r["dataset"] == "(group)"]
        if not union_rows:
            continue
        lines += [f"## {group} ({', '.join(GROUPS.get(group, ()))})", "", "### Union", "",
                  "| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(union_rows, key=lambda r: configs.index(r["config"])):
            lines.append(f"| {r['config']} | {r['gold']} | {r['exact']} | {r['fn']} | {_fmt(r['recall'])} | {r['edits']} | "
                         f"{r['edits_tp']} | {r['edits_over']} | {r['edits_fp']} | {_fmt(r['precision'])} | "
                         f"{_fmt(r['findings_precision'])} ({r['findings_edits_tp']}/{r['findings_edits']}) | "
                         f"{r['edits_only_in_run']} ({r['remask_tp']}/{r['remask_over']}/{r['remask_fp']}) | "
                         f"{r['blocked_items']} | {r['gold_status_differs']} |")
        lines += ["", "### Per rule", "",
                  "| adapter | rule | " + " | ".join(f"{c}: {col}" for c in configs
                                                     for col in ("findings", "precision", "solo FP", "shared FP", "solo gold")) + " |",
                  "|---|---|" + "---|" * (5 * len(configs))]
        rows = [r for r in out["rules"] if r["group"] == group and r["dataset"] == "(group)"]
        keys = sorted({(r["adapter"], r["model"], r["rule_id"]) for r in rows},
                      key=lambda k: (ADAPTER_ORDER.index(k[0]) if k[0] in ADAPTER_ORDER else 99, k[2] != ALL_RULES, k[2]))
        index = {(r["config"], r["adapter"], r["model"], r["rule_id"]): r for r in rows}
        for key in keys:
            cells = []
            for config in configs:
                r = index.get((config, *key))
                cells += ([str(r["findings"]), _fmt(r["precision"]), str(r["solo_fp"]), str(r["shared_fp"]),
                           str(r["solo_gold"])] if r else ["-"] * 5)
            adapter = key[0] + (f" ({key[1]})" if key[1] else "")
            rule = f"**{key[2]}**" if key[2] == ALL_RULES else key[2]
            lines.append(f"| {adapter} | {rule} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Top 10 false-positive types (distinct FP spans of any rule, all datasets)", ""]
    for config in configs:
        rows = sorted((r for r in out["fp_types"] if r["config"] == config and r["group"] == "(all datasets)"),
                      key=lambda r: -r["fp_spans"])[:10]
        lines += [f"### {config}", "", "| # | type | FP spans | union FP edits | top rules |", "|---|---|---|---|---|"]
        lines += [f"| {n} | {r['type']} | {r['fp_spans']} | {r['union_fp_edits']} | {r['top_rules']} |"
                  for n, r in enumerate(rows, 1)]
        lines.append("")
    return "\n".join(lines) + "\n"


def write(out: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("rules", "union", "fp_types", "fp_label_kinds", "runs"):
        rows = out[name]
        with (folder / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["empty"])
            writer.writeheader()
            writer.writerows({k: _fmt(v) if isinstance(v, float) or v is None else v for k, v in row.items()}
                             for row in rows)
    (folder / "configs.json").write_text(json.dumps(out["configs"], indent=2) + "\n", encoding="utf-8")
    (folder / "report.md").write_text(render(out), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", nargs="+", action="append", required=True, metavar=("NAME", "FOLDER"),
                        help="configuration name and the folders holding its run folders")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--answer-dir", type=Path, default=ANSWER)
    args = parser.parse_args(argv)
    configs = [(entry[0], [Path(folder) for folder in entry[1:]]) for entry in args.config]
    out = analyse(configs, args.data_dir, args.answer_dir)
    write(out, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
