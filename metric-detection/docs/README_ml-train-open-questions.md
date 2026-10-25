# ML 학습 데이터: 정해야 할 것

[ML 학습용 합성 데이터 계획](README_ml-train-plan.md)을 진행하면서 정하지 않은 것을 모았다. 정하면 이 문서에서 해당 항목을 지우고, 결과를 계획 문서와 코드에 반영한다.

- 지금 상태(2026-10-25): 계획의 3단계(카드 추첨기, LLM 템플릿 작성 스크립트)까지 끝났다. 다음은 4단계 파일럿이다. 파일럿은 이 작업과 다른 세션에서 [실행 절차](../templates/ml_train/README.md)대로 돌린다.
- 파일럿 전에 꼭 필요한 것: 2절의 API 키와 과금 계정, 사람 검토자(둘 다 정우가 맡는다). 나머지는 정하기 전까지 둘 기본값이 있다.

## 1. 모델 쪽에서 정할 것 (데이터 생성은 기다리지 않는다)

데이터는 "세션 안 item의 어느 span이 정답인가"만 담는다. 모델이 어떤 과제로 학습할지는 모델 담당이 정한 뒤, 이 데이터를 받아 그 과제의 형식으로 바꾼다. 그래서 아래 질문은 데이터 생성을 막지 않는다. 다만 나중에 줄일 수는 있어도 늘릴 수는 없는 것(item 길이, 반복 등장의 정답, 채널)은 넉넉하게 만들어 둔다. 모델 담당이 아직 정하지 않았다.

| 질문 | 정해진 뒤 변환할 때 할 일 | 생성할 때 해 두는 것 |
|---|---|---|
| 입출력 형식: item 하나를 넣고 span(시작, 끝, 유형)을 출력하는가, 토큰마다 태그를 붙이는가(BIO 등) | 글자 좌표 span을 그 형식으로 바꾸는 변환기를 만든다. 토큰 분류라면 LABELING.md의 경계(따옴표 안쪽, `Bearer ` 제외 등)가 토큰 중간에 걸리는 경우를 그때 다룬다 | 글자 좌표 span으로 만든다 |
| 모델이 같은 세션의 앞 item을 함께 보는가 | 퍼뜨림 기준(LABELING.md)은 세션 단위라, 앞에 나온 고유한 값이 뒤 로그에 다시 나오면 그곳도 정답이다. item 하나만 보는 모델이면 그런 등장을 학습 표적에서 빼거나 앞 item 일부를 문맥으로 붙인다 | 반복 등장과 그 정답을 그대로 만든다(계획 3.3절: 여러 item 30%, 여러 채널 20%) |
| 목표 모델 크기와 컨텍스트 길이 | 긴 item을 창 크기로 자른다 | 길이는 실제 트래픽에 맞춘 계획값으로 넉넉하게 만든다(계획 3.1절: tool_output 중앙값 500~800자, 10%는 3,000자 이상). 짧게 만든 item은 나중에 늘릴 수 없다 |
| privesc를 얼마나 섞는가 | train에 섞는 비율을 정한다. 많이 넣으면 비밀번호 학습량은 늘고 리눅스 권한 상승 분야 편향도 커진다 | 상관없다. 계획 문서는 train 정답의 30% 이하를 제안한다 |

정한 것: 학습 데이터의 tool_input에는 정답을 두지 않는다. 배포 환경에서 에이전트는 PromptGuard가 가린 표시만 보므로, tool_input은 비밀값 대신 그 표시(`[PASSWORD_1]` 등)를 담은 문맥으로 만든다(2026-10-25).

## 2. 파일럿 실행 승인

계획 4단계: LLM으로 템플릿 100개를 써서 300세션을 만들고, 자동 검사, 사람 검토 100세션, 비용 실측을 한다.

| 정할 것 | 지금 안 |
|---|---|
| 호출 방식 | 정했다: Claude API의 Message Batches(`ml_train_write.py`). 구독 계정으로 Claude Code를 반복 실행하는 방식은 쓰지 않는다 |
| 실행 승인 | 템플릿 100개, Claude Opus 5.5 Batch로 약 $6(추정, 계획 7절) |
| 생성 모델 | 학습용은 Opus 5.5, 분포 이동 test는 다른 모델(Sonnet 5.5) |
| **API 키와 과금 계정** | 정우가 맡는다 |
| **사람 검토자** | 정우가 맡는다. 2명이 100세션을 본다(1인당 약 3시간). 파일럿 통과 여부를 이 검토로 정한다 |

