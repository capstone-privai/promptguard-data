"""The axes the dashboard counts along: secret types, channels, outcomes, and each dataset's sub-groups.

Changing anything here changes the counts, so this file is part of the detection results' key (runner.SCORING_CODE)
and every commit is evaluated again. Names and descriptions shown in the UI live in catalog.py, which is not.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from typing import Any

from evaluation.dataset.schema import GOLD_TYPES, SCORED_CHANNELS

OTHER_TYPE = "OTHER"
TYPES: tuple[str, ...] = (*GOLD_TYPES, OTHER_TYPE)
CHANNELS: tuple[str, ...] = SCORED_CHANNELS

# Cube columns: gold spans by outcome (evaluation.scorer.span_scoring.SpanStatus), then edits by class.
STATUSES: tuple[str, ...] = ("exact", "over", "partial", "missed")
EDIT_CLASSES: tuple[str, ...] = ("tp", "wide", "fp")  # inside one gold span / overlaps but spills / touches none

# PromptGuard placeholder kinds (pgdetector.core.CANONICAL_TYPES) → gold type. Only edits that touch no gold span
# use it, so that a false positive still counts under a type. CREDENTIAL names no kind and stays OTHER.
KIND_TO_TYPE = {
    "PASSWORD": "PASSWORD",
    "PRIVATE_KEY": "PRIVATE_KEY",
    "TOKEN": "TOKEN", "JWT": "TOKEN", "GITHUB_TOKEN": "TOKEN", "SLACK_TOKEN": "TOKEN",
    "AWS_KEY": "ACCESS_KEY",
    "API_KEY": "SECRET", "SECRET": "SECRET",
}
_PLACEHOLDER = re.compile(r"\[([A-Z0-9_]+?)_\d+\]")

# A dataset with more sub-groups than this keeps the largest ones and folds the rest into OTHER_GROUP.
MAX_GROUPS = 30
OTHER_GROUP = "기타"


def placeholder_type(replacement: str) -> str:
    """Gold type named by the first `[KIND_n]` placeholder in an edit's replacement, else OTHER."""
    found = _PLACEHOLDER.search(replacement)
    return KIND_TO_TYPE.get(found.group(1), OTHER_TYPE) if found else OTHER_TYPE


Grouper = Callable[[Mapping[str, Any]], str]


def _meta(key: str, names: Mapping[str, str] | None = None, strip: str = "") -> Grouper:
    def pick(meta: Mapping[str, Any]) -> str:
        value = meta.get(key)
        if value is None or value == "":
            return "-"
        text = str(value).removeprefix(strip)
        return (names or {}).get(text, text)
    return pick


_FILE_KINDS = {
    "코드": {".go", ".py", ".rb", ".java", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".php", ".cs", ".c", ".h",
             ".cc", ".cpp", ".hpp", ".kt", ".scala", ".vue", ".rs", ".ex", ".exs", ".swift", ".m", ".groovy", ".pl",
             ".lua", ".dart", ".r", ".clj", ".erl", ".hs", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".sql"},
    "설정": {".json", ".yml", ".yaml", ".toml", ".conf", ".cfg", ".ini", ".properties", ".env", ".xml", ".tf",
             ".tfvars", ".j2", ".tpl", ".tmpl", ".template", ".gradle", ".config", ".plist", ".example", ".sample",
             ".dist", ".lock"},
    "문서": {".md", ".markdown", ".txt", ".rst", ".asciidoc", ".adoc", ".html", ".htm", ".tex", ".org", ".log"},
    "키·인증서": {".key", ".pem", ".crt", ".cer", ".p12", ".pfx", ".der", ".pub", ".jks", ".keystore", ".gpg",
                ".asc", ".ppk", ".rsa"},
}


def _file_kind(meta: Mapping[str, Any]) -> str:
    extension = os.path.splitext(str(meta.get("creddata_file") or ""))[1].lower()
    return next((kind for kind, extensions in _FILE_KINDS.items() if extension in extensions), OTHER_GROUP)


_CATEGORIES = {"config": "설정 파일", "command_output": "명령 출력", "log": "로그", "tool_input": "에이전트 명령",
               "natural_language": "자연어", "weak_or_test": "약한·테스트 비밀번호", "negative": "비밀 없음"}

# Sessions file stem → how a session's meta names its sub-group (catalog.DATASETS says what the sub-groups are).
GROUPS: dict[str, Grouper] = {
    "sessions": _meta("scenario"),
    "sessions_from_example": _meta("scenario"),
    "sessions_2": _meta("category", _CATEGORIES),
    "sessions_from_CredData": _file_kind,
    "sessions_from_privesc-llm-data": _meta("scenario"),
    "sessions_from_Nemotron-PII": _meta("domain"),
    "sessions_from_openhands-feedback": _meta("feedback", {"positive": "긍정", "negative": "부정"}),
    "sessions_from_SWE-Gym": _meta("group_id", strip="swe-gym-"),
    "sessions_from_noseyparker": _meta("example_kind", {"example": "양성 예시", "negative_example": "음성 예시"}),
}


def group_of(stem: str) -> Grouper:
    """The sub-group function of a dataset; a dataset not listed groups by meta.category or meta.scenario."""
    if stem in GROUPS:
        return GROUPS[stem]

    def fallback(meta: Mapping[str, Any]) -> str:
        return next((str(meta[key]) for key in ("category", "scenario") if meta.get(key)), "-")

    return fallback
