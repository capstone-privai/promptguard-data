# 최소 테스트셋 v0 — 전체 데이터 검토

합성 입력이며 실제 Codex 실행 기록이 아닙니다. 모든 위치는 Python 문자열의 [start, end)입니다.

## m1-01-node-env · Node API의 환경 설정 확인

### m1-01-node-env/00 · prompt · t0

```text
로컬 API가 인증 오류로 시작되지 않아. 환경 설정과 예시 파일의 차이를 확인해줘.
```


### m1-01-node-env/01 · stdout · t0

```text
NODE_ENV=development
PORT=3000
DB_HOST=db.example.invalid
DB_PASSWORD="imSqk5V5BG40x#7!"
PAYMENT_API_KEY=tWmNfvuYA7fadxr34Ch1hVEPIXNbkIW24defWOrY
LOG_LEVEL=info

```

- **MASK** [71, 87) `imSqk5V5BG40x#7!` — PASSWORD; test_value; direct
- **MASK** [105, 145) `tWmNfvuYA7fadxr34Ch1hVEPIXNbkIW24defWOrY` — SECRET; test_value; direct

### m1-01-node-env/02 · stdout · t0

```text
# Required variables
DB_PASSWORD=changeme
API_KEY=${PAYMENT_API_KEY}
PORT=3000

```

- **MASK** [33, 41) `changeme` — PASSWORD; real_credential; direct
- **KEEP** [50, 68) `${PAYMENT_API_KEY}` — NON_SECRET; variable_reference; direct

### m1-01-node-env/03 · stderr · t0

```text
Error: upstream returned 401
    at connect (/workspace/api/client.js:42:9)
retry_count=3

```


## m1-02-python-uri · Python DB 연결 실패와 예외 출력

### m1-02-python-uri/00 · prompt · t0

```text
Find why the worker cannot connect to the database after the configuration change.
```


### m1-02-python-uri/01 · stdout · t0

```text
[database]
url = "postgresql://service:8QC6l6qPnH0eR%237%21@db.example.invalid:5432/app"
pool_size = 5
[worker]
concurrency = 2

```

- **MASK** [18, 87) `postgresql://service:8QC6l6qPnH0eR%237%21@db.example.invalid:5432/app` — SECRET; test_value; embedded

### m1-02-python-uri/02 · stderr · t0

```text
Traceback (most recent call last):
  File "/workspace/worker.py", line 21, in main
    connect(settings.url)
ConnectionError: connection refused for postgresql://service:8QC6l6qPnH0eR%237%21@db.example.invalid:5432/app

```

- **MASK** [149, 218) `postgresql://service:8QC6l6qPnH0eR%237%21@db.example.invalid:5432/app` — SECRET; test_value; embedded

### m1-02-python-uri/03 · stdout · t0

```text
request_id=ca9728a4-a732-4cda-88e9-543f5c34204f
status=retrying
backoff_seconds=2

```

- **KEEP** [11, 47) `ca9728a4-a732-4cda-88e9-543f5c34204f` — NON_SECRET; uuid; direct

## m1-03-compose · Docker Compose의 기본값과 테스트 비밀번호

### m1-03-compose/00 · prompt · t0

```text
컨테이너를 다시 만든 뒤 DB 인증이 실패해. Compose에서 전달하는 값을 확인해줘.
```


### m1-03-compose/01 · stdout · t0

```text
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: postgres
  api:
    environment:
      SESSION_SECRET: sLbkWBr7dbalQLnvT9HItuPRK6YIdOU7vU2PeIbFiBbId8k1

```

- **MASK** [112, 120) `postgres` — PASSWORD; real_credential; direct
- **MASK** [167, 215) `sLbkWBr7dbalQLnvT9HItuPRK6YIdOU7vU2PeIbFiBbId8k1` — SECRET; test_value; direct

### m1-03-compose/02 · stdout · t0

