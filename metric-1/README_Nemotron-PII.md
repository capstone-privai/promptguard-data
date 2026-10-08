# Nemotron-PII 변환본

[nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII)를 우리 세션 형식으로 바꾼 데이터다. Nemotron-PII는 50여 개 업종의 업무 문서(설정 파일, API 문서, 비밀번호 안내 메일, 가입 양식, 보안 정책 등)를 합성해 PII span을 붙인 데이터다. 여기서 `password`, `api_key`, `http_cookie` 라벨만 골라 지표 1의 정답으로 바꿨다. 기존 데이터에 거의 없던 **자연어 문서와 업무 양식 속 비밀값**을 시험한다.

외부 데이터이므로 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다. 원본 라이선스는 CC BY 4.0이다. 변환 결과는 git에 올리지 않고(`.gitignore`) 아래 순서대로 다시 만든다.

## 다시 만들기

`b70ffaf5ff39e079776134c5bf4381f00a9fd1ed` 리비전 기준. test split 파일 하나(약 150MB)만 있으면 된다. 변환에는 `pyarrow`가 필요하다(`pip install pyarrow`).

```bash
# 1. 받기 (huggingface_hub의 hf CLI)
hf download nvidia/Nemotron-PII --repo-type dataset --revision b70ffaf5ff39e079776134c5bf4381f00a9fd1ed \
  --include "data/test-*" --local-dir ../Nemotron-PII

# 2. 변환과 검증 (이 저장소 루트에서)
python metric-1/scripts/convert_nemotron_pii.py --nemotron ../Nemotron-PII
python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_Nemotron-PII.jsonl --nemotron ../Nemotron-PII
```

`--positives`, `--negatives`로 뽑는 문서 수(기본 3,000개씩)를, `--channel`로 채널 배정(아래)을 바꿀 수 있다.

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_Nemotron-PII.jsonl` | 문서 하나가 세션 하나, item도 하나 |
| `data_answer/gold_from_Nemotron-PII.jsonl` | 정답 span. `gold.jsonl`과 같은 형식 |
| `labels_from_Nemotron-PII.jsonl` | 원본의 모든 span(자격증명이 아닌 PII 포함)을 item 좌표로 옮기고 우리 판정을 붙인 분석용 파일. 값은 들어 있지 않다 |

세션 6,000개: 정답이 있는 문서 3,000개, 정답이 없는 문서 3,000개. 정답 span 3,866개(PASSWORD 1,969 / SECRET 1,388 / TOKEN 509). 29개 업종, 1,365가지 문서 유형이고, 미국식(`us`)과 국제식(`intl`) 문서가 반씩이다.

| channel | item | 정답 span |
|---|---|---|
| `prompt` | 3,062 | 1,892 |
| `tool_output` | 2,938 | 1,974 |

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
| `password` | span 전체 | PASSWORD | 9자 미만, 흔한 비밀번호 목록, placeholder |
| `api_key` | span 전체 | SECRET | 9자 미만, 공개 문서 예시 값, placeholder |
| `http_cookie` | **쿠키 값만** (`user_session=⟦값⟧; Path=/`) | TOKEN | 인증과 무관한 쿠키, 9자 미만, 공개 문서 예시 값 |
| `pin`, `cvv` | 아님 | | 전부 |
| 그 밖의 PII (이름, 이메일, 카드 번호 …) | 아님 | | 전부 |

- **인증 쿠키**: 쿠키 이름에 `sess`, `sid`, `auth`, `jwt`, `token`, `api_key`, `access`, `refresh`, `remember`, `login`, `credential`이 들어가면 인증 쿠키로 본다. 이름에 `csrf`, `xsrf`, `xss`, `cart`, `consent`, `pref`, `track`, `utm`, `_ga`, `feature`, `order`, `timezone`, `lang`, `font`, `theme`가 들어가면 인증 쿠키가 아니다.
- **같은 값이 문서의 다른 곳에 또 나오면 그 위치도 정답이다**(9개). 원본은 한 번만 라벨한 경우가 있다.
- 겹치는 정답 span은 합치고, type은 더 긴 span을 따른다.
- 원본의 offset을 기준으로 쓴다. 원본 span의 `text` 필드는 가끔 소문자로 바뀌어 있다(문서에서 문장 첫 글자라 대문자인 `Password1`이 `password1`로 적힌 경우). 대소문자 말고도 다르면 그 span을 버린다(이 표본에서는 0개).

### 정답에서 뺀 것 (labels 파일에만 기록)

| kind | 원본 라벨 | 수 | 내용 |
|---|---|---|---|
| `short_password` | password | 93 | 9자 미만 (`River45#`, `iloveyou`, `welcome1`) |
| `common_password` | password | 5 | 흔한 비밀번호 목록에 있는 9자 이상 값 (`123456789`, `password1` 등) |
| `placeholder` | password | 1 | `********`, `732****`, `YOUR_API_KEY_HERE` 같은 자리표시자 |
| `known_example` | api_key 32, http_cookie 83 | 115 | jwt.io의 예시 JWT를 그대로 쓰거나 payload만 바꾼 값 (AWS 문서의 `…EXAMPLE` 키처럼 `example`이 든 값은 placeholder로 센다) |
| `non_auth_cookie` | http_cookie | 208 | `csrf_token`, `timezone`, `_ga`, `pref_layout`, `order_id` 같은 쿠키 |
| `cookie_name_only` | http_cookie | 13 | `=`가 없이 쿠키 이름만 라벨된 span |
| `short_cookie` | http_cookie | 1 | 값이 9자 미만인 인증 쿠키 |
| `pin` | pin | 377 | 4~6자리 PIN |
| `cvv` | cvv | 286 | 카드 보안 코드 |
| `pii_other` | 그 밖의 라벨 | 44,999 | 이름, 이메일, 날짜, 주소, 카드 번호, 계좌 번호 등 |

탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. `per_edit.jsonl`의 좌표를 labels 파일과 맞추면 과잉 마스킹이 PIN이나 카드 번호에서 나왔는지, 쿠키에서 나왔는지 나눠 볼 수 있다.

## 기존 두 데이터(CredData, privesc-llm-data)와 같은 기준으로 맞춘 점

| 결정 | 근거 |
|---|---|
| 9자 미만 비밀번호와 흔한 비밀번호는 정답이 아니다 | privesc가 9자 미만 값을 흔한 비밀번호 목록에서 온 값으로 보고 뺐고, CredData도 약한 비밀번호를 F로 둔다. 이 데이터의 짧은 값도 `River45#`, `welcome1` 같은 흔한 값이다. 길이 기준만으로 남는 `123456789` 같은 값은 목록으로 뺐다 |
| 공개 문서 예시 값(jwt.io 예시 JWT 등)은 정답이 아니다 | 지표 1 정의의 "문서에 나오는 예시 값 → 아님"(`AKIAIOSFODNN7EXAMPLE`)과 같다 |
| placeholder와 일부를 가린 값은 정답이 아니다 | 지표 1 정의, CredData의 X |
| 쿠키는 값만 정답이다 | 합성 데이터의 `Set-Cookie: session=⟦값⟧`과 같다. 쿠키 이름과 속성은 비밀이 아니다 |
| 같은 값의 다른 등장 위치도 정답이다 | privesc의 "값이 등장하는 모든 위치를 정답으로 잡는다"와 같다 |
| PIN과 CVV는 정답이 아니다 | 지표 1은 소프트웨어 자격증명(PASSWORD, SECRET, TOKEN, ACCESS_KEY, PRIVATE_KEY)을 본다. PIN은 4~6자리라 privesc의 길이 기준에도 걸린다 |
| 업무 문서 속 정책 예시 비밀번호("such as `Ocean@2025`")도 정답이다 | Nemotron은 실제 값과 예시 값을 구분하지 않는다. 문맥으로 가르는 규칙을 만들면 근거 없는 추측이 들어가므로 원본 라벨을 따른다. CredData의 T를 그대로 쓴 것과 같은 태도다 |

## 기준 시스템 점수

`runs/all_new_sources`(CredSweeper 1.18.5, gitleaks 8.30.1, PromptGuard `promptguard-demo-v0@915492b` mock predictor). CredSweeper와 gitleaks는 네 채널을 모두 검사했고, PromptGuard는 `tool_output`만 처리한다.

| 시스템 | recall | precision | F2 | 1,000줄당 과잉 마스킹 | recall (prompt / tool_output) | recall (PASSWORD / SECRET / TOKEN) |
|---|---|---|---|---|---|---|
| PromptGuard | 0.206 | 0.710 | 0.240 | 3.10 | 0.000 / 0.404 | 0.159 / 0.316 / 0.088 |
| CredSweeper ml=off | 0.309 | 0.652 | 0.345 | 6.05 | 0.209 / 0.404 | 0.233 / 0.465 / 0.175 |
| CredSweeper ml=on | 0.212 | 0.719 | 0.247 | 3.05 | 0.133 / 0.288 | 0.119 / 0.368 / 0.145 |
| gitleaks | 0.098 | 0.757 | 0.118 | 1.15 | 0.074 / 0.120 | 0.003 / 0.215 / 0.141 |

세 시스템 모두 recall이 낮다. 비밀번호가 `key=value` 꼴이 아니라 문장 속에 있기 때문이다("The password for accessing the project documents is …", "use the API key … for authentication"). [README_baseline-recall.md](../docs/README_baseline-recall.md)의 원인 1(키 이름 없는 자리의 값)이 자연어에서 그대로 드러난다. 값 앞 문맥별 recall과 마크다운·표·쿠키에서 놓치는 이유는 [새 외부 소스로 본 기존 시스템의 약점](../docs/README_baseline-new-sources.md)에 있다.

## 알려진 한계

- **LLM이 만든 합성 문서다.** 같은 비밀번호가 여러 문서에 반복된다(`Rainbow@2025`, `Michael1995`). 실제 업무 문서보다 비밀번호가 문장에 더 노골적으로 드러난다.
- **실제 값과 예시 값을 가르지 않는다.** 정책 문서의 "예를 들어 이런 비밀번호" 같은 값도 정답이다(위 표).
- **원본 라벨 누락은 고치지 않았다.** 라벨이 없는 비밀번호성 문자열이 문서에 있으면 그것을 가린 것은 과잉 마스킹으로 센다. CredData의 라벨 없는 줄과 같다.
- **영어 문서뿐이다.**
- **에이전트 세션이 아니다.** 문서 한 장이 세션 하나이고 도구 호출 맥락이 없다.
