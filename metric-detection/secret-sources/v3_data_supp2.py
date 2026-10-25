"""Supplement 2: developer-tool credential files a coding agent routinely reads, plus a few more token-type
unbundlings. Each row is one distinct file/secret location. populate(B) appends to B.ROWS.
"""


def populate(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.DIGITS

    def cfg(cat, sub, path, host, idents, rx, body_pos, body_neg, guide, sev="High", cmd=None, fmt="Config File"):
        cmd = cmd or f"cat {path}"
        add(cat, sub, f"Dev tool credential file ({path})",
            f"`{path}`에 저장된 자격증명. 코딩 에이전트가 설정·인증을 확인하려 이 파일을 읽을 때 마주친다.",
            host, idents, rx, f"$ {cmd}\n{body_pos}", f"$ {cmd}\n{body_neg}", sev,
            ctx="raw", var=sub, fmt=fmt, channel="File_Read_Tool / Bash_Tool_Stdout", files=path, guide=guide)

    # ---- package / registry auth files (cat 05) ----
    cfg("05", "Npmrc_Scoped_AuthToken", "~/.npmrc", "registry.npmjs.org / private registry",
        "_authToken, //registry",
        r"_authToken=([^$\s][^\s]{20,})",
        "//npm.pkg.github.com/:_authToken=npm_%s\n@myorg:registry=https://npm.pkg.github.com" % E.d("s2npm").chars(36, ALNUM),
        "//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}\n@myorg:registry=https://npm.pkg.github.com",
        "`_authToken=` 뒤 리터럴 토큰이 비밀이다. `${NODE_AUTH_TOKEN}` 같은 CI 치환 변수는 값이 아니므로 제외한다. registry URL은 식별자다.")
    cfg("05", "Yarnrc_Yml_NpmAuthToken", ".yarnrc.yml", "npm registry",
        "npmAuthToken, npmRegistries",
        r"npmAuthToken:\s*([^\s\"]{20,})",
        'npmRegistries:\n  "//registry.npmjs.org":\n    npmAuthToken: npm_%s' % E.d("s2yarn").chars(36, ALNUM),
        'npmRegistries:\n  "//registry.npmjs.org":\n    npmAuthToken: "${NPM_TOKEN}"',
        "Yarn Berry의 `npmAuthToken:` 값이 비밀이다. 환경변수 치환(`${NPM_TOKEN}`)은 제외한다.")
    cfg("05", "Pip_Conf_Index_Credentials", "~/.config/pip/pip.conf", "private PyPI index",
        "index-url, extra-index-url",
        r"https?://[^:/\s]+:([^@/\s]{6,})@",
        "[global]\nextra-index-url = https://deploy:%s@pypi.internal/simple" % E.password("s2pip", "random"),
        "[global]\nextra-index-url = https://pypi.internal/simple",
        "index URL의 `user:pass@`에서 비밀번호만 비밀이다. 자격증명이 없는 index URL은 음성이다.")
    cfg("05", "Bundle_Config_Credential", ".bundle/config", "RubyGems private source",
        "BUNDLE_, GEM__",
        r"BUNDLE_[A-Z0-9_.]+:\s*\"([^\"]{8,})\"",
        'BUNDLE_GEMS__MYCO__COM: "deploy:%s"' % E.password("s2bundle", "random"),
        'BUNDLE_GEMS__MYCO__COM: "${GEM_CREDENTIALS}"',
        "Bundler config의 `user:pass` 자격증명이 비밀이다. 환경변수 참조는 제외한다.")
    cfg("05", "Composer_Auth_Json", "~/.composer/auth.json", "Packagist / private Composer repo",
        "http-basic, github-oauth",
        r"\"(password|token)\"\s*:\s*\"([^\"]{8,})\"",
        '{\n  "http-basic": {\n    "repo.myco.com": { "username": "deploy", "password": "%s" }\n  }\n}' % E.password("s2composer", "random"),
        '{\n  "http-basic": {\n    "repo.myco.com": { "username": "deploy", "password": "${COMPOSER_PW}" }\n  }\n}',
        "`password`/`token` 값이 비밀이다. username·repo 호스트는 식별자이고 환경변수 참조는 제외한다.")
    cfg("05", "Gem_Credentials", "~/.gem/credentials", "rubygems.org",
        ":rubygems_api_key:",
        r":rubygems_api_key:\s*(rubygems_[a-f0-9]{48}|\S{20,})",
        "---\n:rubygems_api_key: rubygems_%s" % E.d("s2gem").chars(48, HEX),
        "---\n:rubygems_api_key: <YOUR_API_KEY>",
        "`:rubygems_api_key:` 뒤 값이 비밀이다. `<YOUR_API_KEY>` 자리표시는 제외한다.")

    # ---- cloud / infra CLI credential files ----
    cfg("03", "Pgpass_Line", "~/.pgpass", "PostgreSQL host:port", "host:port:db:user:password",
        r"[^:\s]+:\d+:[^:]*:[^:]+:(\S+)",
        "db.internal:5432:appdb:svc:%s" % E.password("s2pgpass", "random"),
        "db.internal:5432:appdb:svc:*",
        "`.pgpass`의 다섯 번째 필드(password)만 비밀이다. host·port·db·user는 식별자이고 와일드카드 `*`는 값이 아니다.", fmt="pgpass")
    cfg("03", "My_Cnf_Password", "~/.my.cnf", "MySQL/MariaDB", "[client], password",
        r"(?im)^\s*password\s*=\s*(\S+)",
        "[client]\nuser=root\npassword=%s" % E.password("s2mycnf", "random"),
        "[client]\nuser=root\npassword=${MYSQL_PWD}",
        "`[client]` 블록의 `password=` 값이 비밀이다. user·host는 식별자이고 환경변수 참조는 제외한다.", fmt="INI")
    cfg("03", "S3cfg_Secret_Key", "~/.s3cfg", "S3-compatible storage", "secret_key, access_key",
        r"(?im)^secret_key\s*=\s*(\S{20,})",
        "[default]\naccess_key = AKIA%s\nsecret_key = %s" % (E.d("s2s3a").chars(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"), E.aws_secret("s2s3")),
        "[default]\naccess_key = AKIA%s\nsecret_key = ${S3_SECRET}" % E.d("s2s3b").chars(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
        "s3cmd의 `secret_key`만 비밀이다. `access_key`는 식별자이고 환경변수 참조는 제외한다.", fmt="INI")
    cfg("06", "Databrickscfg_Token", "~/.databrickscfg", "*.cloud.databricks.com", "[DEFAULT], token, host",
        r"(?im)^token\s*=\s*(dapi[a-f0-9]{32}|\S{20,})",
        "[DEFAULT]\nhost = https://myco.cloud.databricks.com\ntoken = dapi%s" % E.d("s2dbx").chars(32, HEX),
        "[DEFAULT]\nhost = https://myco.cloud.databricks.com\ntoken = ${DATABRICKS_TOKEN}",
        "`token = dapi...`가 비밀이다. host는 식별자이고 환경변수 참조는 제외한다.", fmt="INI")
    cfg("06", "Snowflake_Connections_Toml", "~/.snowflake/connections.toml", "*.snowflakecomputing.com",
        "password, connections",
        r"password\s*=\s*['\"]([^'\"]{8,})['\"]",
        '[default]\naccount = "ab12345"\nuser = "svc"\npassword = "%s"' % E.password("s2sf", "random"),
        '[default]\naccount = "ab12345"\nuser = "svc"\nauthenticator = "externalbrowser"',
        "`password` 값이 비밀이다. account·user는 식별자이고, `authenticator=externalbrowser`(SSO) 방식은 저장된 비밀이 없다.", fmt="TOML")
    cfg("03", "Azure_AccessTokens_Json", "~/.azure/accessTokens.json", "login.microsoftonline.com",
        "accessToken, refreshToken",
        r"\"(accessToken|refreshToken)\"\s*:\s*\"([^\"]{20,})\"",
        '[\n  { "accessToken": "eyJ0%s", "refreshToken": "0.AX%s" }\n]' % (E.d("s2az1").chars(80, B64URL), E.d("s2az2").chars(60, B64URL)),
        '[\n  { "tokenType": "Bearer", "expiresOn": "2026-02-12 00:00:00" }\n]',
        "`accessToken`/`refreshToken` 값이 비밀이다. tokenType·expiresOn은 메타데이터다.", fmt="JSON")
    cfg("06", "Boto_Config_Credentials", "~/.boto", "GCS/S3 via boto",
        "gs_secret_access_key, aws_secret_access_key",
        r"(?im)(gs_secret_access_key|aws_secret_access_key)\s*=\s*(\S{20,})",
        "[Credentials]\ngs_access_key_id = GOOG%s\ngs_secret_access_key = %s" % (E.d("s2botoa").chars(20, ALNUM), E.aws_secret("s2boto")),
        "[Credentials]\ngs_access_key_id = GOOG%s\ngs_secret_access_key = ${GS_SECRET}" % E.d("s2botob").chars(20, ALNUM),
        "`*_secret_access_key`만 비밀이다. access_key_id는 식별자이고 환경변수 참조는 제외한다.", fmt="INI")

    # ---- editor / agent config files ----
    cfg("02", "VSCode_Settings_Token", ".vscode/settings.json", "확장이 호출하는 API",
        "settings.json, apiKey",
        r"\"[\w.]*(apiKey|token|secret)\"\s*:\s*\"([^\"]{16,})\"",
        '{\n  "myext.apiKey": "sk-%s",\n  "editor.fontSize": 14\n}' % E.d("s2vscode").chars(40, ALNUM),
        '{\n  "myext.apiKey": "${env:MY_API_KEY}",\n  "editor.fontSize": 14\n}',
        "에디터 설정 JSON에 박힌 apiKey/token 값이 비밀이다. `${env:...}` 참조와 fontSize 같은 설정은 제외한다.", fmt="JSON")
    cfg("02", "Continue_Config_Json", ".continue/config.json", "LLM 공급자 API",
        "models, apiKey",
        r"\"apiKey\"\s*:\s*\"([^\"]{16,})\"",
        '{\n  "models": [{ "provider": "anthropic", "apiKey": "sk-ant-api03-%s" }]\n}' % E.d("s2cont").chars(95, B64URL),
        '{\n  "models": [{ "provider": "anthropic", "apiKey": "<ANTHROPIC_API_KEY>" }]\n}',
        "Continue/코딩 어시스턴트 설정의 `apiKey`가 비밀이다. provider 이름과 `<...>` 자리표시는 제외한다.", fmt="JSON")
    cfg("02", "Aider_Model_Settings_Key", ".aider.conf.yml", "LLM 공급자 API",
        "openai-api-key, anthropic-api-key",
        r"(?i)(openai|anthropic)-api-key:\s*(\S{16,})",
        "openai-api-key: sk-%s\nmodel: gpt-4o" % E.d("s2aider").chars(48, ALNUM),
        "openai-api-key: ${OPENAI_API_KEY}\nmodel: gpt-4o",
        "aider 설정의 `*-api-key` 값이 비밀이다. model 이름과 환경변수 참조는 제외한다.", fmt="YAML")

    # ---- CI / pipeline inline secrets ----
    cfg("05", "GitHub_Actions_Inline_Secret", ".github/workflows/deploy.yml", "배포 대상 서비스",
        "env, run, with",
        r"(?i)(TOKEN|KEY|PASSWORD):\s*([A-Za-z0-9._-]{20,})",
        "      env:\n        DEPLOY_TOKEN: ghp_%s\n      run: ./deploy.sh" % E.d("s2gha").chars(36, ALNUM),
        "      env:\n        DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}\n      run: ./deploy.sh",
        "워크플로에 직접 박은 토큰이 비밀이다. `${{ secrets.* }}`/`${{ vars.* }}` 참조는 안전한 사용법이므로 제외한다.", fmt="YAML")
    cfg("05", "GitLab_CI_Variables_Secret", ".gitlab-ci.yml", "배포 대상 서비스",
        "variables, script",
        r"(?i)(TOKEN|KEY|PASSWORD):\s*['\"]?([A-Za-z0-9._-]{20,})",
        "variables:\n  REGISTRY_PASSWORD: %s\nscript:\n  - docker login -p $REGISTRY_PASSWORD" % E.tok("", 32, ALNUM, tag="s2glci"),
        "variables:\n  REGISTRY_PASSWORD: $CI_REGISTRY_PASSWORD\nscript:\n  - docker login -p $REGISTRY_PASSWORD",
        "`variables:`에 평문으로 둔 비밀이 노출이다. `$CI_*`/보호 변수 참조는 안전한 사용법이라 제외한다.", fmt="YAML")
    cfg("06", "Jenkinsfile_WithCredentials_Literal", "Jenkinsfile", "Jenkins 자격증명",
        "withCredentials, credentials(",
        r"(?i)(auth|bearer|token)[:= ]+['\"]?([A-Za-z0-9]{24,})",
        "withCredentials([string(credentialsId: 'tok', variable: 'TOK')]) {\n  sh \"curl -H 'auth: %s'\"\n}" % E.d("s2jenk").chars(32, ALNUM),
        "withCredentials([string(credentialsId: 'tok', variable: 'TOK')]) {\n  sh 'curl -H \"auth: $TOK\"'\n}",
        "파이프라인에 리터럴로 박힌 비밀이 노출이다. `credentialsId`로 주입해 `$TOK`로 참조하는 올바른 사용은 제외한다.", fmt="Groovy")

    # ---- shell / REPL history variants ----
    cfg("12", "Psql_History_Credential", "~/.psql_history", "PostgreSQL",
        ".psql_history, \\c, PGPASSWORD",
        r"(?i)(PGPASSWORD=|password\s+')(\S{6,})",
        "\\c appdb\nALTER USER svc WITH PASSWORD '%s';" % E.password("s2psqlh", "random"),
        "\\c appdb\n\\dt\nSELECT count(*) FROM users;",
        "psql 히스토리에 남은 `ALTER USER ... PASSWORD '...'`의 비밀번호가 노출이다. 조회·메타 명령만 있는 줄은 음성이다.", fmt="SQL History")
    cfg("12", "Mysql_History_Credential", "~/.mysql_history", "MySQL",
        ".mysql_history, IDENTIFIED BY",
        r"(?i)IDENTIFIED BY\s+'([^']{6,})'",
        "CREATE USER 'svc'@'%%' IDENTIFIED BY '%s';" % E.password("s2myh", "random"),
        "SHOW DATABASES;\nUSE appdb;\nSELECT VERSION();",
        "`IDENTIFIED BY '...'`의 비밀번호가 노출이다. SHOW/USE/SELECT 같은 줄은 음성이다.", fmt="SQL History")
    cfg("12", "Core_Dump_Strings_Secret", "core.12345 (strings)", "크래시한 프로세스의 서비스",
        "strings, core dump, heap",
        r"(?i)(password|secret|token)=([A-Za-z0-9._/+-]{12,})",
        "$ strings core.12345 | grep -i pass\nDB_PASSWORD=%s" % E.tok("", 32, ALNUM, tag="s2core"),
        "$ strings core.12345 | grep -i pass\n(no matches)",
        "코어 덤프에서 `strings`로 추출한 메모리 속 평문 비밀이 노출이다. 매칭이 없으면 음성이다.", cmd="strings core.12345 | grep -i pass",
        fmt="Raw Stream")

    # ---- a few more token-type unbundlings ----
    pfx("09", "Slack_Config_Access_Token", "Slack", "osv-scalibr veles/slackappconfigaccesstoken",
        "slack.com/api/apps", "SLACK_CONFIG_ACCESS_TOKEN", "xoxe.xoxp-1", 100, alph=B64URL, sep="-", sev="High",
        ctx="env", regex=r"\bxoxe\.xoxp-1-[A-Za-z0-9-]{100,}\b",
        what="Slack 앱 설정 액세스 토큰(`xoxe.xoxp-1-`). 앱 매니페스트 수정 권한.")
    pfx("09", "Slack_Config_Refresh_Token", "Slack", "osv-scalibr veles/slackappconfigrefreshtoken",
        "slack.com/api/apps", "SLACK_CONFIG_REFRESH_TOKEN", "xoxe-1", 147, alph=B64URL, sep="-", sev="High",
        ctx="env", regex=r"\bxoxe-1-[A-Za-z0-9_-]{140,}\b", what="Slack 앱 설정 리프레시 토큰(`xoxe-1-`).")
    pfx("03", "AWS_IAM_Role_Unique_Id", "Amazon", "awslabs/git-secrets (AROA prefix)",
        "AWS IAM", "AWS_ROLE_ID", "AROA", 16, alph="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", sep="", sev="Medium",
        ctx="env", regex=r"\bAROA[A-Z0-9]{16}\b", var="AWS_ROLE_ID",
        what="AWS IAM 역할 고유 ID(`AROA`). 정책 신뢰관계·세션 추적에 쓰이는 식별자지만 유출 시 공격면 정보가 된다.",
        neg="AROAEXAMPLEEXAMPLE00")
    pfx("03", "GCP_OAuth_Client_ID_Negative", "Google", "gitleaks (gcp client id)",
        "oauth2.googleapis.com", "GOOGLE_CLIENT_ID", "", 12, alph=DIGITS, sep="", sev="None (Negative)",
        ctx="js", regex=r"\b\d{12}-[a-z0-9]{32}\.apps\.googleusercontent\.com\b", var="GOOGLE_CLIENT_ID",
        what="GCP OAuth 클라이언트 ID(`...apps.googleusercontent.com`). 공개 식별자라 비밀이 아니다(대조군).",
        neg="${GOOGLE_CLIENT_ID}")
    B.ROWS[-1]["Risk_Severity"] = "None (Negative)"
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        'const clientId = "%s-%s.apps.googleusercontent.com";'
        % (E.d("s2gcid").chars(12, DIGITS), E.d("s2gcid2").chars(32, "abcdefghijklmnopqrstuvwxyz0123456789")), "gcpclientid")
    B.ROWS[-1]["SLM_Training_Guideline_KR"] = (
        "OAuth client_id는 공개 식별자라 마스킹하면 로그인이 깨진다. 짝인 client_secret(`GOCSPX-`)만 비밀이다. "
        "둘이 같은 파일에 있어도 secret만 고른다.")
