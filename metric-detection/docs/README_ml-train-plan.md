# ML 학습용 합성 데이터: 빈틈 분석과 생성 계획

코딩 에이전트가 주고받는 텍스트에서 자격증명을 문맥까지 보고 찾는 소형 언어모델을 학습시키려 한다. 이 문서는 지금 학습에 쓸 수 있는(`ml_train`) 데이터가 무엇이 부족한지 숫자로 보이고, 그 빈틈을 채울 합성 데이터(train / val / test)를 어떻게 만들지 정한다. 계획 단계이며 아직 아무것도 생성하지 않았다.

- 분석 대상: 2026-10-08에 생성한 `ml_train` 데이터 4종(내장 코퍼스, 템플릿 예시, 에이전트 세션 v2, privesc-llm-data)
- 정답 기준: [LABELING.md](../LABELING.md). privesc 숫자는 main(`35066af`)의 `convert_privesc.py`로 다시 만든 결과다
- 범위: metric-detection 형식의 학습 데이터만 다룬다. LLM 합성은 한 번 생성하고 끝낸다. metric-task 과제(작업 폴더, 성공 조건)는 이 데이터에서 만들지 않고 따로 합성한다
- 정해진 것: 생성 방식은 **혼합**(LLM이 맥락 템플릿을 쓰고 값은 결정적 생성기로 넣는다), 분할은 **맥락 원형 단위 + 분포 이동 test**, 규모는 **약 8,000세션**(300세션 파일럿을 먼저 한다)

## 1. 지금 데이터의 빈틈

### 1.1 옛 기준으로 만든 데이터

10-08 생성본은 LABELING.md 이전 기준이다. 학습에 쓰기 전에 모두 main의 생성기와 변환기로 다시 만든다. 다시 만든 결과는 `dataset_verify.py`의 LABELING 검사를 모두 통과한다.

| 데이터 | 옛 기준 | 새 기준 | 차이 |
|---|---|---|---|
| privesc-llm-data | 정답 10,624 (채점 6,804) | 정답 15,716 (채점 9,392) | 9자 미만 값, 흔한 값, 에이전트가 시도한 틀린 비밀번호가 자격증명 자리에 있으면 정답이 된다. 고유 비밀번호 값 2,677 → 4,626 |
| authored 3종 | `db_uri` 정답 7개가 URI 전체(SECRET) | 비밀번호 부분만(PASSWORD) | main의 `8b3c98d`에서 고쳤다. 정답 수(32, 10, 78)는 같고 type만 바뀐다 |

### 1.2 축별 분포

authored는 내장 코퍼스, 템플릿 예시, 에이전트 세션 v2를 합친 값이다. "실제 트래픽"은 평가 전용 외부 데이터(openhands-feedback, SWE-Gym)의 집계 통계이며, 텍스트나 값은 쓰지 않았다.

