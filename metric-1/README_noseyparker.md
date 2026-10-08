# Nosey Parker 규칙 예시 변환본

비밀 탐지기 [Nosey Parker](https://github.com/praetorian-inc/noseyparker)의 내장 규칙 189개에 딸린 예시를 우리 세션 형식으로 바꾼 데이터다. 규칙마다 실제 코드·설정에서 가져온 듯한 짧은 예시(`examples`, 규칙이 잡아야 하는 것)와 비슷하지만 잡으면 안 되는 예시(`negative_examples`)가 있다. Anthropic, Slack, Stripe, Twilio, HashiCorp Vault, Azure, Okta, Mapbox 같은 **수백 종 서비스의 토큰 형식**을 한 번에 시험한다. 기존 데이터는 형식 종류가 적거나(합성 데이터, privesc) CredSweeper 규칙 중심(CredData)이었다.

외부 데이터이므로 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다. 원본 라이선스는 Apache-2.0이다. 변환 결과는 git에 올리지 않고 아래 순서대로 다시 만든다.

## 다시 만들기

`2e6e7f36ce36619852532bbe698d8cb7a26d2da7` 커밋 기준. 규칙 폴더만 받으면 된다(약 1MB). 변환에는 PyYAML이 필요하다(credsweeper를 설치하면 같이 깔린다).

```bash
# 1. 규칙 폴더만 받기 (sparse checkout)
git clone --filter=blob:none --sparse https://github.com/praetorian-inc/noseyparker ../noseyparker
git -C ../noseyparker checkout 2e6e7f36ce36619852532bbe698d8cb7a26d2da7
git -C ../noseyparker sparse-checkout set --no-cone '/crates/noseyparker/data/default/builtin/rules/*' '/LICENSE*'

# 2. 변환과 검증 (이 저장소 루트에서)
python metric-1/scripts/convert_noseyparker.py --noseyparker ../noseyparker
python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_noseyparker.jsonl --noseyparker ../noseyparker
```

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_noseyparker.jsonl` | 예시 하나가 세션 하나, item 하나 (channel `tool_output`) |
| `data_answer/gold_from_noseyparker.jsonl` | 정답 span |
| `labels_from_noseyparker.jsonl` | 모든 규칙의 모든 캡처와 우리 판정(규칙 id, 그룹 번호 포함). 값은 들어 있지 않다 |

세션 573개(양성 예시 430 + 음성 예시 143), 정답 span 351개(TOKEN 141 / SECRET 137 / PASSWORD 67 / ACCESS_KEY 3 / PRIVATE_KEY 3). 정답이 있는 세션은 336개다. 양성 예시 430개 중 311개, 음성 예시 143개 중 25개에 정답이 있다(아래).

예시는 에이전트가 읽은 파일 조각으로 보고 모두 `tool_output`에 둔다. CredData 변환과 같다.

## 변환 규칙

규칙마다 정규식이 있고, 그 캡처 그룹이 비밀값이다. **모든 규칙을 모든 예시에 적용한다.** 그래서 한 규칙의 음성 예시라도 다른 규칙이 비밀로 잡으면 정답이 생긴다(예: Slack bot 토큰 규칙의 음성 예시인 user 토큰은 user 토큰 규칙이 잡는다). 음성 예시 25개가 이렇게 정답을 얻었다.

### 어떤 캡처가 정답인가

| 규칙 | 정답 | type |
|---|---|---|
| 카테고리에 `secret`이 있는 규칙 | 비밀 그룹의 캡처. 기본은 1번 그룹이고, 사용자명·client id·호스트와 비밀을 함께 잡는 규칙 25개는 비밀 그룹만 쓴다(`SECRET_GROUPS`, 예: Generic Username and Password는 2번) | 규칙 이름으로: Private Key → PRIVATE_KEY, Password·Credentials·netrc → PASSWORD, Token·JWT·Bearer → TOKEN, 나머지 SECRET |
| AWS API Key (`np.aws.1`, 액세스 키 id), Mapbox Public Access Token (`np.mapbox.1`) | 캡처 | ACCESS_KEY |
| 그 밖의 `secret` 없는 규칙 (AWS 계정 id, S3·GCS 버킷, ARN, OAuth client id, age 공개키, Shopify 도메인 등) | 아님 | |
| 카테고리 `hashed` (bcrypt, sha512crypt, Kerberos 해시 등) | 아님 | |

캡처 값에 대해 다음은 정답에서 뺀다.

| kind | 수 | 내용 |
|---|---|---|
| `identifier` | 56 | `secret` 카테고리가 없는 규칙의 캡처 |
| `short` | 39 | 9자 미만 (`admin`, `pyne`, `4ian1234`, `password`) |
| `placeholder` | 35 | `aaaa…`(같은 글자 8개 이상), `ABCDEFGH…`, `12345678`, `a1b2c3…`, `xxxx`, `<…>`, `${…}` |
| `password_hash` | 19 | 비밀번호 해시 |
| `known_example` | 10 | 공개 문서의 예시 값: RFC 7617의 `open sesame`과 그 Basic 인증 문자열, RFC 6750의 `mF_9.B5f-4.1JqM`, `EXAMPLE`이 든 값 |
| `reference` | 4 | 변수 참조 (`$Password`, `%nothing%`) |
| `common_password` | 1 | 흔한 비밀번호 (`Secret123`) |

- 같은 값이 예시의 다른 곳에 또 나오면 그 위치도 정답이다.
- 겹치는 정답 span은 합치고, type은 더 긴 span을 따른다. 여러 규칙이 같은 값을 잡는 경우가 많아 66번 합쳤다.
- Python `re`가 받지 않는 정규식 2개(패턴 중간의 전역 플래그)는 플래그를 맨 앞으로 옮겨 컴파일한다.
- 예시 값 상당수는 Nosey Parker 작성자가 실제 값을 일부 바꿔 무력화한 값이다(값 중간의 `ace5`, `Cf99` 같은 표시). 실제 형식을 따르는 합성·난독화 값이므로 지표 1 정의에서는 자격증명이다. CredData의 난독화 T 값과 같다.

## 기존 두 데이터(CredData, privesc-llm-data)와 같은 기준으로 맞춘 점

| 결정 | 근거 |
|---|---|
| 해시는 정답이 아님 | privesc의 `password_hash` |
| 9자 미만, 흔한 비밀번호는 정답이 아님 | privesc, CredData |
| placeholder, 문서 예시 값, 변수 참조는 정답이 아님 | 지표 1 정의, CredData의 X |
| 식별자(계정 id, 버킷, client id)는 정답이 아님. 단 AWS 액세스 키 id와 공개용 키는 ACCESS_KEY 정답 | CredData가 AWS Client ID를 ACCESS_KEY로 두는 것, 지표 1 정의의 "공개용 키 → 자격증명", 합성 데이터의 `pk_test_` |
| 사용자명과 비밀을 함께 잡는 규칙은 비밀 부분만 | privesc에서 사용자명은 자격증명 자리에서만 정답으로 본 것과 같은 취지 |
| 같은 값의 모든 등장 위치가 정답 | privesc |

## 기준 시스템 점수

`runs/all_new_sources`. 모든 item이 `tool_output`이라 세 시스템이 같은 텍스트를 본다.

| 시스템 | recall | precision | F2 | partial 비율 | recall (PASSWORD / SECRET / TOKEN) |
|---|---|---|---|---|---|
| PromptGuard | 0.775 | 0.758 | 0.772 | 0.043 | 0.687 / 0.781 / 0.816 |
| CredSweeper ml=off | 0.789 | 0.749 | 0.781 | 0.028 | 0.687 / 0.796 / 0.830 |
| CredSweeper ml=on | 0.726 | 0.846 | 0.748 | 0.020 | 0.388 / 0.781 / 0.830 |
| gitleaks | 0.627 | 0.887 | 0.666 | 0.000 | 0.164 / 0.737 / 0.738 |

- **Nosey Parker 자신은 평가하지 않는다.** 이 예시는 Nosey Parker의 규칙 테스트라 그 도구는 거의 다 맞힌다. 여기서 보는 것은 CredSweeper, gitleaks, PromptGuard가 Nosey Parker가 아는 형식을 얼마나 아는가다.
- 예시가 한두 줄짜리라 `fp_per_1k_lines`(PromptGuard 88, gitleaks 26)는 크게 나온다. 다른 데이터와 비교하지 않는다.
- 어느 형식을 어느 도구가 놓쳤는지는 [새 외부 소스로 본 기존 시스템의 약점](../docs/README_baseline-new-sources.md#4-서비스-형식-규칙의-범위)에 있다.

## 알려진 한계

- **예시가 짧고 깨끗하다.** 대부분 비밀값이 한 줄짜리 대입문에 있다. 주변 맥락이 거의 없어 실제 파일보다 쉽다.
- **정답이 Nosey Parker 규칙에 묶인다.** 규칙의 캡처 경계가 곧 정답 경계다. 다른 탐지기가 값을 다르게 잘라도 다 덮으면 `full`이지만, 규칙이 접두어만 잡는 형식이면 탐지기가 넓게 가린 부분은 정답 밖이 된다.
- **규칙의 카테고리에 기댄다.** `secret` 카테고리가 빠진 규칙의 캡처는 실제로 비밀이어도 정답이 아니다.
- 비밀이 없는 일반 텍스트는 들어 있지 않다. 과잉 마스킹은 음성 예시와 예시 속 비밀 아닌 부분에서만 생긴다.
