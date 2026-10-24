# 정답 레이블 기준

metric-detection의 모든 데이터셋(합성 3종, CredData, privesc-llm-data, Nemotron-PII, openhands-feedback, SWE-Gym, Nosey Parker)은 이 문서 하나의 기준으로 정답을 매긴다. 데이터셋별 README에는 이 기준을 그 소스에 어떻게 적용했는지만 쓰고, 기준을 따로 정하지 않는다. 규칙의 구현은 [scripts/label_rules.py](scripts/label_rules.py) 한 곳에 있고, 생성기와 변환기가 모두 이 모듈을 쓰며, [dataset_verify.py](scripts/dataset_verify.py)가 모든 정답이 이 규칙을 지키는지 검사한다.

## 원칙: 텍스트만 보고 판정한다

정답은 **그 텍스트를 읽는 사람이 자격증명 자리에 들어간 값이라고 판정할 수 있는 리터럴 값**이다. 텍스트 밖의 정보는 쓰지 않는다.

- 값이 실제로 동작하는지, 인증에 성공했는지는 보지 않는다. 틀린 비밀번호를 넣어 본 것도, 오타가 난 비밀번호도 자격증명 자리에 있으면 정답이다.
- 값의 강도는 보지 않는다. `admin`, `root`, `postgres`, `password123`, `12345678`처럼 짧거나 흔한 값도 정답이다.
- 테스트·개발용인지는 보지 않는다. `test_api_key`, `mock_token`, `x-pack-test-password`도 정답이다.
- 원본 데이터가 그 값을 어떻게 라벨했는지(CredData의 T/X/F, Nemotron의 라벨, privesc metadata에 심은 값인지)는 후보를 찾는 데만 쓰고, 판정은 이 문서의 규칙으로 다시 한다.

탐지기가 볼 수 없는 정보가 정답에 끼어들면 데이터셋마다 정답의 뜻이 달라진다. 이 원칙은 모든 데이터셋에 같은 규칙을 기계적으로 적용하기 위한 것이다.

## 정답인 것

다음 중 하나에 해당하는 값이다.

| 경우 | 예 |
|---|---|
| 자격증명 자리에 들어간 리터럴 | `DB_PASSWORD=admin`, `"api_key": "test_api_key"`, `-p hunter2`, `sshpass -p '…'`, `echo '…' \| sudo -S`, `--requirepass …`, `Password=…;`(연결 문자열) |
| 인증 헤더·쿠키의 값 | `Authorization: Bearer ⟦값⟧`, `Authorization: Basic ⟦값⟧`, `Cookie: session=⟦값⟧` |
| URL에 든 자격증명 | `postgresql://app:⟦값⟧@db:5432/app`, `https://x-access-token:⟦값⟧@github.com/…` |
| 형식만으로 자격증명인 값 | 서비스 접두어가 있는 토큰(`ghp_…`, `xoxb-…`, `sk-…`, `AKIA…`), 개인키 블록, 인증 자리의 JWT |
| 문장 속에서 자격증명이라고 밝힌 값 | "비번은 ⟦값⟧이야", "The password for the share is ⟦값⟧", "use the API key ⟦값⟧" |
| 자격증명 자체인 URL | Slack·Teams·Discord 웹훅처럼 URL을 아는 것만으로 쓸 수 있는 URL |

**자격증명 자리**는 키·옵션·문맥이 비밀번호, 비밀, 토큰, 키, 인증을 가리키는 자리다(`password`, `passwd`, `pwd`, `pass`, `secret`, `token`, `api_key`, `apikey`, `access_key`, `private_key`, `auth`, `credential`, `-p`, `--password` 등). 키 이름에 이런 말이 들어 있어도 값이 그 자격증명이 아니면 자격증명 자리가 아니다. 예: `"TITLE_CHANGE_PASSWORD": "Endre passord"`(화면 문구), `password_min_length = 12`(설정값), `max_tokens = 4096`.