## 3. LABELING.md와 label_rules가 어긋나는 곳

학습 데이터는 `label_rules`가 정답으로 읽는 값만 만든다. 아래 항목은 LABELING.md 원칙과 `label_rules` 구현이 다르거나 기준이 비어 있어, 정할 때까지 생성하지 않는다.

| 항목 | 내용 | 선택지 |
|---|---|---|
| 공백으로 이은 패스프레이즈 (`correct horse battery staple`) | 원칙("자격증명 자리에 들어간 리터럴")으로는 정답이다. 그런데 `label_rules.is_phrase`가 흔한 영어 단어 여럿이 공백으로 이어진 값을 `descriptor`(`new password` 같은 설명 문구)로 읽어 정답에서 뺀다 | (a) `is_phrase`가 자격증명 자리(`passphrase:` 등)의 값은 문구로 보지 않게 고친다. (b) 지금처럼 생성하지 않는다. 생성기는 `-`, `_`, `.`로 잇거나 붙인 패스프레이즈만 만든다 |
| PuTTY 개인키 (`PuTTY-User-Key-File-3:` 블록) | LABELING.md "경계"에는 PEM 형식(BEGIN 줄부터 END 줄까지)만 있다. PuTTY 형식은 머리글, 공개 부분, 개인 부분, MAC이 여러 줄로 이어진다 | (a) 블록 전체, (b) `Private-Lines:` 아래 본문만, (c) 다루지 않는다 |
| 자리표시인데 label_rules가 정답으로 읽는 값 (비밀 출처 카탈로그 검토에서 찾음) | LABELING.md로는 template·reference인데 `exclusion_kind`가 None을 돌려준다: `<generate-with-openssl-rand-hex-32>`(LABELING.md의 template 예), `<base64-encoded>`, `django-insecure-change-me-in-production`, `${MAILCHIMP_API_KEY}-us1`. `value_gen.neg_template`은 앞의 것 대신 label_rules가 template으로 읽는 `<generate-a-key-with-openssl-rand-hex-32>`를 만든다(2026-10-25) | (a) `label_rules.EXCLUDED_VALUE`를 넓힌다(평가 데이터 정답이 바뀔 수 있다). (b) 지금처럼 이런 값은 대조군으로 만들지 않는다 |
| Sentry DSN 안의 공개 키 (`https://⟦키⟧@o1.ingest.sentry.io/1`) | URL의 사용자 자리에 키만 있고 비밀번호 자리가 없어 LABELING.md "URL 속 자격증명"에 맞는 경우가 없다. 카탈로그는 공개 키라 음성으로 둔다 | (a) 공개용 키처럼 정답(ACCESS_KEY), (b) 식별자. 정할 때까지 생성하지 않는다 |

## 4. 기존 v2 템플릿의 두 정답

평가 데이터 `sessions_2`(에이전트 세션 v2)의 정답 두 개가 `dataset_verify`는 통과하지만, 학습 데이터용으로 더 엄격하게 만든 자리 검사(`ml_train_build.py verify`)에는 걸린다. 고치면 sessions_2의 정답이 바뀐다.

| 세션 | 지금 정답 | 문제 | 고치는 방법 |
|---|---|---|---|
| `v2-nl-03-wiki` | 웹훅 URL `https://hooks.example.invalid/hooks/⟦토큰⟧`의 경로 끝 토큰 | LABELING.md는 웹훅처럼 자격증명 자체인 URL이면 URL 전체를 정답으로 본다 | 템플릿의 placeholder가 URL 전체를 덮게 한다(type SECRET) |
| `v2-weak-01-conftest` | `os.environ.get("ADMIN_PASSWORD", "admin")`의 `admin` | 원칙상 정답(기본값으로 넣은 비밀번호 리터럴)이지만, `label_rules`에 이 자리 규칙이 없어 흔한 값 `admin`이 자격증명 자리 밖으로 읽힌다 | `label_rules.SLOT`에 환경변수 기본값 자리(`getenv("…PASSWORD…", "⟦값⟧")`)를 더한다. 정답은 그대로다 |