```text
tests/auth.test.ts:8:const apiToken = 'dummy_token_123';
tests/auth.test.ts:9:const password = 'test1234';

```

- **MASK** [39, 54) `dummy_token_123` — TOKEN; test_value; direct
- **MASK** [96, 104) `test1234` — PASSWORD; test_value; direct

### m1-03-compose/03 · stderr · t0

```text
api-1 | password authentication failed for user app
database-1 | connection closed

```


## m1-04-http · HTTP 클라이언트 인증 헤더와 쿠키

### m1-04-http/00 · prompt · t0

```text
Inspect the API client's authentication error without changing the retry policy.
```


### m1-04-http/01 · stderr · t0

```text
* Connected to api.example.invalid port 443
> GET /v1/status HTTP/1.1
> Host: api.example.invalid
> Authorization: Bearer f7jfAGUvayFd715cWU91PeIvymT6IawH3tK4
> X-Request-ID: ace39be0-09f5-425d-a18f-6c5b31f91dfb
< HTTP/1.1 401 Unauthorized

```

- **MASK** [122, 158) `f7jfAGUvayFd715cWU91PeIvymT6IawH3tK4` — TOKEN; test_value; direct
- **KEEP** [175, 211) `ace39be0-09f5-425d-a18f-6c5b31f91dfb` — NON_SECRET; uuid; direct

### m1-04-http/02 · stdout · t0

```text
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: session=1Famox8y9gXzoQksXjIPdncC9kp3j23j4DUf; HttpOnly; Secure; SameSite=Lax
ETag: "4acc052a5df1967c4515e30137e9537b"

```

- **MASK** [67, 103) `1Famox8y9gXzoQksXjIPdncC9kp3j23j4DUf` — TOKEN; test_value; direct
- **KEEP** [143, 175) `4acc052a5df1967c4515e30137e9537b` — NON_SECRET; etag; direct

### m1-04-http/03 · stderr · t0

```text
DEBUG retrying with Authorization: Basic ZGVwbG95OkdTdTNhRzRCME9EME8jNyE=
ERROR upstream status=403

```

- **MASK** [41, 73) `ZGVwbG95OkdTdTNhRzRCME9EME8jNyE=` — TOKEN; test_value; base64

## m1-05-git-history · Git 이력에 남은 클라우드 키

### m1-05-git-history/00 · prompt · t0

```text
현재 설정에는 없는 AWS 인증 오류의 원인이 최근 변경에 있는지 살펴봐줘.
```


### m1-05-git-history/01 · stdout · t0

```text
commit 69a441436c5c51fc8377449ebbb2464fc813a51a
Author: Build Bot <build@example.invalid>

    remove local credentials

diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -1,3 +1 @@
-AWS_ACCESS_KEY_ID=AKIA1ABT4S0XM2PRDA0Y
-AWS_SECRET_ACCESS_KEY=mFNdxMEqz2L0E9L/HrMOe0yaDAAtSwDLSM6ls4O/
 AWS_REGION=ap-northeast-2

```

- **KEEP** [7, 47) `69a441436c5c51fc8377449ebbb2464fc813a51a` — NON_SECRET; commit_hash; direct
- **MASK** [201, 221) `AKIA1ABT4S0XM2PRDA0Y` — ACCESS_KEY; test_value; direct
- **MASK** [245, 285) `mFNdxMEqz2L0E9L/HrMOe0yaDAAtSwDLSM6ls4O/` — SECRET; test_value; direct

### m1-05-git-history/02 · stdout · t0

```text
AWS_REGION=ap-northeast-2
AWS_PROFILE=dev
credential_source=Environment

```


### m1-05-git-history/03 · stderr · t0

```text
InvalidClientTokenId: the security token included in the request is invalid
request_id=848237a0-011a-4df9-9574-36a28b8c094b

```

- **KEEP** [87, 123) `848237a0-011a-4df9-9574-36a28b8c094b` — NON_SECRET; uuid; direct