## 정답이 아닌 것

자격증명 자리에 있어도 다음은 정답이 아니다. 왼쪽의 kind는 각 데이터셋의 labels 파일과 리뷰 파일에 그대로 쓰는 이름이다.

| kind | 내용 | 예 |
|---|---|---|
| `redaction` | 지우거나 가린 흔적 | `********`, `xxxx`, `XXXX`, `[REDACTED]`, `<redacted>`, `ghp_-XXX`, `sk-...9f2c`, `login_and_password_removed` |
| `template` | 채워 넣을 자리를 표시한 문법이나 안내문 | `<your-token>`, `<password>`, `{{ .Values.x }}`, `YOUR_API_KEY`, `your-token-here`, `<generate-with-openssl-rand-hex-32>`, `your-secret-key-change-this-in-production` |
| `reference` | 변수·환경변수·속성 참조 | `${TOKEN}`, `$DB_PASS`, `%PASS%`, `os.environ["KEY"]`, `self.api_key`, `{token}` |
| `code` | 값이 아닌 코드 표현식, 타입, 함수 호출 | `values[EnvAPIPassword]`, `password: string;`, `kwargs.get(`, `generate_password_hash(` |
| `doc_example` | 공개 문서·표준·도구 설명서에 실린 예시 값, 또는 글에서 예시라고 밝힌 값 | `AKIAIOSFODNN7EXAMPLE`, jwt.io 예시 JWT, RFC 7617의 `open sesame`, `EXAMPLE`이 든 값, 정책 문서의 "such as `Ocean@2025`", man 페이지의 `--password pass` |
| `descriptor` | 값이 아니라 그 값을 가리키는 말 | `new password`, `your password`, `temporary password` |
| `hash` | 비밀번호 해시와 같은 단방향 해시 | `$6$…`, `$2a$04$…`, `$y$…`, Kerberos 해시 |
| `identifier` | 사용자명, 이메일, 계정·리소스·클라이언트 id, request id, 커밋 해시, 이름 | `x-github-request-id`, `"_postman_id": "…"`, `"uid": "…"`, OAuth client id, AWS 계정 id, ARN, `/etc/passwd`의 사용자명 |
| `non_credential` | 자격증명이 아닌 비밀·개인정보 | PIN, CVV, 카드 번호, 계좌 번호, CSRF 토큰, 추적·환경설정 쿠키 |
| `empty` | 빈 값 | `DB_PASSWORD=` |

- UUID는 모양이 아니라 자리로 판정한다. `api_key = "1fd2…"`의 UUID는 정답이고, `"id": "…"`, `RequestId`, `ChangeToken`(AWS의 중복 요청 방지 값)의 UUID는 `identifier`다.
- 해시 모양의 hex도 자리로 판정한다. `SECRET_KEY = "9f2c…"`(64자 hex)는 정답이고, 비밀번호를 해시한 값은 `hash`다.
- 무작위 모양이 아닌 값도 정답에서 빼지 않는다. `aaaaaaaa`, `12345678`, `a1b2c3d4`, `changeme`가 자격증명 자리에 있으면 정답이다. 빼는 것은 위 표의 경우뿐이다.

## 같은 값의 다른 등장 위치 (퍼뜨림 기준)

위 규칙으로 정답이 된 값이 같은 세션의 자격증명 자리 밖에 또 나올 때, 그곳도 정답으로 칠지는 **값이 고유한지 흔한지**로 정한다. 이 기준은 값을 정답으로 칠지가 아니라 다른 등장으로 퍼뜨릴지만 정한다. 자격증명 자리에 있는 값은 흔하든 짧든 항상 정답이다.

| 값 | 자격증명 자리 | 자격증명 자리 밖의 다른 등장 |
|---|---|---|
| 고유한 값 (`toor`, `qwer1234`, `P@ssw0rd`, 무작위 값) | 정답 | 정답. 단 `identifier` 역할로 나온 곳은 아님 |
| 흔한 값 (`root`, `admin`, `password`, `guest`, `debian`, `123456`) | 정답 | 정답 아님 |

