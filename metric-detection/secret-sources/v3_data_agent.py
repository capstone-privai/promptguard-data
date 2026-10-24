"""Coding-agent runtime rows (macro category 12): the unstructured / multi-turn / runtime contexts a coding
agent meets that static regex scanners miss. populate(B) appends to B.ROWS. Each row is authored directly via
B.addrow so the positive/negative snippets carry full tool-call / terminal / AST context.
"""


def populate(B):
    E = B.E
    HEX, ALNUM, B64, B64URL, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.DIGITS
    ESC = "\x1b"
    C = B.CATS["12"][0]

    def row(sub, ref, what, files, channel, fmt, host, idents, regex, pos, neg, sev, guide):
        B.ROWS.append({
            "Macro_Category": C, "Sub_Category": sub, "Reference_Benchmark_or_Repo": ref,
            "Source_Description_KR": what, "Typical_File_Paths_or_Streams": files,
            "Agent_Acquisition_Channel": channel, "Data_Format_or_Syntax": fmt, "Asset_or_Host_Pair_Context": host,
            "Key_Identifiers_and_Indicators": idents, "Regex_or_Structural_Signature": regex,
            "Synthetic_Positive_Example_Raw": B._unique(pos, sub), "Hard_Negative_Counterpart_Example": neg,
            "Risk_Severity": sev, "SLM_Training_Guideline_KR": guide})

    # ---------- ANSI escape codes mixed into terminal output ----------
    row("ANSI_Colored_NPM_Login_Token", "Agentic terminal output (Bash_Tool_Stdout) & npm CLI",
        "npm/CLI 로그인 출력에 ANSI 색상 제어문자가 섞여, 토큰 앞뒤·중간에 `\\x1b[..m`이 끼는 경우. 정적 스캐너는 토큰이 끊겨 보여 놓친다.",
        "터미널 stdout, CI 로그", "Bash_Tool_Stdout", "ANSI Terminal Output", "registry.npmjs.org",
        "\\x1b[32m, authToken, npm notice",
        r"npm_[A-Za-z0-9]{36}",
        f"{ESC}[32m+{ESC}[0m added auth to {ESC}[1mregistry.npmjs.org{ESC}[0m\nnpm notice token "
        f"{ESC}[33mnpm_{E.d('ansi_npm').chars(36, ALNUM)}{ESC}[0m saved",
        f"{ESC}[32m+{ESC}[0m added auth to {ESC}[1mregistry.npmjs.org{ESC}[0m\nnpm notice using "
        f"{ESC}[33m${{NPM_TOKEN}}{ESC}[0m from env",
        "High", "색상 코드(`\\x1b[33m` 등)를 먼저 걷어내고 그 안의 `npm_...` 토큰을 하나의 span으로 봐야 한다. 제어문자 때문에 토큰이 "
        "나뉘어 보여도 실제 값으로 인식하도록 학습한다.")
    row("ANSI_Colored_AWS_CLI_Error", "Agentic terminal output & AWS CLI stderr",
        "AWS CLI 오류 메시지가 색상 코드와 함께 출력되며 그 안에 액세스 키가 노출되는 경우.",
        "터미널 stderr, CI 로그", "Bash_Tool_Stdout / Error_Log", "ANSI Terminal Output", "sts.amazonaws.com",
        "\\x1b[31m, InvalidClientTokenId, AKIA",
        r"(AKIA|ASIA)[A-Z0-9]{16}",
        f"{ESC}[31merror{ESC}[0m: InvalidClientTokenId for key {ESC}[1mAKIA{E.d('ansi_aws').chars(16, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')}{ESC}[0m\n  check your credentials",
        f"{ESC}[31merror{ESC}[0m: InvalidClientTokenId for key {ESC}[1mAKIAIOSFODNN7EXAMPLE{ESC}[0m\n  check your credentials",
        "High", "stderr의 색상 코드 사이에 낀 `AKIA...` 키를 복원해 탐지하되, 공식 예시 `AKIAIOSFODNN7EXAMPLE`는 제외한다.")
    row("ANSI_Vite_Env_Dump", "Agentic terminal output & Vite dev server",
        "Vite/Next 개발 서버가 환경변수를 색상과 함께 덤프할 때 `VITE_` 공개 변수와 서버 비밀이 함께 찍히는 경우.",
        "dev server stdout", "Bash_Tool_Stdout", "ANSI Terminal Output", "앱 백엔드 API",
        "\\x1b[36m, VITE_, loaded env",
        r"sk-[A-Za-z0-9]{48}",
        f"{ESC}[36mvite{ESC}[0m loaded env:\n  VITE_API_URL={ESC}[2mhttps://api.internal{ESC}[0m\n  "
        f"OPENAI_API_KEY={ESC}[33msk-{E.d('ansi_vite').chars(48, ALNUM)}{ESC}[0m",
        f"{ESC}[36mvite{ESC}[0m loaded env:\n  VITE_API_URL={ESC}[2mhttps://api.internal{ESC}[0m\n  "
        f"VITE_PUBLIC_KEY={ESC}[2mpk_live_public_safe_to_expose{ESC}[0m",
        "High", "`VITE_`/`NEXT_PUBLIC_` 접두 변수는 클라이언트에 노출되는 설계라 비밀이 아니다. 같은 덤프 안의 접두사 없는 서버 키"
        "(OPENAI_API_KEY 등)만 마스킹한다.")

    # ---------- language AST / fallback defaults / encoding ----------
    row("Python_getenv_Fallback_Default", "Language AST (Python) & CredData-style source",
        "`os.getenv(\"KEY\", \"기본값\")`의 두 번째 인자(폴백)에 실제 비밀이 박힌 경우. 환경변수가 없을 때 쓰이는 하드코딩 비밀이다.",
        "*.py", "Source_Code", "Python", "앱이 호출하는 API",
        "os.getenv, os.environ.setdefault, fallback",
        r"os\.getenv\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]{16,})['\"]\s*\)",
        f'STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_live_{E.d("py_fb").chars(30, ALNUM)}")',
        'STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")',
        "High", "`os.getenv(name, default)`에서 두 번째 인자가 핵심이다. 빈 문자열·`None`·placeholder면 안전하지만, 실제 토큰 형태면 "
        "환경변수가 비었을 때 쓰이는 비밀이므로 마스킹한다.")
    row("Python_environ_setdefault", "Language AST (Python)",
        "`os.environ.setdefault(\"KEY\", \"값\")`로 비밀을 기본 주입하는 패턴.",
        "*.py, settings.py", "Source_Code", "Python", "앱이 호출하는 API",
        "os.environ.setdefault",
        r"os\.environ\.setdefault\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]{12,})['\"]\s*\)",
        f'os.environ.setdefault("DJANGO_SECRET", "{E.d("py_sd").chars(50, ALNUM)}")',
        'os.environ.setdefault("DJANGO_SECRET", os.urandom(32).hex())',
        "High", "두 번째 인자가 리터럴 비밀이면 마스킹한다. `os.urandom(...)`처럼 런타임 생성 호출은 값이 아니므로 제외한다.")
    row("Python_bytes_fromhex_Key", "Language AST (Python) obfuscation",
        "`bytes.fromhex(\"...\")`로 hex 문자열을 키 바이트로 복원하는 난독화. hex 리터럴이 실제 키다.",
        "*.py, crypto.py", "Source_Code", "Python", "암복호화 모듈",
        "bytes.fromhex, binascii.unhexlify",
        r"bytes\.fromhex\(\s*['\"]([0-9a-fA-F]{32,})['\"]\s*\)",
        f'AES_KEY = bytes.fromhex("{E.d("py_hex").chars(64, HEX)}")',
        'AES_KEY = bytes.fromhex(os.environ["AES_KEY_HEX"])',
        "Medium", "`fromhex`의 리터럴 hex가 32자 이상이면 키일 가능성이 높다. 변수를 참조하는 인자는 제외한다. 인코딩됐다고 넘기지 말고 복원 의도를 본다.")
    row("JS_Buffer_From_Base64_Key", "Language AST (JS/TS) obfuscation",
        "`Buffer.from(\"...\", 'base64')` / `atob(\"...\")`로 base64 비밀을 런타임에 디코딩하는 패턴.",
        "*.js, *.ts", "Source_Code", "JavaScript", "앱이 호출하는 API",
        "Buffer.from, atob, base64",
        r"(?:Buffer\.from|atob)\(\s*['\"]([A-Za-z0-9+/=]{24,})['\"]",
        f'const key = Buffer.from("{E.b64url_bytes(E.d("js_b64").raw(30)).replace("-","+").replace("_","/")}", "base64").toString();',
        'const key = Buffer.from(process.env.KEY_B64, "base64").toString();',
        "Medium", "`Buffer.from(..., 'base64')`/`atob`의 리터럴 인자가 디코딩되면 비밀인 경우가 많다. `process.env.*`를 디코딩하는 코드는 제외한다.")
    row("JS_Array_Join_Obfuscated_Key", "Language AST (JS) obfuscation",
        "문자 배열을 `.join('')`로 이어 붙여 키 문자열을 숨기는 난독화.",
        "*.js, bundled output", "Source_Code", "JavaScript", "앱이 호출하는 API",
        ".join(''), String.fromCharCode",
        r"\[(?:['\"][A-Za-z0-9+/_-]['\"],?\s*){16,}\]\.join\(",
        "const t = ['s','k','-','%s'].join('');" % "','".join(E.d("js_join").chars(40, ALNUM)),
        "const parts = ['a','b','c'].join('/'); // path builder",
        "Medium", "조각난 문자 배열을 join으로 복원하면 토큰이 되는지 본다. 경로·단어를 만드는 평범한 join(음성)과 구분하도록 학습한다.")
    row("Vite_ImportMeta_Env_Fallback", "Language AST (Vite/TS)",
        "`import.meta.env.VITE_X || \"sk-...\"`처럼 OR 폴백에 실제 비밀을 둔 경우.",
        "*.ts, vite 앱", "Source_Code", "TypeScript", "앱이 호출하는 API",
        "import.meta.env, ||, fallback",
        r"import\.meta\.env\.\w+\s*\|\|\s*['\"]([^'\"]{16,})['\"]",
        f'const key = import.meta.env.VITE_OPENAI || "sk-{E.d("vite_fb").chars(48, ALNUM)}";',
        'const key = import.meta.env.VITE_OPENAI || "";',
        "High", "`||` 뒤 리터럴이 토큰 형태면 폴백 비밀이다. 빈 문자열·placeholder면 제외한다.")
    row("Java_Spring_Value_Default", "Language AST (Java/Spring) & WrongSecrets",
        "Spring `@Value(\"${api.key:기본값}\")`의 콜론 뒤 기본값에 비밀이 박힌 경우. 프로퍼티가 없으면 이 값이 주입된다.",
        "*.java", "Source_Code", "Java", "앱이 호출하는 API",
        "@Value, ${...:default}",
        r"@Value\(\s*['\"]\$\{[^:}]+:([^}]{12,})\}['\"]\s*\)",
        f'@Value("${{stripe.key:sk_live_{E.d("java_val").chars(28, ALNUM)}}}")\nprivate String stripeKey;',
        '@Value("${stripe.key:}")\nprivate String stripeKey;',
        "High", "`${프로퍼티:기본값}`에서 콜론 뒤가 기본값이다. 비어 있으면 안전하지만 토큰 형태면 코드에 박힌 폴백 비밀이다.")
    row("Kotlin_Elvis_Fallback", "Language AST (Kotlin)",
        "Kotlin `System.getenv(\"KEY\") ?: \"기본값\"`의 엘비스 연산자 뒤 기본값에 비밀이 박힌 경우.",
        "*.kt", "Source_Code", "Kotlin", "앱이 호출하는 API",
        "System.getenv, ?:",
        r"System\.getenv\([^)]+\)\s*\?:\s*\"([^\"]{12,})\"",
        f'val token = System.getenv("GH_TOKEN") ?: "ghp_{E.d("kt_fb").chars(36, ALNUM)}"',
        'val token = System.getenv("GH_TOKEN") ?: error("GH_TOKEN required")',
        "High", "`?:` 뒤 리터럴이 토큰 형태면 폴백 비밀이다. `error(...)`·`throw`로 끝나는 경우는 값이 아니므로 제외한다.")
    row("Go_Getenv_Fallback", "Language AST (Go)",
        "Go에서 `os.Getenv(\"KEY\")`가 비면 하드코딩 상수로 대체하는 패턴.",
        "*.go", "Source_Code", "Go", "앱이 호출하는 API",
        "os.Getenv, const, fallback",
        r"if\s+\w+\s*==\s*\"\"\s*\{\s*\w+\s*=\s*\"([^\"]{16,})\"",
        f'key := os.Getenv("API_KEY")\nif key == "" {{\n    key = "{E.d("go_fb").chars(40, ALNUM)}"\n}}',
        'key := os.Getenv("API_KEY")\nif key == "" {\n    log.Fatal("API_KEY required")\n}',
        "Medium", "환경변수가 비었을 때 대입하는 리터럴 상수가 비밀이다. `log.Fatal`로 끝나면 폴백 비밀이 없는 것이다.")

    # ---------- tool-call -> tool-result multi-turn trajectories ----------
    row("Docker_Inspect_Env_Secret", "Agent tool trajectory & `docker inspect`",
        "`docker inspect`의 `Config.Env` 배열에 컨테이너 환경변수로 박힌 비밀이 그대로 나오는 경우.",
        "docker inspect stdout (JSON)", "Bash_Tool_Stdout", "JSON", "컨테이너가 붙는 서비스",
        "docker inspect, Config.Env",
        r"\"[A-Z_]*(PASSWORD|SECRET|TOKEN|KEY)=([^\"]{8,})\"",
        '[Tool Call]: bash({"command":"docker inspect api | jq .[0].Config.Env"})\n[Tool Result]:\n[\n  "PATH=/usr/bin",\n  "DB_PASSWORD=%s"\n]' % E.password("docker_env", "random"),
        '[Tool Call]: bash({"command":"docker inspect api | jq .[0].Config.Env"})\n[Tool Result]:\n[\n  "PATH=/usr/bin",\n  "DB_PASSWORD=${DB_PASSWORD}"\n]',
        "High", "`Config.Env`의 `KEY=value`에서 PASSWORD/SECRET/TOKEN 변수의 값만 비밀이다. PATH·HOME 같은 값과 `${...}` 참조는 제외한다.")
    row("Helm_Get_Values_Secret", "Agent tool trajectory & `helm get values`",
        "`helm get values`가 릴리스의 values(비밀 포함)를 YAML로 덤프하는 경우.",
        "helm stdout (YAML)", "Bash_Tool_Stdout", "YAML", "Kubernetes 릴리스",
        "helm get values, USER-SUPPLIED VALUES",
        r"(?i)(password|secret|token)\s*:\s*(\S{8,})",
        'USER-SUPPLIED VALUES:\npostgresql:\n  auth:\n    password: %s' % E.password("helm", "random"),
        'USER-SUPPLIED VALUES:\npostgresql:\n  auth:\n    existingSecret: pg-credentials',
        "High", "values YAML의 password/secret 필드 값이 비밀이다. `existingSecret`처럼 Secret 이름만 가리키는 참조는 비밀이 아니다.")
    row("Terraform_State_Show_Secret", "Agent tool trajectory & `terraform state show`",
        "`terraform state show`/`terraform output`가 state에 평문 저장된 비밀을 출력하는 경우.",
        "terraform stdout, terraform.tfstate", "Bash_Tool_Stdout / File_Read", "HCL / JSON", "프로비저닝 리소스",
        "terraform state show, (sensitive value), tfstate",
        r"(password|secret|master_password)\s*=\s*\"([^\"]{8,})\"",
        '[Tool Result]:\n# aws_db_instance.main:\nresource "aws_db_instance" "main" {\n    password = "%s"\n}' % E.password("tfstate", "random"),
        '[Tool Result]:\n# aws_db_instance.main:\nresource "aws_db_instance" "main" {\n    password = (sensitive value)\n}',
        "Critical", "state에 평문으로 남은 password/secret 값이 비밀이다. `(sensitive value)`로 가려진 출력은 값이 없으니 제외한다.")
    row("Git_Log_S_Deleted_Secret", "Agent tool trajectory & `git log -S -p`",
        "`git log -S\"secret\" -p` 또는 `git stash show -p`가 과거 커밋에서 지워진 비밀을 diff로 되살려 보여주는 경우.",
        "git stdout (diff)", "Git_Diff_Patch / Bash_Tool_Stdout", "Git Diff", "과거 커밋이 쓰던 서비스",
        "git log -S, git stash show, - (removed line)",
        r"^-.*(SECRET|TOKEN|KEY|PASSWORD)\s*[:=]\s*(\S{12,})",
        '[Tool Result]:\ncommit a1b2c3d\n--- a/config.py\n+++ b/config.py\n@@\n-API_SECRET = "%s"\n+API_SECRET = os.environ["API_SECRET"]' % E.tok("", 40, ALNUM, tag="gitlog"),
        '[Tool Result]:\ncommit a1b2c3d\n--- a/config.py\n+++ b/config.py\n@@\n-API_SECRET = os.getenv("OLD")\n+API_SECRET = os.environ["API_SECRET"]',
        "High", "커밋에서 삭제됐어도(`-` 줄) diff에 남은 리터럴 비밀은 여전히 유효할 수 있어 비밀로 본다. 환경변수 참조로의 변경은 값이 아니다.")
    row("Git_Reflog_Credentials_URL", "Agent tool trajectory & `git reflog` / remote URL",
        "git remote URL이나 reflog에 `https://user:token@host` 형태로 자격증명이 박혀 노출되는 경우.",
        "git stdout, .git/config", "Bash_Tool_Stdout / File_Read", "Git Config", "git 원격 호스트",
        "git remote -v, https://x-access-token:",
        r"https://[^:/\s]+:([^@/\s]{8,})@",
        '[Tool Result]:\norigin\thttps://x-access-token:ghp_%s@github.com/org/repo.git (fetch)' % E.d("reflog").chars(36, ALNUM),
        '[Tool Result]:\norigin\thttps://github.com/org/repo.git (fetch)',
        "High", "URL의 `user:` 와 `@` 사이 토큰/비밀번호만 마스킹한다. 자격증명이 없는 평범한 원격 URL은 음성이다.")
    row("SQLite_Select_ASCII_Table", "Agent tool trajectory & sqlite3/psql CLI",
        "로컬 DB에서 `SELECT`한 결과가 아스키 표(`| id | token |`)로 출력되며 토큰 컬럼 값이 그대로 보이는 경우.",
        "db CLI stdout", "Bash_Tool_Stdout", "ASCII Table", "애플리케이션 DB",
        "SELECT, | token |, api_tokens",
        r"\|\s*([A-Za-z0-9._-]{20,})\s*\|",
        '[Tool Result]:\n+----+--------------------------------+\n| id | api_token                      |\n+----+--------------------------------+\n|  1 | %s |\n+----+--------------------------------+' % E.tok("", 30, ALNUM, tag="sqlite"),
        '[Tool Result]:\n+----+-------------+\n| id | status      |\n+----+-------------+\n|  1 | active      |\n+----+-------------+',
        "High", "아스키 표의 셀 중 token/secret/password 컬럼 값이 비밀이다. id·status 같은 일반 컬럼 값은 음성이다. 표 구분선(`+--+`)은 값이 아니다.")
    row("Redis_HGETALL_Output", "Agent tool trajectory & redis-cli",
        "`redis-cli HGETALL session:*`가 세션 토큰·비밀번호 해시를 키-값 쌍으로 쏟아내는 경우.",
        "redis-cli stdout", "Bash_Tool_Stdout", "Raw Stream", "Redis 캐시",
        "HGETALL, GET, session:",
        r"\d+\)\s+\"(access_token|token|secret)\"\n\d+\)\s+\"([^\"]{16,})\"",
        '[Tool Result]:\n1) "user_id"\n2) "42"\n3) "access_token"\n4) "%s"' % E.tok("", 40, B64URL, tag="redis"),
        '[Tool Result]:\n1) "user_id"\n2) "42"\n3) "last_seen"\n4) "2026-02-11T08:00:00Z"',
        "High", "redis 출력에서 access_token/secret 키 바로 다음 값이 비밀이다. user_id·last_seen 같은 필드 값은 음성이다.")
    row("Procfs_Environ_Null_Stream", "privesc-llm-data & `/proc/<pid>/environ`",
        "`cat /proc/<pid>/environ`은 환경변수를 널(\\x00)로 구분해 한 줄로 쏟아낸다. 그 안에 프로세스 비밀이 섞여 있다.",
        "/proc/<pid>/environ, /proc/<pid>/cmdline", "Bash_Tool_Stdout / File_Read", "Null-Delimited Stream",
        "실행 중 프로세스가 붙는 서비스", "/proc/, environ, \\x00",
        r"(PASSWORD|SECRET|TOKEN|KEY)=([^\\\s]{8,})",
        '[Tool Result]:\nPATH=/usr/bin\\x00HOME=/root\\x00DB_PASSWORD=%s\\x00SHELL=/bin/bash' % E.password("procfs", "random"),
        '[Tool Result]:\nPATH=/usr/bin\\x00HOME=/root\\x00TERM=xterm\\x00SHELL=/bin/bash',
        "High", "널 구분 스트림을 `\\x00`로 쪼갠 뒤 각 `KEY=value`에서 비밀 변수만 고른다. PATH·HOME·TERM 같은 값은 음성이다.")
    row("Shell_History_Inline_Secret", "privesc-llm-data & shell history artifacts",
        "`~/.bash_history`나 `history` 출력에 `export TOKEN=...`, `curl -u user:pass`가 그대로 남은 경우.",
        "~/.bash_history, ~/.zsh_history, ~/.psql_history", "File_Read_Tool / Bash_Tool_Stdout", "Shell History",
        "명령이 접속한 서비스", "history, export, .bash_history",
        r"export\s+[A-Z_]*(TOKEN|SECRET|KEY|PASSWORD)=(\S{12,})",
        '[Tool Result]:\n  512  cd /app\n  513  export GITHUB_TOKEN=ghp_%s\n  514  git push' % E.d("histtok").chars(36, ALNUM),
        '[Tool Result]:\n  512  cd /app\n  513  export EDITOR=vim\n  514  git push',
        "High", "history 줄 번호 뒤의 `export SECRET=값`에서 값만 비밀이다. `export EDITOR=vim` 같은 비민감 변수는 음성이다.")
    row("MCP_Config_Env_Block", "MCP config & claude_desktop_config.json / .cursor/mcp.json",
        "MCP 서버 설정의 `env` 블록에 각 서버로 주입할 API 키가 평문으로 들어가는 경우. 에이전트가 설정 파일을 읽을 때 마주친다.",
        "claude_desktop_config.json, .cursor/mcp.json, .vscode/mcp.json", "File_Read_Tool / MCP_JSON_RPC", "JSON",
        "MCP 서버가 붙는 외부 서비스", "mcpServers, env, command",
        r"\"env\"\s*:\s*\{[^}]*\"[A-Z_]+\"\s*:\s*\"([^\"]{16,})\"",
        '{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_%s" }\n    }\n  }\n}' % E.d("mcpenv").chars(36, ALNUM),
        '{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${input:github_token}" }\n    }\n  }\n}',
        "Critical", "`mcpServers.*.env`의 값이 토큰 형태면 비밀이다. `${input:...}`/`${env:...}` 참조 구문은 값이 아니므로 제외한다. "
        "command·args는 비밀이 아니다.")
    row("MCP_JSONRPC_Poisoned_Tool_Result", "MCPSecBench (arXiv:2508.13220) & MCP JSON-RPC 2.0",
        "오염된 MCP 도구가 JSON-RPC `result.content[*].text`에 비밀을 섞어 돌려주는 경우. 응답 페이로드 내부 텍스트에서 span을 찾아야 한다.",
        "MCP stdio JSON-RPC stream", "MCP_JSON_RPC", "JSON-RPC 2.0", "MCP 도구가 접근한 백엔드",
        "jsonrpc, result.content, text",
        r"\"text\"\s*:\s*\"[^\"]*(token|secret|key)=([A-Za-z0-9._-]{12,})",
        '{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"query ok: db_token=%s"}]}}' % E.tok("", 32, ALNUM, tag="mcprpc"),
        '{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"query ok: rows=1420, latency=38ms"}]}}',
        "Critical", "JSON-RPC `result.content[].text` 문자열 내부에 섞인 `token=값`을 탐지한다. 통계·상태만 든 정상 응답은 음성이다. "
        "프로토콜 필드(jsonrpc/id/type)는 비밀이 아니다.")
    row("Stack_Trace_Local_Variable_Secret", "SWE-Gym / openhands-feedback & ORM crash dump",
        "예외 트레이스백의 지역 변수 덤프나 ORM 오류에 DB URL·비밀번호가 평문으로 찍히는 경우.",
        "에러 로그, stderr", "Error_Log / Bash_Tool_Stdout", "Traceback", "크래시한 서비스의 DB",
        "Traceback, sqlalchemy.url, OperationalError",
        r"(postgresql|mysql|mongodb)://[^:/\s]+:([^@/\s]{6,})@",
        'Traceback (most recent call last):\n  ...\nsqlalchemy.exc.OperationalError: (connection failed)\n  url: postgresql://app:%s@db.internal:5432/prod' % E.password("trace", "random"),
        'Traceback (most recent call last):\n  ...\nsqlalchemy.exc.OperationalError: (connection failed)\n  url: postgresql://app:${PGPASSWORD}@db.internal:5432/prod',
        "High", "트레이스백 안의 연결 URL에서 비밀번호 부분만 마스킹한다. host·db·user는 식별자이며 `${PGPASSWORD}` 참조는 제외한다.")
    row("Jupyter_Notebook_Output_Cell", "Jupyter .ipynb output cells",
        "주피터 노트북의 출력 셀(`outputs[].text`)에 `print(os.environ)`나 API 응답으로 비밀이 저장돼 커밋되는 경우.",
        "*.ipynb", "File_Read_Tool", "JSON (ipynb)", "노트북이 호출한 API",
        "outputs, text/plain, print(os.environ)",
        r"[\'\"](AWS_SECRET_ACCESS_KEY|OPENAI_API_KEY|API_KEY)[\'\"]\s*:\s*[\'\"]([^\'\"]{16,})[\'\"]",
        '"outputs": [{"output_type":"stream","text":["{\'OPENAI_API_KEY\': \'sk-%s\'}"]}]' % E.d("ipynb").chars(48, ALNUM),
        '"outputs": [{"output_type":"stream","text":["{\'LANG\': \'en_US.UTF-8\', \'PWD\': \'/work\'}"]}]',
        "High", "노트북 output 셀에 캐시된 환경변수 덤프·API 응답에서 비밀만 고른다. LANG·PWD 같은 비민감 환경변수는 음성이다.")
    row("Frontend_SourceMap_Inlined_Env", "Frontend build sourcemaps (.js.map)",
        "번들러 소스맵(`.js.map`)의 `sourcesContent`에 빌드 시 인라인된 환경변수(서버 비밀 포함)가 남는 경우.",
        "dist/*.js.map, build/", "File_Read_Tool", "JSON (sourcemap)", "앱 백엔드 API",
        "sourcesContent, process.env, .js.map",
        r"sourcesContent.*?(SECRET|TOKEN|API_KEY)\s*=\s*\\?[\"']?([A-Za-z0-9+/_-]{16,})",
        '{"version":3,"sourcesContent":["const API_SECRET=\\"%s\\";export default API_SECRET;"]}' % E.tok("", 40, ALNUM, tag="sourcemap"),
        '{"version":3,"sourcesContent":["const API_URL=\\"https://api.internal\\";export default API_URL;"]}',
        "High", "소스맵 `sourcesContent`에 번들된 원본 코드 속 비밀을 탐지한다. API_URL 같은 비민감 상수는 음성이다. 빌드 산출물도 검사 대상임을 학습한다.")
    row("Playwright_HAR_Session_Cookie", "Playwright/Puppeteer storageState & HAR capture",
        "브라우저 자동화가 저장한 `storageState.json`/HAR에 세션 쿠키·Authorization 헤더가 그대로 기록되는 경우.",
        "storageState.json, *.har, playwright/.auth/", "File_Read_Tool", "JSON (HAR)", "로그인한 웹 서비스",
        "cookies, storageState, set-cookie, authorization",
        r"\"(name|key)\"\s*:\s*\"(session|sid|auth|token)[^\"]*\",\s*\"value\"\s*:\s*\"([^\"]{16,})\"",
        '{"cookies":[{"name":"session","value":"%s","domain":"app.internal"}]}' % E.tok("", 48, B64URL, tag="har"),
        '{"cookies":[{"name":"theme","value":"dark","domain":"app.internal"}]}',
        "High", "저장된 쿠키/헤더 중 session/auth/token 이름의 value가 비밀이다. theme·locale 같은 쿠키 값은 음성이다.")
    row("Base64_Hex_Decode_Pipeline_Stdout", "Agent tool trajectory & decode pipeline",
        "`echo <b64> | base64 -d`나 `xxd`/`openssl`로 인코딩된 비밀을 복원하는 명령의 stdout에 평문 키가 찍히는 경우.",
        "터미널 stdout", "Bash_Tool_Stdout", "Raw Stream", "복호화된 비밀이 접근하는 서비스",
        "base64 -d, xxd, openssl enc -d",
        r"(?i)(?:-----BEGIN[^-]+PRIVATE KEY-----|(?:secret|token|key)=\S{16,})",
        '[Tool Call]: bash({"command":"echo $ENC | base64 -d"})\n[Tool Result]:\nAPI_TOKEN=%s' % E.tok("", 40, ALNUM, tag="decode"),
        '[Tool Call]: bash({"command":"echo $DATA | base64 -d"})\n[Tool Result]:\nHello, build artifact v1.2.3',
        "High", "디코딩 명령의 결과물(tool result)이 비밀 형태면 마스킹한다. 평범한 텍스트를 디코딩한 결과는 음성이다. 명령(tool_input)과 결과를 함께 본다.")
    row("Cloud_CLI_Token_Print", "Agent tool trajectory & gcloud/aws/az token print",
        "`gcloud auth print-access-token`, `aws sts get-session-token`, `az account get-access-token`이 토큰을 stdout에 그대로 출력하는 경우.",
        "cloud CLI stdout", "Bash_Tool_Stdout", "Raw Stream / JSON", "클라우드 API",
        "print-access-token, get-session-token, ya29.",
        r"\bya29\.[A-Za-z0-9_-]{50,}\b|\"SecretAccessKey\"\s*:\s*\"([A-Za-z0-9/+]{40})\"",
        '[Tool Call]: bash({"command":"gcloud auth print-access-token"})\n[Tool Result]:\nya29.%s' % E.d("gcloudtok").chars(120, B64URL),
        '[Tool Call]: bash({"command":"gcloud config get-value project"})\n[Tool Result]:\nmy-project-id',
        "High", "토큰 발급 명령의 출력(`ya29....`, STS JSON의 SecretAccessKey)이 비밀이다. project-id·region 같은 비민감 출력은 음성이다.")

    # ---------- Korea public / benchmark rows ----------
    row("Korea_Public_Data_Portal_ServiceKey", "공공데이터포털(data.go.kr) 일반 인증키 & data.go.kr 표준 문서",
        "공공데이터포털 OpenAPI의 `serviceKey`. 인코딩 키는 `+`/`=`가 `%2B`/`%3D`로 든 형태이고, 디코딩 키는 원문이다. URL 쿼리에 그대로 노출된다.",
        "*.py, *.java, .env, 요청 URL", "Source_Code / Bash_Tool_Stdout", "URL Query", "apis.data.go.kr",
        "serviceKey, data.go.kr, %2B, %3D",
        r"serviceKey=([A-Za-z0-9%]{40,})",
        'url = "http://apis.data.go.kr/B551011/KorService1/areaBasedList?serviceKey=%s%%3D%%3D&numOfRows=10"' % E.d("datagokr").chars(80, ALNUM),
        'url = "http://apis.data.go.kr/B551011/KorService1/areaBasedList?serviceKey=${SERVICE_KEY}&numOfRows=10"',
        "High", "쿼리스트링의 `serviceKey=` 값이 비밀이다. 인코딩(`%2B`,`%3D` 포함)·디코딩 두 형태 모두 잡되, `${SERVICE_KEY}` 참조는 제외한다. "
        "numOfRows 같은 일반 파라미터는 음성이다.")
    row("CredData_SecretBench_Hard_Negatives", "Samsung CredData (Class F/X) & SecretBench (is_template)",
        "학술 벤치마크가 정의한 대표 오탐군: 플레이스홀더, 템플릿 변수, 문서 예시 키, 해시, 공개키, UUID. 형태는 비밀 같지만 마스킹하면 안 된다.",
        "*.md, .env.example, package-lock.json, tests/*", "All_Agent_Contexts", "Placeholders / Hashes / UUID",
        "None (Safe Context)", "EXAMPLE, YOUR_KEY, ${VAR}, sha512-, uuid",
        r"(?i)(example|placeholder|your_?api_?key|changeme|xxxx+|\$\{[^}]+\}|sha512-)",
        'AWS_KEY="AKIA%s"' % E.d("hn_real").chars(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
        'AWS_KEY="AKIAIOSFODNN7EXAMPLE"\nAPI_KEY="${OPENAI_API_KEY}"\nintegrity="sha512-2b3a4f5e6d7c8b9a=="\ntrace_id="550e8400-e29b-41d4-a716-446655440000"',
        "None (Negative)", "CredData의 F(False)·X(Template/Example) 클래스와 SecretBench의 is_template을 반영한다. `EXAMPLE`·`${VAR}`·"
        "SRI 해시·UUID는 비밀 형태여도 마스킹하지 않는다. 양성은 실제 난수 본문을 가진 키뿐이다.")

    # ---------- a handful more AST/runtime to broaden coverage ----------
    row("Dockerfile_ARG_ENV_Secret", "gitleaks & WrongSecrets (Dockerfile ARG/ENV)",
        "Dockerfile의 `ARG`/`ENV`에 비밀을 박아 빌드 이미지 레이어에 영구히 남는 경우.",
        "Dockerfile, *.dockerfile", "Source_Code / File_Read", "Dockerfile", "컨테이너가 붙는 서비스",
        "ARG, ENV, Dockerfile",
        r"(?i)(ARG|ENV)\s+[A-Z_]*(TOKEN|SECRET|KEY|PASSWORD)[= ]['\"]?(\S{12,})",
        'FROM node:20\nENV NPM_TOKEN="npm_%s"\nRUN npm ci' % E.d("dockerfile").chars(36, ALNUM),
        'FROM node:20\nARG NPM_TOKEN\nRUN --mount=type=secret,id=npm npm ci',
        "High", "`ENV KEY=값`의 리터럴이 비밀이다. 값 없는 `ARG KEY`(빌드 시 주입)나 BuildKit `--mount=type=secret`은 안전하다.")
    row("Env_Printenv_Full_Dump", "Agent tool trajectory & `env` / `printenv`",
        "에이전트가 디버깅으로 `env`를 통째로 덤프해 모든 환경변수(비밀 포함)가 한꺼번에 노출되는 경우.",
        "터미널 stdout", "Bash_Tool_Stdout / Env_Dump", "Raw Stream", "프로세스가 붙는 여러 서비스",
        "env, printenv, SHLVL",
        r"^[A-Z_]*(SECRET|TOKEN|KEY|PASSWORD)=(\S{8,})$",
        '[Tool Result]:\nSHLVL=1\nPWD=/app\nAWS_SECRET_ACCESS_KEY=%s\nTERM=xterm' % E.aws_secret("printenv"),
        '[Tool Result]:\nSHLVL=1\nPWD=/app\nLANG=C.UTF-8\nTERM=xterm',
        "High", "전체 덤프에서 SECRET/TOKEN/KEY/PASSWORD 변수 줄만 고른다. SHLVL·PWD·LANG·TERM 등 수십 개 비민감 변수가 섞여 있어도 혼동하지 않도록 학습한다.")
    row("CI_Log_Masked_Vs_Leaked", "GitHub Actions / GitLab CI logs",
        "CI 로그는 등록된 시크릿을 `***`로 가리지만, 가공·인코딩된 값이나 등록 안 된 토큰은 그대로 새어 나온다.",
        "CI 로그 stdout", "Bash_Tool_Stdout / Error_Log", "ANSI Terminal Output", "배포 대상 서비스",
        "***, echo, set-output",
        r"(?i)(deploy|token|key|secret)_[A-Za-z0-9]{20,}",
        '[Tool Result]:\n$ echo "deploying with $DEPLOY_KEY"\ndeploying with deploy_%s' % E.d("cilog").chars(32, ALNUM),
        '[Tool Result]:\n$ echo "deploying with $DEPLOY_KEY"\ndeploying with ***',
        "High", "CI가 `***`로 마스킹한 값은 이미 가려졌으니 음성이다. 반면 마스킹을 빠져나온 실제 토큰은 양성이다. `***`/`[MASKED]` 자체는 비밀이 아니다.")
