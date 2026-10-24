# Nemotron-PII 변환본

[nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII)를 우리 세션 형식으로 바꾼 데이터다. Nemotron-PII는 50여 개 업종의 업무 문서(설정 파일, API 문서, 비밀번호 안내 메일, 가입 양식, 보안 정책 등)를 합성해 PII span을 붙인 데이터다. 여기서 `password`, `api_key`, `http_cookie` 라벨만 골라 metric-detection의 정답으로 바꿨다. 기존 데이터에 거의 없던 **자연어 문서와 업무 양식 속 비밀값**을 시험한다.

외부 데이터이므로 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다. 원본 라이선스는 CC BY 4.0이다. 변환 결과는 git에 올리지 않고(`.gitignore`) 아래 순서대로 다시 만든다.

## 다시 만들기

`b70ffaf5ff39e079776134c5bf4381f00a9fd1ed` 리비전 기준. test split 파일 하나(약 150MB)만 있으면 된다. 변환에는 `pyarrow`가 필요하다(`pip install pyarrow`).

```bash
# 1. 받기 (huggingface_hub의 hf CLI)
hf download nvidia/Nemotron-PII --repo-type dataset --revision b70ffaf5ff39e079776134c5bf4381f00a9fd1ed \
  --include "data/test-*" --local-dir ../Nemotron-PII

# 2. 변환과 검증 (이 저장소 루트에서)
python metric-detection/scripts/convert_nemotron_pii.py --nemotron ../Nemotron-PII
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_Nemotron-PII.jsonl --nemotron ../Nemotron-PII
```

`--positives`, `--negatives`로 뽑는 문서 수(기본 3,000개씩)를, `--channel`로 채널 배정(아래)을 바꿀 수 있다.

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_Nemotron-PII.jsonl` | 문서 하나가 세션 하나, item도 하나 |
| `data_answer/gold_from_Nemotron-PII.jsonl` | 정답 span. `gold.jsonl`과 같은 형식 |
| `labels_from_Nemotron-PII.jsonl` | 원본의 모든 span(자격증명이 아닌 PII 포함)을 item 좌표로 옮기고 우리 판정을 붙인 분석용 파일. 값은 들어 있지 않다 |

세션 6,000개: 정답이 있는 문서 3,000개, 정답이 없는 문서 3,000개. 정답 span 3,892개(PASSWORD 2,144 / SECRET 1,275 / TOKEN 473). 29개 업종, 1,365가지 문서 유형이고, 미국식(`us`)과 국제식(`intl`) 문서가 반씩이다.

| channel | item | 정답 span |
|---|---|---|
| `prompt` | 3,056 | 1,873 |
| `tool_output` | 2,944 | 2,019 |

정답이 많은 문서 유형은 Application Setup Guide, Temporary Password Notification, API Endpoint, API Documentation, Test Login Script, System Configuration File 순이다.

## 변환 규칙

### 문서 고르기

- **test split만 쓴다.** train split은 나중에 모델 학습에 쓸 여지를 남긴다.
- 원본은 uid 하나에 문서가 두 개(locale `us`, `intl`)씩 있고 내용이 다르다. 그래서 세션 id는 `nemotron-<uid>-<locale>`이다.
- 문서 순서는 `sha256(uid-locale)`로 정한다. 그 순서대로 정답이 있는 문서와 없는 문서를 3,000개씩 채운다. 같은 리비전이면 항상 같은 문서가 뽑힌다.
- 정답이 없는 문서에도 이름, 이메일, 카드 번호, 계좌 번호 같은 PII와 PIN, CVV가 들어 있다. 자격증명 탐지기가 이런 값을 가리면 과잉 마스킹이 된다.

### 채널

원본의 `document_format`으로 정한다. 같은 문서가 에이전트에 들어오는 가장 자연스러운 길을 골랐다.

| document_format | channel | 뜻 |
|---|---|---|
| `structured` (설정 파일, 양식, 스크립트, 표) | `tool_output` | 에이전트가 파일을 읽어 받은 도구 결과 |
| `unstructured` (메일, 편지, 메모, 정책 문서) | `prompt` | 사용자가 대화창에 붙여 넣은 글 |

기존 외부 데이터에는 `prompt` 채널 정답이 없었다(CredData는 `tool_output`뿐, privesc는 `prompt`에 정답 0개). 이 데이터의 절반이 `prompt` 채널이다. `tool_output`만 처리하는 시스템은 그만큼 놓친다. 모두 한 채널로 두려면 `--channel tool_output` 또는 `--channel prompt`를 준다.

### 정답

| 원본 라벨 | 정답 | type | 정답에서 빼는 경우 |
|---|---|---|---|
| `password` | span 전체 | PASSWORD | 예시라고 밝힌 값, placeholder |
| `api_key` | span 전체 | SECRET | 예시라고 밝힌 값, 공개 문서 예시 값, placeholder |
| `http_cookie` | **쿠키 값만** (`user_session=⟦값⟧; Path=/`) | TOKEN | 인증과 무관한 쿠키, 예시라고 밝힌 값, 공개 문서 예시 값 |
| `pin`, `cvv` | 아님 | | 전부 |
| 그 밖의 PII (이름, 이메일, 카드 번호 …) | 아님 | | 전부 |

- **인증 쿠키**: 쿠키 이름에 `sess`, `sid`, `auth`, `jwt`, `token`, `api_key`, `access`, `refresh`, `remember`, `login`, `credential`이 들어가면 인증 쿠키로 본다. 이름에 `csrf`, `xsrf`, `xss`, `cart`, `consent`, `pref`, `track`, `utm`, `_ga`, `feature`, `order`, `timezone`, `lang`, `font`, `theme`가 들어가면 인증 쿠키가 아니다.
- 원본 span은 생성기가 자격증명 자리에 넣은 값이라, 길이나 강도와 상관없이 정답이다([LABELING.md](LABELING.md)). 짧은 비밀번호(`River45#`, `welcome1`)도 정답이다.
- **예시라고 밝힌 값은 정답이 아니다**(`doc_example`). 값 바로 앞이 "such as", "like", "e.g.", "for example", OpenAPI의 `example:`인 경우다(`label_rules.is_example`). 정책 문서의 "use a strong password, such as `River2025!`"가 여기에 든다.
- **같은 값이 문서의 다른 곳에 또 나오면** LABELING.md의 퍼뜨림 기준을 따른다. 고유한 값은 식별자 자리가 아니면 정답(`repeated_value`, 14개), 흔한 값은 자격증명 자리에서만 정답이다. 정답이 아닌 등장은 `identifier`나 `not_propagated`로 남는다.
- 겹치는 정답 span은 합치고, type은 더 긴 span을 따른다.
- 원본의 offset을 기준으로 쓴다. 원본 span의 `text` 필드는 가끔 소문자로 바뀌어 있다(문서에서 문장 첫 글자라 대문자인 `Password1`이 `password1`로 적힌 경우). 대소문자 말고도 다르면 그 span을 버린다(이 표본에서는 0개).

