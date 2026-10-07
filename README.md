# PromptGuard 평가 데이터

PromptGuard의 평가 지표별 데이터셋을 관리한다. 지금은 **지표 1: 탐지·마스킹 성능** 데이터만 있다. 코딩 에이전트가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾는지를 span 단위로 채점한다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-1/](metric-1/) | 탐지·마스킹 평가 데이터, 정답 span, 생성·검증 도구, 채점기 | 합성 파일럿 v0.1, 사람 검토 대기 |
| [metric-2/](metric-2/) | 작업 성공 평가 데이터 | 준비용 폴더 |
| [metric-3/](metric-3/) | KEEP 판단 정확도 평가 데이터 | 준비용 폴더 |

이 저장소는 데이터, 생성·검증 도구, 채점기를 맡는다. 평가 대상 시스템(PromptGuard)은 [promptguard-demo-v0](https://github.com/capstone-privai/promptguard-demo-v0)에 있고, 채점기가 그 체크아웃을 불러 쓴다.

## 지표 1

데이터셋 구성, 형식, 사용 용도, 생성·검증 방법, 채점 기준은 [metric-1/README.md](metric-1/README.md)에 있다. 채점기 옵션과 지표의 정확한 정의는 [metric-1/evaluation/README.md](metric-1/evaluation/README.md)에 있다.