| 축 | authored | privesc (새 기준) | 학습에 문제인 이유 |
|---|---|---|---|
| 양 | 57세션, 212 item, 정답 120개(고유값 약 104개) | 2,200세션, 122,286 item, 정답 15,716개 | authored는 학습량으로 의미가 없다. 사실상 privesc 한 분야가 전부다 |
| 유형 | PASSWORD 47, SECRET 34, TOKEN 25, ACCESS_KEY 11, PRIVATE_KEY 3 (span) | PASSWORD 15,557, PRIVATE_KEY 159 | TOKEN, ACCESS_KEY, SECRET은 authored의 70여 개가 전부다 |
| 서비스 형식 | AWS 6, GitHub 5, JWT 3, PEM 3, Stripe `pk_` 2, PyPI 1 (고유값) | PEM뿐 | OpenAI, Anthropic, GCP `AIza`, GitLab, Slack, npm, HF, SendGrid, Twilio, Azure, 웹훅 URL이 0개다 |
| 값 모양 | v2 비밀번호 27개 중 13개가 14자에 문자 종류 4개(생성기 `strong_password`). 내장 코퍼스는 `…#7!`로 끝나는 16자. `token`·`api_key` 40자, `secret` 48자로 고정 | 비밀번호의 98%가 영숫자뿐이다. 12자 영숫자 48%, 16자 hex 9.5%, 기호가 든 값은 사실상 0 | 모델이 문맥이 아니라 길이와 문자 구성(생성기 지문)을 외운다. type도 길이만으로 맞힐 수 있다 |
| 약하거나 사람이 지은 값 | 흔한 값 15%, 영어 단어가 든 값 33% (비밀번호 39개) | 흔한 값 28%, 8자 미만 28% | privesc의 약한 값은 대부분 `weak_password` 시나리오(사용자명과 같은 4자 소문자 581개)와 추측 시도라 한쪽으로 치우쳐 있다 |
| 문맥 유형 | key=value(ini, yaml, env)가 대부분. diff 4, HTTP 3, 스택트레이스 1, 마크다운 표 0, 코드 펜스 1 | JSON kv 6,315, `echo … \| sudo` 4,201, 시스템 프롬프트 문장 2,337 | 리눅스 권한 상승 한 분야에 몰려 있다. 소스 코드, 문서, 이슈 글, CI 로그가 거의 없다 |
| 언어 | 한국어 item 18%, 정답 있는 item 중 한국어 8~12% | 한국어 0 | 한국어 문장 속 비밀은 10개도 안 된다 |
| 채널 | 정답이 prompt 6, instructions 2, tool_output 106, tool_input 6 | prompt 0. instructions 2,200개는 모두 `User: 'x' \| Password: 'y'` 한 형식 | prompt와 instructions의 정답을 배울 예시가 없다 |
| 음성 | 채점 item의 55~65%가 음성. 그중 어려운 음성이 든 것 10~21% (UUID 15, hex 18, 참조 8, 가린 흔적 8, 템플릿 1, 문서 예시 0, 해시 0) | 음성 86%, 그중 어려운 음성이 든 것 2.5% (대부분 `$VAR` 참조 4,889, crypt 해시 282, 공개키 299) | 자격증명 자리에 있지만 정답이 아닌 값(placeholder, 문서 예시, 해시, 가린 값)을 거의 배우지 못한다 |
| 양성 비율 | item의 35~45%가 양성 | 14% | 실제 트래픽(SWE-Gym)은 item 18,900개에 정답 2개다. 확신을 과하게 갖도록 보정된다 |
| 경계 사례 | URL 속 비밀번호 2, Basic 2, Bearer 2, 쿠키 2, 잘린 PEM 0, 줄바꿈으로 끊긴 값 0, JSON 이스케이프 PEM 1 | URL 50, 잘린 PEM 12, 끊긴 값 3, 이스케이프 PEM 159 | LABELING.md "경계" 규칙 하나에 예시가 0~2개다 |
| 흔한 값이 두 자리에 함께 나옴 | 3세션 | 893세션 | privesc의 `/home/x`, `/etc/passwd` 형태로만 배운다 |
| 세션 구조 | item 3~5개, 거의 1턴. item 길이 중앙값 66~89자. 같은 값이 여러 item에 나오는 경우 9~19%, 여러 채널 4~9% | item 중앙값 48개, 6턴. 여러 채널 81% | 실제 tool_output 길이 중앙값은 600~760자다. 긴 출력 속 한 줄을 찾는 연습이 없다 |
| 도구 형식 | 날 텍스트 | tool_output 100%가 JSON 문자열, `\n` 이스케이프 69% | 실제 트래픽에 흔한 줄 번호 붙은 파일 보기(openhands 604건, SWE-Gym 3,568건)가 양쪽 모두 0이다 |
| 편향·누수 | group_id가 세션마다 다르다 | 시스템 프롬프트 2,200개가 값과 이름을 빼면 1개, 사용자 메시지 1개, group_id 10개, 모델 1개, tool_output의 25%가 완전 중복 | 세션 단위로 나누면 같은 템플릿이 train과 test에 함께 들어간다. 시나리오 단위로 나누면 test가 시나리오 1~2개가 된다 |

## 2. 생성 방식: 혼합

```
카드 추첨(결정적) → LLM이 placeholder 템플릿 작성 → 템플릿 정적 검사 → 빌드(값 생성, 정답 기록) → 검증 → 분할
                    손으로 쓴 경계 규칙 템플릿 ──────────┘
```

