"""Supplementary rows: additional distinct secret types and agent/AST contexts to broaden coverage toward the
600 goal. populate(B) appends to B.ROWS. Same conventions as the other data modules.
"""


def populate(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.DIGITS

    # ================= crypto exchanges (cat 08) =================
    ex = [("Bithumb", "api.bithumb.com", "BITHUMB", 32), ("Coinone", "api.coinone.co.kr", "COINONE", 40),
          ("Korbit", "api.korbit.co.kr", "KORBIT", 40), ("Gopax", "api.gopax.co.kr", "GOPAX", 44),
          ("OKX", "www.okx.com", "OKX", 32), ("Bybit", "api.bybit.com", "BYBIT", 36),
          ("KuCoin", "api.kucoin.com", "KUCOIN", 36), ("Gate_io", "api.gateio.ws", "GATEIO", 64),
          ("Bitget", "api.bitget.com", "BITGET", 40), ("HTX_Huobi", "api.huobi.pro", "HUOBI", 36),
          ("MEXC", "api.mexc.com", "MEXC", 32), ("Kraken", "api.kraken.com", "KRAKEN", 56)]
    for name, host, kw, n in ex:
        pfx("08", f"{name}_API_Secret", name.replace("_", "."), "gitleaks & secrets-patterns-db (exchange secret)",
            host, f"{kw}_API_SECRET", "", n, alph=ALNUM if n != 56 else B64, sep="", sev="High", ctx="env",
            regex=rf"(?i){kw.lower()}[\w.\-]{{0,20}}secret['\"\s:=]{{1,5}}([A-Za-z0-9/+=]{{{n}}})",
            what=f"{name.replace('_','.')} 거래소 API Secret({n}자). API key와 함께 HMAC 서명으로 주문·출금 권한을 가진다.",
            neg="${" + kw + "_API_SECRET}", var=f"{kw}_API_SECRET")
    add("08", "OKX_API_Passphrase", "OKX docs (OK-ACCESS-PASSPHRASE)",
        "OKX는 key/secret 외에 사용자가 정한 passphrase까지 세 요소로 서명한다. passphrase도 비밀이다.",
        "www.okx.com", "OK-ACCESS-PASSPHRASE, apiKey, secretKey",
        r"(?i)passphrase['\"\s:=]{1,5}([^\s'\"]{6,})",
        'OKX_API_PASSPHRASE = "%s"' % E.password("okx_pass", "random"), 'OKX_API_PASSPHRASE = "${OKX_PASSPHRASE}"',
        "High", ctx="py", var="OKX_API_PASSPHRASE",
        guide="거래소 3요소(key/secret/passphrase) 중 secret과 passphrase가 비밀이다. apiKey는 공개 식별자다. passphrase가 참조 구문이면 제외한다.")

    # ================= Korea/Asia auth & social (cat 09) =================
    add("09", "Kakao_REST_API_Key_AdminKey", "developers.kakao.com (Authorization: KakaoAK {ADMIN_KEY})",
        "카카오 Admin 키. `Authorization: KakaoAK` 헤더로 서버에서만 쓰며, REST/JS/Native 앱키 중 유일하게 비밀로 다뤄야 한다.",
        "kapi.kakao.com", "KAKAO_ADMIN_KEY, KakaoAK",
        r"(?i)KakaoAK\s+([a-f0-9]{32})",
        "$ curl -s https://kapi.kakao.com/v2/user/me \\\n    -H 'Authorization: KakaoAK %s'" % E.d("kakao_admin").chars(32, HEX),
        "$ curl -s https://kapi.kakao.com/v2/user/me \\\n    -H 'Authorization: KakaoAK ${KAKAO_ADMIN_KEY}'",
        "Critical", ctx="raw", var="KAKAO_ADMIN_KEY", fmt="HTTP Header",
        guide="카카오 앱키 4종 중 JavaScript 키·Native 키는 클라이언트 공개용이고, Admin 키(`KakaoAK` 헤더)만 서버 비밀이다. REST API 키도 비밀로 본다.")
    pfx("09", "Kakao_JavaScript_Key_Negative", "Kakao", "developers.kakao.com (JavaScript key)",
        "web", "KAKAO_JS_KEY", "", 32, alph=HEX, sep="", sev="None (Negative)", ctx="js",
        regex=r"\b[a-f0-9]{32}\b", var="kakaoJsKey",
        what="카카오 JavaScript 앱키. 웹 프런트엔드에 노출되는 공개 키라 비밀이 아니다(오탐 방지 대조군).",
        neg="process.env.KAKAO_JS_KEY",
        guide="JS 키는 도메인 등록으로 보호되는 공개 키다. Admin 키(KakaoAK)와 형식이 비슷해도 용도가 공개이므로 마스킹하면 로그인 위젯이 깨진다.")
    B.ROWS[-1]["Risk_Severity"] = "None (Negative)"
    pfx("09", "Naver_Login_Client_Secret", "Naver", "developers.naver.com (OAuth client secret)",
        "nid.naver.com", "NAVER_CLIENT_SECRET", "", 10, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)naver[\w.\-]{0,20}client[_-]?secret['\"\s:=]{1,5}([A-Za-z0-9]{8,16})",
        what="네이버 로그인 OAuth client secret(10자 안팎). client_id는 공개 식별자다.", neg="${NAVER_CLIENT_SECRET}",
        var="NAVER_CLIENT_SECRET")
    pfx("09", "PAYCO_Client_Secret", "PAYCO", "developers.payco.com",
        "apis.payco.com", "PAYCO_CLIENT_SECRET", "", 32, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)payco[\w.\-]{0,20}secret['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="PAYCO 간편결제/로그인 client secret(32자).", neg="${PAYCO_CLIENT_SECRET}", var="PAYCO_CLIENT_SECRET")
    pfx("09", "Gitee_Token", "Gitee", "secrets-patterns-db & Gitee personal access token",
        "gitee.com", "GITEE_TOKEN", "", 32, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)gitee[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="Gitee(码云, 중국 Git 호스팅) 개인 액세스 토큰(32자).", neg="${GITEE_TOKEN}")
    pfx("09", "Qiniu_Secret_Key", "Qiniu", "gitleaks & Qiniu(七牛) cloud",
        "qiniu.com", "QINIU_SECRET_KEY", "", 40, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"(?i)qiniu[\w.\-]{0,30}['\"\s:=]{1,5}([A-Za-z0-9_-]{40})",
        what="Qiniu(七牛) 클라우드 스토리지 Secret Key(40자).", neg="${QINIU_SECRET_KEY}", var="QINIU_SECRET_KEY")

    # ================= more DB connection schemes (cat 04) =================
    for scheme, host, sub, note in (
            ("sqlserver", "sql.internal:1433", "SQLServer", "SQL Server"),
            ("mariadb", "db.internal:3306", "MariaDB", "MariaDB"),
            ("clickhouse", "ch.internal:8443", "ClickHouse", "ClickHouse"),
            ("cockroachdb", "crdb.internal:26257", "CockroachDB", "CockroachDB"),
            ("cassandra", "cass.internal:9042", "Cassandra", "Cassandra"),
            ("neo4j+s", "graph.internal:7687", "Neo4j_Bolt", "Neo4j Bolt"),
            ("amqps", "mq.internal:5671", "AMQPS", "AMQPS/RabbitMQ TLS"),
            ("rediss", "cache.internal:6380", "Redis_TLS", "Redis TLS")):
        pw = E.password("supp_db:" + sub, "random")
        add("04", f"{sub}_Connection_String", "Skyscanner/whispers uri.py & gitleaks (db uri)",
            f"{note} 접속 URL. `{scheme}://user:password@host`의 비밀번호만 비밀이고 나머지는 식별자다.",
            host, "DATABASE_URL, user, password",
            rf"{scheme.replace('+', chr(92)+'+')}://[^:/\s]+:([^@/\s]+)@[^\s]+",
            f"{scheme}://svc:{pw}@{host}/app", f"{scheme}://svc:${{DB_PASSWORD}}@{host}/app", "High",
            ctx="env", var="DATABASE_URL", fmt="Connection String",
            guide="`user:` 와 `@` 사이 비밀번호만 마스킹한다. host/port/db와 `${DB_PASSWORD}` 참조는 제외한다.")
    add("04", "Kafka_SASL_JAAS_Password", "gitleaks & Kafka client JAAS config",
        "Kafka 클라이언트 SASL/PLAIN JAAS 설정의 `password=`. 브로커 인증 비밀이다.",
        "kafka.internal:9093", "sasl.jaas.config, PlainLoginModule, password",
        r"(?i)password\s*=\s*['\"]([^'\"]{6,})['\"]",
        'sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="svc" password="%s";' % E.password("kafka", "random"),
        'sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="svc" password="${KAFKA_PASSWORD}";',
        "High", ctx="raw", var="sasl_jaas", fmt="Properties", files="client.properties, application.yml",
        guide="JAAS 문자열 안 `password=\"...\"`만 비밀이다. username·LoginModule 클래스명은 식별자다.")
    add("04", "Elasticsearch_Basic_Auth_URL", "gitleaks & Elasticsearch client URL",
        "Elasticsearch 접속 URL에 `https://user:pass@host` 형태로 든 자격증명.",
        "es.internal:9200", "ELASTICSEARCH_URL, elastic:, @",
        r"https?://[^:/\s]+:([^@/\s]{6,})@[^\s]*:9200",
        "ELASTICSEARCH_URL=https://elastic:%s@es.internal:9200" % E.password("es", "random"),
        "ELASTICSEARCH_URL=https://elastic:${ES_PASSWORD}@es.internal:9200", "High", ctx="raw",
        var="ELASTICSEARCH_URL", fmt="Connection String",
        guide="URL의 `user:` 와 `@` 사이 비밀번호만 마스킹한다. 포트·인덱스·호스트는 식별자다.")

    # ================= more agent tool-chain trajectories (cat 12) =================
    tc = [
        ("Vault_KV_Get_Output", "vault kv get -format=json secret/app", "data.data 필드의 비밀",
         r"\"[a-z_]*(password|api_key|token)\"\s*:\s*\"([^\"]{8,})\"",
         '[Tool Result]:\n{\n  "data": { "data": { "db_password": "%s" } }\n}' % E.password("vaultkv", "random"),
         '[Tool Result]:\n{\n  "data": { "data": { "db_password": "<hidden>" } }\n}',
         "`vault kv get`의 `data.data` 안 값이 비밀이다. 메타데이터(version, created_time)는 식별자다."),
        ("OnePassword_CLI_Read", "op read op://vault/db/password", "op CLI가 출력한 평문 비밀",
         r"\n(\S{10,})$",
         '[Tool Call]: bash({"command":"op read op://prod/postgres/password"})\n[Tool Result]:\n%s' % E.password("opcli", "random"),
         '[Tool Call]: bash({"command":"op read op://prod/postgres/username"})\n[Tool Result]:\nsvc_deploy',
         "`op read`는 지정 필드의 평문 값을 그대로 출력한다. password 필드 결과는 비밀, username 결과는 식별자다. tool_input의 경로로 무엇을 읽는지 본다."),
        ("Kubeconfig_Client_Key_Data", "cat ~/.kube/config", "client-key-data의 base64 개인 키",
         r"client-key-data:\s*([A-Za-z0-9+/=]{40,})",
         'users:\n- name: admin\n  user:\n    client-certificate-data: %s\n    client-key-data: %s'
         % (E.d("kubecert").chars(40, B64), E.d("kubekey").chars(120, B64)),
         'users:\n- name: admin\n  user:\n    exec:\n      command: aws\n      args: ["eks","get-token"]',
         "kubeconfig의 `client-key-data`(base64 개인 키)가 비밀이다. `certificate-data`는 공개 인증서, `exec` 플러그인 방식은 저장된 비밀이 없다."),
        ("GCloud_ADC_JSON", "cat ~/.config/gcloud/application_default_credentials.json", "refresh_token/client_secret",
         r"\"(refresh_token|client_secret)\"\s*:\s*\"([^\"]{20,})\"",
         '[Tool Result]:\n{\n  "client_id": "764086.apps.googleusercontent.com",\n  "refresh_token": "1//%s",\n  "type": "authorized_user"\n}' % E.d("adc").chars(50, B64URL),
         '[Tool Result]:\n{\n  "client_id": "764086.apps.googleusercontent.com",\n  "type": "authorized_user"\n}',
         "ADC JSON의 `refresh_token`/`client_secret`이 비밀이다. client_id·type은 식별자다."),
        ("Maven_Settings_Server_Password", "cat ~/.m2/settings.xml", "server/password",
         r"<password>([^<]{6,})</password>",
         '<servers>\n  <server>\n    <id>nexus</id>\n    <username>deploy</username>\n    <password>%s</password>\n  </server>\n</servers>' % E.password("maven", "random"),
         '<servers>\n  <server>\n    <id>nexus</id>\n    <username>deploy</username>\n    <password>${env.NEXUS_PW}</password>\n  </server>\n</servers>',
         "`<password>` 태그 안 값이 비밀이다. `<username>`·`<id>`는 식별자이고 `${env....}` 참조는 제외한다."),
        ("Rclone_Config_Token", "cat ~/.config/rclone/rclone.conf", "token/pass (obscured)",
         r"(?i)(token|pass)\s*=\s*(\S{16,})",
         '[gdrive]\ntype = drive\ntoken = {"access_token":"ya29.%s","refresh_token":"1//%s"}' % (E.d("rclone1").chars(60, B64URL), E.d("rclone2").chars(40, B64URL)),
         '[gdrive]\ntype = drive\ntoken = ${RCLONE_TOKEN}',
         "rclone.conf의 `token`/`pass` 값이 비밀이다. `type`·remote 이름은 식별자다. rclone의 obscure된 pass도 되돌릴 수 있어 비밀로 본다."),
        ("AWS_SSO_Cache_Token", "cat ~/.aws/sso/cache/*.json", "accessToken",
         r"\"accessToken\"\s*:\s*\"([^\"]{20,})\"",
         '[Tool Result]:\n{\n  "startUrl": "https://my.awsapps.com/start",\n  "accessToken": "%s",\n  "expiresAt": "2026-02-12T00:00:00Z"\n}' % E.d("ssocache").chars(120, B64URL),
         '[Tool Result]:\n{\n  "startUrl": "https://my.awsapps.com/start",\n  "expiresAt": "2026-02-12T00:00:00Z"\n}',
         "SSO 캐시의 `accessToken`은 유효기간 내 실제 자격이라 비밀이다. startUrl·expiresAt는 식별자/메타다."),
        ("Ansible_Vault_Decrypted_View", "ansible-vault view group_vars/all/vault.yml", "복호화된 vault 변수",
         r"(?i)vault_\w*(password|secret|key)\s*:\s*(\S{8,})",
         '[Tool Result]:\nvault_db_password: %s\nvault_api_key: %s' % (E.password("av1", "random"), E.tok("", 32, ALNUM, tag="av2")),
         '[Tool Result]:\n$ANSIBLE_VAULT;1.1;AES256\n66383934653...(still encrypted)',
         "`ansible-vault view`가 복호화해 평문으로 보여준 변수는 비밀이다. `$ANSIBLE_VAULT;1.1;AES256` 암호문 블록 자체는 복호화 전이라 음성이다."),
        ("Gradle_Properties_Credential", "cat ~/.gradle/gradle.properties", "repo password / signing key",
         r"(?i)\w*(password|apikey|secret)\s*=\s*(\S{8,})",
         '[Tool Result]:\nnexusUsername=deploy\nnexusPassword=%s\nsigning.keyId=24875A1F' % E.password("gradle", "random"),
         '[Tool Result]:\nnexusUsername=deploy\nnexusPassword=\norg.gradle.jvmargs=-Xmx2g',
         "gradle.properties의 password/apikey/secret 값이 비밀이다. username·keyId·jvmargs는 식별자/설정이고 빈 값은 음성이다."),
        ("Wrangler_Secret_Put_Stdin", "wrangler secret put API_KEY", "Cloudflare Workers 시크릿 입력",
         r"(?i)(secret|key|token)\s*[:=]\s*(\S{16,})",
         '[Tool Call]: bash({"command":"echo \'api_key=%s\' | wrangler secret put API_KEY"})' % E.tok("", 32, ALNUM, tag="wrangler"),
         '[Tool Call]: bash({"command":"wrangler secret put API_KEY < /dev/stdin"})',
         "secret을 stdin으로 넣는 명령(tool_input)에 리터럴 값이 박히면 비밀이다. 파일/stdin 리다이렉션만 있는 명령은 음성이다."),
        ("Heroku_Config_Output", "heroku config -a myapp", "config vars 덤프",
         r"(?i)(SECRET|TOKEN|KEY|URL)\s*:\s*(\S*://\S+|[A-Za-z0-9/+_-]{20,})",
         '[Tool Result]:\n=== myapp Config Vars\nDATABASE_URL: postgres://u:%s@h:5432/d\nSECRET_KEY_BASE: %s' % (E.password("heroku1", "random"), E.tok("", 48, HEX, tag="heroku2")),
         '[Tool Result]:\n=== myapp Config Vars\nRACK_ENV: production\nLOG_LEVEL: info',
         "`heroku config`의 DATABASE_URL·SECRET_KEY_BASE 등 값이 비밀이다. RACK_ENV·LOG_LEVEL 같은 비민감 설정은 음성이다."),
        ("Systemctl_Show_Environment", "systemctl show app -p Environment", "유닛 Environment= 비밀",
         r"Environment=\{?[A-Z_]*(SECRET|TOKEN|KEY|PASSWORD)=([^\s}]{8,})",
         '[Tool Result]:\nEnvironment=DB_PASSWORD=%s API_PORT=8080' % E.password("systemd", "random"),
         '[Tool Result]:\nEnvironment=API_PORT=8080 LOG_LEVEL=info',
         "systemd 유닛의 `Environment=`에 박힌 비밀 변수가 노출된다. API_PORT·LOG_LEVEL 같은 값은 음성이다."),
    ]
    for sub, cmd, _desc, rx, pos, neg, guide in tc:
        add("12", sub, "Agent tool trajectory & " + cmd.split()[0],
            f"`{cmd}` 류 명령의 출력/입력에 자격증명이 드러나는 경우. 에이전트가 설정을 조회·주입할 때 마주친다.",
            "로컬 설정/서비스", cmd.split()[0] + ", " + sub, rx, pos, neg, "High",
            ctx="raw", var=sub, fmt="Tool Result", channel="Bash_Tool_Stdout / File_Read",
            files="터미널 stdout, 설정 파일", guide=guide)

    # ================= AST fallback contrasts in more languages (cat 12) =================
    ast = [
        ("Ruby_ENV_Fetch_Default", "Ruby", "*.rb, config/*.rb",
         r"ENV\.fetch\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]{12,})['\"]\s*\)",
         'STRIPE_KEY = ENV.fetch("STRIPE_SECRET_KEY", "sk_live_%s")' % E.d("ruby").chars(28, ALNUM),
         'STRIPE_KEY = ENV.fetch("STRIPE_SECRET_KEY") { raise "missing key" }',
         "`ENV.fetch(name, default)`의 두 번째 인자가 리터럴 비밀이면 마스킹한다. 블록(`{ raise }`)으로 기본값을 막은 형태는 비밀이 없다."),
        ("CSharp_Env_Null_Coalesce", "C#", "*.cs, appsettings 로더",
         r"GetEnvironmentVariable\([^)]+\)\s*\?\?\s*\"([^\"]{12,})\"",
         'var key = Environment.GetEnvironmentVariable("API_KEY") ?? "%s";' % E.tok("", 40, ALNUM, tag="csharp"),
         'var key = Environment.GetEnvironmentVariable("API_KEY") ?? throw new Exception("API_KEY");',
         "`?? \"리터럴\"` 폴백이 토큰 형태면 비밀이다. `?? throw ...`는 폴백 비밀이 없다."),
        ("Rust_Env_Unwrap_Or", "Rust", "*.rs",
         r"env::var\([^)]+\)\.unwrap_or\(\s*\"([^\"]{12,})\"",
         'let token = std::env::var("GH_TOKEN").unwrap_or("ghp_%s".to_string());' % E.d("rust").chars(36, ALNUM),
         'let token = std::env::var("GH_TOKEN").expect("GH_TOKEN must be set");',
         "`unwrap_or(\"리터럴\")`의 인자가 토큰 형태면 비밀이다. `expect(...)`로 끝나면 폴백 비밀이 없다."),
        ("PHP_Getenv_Elvis_Default", "PHP", "*.php, config/*.php",
         r"getenv\(\s*['\"][^'\"]+['\"]\s*\)\s*\?:\s*['\"]([^'\"]{12,})['\"]",
         "$key = getenv('API_KEY') ?: '%s';" % E.tok("", 32, ALNUM, tag="php"),
         "$key = getenv('API_KEY') ?: throw new RuntimeException('API_KEY');",
         "PHP 엘비스(`?:`) 뒤 리터럴이 토큰 형태면 비밀이다. 예외를 던지는 형태는 폴백 비밀이 없다."),
    ]
    for sub, lang, files, rx, pos, neg, guide in ast:
        add("12", sub, f"Language AST ({lang}) fallback default", f"{lang}에서 환경변수가 없을 때 쓰는 하드코딩 폴백 비밀.",
            "앱이 호출하는 API", f"getenv, fallback, {lang}", rx, pos, neg, "High",
            ctx="raw", var=sub, fmt=f"{lang} Source", channel="Source_Code", files=files, guide=guide)

    # a strong dedicated negative row (dotenv example file)
    add("12", "Dotenv_Example_File_Negative", "CredData Class X & .env.example convention",
        "`.env.example`는 커밋되는 템플릿이라 값 자리에 플레이스홀더만 있다. 실제 `.env`와 대비되는 대표 음성.",
        "None (Safe Context)", ".env.example, your-, changeme, xxxx",
        r"DB_PASSWORD=([A-Za-z0-9_]{12,})",
        'DB_PASSWORD=super_secret_prod_pw_%s' % E.d("dotenv_real").chars(10, ALNUM),
        '# .env.example\nDB_PASSWORD=your-db-password-here\nAPI_KEY=changeme\nJWT_SECRET=<generate-with-openssl>',
        "None (Negative)", ctx="raw", var="DOTENV", channel="File_Read_Tool", fmt="DotEnv",
        files=".env.example, .env.sample, .env.template",
        guide="`.env.example`의 `your-...`/`changeme`/`<...>`는 전부 플레이스홀더라 마스킹하지 않는다. 실제 `.env`에 든 난수 값만 비밀이다.")

    # ================= more observability / alerting (cat 10) =================
    obsv = [("Rollbar", "api.rollbar.com", "ROLLBAR_TOKEN", 32), ("Bugsnag", "api.bugsnag.com", "BUGSNAG_API_KEY", 32),
            ("PagerDuty", "api.pagerduty.com", "PAGERDUTY_TOKEN", 20), ("Opsgenie", "api.opsgenie.com", "OPSGENIE_KEY", 36),
            ("Honeybadger", "api.honeybadger.io", "HONEYBADGER_API_KEY", 32), ("Raygun", "api.raygun.com", "RAYGUN_KEY", 28),
            ("Logzio", "api.logz.io", "LOGZIO_TOKEN", 36), ("Airbrake", "api.airbrake.io", "AIRBRAKE_KEY", 32)]
    for name, host, kw, n in obsv:
        pfx("10", f"{name}_Token", name, "secrets-patterns-db & gitleaks (observability)",
            host, kw, "", n, alph=HEX if n in (32, 36) else ALNUM, sep="", sev="Medium", ctx="env",
            regex=rf"(?i){name.lower()}[\w.\-]{{0,20}}['\"\s:=]{{1,5}}([A-Za-z0-9]{{{n}}})",
            what=f"{name} 관측/알림 서비스 API 토큰({n}자).", neg="${" + kw + "}", var=kw)
    add("10", "Splunk_HEC_Token", "gitleaks & Splunk HTTP Event Collector",
        "Splunk HEC 토큰(UUID). `Authorization: Splunk {token}` 헤더로 로그를 전송한다.",
        "*.splunkcloud.com:8088", "Splunk, HEC, Authorization: Splunk",
        r"(?i)Splunk\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        "$ curl -k https://hec.splunkcloud.com:8088/services/collector \\\n    -H 'Authorization: Splunk %s'" % E.uuid("splunk"),
        "$ curl -k https://hec.splunkcloud.com:8088/services/collector \\\n    -H 'Authorization: Splunk ${SPLUNK_HEC_TOKEN}'",
        "High", ctx="raw", var="SPLUNK_HEC_TOKEN", fmt="HTTP Header",
        guide="`Splunk ` 뒤 UUID 토큰이 비밀이다. 엔드포인트 경로·`:8088` 포트는 식별자이고 `${...}` 참조는 제외한다.")
