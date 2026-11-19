# PromptGuard 평가 데이터

PromptGuard의 평가 지표별 데이터셋을 관리한다. 지금은 **metric-detection: 탐지·마스킹 성능**, **metric-task: 작업 성공**, **metric-latency: 탐지기 호출 지연**이 있다. metric-detection은 코딩 에이전트가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾는지를 span 단위로 채점하고, metric-task는 비밀을 가렸을 때 에이전트가 과제를 여전히 해내는지를 Claude Code로 직접 돌려 잰다.

탐지 평가 데이터는 v0.1 → v2 → v3로 바뀌었고, 지금 기준은 **v3**(CredData-trajectory test)다. 버전마다 무엇이 바뀌었는지는 아래 [평가 데이터 버전](#평가-데이터-버전)에 있다. v0.1의 탐지 데이터 9종, 작업 과제 135개, 지연 워크로드와 ML 평가 분할·표본의 목적·구성·규모·해석상 주의점은 [평가 데이터 전체 안내](EVALUATION_DATA.md)에 있다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-detection/](metric-detection/) | 탐지·마스킹 평가 데이터, 정답 span, 생성·검증 도구, 채점기 | 평가 데이터 v3: CredData-trajectory test(정답 1,889 span). v0.1의 9종(합성 3 + 외부 소스 6)은 실제 트래픽 오탐과 이전 결과 재현에 쓴다 |
| [metric-task/](metric-task/) | 마스킹 조건별 과제 성공과 서버 누출 평가: 과제 26개, Claude Code 실행기, API 요청 기록 프록시, 결과 | Sonnet 5.5로 3회 반복한 결과 + 요청 기록을 켠 시험 실행(10개 × 3조건) |
| [metric-latency/](metric-latency/) | 탐지기 호출 지연 평가기: 탐지기를 HTTP 블랙박스로 띄워 합성 입력, Final Guard 재생, Mod 호출 기록 재생으로 잰다 | 시스템 앙상블과 어댑터별 첫 측정 |
| [dashboard/](dashboard/) | 평가 대시보드: 서버가 PromptGuard `main`을 따라가며 커밋마다 metric-detection, metric-latency를 돌리고, 사람이 돌린 metric-task 배치와 함께 웹으로 보여 준다 | `main`의 커밋 7개(탐지기 상태 3가지) 평가 |
| [demo/](demo/) | 시연 화면: Mod가 탐지기를 부를 때마다 입력 채널과 원문, 모듈별 탐지 스팬과 그 합집합, 가린 뒤 모델로 가는 텍스트를 실시간으로 보여 준다 | 실제 Mod 훅으로 재구성 텍스트 일치 확인 |
| [metric-detection/docs/](metric-detection/docs/) | 분석 문서: [기존 시스템의 recall이 낮은 이유](metric-detection/docs/README_baseline-recall.md), [새 외부 소스로 본 기존 시스템의 약점](metric-detection/docs/README_baseline-new-sources.md), [탐지기 구성별 성능](metric-detection/docs/README_ensemble.md) | 앞의 두 편은 이전 시스템으로 잰 2026-10-08 결과, 구성별 성능은 현재 시스템으로 잰 2026-10-14 결과 |

이 저장소는 데이터, 생성·검증 도구, 채점기를 맡는다. 평가 대상 시스템(PromptGuard)은 Claude Code에 붙는 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)이다. metric-detection 채점기는 그 체크아웃의 탐지기(`src/detector`의 앙상블)를 불러 쓰고 Native Mod의 치환 규칙을 따르며, metric-task는 Native Mod를 그대로 쓴다. 이 저장소는 평가만 맡는다. 어떤 탐지 모듈(ML 포함)을 켜고 어떻게 합칠지는 PromptGuard 저장소가 정하고, 채점기와 대시보드는 체크아웃에 설정된 그대로 돌린다. [metric-detection/docs/](metric-detection/docs/)의 분석 문서 중 baseline 두 편은 이전 시스템(promptguard-demo-v0)으로 잰 결과다.

## 평가 데이터 버전

탐지·마스킹 평가(metric-detection)의 데이터와 채점 기준은 세 번 바뀌었다. 버전이 다르면 수치를 서로 비교하지 않는다. 같은 시스템(PromptGuard 668c2c1, ML 끔)도 버전에 따라 값이 다르다.

