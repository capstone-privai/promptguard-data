# PromptGuard ML 학습 데이터 — 0단계 묶음

API를 새로 부르지 않고 **지금 저장소에 있는 템플릿과 privesc만으로** 만든 첫 묶음이다. 목적은 두 가지다.
(1) 학습 → 평가 파이프라인이 끝까지 도는지 확인한다. (2) 이 데이터만으로도 ML이 규칙 탐지기보다 나은 점이 있는지 본다.
본 생성(LLM 카드 약 2,150장 추가)은 이 결과를 보고 정한다. 그래서 **양과 분포가 계획(약 8,000세션)보다 훨씬 작고 치우쳐 있다**(아래 한계).

이 폴더는 `ml_train_export.py`가 쓰고 `ml_train_handoff.py`가 이 README를 덧쓴다. 같은 커밋에서 다시 빌드하면 바이트 단위로 같은 파일이 나온다
(기대 sha256은 저장소의 `metric-detection/templates/ml_train/handoff_step0.json`). 재현 방법은 `metric-detection/colab/build_ml_handoff.ipynb` 또는
`metric-detection/scripts/build_ml_handoff.sh`.

## 무엇이 어디에 있나

| 위치 | split | 쓰는 곳 |
|---|---|---|
| `ml_handoff/model_A/` | train, val | **모델 A** 학습과 모델 선택(조기 종료): 손 템플릿 + privesc |
| `ml_handoff/model_B/` | train, val | **모델 B** 학습과 모델 선택: 손 템플릿 + LLM 템플릿 + privesc |
| `ml_handoff/sessions_*.jsonl`, `gold_*.jsonl`, `labels_*.jsonl` | train, val | export 원본. `model_B/`와 바이트까지 같다. 학습에는 `model_A/`·`model_B/`를 쓴다 |
| `data_test/sessions_mleval_<입력>_<split>.jsonl`, `data_answer/gold_mleval_…`, `labels_mleval_…` | test, test_ood | 평가 전용. 학습에 쓰지 않는다 |

형식(필드 설명)은 아래 "파일 형식" 절에 있다. 출처는 세 가지다.

- **손 템플릿**(`group_id`가 `hand-`): 사람이 직접 쓴 경계 규칙 세션 160개 × 값 변형 5.
- **LLM 템플릿**(`c`, `o`, `a`, `b`, `p`로 시작): Claude가 카드대로 쓴 템플릿 × 값 변형 3(분포 이동 `o`는 2). `c`는 파일럿, `o`는 분포 이동 test,
  `a`는 자연어·문서 칸 보강, `b`는 설정 파일의 일반 값 음성, `p`는 개인정보 음성 묶음이다.
- **privesc**(`privesc-<시나리오>`): 비밀을 심어 둔 리눅스 VM에서 실제 에이전트가 권한 상승을 푼 기록. train 정답의 30% 이하로 표본 추출했다.

## 모델 A와 B

두 모델을 같은 설정으로 학습해 **LLM 템플릿을 더한 효과**를 본다. 두 폴더 모두 `sessions_`, `gold_`, `labels_` × `train`, `val` 6개 파일이고,
줄은 export 파일에서 그대로 골라 옮긴 것이다. **privesc 세션은 A와 B가 완전히 같다**(30% 상한을 B의 합성 train 정답 기준으로 한 번만 뽑았다).
그래서 A에서는 privesc 비중이 더 크다. privesc에는 val이 없어 **A의 val은 손 템플릿뿐**이다.
**평가 파일(test, test_ood)은 A·B 공통**이다(LLM 템플릿 test·test_ood도 A로 똑같이 채점한다).

| 모델 | 폴더 | 출처 | train 세션 | train 정답 | val 세션 | val 정답 | train 정답 중 privesc |
|---|---|---|---|---|---|---|---|
| A | `ml_handoff/model_A/` | 손 템플릿 + privesc | 1,108 | 5,563 | 80 | 435 | 36.9% |
| B | `ml_handoff/model_B/` | 손 템플릿 + LLM 템플릿 + privesc | 1,693 | 6,847 | 155 | 615 | 30.0% |

