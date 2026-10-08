# PromptGuard 평가 데이터

PromptGuard의 평가 지표별 데이터셋을 관리한다. 지금은 **지표 1: 탐지·마스킹 성능**과 **지표 2: 작업 성공** 데이터가 있다. 지표 1은 코딩 에이전트가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾는지를 span 단위로 채점하고, 지표 2는 비밀을 가렸을 때 에이전트가 과제를 여전히 해내는지를 Claude Code로 직접 돌려 잰다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-1/](metric-1/) | 탐지·마스킹 평가 데이터, 정답 span, 생성·검증 도구, 채점기 | 합성 파일럿 v0.1(사람 검토 대기) + 외부 소스 6개 |
| [metric-2/](metric-2/) | 마스킹 조건별 과제 성공 평가: 과제 26개, Claude Code 실행기, 결과 | Sonnet 5.5로 3회 반복한 결과 있음 |
| [metric-3/](metric-3/) | KEEP 판단 정확도 평가 데이터 | 준비용 폴더 |
| [docs/](docs/) | 분석 문서: [기존 시스템의 recall이 낮은 이유](docs/README_baseline-recall.md), [새 외부 소스로 본 기존 시스템의 약점](docs/README_baseline-new-sources.md) | 지표 1 채점 결과(2026-10-08) 기준 |

이 저장소는 데이터, 생성·검증 도구, 채점기를 맡는다. 평가 대상 시스템(PromptGuard)은 [promptguard-demo-v0](https://github.com/capstone-privai/promptguard-demo-v0)에 있고, 지표 1 채점기가 그 체크아웃을 불러 쓴다. 지표 2는 Claude Code에 붙는 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)의 Native Mod를 그대로 쓴다.

## 지표 1

데이터셋 구성, 형식, 사용 용도, 생성·검증 방법, 채점 기준은 [metric-1/README.md](metric-1/README.md)에 있다. 채점기 옵션과 지표의 정확한 정의는 [metric-1/evaluation/README.md](metric-1/evaluation/README.md)에 있다. 기존 시스템(CredSweeper, gitleaks)의 약점 분석은 [docs/](docs/)에 있다.

## 지표 2

과제 26개를 Claude Code로 풀게 하면서, PromptGuard Native Mod 뒤의 탐지기만 바꿔 세 조건(마스킹 없음, 정답 비밀만 마스킹, PromptGuard)을 비교한다. 과제 구성, 바로 실행하는 방법(`m2.py play`), 결과와 실패 사례는 [metric-2/README.md](metric-2/README.md)에 있다.
