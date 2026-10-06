# PromptGuard 평가 데이터

PromptGuard의 평가 지표별 데이터셋을 관리한다. 지금은 **지표 1: 탐지·마스킹 성능** 데이터만 있다. 에이전트(opencode)가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾는지를 span 단위로 채점한다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [metric-1/](metric-1/) | 탐지·마스킹 평가 데이터, 정답 span, 생성·검증 도구, 채점기 | 합성 파일럿 v0.1, 사람 검토 대기 |
| [metric-2/](metric-2/) | 작업 성공 평가 데이터 | 준비용 폴더 |
| [metric-3/](metric-3/) | KEEP 판단 정확도 평가 데이터 | 준비용 폴더 |

이 저장소는 데이터, 생성·검증 도구, 채점기를 맡는다. 평가 대상 시스템(PromptGuard)은 [promptguard-demo-v0](https://github.com/capstone-privai/promptguard-demo-v0)에 있고, 채점기가 그 체크아웃을 불러 쓴다.

## 지표 1

### 폴더

| 경로 | 내용 |
|---|---|
| `metric-1/data_test/` | 평가기 입력(세션). 정답은 들어 있지 않다 |
| `metric-1/data_answer/` | 정답 span(gold) |
| `metric-1/scripts/` | 생성(`build_dataset.py`, `convert_creddata.py`), 검증(`verify_dataset.py`), 용도 정책(`dataset_policy.py`), 채점(`evaluate.py`) |
| [`metric-1/evaluation/`](metric-1/evaluation/README.md) | 채점기: 시스템 어댑터, span 채점, 지표 집계, 결과 파일 |
| `metric-1/templates/` | placeholder로 세션을 쓰는 템플릿과 [작성법](metric-1/templates/README.md) |
| `metric-1/manual_review/` | CredData X/F 행을 다시 판정하는 로컬 검수 페이지 |
| [`metric-1/README_CredData.md`](metric-1/README_CredData.md) | CredData 변환 방법, 변환 규칙, 우리 라벨 기준과 다른 점 |

### 데이터셋

| 입력 (`data_test/`) | 정답 (`data_answer/`) | 세션 | item | gold span | origin |
|---|---|---|---|---|---|
| `sessions.jsonl` | `gold.jsonl` | 12 | 51 | 32 | authored |
| `sessions_from_example.jsonl` | `gold_from_example.jsonl` | 2 | 9 | 10 | authored |
| `sessions_from_CredData.jsonl` | `gold_from_CredData.jsonl` | 11,030 | 25,345 | 15,596 | external |

- **내장 코퍼스**(`sessions.jsonl`): `build_dataset.py`에 직접 쓴 합성 세션이다. 환경 파일, 트레이스백, HTTP 헤더, git 이력, Kubernetes Secret, PEM 키, 비밀이 없는 음성 예시 등 12개 상황을 담았다.
- **템플릿 예시**(`sessions_from_example.jsonl`): [templates/example.jsonl](metric-1/templates/example.jsonl)의 placeholder를 채워 만든 세션이다.
- **CredData**(`sessions_from_CredData.jsonl`): [Samsung CredData](https://github.com/Samsung/CredData)의 파일 조각을 세션 형식으로 바꾼 것이다. **평가 전용이며 학습에 쓰지 않는다.** 파일 본문은 원본 저장소의 라이선스를 따르므로 git에 올리지 않고 각자 다시 만든다([README_CredData.md](metric-1/README_CredData.md)).

합성 데이터의 비밀값은 모두 결정적으로 만든 가짜 값이다. 정답은 탐지기 결과와 상관없이, 값을 끼워 넣는 순간에 위치를 기록해 만든다.

### 형식

세션 하나는 `session_id`, `items`, `meta`로 이루어진다. item은 에이전트와 오간 텍스트 한 덩어리다.

```json
{"session_id": "m1-01-node-env",
 "items": [{"item_id": 0, "turn_id": "t0", "channel": "prompt", "text": "로컬 API가 인증 오류로 ..."},
           {"item_id": 1, "turn_id": "t0", "channel": "tool_output", "text": "NODE_ENV=development\n..."}],
 "meta": {"origin": "authored", "allowed_use": ["rule_eval", "ml_eval", "ml_train"], "...": "..."}}
```

`channel`은 그 텍스트가 opencode의 어느 지점을 지나는지 나타낸다.

| channel | 내용 | opencode 플러그인 훅 |
|---|---|---|
| `prompt` | 사용자 메시지 | `chat.message` |
| `instructions` | AGENTS.md, CLAUDE.md, config의 instructions | `experimental.chat.system.transform` |
| `tool_input` | 모델이 쓴 도구 인자 (예: bash 명령) | `tool.execute.before` |
| `tool_output` | 모델에 돌아가는 도구 결과. bash는 stdout과 stderr가 합쳐져 나온다 | `tool.execute.after` |

정답 파일은 한 줄에 span 하나다. span이 없는 item은 정답 파일에 나오지 않는다.

```json
{"session_id": "m1-01-node-env", "item_id": 1, "span_id": 0, "span": {"start": 71, "end": 87, "type": "PASSWORD"}}
```

- `start`, `end`: item `text` 안의 위치. Python 문자열 인덱스(코드 포인트) 기준이며 `end`는 포함하지 않는다.
- `type`: `PASSWORD`, `SECRET`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY` 중 하나.

### 사용 용도

세션마다 `meta.origin`과 `meta.allowed_use`가 붙는다. 용도 표는 [dataset_policy.py](metric-1/scripts/dataset_policy.py) 한 곳에만 정의되어 있고, 검증 단계에서 이 표와 다르면 실패한다. 데이터를 쓰는 쪽은 `require_use(sessions, "ml_train")`처럼 용도를 확인한 뒤 쓴다.

| origin | 뜻 | allowed_use |
|---|---|---|
| `authored` | 비밀이 자연스럽게 놓일 맥락에 직접 쓴 세션 | rule_eval, ml_eval, ml_train |
| `recorded` | 미리 비밀을 심어 둔 환경에서 실제로 실행한 에이전트 세션 | rule_eval, ml_eval, ml_train |
| `injected` | 비밀용으로 쓰지 않은 궤적에 비밀을 끼워 넣은 세션 | rule_eval |
| `external` | 외부 벤치마크(CredData) | rule_eval, ml_eval |

### 생성과 검증

저장소 루트에서 실행한다.

```bash
python metric-1/scripts/build_dataset.py                       # 내장 코퍼스
python metric-1/scripts/build_dataset.py --template metric-1/templates/example.jsonl --origin authored
python metric-1/scripts/convert_creddata.py --creddata ../CredData

python metric-1/scripts/verify_dataset.py <sessions 파일> [--gold <gold 파일>] [--creddata ../CredData]
```

검증 항목은 스키마, origin과 용도의 일치, span 범위와 겹침, 정답 누락(같은 비밀값이 다른 곳에도 나오는데 정답에서 빠졌는지), 재생성 시 바이트 단위 일치다.

생성 스크립트는 세션을 `metric-1/data_test/`, 정답을 `metric-1/data_answer/`에 쓴다. 검증 스크립트는 `data_test/sessions*.jsonl`에 짝지어진 `data_answer/gold*.jsonl`을 자동으로 찾는다.

### 채점

```bash
pip install -r metric-1/evaluation/requirements.txt
python metric-1/scripts/evaluate.py run --system promptguard [--sessions <sessions 파일>] [--system-root ../promptguard-demo-v0]
python metric-1/scripts/evaluate.py run --system credsweeper|oracle|identity [--sessions <sessions 파일>]
```

결과는 `runs/<시각>_<system>/`에 쌓인다. 세션의 `meta.allowed_use`에 실행 용도(`rule_eval`, ML predictor면 `ml_eval`)가 없으면 실행하지 않는다. 옵션, 채널 대응, 지표 정의는 [metric-1/evaluation/README.md](metric-1/evaluation/README.md)에 있다.