비밀번호가 `root`인 세션이라면 `{"password": "⟦root⟧"}`, `echo '⟦root⟧' | su -`, `Trying root:⟦root⟧`는 정답이고, `"user": "root"`, `/root/.ssh`, `Running as root`는 정답이 아니다. 흔한 문자열은 문맥이 자격증명이라고 가리키는 곳에서만 비밀이다. 다른 등장까지 정답으로 두면 모델이 문맥이 아니라 세션에서 본 문자열을 외우게 된다.

**흔한 값**은 비밀이 아닌 뜻으로도 흔히 쓰이는 문자열이다. 대소문자를 구분하지 않고, 다음 중 하나에 걸리면 흔한 값이다.

1. 영어 단어 목록에 있다. 버전을 고정한 SCOWL(en_US, 크기 60)을 저장소에 둔다.
2. 배경 말뭉치에 흔히 나온다. 정답이 거의 없는 실제 에이전트 트래픽(SWE-Gym, openhands-feedback, 두 데이터의 정답 값은 뺀다)에서 5회 이상, 3개 이상 세션에 나온 토큰이다. `debian`, `postgres` 같은 기술 용어를 잡는다.
3. 같은 세션에서 `identifier` 자리(사용자명, 호스트명, 경로 성분)에도 나온다. privesc `weak_password` 시나리오처럼 사용자명을 비밀번호로 쓴 경우를 잡는다.
4. 숫자로만 되어 있다.

틀릴 때 덜 해로운 쪽을 고른 기준이다. 흔한 값을 고유하다고 잘못 보면 일반 단어까지 정답이 되어 학습에 해롭고, 고유한 값을 흔하다고 잘못 보면 다른 등장 몇 곳이 빠질 뿐이다. 그래서 넷 중 하나에만 걸려도 흔한 값으로 본다.

다른 문자열 안의 일부로 나온 것(앞뒤가 영숫자나 `_`로 이어짐)은 같은 값의 등장으로 보지 않는다.

## 경계

span은 **비밀값 문자열 그 자체**다. 탐지기가 값만 가리면 `exact`가 되도록 잡는다.

| 형식 | span | 예 (⟦⟧가 span) |
|---|---|---|
| 따옴표로 감싼 값 | 따옴표 안쪽 | `"password": "⟦hunter2⟧"` |
| 인증 스킴 | 스킴 이름과 공백은 뺀다 | `Bearer ⟦eyJ…⟧`, `Basic ⟦dXNlcjpwdw==⟧`, `token ⟦ghp_…⟧` |
| Basic 인증 문자열 | base64 전체. 안의 `user:pw`를 나누지 않는다 | `Basic ⟦dXNlcjpwdw==⟧` |
| URL 속 자격증명 | 비밀번호(또는 토큰) 부분만. 사용자명, 호스트, 경로는 뺀다 | `postgresql://app:⟦pw⟧@db:5432/app` |
| `사용자명:비밀번호` 쌍 | 비밀번호만 | `admin:⟦pw⟧` |
| 쿠키 | 값만. 이름과 속성은 뺀다 | `session=⟦값⟧; Path=/` |
| 연결 문자열 | 값만 | `Password=⟦값⟧;` |
| 개인키 블록 | BEGIN 줄 첫 `-`부터 END 줄 마지막 `-`까지. 뒤의 따옴표, 쉼표, 세미콜론은 뺀다 | `"⟦-----BEGIN … -----END PRIVATE KEY-----⟧",` |
| 잘린 개인키 블록 | BEGIN 줄부터 마지막 본문 줄 끝까지. BEGIN 줄만 있고 본문이 없으면 정답이 아니다 | |
| 문자열 안에 이스케이프된 값 | 텍스트에 보이는 그대로 (`\n` 두 글자 포함) | `"key": "⟦-----BEGIN…\n…-----⟧"` |
| 터미널 폭 때문에 줄이 끊긴 값 | 줄바꿈을 포함한 span 하나 | |
| 자격증명 자체인 URL | URL 전체 | `⟦https://hooks.slack.com/services/T…/B…/…⟧` |

