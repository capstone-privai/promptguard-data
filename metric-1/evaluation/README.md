# 지표 1 채점기

`data_test/`의 세션을 평가 대상 시스템에 통과시키고, `data_answer/`의 정답 span과 비교해 비밀값을 얼마나 잘 가렸는지 채점한다. PromptGuard는 별도 저장소([promptguard-demo-v0](https://github.com/capstone-privai/promptguard-demo-v0))에 있고, 채점기는 그 저장소의 `promptguard.pipeline.process_output`을 그대로 불러 쓴다. 시스템의 실행 코드를 복사하지 않으며, 에이전트나 훅, 데몬 같은 실행 환경은 띄우지 않는다. macOS와 Linux에서 Python 3.10 이상, 표준 라이브러리, 고정 버전 `credsweeper`로 돈다.

데이터를 만드는 일(비밀 주입, 원문 수집)은 [scripts/](../scripts/)가 맡고, 이 패키지는 그 결과물을 읽기만 한다.

## 실행

저장소 루트에서 실행한다. `credsweeper`가 필요하다(`pip install -r metric-1/evaluation/requirements.txt`).

```bash
python metric-1/scripts/evaluate.py validate                                   # 기본: data_test/sessions.jsonl
python metric-1/scripts/evaluate.py run --system oracle
python metric-1/scripts/evaluate.py run --system promptguard
python metric-1/scripts/evaluate.py run --system promptguard --sweep 0:1:0.1
python metric-1/scripts/evaluate.py run --system credsweeper --ml off
python metric-1/scripts/run_gitleaks.py                                        # gitleaks 탐지 결과를 runs/gitleaks/에 쓴다
python metric-1/scripts/evaluate.py run --system gitleaks --findings runs/gitleaks/sessions.jsonl
python metric-1/scripts/evaluate.py run --system promptguard --sessions metric-1/data_test/sessions_from_CredData.jsonl
python metric-1/scripts/evaluate.py run --system credsweeper --channels all --sessions metric-1/data_test/sessions_from_privesc-llm-data.jsonl
```

각 데이터셋의 특성과 점수를 읽을 때 주의할 점은 [데이터셋별 해석](#데이터셋별-해석)에 있다.

`--gold`를 생략하면 `data_test/sessions*.jsonl`에 짝지어진 `data_answer/gold*.jsonl`을 쓴다(`dataset_verify.py`와 같은 규칙). `data_test/` 밖에 있는 `sessions*.jsonl`은 같은 폴더의 `gold*.jsonl`과 짝짓는다.

`--system promptguard`는 PromptGuard 체크아웃을 다음 순서로 찾는다: `--system-root DIR`, 환경 변수 `PROMPTGUARD_ROOT`, 이 저장소 옆의 `../promptguard-demo-v0`. 그 체크아웃이 지금 가리키는 브랜치의 코드가 평가된다.

실행할 때마다 `runs/<YYYYmmdd-HHMMSS>_<system>[_<predictor>]/`가 생기고, 그 경로와 recall, precision, F2, 1,000줄당 과잉 마스킹, gold 수, 비밀 밀도가 출력된다. `runs/`는 git에 올리지 않는다.

### 옵션

| 옵션 | 대상 | 뜻 |
|---|---|---|
| `--sessions PATH` | 전부 | 세션 파일 (기본 `metric-1/data_test/sessions.jsonl`) |
| `--gold PATH` | 전부 | 정답 파일 (기본: 위의 짝짓기 규칙) |
| `--use rule_eval\|ml_eval` | run | 모든 세션의 `meta.allowed_use`에 이 용도가 있어야 실행한다. 기본은 `credsweeper --ml on` 또는 PromptGuard의 mock이 아닌 predictor면 `ml_eval`, 그 밖에는 `rule_eval` |
| `--system-root DIR` | promptguard | PromptGuard 체크아웃 경로 |
| `--predictor NAME` | promptguard | `promptguard.decision.registry`의 predictor (기본 `mock`) |
| `--threshold T` | promptguard | 모든 판단을 `confidence >= T`이면 MASK로 다시 정한다 |
| `--sweep START:STOP:STEP` | promptguard | 임계값마다 한 번씩 전체를 돌리고(양 끝 포함), PR-AUC와 고정 recall에서의 precision을 낸다 |
| `--ml on\|off` | credsweeper | CredSweeper ML 검증 (기본 off, 데모 탐지기 설정과 같음) |
| `--channels LIST\|all` | credsweeper | 검사할 채널(쉼표 구분). 기본은 PromptGuard가 처리하는 `tool_output` |
| `--findings PATH` | gitleaks (필수) | `scripts/run_gitleaks.py`가 쓴 탐지 결과. 채점하는 세션 파일에서 만든 것이어야 한다(SHA-256 확인) |
| `--out DIR` | run | 실행 폴더를 만들 상위 폴더 (기본 `runs`) |
| `--debug` | run | 원본 후보와 예측을 담은 `debug/`도 쓴다. **비밀값이 들어 있다.** |

종료 코드: `0` 정상, `1` 데이터 검증 실패 또는 용도 불일치, `2` edit 검증 실패(결과를 쓰지 않음), `3` 설정 오류.

CredSweeper의 ML 검증을 켠 평가는 `ml_eval`이다. `authored`, `recorded`, `external`에서는 허용하고, `injected`에서는 허용하지 않는다. 자동으로 선택한 용도는 `run_meta.json`의 `dataset.use`에 기록한다. `--use`를 지정하면 그 용도를 우선한다.

## 평가 대상

| system | 동작 |
|---|---|
| `promptguard` | 세션마다 `PlaceholderRegistry` 하나를 두고 item을 순서대로 `process_output`에 넣는다. `prompt` item이 오면 실제 런타임처럼 task context를 바꾼다(`build_task_context(text, turn_id)`). 첫 prompt 전에는 빈 context다. 데이터 채널은 `CHANNEL_MAP`(현재 `tool_output → stdout`)으로 시스템 채널에 대응시키고, 대응 채널이 `PROCESSED_CHANNELS`에 있을 때만 처리한다. 나머지는 그대로 통과한다. |
| `credsweeper` | 같은 채널(`tool_output`)을 CredSweeper만으로 검사해 탐지 결과를 전부 `[SECRET]`으로 가린다. PromptGuard의 URI 후처리는 일부러 적용하지 않는다. |
| `gitleaks` | `scripts/run_gitleaks.py`가 미리 돌린 gitleaks(기본 설정) 탐지 결과를 읽어 전부 `[SECRET]`으로 가린다. 채점기는 하위 프로세스를 띄우지 않으므로 gitleaks는 채점 전에 따로 돌린다. 검사 채널은 그 스크립트의 `--channels`(기본 `tool_output`)를 따른다. gitleaks는 item 전체를 한 번에 검사하므로 item별 지연 시간은 없고, 전체 검사 시간은 `run_meta.json`의 `scan_seconds`에 남는다. |
| `oracle` | 정답 span을 정확히 가린다. recall 1.0, precision 1.0이 나와야 한다. |
| `identity` | 아무것도 바꾸지 않는다. recall 0.0, precision N/A가 나와야 한다. |

현재 PromptGuard(demo-v0)는 셸 명령 출력(stdout, stderr)만 처리한다. 따라서 `prompt`, `instructions`, `tool_input` 채널의 비밀은 항상 놓친 것으로 집계되고, 채널별 recall에 그대로 드러난다. 데이터의 `tool_output`은 stdout과 stderr를 구분하지 않으므로 시스템에는 `stdout`으로 넘긴다. 채널 대응은 `CHANNEL_MAP` 한 곳에만 있으므로, 연동할 에이전트가 정해져 시스템이 처리하는 채널이 늘어나면 그 표만 바꾸면 된다.

## 데이터셋별 해석

데이터셋마다 정답이 놓인 채널, 정답 유형, 음성의 성격이 다르다. 점수는 같은 데이터셋 안에서만 비교하고, 데이터셋끼리 나란히 놓을 때는 아래 차이를 같이 적는다. 만드는 방법과 정답 규칙은 [지표 1 README](../README.md#데이터셋)와 각 변환 문서에 있다.

| 세션 파일 | origin | 정답 유형 | 정답이 있는 채널 | 주의 |
|---|---|---|---|---|
| `sessions.jsonl`, `sessions_from_example.jsonl`, `sessions_2.jsonl` | authored | 다섯 유형 모두 | 네 채널 모두 | 합성 세션. 음성도 직접 쓴 것이다 |
| `sessions_from_CredData.jsonl` | external | 다섯 유형 모두 | `tool_output`만 | precision은 하한값이다([README_CredData.md](../README_CredData.md#xf를-음성으로-쓸-때-유의할-점)) |
| `sessions_from_privesc-llm-data.jsonl` | recorded | PASSWORD, PRIVATE_KEY만 | `instructions`, `tool_input`, `tool_output` | 아래 참고 |

### privesc-llm-data

실제 에이전트 궤적에 심어 둔 값을 찾아 정답을 자동으로 만든 데이터다([README_privesc-llm-data.md](../README_privesc-llm-data.md)). 점수를 읽을 때 다음을 본다.

- **`tool_output`만 처리하는 시스템은 recall 상한이 약 0.43이다.** 정답 10,546개 중 `tool_output`에 4,565개가 있고, 나머지는 시스템 프롬프트(`instructions` 2,200개)와 에이전트가 쓴 명령(`tool_input` 3,781개)에 있다. 같은 비밀번호가 세 채널에 반복해서 나오므로, 채널별 recall(`recall_by_channel`)을 함께 본다. CredSweeper와 gitleaks를 PromptGuard와 같은 조건에서 비교하려면 기본 채널(`tool_output`)로 돌리고, 탐지기 자체의 성능을 보려면 `--channels all`로 돌린다.
- **`prompt` 채널에는 정답이 없다.** `prompt` item은 모든 세션에 같은 시작 지시문이라 PromptGuard의 task context도 세션마다 같다. 과제 설명과 로그인 계정은 `instructions`에 있다.
- **줄 단위 지표는 다른 데이터셋과 비교하지 않는다.** `tool_input`과 `tool_output`의 text는 도구 호출 인자와 도구 결과의 JSON 문자열이라, 그 안의 줄바꿈이 실제 줄바꿈이 아니라 `\n` 두 글자다. 그래서 이 두 채널의 item 117,886개는 모두 한 줄로 세고, `lines_total`(192,686)이 작게 잡힌다. 이를 분모로 쓰는 `fp_per_1k_lines`와 `density_per_1k_lines`는 이 데이터 안에서만 비교한다.
- **같은 이유로 줄 단위로 동작하는 탐지 규칙에 불리할 수 있다.** 도구 결과 전체가 한 줄이고 비밀 주변에 JSON 따옴표와 escape가 붙는다. 실제 에이전트의 셸 출력과 모양이 다르다는 점을 결과에 적는다.
- **유형별 recall은 PASSWORD와 PRIVATE_KEY만 나온다.** 나머지 유형은 `None`이다. PASSWORD는 12자 무작위 영숫자나 16자 hex라 키 이름이나 맥락 없이 값만 보고는 찾기 어렵다.
- **과잉 마스킹의 출처는 labels 파일로 나눈다.** `metric-1/labels_from_privesc-llm-data.jsonl`에는 정답에서 뺀 `password_hash`(`/etc/shadow` 해시)와 `attempted_password`(에이전트가 시도했지만 심은 값이 아닌 비밀번호)의 좌표가 있다. `per_edit.jsonl`에서 `overlaps_gold`가 false인 edit를 이 좌표와 맞추면, 과잉 마스킹이 이런 비밀번호성 문자열에서 나왔는지 다른 텍스트에서 나왔는지 나눠 볼 수 있다.
- **규모.** 세션 2,200개, item 122,286개다. 모든 채널을 검사할 때 gitleaks는 `run_gitleaks.py` 전체가 약 30초, CredSweeper(`--ml off`)는 약 40초 걸린다(Apple Silicon 노트북 기준).
- origin이 `recorded`라 `rule_eval`, `ml_eval`, `ml_train` 모두 허용된다. CredSweeper `--ml on`과 PromptGuard의 ML predictor로도 평가할 수 있다.

## 데이터 형식

[지표 1 README](../README.md#형식)의 형식을 그대로 읽는다. 채점에 쓰는 규칙은 다음과 같다.

- 세션 파일: 한 줄에 세션 하나(`session_id`, `items`, `meta`). `session_id`는 파일 안에서 유일하고, `item_id`는 세션 안에서만 유일한 0 이상의 정수다. item은 시간 순서다.
- `channel`은 `prompt`, `instructions`, `tool_input`, `tool_output` 중 하나.
- 정답 파일: 한 줄에 span 하나(`session_id`, `item_id`, `span_id`, `span: {start, end, type}`). span이 없는 item과 세션은 정답 파일에 나오지 않는다.
- `type`은 `PASSWORD`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY`, `SECRET` 중 하나(시스템의 `CandidateType`). 유형은 분석용일 뿐 성공 판정에 쓰지 않는다.
- 위치는 item `text`의 Python 문자열(코드 포인트) 인덱스이며 `start`는 포함, `end`는 포함하지 않는다. 비어 있으면 안 된다. 한 item 안의 정답 span은 겹치면 안 되고, 맞닿는 것은 괜찮다.
- `meta`는 `run_meta.json`에 요약되어 남으므로 비밀값을 넣지 않는다.

`validate`는 문제를 한꺼번에 `session / item / 메시지` 형태로 보여 준다. `run`은 항상 먼저 검증하고, 형식이 틀리거나 용도가 맞지 않으면 아무것도 실행하지 않는다. 키 집합, `span_id` 순서, origin과 용도의 일치, 정답 누락, 재생성 일치처럼 데이터 계약 전체는 `scripts/dataset_verify.py`가 검사한다.

## 채점

- 정답은 데이터셋에서만 온다. 시스템이 보지 못한 비밀도 놓친 것으로 센다.
- 채점에는 시스템이 보고한 edit(원문 좌표의 `start`, `end`, `replacement`)만 쓴다. item을 채점하기 전에 edit를 원문에 적용해 보고, 결과가 시스템의 실제 출력과 한 글자라도 다르면 종료 코드 2로 멈춘다. 후보, 예측, 감사 로그는 채점에 쓰지 않고, 출력 텍스트끼리 diff하지도 않는다.
- 정답 span의 모든 글자가 edit 합집합 안에 있으면 `full`, 한 글자도 없으면 `missed`, 그 사이면 `partial`이다. edit는 정답 span과 조금이라도 겹치면 참양성이다. 대체 문자열의 내용은 보지 않는다. 판정 예시는 [지표 1 README](../README.md#판정)에 있다.

## 지표

| 키 | 정의 |
|---|---|
| `recall` | full 정답 span / 전체 정답 span |
| `precision` | 정답과 겹치는 edit / 전체 edit |
| `f2` | `5PR / (4P + R)`. 둘 다 0이면 `0.0`, 하나라도 `None`이면 `None` |
| `pr_auc` | sweep 전용. recall 0부터 계단식으로 잰 PR 면적. 같은 recall이면 가장 높은 precision을 쓴다. 서로 다른 점이 둘 미만이면 `None` |
| `precision_at_recall` | sweep 전용. recall ≥ 0.95 / 0.99인 임계값 중 가장 높은 precision과 그 임계값 |
| `fp_per_1k_lines` | 정답과 겹치지 않는 edit / 전체 줄 수 × 1000 |
| `char_recall` | 가려진 정답 글자 수 / 전체 정답 글자 수 |
| `partial_rate`, `missed_rate` | partial / missed 정답 span의 비율 |
| `recall_by_type`, `recall_by_channel` | 유형별, 채널별 recall. 해당 그룹에 정답이 없으면 `None` |
| `latency_ms` | 시스템이 처리한 item의 p50 / p95 / max / n (선형 보간 백분위). 같은 기계에서 잰 실행끼리만 비교한다 |
| `density_per_1k_lines`, `lines_total`, `composition` | 1,000줄당 정답 수, 전체 줄 수(`count("\n")`에 끝 줄이 개행 없이 끝나면 1을 더함), 유형별·채널별 정답 수 |

분모가 0인 비율은 `None`(`N/A`로 표시)이다. PR-AUC와 고정 recall에서의 precision은 임계값 격자에 따라 달라지므로 `metrics.json`에 쓴 임계값을 함께 남긴다. mock predictor는 confidence를 항상 1.0으로 내므로 sweep이 한 점으로 모이고, 두 요약 지표는 `None`이 된다. 정상이다.

## 실행 폴더

| 파일 | 내용 |
|---|---|
| `run_meta.json` | 시작 시각, 이 저장소의 git commit·branch(`git`), 평가한 PromptGuard 체크아웃의 경로·commit·branch(`system_git`), 시스템 설정, 임계값, 세션·정답 파일의 경로와 SHA-256, 용도(`use`), 세션·item·정답 수, meta 요약, 버전, 플랫폼 |
| `metrics.json` | 위 지표. sweep이면 `thresholds`, `summary`, 임계값별 `points` |
| `per_span.jsonl` | 정답 span 하나당 한 줄: `session_id`, `item_id`, `span_id`, `start`, `end`, `type`, `channel`, `status`, `exposed_chars` (sweep이면 `threshold` 추가) |
| `per_edit.jsonl` | edit 하나당 한 줄: `session_id`, `item_id`, `start`, `end`, `overlaps_gold` (sweep이면 `threshold` 추가) |
| `pr_curve.csv`, `pr_curve.png` | sweep 전용. PNG는 선택 의존성인 `matplotlib`이 있을 때만 |
| `report.md` | 위 내용을 사람이 읽기 좋게 정리한 요약 |
| `debug/items.jsonl` | `--debug` 전용. 원본 후보와 예측, **비밀값 포함** |

`debug/` 밖의 파일에는 원문 텍스트가 들어가지 않는다. git 정보는 `git`을 실행하지 않고 `.git`에서 직접 읽으므로 `dirty`는 항상 `null`이다.

## 구조와 규칙

```text
metric-1/
  scripts/evaluate.py   진입점 (metric-1/을 sys.path에 넣고 evaluation.cli.main 실행)
  evaluation/
    dataset/   형식, 로더, 검증기              (promptguard import 금지)
    scorer/    edit 검증, span 채점            (promptguard import 금지)
    report/    집계, sweep, 메타, 파일 쓰기     (promptguard import 금지)
    adapters/  평가 대상 시스템, 체크아웃 탐색  (promptguard를 import하는 유일한 곳)
    run.py     데이터 → 어댑터 → 채점 → 집계
    cli.py     명령행
```

- `evaluation/adapters/`는 `promptguard.pipeline`, `promptguard.redaction.engine`, `promptguard.redaction.placeholders`, `promptguard.decision.registry`, `promptguard.decision.base`, `promptguard.common.schema`만 import할 수 있다. `promptguard/`는 `evaluation`을 import하지 않는다. `evaluation/` 어디서도 `subprocess`나 네트워크 모듈을 import하지 않는다. `tests/test_dependency_rules.py`가 이 규칙을 검사한다.
- 채점기는 자체 `Edit` 타입을 쓴다. 어댑터가 시스템 edit를 필드 단위로 옮기고, `tests/test_system_contract.py`가 필드 이름, `GOLD_TYPES`, `CHANNELS`가 시스템 및 `dataset_build.py`와 같은지 확인한다. 의미가 바뀌면 edit 검증이 잡아낸다.
- 여기서 PromptGuard 코드를 고치지 않는다. 평가에 시스템 변경이 필요하면 [SYSTEM_REQUESTS.md](SYSTEM_REQUESTS.md)에 적는다.
- 테스트 fixture에는 실제 서비스 형식의 비밀(클라우드 키, API 키 접두사, PEM 블록)을 넣지 않는다. `DB_PASSWORD=mysecret123` 같은 값을 쓴다.

## 테스트

```bash
cd metric-1 && python -m unittest discover -s evaluation/tests -t .
```

`credsweeper`가 없으면 CredSweeper와 PromptGuard 테스트를, PromptGuard 체크아웃을 찾지 못하면 PromptGuard 테스트를 건너뛴다.

## 알려진 한계

- sweep은 임계값마다 탐지를 다시 돌린다. 단순하지만 큰 데이터에서는 느리다. 탐지 결과를 캐시하려면 시스템 변경이 필요하므로 `SYSTEM_REQUESTS.md`를 거친다.
- 과제 맥락에 따른 KEEP 판단을 끈 상태("KEEP disabled")의 지표 1은 시스템이 그 모드를 제공할 때까지 잴 수 없다.
- 실행 폴더 이름은 초 단위 현지 시각이다. 동시에 실행하면 `-2`, `-3`, …이 붙는다.
