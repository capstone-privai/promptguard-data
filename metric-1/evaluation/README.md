# 지표 1 채점기

`data_test/`의 세션을 평가 대상 시스템에 통과시키고, `data_answer/`의 정답 span과 비교해 비밀값을 얼마나 잘 가렸는지 채점한다. PromptGuard는 별도 저장소([promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0))에 있다. 그 시스템은 Claude Code Native Mod가 모델로 가는 텍스트를 CredSweeper worker에 보내고, 찾은 값마다 `[PASSWORD_1]` 같은 placeholder를 덮어쓴다. 채점기는 그 체크아웃의 worker 코드(`src/credsweeper-adapter/worker.py`)를 프로세스 안에서 그대로 불러 탐지하고, Mod의 치환 규칙(`src/native-mod/hooks/register.mjs`의 `placeholder`, `redactText`)대로 텍스트를 바꾼다. Claude Code, MCP bridge, HTTP 서버는 띄우지 않는다. macOS와 Linux에서 Python 3.10 이상, 표준 라이브러리, 시스템과 같은 고정 버전 `credsweeper`(1.19.0)로 돈다.

데이터를 만드는 일(비밀 주입, 원문 수집)은 [scripts/](../scripts/)가 맡고, 이 패키지는 그 결과물을 읽기만 한다.

## 실행

저장소 루트에서 실행한다. `credsweeper`가 필요하다(`pip install -r metric-1/evaluation/requirements.txt`). PromptGuard 체크아웃의 `.venv/bin/python`에는 같은 버전이 이미 설치되어 있으므로 그것으로 돌려도 된다.

```bash
python metric-1/scripts/evaluate.py validate                                   # 기본: data_test/sessions.jsonl
python metric-1/scripts/evaluate.py run --system oracle
python metric-1/scripts/evaluate.py run --system promptguard
python metric-1/scripts/evaluate.py run --system credsweeper --ml off
python metric-1/scripts/run_gitleaks.py                                        # gitleaks 탐지 결과를 runs/gitleaks/에 쓴다
python metric-1/scripts/evaluate.py run --system gitleaks --findings runs/gitleaks/sessions.jsonl
python metric-1/scripts/evaluate.py run --system promptguard --sessions metric-1/data_test/sessions_from_CredData.jsonl
python metric-1/scripts/evaluate.py run --system credsweeper --channels all --sessions metric-1/data_test/sessions_from_privesc-llm-data.jsonl
```

### 전체 조합 한 번에 돌리기

`scripts/run_all.py`는 데이터셋(`data_test/sessions*.jsonl` 전부) × 시스템 5개 × CredSweeper ML on/off를 모두 펼쳐 돌린다. CredSweeper와 gitleaks는 항상 네 채널을 모두 검사하고(`--channels all`), 채널별 결과는 각 실행의 `recall_by_channel`로 본다. gitleaks는 데이터셋마다 `run_gitleaks.py --channels all`을 먼저 돌린다. 데이터셋이 허용하지 않는 용도이거나 의존성(credsweeper, gitleaks, PromptGuard 체크아웃과 그 체크아웃이 고정한 CredSweeper 버전)이 없는 조합은 이유를 남기고 건너뛴다.

```bash
python metric-1/scripts/run_all.py --dry-run                 # 조합 목록만 출력
python metric-1/scripts/run_all.py --jobs 4                  # 전부 실행
python metric-1/scripts/run_all.py --datasets sessions_2 --systems credsweeper gitleaks
```

결과는 `runs/all_<YYYYmmdd-HHMMSS>/`에 모인다. 조합마다 실행 폴더 하나, `logs/`에 각 조합의 출력, `gitleaks/`에 탐지 결과, `summary.csv`와 `summary.md`에 조합별 상태와 주요 지표가 있다. 모든 조합이 성공하면 종료 코드 0, 실패하거나 건너뛴 조합이 있으면 1이다. 축을 좁히는 옵션은 `--help`에 있다.

