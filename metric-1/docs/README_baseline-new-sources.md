# 새 외부 소스로 본 기존 시스템의 약점

2026-10-08에 더한 외부 소스 4개(Nemotron-PII, Nosey Parker, openhands-feedback, SWE-Gym)로 기존 시스템(CredSweeper, gitleaks)을 채점한 결과를 정답 span과 edit 단위로 따라가 약점을 정리한 문서다. [기존 시스템의 recall이 낮은 이유](README_baseline-recall.md)의 후속이다. 그 문서가 합성 데이터, CredData, privesc-llm-data에서 놓친 정답을 봤다면, 이 문서는 새 소스가 처음 보여 준 세 가지를 본다.

- **업무 문서와 자연어 속 비밀** (Nemotron-PII): 메일, 안내문, API 문서, 양식
- **수백 종 서비스의 토큰 형식** (Nosey Parker): 규칙 189개의 예시
- **실제 에이전트 트래픽의 과잉 마스킹** (openhands-feedback, SWE-Gym): 정답이 거의 없는 실제 세션 약 95만 줄

원인이 의심되면 같은 줄을 도구에 직접 넣어 확인했다. 아래 표의 "찾음", "못 찾음"은 그 결과다.

- 대상 실행: `metric-1/results/all_new_sources`. 지금 `data_test/`, `data_answer/`의 네 데이터와 SHA-256이 같다.
- 도구 버전: CredSweeper 1.18.5, gitleaks 8.30.1(기본 설정), PromptGuard `promptguard-demo-v0@915492b`(predictor=mock)
- 판정은 [채점 기준](../metric-1/README.md#채점-기준)을 따른다. `partial`(일부만 가림)도 실패로 센다.
- 시스템 구성: CredSweeper와 gitleaks는 네 채널을 모두 본다. PromptGuard는 `tool_output`만 처리하고 탐지는 CredSweeper(ML off)라서, 아래 CredSweeper의 약점을 그대로 물려받는다.
- 규칙별 분석: 채점기와 같은 설정으로 CredSweeper를 다시 돌려 탐지마다 규칙 이름을 붙였다(span 판정은 실행 기록과 모두 같다). gitleaks는 탐지 결과 파일의 규칙 이름을 썼다.

## 요약

### 놓친 비밀

| 데이터셋 | 정답 | PromptGuard | CS ml=off | CS ml=on | gitleaks | 비고 |
|---|---|---|---|---|---|---|
| Nemotron-PII | 3,866 | 0.206 | 0.309 | 0.212 | **0.098** | |
| Nosey Parker | 351 | 0.775 | 0.789 | 0.726 | 0.627 | |
| openhands-feedback | 47 | 0.957 | 1.000 | 0.979 | **0.106** | 상한값이다. 정답 후보를 CredSweeper와 gitleaks가 냈다 |
| SWE-Gym | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 정답이 2개라 의미가 적다 |

### 실제 에이전트 트래픽의 과잉 마스킹

정답과 겹치지 않는 edit 수다. 괄호는 1,000줄당 수다.

| 데이터셋 | 줄 수 | PromptGuard | CS ml=off | CS ml=on | gitleaks |
|---|---|---|---|---|---|
| openhands-feedback | 344,065 | 181 (0.53) | 293 (0.85) | 64 (0.19) | 2 (0.006) |
| SWE-Gym | 604,706 | 516 (0.85) | 733 (1.21) | 264 (0.44) | 20 (0.03) |

두 도구의 약점은 방향이 반대다. CredSweeper(ML off)는 많이 찾지만 코드에서 비밀이 아닌 것도 많이 가린다. gitleaks는 거의 잘못 가리지 않는 대신 Nemotron-PII와 openhands-feedback에서 정답의 90%를 놓친다. 약점은 아래 아홉 가지로 정리된다. 1~5는 비밀을 놓치는 쪽, 6~7은 비밀이 아닌 것을 가리는 쪽, 8은 CredSweeper의 ML 검증, 9는 정답·데이터 쪽 문제다.

| # | 약점 | 영향 | 대표 근거 |
|---|---|---|---|
| 1 | **문장 속 값** | 둘 다 | Nemotron 정답의 54%(2,085개)가 문장 속에 있다. CS 0.050, gitleaks 0.005 |
| 2 | **문서 서식이 키-값 꼴을 깨뜨림** | 둘 다 | `**Password:** X`는 CS 5/99, gitleaks 0/99. 콜론이 굵은 글씨 밖에 있는 `**Password**: X`는 CS 131/134 |
| 3 | **키 이름 목록의 빈틈** | 둘 다 | 쿠키 `user_session=`, `user_sess=`의 값 418개: CS 12, gitleaks 0. gitleaks는 `PASS`, `PWD`, curl 밖의 `Bearer`를 모른다 |
| 4 | **서비스 형식 규칙의 범위** | 둘 다 | Nosey Parker에서 둘 다 놓친 58개 중 31개는 어느 쪽에도 형식 규칙이 없다. gitleaks는 URL 속 비밀번호를 1/14만 찾는다 |
| 5 | **gitleaks 일반 규칙의 값 조건** | gitleaks | 특수문자가 든 비밀번호 0/338(Nemotron), Django `SECRET_KEY` 0/36(openhands). 값 속 `dev_`, 값 뒤의 `,` `?` `&`, 값 앞의 `b'`에서도 탈락 |
| 6 | **키워드 규칙이 코드 조각을 값으로 잡음** | CS ML off | 실제 트래픽 과잉 마스킹 1,026개 중 730개. `key: "Enter"`, `max_input_tokens = 4096` |
| 7 | **값 모양만 보는 info 규칙** | CS | ML을 켜도 남는 과잉 마스킹 328개 중 286개가 UUID, 15자 소문자, 도메인 규칙에서 나온다 |
| 8 | **ML 검증이 기억하기 쉬운 비밀번호를 버림** | CS ML on | 네 데이터에서 새로 찾은 정답 0개, 잃은 정답 396개. 단어가 든 비밀번호는 31%만 남는다 |
| 9 | **정답·데이터 쪽 문제** | 정답 | Nemotron의 구절 라벨(`Temporary Password` 등) 44개, Nosey Parker의 경계·placeholder·난독화 문제 17개 |

1, 3, 5, 8은 이전 문서에서 본 원인(원인 1, 4, 5와 ML 검증)이 새 데이터에서 더 크게 나타난 것이고, 2, 4, 6, 7은 새로 보인 것이다.

## 1. 문장 속 값

Nemotron-PII는 메일, 안내문, 정책 문서 같은 업무 문서다. 정답 3,866개를 값 앞 문맥(같은 줄 앞 80자)으로 나누면 다음과 같다.

| 값 앞 문맥 | 정답 | PromptGuard | CS ml=off | CS ml=on | gitleaks |
|---|---|---|---|---|---|
| 문장 (`… the temporary password X`) | 2,085 | 0.023 | 0.050 | 0.050 | 0.005 |
| 키-값 (`Password: X`, `"api_key": "X"`) | 819 | 0.634 | 0.951 | 0.534 | 0.344 |
| 쿠키 (`user_session=X; Path=/`) | 509 | 0.088 | 0.175 | 0.145 | 0.141 |
| 마크다운 굵은 글씨 (`**Password:** X`) | 259 | 0.483 | 0.529 | 0.471 | 0.004 |
| 표 셀 (`\| Password \| X \|`) | 78 | 0.103 | 0.103 | 0.103 | 0.013 |
| `Authorization: Bearer X` | 76 | 0.645 | 0.947 | 0.934 | 0.132 |
| XML 요소 (`<apiKey>X</apiKey>`) | 40 | 0.100 | 0.100 | 0.100 | 0.000 |

키-값 꼴이면 CredSweeper가 0.951을 찾지만, 문장 속 값은 0.050이다. 두 도구 모두 **키 이름 + 구분자(`=`, `:`) + 값** 꼴에서 후보를 만들기 때문에, 키워드가 값 바로 앞에 있어도 구분자가 없으면 후보가 생기지 않는다. privesc에서 본 위치 인자([이전 문서 원인 1](README_baseline-recall.md#1-키-이름-없는-자리의-값))와 같은 구조가 문서에서 나타난 것이다.

문장 속 값을 키워드와 값 사이의 거리로 다시 나눴다. 마지막 열은 CredSweeper를 문서 모드(`doc=True`, CLI의 `--doc`)로 돌린 결과다.

| 문장의 꼴 | 정답 | CS ml=off | gitleaks | CS 문서 모드 | 예 |
|---|---|---|---|---|---|
| 키워드 바로 뒤 | 1,249 | 0.055 | 0.009 | 0.048 | `Please use the temporary password H9f$KmP2wL8! to verify your identity.` |
| 키워드 + `is` | 195 | 0.036 | 0.000 | 0.851 | `Your chosen password is G4p@Zk9mX7q.` |
| 키워드가 몇 단어 앞 | 550 | 0.047 | 0.000 | 0.047 | `The password for accessing the portal is Rainbow@2025.` |
| 키워드가 뒤에 있거나 없음 | 91 | 0.022 | 0.000 | 0.022 | `… uses Pineapple$Cake#Rainbow as the default password` |

- **문서 모드는 `password is X` 꼴만 메운다.** 문서 모드는 규칙 집합을 문서용(`DOC_CREDENTIALS` 등)으로 바꾸는 모드라 코드용 규칙이 꺼진다. 그래서 마크다운 `**Password**: X`를 거의 못 찾게 되고(0.529 → 0.039), 데이터 전체 recall은 0.309에서 0.301로 오히려 내려간다. 두 모드로 따로 돌려 합쳐도 0.352다.
- **두 도구를 합쳐도 같다.** CredSweeper와 gitleaks의 edit를 합쳐 채점하면 1,202개(0.311)로, CredSweeper 혼자보다 9개 많다. 두 도구가 같은 자리에서 함께 놓친다.
- **정답의 절반(1,892개)이 `prompt` 채널에 있다.** 비정형 문서를 사용자가 붙여 넣은 글로 두었기 때문이다. CredSweeper는 여기서 396개(0.209), gitleaks는 140개(0.074)를 찾는다. PromptGuard는 `prompt`를 처리하지 않아 0개다([이전 문서 원인 2](README_baseline-recall.md#2-처리하지-않는-채널-promptguard)).

Nosey Parker에도 같은 꼴이 있다. `The default Password is 'blooberry'`, `ensure the password is "centipede"`는 두 도구 모두 놓쳤고 문서 모드는 찾는다. Jenkins가 출력한 초기 관리자 비밀번호처럼 안내 문장 다음 줄에 값만 있는 것은 어느 모드도 못 찾는다.

## 2. 문서 서식이 키-값 꼴을 깨뜨림

키 이름이 값 바로 앞에 있어도 그 사이에 서식 문자가 끼면 키-값 꼴로 보지 않는다. Nemotron-PII의 마크다운 굵은 글씨는 콜론의 위치 하나로 결과가 갈린다.

| 꼴 | 정답 | CS ml=off | gitleaks |
|---|---|---|---|
| `**Password**: X` (콜론이 굵은 글씨 밖) | 134 | 131 | 1 |
| `**Password:** X` (콜론이 굵은 글씨 안) | 99 | 5 | 0 |
| `the **password** X` (콜론 없음) | 26 | 1 | 0 |

같은 값을 서식만 바꿔 넣어 확인했다.

| 줄 | CredSweeper | gitleaks |
|---|---|---|
| `API Key: sP7dK8nYmZ2rWxQ1tLvC3aH5jR9tUvM4` | 찾음 | 찾음 |
| `- **API Key**: sP7dK8nY…` | 찾음 | 못 찾음 |
| `- **API Key:** sP7dK8nY…` | 못 찾음 | 못 찾음 |
| `\| API Key \| sP7dK8nY… \|` | 못 찾음 | 못 찾음 |
| `<apiKey>sP7dK8nY…</apiKey>` | 못 찾음 (문서 모드는 찾음) | 못 찾음 |
| `<add key="FromEmailPassword" value="sP7dK8nY…"/>` | 못 찾음 (문서 모드는 값 대신 키 이름을 가림) | 못 찾음 |
| `machine api.github.com login ziggy password sP7dK8nY…` (netrc) | 못 찾음 | 못 찾음 |
| `new NetworkCredential("user@example.com", "sP7dK8nY…")` | 못 찾음 | 못 찾음 |

- gitleaks의 `generic-api-key`는 키워드와 구분자 사이에 글자, 공백, `.`, `-`, 따옴표만, 구분자와 값 사이에 따옴표, 공백, `=`만 허용한다. `**`가 끼면 콜론이 어디 있든 놓친다.
- Nemotron의 표 셀(78개)은 두 도구 모두 0.1 안팎이다. XML 요소(40개)에서 CredSweeper가 찾은 4개는 값이 UUID라서 UUID 규칙에 걸린 것이고, 요소 이름(`<apiKey>`, `<Password>`)을 보고 찾은 것은 없다.
- Nosey Parker에서 두 도구가 모두 놓친 비밀번호 11개도 키-값 꼴이 아니다: 문장(2), .NET 설정의 `<add key="…Password" value="…"/>`(2), netrc(2), `NetworkCredential("user", "pw")`(2), PsExec의 `-p dev_admin`(1), 안내 문장 다음 줄의 값(1), 붙여 쓴 문자열 `'A3T0…''ded7…'`(1).

## 3. 키 이름 목록의 빈틈

키-값 꼴이어도 키 이름이 도구의 키워드 목록에 없으면 후보가 생기지 않는다([이전 문서 원인 4](README_baseline-recall.md#4-규칙에-없는-키-이름)).

**쿠키 이름.** Nemotron-PII의 TOKEN 정답 509개는 모두 인증 쿠키의 값이다.

| 쿠키 | 정답 | CS ml=off | gitleaks |
|---|---|---|---|
| `user_session=`, `user_sess=` (값은 10~16자 무작위 문자열) | 418 | 12 | 0 |
| 그 밖의 이름(`auth_token=`, `api_key=` …), 값이 JWT가 아님 | 18 | 10 | 6 |
| 값이 JWT (`jwt_token=eyJ…`) | 73 | 67 | 66 |

`session`은 두 도구의 키워드가 아니다. 그래서 `Set-Cookie: user_session=…`은 둘 다 못 찾고, `Set-Cookie: session_token=…`은 `token` 덕분에 둘 다 찾는다. CredSweeper가 찾은 `user_session` 값 12개도 같은 줄의 다른 키워드(8개), 15자 소문자 패턴(3개), UUID 규칙(1개)에 우연히 걸린 것이다. JWT 쿠키는 값의 모양(`eyJ…`)으로 찾는다.

**gitleaks의 키워드.** gitleaks 일반 규칙의 키워드는 `access`, `auth`, `api`, `credential`, `creds`, `key`, `passwd`, `password`, `secret`, `token`이다. 줄임말은 모른다.

| 줄 | CredSweeper | gitleaks |
|---|---|---|
| `DB_PASSWORD=Wk7jQ9zRp2bNtLmY` | 찾음 | 찾음 |
| `DB_PASS=Wk7jQ9zRp2bNtLmY` | 찾음 | 못 찾음 |
| `DB_PWD=Wk7jQ9zRp2bNtLmY` | 찾음 | 못 찾음 |
| `Authorization: Bearer sV9pB2tL…` | 찾음 | 못 찾음 |
| `curl -H "Authorization: Bearer sV9pB2tL…" https://…` | 찾음 | 찾음 (`curl-auth-header`) |

gitleaks는 `Bearer` 토큰을 curl 명령 안에서만 찾는다. Nemotron의 `Authorization: Bearer` 76개 중 curl 명령 안 9개는 모두 찾았지만, 나머지 67개는 1개만 찾았다(CredSweeper는 `Bearer Authorization` 규칙으로 76개 중 72개).

**두 도구 모두 모르는 키 이름.** Azure DevOps 토큰을 담은 `ado_pat`, `azure_devops_pat`, CodeClimate의 `CC_TEST_REPORTER_ID`, Jenkins의 `Jenkins-Crumb:` 헤더, API 문서의 `example:`, `value:`(Nemotron 26개 중 CredSweeper 5개, gitleaks 3개) 같은 자리다.

## 4. 서비스 형식 규칙의 범위

키 이름 없이 값만 있는 토큰(`xoxb-…`, `dp.st.…`)은 그 서비스의 형식 규칙이 있어야 찾는다. Nosey Parker에서 값 앞에 키가 없는 정답 94개는 CredSweeper 0.596, gitleaks 0.511이다. 두 도구가 아는 형식이 서로 달라서, 합치면 recall이 0.835(CredSweeper 0.789, gitleaks 0.627)로 오른다. 놓친 정답을 도구별로 나누면 다음과 같다.

| | 정답 | 내용 |
|---|---|---|
| 둘 다 놓침 | 58 | 아래 표 |
| CredSweeper만 놓침 | 16 | 형식 규칙 없음 6(SonarQube 옛 형식 3, Mapbox 공개 토큰 `pk.`, New Relic `NRAA-`, Blynk 조직 자격증명), 규칙의 길이 상한(160자)을 넘는 Vault 배치 토큰 1(`partial`), 함수 인자 2(`env('TWILIO_API_KEY', '…')`처럼 `,` 뒤의 값. gitleaks는 `,`도 구분자로 받는다), [9절](#9-정답데이터-쪽-문제)의 데이터 문제 7 |
| gitleaks만 놓침 | 73 | [5절](#5-gitleaks-일반-규칙의-값-조건)의 값 조건 38(특수문자 18, 엔트로피 10, 값 뒤 `&` 4, 불용어 3, 10자 미만 3), 키 없는 토큰 17(Docker Hub `dckr_pat_` 3, NuGet 2, Tavily `tvly-` 2, Square `sq0atp-`, Google `ya29.` 등. 형식 규칙이 없거나 예시가 규칙의 형식과 다르다), URL 속 비밀번호 13, 키워드가 아닌 키 이름 5 |

두 도구가 모두 놓친 58개:

| 원인 | 정답 | 예 |
|---|---|---|
| 형식 규칙으로도, 키 이름으로도 잡히지 않음 | 31 | Doppler 서비스·CLI·서비스 계정·SCIM·감사 토큰(`dp.st.`, `dp.ct.` …, 5), Microsoft Teams 옛 웹훅 주소(5), TrueNAS API 키(JSON-RPC `params` 안, 4), Dependency-Track `odt_`(3), Twitch 스트림 키 `live_`(3), ThingsBoard 주소 경로 속 토큰(3), Azure DevOps PAT(2), crates.io, Okta, New Relic EU 라이선스 키, CodeClimate, Jenkins crumb, Vault unseal 키(명령 인자) |
| 키-값 꼴이 아님 | 11 | [2절](#2-문서-서식이-키-값-꼴을-깨뜨림) 마지막 항목 |
| 키-값 꼴이지만 CredSweeper 필터와 gitleaks 값 조건에 함께 걸림 | 6 | `Password=thisismypassword`(2), `secret: "development#product"`(2), `password = 'abuser123456'`, `password='1qay@WXS????'` |
| 정답 쪽 문제 | 10 | [9절](#9-정답데이터-쪽-문제) |

- **같은 서비스의 다른 토큰을 모른다.** CredSweeper와 gitleaks 모두 Doppler 개인 토큰(`dp.pt.`)만 안다. 접두어만 다른 나머지 5종은 놓친다.
- **형식이 바뀐 토큰을 모른다.** SonarQube 토큰은 CredSweeper가 접두어가 붙은 새 형식(`sqp_…`, `squ_…`)만 알고 접두어 없는 옛 형식(`-Dsonar.login=<40자 hex>`)은 모른다. Microsoft Teams 웹훅은 옛 주소(`outlook.office.com/webhook/…`)를 두 도구 모두 모른다. gitleaks는 새 주소(`….webhook.office.com/webhookb2/…`)용 규칙이 있지만, 넣어 보면 비밀값으로 UUID 안의 다섯 글자(`aed6-`)만 보고한다. 정규식의 첫 캡처 그룹이 UUID의 반복 부분(`([a-z0-9]{4}-){3}`)이기 때문이다. 이 결과대로 가리면 주소가 거의 그대로 남는다.
- **우연히 일부만 가린다.** Microsoft Teams 옛 웹훅 4개는 CredSweeper의 UUID 규칙이 주소 속 UUID만 가려 `IncomingWebhook/<32자 hex>/` 부분이 남았다(`partial`). 형식을 알아서 가린 것이 아니다.
- **gitleaks에는 URL 속 비밀번호 규칙이 없다.** `mongodb://user:pass@host` 꼴 14개 중 1개(GitHub 토큰 형식이라 걸린 값)만 찾았다. `DATABASE_URL=postgresql://service:…@db:5432/app`처럼 키워드가 붙어도 값에 `:`, `/`, `@`가 있어 일반 규칙에 걸리지 않는다. CredSweeper는 `URL Credentials` 규칙으로 14개를 모두 찾는다.

## 5. gitleaks 일반 규칙의 값 조건

형식이 정해지지 않은 값은 gitleaks에서 `generic-api-key` 규칙 하나가 맡는다. [이전 문서 원인 5](README_baseline-recall.md#5-gitleaks-일반-규칙의-값-조건)에서 본 조건(값의 글자가 `[A-Za-z0-9_.=-]`뿐, 엔트로피 3.5 초과, 숫자 하나 이상, 불용어 없음)이 새 데이터에서 더 크게 작용하고, 조건이 몇 가지 더 보였다.

**특수문자.** 사람이 정한 비밀번호에는 대개 특수문자가 있다.

- Nemotron에서 키-값 꼴인 비밀번호 398개 중 338개에 특수문자가 있고(`Ocean@2025`, `B7k#mP9vL2@xZ5`), gitleaks는 이 중 하나도 찾지 못했다. 특수문자가 없는 60개도 54개는 엔트로피가 3.5 이하라, 모두 합쳐 5개(0.013)를 찾았다.
- openhands-feedback의 Django `SECRET_KEY`(한 세션에 36곳)는 `django-insecure-` 뒤에 `^`, `!`, `%`, `(`, `@`, `#` 같은 글자가 섞인 값이라 0/36이다. OWASP Juice Shop 소스의 비밀번호 3개와 비밀번호 생성기가 출력한 값 1개도 특수문자나 공백 때문에 놓쳤다. 이 데이터에서 gitleaks recall이 0.106인 이유의 대부분이다.

**값 속의 불용어.** 이 규칙에는 불용어가 1,446개 있고, 값에 하나라도 들어 있으면 버린다. `dev_`, `read`, `write`, `view`, `user`, `session`, `example`도 불용어다.

| 값 (`api key: ` 뒤) | gitleaks |
|---|---|
| `8Zk3pLw4TbM7mQ9sN6xUvZGtR5kLjY1` | 찾음 |
| 같은 값 앞에 `test_`, `prod_`, `live_`, `svc_`, `abc_` | 찾음 |
| 같은 값 앞에 `api_dev_`, `xyz_dev_`, `write_`, `read_`, `view_` | 못 찾음 |

Nemotron의 API 키에는 `api_dev_`, `write_dev_`, `read_dev_` 같은 접두어가 많다. 키-값 꼴인 API 키 중 gitleaks가 놓친 144개 중 76개가 불용어(`dev_`, `write`, `read`, `view`, `staging` …) 때문이다. Nosey Parker의 `password = 'abuser123456'`도 `user` 때문에 버린다.

**값 앞뒤의 글자.** 값 바로 뒤에는 공백, 따옴표, `;`, 줄 끝만 올 수 있고, 값 바로 앞에는 따옴표, 공백, `=`만 올 수 있다. 문장, URL, 코드에 흔한 글자가 오면 놓친다.

| 줄 | gitleaks |
|---|---|
| `api key: Wk7jQ9zRp2bNtLmYvF0eD8zXnWvTq6mB` | 찾음 |
| `api key: Wk7jQ9zR…, endpoint: /data` | 못 찾음 |
| `api key: Wk7jQ9zR…?` | 못 찾음 |
| `curl "https://blynk.cloud/external/api/get?token=Rps15JIC…"` | 찾음 |
| `curl "https://blynk.cloud/external/api/get?token=Rps15JIC…&V1"` | 못 찾음 |
| `FERNET_KEY = 'Q7mZp2Lw…'` | 찾음 |
| `FERNET_KEY = b'Q7mZp2Lw…'` (Python bytes) | 못 찾음 |

`.`은 값의 글자로 받아들이므로 문장 끝의 마침표는 통과한다. 데이터에서는 Nemotron의 `,`(15), 마크다운의 `**`(9), Nosey Parker의 `&`(Blynk 4), openhands-feedback의 `b'…'`(Fernet 키 2)가 이 조건에 걸렸다. CredSweeper는 이 절의 줄을 모두 찾는다.

## 6. 키워드 규칙이 코드 조각을 값으로 잡음

openhands-feedback과 SWE-Gym은 실제 에이전트 트래픽이라 정답이 거의 없고, 가린 것은 대부분 과잉 마스킹이다. CredSweeper(ML off)의 과잉 마스킹 1,026개 중 71%(730개)가 키워드 규칙(`Key`, `Password`, `Token`, `API`, `Auth` 등)에서 나왔다. 키 이름 안에 키워드가 들어 있고 뒤에 `=`나 `:`가 오면 그 뒤를 값으로 보는데, 코드에는 이런 줄이 많다. 무엇을 가렸는지는 정답 검토 때 남긴 판정([reviews/](../metric-1/reviews/README.md))으로 나눴다.

| 가려진 것 | CS ml=off | CS ml=on | 예 |
|---|---|---|---|
| 9자 미만 코드 조각 | 338 | 24 | `key: "Enter"`, `self._initial_pwd = work_dir`, `KeyError: When`, `Co-authored-by: Xingyao`(`authored`의 `auth`) |
| 변수·속성 참조 | 95 | 0 | `<li key={pr.id}>`, `"KeySchema": self.schema`, `password += string.ascii_letters` |
| 식별자·단어 | 78 | 6 | `AuthFlow='ADMIN_NO_SRP_AUTH'`, `_border_key_map = {"diagonalup": …` |
| 숫자·버전·날짜 | 74 | 0 | `max_input_tokens = 4096`, `key_size=2048`, `"jsonwebtoken": "^9.0.2"`, `X-GitHub-Api-Version: 2022-11-28` |
| 코드 식 | 41 | 0 | `cfg[key] = instantiate_node(` |
| placeholder·가린 흔적 | 36 | 0 | `export GITHUB_TOKEN=ghp_-XXX`, `os.environ['AWS_ACCESS_KEY_ID'] = 'dummy'` |
| 흔한 테스트 비밀번호 | 27 | 5 | moto 테스트의 `TempP@ssw0rd!`, `Testpass1!` |
| 그 밖(이름, 해시, SSH 호스트 키 지문) | 41 | 6 | `s3.put_object('my-bucket', …)`, dask `tokenize()` 해시 |
| 합계 | 730 | 41 | |

- **숫자를 가리면 과제가 막힌다.** [지표 2](../metric-2/README.md)의 t23에서 PromptGuard가 `token_ttl_seconds = 5400`의 숫자를 가려 실패한 것과 같은 꼴이 실제 트래픽에서 74번 나왔다. PromptGuard는 `tool_output`만 처리하므로 이 중 51개를 가린다.
- **ML 검증이 이 종류는 대부분 걸러 낸다(730 → 41).** 키워드 규칙은 ML 검증 대상이라, 값이 코드처럼 보이면 버린다.
- **문서에서도 같다.** Nemotron에서는 키워드가 있는 줄의 `:` 뒤를 값으로 잡아 시각 조각(`… valid until 2024-10-28T22:` 뒤의 `07:04.`), IPv6 주소 조각, URL 조각(`https:` 뒤의 `//owasp.org.`)을 가린다. `- **Key Performance Indicators**: Increase`처럼 `Key`로 시작하는 제목도 가린다.

gitleaks의 과잉 마스킹은 SWE-Gym 20개, openhands-feedback 2개뿐이다. moto 테스트의 `MasterUserPassword="test123456789"`(8), dask 해시를 출력한 `Token1: <32자 hex>`(10), `ClientToken` 자리의 placeholder(2), `KeyError: '<긴 식별자>'`(2)다. 5절의 엄격한 값 조건이 여기서는 장점으로 작용한다.

## 7. 값 모양만 보는 info 규칙

ML을 켜도 남는 과잉 마스킹 328개 중 286개는 아래 규칙에서 나온다. 모두 `severity: info`이고 ML 검증 대상이 아니라(`use_ml`이 꺼져 있다), 값의 모양만 맞으면 가린다.

| 규칙 | 값 모양 | CS ml=off | CS ml=on | 가려진 것 |
|---|---|---|---|---|
| UUID | UUID | 173 | 173 | AWS request id(`<RequestId>…</RequestId>`), KMS 키 id, 리소스 id |
| Dropbox App secret | 15자 소문자·숫자 | 79 | 79 | 파일 이름(`img2tensorboard`, `cygwinccompiler`), 도메인(`amerpoultryassn`), 터미널 색 코드가 붙은 단어(`36mplatformdirs`) |
| Firebase Domain, AWS S3 Bucket | `*.firebaseio.com`, `*.s3.amazonaws.com` | 34 | 34 | 공개 API 주소(`hacker-news.firebaseio.com`), moto 테스트의 버킷 주소 |

CredSweeper를 `severity=low`로 돌려 info 규칙을 빼면, ML on 기준으로 SWE-Gym의 과잉 마스킹이 264개에서 21개, openhands-feedback이 64개에서 25개로 준다. 두 데이터의 정답은 하나도 잃지 않고, SWE-Gym의 21개는 gitleaks(20개)와 비슷하다. 반대로 Nemotron에서는 UUID 모양 API 키(`The API key for accessing transaction data is e5a8b34c-…`)를 잃어 recall이 0.212에서 0.177로 내려간다(ML off는 0.309 → 0.280). Nemotron에서 UUID 규칙으로만 찾은 API 키가 107개다. UUID 규칙은 문맥을 보지 않으므로 request id와 UUID 모양 키를 가르지 못하고, 둘 다 가리거나 둘 다 놓친다. Nosey Parker는 거의 바뀌지 않는다(0.789 → 0.786).

## 8. ML 검증이 기억하기 쉬운 비밀번호를 버림

CredSweeper의 ML 검증은 규칙이 만든 후보를 거르는 분류기다. 네 데이터 모두에서 ML을 켜서 새로 찾은 정답은 0개이고, 잃은 정답은 396개(Nemotron 373, Nosey Parker 22, openhands-feedback 1)다. 과잉 마스킹은 줄인다(실제 트래픽 1,026 → 328개).

잃은 값은 사람이 기억하기 쉬운 비밀번호에 몰려 있다. Nemotron에서 CS ml=off가 찾은 비밀번호 458개를 값의 모양으로 나누면 다음과 같다.

| 값 | ML off가 찾은 수 | ML on에서 남은 수 | 예 |
|---|---|---|---|
| 영어 단어가 든 값 | 298 | 93 (31%) | `River2025!`, `Ocean@2025`, `OceanWave#RedSunset` |
| 무작위 값 | 160 | 142 (89%) | `G7h$2mXkP@5b`, `b7M@k9P4j$5L2z` |

같은 값을 줄 모양만 바꿔 넣으면, 무작위 값은 어디서나 남고 단어가 든 값은 코드 대입문에서만 남는다.

| 값 | `Password: X` | `- Password: X` | `password = "X"` | `DB_PASSWORD=X` | `"password": "X"` |
|---|---|---|---|---|---|
| `River2025!` | 버림 | 버림 | 남김 | 버림 | 버림 |
| `Ocean@2025` | 버림 | 버림 | 남김 | 버림 | 버림 |
| `G7h$2mXkP@5b` | 남김 | 남김 | 남김 | 남김 | 남김 |
| `super$ecret` | 버림 | 버림 | 버림 | 버림 | 버림 |

API 키도 `api_dev_`, `write_dev_` 같은 접두어가 붙으면 절반(105/198)만 남고, 접두어 없는 무작위 키는 84%(200/239)가 남는다. Nosey Parker에서 잃은 22개도 `super$ecret`(8), `thisismypassword`, `whiteduke` 같은 값이다.

ML 모델은 CredData로 학습했고, CredData는 약한 비밀번호와 테스트 값을 F로 둔다. 지표 1은 9자 이상이고 흔한 목록에 없는 비밀번호를 정답으로 보므로([정답의 정의](../metric-1/README.md#정답의-정의)), 두 기준이 어긋나는 자리에서 ML이 정답을 버린다.

## 9. 정답·데이터 쪽 문제

탐지기가 아니라 정답이나 데이터 때문에 놓친 것으로 잡히거나 과잉 마스킹으로 잡힌 경우다. 고칠 대상이 다르므로 따로 센다([이전 문서 원인 7, 8](README_baseline-recall.md#7-정답-경계가-비밀값보다-넓음)과 같은 성격이다).

**Nemotron-PII**

- **값이 아닌 구절이 정답에 들어 있다.** 공백이 든 정답 39개가 모두 `Temporary Password`(20), `new password`(3), `username and password`(2) 같은 구절이다. 사회보장번호 꼴(`396-70-2501`) 3개와 생체 식별자 번호 2개도 PASSWORD로 들어 있다. 원본 라벨의 오류인데 변환 규칙에서 걸러지지 않았다. 모든 시스템이 놓친 것으로 잡혀 recall을 약 1%p 깎는다.
- **공개 예시 JWT는 정답이 아니지만 탐지기는 가린다.** jwt.io의 예시 JWT는 정의대로 정답에서 뺐는데(`known_example`), 탐지기는 이 값을 알아볼 방법이 없다. gitleaks 과잉 마스킹 121개 중 100개, CredSweeper(ML off) 636개 중 113개가 이 값이다. 이 데이터의 precision은 그만큼 낮게 나온다.

**Nosey Parker** (둘 다 놓친 58개 중 10개, CredSweeper만 놓친 16개 중 7개)

| 경우 | 정답 | 내용 |
|---|---|---|
| 정답 경계가 비밀값보다 넓음 | 5 | 연결 문자열 전체(`Server=…;User ID=…;Password=…;…`, 2), 이스케이프가 붙은 값(`\"goodspec\`, 1), Slack 웹훅의 공개 접두어 `https://hooks.slack.com/services`(2). 탐지기는 비밀번호나 경로만 가려 `partial`이 된다. 노출된 부분에 비밀값은 없다 |
| 비밀이 아닌 값 | 6 | placeholder(`SOME_PASSWORD`, `myPassword` 3), 변수 참조(`#{datastore['DBPASSWORD']}`), 비밀번호와 같은 값이 사용자명 자리(`User ID=…`)에 나온 위치 |
| 체크섬이 깨진 난독화 값 | 5 | GitHub(`ghp_`, `ghs_`), npm, Atlassian, age 키. Nosey Parker 작성자가 글자를 바꿔 무력화한 값이라 CredSweeper의 체크섬 검사(`ValueGitHubCheck` 등)에 걸린다. 필터를 끄면 5개 모두 찾고, 실제 토큰이면 통과한다 |
| 실제와 길이가 다른 값 | 1 | Telegram 봇 토큰. 콜론 뒤가 실제 형식(35자)보다 한 글자 짧다 |

**openhands-feedback.** recall은 상한값이다. 정답 후보를 CredSweeper와 gitleaks(와 정규식)가 냈으므로, 두 도구가 다 놓친 자격증명은 정답에 들어갈 수 없다. 이 데이터의 CredSweeper recall 1.000은 약점이 없다는 뜻이 아니다.

## 정리

- **놓치는 쪽의 공통 원인은 여전히 "키 이름 + 구분자 + 값" 가정이다.** 이전 문서는 셸 명령의 위치 인자에서 이 가정이 깨지는 것을 봤고, 새 데이터는 업무 문서에서 더 넓게 깨지는 것을 보여 준다. 문장(54%)뿐 아니라 마크다운 굵은 글씨, 표, XML처럼 키가 바로 앞에 있는 서식에서도 놓친다. 두 도구를 합쳐도 Nemotron recall은 0.311이라, 도구를 더해서는 메워지지 않는다.
- **형식이 정해진 토큰은 두 도구가 서로 보완한다.** Nosey Parker에서 합치면 0.835다. 남는 것은 어느 쪽에도 형식 규칙이 없는 서비스(Doppler의 개인 토큰 외 토큰, TrueNAS, Twitch 등)와 형식이 바뀐 토큰이다. 형식 규칙 목록은 서비스가 늘고 형식이 바뀔 때마다 따라가야 한다.
- **과잉 마스킹은 두 갈래다.** 코드 조각을 값으로 잡는 키워드 규칙(71%)은 ML 검증으로 대부분 걸러지지만, 값 모양만 보는 info 규칙(UUID 등)은 ML을 거치지 않는다. `severity=low`와 ML on을 함께 쓰면 SWE-Gym의 과잉 마스킹이 gitleaks 수준으로 내려가지만, UUID 모양 키와 기억하기 쉬운 비밀번호를 놓친다. 지금 도구에는 이 둘을 문맥으로 가르는 장치가 없다.
- **PromptGuard 데모에 대한 함의.**
  - 지금 데모는 `tool_output`에서 CredSweeper ML off와 같다. 실제 트래픽에서 1,000줄당 0.53~0.85번 코드 조각과 request id를 가리고, 그중 숫자·버전이 51개다. predictor가 후보를 거르는 단계에서 6, 7절의 과잉 마스킹을 줄여야 한다.
  - predictor로 CredSweeper ML을 그대로 쓰면 8절처럼 지표 1의 정답을 버린다. 판정 기준을 지표 1의 정의에 맞춰야 한다.
  - Nemotron 정답의 절반이 `prompt` 채널에 있어, 사용자가 붙여 넣은 글을 처리하지 않으면 이 데이터의 recall 상한이 0.51이다.
  - CredSweeper와 다른 점은 채널(Nemotron `prompt` 396개, openhands-feedback `tool_input` 2개)과 겹친 탐지 처리(Nosey Parker `partial` 5개: Databricks, New Relic `NRII-` 2, base64 PEM, Slack 앱 토큰의 끝이 노출됨. [이전 문서 원인 6](README_baseline-recall.md#6-겹친-탐지-중-짧은-쪽을-남김-promptguard))뿐이다.
  - 탐지 단계에서 후보를 넓히려면 문장 속 "키워드 … `is`/`:` 값", 마크다운·표·XML의 키-값, 쿠키 이름, 같은 세션에서 이미 비밀로 판정한 값의 재등장을 볼 수 있다. [이전 문서의 정리](README_baseline-recall.md#정리)와 같은 방향이다.
- **데이터 쪽 할 일.** Nemotron의 구절·번호 라벨 44개는 변환 규칙에서 빼는 것이 맞다. Nosey Parker는 정답 경계(연결 문자열 전체, Slack 접두어), placeholder(`SOME_PASSWORD`, `myPassword`), 사용자명 자리의 같은 값을 정답에서 빼거나 좁힐지 정해야 한다. 체크섬이 깨진 난독화 값은 이전 문서의 CredData 난독화 값과 같이 다룬다.
