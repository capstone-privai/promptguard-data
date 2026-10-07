# 기존 시스템의 recall이 낮은 이유

지표 1 데이터셋으로 기존 시스템(CredSweeper, gitleaks)과 PromptGuard 데모를 채점했을 때 recall이 낮게 나온 자리를 span 단위로 따라가 원인을 정리한 문서다. 놓친 정답 span마다 원문에서 채널, 값 앞 문맥, 값의 모양을 붙여 recall을 나눠 보고, 원인이 의심되면 해당 도구에 같은 값을 직접 넣어 확인했다.

- 대상 실행
  - 합성 데이터(`sessions`, `sessions_2`, `sessions_from_example`): `runs/all_20261008-010650`. 합성 AWS 키 ID 생성을 고친 뒤([8절](#8-형식에-맞지-않는-값)) 다시 만든 데이터다.
  - CredData, privesc-llm-data: `runs/all_20261007-221606`. 그 뒤로 채점기와 이 두 데이터는 바뀌지 않았다.
- 도구 버전: CredSweeper 1.18.5, gitleaks 8.30.1, PromptGuard `promptguard-demo-v0@915492b`(predictor=mock)
- 판정은 [채점 기준](README.md#채점-기준)을 따른다. `partial`(일부만 가림)도 실패로 센다.
- 시스템 구성: CredSweeper와 gitleaks는 네 채널을 모두 본다. PromptGuard는 `tool_output`만 처리하고, 탐지는 CredSweeper(ML off)이며 mock predictor는 후보를 모두 MASK한다.

## 요약

| 데이터셋 | 정답 | PromptGuard | CS ml=off | CS ml=on | gitleaks |
|---|---|---|---|---|---|
| 내장 코퍼스 (`sessions`) | 32 | 0.656 | 0.656 | 0.594 | 0.313 |
| 에이전트 세션 v2 (`sessions_2`) | 78 | 0.628 | 0.692 | 0.641 | 0.474 |
| 템플릿 예시 (`sessions_from_example`) | 10 | 0.900 | 0.900 | 0.800 | 0.800 |
| CredData | 15,596 | 0.973 | 0.977 | 0.971 | 0.433 |
| privesc-llm-data | 10,624 | **0.167** | **0.499** | **0.492** | **0.116** |

낮은 recall은 아래 여덟 가지 원인으로 거의 다 설명된다. 앞의 여섯은 시스템의 구조나 설계에서 오고, 뒤의 둘은 정답·데이터 쪽 문제라 고칠 대상이 다르다.

| # | 원인 | 영향받는 시스템 | 대표 근거 |
|---|---|---|---|
| 1 | **키 이름 없는 자리의 값** (위치 인자, 자연어) | 전부 | privesc에서 값 바로 앞이 `key=`/`key:` 꼴이면 CS recall 0.955~1.000, 아니면 0.004~0.020 |
| 2 | **처리하지 않는 채널** | PromptGuard | privesc 정답의 57%(6,020개)가 `instructions`/`tool_input`에 있다 |
| 3 | **약한·기본 비밀번호 필터** | CredSweeper, PromptGuard | `postgres`, `root`, `qwer1234`는 필터를 끄면 찾는다. ML을 켜면 더 버린다 |
| 4 | **규칙에 없는 키 이름** | CredSweeper, PromptGuard | `Cookie: session=`, `?code=`, `X-Amz-Signature=`, 웹훅 URL 경로, `비번` |
| 5 | **gitleaks 일반 규칙의 값 조건** | gitleaks | privesc의 `password` 자리에서도 엔트로피 3.5 이하인 값은 0/3,786 |
| 6 | **겹친 탐지 중 짧은 쪽을 남김** | PromptGuard | CredData에서 CS보다 70개 덜 맞힘 (`X-Amz-Credential` 57개) |
| 7 | **정답 경계가 비밀값보다 넓음** | 전부 (`partial`) | URI 전체, CredData의 줄 전체 PEM·JWK. 노출된 부분에 비밀값은 없다 |
| 8 | **형식에 맞지 않는 값** | gitleaks, CredSweeper | CredData 난독화로 형식이 깨진 AWS 키 ID·GUID, privesc의 잘린 개인키 |

ML 검증(CredSweeper `--ml on`)은 어느 데이터셋에서도 recall을 올리지 못했다. privesc와 CredData에서 ML이 새로 찾은 정답 span은 **0개**이고, 진짜 값을 버린 것만 privesc 73개, CredData 96개다. ML은 규칙이 만든 후보를 거르는 분류기라서, 규칙이 후보를 만들지 못한 값(원인 1, 4)은 보지 못한다. 효과는 precision에만 나타난다(privesc 0.489 → 0.916).

## 1. 키 이름 없는 자리의 값

CredSweeper의 비밀번호류 규칙과 gitleaks의 `generic-api-key`는 모두 **키 이름 + 구분자(`=`, `:`) + 값** 꼴에서 후보를 만든다. 값이 명령의 위치 인자나 문장 속에 있으면, 근처에 키워드가 있어도 후보가 생기지 않는다.

### privesc-llm-data

privesc는 셸 명령 궤적이라 비밀번호가 키 이름 없이 인자로 넘어가는 경우가 많다. 값 바로 앞(같은 줄 40자)이 `key=`, `key:`, `"key": "` 꼴인지로 나누면 결과가 갈린다.

| 채널 | 대입 문법 | 정답 | PromptGuard | CS off | CS on | gitleaks |
|---|---|---|---|---|---|---|
| instructions | 있음 | 2,200 | 0.000 | 1.000 | 0.995 | 0.276 |
| tool_input | 있음 | 1,329 | 0.000 | 0.986 | 0.968 | 0.178 |
| tool_output | 있음 | 1,799 | 0.955 | 0.955 | 0.934 | 0.198 |
| tool_input | 없음 | 2,491 | 0.000 | 0.004 | 0.004 | 0.000 |
| tool_output | 없음 | 2,805 | 0.020 | 0.020 | 0.020 | 0.012 |

앞 40자에 `password` 같은 키워드가 있는지로 나눠도 비슷하게 갈리지만(0.86~1.0 vs 0.01~0.08), 대입 문법이 더 정확한 기준이다. `The temporary deploy password is X`처럼 키워드가 있어도 구분자가 없으면 찾지 못한다(내장 코퍼스 `m1-08`).

CS ml=off가 놓친 비밀번호를 명령 유형으로 나누면 다음과 같다.

| 값이 놓인 자리 | 정답 | CS off recall | 놓친 수 |
|---|---|---|---|
| `"password": "…"`, `Password: '…'` (대입) | 4,978 | 0.995 | 22 |
| `echo '…' \| sudo -S`, `echo 'root:…'` | 4,128 | 0.000 | 4,128 |
| here-string, heredoc (`su <<< '…'`, `<< 'EOF'`) | 265 | 0.015 | 261 |
| `sshpass -p`, `mysql -p'…'`, `docker login -p` | 216 | 0.000 | 216 |
| `expect`의 `send`, `sendline(…)`, `os.write(fd, b'…')` | 167 | 0.000 | 167 |
| `printf '%s\n' '…'` | 134 | 0.000 | 134 |
| `test_credentials("root", "…")` | 95 | 0.000 | 95 |
| `grep -r "…"` (값 자체를 검색) | 59 | 0.000 | 57 |
| 그 밖 | 423 | 0.454 | 231 |

같은 세션 안에서도 이 차이가 그대로 보인다. `privesc-training-password_reuse-1684`의 값 `B06JTsH1Uqft`는 9곳에 나온다. `Password: '…'`와 `"password": "…"` 꼴인 3곳만 찾았고, `echo '…'`, `test_credentials(\"root\", \"…\")` 꼴인 6곳은 놓쳤다. 값의 모양은 모두 같다.

### 합성 데이터와 CredData

합성 데이터에서도 같은 원인이 반복된다. `-p'…'`, `sshpass -p`, `docker login -p`, `--requirepass` 뒤의 값(6개)과 자연어 속 비밀번호(`비번 X 이야`, `(qa-admin / X)` 등 7개)는 모든 시스템이 놓쳤다.

CredData의 진짜 누락(CS ml=off `missed` 129개)도 119개가 대입 문법 밖이다. JSON 배열의 두 번째 원소(`"tokens":["…","…"]`, 52개), 튜플(`login, password = 'a', 'b'`), 함수 인자(`GitCredential("alice", "…")`) 같은 자리다. CredData에서 이 원인이 크게 드러나지 않는 것은, 소스 코드와 설정 파일이라 비밀값이 거의 항상 키 이름과 짝지어 나오기 때문이다. CredData 정답의 73%(11,327 / 15,596)가 대입 문법 바로 뒤에 있다. 그리고 CredSweeper의 ML 모델은 CredData로 학습했으므로, CredData의 ml=on 수치는 학습 분포 안에서 잰 값으로 봐야 한다.

## 2. 처리하지 않는 채널 (PromptGuard)

PromptGuard는 `tool_output`만 처리하므로 나머지 채널의 정답은 항상 놓친다([채점 기준](README.md#단위)에 적힌 대로 의도된 동작이다).

| 데이터셋 | `tool_output` 밖의 정답 | `tool_output` 안 recall: PromptGuard | `tool_output` 안 recall: CS off |
|---|---|---|---|
| privesc | 6,020 / 10,624 (57%) | 0.386 | 0.386 |
| sessions_2 | 11 / 78 | 0.731 | 0.731 |

`tool_output` 안에서는 PromptGuard와 CS ml=off가 같다. predictor가 후보를 전부 MASK하므로 탐지기 성능이 곧 시스템 성능이다. privesc에서 PromptGuard가 0.167인 것은 채널 범위(원인 2)와 위치 인자(원인 1)가 겹친 결과다. 놓친 8,849개 중 6,020개가 채널 때문이고, 나머지 2,829개도 대부분 위치 인자다.

## 3. 약한·기본 비밀번호 필터

CredSweeper는 ML을 꺼도 규칙 뒤에 필터가 돈다(`use_filters=True`). 이 필터가 사전에 있는 값, 짧은 값, 반복 패턴을 지운다. 같은 줄을 필터를 켜고 끈 CredSweeper에 넣어 확인했다.

| 줄 | 필터 켬 | 필터 끔 |
|---|---|---|
| `POSTGRES_PASSWORD: postgres` | 못 찾음 | 찾음 |
| `MYSQL_ROOT_PASSWORD: root` | 못 찾음 | 찾음 |
| `DB_PASSWORD=qwer1234` | 못 찾음 | 찾음 |
| `const password = 'test1234';` | 못 찾음 | 찾음 |
| `os.environ.get("ADMIN_PASSWORD", "admin")` | 못 찾음 | 찾음 |
| `.pypirc`의 `password = pypi-AgEI…`(110자) | 못 찾음 | 찾음 |
| `POSTGRES_PASSWORD: Xk29fLq8Zt` | 찾음 | 찾음 |

합성 데이터에서 이 필터 때문에 놓친 것은 9개다(`postgres` 2, `root`, `admin`, `qwer1234`, `test1234`, `dummy_token_123`, `test-api-key`, pypi 토큰). ML을 켜면 `changeme`(2), `minioadmin`, `password123`, `guest`, `Mailer#2026`도 버린다. 합성 데이터에서 ml=off → ml=on으로 떨어진 7개 중 6개가 이런 값이고, 나머지 하나는 `${SERVICE_KEY:-…}`의 기본값이다.

지표 1은 [설정에 들어간 약한 비밀번호도 자격증명으로 본다](README.md#정답의-정의). CredSweeper의 필터는 "실제로 쓰일 법한 비밀인가"를 거르는 설계라 이 정의와 어긋난다.

## 4. 규칙에 없는 키 이름

키-값 꼴이어도 키 이름이 CredSweeper의 키워드 목록에 없으면 후보가 생기지 않는다. 필터를 꺼도 찾지 못한다.

- HTTP 쿠키: `Set-Cookie: session=…`, `Cookie: sessionid=…`
- OAuth·서명 쿼리: `?code=…`, `X-Amz-Signature=…`
- URL 경로 안의 토큰: `https://hooks.example.invalid/hooks/<token>`
- 한국어 키워드: `비번`, `비밀번호는`
- URL 인코딩된 연결 문자열: `connection_uri_encoded=postgresql%3A%2F%2F…`
- 문맥이 전혀 없는 값: Kubernetes Secret을 디코드해 값만 출력한 줄

## 5. gitleaks 일반 규칙의 값 조건

gitleaks에서 형식이 정해진 토큰(`ghp_`, `AKIA`, PEM 등)이 아닌 값은 `generic-api-key` 규칙 하나가 맡는다. 이 규칙은 키워드와 구분자 말고도 값에 조건을 건다. 값을 바꿔 가며 gitleaks에 넣어 확인한 조건은 다음과 같다.

| 조건 | 탈락 예 | 통과 예 |
|---|---|---|
| 글자가 `[A-Za-z0-9_.=-]`뿐 | `imSqk5V5BG4Ox#7!` | `imSqk5V5BG4Ox7` |
| 엔트로피가 3.5 **초과** | `62eb67c507d42a3a` (정확히 3.5) | `62eb67c597d4ba3f` (3.625) |
| 숫자가 하나 이상 | `XrYDCLmoEsze` | `XrYDCLmoEs2e` |
| stopword를 포함하지 않음 | `lo8t7V9WPrOC` (`proc` 포함) | `lo8t7V9WPxOC` |

엔트로피 조건이 가장 크게 작용한다. 12자 값의 엔트로피는 최대 log2(12) ≈ 3.585라서, **글자가 하나만 겹쳐도 3.5 아래로 떨어진다.** privesc 비밀번호의 84%가 12자다. 그래서 privesc에서 `"password": "…"` 꼴인 자리만 봐도 결과가 엔트로피로 갈린다.

| privesc, 대입 문법 자리 | 정답 | gitleaks recall |
|---|---|---|
| 엔트로피 ≤ 3.5 | 3,786 | 0.000 |
| 엔트로피 > 3.5 | 1,192 | 0.892 (놓친 129개 중 122개는 숫자가 없는 값) |

합성 데이터의 비밀번호는 끝에 `#7!`, `~`, `&` 같은 특수문자가 붙어 있어 첫 조건에서 탈락한다. 합성 데이터의 PASSWORD·SECRET·TOKEN 정답 중 특수문자가 있는 값은 gitleaks recall 0.103(39개), 없는 값은 0.552(67개)다. CredData에서도 엔트로피 3.5 이하인 정답 3,651개 중 gitleaks가 찾은 것은 11개다.

## 6. 겹친 탐지 중 짧은 쪽을 남김 (PromptGuard)

PromptGuard와 CS ml=off는 같은 CredSweeper를 쓰지만, CredData에서 PromptGuard가 70개를 덜 맞혔다. 같은 값에 CredSweeper 규칙 둘이 겹쳐 걸렸을 때 고르는 쪽이 다르기 때문이다.

- 평가기의 CredSweeper 어댑터(`select_non_overlapping`)는 **가장 긴** span을 남긴다.
- PromptGuard(`detector/rules.py`의 `_normalize`)는 PEM·URL Credentials 규칙을 먼저 두고, 나머지는 **가장 짧은** span을 남긴다.

`X-Amz-Credential=AKIA…%2F<날짜>%2F<리전>%2Fs3%2Faws4_request`에서 `Credential` 규칙은 값 전체를, AWS 키 규칙은 앞의 `AKIA…` 20자만 잡는다. PromptGuard는 짧은 쪽을 남기므로 나머지가 `partial`이 된다(57개). NTLM 토큰 5개도 같은 이유다. 여기서 노출된 부분은 날짜·리전이라 실제 위험은 작다. 하지만 같은 방식이 비밀값 중간에서 일어나면 진짜 노출이 된다.

## 7. 정답 경계가 비밀값보다 넓음

`partial`로 잡힌 것 중 상당수는 탐지 실패가 아니라 정답 span이 비밀값보다 넓게 잡힌 경우다. 안 덮인 글자를 직접 확인한 결과, 노출된 부분에 비밀값은 없었다.

| 경우 | 정답 span | 시스템이 가린 부분 | 건수 (CS off) |
|---|---|---|---|
| 연결 문자열 (합성) | `postgresql://service:pw@host:5432/app` 전체 | `pw`만 | 7 |
| CredData의 PEM·개인키 | 줄 전체(`$key = PublicKeyLoader::load('…');`), 여러 줄 문자열의 따옴표와 `+` | `-----BEGIN` ~ `-----END` | 138 |
| CredData의 JWK | 객체 전체(`kty`, `n`, `e` 등 공개 필드 포함) | 비밀 필드 값만 | 65 |

CredData의 CS ml=off `partial` 225개 중 203개가 위 두 경우이고, 이 때문에 CredData recall이 약 1.4%p 깎인다. CredData 쪽은 [README_CredData.md](README_CredData.md)의 변환 규칙("ValueStart가 없으면 LineStart..LineEnd")에서, 합성 쪽은 연결 문자열 전체를 SECRET 하나로 라벨링하는 방식에서 온다.

## 8. 형식에 맞지 않는 값

형식이 정해진 비밀값은 형식을 검사하는 탐지기에서만 잡히므로, 데이터의 값이 실제 형식과 다르면 recall이 실제보다 낮게 나온다.

**합성 AWS 키 ID (고침).** 실제 AWS 액세스 키 ID는 `AKIA` 뒤 16자가 `A-Z`와 `2-7`(base32)로만 이루어지고, gitleaks는 이 형식을 검사한다. 생성기가 뒤 16자를 `A-Z0-9`에서 뽑아 합성 `AKIA…` 정답 7개가 모두 형식에 맞지 않았다. [dataset_build.py](scripts/dataset_build.py)의 `AWS_ACCESS_ID`로 문자 집합을 고치고 데이터를 다시 만들었다. 값의 길이와 위치는 그대로라 정답 파일은 바뀌지 않았고, 채점 결과도 이 7개만 바뀌었다.

| 데이터셋 | gitleaks recall (고치기 전 → 후) | CredSweeper·PromptGuard |
|---|---|---|
| `sessions` | 0.281 → 0.313 (+1) | 변화 없음 |
| `sessions_2` | 0.410 → 0.474 (+5) | 변화 없음 |
| `sessions_from_example` | 0.700 → 0.800 (+1) | 변화 없음 |

고친 뒤 형식에 맞는 `AKIA…` 값은 gitleaks가 101/101(합성 7, CredData 94)을 찾는다.

**CredData의 난독화 값.** CredData는 원본 비밀값의 글자를 바꿔 난독화하는데, 이때 형식이 깨진 값이 남아 있다.

- 형식에 맞지 않는 `AKIA…` 7개(`AKIAS72BG0QG…`처럼 `0`, `1`, `8`, `9`가 섞인 값): gitleaks 0/7. 형식을 검사하지 않는 CredSweeper는 7개 모두 찾는다.
- 16진수가 아닌 글자가 들어간 GUID 19개(`P41RYE50-I6C6-…`): CredSweeper 0/19

**privesc의 잘린 개인키.** 출력이 중간에 잘려 `-----END` 줄이 없는 개인키 12개는 모든 시스템이 놓쳤다. privesc의 PRIVATE_KEY recall이 0.912에 머무는 이유다.

## 정리

- 기존 시스템의 recall 한계는 대부분 **키 이름과 짝지어진 값만 후보로 만드는 구조**에서 온다(원인 1, 4). 소스 코드 중심인 CredData에서는 이 한계가 거의 보이지 않고, 셸 명령과 자연어가 많은 에이전트 궤적에서 크게 드러난다. 후처리 ML은 후보를 거르기만 하므로 이 부분을 메우지 못한다. PromptGuard가 차별점을 보여줄 수 있는 자리가 여기다. 같은 세션에서 같은 값이 키가 있는 자리에서는 잡히고 키가 없는 자리에서는 놓치는 대조가 근거가 된다.
- PromptGuard 데모의 지금 수치는 CredSweeper ML-off와 사실상 같고, 차이는 채널 범위(원인 2)와 겹침 처리(원인 6)뿐이다. predictor는 탐지기가 만든 후보만 받으므로, 지금 구조에서는 predictor를 바꿔도 원인 1, 3, 4가 메워지지 않는다. 탐지 단계에 후보를 넓히는 장치가 필요하다. 예를 들어 같은 세션에서 이미 비밀로 판정한 값이 다시 나오는지 추적하거나, 셸 명령의 인자 위치를 보는 규칙을 둘 수 있다.
- 원인 7, 8은 데이터와 채점 쪽 문제다. 합성 AWS 키 ID는 고쳤다. 남은 것은 연결 문자열·CredData PEM의 정답 경계를 어디까지로 볼지 정하는 일과, `partial` 중 경계 문제만 따로 세는 지표를 두는 일이다.
