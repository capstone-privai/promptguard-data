# ML 학습용 LLM 템플릿

[ML 학습용 합성 데이터 계획](../../docs/README_ml-train-plan.md)의 3단계 장치다. 카드(템플릿 하나의 작업 지시서)를 뽑고, Claude가 Message Batches API로 카드마다 placeholder 템플릿을 쓰고, 검사를 통과한 템플릿만 모은다. 템플릿을 데이터로 만드는 것은 [ml_train_build.py](../../scripts/ml_train_build.py)다([작성법](../README.md#ml-학습용-템플릿-ml_train_buildpy)).

| 파일 | 내용 | git |
|---|---|---|
| `card_config.toml` | 카드의 목표 분포(계획 3절): 문맥 유형 × 비밀 유형, kind, 채널, 반복, 언어, 도구 형식, 크기, 어려운 음성, 경계 규칙, 분포 이동 test | 올림 |
| `prompt_v1.md` | Claude에 주는 시스템 프롬프트. 고치면 파일 이름과 `ml_train_write.PROMPT_VERSION`을 함께 올린다 | 올림 |
| `cards.jsonl`, `cards_pilot.jsonl` | 뽑은 카드. 설정과 코드에서 바이트 단위로 다시 만들어진다 | 안 올림 |
| `batches/NAME.json` | batch id, 카드 파일 sha256, 프롬프트 버전, 요청 custom_id. 본문은 없다 | 올림 |
| `raw/` | 응답 원문과 거절 사유. 거절된 응답에는 모델이 쓴 리터럴 비밀이 있을 수 있다 | 안 올림 |
| `NAME.jsonl` | 통과한 템플릿. placeholder만 있고 값은 없다. 다시 만들 수 없는 원본이라 이 저장소에 커밋한다(본 생성분 약 10MB). 커밋 전에 gitleaks로 한 번 더 본다 | 올림 |

## 순서

저장소 루트에서 실행한다. API 키는 `ANTHROPIC_API_KEY`나 `ant auth login` 프로필에서 읽는다. `anthropic` SDK가 필요하다(`pip install anthropic`).

파일럿과 본 생성은 **같은 이름**(아래 예의 `v1`)을 쓴다. `submit`은 그 이름으로 이미 통과한 카드를 건너뛰므로, 본 생성은 파일럿에서 통과한 카드를 다시 만들지 않는다. 파일럿 뒤에 프롬프트를 고쳤다면 `prompt_v2.md`를 만들고(`ml_train_write.PROMPT_VERSION`도 올린다) 이름도 `v2`로 바꿔 처음부터 다시 한다. 한 이름 안에 다른 프롬프트로 쓴 템플릿이 섞이지 않게 하기 위해서다.

```bash
# 1. 카드: 전체 2,490장과, 그중 split·문맥 비율을 지킨 파일럿 100장
python metric-detection/scripts/ml_train_cards.py
python metric-detection/scripts/ml_train_cards.py --limit 100 --out metric-detection/templates/ml_train/cards_pilot.jsonl

# 2. 파일럿 (약 $6). requests는 API를 부르지 않고 요청만 확인한다
python metric-detection/scripts/ml_train_write.py requests metric-detection/templates/ml_train/cards_pilot.jsonl --out /tmp/pilot_requests.jsonl
python metric-detection/scripts/ml_train_write.py submit metric-detection/templates/ml_train/cards_pilot.jsonl --name v1
python metric-detection/scripts/ml_train_write.py collect v1 --wait
python metric-detection/scripts/ml_train_write.py process v1 --cards metric-detection/templates/ml_train/cards_pilot.jsonl
# 거절된 카드만 다시: submit -> collect -> process를 같은 이름으로 다시 돌린다

# 3. 빌드하고 따로 검증한 뒤 사람이 검토한다 (계획 6절의 통과 기준)
python metric-detection/scripts/ml_train_build.py build metric-detection/templates/ml_train/v1.jsonl
python metric-detection/scripts/ml_train_build.py verify metric-detection/data_test/sessions_ml_v1.jsonl
python metric-detection/scripts/ml_train_build.py report metric-detection/data_test/sessions_ml_v1.jsonl

# 4. 본 생성 (약 $130): 전체 카드로 같은 이름. 파일럿에서 통과한 카드는 건너뛴다
python metric-detection/scripts/ml_train_write.py submit metric-detection/templates/ml_train/cards.jsonl --name v1
python metric-detection/scripts/ml_train_write.py collect v1 --wait
python metric-detection/scripts/ml_train_write.py process v1
# 다시 3번으로 빌드와 검증. 그다음 v1.jsonl과 batches/v1.json을 gitleaks로 확인하고 커밋한다
```

split은 카드를 뽑을 때 정해진다. 문맥 × 비밀 유형 칸마다 train 80, val 10, test 10으로 나누고(전체 수는 정확히 1,792, 224, 224), 분포 이동 test 250장은 따로 뽑는다. 템플릿은 카드의 split과 group_id를 그대로 meta에 받고, 그 템플릿의 variants도 모두 같은 split에 남는다.

`process`가 템플릿을 받아들이는 조건은 다섯 가지다.
- 응답이 끝까지 나왔다(`stop_reason`이 `end_turn`).
- JSON이 스키마에 맞는다.
- 카드를 따랐다.
  - item 수가 ±1, 턴 수가 +1 안이다.
  - 카드의 placeholder가 모두 지정 채널과 반복 조건대로 있다.
  - 어려운 음성이 모두 있다.
  - 카드에 없는 placeholder가 없고, tool_input에는 비밀 placeholder 대신 카드의 `{{mask:NAME}}`이 있다.
  - `ko`·`mixed` 카드는 개발자 메시지에 한국어가 있다.
- placeholder 밖에 비밀이 없다. 형식만으로 자격증명인 값, 자격증명 키 뒤의 리터럴, gitleaks 탐지를 본다.
- 그 템플릿 하나를 `ml_train_build`로 빌드하고 검사했을 때 통과한다.

## 설정

| 항목 | 값 | 바꿀 곳 |
|---|---|---|
| 모델 | 학습·검증·test: `claude-opus-5-5`, 분포 이동 test: `claude-sonnet-5-5` | `card_config.toml` `[templates]` |
| effort | `medium`, adaptive thinking | `ml_train_write.EFFORT` |
| max_tokens | 32,000 | `ml_train_write.MAX_TOKENS` |
| 출력 | JSON 스키마로 강제(`output_config.format`) | `ml_train_write.SCHEMA` |
| 캐시 | 시스템 프롬프트에 `cache_control`. 프롬프트가 약 2,100토큰이라 모델의 최소 캐시 길이보다 짧으면 캐시되지 않는다 | |

Batch API는 서버 측 `fallbacks`를 받지 않는다. 안전 분류기가 거절한 요청(`stop_reason: refusal`)은 `process`가 거절로 기록하고, 다시 `submit`하면 새로 시도한다.

`process`가 내는 `batch_cost_usd`는 응답의 토큰 사용량에 Batch 단가를 곱한 추정치다. 실제 청구액은 Console에서 확인한다.