각 데이터셋의 특성과 점수를 읽을 때 주의할 점은 [데이터셋별 해석](#데이터셋별-해석)에 있다.

`--gold`를 생략하면 `data_test/sessions*.jsonl`에 짝지어진 `data_answer/gold*.jsonl`을 쓴다(`dataset_verify.py`와 같은 규칙). `data_test/` 밖에 있는 `sessions*.jsonl`은 같은 폴더의 `gold*.jsonl`과 짝짓는다.

`--system promptguard`는 PromptGuard 체크아웃을 다음 순서로 찾는다: `--system-root DIR`, 환경 변수 `PROMPTGUARD_CLAUDE_ROOT`(지표 2와 같다), 이 저장소 옆의 `../promptguard-claude-demoV0`. 그 체크아웃이 지금 가리키는 브랜치의 코드가 평가된다. 설치된 `credsweeper`가 체크아웃의 `requirements.txt`에 고정된 버전과 다르면 설정 오류로 멈춘다.

실행할 때마다 `runs/<YYYYmmdd-HHMMSS>_<system>[_<설정>]/`가 생기고, 그 경로와 recall, precision, F2, 1,000줄당 과잉 마스킹, gold 수, 비밀 밀도가 출력된다. `runs/`는 git에 올리지 않는다.

### 옵션

| 옵션 | 대상 | 뜻 |
|---|---|---|
| `--sessions PATH` | 전부 | 세션 파일 (기본 `metric-1/data_test/sessions.jsonl`) |
| `--gold PATH` | 전부 | 정답 파일 (기본: 위의 짝짓기 규칙) |
| `--use rule_eval\|ml_eval` | run | 모든 세션의 `meta.allowed_use`에 이 용도가 있어야 실행한다. 기본은 `credsweeper --ml on`이면 `ml_eval`, 그 밖에는 `rule_eval` |
| `--system-root DIR` | promptguard | promptguard-claude-demoV0 체크아웃 경로 |
| `--ml on\|off` | credsweeper | CredSweeper ML 검증 (기본 off, PromptGuard worker 설정과 같음) |
| `--channels LIST\|all` | credsweeper | 검사할 채널(쉼표 구분). 기본은 PromptGuard가 처리하는 `prompt,instructions,tool_output` |
| `--findings PATH` | gitleaks (필수) | `scripts/run_gitleaks.py`가 쓴 탐지 결과. 채점하는 세션 파일에서 만든 것이어야 한다(SHA-256 확인) |
| `--out DIR` | run | 실행 폴더를 만들 상위 폴더 (기본 `runs`) |
| `--debug` | run | 시스템의 원본 탐지 결과를 담은 `debug/`도 쓴다. **비밀값이 들어 있을 수 있다.** |

종료 코드: `0` 정상, `1` 데이터 검증 실패 또는 용도 불일치, `2` edit 검증 실패(결과를 쓰지 않음), `3` 설정 오류.

CredSweeper의 ML 검증을 켠 평가는 `ml_eval`이다. `authored`, `recorded`, `external`에서는 허용하고, `injected`에서는 허용하지 않는다. 자동으로 선택한 용도는 `run_meta.json`의 `dataset.use`에 기록한다. `--use`를 지정하면 그 용도를 우선한다.

## 평가 대상

| system | 동작 |
|---|---|
| `promptguard` | 세션마다 Mod의 placeholder 장부 하나를 두고 item을 순서대로 처리한다. 처리하는 채널(아래 표)의 item은 worker의 `Adapter.scan`으로 탐지하고, Mod처럼 뒤쪽 탐지부터 placeholder로 바꾼다. 같은 값은 세션 안에서 같은 placeholder가 된다. 나머지 채널은 그대로 통과한다. |
| `credsweeper` | 같은 채널(`prompt`, `instructions`, `tool_output`)을 CredSweeper 기본 규칙만으로 검사해 탐지 결과를 전부 `[SECRET]`으로 가린다. PromptGuard worker의 추가 규칙(`rules-demo.yaml`)과 걸러내기(무해한 변수명, 유형 없는 `Credential` 규칙)는 일부러 적용하지 않는다. |
| `gitleaks` | `scripts/run_gitleaks.py`가 미리 돌린 gitleaks(기본 설정) 탐지 결과를 읽어 전부 `[SECRET]`으로 가린다. 채점기는 하위 프로세스를 띄우지 않으므로 gitleaks는 채점 전에 따로 돌린다. 검사 채널은 그 스크립트의 `--channels`(기본은 PromptGuard와 같은 세 채널)를 따른다. gitleaks는 item 전체를 한 번에 검사하므로 item별 지연 시간은 없고, 전체 검사 시간은 `run_meta.json`의 `scan_seconds`에 남는다. |
| `oracle` | 정답 span을 정확히 가린다. recall 1.0, precision 1.0이 나와야 한다. |
| `identity` | 아무것도 바꾸지 않는다. recall 0.0, precision N/A가 나와야 한다. |

### PromptGuard가 처리하는 채널

데이터 채널은 Mod가 텍스트를 가로채는 훅에 다음처럼 대응한다. 대응은 `promptguard_adapter.py`의 `CHANNEL_MAP` 한 곳에 있다.

| 데이터 채널 | Mod의 훅 | worker에 넘기는 `source` |
|---|---|---|
| `prompt` | `prompt.submit` (사용자 프롬프트) | `user_prompt` |
| `instructions` | `prompt.context` (CLAUDE.md) | `claude_md` |
| `tool_output` | `tool.call` (도구 결과) | `tool_result` |
| `tool_input` | 없음. 모델이 쓴 도구 인자는 가리지 않는다 | - |

- `source`는 탐지 결과에 붙는 이름일 뿐이고 탐지 방식은 채널과 상관없이 같다. Mod는 도구마다 `bash_stdout`, `read_result` 같은 이름을 쓰지만 데이터의 `tool_output`은 도구를 구분하지 않으므로 `tool_result`로 넘긴다.
- `tool_input` 채널의 비밀은 항상 놓친 것으로 집계되고, 채널별 recall에 그대로 드러난다.
- `--append-system-prompt`로 넣은 지침은 Mod 훅에 보이지 않는다(시스템 README의 제한 사항). `instructions`는 CLAUDE.md로 들어간다고 본다.
- **fail-open.** worker 결과가 안전하지 않거나(오류 목록, 잘못된 오프셋 단위, 범위 밖이거나 겹치는 span) worker가 예외를 내면 Mod의 훅이 예외를 던진다. Mod의 훅에는 `.catch`가 없어 Claude Code가 그 훅을 건너뛰므로, 그 텍스트는 원문 그대로 모델에 간다. 채점기도 그 item을 원문 그대로 두고, 그런 item 수를 `run_meta.json`의 `system.failed_open_items`에 남긴다. 실패 전에 매긴 placeholder 번호는 Mod처럼 장부에 남는다. 예: CredSweeper의 `PEM Private Key` 규칙이 빈 span을 내면 worker가 결과 전체를 `INVALID_OFFSET_RANGE`로 거부하고, 개인 키가 든 텍스트가 통째로 나간다(`sessions_from_CredData.jsonl`에서 item 6개).

## 데이터셋별 해석

데이터셋마다 정답이 놓인 채널, 정답 유형, 음성의 성격이 다르다. 점수는 같은 데이터셋 안에서만 비교하고, 데이터셋끼리 나란히 놓을 때는 아래 차이를 같이 적는다. 만드는 방법과 정답 규칙은 [지표 1 README](../README.md#데이터셋)와 각 변환 문서에 있다.

| 세션 파일 | origin | 정답 유형 | 정답이 있는 채널 | 주의 |
|---|---|---|---|---|
| `sessions.jsonl`, `sessions_from_example.jsonl`, `sessions_2.jsonl` | authored | 다섯 유형 모두 | 네 채널 모두 | 합성 세션. 음성도 직접 쓴 것이다 |
| `sessions_from_CredData.jsonl` | external | 다섯 유형 모두 | `tool_output`만 | precision은 하한값이다([README_CredData.md](../README_CredData.md#xf를-음성으로-쓸-때-유의할-점)) |
| `sessions_from_privesc-llm-data.jsonl` | recorded | PASSWORD, PRIVATE_KEY만 | `instructions`, `tool_input`, `tool_output` | 아래 참고 |
| `sessions_from_Nemotron-PII.jsonl` | external | PASSWORD, SECRET, TOKEN | `prompt`, `tool_output` (반씩) | 자연어 문서 속 비밀. `tool_output`만 처리하는 시스템은 `prompt` 절반을 놓친다([README_Nemotron-PII.md](../README_Nemotron-PII.md)) |
| `sessions_from_openhands-feedback.jsonl` | external | 다섯 유형 (47개) | `tool_input`, `tool_output` | 실제 사용자 세션. 정답 후보를 CredSweeper와 gitleaks가 냈으므로 recall은 상한값이다. 과잉 마스킹을 본다([README_openhands-feedback.md](../README_openhands-feedback.md)) |
| `sessions_from_SWE-Gym.jsonl` | external | TOKEN (2개) | `tool_output` | 거의 음성. 실제 코딩 에이전트 트래픽의 1,000줄당 과잉 마스킹을 본다([README_SWE-Gym.md](../README_SWE-Gym.md)) |
| `sessions_from_noseyparker.jsonl` | external | 다섯 유형 | `tool_output` | 한두 줄짜리 예시라 줄 단위 지표는 크게 나온다. 형식별 recall을 본다([README_noseyparker.md](../README_noseyparker.md)) |

### privesc-llm-data

실제 에이전트 궤적에 심어 둔 값을 찾아 정답을 자동으로 만든 데이터다([README_privesc-llm-data.md](../README_privesc-llm-data.md)). 점수를 읽을 때 다음을 본다.

- **PromptGuard의 recall 상한은 약 0.64다.** 정답 10,624개 중 `tool_output`에 4,604개, 시스템 프롬프트(`instructions`)에 2,200개, 에이전트가 쓴 명령(`tool_input`)에 3,820개가 있고, Mod는 `tool_input`을 가리지 않는다. `tool_output`만 처리하는 시스템이라면 약 0.43이다. 같은 비밀번호가 세 채널에 반복해서 나오므로, 채널별 recall(`recall_by_channel`)을 함께 본다. CredSweeper와 gitleaks를 PromptGuard와 같은 조건에서 비교하려면 기본 채널(`prompt`, `instructions`, `tool_output`)로 돌리고, 탐지기 자체의 성능을 보려면 `--channels all`로 돌린다.
- **`prompt` 채널에는 정답이 없다.** `prompt` item은 모든 세션에 같은 시작 지시문이다. 과제 설명과 로그인 계정은 `instructions`에 있다.
- **줄 단위 지표는 다른 데이터셋과 비교하지 않는다.** `tool_input`과 `tool_output`의 text는 도구 호출 인자와 도구 결과의 JSON 문자열이라, 그 안의 줄바꿈이 실제 줄바꿈이 아니라 `\n` 두 글자다. 그래서 이 두 채널의 item 117,886개는 모두 한 줄로 세고, `lines_total`(192,686)이 작게 잡힌다. 이를 분모로 쓰는 `fp_per_1k_lines`와 `density_per_1k_lines`는 이 데이터 안에서만 비교한다.
- **같은 이유로 줄 단위로 동작하는 탐지 규칙에 불리할 수 있다.** 도구 결과 전체가 한 줄이고 비밀 주변에 JSON 따옴표와 escape가 붙는다. 실제 에이전트의 셸 출력과 모양이 다르다는 점을 결과에 적는다.
- **유형별 recall은 PASSWORD와 PRIVATE_KEY만 나온다.** 나머지 유형은 `None`이다. PASSWORD는 대부분 12자 무작위 영숫자나 16자 hex라 키 이름이나 맥락 없이 값만 보고는 찾기 어렵다.
- **과잉 마스킹의 출처는 labels 파일로 나눈다.** `metric-1/labels_from_privesc-llm-data.jsonl`에는 정답에서 뺀 `password_hash`(`/etc/shadow` 해시), `username_occurrence`(사용자 이름과 같은 비밀번호가 경로나 사용자명 필드에 나온 것), `attempted_password`(에이전트가 시도했지만 심은 값이 아닌 비밀번호)의 좌표가 있다. `per_edit.jsonl`에서 `overlaps_gold`가 false인 edit를 이 좌표와 맞추면, 과잉 마스킹이 이런 비밀번호성 문자열에서 나왔는지 다른 텍스트에서 나왔는지 나눠 볼 수 있다.
- **규모.** 세션 2,200개, item 122,286개다. 모든 채널을 검사할 때 gitleaks는 `run_gitleaks.py` 전체가 약 30초, CredSweeper(`--ml off`)는 약 40초 걸린다(Apple Silicon 노트북 기준).
- origin이 `recorded`라 `rule_eval`, `ml_eval`, `ml_train` 모두 허용된다. CredSweeper `--ml on`으로도 평가할 수 있다.

## 데이터 형식

[지표 1 README](../README.md#형식)의 형식을 그대로 읽는다. 채점에 쓰는 규칙은 다음과 같다.

- 세션 파일: 한 줄에 세션 하나(`session_id`, `items`, `meta`). `session_id`는 파일 안에서 유일하고, `item_id`는 세션 안에서만 유일한 0 이상의 정수다. item은 시간 순서다.
- `channel`은 `prompt`, `instructions`, `tool_input`, `tool_output` 중 하나.
- 정답 파일: 한 줄에 span 하나(`session_id`, `item_id`, `span_id`, `span: {start, end, type}`). span이 없는 item과 세션은 정답 파일에 나오지 않는다.
- `type`은 `PASSWORD`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY`, `SECRET` 중 하나. 유형은 분석용일 뿐 성공 판정에 쓰지 않는다. PromptGuard의 placeholder 유형(`API_KEY`, `AWS_KEY`, `JWT` 등)과는 따로 정한 것이다.
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
| `fp_per_1k_lines` | 정답과 겹치지 않는 edit / 전체 줄 수 × 1000 |
| `char_recall` | 가려진 정답 글자 수 / 전체 정답 글자 수 |
| `partial_rate`, `missed_rate` | partial / missed 정답 span의 비율 |
| `recall_by_type`, `recall_by_channel` | 유형별, 채널별 recall. 해당 그룹에 정답이 없으면 `None` |
| `latency_ms` | 시스템이 처리한 item의 p50 / p95 / max / n (선형 보간 백분위). 같은 기계에서 잰 실행끼리만 비교한다 |
| `density_per_1k_lines`, `lines_total`, `composition` | 1,000줄당 정답 수, 전체 줄 수(`count("\n")`에 끝 줄이 개행 없이 끝나면 1을 더함), 유형별·채널별 정답 수 |

분모가 0인 비율은 `None`(`N/A`로 표시)이다. PromptGuard는 confidence 점수 없이 탐지하면 곧바로 가리므로 임계값 sweep(PR-AUC, 고정 recall에서의 precision)은 없다.

## 실행 폴더

| 파일 | 내용 |
|---|---|
| `run_meta.json` | 시작 시각, 이 저장소의 git commit·branch(`git`), 평가한 PromptGuard 체크아웃의 경로·commit·branch(`system_git`), 시스템 설정(PromptGuard는 처리 채널과 `failed_open_items` 포함), 세션·정답 파일의 경로와 SHA-256, 용도(`use`), 세션·item·정답 수, meta 요약, 버전, 플랫폼 |
| `metrics.json` | 위 지표 |
| `per_span.jsonl` | 정답 span 하나당 한 줄: `session_id`, `item_id`, `span_id`, `start`, `end`, `type`, `channel`, `status`, `exposed_chars` |
| `per_edit.jsonl` | edit 하나당 한 줄: `session_id`, `item_id`, `start`, `end`, `overlaps_gold` |
| `report.md` | 위 내용을 사람이 읽기 좋게 정리한 요약 |
| `debug/items.jsonl` | `--debug` 전용. PromptGuard는 item마다 worker 결과(위치, 유형, 규칙, 값의 HMAC)와 fail-open 이유. 원문 위치를 알려 주므로 공유하지 않는다 |

`debug/` 밖의 파일에는 원문 텍스트가 들어가지 않는다. git 정보는 `git`을 실행하지 않고 `.git`에서 직접 읽으므로 `dirty`는 항상 `null`이다.

## 구조와 규칙

```text
metric-1/
  scripts/evaluate.py   진입점 (metric-1/을 sys.path에 넣고 evaluation.cli.main 실행)
  evaluation/
    dataset/   형식, 로더, 검증기              (시스템을 불러오지 않음)
    scorer/    edit 검증, span 채점            (시스템을 불러오지 않음)
    report/    집계, 메타, 파일 쓰기           (시스템을 불러오지 않음)
    adapters/  평가 대상 시스템, 체크아웃 탐색  (system_root.py가 PromptGuard worker를 불러오는 유일한 곳)
    run.py     데이터 → 어댑터 → 채점 → 집계
    cli.py     명령행
```

- PromptGuard 체크아웃의 코드는 `adapters/system_root.py`만 불러온다(`worker.py`를 import). `dataset/`, `scorer/`, `report/`는 시스템을 불러오지 않는다. 예전 시스템(promptguard-demo-v0)의 `promptguard` 패키지는 어디서도 import하지 않는다. `evaluation/` 어디서도(테스트 제외) `subprocess`나 네트워크 모듈을 import하지 않는다. `tests/test_dependency_rules.py`가 이 규칙을 검사한다.
- Mod의 치환은 JavaScript라서 어댑터의 `ModSession`이 같은 규칙으로 다시 구현한다. `tests/test_system_contract.py`가 Node로 실제 `register.mjs`를 돌려, 같은 worker 결과에 같은 텍스트가 나오는지(실패할 입력이면 둘 다 실패하는지) 확인한다. `CHANNEL_MAP`의 `source`가 Mod에 있는지, `GOLD_TYPES`와 `CHANNELS`가 `dataset_build.py`와 같은지도 확인한다. 채점기는 자체 `Edit` 타입을 쓰고, edit 검증이 출력과 어긋나는 edit를 잡아낸다.
- 여기서 PromptGuard 코드를 고치지 않는다. 평가에 시스템 변경이 필요하면 [SYSTEM_REQUESTS.md](SYSTEM_REQUESTS.md)에 적는다.
- 테스트 fixture에는 실제 서비스 형식의 비밀(클라우드 키, API 키 접두사, PEM 블록)을 넣지 않는다. `DB_PASSWORD=mysecret123` 같은 값을 쓴다.

## 테스트

```bash
cd metric-1 && python -m unittest discover -s evaluation/tests -t .
```

`credsweeper`가 없으면 CredSweeper 테스트를, PromptGuard 체크아웃을 찾지 못하거나 설치된 `credsweeper`가 체크아웃의 고정 버전과 다르면 PromptGuard 테스트를, `node`가 없으면 Mod 대조 테스트를 건너뛴다.

## 알려진 한계

- worker의 HTTP·MCP 전송 계층은 재현하지 않는다. 실제 Mod에서는 요청 본문이 8MB를 넘거나 bridge가 5초 안에 답을 받지 못하면 훅이 실패해 원문이 나가지만(fail-open), 채점기는 그런 item도 끝까지 탐지한다. `latency_ms.max`가 5,000ms에 가까우면 이 차이를 의심한다.
- 지연 시간은 worker의 탐지와 치환만 잰 값이다. Mod와 bridge를 오가는 시간은 들어가지 않는다.
- 실행 폴더 이름은 초 단위 현지 시각이다. 같은 초에 같은 설정으로 실행하면 `-2`, `-3`, …이 붙는다.