1. **카드 추첨**: 카드 한 장이 템플릿 하나의 작업 지시서다. 문맥 유형, 서식, 도구 형식, 언어, 채널 배치, 비밀 유형과 서비스, 경계 규칙, 어려운 음성, 길이 구간을 3절의 목표 분포에 맞춰 시드로 뽑는다. 같은 시드면 같은 카드가 나온다.
2. **LLM 템플릿 작성**: LLM이 카드를 받아 세션 하나를 처음부터 쓴다. 비밀이 들어갈 자리에는 리터럴 대신 `{{kind:name}}` placeholder만 쓴다. 비밀이 그 맥락에 원래 있는 것으로 쓰므로 `authored`다. 이미 있는 궤적에 비밀을 끼워 넣지 않는다(그러면 `injected`라 학습에 못 쓴다).
3. **손 템플릿**: LABELING.md 경계 규칙과 퍼뜨림 기준은 LLM이 정확히 지키기 어렵다. 규칙마다 손으로 쓴 완결된 세션(약 160개)을 두고, 키 이름, 따옴표, 서식, 언어를 바꿔 조합으로 늘린다.
4. **빌드**: `dataset_build.py`가 placeholder를 값 생성기로 채우고, 넣는 순간 위치를 정답으로 기록한다. 탐지기 결과는 정답에 쓰지 않는다.
5. **어려운 음성도 placeholder로 넣는다**: `{{neg:kind}}`(예: `neg:template`, `neg:hash`, `neg:doc_example`)는 정답이 아닌 값을 생성하고, 그 위치와 kind를 labels 파일에 남긴다. 어려운 음성의 수를 카드로 통제하고 종류별로 집계하기 위해서다.

템플릿에는 비밀값이 없으므로 git에 올릴 수 있다. LLM 출력은 다시 만들면 달라지므로, 템플릿 파일 자체를 원본으로 보관하는 것이 재현성의 근거다(7절).

### 생성기: `ml_train_build.py`와 `value_gen.py` (구현함)