- 앞뒤 공백은 항상 뺀다.
- 값 바로 뒤의 문장 부호(`.`, `,`, `;`, `)`, 마크다운 `**`, 백틱)는 값에 포함하지 않는다. 값 자체가 그 문자로 끝나는 경우(비밀번호 `abc!.`)는 자격증명 자리의 구분자(따옴표, 줄 끝, 공백)로 경계를 정한다.
- 여러 값이 맞닿거나 겹치면 하나로 합치고, type은 더 긴 쪽을 따른다. 개인키와 겹치면 PRIVATE_KEY가 우선한다.

## 유형

유형은 채점에 쓰지 않고 유형별 recall에만 쓴다. 모든 데이터셋이 같은 규칙으로 정한다.

| type | 기준 | 예 |
|---|---|---|
| `PRIVATE_KEY` | 개인키 재료 | PEM·OpenSSH·PuTTY 개인키, JWK의 개인 성분, PASERK·NKEY seed |
| `PASSWORD` | 사람이나 시스템이 로그인에 쓰는 비밀번호, 패스프레이즈 | `DB_PASSWORD`, URL 속 비밀번호, `sudo -S` 입력, Basic 인증이 아닌 `user:pw`의 pw |
| `TOKEN` | 그 자체로 제시하면 인증되는 토큰 | JWT, OAuth 액세스·리프레시 토큰, PAT(`ghp_`, `glpat-`), Slack `xox?-`, 세션 쿠키, Basic 인증 문자열 |
| `ACCESS_KEY` | 키 쌍의 id 부분이나 공개용 키로, 그래도 자격증명으로 다루는 값 | AWS `AKIA…`/`ASIA…`, Stripe `pk_…`, Mapbox `pk.…` |
| `SECRET` | 위에 들지 않는 나머지 비밀 | API 키(`sk-…`, `AIza…`), 클라이언트 시크릿, 서명·암호화 키, AWS 시크릿 키, 웹훅 URL |

키 이름이 유형을 정하지 않는 경우(`credential: …`, 자연어)는 값의 형식으로 정하고, 형식으로도 알 수 없으면 `SECRET`이다.

## 채널

`tool_input`의 정답도 이 기준으로 똑같이 만든다. 채점에서만 뺀다([README.md](README.md#단위)).

## 검증

`dataset_verify.py`는 모든 데이터셋의 정답에 대해 다음을 검사하고, 하나라도 어기면 실패한다. 지금 구현된 것은 3번(privesc처럼 우리가 정답을 만든 데이터의 누락 검사)이고, 1, 2, 4번은 아직 검사기에 넣지 않았다. `label_rules.exclusion_kind`는 CredData 변환에서 쓴다.

1. 정답 값이 위 "정답이 아닌 것"의 규칙(`label_rules.exclusion_kind`)에 걸리지 않는다.
2. span 경계가 정규화되어 있다: 앞뒤 공백, 감싼 따옴표, 인증 스킴, 뒤따르는 문장 부호가 없다(`label_rules.normalize_span`을 다시 적용해도 그대로다).
3. 고유한 정답 값이 그 세션의 다른 곳에 나오면 그곳도 정답이거나 `identifier` 역할로 기록되어 있다. 흔한 정답 값은 자격증명 자리에만 있다.
4. type이 위 유형 규칙과 맞는다.

규칙으로 판정할 수 없어 사람이 정한 값(리뷰 파일의 `reviewed_by: manual`)도 1, 2, 4를 지켜야 한다.
