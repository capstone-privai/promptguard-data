"""Service / token-type rows for the v3 dataset. populate(B) fills B.ROWS using B.pfx and B.add.

Formats (prefixes, lengths, regexes) are taken from the scanner catalogs and official SDK docs gathered during
discovery; the specific values are deterministic fakes from v3_engine.
"""


def populate(B):
    E = B.E
    pfx = B.pfx
    add = B.add
    HEX, ALNUM, B64, B64URL, BASE32 = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32

    # ================= 01 Generic high-frequency (v2 SRC-001..016 unbundled) =================
    g = "01"
    add(g, "GG_Generic_High_Entropy_Assignment",
        "Yelp/detect-secrets (keyword.py) & gitleaks generic-api-key & GitGuardian generic detectors",
        "변수명이 secret/api_key/token 등이고 32~64자 고엔트로피 문자열이 대입된 범용 비밀. 서비스 접두사가 없어 정적 스캐너가 자주 놓친다.",
        "같은 파일 내 API 엔드포인트 URL", "secret, api_key, auth_token, access_key",
        r"(?i)(secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*['\"]([A-Za-z0-9+/=_-]{32,64})['\"]",
        E.tok("", 40, HEX, tag="gg_entropy"), "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e", "High",
        ctx="py", var="INTERNAL_BILLING_SECRET",
        guide="엔트로피와 길이가 같아도(40자 hex) 변수명이 SECRET인지 CHUNK_HASH/빌드 다이제스트인지로 갈린다. Hard Negative는 "
              "webpack 청크 해시처럼 비밀이 아닌 동일 길이 hex이므로, 주변 변수명·주석·용도를 함께 봐야 한다.")
    add(g, "GG_Generic_Password_Assignment",
        "Samsung/CredSweeper (rules/config.yaml: Password) & Yelp/detect-secrets",
        "password/passwd/pwd 변수에 평문 비밀번호가 대입된 가장 흔한 형태.",
        "같은 파일의 DB host/user", "password, passwd, pwd, db_password",
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{6,})['\"]",
        E.password("gg_pw", "random"), "${DB_PASSWORD}", "High", ctx="py", var="db_password",
        guide="평문 비밀번호와 `${DB_PASSWORD}` 같은 환경변수 참조를 구분한다. 참조 구문(`${...}`, `os.getenv(...)`)은 값이 아니므로 "
              "마스킹하지 않는다.")
    add(g, "GG_Username_Password_Pair",
        "Samsung/CredSweeper & SecretBench (paired credentials)",
        "아이디와 비밀번호가 인접한 두 줄/한 줄에 함께 나오는 쌍. 비밀번호 쪽만 비밀값이다.",
        "로그인 대상 서비스/호스트", "username, user, login, password",
        r"(?i)user(name)?\s*[:=].+\n\s*password\s*[:=]\s*['\"]?(\S+)",
        'username: svc_deploy\npassword: "%s"' % E.password("gg_pair"),
        'username: svc_deploy\npassword: "${DB_PASSWORD}"', "High", ctx="raw", var="USERNAME",
        files="config/*.yml, docker-compose.yml, *.env",
        guide="쌍에서 username은 식별자(비밀 아님), password만 비밀이다. 두 span을 모두 마스킹하지 않고 비밀번호 span만 고르도록 학습한다.")
    add(g, "GG_Bearer_Token_Authorization_Header",
        "gitleaks (generic) & TruffleHog (http Authorization) & nuclei http/exposures",
        "HTTP Authorization 헤더에 들어가는 Bearer 토큰. 코드·curl·로그 어디서나 나타난다.",
        "요청 대상 API 호스트", "Authorization, Bearer",
        r"(?i)authorization:\s*bearer\s+([A-Za-z0-9._\-]{16,})",
        E.tok("", 48, B64URL, tag="gg_bearer"), "Bearer ${ACCESS_TOKEN}", "High",
        ctx="curl", var="ACCESS_TOKEN", flag="Authorization: Bearer", rhost="https://api.internal/v1/me",
        fmt="HTTP Header", guide="`Bearer` 다음의 긴 토큰만 비밀이다. `Bearer ${ACCESS_TOKEN}`처럼 참조가 오거나 `Bearer `만 있고 "
        "값이 없는 경우는 마스킹하지 않는다.")
    add(g, "GG_Generic_Encryption_Key",
        "gitleaks (generic) & Samsung/CredSweeper (AES/encryption key)",
        "대칭키 암호화에 쓰는 raw 키(hex/base64). ENCRYPTION_KEY/AES_KEY/SECRET_KEY 변수.",
        "암복호화 모듈", "encryption_key, aes_key, secret_key, cipher_key",
        r"(?i)(encryption|aes|cipher|secret)[_a-z]*key\s*[:=]\s*['\"]?([A-Fa-f0-9]{32,64}|[A-Za-z0-9+/=]{24,})",
        E.tok("", 64, HEX, tag="gg_enc"), "0000000000000000000000000000000000000000000000000000000000000000",
        "High", ctx="env", var="AES_ENCRYPTION_KEY",
        guide="실제 난수 키와 전부 0(초기화·예시) 키를 구분한다. 길이가 맞아도 모두 같은 문자면 비밀이 아니다.")
    add(g, "GG_Company_Email_Password_Combo",
        "SecretBench (email:password) & Nemotron-PII (credential email)",
        "업무 메일 주소와 비밀번호가 콜론으로 붙은 조합. 유출 계정 문맥에서 흔하다.",
        "SMTP/로그인 서버", "email, smtp_user, password",
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}:(\S{6,})",
        f"devops@example.co.kr:{E.password('gg_email','random')}", "devops@example.co.kr:${SMTP_PASSWORD}",
        "High", ctx="env", var="SMTP_CREDENTIALS", fmt="user:pass",
        guide="`이메일:값` 조합에서 이메일은 비밀이 아니고 콜론 뒤 비밀번호만 비밀이다. 뒤가 `${...}` 참조면 마스킹하지 않는다.")
    add(g, "GG_Database_Password_In_Config",
        "Skyscanner/whispers (uri.py, jproperties) & gitleaks",
        "DB 설정 블록 안의 password 필드. host/port/user는 비밀이 아니다.",
        "DB 호스트:포트", "DB_PASSWORD, datasource.password",
        r"(?i)(db|database|datasource)[._]?password\s*[:=]\s*(\S+)",
        E.password("gg_dbpw", "random"), "changeme", "High", ctx="java", var="spring_datasource_password",
        guide="같은 블록의 host/port/user/dbname은 식별자다. password 값만 비밀이며, `changeme` 같은 기본 플레이스홀더는 제외한다.")
    add(g, "GG_X_API_Key_Header",
        "nuclei http/exposures & gitleaks (generic api key header)",
        "커스텀 X-API-Key 헤더로 전달되는 키. 많은 사내·공개 API가 이 방식을 쓴다.",
        "요청 대상 API 호스트", "X-API-Key, x-api-key, apikey header",
        r"(?i)x-api-key:\s*([A-Za-z0-9._\-]{16,})",
        E.tok("", 36, ALNUM, tag="gg_xapi"), "x-api-key: <API_KEY>", "High",
        ctx="header", var="X_API_KEY", flag="X-API-Key", rhost="/v1/send", fmt="HTTP Header",
        guide="헤더 이름(X-API-Key)은 지표일 뿐 비밀이 아니다. 콜론 뒤 값만 비밀이며 `<API_KEY>`·`<...>` 플레이스홀더는 제외한다.")
    add(g, "GG_Basic_Auth_Base64_String",
        "Skyscanner/whispers (uri.py) & gitleaks (basic-auth) & detect-secrets (basic_auth)",
        "Authorization: Basic 뒤의 base64(user:pass) 문자열. 디코딩하면 자격증명이 드러난다.",
        "요청 대상 API 호스트", "Authorization, Basic",
        r"(?i)authorization:\s*basic\s+([A-Za-z0-9+/=]{16,})",
        E.b64url_bytes(b"svc_account:" + E.password("gg_basic", "random").encode()).replace("-", "+").replace("_", "/"),
        "Basic ${BASIC_AUTH}", "High", ctx="curl", var="BASIC_AUTH", flag="Authorization: Basic",
        rhost="https://api.internal/token", fmt="HTTP Header / Base64",
        guide="base64로 인코딩돼 겉보기엔 랜덤이지만 `user:pass`를 담은 비밀이다. 디코딩 결과가 자격증명 형태인지, 아니면 공개 식별자인지로 판단하도록 "
        "학습한다.")
    add(g, "GG_Base64_Encoded_High_Entropy_Blob",
        "Samsung/CredSweeper (base64) & Skyscanner/whispers (base64.yml)",
        "변수명이 비밀을 암시하고 값이 긴 base64 blob인 경우(인코딩된 키/인증서 등).",
        "복호화 후 사용되는 자격증명", "token, key, credentials, _b64",
        r"(?i)(token|key|secret|cred)[\w]*\s*[:=]\s*['\"]([A-Za-z0-9+/]{40,}={0,2})['\"]",
        E.b64url_bytes(E.d("gg_b64").raw(48)).replace("-", "+").replace("_", "/"),
        E.b64url_bytes(b"this is a public notice banner text").replace("-", "+").replace("_", "/"),
        "Medium", ctx="py", var="SERVICE_ACCOUNT_SECRET_B64",
        guide="같은 base64라도 디코딩 시 키/자격증명이면 비밀, 공개 문구·설정이면 아니다. 변수명과 길이가 핵심 단서다.")
    add(g, "GG_Generic_CLI_Secret_Flag",
        "gitleaks (cli) & Bash_Tool_Stdout (agent-run commands)",
        "셸 명령의 --token/--password/--api-key 플래그 뒤에 그대로 적힌 비밀. 에이전트가 실행하는 명령에 자주 섞인다.",
        "명령이 접속하는 서비스", "--token, --password, --api-key, -p",
        r"(?i)--(token|password|api[_-]?key|secret)[= ]+(\S+)",
        "$ deploy --token %s --env prod" % E.tok("", 40, ALNUM, tag="gg_cli"),
        "$ deploy --token $GITHUB_TOKEN --env prod", "High",
        ctx="raw", var="deploy", channel="Bash_Tool_Stdout / Source_Code", fmt="CLI Argument",
        guide="플래그 뒤 값이 리터럴 비밀인지 `$GITHUB_TOKEN`/`$(cat ...)` 같은 참조인지로 가른다. tool_input(명령 자체)에 들어간 비밀도 잡아야 한다.")
    add(g, "GG_Curl_User_Password_Flag",
        "gitleaks & Skyscanner/whispers (uri.py)",
        "curl -u user:pass 형태로 명령줄에 노출된 자격증명.",
        "curl 대상 URL", "curl -u, --user",
        r"curl\s+.*-u\s+([^:\s]+):(\S+)",
        f"admin:{E.password('gg_curl','random')}", "admin:$PASSWORD", "High",
        ctx="stdout", var="curl", flag="curl -u admin:*** https://api.internal -o -", channel="Bash_Tool_Stdout",
        fmt="CLI Argument",
        guide="`-u user:pass`에서 콜론 뒤만 비밀이다. 값이 `$PASSWORD` 같은 변수면 마스킹하지 않는다.")
    add(g, "GG_Laravel_Sanctum_Token",
        "gitleaks (generic) & Secrets-Patterns-DB (Laravel Sanctum)",
        "Laravel Sanctum/Passport 개인 액세스 토큰. `id|hash` 구조로, 파이프 뒤 해시가 비밀이다.",
        "Laravel 애플리케이션", "sanctum, plainTextToken, Bearer",
        r"\b\d+\|[A-Za-z0-9]{40,64}\b",
        f"{E.d('gg_sanctum').between(10,999)}|{E.tok('',48,ALNUM,tag='gg_sanctum2')}",
        "{id}|{hash}", "High", ctx="env", var="SANCTUM_TOKEN",
        files=".env, routes/api.php, *.log",
        guide="앞의 숫자 id는 공개 식별자, 파이프(|) 뒤 40~64자 해시가 비밀이다. `{id}|{hash}` 같은 템플릿 표기는 제외한다.")
    add(g, "GG_PowerShell_ConvertTo_SecureString",
        "gitleaks (powershell) & Secrets-Patterns-DB",
        "PowerShell에서 평문을 SecureString으로 바꾸는 구문. -String 뒤 평문이 비밀이다.",
        "대상 PowerShell 세션/서비스", "ConvertTo-SecureString, -AsPlainText",
        r"ConvertTo-SecureString\s+(?:-String\s+)?['\"]([^'\"]{6,})['\"]\s+-AsPlainText",
        '$sec = ConvertTo-SecureString -String "%s" -AsPlainText -Force' % E.password("gg_ps", "random"),
        '$sec = ConvertTo-SecureString -String $env:SVC_PASSWORD -AsPlainText -Force', "High", ctx="raw", var="ps",
        channel="Source_Code / Bash_Tool_Stdout", fmt="PowerShell", files="*.ps1, deploy/*.ps1",
        guide="`-AsPlainText` 앞의 리터럴 문자열이 비밀이다. `$env:...` 환경변수 참조는 값이 아니므로 제외한다.")
    add(g, "GG_Terraform_Variable_Default_Secret",
        "gitleaks & nuclei (http/exposures/configs) & WrongSecrets",
        "Terraform 변수의 default 값에 하드코딩된 비밀. `variable { default = \"...\" }`.",
        "프로비저닝 대상 리소스", "variable, default, sensitive",
        r"(?s)variable\s+\"[^\"]+\"\s*\{[^}]*default\s*=\s*\"([^\"]{8,})\"",
        'variable "db_password" {\n  type    = string\n  default = "%s"\n}' % E.tok("", 32, ALNUM, tag="gg_tf"),
        'variable "db_password" {\n  type    = string\n  default = var.db_password\n}', "High", ctx="raw", var="tf",
        channel="File_Read_Tool / Source_Code", fmt="HCL", files="variables.tf, terraform.tfvars, *.tf",
        guide="`default`에 박힌 리터럴이 비밀이다. `var.db_password`처럼 다른 변수를 참조하는 값은 비밀이 아니다.")
    add(g, "GG_Access_Secret_Key_Tuple",
        "SecretBench (AssetHarvester paired key/secret) & Samsung/CredSweeper",
        "access key와 secret key가 짝으로 나오는 범용 튜플. 둘 다 있어야 인증되며 secret 쪽이 핵심이다.",
        "짝지어진 API 엔드포인트", "access_key, secret_key, key_id, key_secret",
        r"(?i)access[_-]?key[_-]?id\s*[:=].+\n.*secret[_-]?access[_-]?key\s*[:=]\s*(\S+)",
        "[default]\naws_access_key_id = AKIA%s\naws_secret_access_key = %s"
        % (E.d("gg_akid").chars(16, BASE32), E.aws_secret("gg_tuple")),
        "[default]\naws_access_key_id = AKIA%s\naws_secret_access_key = <SECRET_ACCESS_KEY>"
        % E.d("gg_akid2").chars(16, BASE32), "High", ctx="raw", var="aws_secret_access_key",
        files="~/.aws/credentials, .env, config.ini",
        guide="access key id(공개 식별자)와 secret key(비밀)를 구분한다. AssetHarvester 관점에서 두 값은 한 자산에 묶이지만 마스킹 대상은 secret 쪽이다.")

    _ai(B)
    _cloud(B)
    _db(B)
    _vcs(B)
    _secmgr(B)
    _enterprise(B)
    _fintech(B)
    _messaging(B)
    _observ(B)
    _crypto(B)
    _mobile(B)


# imported lower; defined after populate for readability
from v3_data_services_more import _ai, _cloud, _db, _vcs, _secmgr, _enterprise, _fintech, _messaging, \
    _observ, _crypto, _mobile  # noqa: E402
