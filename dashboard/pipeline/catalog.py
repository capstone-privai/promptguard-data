"""What the UI calls things: dataset names and descriptions, what their sub-groups are, type and channel names.

Display only: the service writes these into index.json on every cycle, so an edit here shows up without evaluating
anything again. What the counts are grouped by lives in taxonomy.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline.taxonomy import CHANNELS, GROUPS, OTHER_TYPE, TYPES

TYPE_LABELS = {"PASSWORD": "비밀번호", "TOKEN": "토큰", "ACCESS_KEY": "액세스 키", "PRIVATE_KEY": "개인 키",
               "SECRET": "시크릿", OTHER_TYPE: "미분류"}
CHANNEL_LABELS = {"prompt": "사용자 프롬프트", "instructions": "지침", "tool_output": "도구 결과"}


@dataclass(frozen=True)
class DatasetInfo:
    label: str
    about: str  # one or two sentences; the UI shows it only on request
    group_label: str  # what the dataset's sub-groups are, e.g. "시나리오"


# Keyed by the sessions file stem, in the order the UI lists them (metric-detection/README.md#데이터셋).
DATASETS: dict[str, DatasetInfo] = {
    "sessions": DatasetInfo(
        "내장 코퍼스", "dataset_build.py에 직접 쓴 합성 세션 12개. 환경 파일, 트레이스백, HTTP 헤더, git 이력, "
        "Kubernetes Secret, PEM 키, 비밀이 없는 음성 예시를 담았다.", "시나리오"),
    "sessions_from_example": DatasetInfo(
        "템플릿 예시", "templates/example.jsonl의 placeholder를 채워 만든 합성 세션 2개.", "시나리오"),
    "sessions_2": DatasetInfo(
        "에이전트 세션 v2", "에이전트 작업 상황을 7개 범주(설정 파일, 명령 출력, 로그, 에이전트 명령, 자연어, 약한·테스트 "
        "비밀번호, 비밀 없음)로 나눠 쓴 합성 세션 43개.", "범주"),
    "sessions_from_CredData": DatasetInfo(
        "CredData", "Samsung CredData의 소스 파일 조각. 정답은 모두 도구 결과에 있고, 라벨이 없는 비밀이 섞여 있어 "
        "precision은 하한값이다.", "파일 종류"),
    "sessions_from_privesc-llm-data": DatasetInfo(
        "privesc-llm-data", "리눅스 권한 상승 에이전트의 실제 궤적. 환경에 심어 둔 비밀번호와 SSH 키가 정답이다. 도구 "
        "결과가 JSON 문자열이라 줄바꿈이 \\n 두 글자로 들어 있다.", "시나리오"),
    "sessions_from_Nemotron-PII": DatasetInfo(
        "Nemotron-PII", "합성 업무 문서(설정 파일, API 문서, 비밀번호 안내 메일, 양식 등). 비정형 문서는 사용자 프롬프트, "
        "정형 문서는 도구 결과로 넣었다.", "문서 분야"),
    "sessions_from_openhands-feedback": DatasetInfo(
        "openhands-feedback", "OpenHands 실제 사용자 세션. 업스트림이 민감정보를 지워 거의 음성이라 과잉 마스킹을 본다. "
        "정답 후보를 CredSweeper와 gitleaks가 냈으므로 recall은 상한값이다.", "피드백"),
    "sessions_from_SWE-Gym": DatasetInfo(
        "SWE-Gym", "코딩 에이전트 궤적(moto, MONAI, pandas 등). 정답이 2개뿐인 음성 데이터라 실제 코딩 트래픽의 과잉 "
        "마스킹을 본다.", "저장소"),
    "sessions_from_noseyparker": DatasetInfo(
        "Nosey Parker", "Nosey Parker 내장 규칙 189개의 예시와 음성 예시. 수백 종 서비스의 토큰 형식을 시험한다.",
        "예시 종류"),
}


def dataset_info(stem: str) -> DatasetInfo:
    """Registered display data, or a plain default for a sessions file the registry does not know yet."""
    if stem in DATASETS:
        return DATASETS[stem]
    return DatasetInfo(stem.removeprefix("sessions_from_").removeprefix("sessions_") or stem, "", "그룹")


def dataset_order(stems: list[str]) -> list[str]:
    known = [stem for stem in DATASETS if stem in stems]
    return known + sorted(stem for stem in stems if stem not in DATASETS)


def as_json() -> dict[str, Any]:
    """Every name the UI shows, for index.json."""
    return {
        "datasets": {stem: {"label": info.label, "about": info.about, "group_label": info.group_label}
                     for stem, info in DATASETS.items()},
        "types": {type_: TYPE_LABELS.get(type_, type_) for type_ in TYPES},
        "channels": {channel: CHANNEL_LABELS.get(channel, channel) for channel in CHANNELS},
    }


assert set(GROUPS) == set(DATASETS), "taxonomy.GROUPS and catalog.DATASETS must list the same datasets"