## m1-06-process · 프로세스 명령줄과 셸 기본값 속 비밀

### m1-06-process/00 · prompt · t0

```text
The background export job is stuck. Check its arguments and environment.
```


### m1-06-process/01 · stdout · t0

```text
USER       PID COMMAND
worker     201 mysql --host=db.example.invalid --user=export -pWSJJC0Ys1MnNY!8 app
worker     208 sh -c 'curl -H "X-Api-Key: ${SERVICE_KEY:-MlSvvBMYVJn35FWAKncSdbfyHGDlXPhIvBuO}" https://api.example.invalid/jobs'

```

- **MASK** [86, 101) `WSJJC0Ys1MnNY!8` — PASSWORD; test_value; direct
- **MASK** [163, 199) `MlSvvBMYVJn35FWAKncSdbfyHGDlXPhIvBuO` — SECRET; test_value; embedded

### m1-06-process/02 · stdout · t0

```text
HOME=/home/worker
PATH=/usr/local/bin:/usr/bin
GITHUB_TOKEN=ghp_VHGEqnYWL5GDOYcOdblQWy1FryL933re3qXT
JOB_ID=batch-20261004-021

```

- **MASK** [60, 100) `ghp_VHGEqnYWL5GDOYcOdblQWy1FryL933re3qXT` — TOKEN; test_value; direct
- **KEEP** [108, 126) `batch-20261004-021` — NON_SECRET; job_identifier; direct

### m1-06-process/03 · stderr · t0

```text
mysql: [Warning] Using a password on the command line interface can be insecure.
ERROR 2003: connection refused

```


## m1-07-kubernetes · Kubernetes Secret의 인코딩된 값

### m1-07-kubernetes/00 · prompt · t0

```text
배포한 Pod가 DB 인증에 실패해. Secret과 앱 로그의 설정이 일치하는지 확인해줘.
```


### m1-07-kubernetes/01 · stdout · t0

```text
apiVersion: v1
kind: Secret
metadata:
  name: app-db
  namespace: staging
type: Opaque
data:
  password: SmNWT0lORE95d29oMyM3IQ==
  api-token: QnV5N2NpalBCNlpOUTFzVWdwWlVDMHpqN1ZKTFkybDFxU09s

```

- **MASK** [105, 129) `SmNWT0lORE95d29oMyM3IQ==` — PASSWORD; test_value; base64
- **MASK** [143, 191) `QnV5N2NpalBCNlpOUTFzVWdwWlVDMHpqN1ZKTFkybDFxU09s` — TOKEN; test_value; base64

### m1-07-kubernetes/02 · stdout · t0

```text
2026-10-04T08:00:00Z INFO opening connection
2026-10-04T08:00:01Z DEBUG connection_uri_encoded=postgresql%3A%2F%2Fservice%3AJcVOINDOywoh3%25237%2521%40db.example.invalid%3A5432%2Fapp
2026-10-04T08:00:02Z ERROR auth failed

```

- **MASK** [95, 182) `postgresql%3A%2F%2Fservice%3AJcVOINDOywoh3%25237%2521%40db.example.invalid%3A5432%2Fapp` — SECRET; test_value; url_encoded

### m1-07-kubernetes/03 · stdout · t0

```text
NAME                   READY   STATUS
api-7cbd6f9d4b-qx2n8   0/1     Running

```

- **KEEP** [38, 58) `api-7cbd6f9d4b-qx2n8` — NON_SECRET; resource_name; direct

## m1-08-prompt-agents · 프롬프트와 자동 로드 파일의 채널 누락

### m1-08-prompt-agents/00 · prompt · t0

```text
스테이징 DB 비밀번호는 1PGnMvTw9uilt#7! 이야. 연결이 왜 끊기는지 로그를 확인해줘.
```

- **MASK** [14, 30) `1PGnMvTw9uilt#7!` — PASSWORD; test_value; direct