모델별 파일 sha256:

| 파일 | 모델 A | 모델 B |
|---|---|---|
| `sessions_train.jsonl` | `3f4759d5c0082b09a147c777ccbd1c5deb2fdc32eb65331103216248123d8164` | `447d1aacfafb7efa88c7c6872d189e10d8337c4ad709f6c2d114ab97d9cfafb1` |
| `gold_train.jsonl` | `6dc7dbe58e1582b5111b76062d68fe2a8aab76a99cae56fa3d139a8936a401f9` | `40d944a6139d6557cb74d34a809cf09891dc33ad5a0ee303b37b343012bb22a0` |
| `labels_train.jsonl` | `a8a6ea36b46176e150d26e2f09420de4f14aa19a169792230ae5a1706cf28803` | `173f5c72eac29ab6922c781fbffa951dafc9f3ae39b0bf60a9e68e60050834f7` |
| `sessions_val.jsonl` | `5c74be06d97b99f0054d220ad882cddbcf5accb92648ec36af03f0c7a54a58b1` | `dff827ce9b258d3a6e9ce7cccf1fa1e985f9380e27d078c0c7880423173447ef` |
| `gold_val.jsonl` | `a434f8990c987affefbd6d57a34c6d4e17e6d4de4df64f86048db35493973486` | `ad43c23414cf65b26d7458aa861ac0f1a6382975609a70ff4b4d23e9272b1e9c` |
| `labels_val.jsonl` | `bdbeca38ed785d3c1032d7ffdca842f7709d8170306e1db19b456573793ba221` | `a14200cca6a222b50aa7eb97dd09494651c6babad572b5f0adfda240958ac584` |

## 수

### split × 출처별 세션 / 정답 span

| split | 손 템플릿 세션 | LLM 템플릿 세션 | privesc 세션 | 손 템플릿 정답 | LLM 템플릿 정답 | privesc 정답 | 합계 세션 | 합계 정답 |
|---|---|---|---|---|---|---|---|---|
| train | 640 | 585 | 468 | 3,510 | 1,284 | 2,053 | 1,693 | 6,847 |
| val | 80 | 75 | 0 | 435 | 180 | 0 | 155 | 615 |
| test | 80 | 60 | 0 | 435 | 150 | 0 | 140 | 585 |
| test_ood | 0 | 10 | 440 | 0 | 14 | 2,031 | 450 | 2,045 |

train 정답 중 privesc 비율: 29.98% (목표 30% 이하, privesc 표본 목표 정답 수 2,054).

### 정답 대비 음성

음성 = labels의 이름 붙은 비정답 구간(어려운 음성, 식별자 등). privesc의 `mask`(tool_input의 `[PASSWORD_1]` 같은 가림 표시)는 따로 센다.

| split | 출처 | 정답 | 음성 | 음성 / 정답 | mask |
|---|---|---|---|---|---|
| train | 손 템플릿 | 3,510 | 1,160 | 0.33 | 15 |
| train | LLM 템플릿 | 1,284 | 1,755 | 1.37 | 327 |
| train | privesc | 2,053 | 15,594 | 7.60 | 1,406 |
| val | 손 템플릿 | 435 | 145 | 0.33 | 0 |
| val | LLM 템플릿 | 180 | 210 | 1.17 | 63 |
| test | 손 템플릿 | 435 | 145 | 0.33 | 0 |
| test | LLM 템플릿 | 150 | 162 | 1.08 | 51 |
| test_ood | LLM 템플릿 | 14 | 6 | 0.43 | 4 |
| test_ood | privesc | 2,031 | 14,069 | 6.93 | 1,361 |

privesc 음성의 대부분은 `identifier`(`ls -l` 소유자 칸의 `root` 등)라 다른 출처와 비율을 섞어 보지 않는다.

### 정답 유형별 (train)