| 버전 | 기간 | 탐지 데이터 | 채점 | 668c2c1 recall / precision / F2 | 프로토타입 F2 |
|---|---|---|---|---|---|
| v0.1 | ~2026-11-16 | 9종: 합성 3(내장 코퍼스, 템플릿 예시, 에이전트 세션 v2) + 외부 소스 6(CredData, privesc-llm-data, Nemotron-PII, openhands-feedback, SWE-Gym, Nosey Parker) | exact recall, edit precision. 모든 커밋을 Mod의 Python 포트 하나로 채점 | (데이터셋별) | - |
| v2 | 2026-11-17 ~ 11-19 | CredData-trajectory test: 세션 559, 채점 정답 2,034 span / 고유 값 682 | 다 가린 정답 기준 recall, 글자 기준 precision, F2. 커밋마다 그 커밋의 Native Mod(Node) | 0.892 / 0.569 / 0.801 | 0.816 |
| **v3** | 2026-11-19 ~ | CredData-trajectory test: 세션은 v2와 같음, 채점 정답 1,889 span / 고유 값 663, 채점 제외 127 span / 19값 | v2 + 채점 제외 자리, 공백만 남은 정답은 다 가린 것으로 셈 | 0.906 / 0.550 / 0.802 | 0.844 |

### v0.1: 합성 파일럿과 외부 소스 9종

처음 만든 탐지 데이터다. 직접 작성한 합성 세션 3종(사람 검토 대기)과 외부 데이터를 변환한 6종이다. 데이터셋마다 다른 상황(저장소 파일 속 비밀, 에이전트 실행 기록, 자연어 문서, 실제 사용자 세션의 과잉 마스킹, 서비스별 토큰 형식)을 시험하며, 표는 데이터셋 목적별로 따로 읽는다. 데이터셋별 구성과 규모는 [EVALUATION_DATA.md](EVALUATION_DATA.md)와 [metric-detection/README.md](metric-detection/README.md)에 있다.

- 채점: 정답 span의 글자를 정확히 다 가린 것만 찾은 것으로 세는 exact recall, 정답 span 하나 안에 든 edit의 비율인 edit precision.
- 치환: 모든 커밋을 Native Mod의 Python 포트 하나로 바꿨다. 그래서 커밋마다 다른 placeholder·재마스킹·실패 처리 규칙이 반영되지 않았다.
- 지금 쓰는 곳: openhands-feedback, SWE-Gym은 실제 트래픽 오탐(1,000줄당 오탐) 측정에 그대로 쓴다. 나머지는 이전 결과를 재현할 때만 쓴다. [metric-detection/docs/](metric-detection/docs/)의 분석 문서와 대시보드의 이전 결과가 이 버전으로 잰 값이다.

### v2: CredData-trajectory test로 바꿈

탐지 데이터를 **CredData-trajectory test** 하나로 바꿨다. CredData를 저장소·component 단위로 나눈 split(creddata-v1)의 test 쪽 원본 파일 전체에 값을 심은 작업 공간을 만들고, Claude Code가 그 작업(코드 분석, 문서 작성, 리팩터링, 테스트 작성, 한·영 지시문)을 실제로 푼 세션 기록이다. 에이전트가 실제로 주고받은 텍스트로 재며, ML 학습 데이터(train 쪽)와 원본 저장소가 겹치지 않는다. 만드는 법은 [creddata_tasks/README.md](metric-detection/templates/creddata_tasks/README.md)와 [creddata_eval_set.py](metric-detection/scripts/creddata_eval_set.py)에 있다.

- 데이터: `metric-detection/data_test/sessions_from_CredData-trajectory.jsonl`(세션 559, sha256 `2c856d91…`)과 `metric-detection/data_answer/gold_from_CredData-trajectory.jsonl`. 채점 채널(prompt, instructions, tool_output)의 정답은 2,034 span, 고유 값 682개다.
- 채점(090122b, ece457b): recall = 다 가린 정답 span(exact + over) / 정답 span, precision = 가린 글자 중 정답 글자의 비율, F2 = 5PR/(4P+R). 예전 exact recall과 edit precision은 summary.csv에 같이 남긴다. 각 커밋은 그 커밋의 detector와 그 커밋의 Native Mod(`register.mjs`를 Node로 실행, [node_mod.py](metric-detection/evaluation/adapters/node_mod.py))로 채점한다.
- 결과: 커밋 × ML 모델 행렬을 [creddata_matrix.py](metric-detection/scripts/creddata_matrix.py)로 잰다. 탐지 결과를 저장해 두므로 채점 기준만 바뀌면 `rescore --from-detections`로 detector 없이 다시 채점한다.

### v3: 라벨 규칙 수정과 채점 제외 (현재)

2026-11-19에 라벨 규칙을 고치고(URL의 `password@host:` 뒤 포트, 대입의 왼쪽 이름, 번역 파일의 화면 문구, 정답 감사에서 나온 틀린 값 13개), CredData-trajectory 정답을 다시 만들었다. 규칙은 [LABELING.md](metric-detection/LABELING.md), 바뀐 수는 [README_CredData.md](metric-detection/README_CredData.md)에 있다.