### 정답에서 뺀 것 (labels 파일에만 기록)

| kind | 원본 라벨 | 수 | 내용 |
|---|---|---|---|
| `doc_example` | password 33, api_key 27, http_cookie 22 | 82 | 글에서 예시라고 밝힌 값 ("such as …", "like …", `example:`) |
| `placeholder` | password | 1 | `********`, `732****`, `YOUR_API_KEY_HERE` 같은 자리표시자 |
| `known_example` | api_key 32, http_cookie 68 | 100 | jwt.io의 예시 JWT를 그대로 쓰거나 payload만 바꾼 값 (AWS 문서의 `…EXAMPLE` 키처럼 `example`이 든 값은 placeholder로 센다) |
| `non_auth_cookie` | http_cookie | 193 | `csrf_token`, `timezone`, `_ga`, `pref_layout`, `order_id` 같은 쿠키 |
| `cookie_name_only` | http_cookie | 11 | `=`가 없이 쿠키 이름만 라벨된 span |
| `identifier` | 정답 값의 다른 등장 | 11 | 정답 값이 사용자명 칸 같은 식별자 자리에 또 나온 것 |
| `pin` | pin | 405 | 4~6자리 PIN |
| `cvv` | cvv | 288 | 카드 보안 코드 |
| `pii_other` | 그 밖의 라벨 | 45,024 | 이름, 이메일, 날짜, 주소, 카드 번호, 계좌 번호 등 |

탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. `per_edit.jsonl`의 좌표를 labels 파일과 맞추면 과잉 마스킹이 PIN이나 카드 번호에서 나왔는지, 쿠키에서 나왔는지 나눠 볼 수 있다.

## LABELING.md를 이 데이터에 적용한 점