| 출처 | PASSWORD | SECRET | TOKEN | ACCESS_KEY | PRIVATE_KEY |
|---|---|---|---|---|---|
| 손 템플릿 | 1,635 | 502 | 973 | 40 | 360 |
| LLM 템플릿 | 516 | 279 | 351 | 66 | 72 |
| privesc | 2,053 | 0 | 0 | 0 | 0 |
| 비율 | 61.4% | 11.4% | 19.3% | 1.5% | 6.3% |

### LLM 템플릿의 문맥 × 주 비밀 유형 (train + val 세션)

손 템플릿과 privesc에는 카드가 없어 이 표에 없다. `none`은 비밀이 없는 세션(음성 세션)이다.

| 문맥 | PASSWORD | SECRET | TOKEN | ACCESS_KEY | PRIVATE_KEY | none | 합계 | 비율 |
|---|---|---|---|---|---|---|---|---|
| config | 39 | 33 | 33 | 0 | 0 | 132 | 237 | 35.9% |
| command_output | 6 | 3 | 0 | 6 | 0 | 12 | 27 | 4.1% |
| log | 9 | 0 | 15 | 0 | 0 | 3 | 27 | 4.1% |
| stacktrace | 12 | 3 | 0 | 0 | 0 | 3 | 18 | 2.7% |
| diff | 12 | 3 | 3 | 0 | 0 | 0 | 18 | 2.7% |
| http | 3 | 3 | 9 | 0 | 0 | 6 | 21 | 3.2% |
| natural_language | 27 | 63 | 72 | 0 | 0 | 27 | 189 | 28.6% |
| document | 69 | 3 | 0 | 0 | 3 | 9 | 84 | 12.7% |
| key_file | 0 | 0 | 0 | 0 | 9 | 0 | 9 | 1.4% |
| 합계 | 177 | 111 | 132 | 6 | 12 | 192 | 660 | |

LLM 묶음별 세션: train a 150, b 180, c 198, p 57; val a 18, b 24, c 24, p 9; test a 18, b 18, c 18, p 6; test_ood o 10

### privesc 표본

| split | 시나리오별 세션 |
|---|---|
| train | capabilities_gtfobins 59, cron_wildcard 59, cron_writable_script 59, password_file 59, password_history 58, sudo_gtfobins 58, suid_gtfobins 58, weak_password 58 (합 468) |
| test_ood | password_reuse 220, ssh_key_reuse 220 (합 440) |

거의 같은 문맥(값·숫자를 가린 단어 3-gram 유사도 0.8 이상) 쌍: reported 16 (`reported`는 privesc끼리라 옮기지 않고 기록만 한 쌍). 평가 쪽에서 train으로 옮긴 세션: 없음.
train과 평가 쪽에 함께 나오는 정답 값(값 없이 manifest에 기록): 12개. 모두 privesc 기록이거나
`value_gen.WEAK`의 약한 비밀번호(`toor`류 고정 목록, `weak_list: true`)다.

## 알려진 한계 — 점수를 읽을 때

1. **LLM 템플릿이 설정·자연어·문서 문맥으로 쏠려 있다.** 본 생성 전이라 파일럿 80장에 보강 묶음(a·b·p)만 더해졌기 때문이다.
   로그, 스택트레이스, diff, HTTP, 키 파일 문맥은 아주 적다. 문맥별 점수는 표본이 작다는 점을 감안한다.
2. **ACCESS_KEY 정답이 적다**(위 유형 표). 이 유형의 재현율은 신뢰구간이 넓다.
3. **privesc는 한 분야(리눅스 권한 상승)에 치우치고, test_ood가 train과 같은 VM이다.** OOD 시나리오 2개가 train 시나리오와
   수천 item이 사실상 같고(manifest `near_duplicates`, rule `reported`), 에이전트의 추측 비밀번호가 양쪽에 나온다. privesc test_ood 점수는 낙관적이다.
4. **CredData·Nemotron-PII 평가는 낙관적이다.** 보강 카드(a·b·p)를 이 두 평가의 오탐·미탐 분석으로 설계했기 때문이다(텍스트와 값은 쓰지 않았다).
   ML이 규칙보다 나은지 판단할 때는 **authored test(`sessions_mleval_v1_test`, `sessions_mleval_hand_v1_test`), 분포 이동 test(`sessions_mleval_v1_test_ood`), privesc test_ood**를 우선 본다.
   단, `v1_test_ood`는 10세션뿐이다.