- 채점 제외: 세션은 과제 목록을 고정했을 때 만든 것이라, 규칙이 바뀌어 정답이 아니게 된 슬롯에 심은 값이 세션 텍스트에 남아 있다. 정답 파일은 그 값의 모든 등장을 `"excluded": "slot_no_longer_gold"` 행으로 표시한다(채점 채널 127 span, 고유 값 19개, 6,142자). 채점기는 이 자리를 정답도 오탐도 아닌 것으로 본다. 가리지 않아도 놓친 것이 아니고, 가려도 그 글자를 precision의 가린 글자에 넣지 않는다.
- 공백: 정답 span에서 가리지 않은 글자가 공백·줄바꿈뿐이면(줄마다 가린 PEM 본문) 다 가린 것으로 센다.
- 데이터: 세션 파일은 v2와 같다. 정답은 2,441 span(채점 대상 1,889, 고유 값 663)에 채점 제외 150행이다. `gold_from_CredData-trajectory.jsonl` sha256 `a593cf70…e8083`이다. 이 정답 파일은 `"excluded"` 행을 읽는 v3 채점기가 있어야 한다.
- 결과: [summary.md](metric-detection/results/creddata-trajectory/summary.md). v2보다 recall은 행마다 약 1.5%p 오르고 precision은 약 2%p 내려간다. 순위는 같다.
- 한계: 채점기의 Mod 드라이버(`mod_driver.mjs`)는 Mod에 환경 변수를 넘기지 않는다. 그래서 각 커밋의 기본 설정만 잴 수 있고, `PG_REMASK_SHORT` 같은 기본값이 아닌 Mod 설정은 따로 넘겨야 한다.

### 데이터 파일과 이전 버전

탐지 데이터 파일(`metric-detection/data_test/`, `data_answer/`, `labels_from_CredData.jsonl`)은 비밀 형식 문자열이 들어 있어 git에 올리지 않는다. 서버의 작업 폴더에는 v3가 들어 있고, v2와 v3 파일은 `runs/eval-data-versions/{v2,v3}/`에 같은 상대 경로와 `SHA256SUMS`로 보관한다. v2로 다시 재려면 v2 파일과 v2 채점기(ece457b)를 함께 쓴다. 행렬의 채점 결과는 `runs/creddata-traj-eval/results/`(v2)와 `results-v3/`(v3)에 따로 있으며, v3 표를 다시 만들 때는 `creddata_matrix.py report --results runs/creddata-traj-eval/results-v3`를 준다.

## metric-detection

데이터셋 구성(v0.1의 9종), 형식, 사용 용도, 생성·검증 방법, 채점 기준은 [metric-detection/README.md](metric-detection/README.md)에 있다. CredData-trajectory test(v2, v3)의 결과는 [results/creddata-trajectory/summary.md](metric-detection/results/creddata-trajectory/summary.md)에 있다. 채점기 옵션과 지표의 정확한 정의는 [metric-detection/evaluation/README.md](metric-detection/evaluation/README.md)에 있다. 기존 시스템(CredSweeper, gitleaks)의 약점 분석은 [metric-detection/docs/](metric-detection/docs/)에 있다.

## metric-task

과제 26개를 Claude Code로 풀게 하면서, PromptGuard Native Mod 뒤의 탐지기만 바꿔 세 조건(마스킹 없음, 정답 비밀만 마스킹, PromptGuard)을 비교한다. 실행마다 로컬 기록 프록시가 Anthropic API로 나간 요청 본문을 남기고, 과제의 비밀이 서버에 도착했는지와 요청의 어느 자리(시스템 프롬프트, 도구 결과 등)로 갔는지를 잰다. 과제 구성, 바로 실행하는 방법(`m2.py play`), 결과와 실패 사례는 [metric-task/README.md](metric-task/README.md)에, 결과를 읽는 기준은 [metric-task/EVALUATION.md](metric-task/EVALUATION.md)에 있다.

## metric-latency

PromptGuard의 탐지기가 그 순간 받은 텍스트를 검사하는 시간을 탐지기 호출(`POST /scan-batch`) 단위로 잰다. 평가기는 시스템 코드를 import하지 않고 탐지기를 worker의 HTTP 프로토콜로만 다룬다. 워크로드(합성 입력, metric-task 요청 기록으로 재생한 Final Guard 호출, metric-task에서 기록한 Mod 호출), 실행 방법, 평가기가 시스템에 기대는 것은 [metric-latency/README.md](metric-latency/README.md)에 있다.