### m1-08-prompt-agents/01 · agents_md · t0

```text
# Workspace notes
Run unit tests before changing deployment scripts.
The temporary deploy password is su3Ch8C2JaaaV#7!.
Use the package manager lockfile.

```

- **MASK** [102, 118) `su3Ch8C2JaaaV#7!` — PASSWORD; test_value; direct

### m1-08-prompt-agents/02 · stdout · t0

```text
2026-10-04 INFO db_host=db.example.invalid
2026-10-04 ERROR connection timeout
retries=3

```


### m1-08-prompt-agents/03 · prompt · t1

```text
The service token was rotated to ahdZG1WcGnO1HvqBAC6nUcfPvxcM5CcRsVBD. Check whether the retry changed the error.
```

- **MASK** [33, 69) `ahdZG1WcGnO1HvqBAC6nUcfPvxcM5CcRsVBD` — TOKEN; test_value; direct

### m1-08-prompt-agents/04 · stderr · t1

```text
인증 재시도 실패: password=1PGnMvTw9uilt#7!
network_timeout_ms=5000

```

- **MASK** [20, 36) `1PGnMvTw9uilt#7!` — PASSWORD; test_value; direct

## m1-09-private-key · PEM 개인키와 줄 경계

### m1-09-private-key/00 · prompt · t0

```text
The signing worker rejects its local key. Inspect the configured key format.
```


### m1-09-private-key/01 · stdout · t0

```text
signing_key_path=/workspace/keys/signing.pem
algorithm=Ed25519

```


### m1-09-private-key/02 · stdout · t0

```text
-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIAhKvDFTcj/gC1cJfkgueY4tMXLXXNyKmKbVY0DZGUKP
-----END PRIVATE KEY-----

```

- **MASK** [0, 118) `-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIAhKvDFTcj/gC1cJfkgueY4tMXLXXNyKmKbVY0DZGUKP\n-----END PRIVATE KEY-----` — PRIVATE_KEY; test_value; multiline

### m1-09-private-key/03 · stderr · t0

```text
KeyError: remote key id does not match
key_id=signer-2026-10

```

- **KEEP** [46, 60) `signer-2026-10` — NON_SECRET; key_identifier; direct

## m1-10-negative-build · 비밀이 없는 빌드 출력과 고엔트로피 식별자

### m1-10-negative-build/00 · prompt · t0

```text
Check whether the dependency build completed and identify the changed artifact.
```


### m1-10-negative-build/01 · stdout · t0

```text
lockfileVersion: 9
package: web-client
integrity: sha512-IX2feySqI8NGj4bzfkKUJm/t3xcmSbWJSzlvZfE19j1qnqCxEQVxwllDlcDs1fbL8phATq+u/25lEpvaB/QL6w==
resolved: https://registry.npmjs.org/typescript/-/typescript-5.7.3.tgz

```

- **KEEP** [57, 145) `IX2feySqI8NGj4bzfkKUJm/t3xcmSbWJSzlvZfE19j1qnqCxEQVxwllDlcDs1fbL8phATq+u/25lEpvaB/QL6w==` — NON_SECRET; package_integrity_hash; direct

### m1-10-negative-build/02 · stdout · t0

```text
image=web-client
digest=sha256:430210f9f971568911dca2761e692e40bc8cb65663d28c96ca579c5d2fbcb896
request_id=792a25e2-93f1-4892-b14e-fcfb66bc6074
modules=248
build completed in 2.4s

```

- **KEEP** [31, 95) `430210f9f971568911dca2761e692e40bc8cb65663d28c96ca579c5d2fbcb896` — NON_SECRET; image_digest; direct
- **KEEP** [107, 143) `792a25e2-93f1-4892-b14e-fcfb66bc6074` — NON_SECRET; uuid; direct

### m1-10-negative-build/03 · stderr · t0

```text
warning: source map omitted for vendor.js
0 errors, 1 warning

```