5. **손 템플릿이 정답의 다수를 차지한다.** 경계 규칙을 일부러 몰아 넣은 세션이라 실제 트래픽보다 정답 밀도가 높다.
6. **빠진 입력:** templates/ml_train/raw/v1_local.jsonl (Twilio SID가 든 LLM 템플릿, git 제외라 이 저장소에 없음). 이 템플릿들은 빌드에 들어가지 않았다.
7. 사람 검토(계획 6절)를 아직 하지 않은 템플릿이다.

## 파일 sha256

| 파일 | sha256 |
|---|---|
| `ml_handoff/sessions_train.jsonl` | `447d1aacfafb7efa88c7c6872d189e10d8337c4ad709f6c2d114ab97d9cfafb1` |
| `ml_handoff/gold_train.jsonl` | `40d944a6139d6557cb74d34a809cf09891dc33ad5a0ee303b37b343012bb22a0` |
| `ml_handoff/labels_train.jsonl` | `173f5c72eac29ab6922c781fbffa951dafc9f3ae39b0bf60a9e68e60050834f7` |
| `ml_handoff/sessions_val.jsonl` | `dff827ce9b258d3a6e9ce7cccf1fa1e985f9380e27d078c0c7880423173447ef` |
| `ml_handoff/gold_val.jsonl` | `ad43c23414cf65b26d7458aa861ac0f1a6382975609a70ff4b4d23e9272b1e9c` |
| `ml_handoff/labels_val.jsonl` | `a14200cca6a222b50aa7eb97dd09494651c6babad572b5f0adfda240958ac584` |
| `data_test/sessions_mleval_hand_v1_test.jsonl` | `7162ff3617b0447be06040ad38f2f51c8fcc000d34fa3bb7a7323b3b9be7a520` |
| `data_answer/gold_mleval_hand_v1_test.jsonl` | `a4dd6b047602981dca46e527ef2e0e45c44e3484d008f0d73038f97b9de79c81` |
| `labels_mleval_hand_v1_test.jsonl` | `483a029f5979ebc90234ea581441d22143b3ed6eaaf2d0edde0ced5b0bdbf891` |
| `data_test/sessions_mleval_privesc_test_ood.jsonl` | `b7a8795617be4acc2dca5f4869a642b3c5456ff44f18b54f00d7f531f45c00d4` |
| `data_answer/gold_mleval_privesc_test_ood.jsonl` | `50fa2adcd134e7c6b21f8edd2ce0fa454b2ac83e0349d3c4a25956ae375ec2d1` |
| `labels_mleval_privesc_test_ood.jsonl` | `6958e1daeed828179178e27e07f7d8c4be8391ce65e7e7f778fdf4ec85cb3f97` |
| `data_test/sessions_mleval_v1_test.jsonl` | `83cdcff210033f36eea2fb203a9d3007916f5c9286256dd1b5ee2fde9088ee52` |
| `data_answer/gold_mleval_v1_test.jsonl` | `3cccf94b9da11a8fbef3089132bf5ef36da5ca9d21cacafd7ba59c52878d045d` |
| `labels_mleval_v1_test.jsonl` | `c3c56f792e77748bf8ba8682fe76c38f78992a37c3cc67ba2e7c8a21bc165d1d` |
| `data_test/sessions_mleval_v1_test_ood.jsonl` | `508ae5e9a95bd3db3e8720c164aac68bf431215af8dadd4070d18ec5e1d4c4da` |
| `data_answer/gold_mleval_v1_test_ood.jsonl` | `8417de0ad6a888cd66670879346c2f82b95dfd5be54f1b9b39d659b16ce85e4f` |
| `labels_mleval_v1_test_ood.jsonl` | `fecdb84713215d1ee42fe467f01ba65620aa26f3832759a8d552e39bee974395` |