평가용 데이터의 생성 경로(`dataset_build.py`)는 그대로 두고, 학습 데이터는 [ml_train_build.py](../scripts/ml_train_build.py)로 따로 만들고 검증한다. 문법과 명령은 [templates/README.md](../templates/README.md#ml-학습용-템플릿-ml_train_buildpy)에 있다.

- `build`: `dataset_build`의 placeholder 문법과 생성기를 그대로 쓰고, 아래를 더한다.
  - [value_gen.py](../scripts/value_gen.py)의 kind 43개와 `{{neg:KIND}}` 13종. 비밀 출처 카탈로그에서 서비스 형식 kind 351개와 대조군용 neg kind 8종을 더했다(아래 "비밀 출처 카탈로그")
  - `wrap`, `truncate` 변환
  - `meta.split`(필수), `meta.variants`, `meta.value_profile`
  - kind 이름에는 형식을 밑줄로 붙인다(`password_weak`, `github_fine_grained`, `openai_key`). `:` 뒤는 name 자리이기 때문이다.
- 값이 그 자리에서 정답이 될 수 없으면 다시 뽑는다. 흔한 값이 자격증명 자리 밖에 있거나, label_rules가 제외 kind로 읽거나, 경계 규칙에 맞지 않는 경우다.
- `verify`(따로 실행): 5가지를 본다.
  - `dataset_verify`의 LABELING 검사
  - 정답 자리 검사
  - `neg:` 값의 kind
  - split 누수(group, 고유값)
  - sessions·gold·labels 재생성 바이트 일치
- `report`: 값 모양만으로 정답과 어려운 음성을 가르는 로지스틱 회귀의 AUROC(4.3절)와, 유형별 (길이, 문자 구성) 최빈 칸의 비율을 낸다. scikit-learn이 필요하다.
- VERSION(`metric1-v0.1`)은 바꾸지 않는다. 값 시드가 `VERSION:split:템플릿파일명:session_id[~k]:kind:name`이라, 기존 평가 데이터와도 split끼리도 값이 겹치지 않는다.

### 비밀 출처 카탈로그 (구현함, 2026-10-25)

[secret-sources](../secret-sources/README.md)의 카탈로그(566행, "어떤 서비스·맥락에서 비밀이 어떻게 에이전트에게 들어오는가")를 카드의 장면으로 쓴다. 카탈로그 CSV는 git 밖에 두고(예시 열에 실제 형식의 가짜 키가 있다), [ml_train_catalog.py](../scripts/ml_train_catalog.py)가 행별 결정([catalog_decisions.toml](../templates/ml_train/catalog_decisions.toml))과 함께 읽어 예시 값 없는 `catalog.jsonl`과 서비스 형식 kind(`value_gen_catalog.py`)를 만든다.

- 판정은 LABELING.md를 따른다. 카탈로그가 음성으로 둔 공개용 키(Stripe `pk_`, Supabase anon JWT, Toss `test_ck_`, Kakao JS 키), 약한 값(`changeme`), 0으로 채운 UUID는 정답으로 보고 대조군으로 쓰지 않는다. 해시·식별자를 양성으로 둔 행은 빼거나 음성 장면으로 쓴다.
- 566행 중 학습 504, 분포 이동 test 전용 8(Twilio, Datadog 키 둘, Hugging Face, Azure 저장소 키, Terraform state, Jupyter 출력, MCP 결과), 제외 54(LABELING 판정·열린 질문, 자동 수집 행의 접두사 조각과 중복).
- 카드마다 행 하나를 받는다. 문맥 × 유형 칸의 수와 split은 그대로이고, 칸 안에서 맞는 행을 덜 쓴 것부터 돌린다. 행이 주 비밀의 kind, 장면 힌트(경로, 포맷, 짝 자산, 주변 이름, 학습 포인트), 대조군(`{{neg:…}}`)을 준다. 대조군은 카드의 어려운 음성에 하나 더 들어간다.
- 평가 전용 출처(CredData, SecretBench, Nemotron-PII, SWE-Gym, openhands-feedback, Nosey Parker)를 인용한 행은 서비스 이름과 값 형식만 쓰고 장면 힌트와 대조군을 넣지 않는다. 그래도 형식 지식(접두사, 길이, 문자 집합)은 공유하므로 Nosey Parker와 CredData 점수는 낙관적일 수 있다(5절).

## 3. 커버리지 설계

### 3.1 전체 구성 (약 8,000세션)

| 출처 | 템플릿 | 값 시드 | 세션 | 용도 |
|---|---|---|---|---|
| LLM 템플릿 | 2,240 | 3 | 6,720 | train / val / test |
| 손 템플릿 (경계 규칙) | 160 | 5 | 800 | train / val / test |
| 분포 이동 test용 LLM 템플릿 | 250 | 2 | 500 | test만 (5.1절) |
| 기존 authored 57세션 (새 기준으로 다시 빌드) | 57 | 1 | 57 | 사람이 쓴 점검용 test |

train / val / test-ID 몫은 약 7,500세션이고, 분포 이동 test와 기존 authored를 더하면 약 8,000세션이다. 세션의 70%는 비밀이 하나 이상 있고 30%는 없다. item 길이를 실제 트래픽에 가깝게 늘리므로(tool_output 중앙값 500~800자, 10%는 3,000자 이상), item 단위 양성 비율은 15~20%가 된다. 예상 규모는 item 약 5만 개, 정답 span 약 2만 5천 개(고유값 약 1만 2천 개)다.

### 3.2 문맥 유형 × 주 비밀 유형 (세션 수)

카드는 세션마다 주 비밀 유형 하나를 뽑고, 같은 세션에 다른 유형을 0~2개 더 넣는다. 아래는 주 유형 기준이고 "음성"은 비밀이 없는 세션이다.

| 문맥 유형 | PASSWORD | SECRET | TOKEN | ACCESS_KEY | PRIVATE_KEY | 음성 | 합계 |
|---|---|---|---|---|---|---|---|
| 설정 파일 (env, yaml, json, toml, ini, properties, compose, k8s, terraform) | 340 | 300 | 160 | 90 | 50 | 360 | 1,300 |
| 명령 출력 (env, ps, docker inspect, kubectl, git config, cloud CLI) | 260 | 170 | 170 | 80 | 40 | 280 | 1,000 |
| 로그 (앱, 액세스, JSON 로그, CI) | 230 | 120 | 170 | 30 | 0 | 250 | 800 |
| 스택트레이스·오류 출력 | 160 | 60 | 60 | 20 | 0 | 200 | 500 |
| diff·git 이력 | 120 | 120 | 80 | 60 | 40 | 180 | 600 |
| HTTP (curl -v, 요청·응답 덤프, HAR, 쿠키) | 60 | 60 | 280 | 20 | 0 | 180 | 600 |
| 소스 코드 (Python, JS/TS, Go, Java, 셸, SQL, 노트북 셀) | 220 | 220 | 150 | 60 | 50 | 400 | 1,100 |
| 자연어 (사용자 요청, 이슈, 채팅, 커밋 메시지) | 330 | 100 | 120 | 30 | 20 | 200 | 800 |
| 문서 (README, 위키, 마크다운 표, 운영 절차) | 120 | 60 | 60 | 20 | 10 | 230 | 500 |
| 키 파일 출력 (PEM, OpenSSH, PuTTY, JWK, 서비스 계정 JSON) | 0 | 40 | 0 | 0 | 220 | 40 | 300 |
| 합계 | 1,840 | 1,250 | 1,250 | 410 | 430 | 2,320 | 7,500 |

이 표는 LLM 템플릿과 손 템플릿을 합친 train / val / test-ID 몫이다. 분포 이동 test와 기존 authored는 들어 있지 않다.

### 3.3 그 밖의 축 목표

| 축 | 목표 |
|---|---|
| 정답의 채널 | 비밀이 처음 나오는 채널은 tool_output 74%, prompt 17%, instructions 9%다. tool_input에는 정답을 두지 않는다(2026-10-25 결정): 배포 환경에서 에이전트는 PromptGuard가 가린 표시만 보므로, tool_input에는 비밀값 대신 그 표시(`[PASSWORD_1]`)가 들어간다. 비밀의 30%는 나중에 tool_input에서 이 표시로 다시 쓰인다(`{{mask:NAME}}`) |
| 언어 | 영어 70%, 한국어 25%, 혼합 5%. 한국어는 자연어, 문서, 로그 메시지, 코드 주석에 둔다 |
| tool_output 형식 | 날 텍스트 셸 출력 40%, 줄 번호 붙은 파일 보기(Read, `cat -n`) 25%, grep 결과(`경로:줄:`) 10%, JSON으로 감싼 결과 15%, 잘린 출력(앞뒤 생략 표시) 10% |
| tool_input 형식 | 셸 명령 60%, JSON 인자 30%, 파일 편집 인자 10% |
| 세션 구조 | item 3~30개(중앙값 8), 턴 1~8. 같은 고유값이 여러 item에 다시 나오는 경우 30%, 여러 채널에 나오는 경우 20% |
| 서비스 형식 | 4.2절의 형식마다 고유값 최소 150개 |

### 3.4 어려운 음성과 경계 규칙

음성 세션의 60% 이상, 양성 세션의 40% 이상에 어려운 음성을 하나 이상 넣는다. 어려운 음성 등장 수는 정답 span 수와 비슷하게(약 1:1) 맞춘다. 절반 이상은 자격증명 자리에 두어, 키 이름만 보고 판정하는 모델이 틀리게 한다.

| 어려운 음성 kind (LABELING.md) | 최소 등장 수 | 예 |
|---|---|---|
| `redaction` | 600 | `********`, `[REDACTED]`, `sk-...9f2c`, `ghp_-XXX` |
| `template` | 800 | `<your-token>`, `YOUR_API_KEY`, `{{ .Values.x }}`, `your-secret-key-change-this` |
| `reference` | 800 | `${DB_PASS}`, `os.environ["KEY"]`, `%PASS%`, `{token}` |
| `code` | 500 | `password: string;`, `kwargs.get(`, `generate_password_hash(` |
| `doc_example` | 400 | `AKIAIOSFODNN7EXAMPLE`, "such as `Ocean@2025`", man 페이지 예시 |
| `descriptor` | 300 | `new password`, `temporary password` |
| `hash` | 500 | `$6$…`, `$2b$…`, bcrypt, Argon2 |
| `identifier` | 1,000 | request id, 커밋 해시, UUID(`"id"` 자리), client id, ARN, 계정 id |
| `non_credential` | 300 | CSRF 토큰, 추적 쿠키, PIN, 카드 번호 |
| `empty` | 300 | `DB_PASSWORD=` |
| 자격증명 단어지만 값이 아님 | 400 | `max_tokens = 4096`, `password_min_length = 12`, 화면 문구 |
| 공개키·인증서 | 300 | `ssh-ed25519 AAAA…`, `BEGIN CERTIFICATE`, BEGIN 줄만 있는 PEM |

| 경계·퍼뜨림 규칙 (LABELING.md) | 최소 정답 수 |
|---|---|
| 따옴표 안쪽, 뒤따르는 문장 부호, 값 자체가 문장 부호로 끝남 | 각 300 |
| `Bearer`, `Basic`, `token` 스킴 | 각 200 |
| URL 속 비밀번호·토큰 (스킴 6종 이상) | 400 |
| `사용자명:비밀번호` 쌍, 연결 문자열 `Password=…;` | 각 200 |
| 쿠키 (`Cookie`, `Set-Cookie`, 속성 포함) | 200 |
| PEM 전체, 잘린 PEM, JSON 이스케이프 PEM | 각 150 |
| 터미널 폭으로 끊긴 값 | 150 |
| base64, URL, JSON 인코딩한 값 | 각 150 |
| 맞닿거나 겹친 값의 병합 | 100 |
| 흔한 값이 자격증명 자리와 일반 자리에 함께 나옴 (`root`와 `/root`, `admin` 사용자와 비밀번호) | 400세션 |
| 고유한 값이 자격증명 자리 밖(로그, 오류 메시지)에 다시 나옴 | 600세션 |
| 고유한 값이 식별자 자리에 다시 나옴 (정답 아님) | 150세션 |

## 4. 값 생성기

생성기가 만드는 값의 모양이 모델이 외울 지문이 되지 않게 하는 것이 목표다.

### 4.1 비밀번호

| 계열 | 비율 | 모양 |
|---|---|---|
| 무작위 | 35% | 길이 6~40(분포를 둔다), 문자 종류 조합 1~4가지, 기호 집합도 무작위 |
| 사람이 지은 값 | 30% | 단어 + 숫자 + 기호(`Summer2024!`), 이름·연도·키보드 패턴, 한글 자판을 영문으로 친 것, leet 치환. 단어는 손으로 고른 중립 단어 211개 |
| 약하거나 흔한 값 | 20% | `admin`, `postgres`, `password123`, `12345678`, 서비스 기본값. 손으로 고른 목록을 쓰고 유출 목록은 쓰지 않는다 |
| 패스프레이즈 | 10% | 단어 3~5개를 `-`, `_`, `.`로 잇거나 붙인다. 공백으로 이은 것은 label_rules가 `descriptor`로 읽어 넣지 않았다(9절) |
| hex·base64 | 5% | 16~64자 |

### 4.2 토큰·키

서비스 형식은 공개 문서의 접두어, 문자 집합, 길이, 체크섬 규칙을 따른다. AWS `AKIA`/`ASIA`와 시크릿, GitHub `ghp_`/`gho_`/`github_pat_`, GitLab `glpat-`, Slack `xox?-`와 웹훅, Stripe `sk_`/`pk_`/`rk_`, OpenAI `sk-proj-`, Anthropic `sk-ant-`, GCP `AIza`와 서비스 계정 JSON, Azure 연결 문자열, SendGrid, Twilio, npm, PyPI, Hugging Face, Discord 웹훅, Datadog, JWT(HS256·RS256, payload 다양화), PEM(RSA PKCS#1, PKCS#8, EC, OpenSSH, PuTTY) 등 25종 이상이다. 접두어가 없는 일반 비밀은 길이 16~64, 문자 집합(hex, base64, base64url, 영숫자)을 무작위로 고른다.

### 4.3 지문 막기

- 유형마다 (길이, 문자 구성) 한 칸이 그 유형 값의 20%를 넘지 않게 한다.
- 어려운 음성 값(해시, UUID, request id, 커밋 해시)도 같은 길이와 문자 구성 범위에서 만든다. 모양만으로는 정답과 음성을 가를 수 없게 하기 위해서다.
- **모양만 보는 기준 모델**: 값의 길이, 문자 구성, 엔트로피만 특징으로 쓰는 로지스틱 회귀로 정답과 어려운 음성을 가려 본다. 성능이 높게 나오면(예: AUROC 0.8 이상) 생성기 분포를 고친다.

## 5. train / val / test 분할

| 집합 | 구성 | 세션 |
|---|---|---|
| train | LLM·손 템플릿 group의 80% + privesc 시나리오 8종 | 약 6,000 + privesc |
| val | group의 10% | 약 750 |
| test-ID | group의 10% | 약 750 |
| test-OOD | 5.1절의 분포 이동 세트 + privesc 시나리오 2종 | 약 500 + privesc 440 |
| test-authored | 기존 authored 57세션 (새 기준으로 다시 빌드) | 57 |

- **group_id = 템플릿 하나**. 한 템플릿에서 나온 세션(값 시드 변형)은 모두 같은 split에 간다. 같은 카드에서 나온 양성·음성 대조 쌍도 같은 group으로 묶는다.
- **값도 나눈다**: 값 시드에 split 이름을 넣고, 빌드 후 split 사이에 같은 값이 없는지 검사한다. 흔한 값 목록은 공유해도 된다.
- **중복 검사**: 값과 숫자를 가린 텍스트로 MinHash를 만들어, split 사이에 유사도 0.8 이상인 item이 있으면 그 group을 옮긴다.
- **privesc** (구현함, [ml_train_privesc.py](../scripts/ml_train_privesc.py)): 정답 수는 많지만 한 분야라서 train 정답의 30% 이하로 묶는다(시나리오를 돌아가며 세션 표본 추출, 목표 정답 수를 인자로 받는다). privesc의 tool_input에는 진짜 비밀번호와 정답(6,324개)이 있어, 학습용은 tool_input의 정답을 모두 `[KIND_n]` 가림 표시로 바꾸고 tool_input은 문맥으로만 쓴다. 앞에서 정답으로 나온 적 없는 값(에이전트가 추측한 값, 가려지지 않은 채로 본 흔한 값, 2,018개)도 tool_input에서 처음 나온 자리에서 번호를 붙여 가린다(2026-10-25 결정). 그런 세션을 빼면 `weak_password` 220세션이 모두 빠지기 때문이다. test-OOD에는 `password_reuse`, `ssh_key_reuse` 2종(440세션)을 표본 없이 모두 둔다. group_id는 `privesc-<시나리오>`다.
- **외부 데이터**(CredData, Nemotron-PII, openhands-feedback, SWE-Gym, Nosey Parker)는 평가에만 쓴다. 텍스트와 값은 쓰지 않았고, 이 계획에는 형식·채널·길이의 집계 통계만 참고했다. 그래도 커버리지 목표를 그 통계에 맞춰 정했으므로 외부 데이터 점수가 실제보다 낙관적으로 나올 수 있다. 그래서 외부 데이터 결과는 "목표 분포를 참고한 평가"라고 함께 적는다. 비밀 출처 카탈로그도 이 출처들을 인용한 행(55행)이 있어 그 텍스트와 예시 값은 쓰지 않았지만, 서비스 형식(접두사, 길이, 문자 집합)은 Nosey Parker 규칙·CredSweeper와 겹치므로 Nosey Parker와 CredData 점수는 더 낙관적일 수 있다.

### 5.1 분포 이동 test (test-OOD)

학습에 나오지 않는 것만 모은다. 학습 카드 추첨에서 아래 값은 아예 뽑지 않는다.

- 문맥 유형 2개: Jupyter 노트북 출력, Terraform state·plan 출력
- 서비스 형식 4개: Twilio, Datadog, Hugging Face, Azure 연결 문자열
- 도구 형식 1개: MCP 도구의 구조화된 결과
- 생성 모델 변경: 템플릿을 학습용과 다른 모델로 쓴다. 학습 데이터의 문체를 외웠는지 확인하기 위해서다

## 6. 품질 검증

| 단계 | 검사 | 실패하면 |
|---|---|---|
| 템플릿 정적 검사 | placeholder 밖에 비밀 모양의 리터럴이 없다(gitleaks, `label_rules`의 자격증명 자리 패턴). placeholder 수와 종류가 카드와 맞는다. 문맥 유형과 서식이 카드와 맞는다 | 템플릿을 버리고 다시 쓴다. 검사기가 찾은 값을 정답으로 바꾸지 않는다 |
| 빌드 후 규칙 검사 | `ml_train_build.py verify`: `dataset_verify.py`의 스키마, 용도 정책, span 범위·겹침, LABELING.md 검증 1~4번(제외 규칙, 경계 정규화, 퍼뜨림 기준, 유형), split 누수, 재생성 바이트 일치 | 검증 실패 |
| 자리 검사 | 같은 `verify`: 정답이 식별자 자리에 없고, 흔한 정답은 자격증명 자리에만 있다. `{{neg:kind}}` 값은 `exclusion_kind`가 그 kind를 돌려준다(kind가 값 모양으로 정해지는 7종) | 템플릿 수정 |
| 분포 리포트 | `ml_train_build.py report`(4.3절 모양 기준 모델). 1절의 축별 집계는 아직 scratchpad 스크립트다 | 카드 추첨 보정 |
| 탐지기 대조 | PromptGuard 앙상블이 정답 밖에서 찾은 값은 사람 검토 목록으로 보낸다. 정답에 자동으로 넣지 않는다 | 사람이 판정한다 |
| 사람 검토 | 파일럿: 300세션 중 문맥 유형·채널으로 층화한 100세션을 2명이 본다. 본 생성: 400세션(5%) 층화 표본 | 아래 기준 미달이면 프롬프트와 카드를 고친다 |

사람 검토에서는 (1) 맥락이 자연스러운지(3단계, `authored` 판정의 근거), (2) 정답이 빠졌거나 넘치는지, (3) 경계가 맞는지를 본다. 통과 기준은 정답 오류(누락과 잘못된 정답 합) 2% 미만, "부자연스러움" 판정 10% 미만이다. 400세션 표본이면 오류율 2%를 95% 신뢰도에서 약 ±1%p로 잴 수 있다. 검토 기록에는 값을 쓰지 않고 위치와 해시만 둔다([reviews/](../reviews/README.md)와 같은 방식).

## 7. 규모, 비용, 저장소 규칙

### 비용 (추정, 파일럿에서 다시 잰다)

템플릿 한 개에 입력 약 4천 토큰(지침과 예시 3천은 캐시, 카드 1천), 출력 약 4.5천 토큰(사고 포함)으로 잡았다. 학습용 템플릿 2,240개에 검사 실패로 20%를 다시 쓴다고 보면 약 2,700회를 호출한다.

| 모델 | 단가 (백만 토큰당 입력 / 출력) | 표준 | Batch(50% 할인) |
|---|---|---|---|
| Claude Opus 5.5 (기본) | $4 / $20 | 약 $260 | 약 $130 |
| Claude Sonnet 5.5 | $2 / $10 | 약 $130 | 약 $65 |

파일럿(템플릿 100개)은 Opus 5.5 Batch로 약 $6다. 분포 이동 test는 학습과 다른 모델로 써야 하므로 학습 템플릿이 Opus 5.5면 Sonnet 5.5로 쓴다(약 $10). 생성 시간은 Batch 처리가 보통 몇 시간 안에 끝나고, 빌드와 검증은 몇 분이다. 시간이 가장 많이 드는 것은 사람 검토다(파일럿 100세션에 1인당 약 3시간).

### 저장소 규칙

- **템플릿은 이 저장소에 커밋한다**(2026-10-25 결정): 비밀값이 없고, LLM 출력은 다시 만들 수 없으므로 템플릿이 원본이다. 예상 크기는 약 10MB다. 커밋 전에 gitleaks로 템플릿을 검사한다. 각 템플릿 meta에 카드 id, 모델 id, 프롬프트 버전, 응답 id를 남긴다. LLM 원문 응답은 올리지 않는다.
- **빌드 결과는 올리지 않는다**: `data_test/`, `data_answer/`는 이미 `.gitignore`에 있다. 실제 형식을 따르는 가짜 키(체크섬이 맞는 GitHub 토큰 등)는 GitHub push protection에 걸린다. 같은 템플릿과 VERSION이면 바이트 단위로 같은 결과가 나와야 한다.
- 진짜 비밀값을 만들거나 가져오지 않는다. 값은 공개된 결정적 시드로 만들며, 실제 인증에 쓰면 안 된다.
- VERSION은 그대로 두고 값 시드에 split과 템플릿 이름을 넣는다(2절). 기존 평가 데이터의 값은 바뀌지 않는다.
- 빌드 결과(`sessions_ml_*`, `gold_ml_*`, `labels_ml_*`)는 `.gitignore`에 있다.

## 8. 진행 순서

1. (끝남) label-unify를 main에 합친다. 2026-10-25, `35066af`. 이후 정답은 `label_rules.py`가 기준이다.
2. (끝남) 생성기: `ml_train_build.py`(build, verify, report)와 `value_gen.py`. 기존 템플릿 3종의 출력은 바이트 단위로 그대로다. 남은 것은 URI 스킴 추가와 1절 축별 집계의 저장소 이전이다.
3. (끝남) 카드 추첨기와 LLM 템플릿 작성 스크립트: `ml_train_cards.py`, `ml_train_write.py`(Message Batches API), `templates/ml_train/`의 설정·프롬프트·[실행 절차](../templates/ml_train/README.md). 가짜 응답으로 검사와 빌드까지 확인했고, API는 아직 부르지 않았다.
4. 파일럿(별도 세션): 템플릿 100개 → 약 290세션. 자동 검사, 사람 검토 100세션, 비용 실측. 결과를 보고 본 생성을 승인받는다.
5. 본 생성: LLM 템플릿 2,240 + 손 템플릿 160 + 분포 이동 250.
6. 분할, 중복 검사, 최종 리포트, 사람 검토 400세션.

## 9. 열린 질문

정하지 않은 것(모델 입출력과 크기, 파일럿 승인, LABELING과 label_rules가 어긋나는 곳, 기존 v2 템플릿의 두 정답)은 [README_ml-train-open-questions.md](README_ml-train-open-questions.md)에 모았다.
