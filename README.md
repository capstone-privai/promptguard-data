# PromptGuard 평가 데이터

PromptGuard의 시스템 평가 지표별 데이터셋을 관리한다. 현재는 **지표 1: 탐지 성능**을 위한 최소 합성 테스트셋 v0.1이 있다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-1/](metric-1/) | 탐지·마스킹 성능 평가 데이터, 정답 span, 생성·검증 도구 | 합성 파일럿 v0.1, 사람 검토 대기 |
| [metric-2/](metric-2/) | 작업 성공 평가 데이터 | 준비용 폴더 |
| [metric-3/](metric-3/) | KEEP 판단 정확도 평가 데이터 | 준비용 폴더 |
| [etc/](etc/) | 이전 후보 레코드 규격·예제·변환·검증 도구 | 원본 보관 |

## 지표 1 시작하기

- [데이터 설명과 실행 방법](metric-1/README.md)
- [원문과 정답을 함께 읽는 검토 문서](metric-1/REVIEW.md)
- [평가기 입력 JSONL](metric-1/sessions.jsonl)
- [구성 통계와 데이터 해시](metric-1/manifest.json)

12개 세션, 51개 입력, 32개 정답 span으로 구성된다. 실제 Codex rollout이 아닌 합성 세션이며, 평가 연결 점검과 라벨 검토용이다. 정답은 탐지기 후보와 독립적으로 주입 시 기록한다.

평가 실행 코드는 [promptguard-demo-v0의 feat/evaluation-metric1 브랜치](https://github.com/capstone-privai/promptguard-demo-v0/tree/feat/evaluation-metric1)에 있다. 이 저장소는 데이터와 생성·검증 보조 도구를 담당한다.

## 보관 원칙

2026-10-04 구조를 재정리하면서 이전 기본 브랜치 커밋 `eef78917dc74fa41c881ff995ace05c9f51cb178`의 파일 7개를 내용 변경 없이 `etc/`로 옮겼다. 이전 이력도 유지한다.

새로 추가한 지표 1 자료의 비밀값은 전부 합성값이다. 버전과 해시를 함께 관리하고, 라벨을 변경할 때는 변경 사유를 남긴다.