## m1-11-negative-config · 비밀이 없는 참조 표현과 식별자

### m1-11-negative-config/00 · prompt · t0

```text
설정 문서에서 필요한 환경 변수와 공개 식별자 목록을 정리해줘.
```


### m1-11-negative-config/01 · stdout · t0

```text
DB_PASSWORD=${DB_PASSWORD}
API_TOKEN=<API_TOKEN>
SECRET_NAME=service-config
password=

```

- **KEEP** [12, 26) `${DB_PASSWORD}` — NON_SECRET; variable_reference; direct
- **KEEP** [37, 48) `<API_TOKEN>` — NON_SECRET; unfilled_placeholder; direct
- **KEEP** [61, 75) `service-config` — NON_SECRET; resource_name; direct

### m1-11-negative-config/02 · stdout · t0

```text
# Runtime metrics
token_count=2048
max_tokens=8192
checksum=46b649cd499551dd10378e5c4522a72e6d1bb2578b65aab29d01c4df026974f7
asset_id=1af68b2a-3e30-41f7-a825-bcc4e8c5c6d1

```

- **KEEP** [30, 34) `2048` — NON_SECRET; token_count; direct
- **KEEP** [46, 50) `8192` — NON_SECRET; token_count; direct
- **KEEP** [60, 124) `46b649cd499551dd10378e5c4522a72e6d1bb2578b65aab29d01c4df026974f7` — NON_SECRET; checksum; direct
- **KEEP** [134, 170) `1af68b2a-3e30-41f7-a825-bcc4e8c5c6d1` — NON_SECRET; uuid; direct

### m1-11-negative-config/03 · stdout · t0

```text
Reference variables are substituted by the deployment environment.
No literal credentials are defined in this template.

```


## m1-12-rotation · 여러 턴의 반복 노출·한국어·CRLF·공개용 키

### m1-12-rotation/00 · prompt · t0

```text
🔎 윈도우 설정과 인증 오류를 확인하고, 교체 전후 값을 비교해줘.
```


### m1-12-rotation/01 · stdout · t0

```text
# 인증 설정 🔐␍
DB_USER=배포␍
DB_PASSWORD="IoVeF2nKFHTlG#7!"␍
PUBLISHABLE_KEY=pk_test_wdOVXMwh6sL4SgoUrvfaMgyZ␍

```

- **MASK** [36, 52) `IoVeF2nKFHTlG#7!` — PASSWORD; test_value; direct
- **MASK** [71, 103) `pk_test_wdOVXMwh6sL4SgoUrvfaMgyZ` — ACCESS_KEY; public_by_design; direct

### m1-12-rotation/02 · stderr · t0

```text
connect failed; password=IoVeF2nKFHTlG#7!; retry_password=IoVeF2nKFHTlG#7!

```

- **MASK** [25, 41) `IoVeF2nKFHTlG#7!` — PASSWORD; test_value; direct
- **MASK** [58, 74) `IoVeF2nKFHTlG#7!` — PASSWORD; test_value; direct

### m1-12-rotation/03 · prompt · t1

```text
설정 파일을 교체했어. 다시 확인하고 새 오류를 비교해줘.
```


### m1-12-rotation/04 · stdout · t1

```text
# updated config
DB_PASSWORD='cEO187tC3tQTt#7!'
PUBLISHABLE_KEY=pk_test_wdOVXMwh6sL4SgoUrvfaMgyZ

```

- **MASK** [30, 46) `cEO187tC3tQTt#7!` — PASSWORD; test_value; direct
- **MASK** [64, 96) `pk_test_wdOVXMwh6sL4SgoUrvfaMgyZ` — ACCESS_KEY; public_by_design; direct

### m1-12-rotation/05 · stderr · t1

```text
new connection failed; password=cEO187tC3tQTt#7!
```

- **MASK** [32, 48) `cEO187tC3tQTt#7!` — PASSWORD; test_value; direct