| 결정 | 근거 |
|---|---|
| 짧거나 흔한 비밀번호도 정답이다 | 값의 강도는 보지 않는다(LABELING.md "원칙"). 생성기가 비밀번호 자리에 넣은 값이다 |
| 공개 문서 예시 값(jwt.io 예시 JWT 등)은 정답이 아니다 | metric-detection 정의의 "문서에 나오는 예시 값 → 아님"(`AKIAIOSFODNN7EXAMPLE`)과 같다 |
| placeholder와 일부를 가린 값은 정답이 아니다 | metric-detection 정의, CredData의 X |
| 쿠키는 값만 정답이다 | 합성 데이터의 `Set-Cookie: session=⟦값⟧`과 같다. 쿠키 이름과 속성은 비밀이 아니다 |
| 같은 값의 다른 등장 위치는 퍼뜨림 기준을 따른다 | LABELING.md "같은 값의 다른 등장 위치" |
| PIN과 CVV는 정답이 아니다 | metric-detection은 소프트웨어 자격증명(PASSWORD, SECRET, TOKEN, ACCESS_KEY, PRIVATE_KEY)을 본다(LABELING.md `non_credential`) |
| 업무 문서 속 예시 비밀번호("such as `Ocean@2025`")는 정답이 아니다 | LABELING.md `doc_example`: 글에서 예시라고 밝힌 값. Nemotron은 실제 값과 예시 값을 구분하지 않으므로 앞 문맥으로 가른다 |

## 기준 시스템 점수

아래 점수는 2026-10-24 정답 기준 통일(LABELING.md) 전의 정답으로 잰 것이다. 문서 표본과 정답이 바뀌었으므로 다시 재야 한다.

`metric-detection/results/all_20261014-021351`(2026-10-14, 정확 일치 채점. CredSweeper 1.19.0, gitleaks 8.30.1, PromptGuard `promptguard-claude-demoV0@8973016`의 탐지기 앙상블). 세 시스템 모두 채점하는 세 채널(`prompt`, `instructions`, `tool_output`)을 검사한다.

| 시스템 | recall | precision | F2 | 1,000줄당 과잉 마스킹 | recall (prompt / tool_output) | recall (PASSWORD / SECRET / TOKEN) |
|---|---|---|---|---|---|---|
| PromptGuard | 0.175 | 0.695 | 0.206 | 1.65 | 0.110 / 0.238 | 0.161 / 0.209 / 0.139 |
| CredSweeper ml=off | 0.255 | 0.540 | 0.285 | 6.05 | 0.147 / 0.359 | 0.191 / 0.380 / 0.163 |
| CredSweeper ml=on | 0.200 | 0.678 | 0.233 | 3.04 | 0.121 / 0.276 | 0.105 / 0.356 / 0.143 |
| gitleaks | 0.076 | 0.588 | 0.092 | 1.15 | 0.048 / 0.102 | 0.001 / 0.159 / 0.139 |

정확 일치 채점에서는 비밀값 바로 뒤의 마침표나 마크다운 `**`까지 가린 경우가 `over`(실패)가 된다. 이런 정답이 PromptGuard 125개(3.2%), CredSweeper ml=off 206개(5.3%)다. 다 가렸는지만 보면 recall은 0.208, 0.309다.

세 시스템 모두 recall이 낮다. 비밀번호가 `key=value` 꼴이 아니라 문장 속에 있기 때문이다("The password for accessing the project documents is …", "use the API key … for authentication"). [README_baseline-recall.md](docs/README_baseline-recall.md)의 원인 1(키 이름 없는 자리의 값)이 자연어에서 그대로 드러난다. 값 앞 문맥별 recall과 마크다운·표·쿠키에서 놓치는 이유는 [새 외부 소스로 본 기존 시스템의 약점](docs/README_baseline-new-sources.md)에 있다.

## 알려진 한계

- **LLM이 만든 합성 문서다.** 같은 비밀번호가 여러 문서에 반복된다(`Rainbow@2025`, `Michael1995`). 실제 업무 문서보다 비밀번호가 문장에 더 노골적으로 드러난다.
- **실제 값과 예시 값을 가르지 않는다.** 정책 문서의 "예를 들어 이런 비밀번호" 같은 값도 정답이다(위 표).
- **원본 라벨 누락은 고치지 않았다.** 라벨이 없는 비밀번호성 문자열이 문서에 있으면 그것을 가린 것은 과잉 마스킹으로 센다. CredData의 라벨 없는 줄과 같다.
- **영어 문서뿐이다.**
- **에이전트 세션이 아니다.** 문서 한 장이 세션 하나이고 도구 호출 맥락이 없다.