manifest 두 개는 쓴 코드의 sha256을 담고 있어 코드만 바뀌어도 값이 바뀐다(데이터 대조에는 쓰지 않는다): `ml_handoff/manifest.json` `705874db35034345…`, `manifest_mleval.json` `1af6f1fbac7e8abd…`

---

## 파일 형식 (ml_train_export.py 안내)

코딩 에이전트가 주고받는 텍스트에서 자격증명을 찾는 모델의 학습 데이터다. metric-detection의 형식 그대로이며, 모델의
과제 형식(토큰 태그 등)으로는 바꾸지 않았다. 바꾸는 것은 모델 쪽이 한다. 평가용(test, test_ood)은 이 폴더에 없다.

promptguard-data 저장소의 `metric-detection/scripts/ml_train_export.py`가 만들었다. 같은 입력이면 바이트 단위로 같은
파일이 나온다. 입력, 버전, 수, 파일 sha256은 `manifest.json`에 있다.

**값은 모두 실제 형식을 따르는 가짜 값이다.** 실제 인증에 쓰지 말고, git에 올리지 않는다(GitHub push protection이
진짜 비밀로 보고 막는다).

### 파일

| 파일 | 한 줄 | 내용 |
|---|---|---|
| `sessions_train.jsonl`, `sessions_val.jsonl` | 세션 하나 | `session_id`, `items`, `meta` |
| `gold_train.jsonl`, `gold_val.jsonl` | 정답 span 하나 | `session_id`, `item_id`, `span_id`, `span` (`start`, `end`, `type`) |
| `labels_train.jsonl`, `labels_val.jsonl` | 정답이 아닌 구간 하나 | `session_id`, `item_id`, `start`, `end`, `gold` (false), `kind` |
| `manifest.json` | | 입력 파일과 sha256, split·출처·유형·채널·음성 kind별 수, 카탈로그 행별 카드 수, 버전, 거의 같은 문맥 처리 |

세 파일의 줄은 sessions 순서, 그 안에서 item 순서를 따른다. span이 없는 item은 gold에 나오지 않는다.

### 형식

```json
{"session_id": "c0001~0",
 "items": [{"item_id": 0, "turn_id": "t0", "channel": "prompt", "text": "..."},
           {"item_id": 1, "turn_id": "t0", "channel": "tool_output", "text": "DB_PASSWORD=..."}],
 "meta": {"split": "train", "group_id": "c0001", "origin": "authored", "...": "..."}}
{"session_id": "c0001~0", "item_id": 1, "span_id": 0, "span": {"start": 12, "end": 28, "type": "PASSWORD"}}
{"session_id": "c0001~0", "item_id": 1, "start": 40, "end": 52, "gold": false, "kind": "reference"}
```

