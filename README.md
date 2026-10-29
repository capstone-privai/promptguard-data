# PromptGuard 평가 데이터

PromptGuard의 평가 지표별 데이터셋을 관리한다. 지금은 **metric-detection: 탐지·마스킹 성능**, **metric-task: 작업 성공**, **metric-latency: 탐지기 호출 지연**이 있다. metric-detection은 코딩 에이전트가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾는지를 span 단위로 채점하고, metric-task는 비밀을 가렸을 때 에이전트가 과제를 여전히 해내는지를 Claude Code로 직접 돌려 잰다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-detection/](metric-detection/) | 탐지·마스킹 평가 데이터, 정답 span, 생성·검증 도구, 채점기 | 합성 파일럿 v0.1(사람 검토 대기) + 외부 소스 6개 |
| [metric-task/](metric-task/) | 마스킹 조건별 과제 성공과 서버 누출 평가: 과제 26개, Claude Code 실행기, API 요청 기록 프록시, 결과 | Sonnet 5.5로 3회 반복한 결과 + 요청 기록을 켠 시험 실행(10개 × 3조건) |
| [metric-latency/](metric-latency/) | 탐지기 호출 지연 평가기: 탐지기를 HTTP 블랙박스로 띄워 합성 입력, Final Guard 재생, Mod 호출 기록 재생으로 잰다 | 시스템 앙상블과 어댑터별 첫 측정 |
| [dashboard/](dashboard/) | 평가 대시보드: 서버가 PromptGuard `main`을 따라가며 커밋마다 metric-detection, metric-latency를 돌리고, 사람이 돌린 metric-task 배치와 함께 웹으로 보여 준다 | `main`의 커밋 7개(탐지기 상태 3가지) 평가 |
| [demo/](demo/) | 시연 화면: Mod가 탐지기를 부를 때마다 입력 채널과 원문, 모듈별 탐지, 앙상블 투표, 가린 뒤 모델로 가는 텍스트를 실시간으로 보여 준다 | 실제 Mod 훅으로 재구성 텍스트 일치 확인 |
| [metric-detection/docs/](metric-detection/docs/) | 분석 문서: [기존 시스템의 recall이 낮은 이유](metric-detection/docs/README_baseline-recall.md), [새 외부 소스로 본 기존 시스템의 약점](metric-detection/docs/README_baseline-new-sources.md), [탐지기 구성별 성능](metric-detection/docs/README_ensemble.md) | 앞의 두 편은 이전 시스템으로 잰 2026-10-08 결과, 구성별 성능은 현재 시스템으로 잰 2026-10-14 결과 |

이 저장소는 데이터, 생성·검증 도구, 채점기를 맡는다. 평가 대상 시스템(PromptGuard)은 Claude Code에 붙는 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)이다. metric-detection 채점기는 그 체크아웃의 탐지기(`src/detector`의 앙상블)를 불러 쓰고 Native Mod의 치환 규칙을 따르며, metric-task는 Native Mod를 그대로 쓴다. 이 저장소는 평가만 맡는다. 어떤 탐지 모듈(ML 포함)을 켜고 어떻게 합칠지는 PromptGuard 저장소가 정하고, 채점기와 대시보드는 체크아웃에 설정된 그대로 돌린다. [metric-detection/docs/](metric-detection/docs/)의 분석 문서 중 baseline 두 편은 이전 시스템(promptguard-demo-v0)으로 잰 결과다.

## metric-detection

데이터셋 구성, 형식, 사용 용도, 생성·검증 방법, 채점 기준은 [metric-detection/README.md](metric-detection/README.md)에 있다. 채점기 옵션과 지표의 정확한 정의는 [metric-detection/evaluation/README.md](metric-detection/evaluation/README.md)에 있다. 기존 시스템(CredSweeper, gitleaks)의 약점 분석은 [metric-detection/docs/](metric-detection/docs/)에 있다.

## metric-task

과제 26개를 Claude Code로 풀게 하면서, PromptGuard Native Mod 뒤의 탐지기만 바꿔 세 조건(마스킹 없음, 정답 비밀만 마스킹, PromptGuard)을 비교한다. 실행마다 로컬 기록 프록시가 Anthropic API로 나간 요청 본문을 남기고, 과제의 비밀이 서버에 도착했는지와 요청의 어느 자리(시스템 프롬프트, 도구 결과 등)로 갔는지를 잰다. 과제 구성, 바로 실행하는 방법(`m2.py play`), 결과와 실패 사례는 [metric-task/README.md](metric-task/README.md)에, 결과를 읽는 기준은 [metric-task/EVALUATION.md](metric-task/EVALUATION.md)에 있다.

## metric-latency

PromptGuard의 탐지기가 그 순간 받은 텍스트를 검사하는 시간을 탐지기 호출(`POST /scan-batch`) 단위로 잰다. 평가기는 시스템 코드를 import하지 않고 탐지기를 worker의 HTTP 프로토콜로만 다룬다. 워크로드(합성 입력, metric-task 요청 기록으로 재생한 Final Guard 호출, metric-task에서 기록한 Mod 호출), 실행 방법, 평가기가 시스템에 기대는 것은 [metric-latency/README.md](metric-latency/README.md)에 있다.