- `start`, `end`: item `text` 안의 위치. Python 문자열 인덱스(코드 포인트)이고 `end`는 포함하지 않는다.
- `type`: `PASSWORD`, `SECRET`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY`. 한 item 안의 정답 span은 겹치지 않는다.
- `channel`: `prompt`(사용자 메시지), `instructions`(시스템 프롬프트에 들어가는 지침), `tool_input`(모델이 쓴 도구
  인자), `tool_output`(도구 결과).
- 정답 기준은 저장소의 `metric-detection/LABELING.md` 하나다. 정답은 "텍스트를 읽는 사람이 자격증명 자리에 들어간 값이라고
  판정할 수 있는 리터럴 값"이고, span은 값 그 자체다(따옴표 안쪽, `Bearer ` 뒤, URL은 비밀번호 부분만, 개인키는 BEGIN 줄부터
  END 줄까지). 같은 세션에서 고유한 정답 값이 다른 곳에 다시 나오면 그곳도 정답이다(흔한 값은 자격증명 자리에서만).
- **`tool_input`에는 정답이 없다.** 배포 환경에서 에이전트는 PromptGuard가 가린 표시만 보므로, 비밀을 다시 쓰는 명령에는
  값 대신 그 표시 `[KIND_n]`(예: `[PASSWORD_1]`)이 들어 있다. labels에 `mask`로 남는다.

### meta

| 필드 | 뜻 |
|---|---|
| `split` | `train` 또는 `val`. 모델 선택과 조기 종료는 val로 한다 |
| `split_moved_from` | 있으면 `test`: 학습 쪽과 거의 같은 문맥이라 평가 쪽에서 옮겨 온 group(manifest의 `near_duplicates`) |
| `group_id` | 맥락 원형 하나(LLM 템플릿 카드 `c0001`, 손 템플릿 `hand-…`, privesc 시나리오 `privesc-…`). 한 group은 한 split에만 있다. 교차 검증으로 나눌 때도 group 단위로 나눈다 |
| `variant` | 같은 템플릿에서 값만 바꿔 만든 몇 번째 세션인지 (`session_id`의 `~k`) |
| `origin` | `authored`(맥락에 맞게 직접 쓴 합성) 또는 `recorded`(비밀을 심은 환경에서 실제로 돌린 에이전트 기록, privesc) |
| `source`, `template` | 만든 생성기와 템플릿 파일 |
| `source_id`, `card`, `negatives`, `boundary_rule`, `generator` | LLM 템플릿의 비밀 출처 카탈로그 행, 카드(문맥, 서식, 도구 형식, 언어), 넣은 어려운 음성, 경계 규칙, 생성 모델·프롬프트·batch |

### labels의 kind

labels는 정답이 아닌 구간이다. 대부분 일부러 넣은 어려운 음성이라, 키 이름만 보고 판정하면 틀리게 되어 있다.

| kind | 뜻 | 예 |
|---|---|---|
| `redaction`, `prefix_redaction` | 지우거나 가린 흔적 | `********`, `[REDACTED]`, `ghp_xxxx…` |
| `template`, `prefix_template`, `template_ko` | 채워 넣을 자리 표시, 안내문 | `<your-token>`, `YOUR_API_KEY`, `glpat-YOUR_TOKEN_HERE` |
| `reference`, `secret_ref` | 변수·환경변수·비밀 저장소 참조 | `${DB_PASS}`, `os.environ["KEY"]` |
| `code` | 값이 아닌 코드 표현식 | `kwargs.get(`, `password: string;` |
| `doc_example`, `prefix_example` | 문서의 예시 값 | `AKIAIOSFODNN7EXAMPLE` |
| `descriptor` | 값이 아니라 값을 가리키는 말 | `new password` |
| `empty` | 빈 값 (start = end) | `DB_PASSWORD=` |
| `hash` | 단방향 해시 | `$6$…`, bcrypt |
| `identifier` | 사용자명, id, 커밋 해시, request id 등. 정답 값과 같은 문자열이 식별자 자리에 다시 나온 곳도 이 kind다 | UUID(`"id"` 자리), ARN |
| `not_propagated` | 정답 값과 같은 흔한 문자열이 자격증명 자리 밖에 나온 곳(정답 아님) | 비밀번호가 `root`일 때 `/root` |
| `non_credential` | 자격증명이 아닌 비밀·개인정보 | CSRF 토큰, PIN |
| `setting`, `auth_setting` | 자격증명 단어가 든 설정값 | `max_tokens = 4096`, `password_min_length = 12` |
| `public_key`, `public_key_raw`, `pem_header`, `wallet_address` | 공개키, 인증서, 본문 없는 PEM 머리글, 지갑 주소 | `ssh-ed25519 AAAA…` |
| `mask` | tool_input에서 에이전트가 쓴 PromptGuard 표시 | `[PASSWORD_1]` |

privesc의 labels는 거의 다 `identifier`(`ls -l` 소유자 칸의 `root` 같은 것)와 `not_propagated`, `mask`다. 음성 kind별
비율이나 가중치는 출처를 섞지 말고 manifest의 `counts_by_input`으로 출처마다 본다.

labels에 없는 구간이 모두 평범한 텍스트라는 뜻은 아니다. 정답이 아닌 것은 gold에 없는 모든 구간이고, labels는 그중
이름을 붙여 둔 것이다.
