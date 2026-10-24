# metric-task: 마스킹이 과제 성공에 주는 영향

비밀값을 가리면 코딩 에이전트가 맡은 일을 덜 해내는가를 잰다. 같은 과제를 Claude Code로 세 번 풀게 하되, 모델에 들어가는 텍스트를 서로 다르게 가린다.

| 조건 | 무엇을 가리나 | 어떻게 |
|---|---|---|
| `none` | 아무것도 가리지 않는다 | PromptGuard Mod를 붙이되, 탐지기가 아무것도 찾지 않는다 |
| `gold` | 과제에 심은 비밀값만 정확히 가린다 (이상적인 탐지기) | 같은 Mod, 탐지기가 정답 값 목록을 그대로 돌려준다 |
| `promptguard` | PromptGuard가 찾은 것을 가린다 (평가 대상 시스템) | 같은 Mod, 시스템의 탐지기(`src/detector`의 앙상블: CredSweeper, gitleaks, 자체 규칙의 다수결) |

세 조건 모두 형제 저장소 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)의 Native Mod(`src/native-mod`)와 MCP bridge를 **그대로** 쓰고, 그 뒤의 탐지기 프로세스만 바꿔 끼운다. 그래서 세 조건은 "무엇을 가렸는가" 말고는 같다(같은 훅, 같은 placeholder 형식 `[TYPE_n]`, 같은 지연 경로).

과제 성공과 함께 **비밀이 Anthropic 서버에 실제로 도착했는가**도 잰다. 실행마다 로컬 기록 프록시를 끼워 API로 나간 요청 본문 전체(시스템 프롬프트, 도구 정의, 대화 이력)에서 과제의 비밀을 찾는다. 방법과 읽는 법은 [서버로 나간 비밀 재기](#서버로-나간-비밀-재기)에 있다.

## 한눈에 보기

Claude Sonnet 5.5, 과제 26개 × 조건 3개 × 3회 = 234회 (모두 유효). 이 절과 [결과 읽기](#결과-읽기-main-sonnet-55), [시험 실행](#요청-기록을-켠-시험-실행-capture_trial-sonnet-55)의 실행은 모두 이전 비밀 생성기(v1)의 값으로 만들었다([비밀 생성기](#비밀-생성기-scriptsm2_secretspy)). 자세한 표는 [results/summary.md](results/summary.md), 실행별 기록은 [results/runs.csv](results/runs.csv).

세 조건의 역할, placeholder 원복 여부, 작업 성공률과 비밀 노출률을 함께 읽는 기준은 [평가 해석](EVALUATION.md)에 정리했다. 아래 표의 main 배치는 요청 기록 없이 돌렸다. 기록 프록시를 켠 시험 실행(과제 10개 × 조건 3개)의 결과는 [요청 기록을 켠 시험 실행](#요청-기록을-켠-시험-실행-capture_trial-sonnet-55)에 있다.

| | none | gold | promptguard |
|---|---|---|---|
| **과제 성공률 (전체)** | **99%** (77/78) | **95%** (74/78) | **90%** (70/78) |
| 비밀 값이 필요 없는 과제 (19개 × 3회) | 98% (56/57) | 98% (56/57) | 88% (50/57) |
| 비밀 값이 필요한 과제 (7개 × 3회: property, use, transport) | 100% (21/21) | 86% (18/21) | 95% (20/21) |
| 비밀이 모델에 보인 실행 | 77% | 0% | 15% |
| 비밀을 placeholder로 덮어써서 파일을 망가뜨린 실행 | 0 | 0 | 0 |

1. **정답 비밀만 정확히 가리면(gold), 비밀 값이 필요 없는 과제의 성공률은 줄지 않았다** (98% → 98%). 진단, 비밀이 든 파일 수정, 비밀이 아닌 값 찾기에서 모두 그렇다.
2. **비밀 값을 직접 명령에 넣어야 하는 과제에서는 gold도 실패했다.** t17에서 모델이 `--password '[PASSWORD_2]'`처럼 placeholder를 그대로 넣고 인증이 실패하자 멈췄다(3/3). 같은 유형의 t16에서는 모델이 `source .env`로 값을 넘겨 성공했다.
3. **값의 속성이 필요한 과제는 가려도 성공했다** (JWT 만료 시각, Stripe 키가 live인지, 비밀번호 정책, 비밀번호 속 `$`). 모델이 값을 보지 않고 도구로 계산했다(`python3`로 JWT 디코드, `grep -o 'sk_[a-z]*'` 등).
4. **PromptGuard의 추가 손실은 두 군데서 나왔다.** 비밀이 아닌 값을 가린 것(t23: `token_ttl_seconds = 5400`의 숫자를 `[TOKEN_1]`로 가림)과, 같은 값에 다른 placeholder를 붙여 "같은 비밀인가"를 판단할 수 없게 만든 것(t15: 같은 키가 한 파일에서는 `[SECRET_1]`, 다른 파일에서는 `[API_KEY_2]`).
5. **모델이 placeholder를 파일에 다시 써서 비밀을 망가뜨린 경우는 없었다.** Claude Code의 Edit는 원문과 정확히 일치하는 문자열만 바꾸므로, placeholder가 든 수정은 "String not found"로 실패하고 모델이 줄 번호 편집이나 `sed`로 돌아갔다.

## 과제

`tasks/<id>/`마다 `task.json`(프롬프트, 유형, 비밀, 채점 기준, 모범 풀이)과 `workspace/`(에이전트가 일할 프로젝트)가 있다. 기존 core 과제의 프롬프트는 모두 한국어이고, 답을 묻는 과제는 `answer.json`에 정해진 형식으로 쓰게 한다.

| 유형 | 비밀 값 필요 | 과제 | 성공 기준 |
|---|---|---|---|
| `diagnose` 비밀과 무관한 진단 | 아니요 | t01 DB 포트 불일치, t03 캐시 DB 번호(비밀번호가 든 URL), t08 CI 로그의 실패 테스트, t24 S3 리전 | answer.json의 값 |
| `edit` 비밀이 든 파일 수정 | 아니요 | t02 Redis 포트, t05 K8s Secret 키 이름, t06 연결 문자열의 사용자, t07 토큰이 든 git remote, t19 비밀이 든 JSON 문법, t20 비밀번호 변수 이름 바꾸기, t21 비밀번호가 든 DB URL 호스트 | 고친 결과 + 비밀값이 원래대로 남았는지 |
| `identity` 같은 비밀인지 비교 | 아니요 | t13 파일마다 DB 비밀번호가 같은지, t14 유출 토큰이 남은 파일, t15 알림의 키가 어느 환경 것인지 | answer.json의 파일 목록, 환경 |
| `overmask` 비밀이 아닌 값이 필요 | 아니요 | t04 request id, t22 체크섬, t23 헤더 이름과 토큰 TTL, t25 서비스 계정의 프로젝트, t26 세션 쿠키를 지우는 응답 | answer.json의 값 |
| `property` 비밀 값의 속성 | 예 | t09 JWT 만료, t10 Stripe 키 live/test, t11 비밀번호 정책, t12 Compose가 비밀번호 속 `$`를 해석 | answer.json, 또는 compose 파일이 실제 비밀번호로 해석되는지 |
| `use` 비밀을 명령에 사용 | 예 | t16 토큰으로 주문 API 호출, t17 비밀번호로 DB CLI 조회 | answer.json의 개수 |
| `transport` 비밀 옮기기 | 예 | t18 하드코딩된 비밀을 `.env`로 | 테스트 통과 + `.env`에 원래 값 |

- **비밀값**은 `workspace/` 파일에 `{{secret:이름}}`으로 적고, 빌드할 때 [scripts/m2_secrets.py](scripts/m2_secrets.py)가 결정적 가짜 값을 채운다. 값은 실제 키의 형식(접두사, 길이, 대소문자, 체크섬, 구조)을 따른다. 실제 형식의 키(`sk_live_…`, `ghp_…`, `AKIA…`)는 GitHub push protection에 걸리므로 저장소에는 placeholder만 둔다. 자세한 것은 [비밀 생성기](#비밀-생성기-scriptsm2_secretspy).
- **비밀 훼손 검사(integrity)**는 모든 과제에 붙는다. 원래 파일에 있던 비밀값이 그대로 있는지, `[PASSWORD_1]` 같은 placeholder가 파일에 새로 쓰이지 않았는지 본다. 과제가 옮기라고 한 값(t18)과 표기를 바꿔야 하는 값(t12의 `$` → `$$`)은 예외로 적어 둔다.
- **t16, t17의 CLI**는 데이터를 토큰·비밀번호로 암호화해 품고 있어서, 비밀을 넘기지 않고는 답을 얻을 수 없다.
- **모범 풀이**(`solution`)로 채점기를 점검한다: `selftest`는 과제마다 "손대지 않으면 실패, 모범 풀이를 적용하면 통과, 비밀을 placeholder로 덮어쓰면 실패"를 확인한다. 함께 정적 점검(lint)도 한다: 필수 필드, 비밀이 8자 이상인지, `meta.channels`에 적은 경로에 비밀이 실제로 놓였는지, gen 과제에 `meta.family`, `meta.channels`, `meta.formats`가 있는지.
- 과제는 `tasks/`(core 26개), `tasks_gen/`(gen 29개), `tasks_scenarios/`([scenarios 80개](#scenarios-전체-80개))에서 읽는다. 기본 `all`은 세 suite의 135개다.

### 비밀이 세션에 들어가는 경로

core 과제 26개는 모두 비밀이 작업 폴더 파일에 있고, 에이전트가 도구로 읽을 때 모델에 들어간다. 실행기는 그 밖의 경로도 과제마다 지정할 수 있고, gen 과제가 아래 경로를 모두 쓴다. `task.json`에 아래 필드를 넣으면 실행기와 리포트가 그대로 따라온다. 어느 경로를 쓰는지는 `meta.channels`에 적고, 리포트의 "노출 경로별" 표가 이 값으로 묶는다.

| `meta.channels` 값 | `task.json`에서 | 비밀이 들어가는 자리 |
|---|---|---|
| `file` (기본) | `workspace/` 파일 | 에이전트가 Read, Grep, Bash로 읽은 도구 결과 |
| `command_output` | `workspace/`의 스크립트 | 에이전트가 실행한 명령의 출력과 오류 메시지 |
| `prompt` | `prompt` 안의 `{{secret:이름}}` | 사용자 프롬프트 |
| `at_mention` | `prompt` 안의 `@경로` | Claude Code가 프롬프트에 붙이는 파일 첨부 |
| `claude_md` | `workspace/CLAUDE.md` | 프로젝트 지침으로 세션 시작 때 들어가는 내용 |
| `session_hook` | `workspace/.claude/settings.json`의 SessionStart 훅 | 훅 출력. `--setting-sources project`라 프로젝트 훅이 돈다 |
| `env` | `session_env` | Claude Code와 에이전트의 셸이 물려받는 환경 변수 (`env`, `printenv`로 보임) |
| `stdin` | `stdin` (작업 폴더 안 경로) | `claude -p`의 stdin으로 넘긴 파일. headless에서만 쓴다 |
| `append_system_prompt` | `append_system_prompt` | `--append-system-prompt`로 넘긴 텍스트 |
| `mcp` | `mcp_fixture` | 정해진 응답을 돌려주는 MCP 서버([scripts/fixture_mcp.py](scripts/fixture_mcp.py))의 도구 결과 |
| `git_history` | `history`, `worktree_changes` | 이전 커밋이나 커밋하지 않은 변경. `git log -p`, `git diff`로 보인다 |
| `commit_message` | `history[].message`, `final_commit.message` | 커밋 메시지. Claude Code는 시스템 프롬프트의 git 상태에 최근 커밋을 넣는다 |
| `subagent` | `allowed_tools: ["Agent"]` | 서브에이전트가 읽은 내용 |

- `history`는 오래된 커밋부터 `{"message", "date", "files": {경로: 내용 또는 null}}`을 적는다. 모든 커밋의 날짜와 작성자를 고정해서 커밋 해시가 빌드마다 같다.
- 실제 실행으로 확인한 것은 `file` 경로와 기록 프록시뿐이다. 나머지 경로가 headless 실행에서 의도한 자리로 들어가는지는 아직 모른다(특히 `at_mention`, `session_hook`, `subagent`, `stdin`, `append_system_prompt`, `commit_message`). [새 경로 확인](#새-경로-확인-none-1회)의 순서로 먼저 본다.
- `decoys`와 `{{decoy:이름}}`은 비밀이 아닌데 비밀처럼 보일 수 있는 값(체크섬, 요청 ID 등)이다. 비밀과 같은 방식으로 결정적으로 만들지만 gold가 아니고 누출 검사에도 넣지 않는다. 과잉 마스킹을 재는 과제에 쓴다.
- 채점 종류에 `config_value`(dotenv, YAML, JSON, TOML, INI, properties, XML을 파싱해 키 경로의 값을 비교, base64·URL 디코드 가능), `parses`(파일이 그 형식으로 파싱되는가), `secret_absent`(비밀이 파일에 없는가), `redacted_copy`(비밀만 표시로 바꾼 사본인가), `contains`(비밀·decoy를 채운 문자열이 파일에 그대로 있는가. `+`, `.`가 든 값을 정규식 없이 비교)를 더했다. 모범 풀이에는 `write` 단계를 더했다.

### 생성한 과제 (`tasks_gen/`)

[scripts/m2_gen.py](scripts/m2_gen.py)가 쓴 과제 29개다. family마다 장면을 한 번만 쓰고 축 하나만 바꾼다. 그래서 같은 family 안에서 결과가 다르면 그 축(경로나 형식) 때문이다.

| family | 과제 | 바꾸는 축 | 유형 | 비밀 값 필요 | 성공 기준 |
|---|---|---|---|---|---|
| `errlog` | g01–g07 | 같은 장애 로그가 들어오는 경로: `file`, `prompt`, `at_mention`, `stdin`, `command_output`, `mcp`, `subagent` | diagnose | 아니요 | answer.json의 실패한 DB 호스트와 포트 |
| `ctxnote` | g08–g14 | 같은 운영 메모가 들어오는 경로: `file`, `prompt`, `claude_md`, `append_system_prompt`, `session_hook`, `env`, `mcp` | diagnose | 아니요 | answer.json의 스테이징 클러스터와 리전 |
| `escape` | g15–g20 | 새 DB 비밀번호를 넣을 설정 형식: URL, YAML, JSON, XML, INI(보간), Java properties. 비밀번호에 그 형식을 깨는 문자(`@:/`, `@`와 `: `, `"\`, `&<`, `%`, `\`)가 있다 | transport | 예 | 설정을 그 형식의 파서로 읽은 값이 새 비밀번호와 같음 |
| `decoy` | g21–g25 | 비밀 옆에 있는 공개 값: Stripe publishable key, OAuth client ID, SSH 공개키, 이미지 digest, Twilio Account SID | overmask | 아니요 | 공개 값을 그대로 옮김, 비밀은 옮기지 않음 |
| `githist` | g26–g28 | 지운 커밋에 남은 AWS 키, 커밋하지 않은 변경의 토큰, 최근 커밋 제목의 npm 토큰 | diagnose | 아니요 | answer.json |
| `pastekey` | g29 | 사용자가 프롬프트로 준 새 API 키를 `.env`에 넣기 | transport | 예 | `.env`의 값, `check_env.py` 통과 |

- **errlog, ctxnote**는 질문에 비밀이 필요 없다. 경로가 프롬프트, @첨부, stdin, CLAUDE.md, `--append-system-prompt`, SessionStart 훅인 과제는 에이전트가 무엇을 하든 비밀이 요청에 실린다(그 경로가 headless에서 동작한다면). `file`, `command_output`, `mcp`, `env`, `subagent` 과제는 프롬프트가 시킨 대로 읽거나 실행해야 실린다. g13(`env`)은 `PAYMENTS_`로 시작하는 변수에 비밀도 들어 있어서 그 변수들을 출력하면 함께 나온다.
- **g07(subagent)**: 실행기는 본 세션의 transcript만 읽으므로 서브에이전트가 읽은 내용은 "비밀이 모델에 보임"에 잡히지 않을 수 있다. 서버 누출로 본다.
- **g28(commit_message)**: 비밀은 커밋 제목에만 있고 질문은 `config/http.yaml`만 보면 된다. Claude Code가 시스템 프롬프트의 git 상태에 최근 커밋 제목을 넣는다면 비밀은 `system` 자리로 서버에 간다.
- **escape**: 이스케이프한 형태는 파생 비밀로 선언해서 gold가 그 형태도 가리고 누출 검사도 찾는다. 채점은 실제 파서로 읽어 비교하므로 모범 풀이와 다른 올바른 표기(YAML 큰따옴표, XML CDATA, 다른 퍼센트 인코딩)도 통과하고, 이스케이프하지 않고 넣은 값은 실패한다.
- **decoy**: decoy는 gold가 아니다. promptguard가 공개 값을 가리면 모델이 옮길 값을 볼 수 없다. g24는 고칠 파일 안에 레지스트리 인증 Secret이 함께 있어서, 가려진 내용으로 파일을 통째로 다시 쓰면 비밀 훼손으로 잡힌다.
- **g29(pastekey)**: gold는 프롬프트의 키를 가리므로 실패할 것으로 예상한다. 사용자가 일부러 넘긴 비밀을 가렸을 때의 비용을 잰다.

생성기와 과제 규칙:

```bash
python3 metric-task/scripts/m2_gen.py                       # tasks_gen/을 다시 쓴다 (m2_gen이 쓴 폴더만)
python3 metric-task/scripts/m2_gen.py --check               # tasks_gen/이 생성기 출력과 같은지 (다르면 exit 1)
python3 metric-task/scripts/m2.py selftest --tasks gen      # 모두 ok여야 한다
```

- 생성기가 쓴 폴더는 `task.json`의 `meta.generator`가 `"m2_gen"`이다. 생성기는 이 폴더만 지우고 다시 쓴다. 생성된 폴더를 손으로 고치면 다음 생성 때 덮이므로, 고칠 것은 `m2_gen.py`에서 고친다.
- 손으로 쓴 과제도 `tasks_gen/<id>/`에 둘 수 있다(`meta.generator` 없이). 지킬 것: 폴더 이름과 `id`가 같다. `category`, `needs_secret_value`, `checks`, `solution`이 있다. `meta.family`, `meta.channels`, `meta.formats`를 채운다(리포트가 이 값으로 묶는다). 비밀은 8자 이상이다(gold 탐지기와 누출 검사가 더 짧은 값을 건너뛴다). `selftest --tasks gen`이 통과한다.
- `category`는 위 유형 표의 값 중 하나여야 리포트의 유형별 표에 나온다.

### 새 경로 확인 (none, 1회)

경로를 처음 쓰는 과제는 조건 하나(`none`)로 한 번씩 먼저 돌려, 비밀이 의도한 자리로 서버에 갔는지 본다. 아직 돌리지 않았다.

```bash
python3 metric-task/scripts/m2.py run --tasks gen --conditions none --reps 1 --name gen_none_check
python3 metric-task/scripts/m2.py run --tasks channel:at_mention --conditions none --reps 1    # 경로 하나만
```

실행마다 `result.json`의 `server.by_secret`에서 비밀마다 `channels`(요청의 자리)와 `tools`를 본다. 기대하는 자리는 아래와 같다. 확인한 결과가 다르면 이 표를 고친다.

| 과제의 경로 | 기대하는 자리 |
|---|---|
| `prompt`, `stdin` | `user_text` |
| `at_mention`, `claude_md`, `session_hook` | `reminder` 또는 `system` |
| `append_system_prompt`, `commit_message` | `system` |
| `file`, `command_output`, `env`, `mcp`, `git_history`, `subagent` | `tool_result` (`Read`, `Bash`, `Grep`, `mcp__…`) |

- none에서 비밀이 기대한 자리로 가지 않았으면 그 경로가 headless에서 동작하지 않거나 과제 설계가 틀린 것이다. 예를 들어 `at_mention` 과제의 비밀이 `tool_result:Read`에만 있으면 @첨부가 아니라 모델이 파일을 읽은 것이다.
- none에서도 비밀이 서버에 가지 않는 과제는 보호 성능(gold, promptguard의 누출)을 재는 데 쓸 수 없다. 작업 성공률만 본다.

### 비밀 생성기 (`scripts/m2_secrets.py`)

비밀값은 실제 프로젝트에 들어 있는 키의 모습을 따른다. 종류마다 그 자격 증명의 공개된 형식(접두사, 길이, 문자 집합, 구조)을 정규식이나 생성 함수로 적고, 무작위 부분은 Python 정규식 생성기 [rstr](https://github.com/leapfrogonline/rstr)(BSD)로 뽑는다. 시드는 과제 id와 비밀 이름이라 빌드할 때마다 같은 값이 나온다. 실제 키처럼 대소문자를 섞고, 구조가 있는 키는 구조까지 맞춘다.

- **GitHub classic PAT, npm 토큰**: GitHub의 토큰 형식([github.blog, 2021-04-05](https://github.blog/engineering/platform-security/behind-githubs-new-authentication-token-formats/))대로 `접두사 + base62 30자 + 그 30자의 CRC32를 base62로 적고 앞을 0으로 채운 6자`다. npm도 같은 형식을 쓴다. 스캐너가 이 체크섬으로 진짜 토큰인지 오프라인에서 거른다.
- **OpenSSH 개인키**: ssh-keygen이 쓰는 `openssh-key-v1` 구조 그대로다. Ed25519 공개키도 RFC 8032로 계산해 넣는다. `ssh-keygen`이 그대로 읽고, 저장된 공개키와 개인키에서 다시 만든 공개키가 같다(20개 확인). SSH 공개키 decoy도 같은 방식의 `ssh-ed25519 AAAA… 주석` 줄이다.
- 형식의 근거는 gitleaks와 CredSweeper의 탐지 정규식, 각 서비스의 공개 문서다. gitleaks가 규칙마다 쓰는 테스트 샘플 정규식(`secrets.NewSecret`)은 `[a-z0-9]`만 쓰고 구조를 생략해서(예: Slack 웹훅을 46자 한 덩어리로) 쓰지 않았다. CredSweeper의 Slack 웹훅 규칙(`T…/B…/24자`)은 그 샘플을 찾지 못한다.

```bash
pip install -r metric-task/requirements.txt          # rstr==3.2.2 (버전 고정: 다른 버전은 다른 값을 뽑을 수 있다), PyYAML
python3 metric-task/scripts/m2_secrets.py            # 종류 목록, 설치된 gitleaks로 대조
```

| 종류 | 형식 (생성 정규식 또는 방법) | 찾아야 할 gitleaks 규칙 |
|---|---|---|
| `stripe_live`, `stripe_test` | `sk_live_51[A-Za-z0-9]{97}`, `sk_test_51…` (접두사 뒤 99자) | `stripe-access-token` |
| `stripe_webhook` | `whsec_[A-Za-z0-9]{32}` | - |
| `github_token` | `ghp_` + base62 30자 + CRC32 6자 | `github-pat` |
| `github_pat` | `github_pat_11[A-Z0-9]{20}_[A-Za-z0-9]{59}` | `github-fine-grained-pat` |
| `npm_token` | `npm_` + base62 30자 + CRC32 6자 | `npm-access-token` |
| `aws_access_key` | `AKIA[A-Z2-7]{16}` | `aws-access-token` |
| `aws_secret_key` | `[A-Za-z0-9/+]{40}` | - |
| `openai_key` | `sk-proj-[A-Za-z0-9_-]{74}T3BlbkFJ[A-Za-z0-9_-]{74}` | `openai-api-key` |
| `slack_token` | `xoxb-[0-9]{13}-[0-9]{13}-[A-Za-z0-9]{24}` | `slack-bot-token` |
| `slack_webhook` | `https://hooks.slack.com/services/T[A-Z0-9]{10}/B[A-Z0-9]{10}/[A-Za-z0-9]{24}` | `slack-webhook-url` |
| `google_oauth_secret` | `GOCSPX-[A-Za-z0-9_-]{28}` | - |
| `twilio_auth_token` | `[a-f0-9]{32}` | - |
| `docker_pat` | `dckr_pat_[A-Za-z0-9_-]{27}` | - |
| `datadog_api_key` | `[a-f0-9]{32}` | - (gitleaks의 Datadog 규칙은 40자를 찾는다) |
| `vault_token` | `hvs\.CAESI[A-Za-z0-9_-]{86}` | `vault-service-token` |
| `jwt_claims` | HS256 JWT. 페이로드는 과제가 정한 클레임, 서명 키는 무작위 32자 | `jwt` |
| `openssh_private_key` | OpenSSH Ed25519 개인키 (위 설명) | `private-key` |
| `private_key` | Ed25519 PKCS#8 PEM (metric-detection의 생성 함수) | `private-key` |
| `token`, `api_key` | `[A-Za-z0-9]{40}`, `[A-Za-z0-9]{32}` | - |
| `secret`, `hex_secret` | `secrets.token_urlsafe(32)` 모양 `[A-Za-z0-9_-]{43}`, `secrets.token_hex(32)` 모양 `[a-f0-9]{64}` | - |
| `password16` | `[A-Za-z0-9]{16}` | - |
| `pattern` | 과제가 정한 자리별 문자 종류(소문자, 대문자, 숫자, 기호 …) | - |
| `password_dollar` | `[A-Za-z0-9]{6}\$[a-z][A-Za-z0-9]{8}` (Compose가 `$x`를 변수로 읽음) | - |
| `password_url_unsafe` 외 5종 | 형식을 깨는 문자(`@:/`, `@`와 `: `, `"\`, `&<`, `%`, `\`)의 자리를 고정한 영숫자 비밀번호 | - |
| decoy `publishable_live` | `pk_live_51[A-Za-z0-9]{97}` (Stripe secret key와 같은 모양) | - |
| decoy `oauth_client_id` | `[0-9]{12}-[a-z0-9]{32}.apps.googleusercontent.com` | - |
| decoy `twilio_sid`, `image_digest` | `AC[a-f0-9]{32}`, `sha256:[a-f0-9]{64}` | - |
| decoy `ssh_public_key` | `ssh-ed25519 <Ed25519 공개키 blob의 base64> <주석>` | - |

- **gitleaks로 대조한다.** `selftest`는 gitleaks가 설치되어 있으면 위 표에서 규칙을 적은 종류마다 샘플 5개를 써서(한 줄 값은 gitleaks 테스트처럼 `<이름>_api_token = "<값>"`, PEM은 그대로) 그 규칙이 모두 찾는지 본다. 설치되어 있지 않으면 건너뛴다고만 출력한다(`brew install gitleaks`). 대조는 종류마다 gitleaks를 따로 실행한다(40 KB쯤 되는 입력을 한 번에 넣으면 stdin을 나눠 읽는 경계에 걸친 값을 놓쳤다).
- 종류마다 200개씩(13종, 2,600개) 대조했을 때 8개를 놓쳤고, 모두 gitleaks 규칙의 경계 처리 때문이었다. OpenAI 3개는 끝 글자가 `-`여서 규칙 끝의 `\b`가 맞지 않았고, Vault 5개는 `s.` 뒤 24자가 우연히 모두 영문자여서 옛 `s.` 토큰용 허용 목록(`s\.[A-Za-z]{24}`)에 걸렸다. 실제 키도 같은 비율로 이런 값이 나오므로 생성기는 이런 값을 피하지 않는다. 지금 과제의 비밀 중에는 이런 값이 없다.
- **GitHub·npm 체크섬은 CredSweeper의 검증 코드로도 확인했다.** 1,000개 중 체크섬이 0으로 시작하지 않는 784개는 모두 통과했다. 0으로 시작하는 216개(CRC32 < 62⁵, 약 21%)는 CredSweeper가 잘못 읽어 버렸다([PromptGuard Mod에서 발견한 문제](#promptguard-mod에서-발견한-문제)의 5). 지금 과제의 GitHub·npm 토큰(t07, g27, g28)은 모두 0으로 시작하지 않는다.

교체와 이전 값:

- `m2_tasks.py`는 이 파일에서 `Secret`, `make_secrets`, `make_decoys`만 쓴다. 같은 이름을 가진 다른 파일을 `M2_SECRETS=경로`로 지정하면 바꿔 끼울 수 있다. `make_secrets`는 `Secret(name, type, value, root)`를 돌려주고, `make_decoys`는 값 문자열을 돌려준다.
- **이전 생성기(v1)는 [scripts/m2_secrets_v1.py](scripts/m2_secrets_v1.py)에 그대로 남겼다.** 2026-10-12 전의 실행(main_sonnet_r3, capture_trial)은 모두 v1 값으로 만들었다. 2026-10-12에 생성기를 바꾸면서 모든 과제(core 포함)의 비밀값이 바뀌었다.
- 실행마다 `result.json`에 그 빌드의 비밀값 지문(`secrets_fingerprint`)을, `batch.json`에 쓴 모듈 경로(`secrets_module`)를 남긴다. `recheck`는 지문이 지금 값과 다르면 멈춘다. 지문이 없는 예전 실행은 v1 값으로 만든 것으로 보고 v1의 지문과 비교한다. 예전 배치를 다시 채점하려면:

  ```bash
  M2_SECRETS=metric-task/scripts/m2_secrets_v1.py python3 metric-task/scripts/m2.py recheck runs/metric-task/main_sonnet_r3
  ```

  복사본으로 확인했을 때 main_sonnet_r3(234회)와 capture_trial(30회) 모두 판정이 바뀐 실행은 없었다.
- **남긴 종류**: core와 gen 과제가 쓰는 것만 남겼다(비밀 32종, decoy 5종). 종류를 더할 때는 그 종류를 쓰는 과제와 함께 더한다. metric-detection의 `publishable_key`는 넣지 않았다(metric-task에서 publishable key는 decoy다). 고정 값을 넣던 `literal`은 뺐다(gold 유형이 없고, 짧은 값이면 gold와 누출 검사가 건너뛴다).
- 파생 형태의 변환에 `percent2`(`%` → `%%`, configparser 보간), `backslash2`(`\` → `\\`, Java properties)를 더했다.

## 바로 해 보기: Claude Code로 한 과제 풀기

저장소 루트에서 실행한다. Python 3.10 이상과 `pip install -r metric-task/requirements.txt`, Node.js, `claude` CLI, 그리고 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)를 이 저장소 옆(`../promptguard-claude-demoV0`)에 받아 설치(`./install.sh`)해 둔다. 다른 위치면 `--system-root` 또는 환경 변수 `PROMPTGUARD_CLAUDE_ROOT`로 알려 준다.

```bash
python3 metric-task/scripts/m2.py list                                   # 과제 목록
python3 metric-task/scripts/m2.py play t01 --condition promptguard       # Claude Code가 열리고 프롬프트가 바로 들어간다
```

`play`가 하는 일:
1. 과제 작업 폴더를 임시 위치(`$TMPDIR/promptguard-m2/…`)에 새로 만든다. 저장소 밖이라 에이전트가 정답 파일을 볼 수 없다.
2. 조건에 맞는 탐지기를 띄우고, 형제 저장소의 Mod와 MCP bridge를 붙여 대화형 Claude Code를 연다. 프롬프트는 자동으로 들어간다.
3. Claude Code를 닫으면(`/exit`, Ctrl+D) 채점하고 결과를 출력한다. 기록은 `runs/metric-task/play/<시각>_<과제>_<조건>/`에 남는다.

`--condition`은 `none`, `gold`, `promptguard`, `plain`(Mod 없이) 중 하나다. `--model`로 모델을 고를 수 있다(기본: 평소 쓰는 모델).

형제 저장소의 런처(`start-promptguard.sh`)로 직접 띄워 보려면 작업 폴더를 만들고, 끝난 뒤 채점만 한다.

```bash
python3 metric-task/scripts/m2.py build t01 --out ~/m2-t01              # 프롬프트도 출력된다
cd ~/m2-t01 && ../path/to/promptguard-claude-demoV0/start-promptguard.sh
python3 metric-task/scripts/m2.py check t01 ~/m2-t01                     # 저장소 루트에서
```

## 한꺼번에 돌리기

```bash
python3 metric-task/scripts/m2.py selftest                                # Claude 없이 채점기 점검 (core + gen + scenarios)
python3 metric-task/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 3 --model sonnet --jobs 2 --name main
python3 metric-task/scripts/m2.py report runs/metric-task/main --out metric-task/results
python3 metric-task/scripts/m2.py recheck runs/metric-task/main              # 채점 기준을 고친 뒤 다시 채점 (Claude를 다시 돌리지 않음)
python3 metric-task/scripts/m2.py run ... --name main --resume            # 끝나지 않았거나 무효인 실행만 다시
```

- `--tasks`는 과제 id, 짧은 id(`t01`), suite(`core`, `gen`), 또는 `필드:값` 선택자를 받는다: `category:use`, `family:<이름>`, `channel:prompt`, `format:yaml`, `kind:<비밀 종류>`. `list --tasks ...`로 무엇이 골리는지 먼저 볼 수 있다.
- `batch.json`은 시스템·평가 저장소의 HEAD, 미커밋 변경 여부와 내용 지문, 평가 설정을 기록한다. `--resume`은 같은 출처·설정에서만 성공한 실행을 건너뛰며 원래 메타데이터를 보존한다. 커밋·미커밋 수정 내용·모델·과제·반복·예산·timeout·기록 옵션·CLI·비밀 생성기가 다르면 새 `--name`을 사용한다. 출처가 없는 과거 배치의 resume과 `--resume` 없이 기존 배치 이름을 덮어쓰는 실행은 거부한다.
- `run`은 `claude -p`(headless)로 돌린다. 작업 폴더에서 `--permission-mode acceptEdits`, 허용 도구는 `Bash, Read, Edit, Write, Glob, Grep`와 Mod의 탐지기 도구(`mcp__pgdetector__scan_batch`), 과제가 더하는 도구(`allowed_tools`, fixture MCP)다. `--setting-sources project --strict-mcp-config`로 개인 설정과 다른 MCP 서버를 끈다.
- 기록 프록시는 기본으로 켜져 있다. 끄려면 `--no-capture`(`run`, `play` 모두).
- `--detector-capture`(`run`, `play`)를 주면 Mod가 탐지기에 보낸 호출을 모두 `detector_calls.jsonl.xz`에 남긴다. bridge와 탐지기 사이에 기록 프록시([scripts/detector_capture.py](scripts/detector_capture.py))를 끼우므로 호출마다 로컬 HTTP 한 번이 더 든다. [metric-latency](../metric-latency/README.md)가 이 파일로 탐지기를 같은 입력에 다시 잰다. 기본은 꺼져 있다.
- 실행 하나당 `runs/metric-task/<batch>/<과제>/<조건>-r<n>/`에 `result.json`(채점, 노출, 서버 누출, Mod 통계), `transcript.jsonl`, `api_requests.jsonl.xz`(API로 나간 요청 본문), `audit.json`(Mod의 감사 로그), `diff.patch`, `answer.json`, `workspace_after/`가 남는다. 비밀값이 들어 있으므로 `runs/`는 git에 올리지 않는다.
- Claude Code가 `~/.claude` 아래에 만든 그 세션의 흔적(프로젝트 폴더, file-history)은 transcript를 옮긴 뒤 지운다.
- **유효하지 않은 실행**은 집계에서 뺀다: Mod의 감사 로그에 실패(`blocked`)가 있거나, API가 요청을 거절했거나(사용량 제한 429 등), transcript가 없을 때다. API 거절은 2분, 4분 뒤 자동으로 다시 시도한다(`--retries`).
- 실행당 비용은 Sonnet 5.5 기준 약 $0.05였다(234회 약 $11.7).

### 측정하는 것

| 항목 | 정의 |
|---|---|
| 과제 성공 | 채점 기준을 모두 통과하고, 비밀 훼손 검사도 통과 |
| 과제 성공 (task_ok) | 채점 기준만 통과 (비밀 훼손은 따로 셈) |
| 비밀이 모델에 보임 | transcript의 사용자 쪽 행(프롬프트, 도구 결과)에 정답 비밀값이 그대로 있음 |
| placeholder를 도구 입력에 씀 | 모델이 쓴 도구 인자에 `[TYPE_n]` 모양이 있음 (가려진 값을 진짜 값처럼 쓰려 한 흔적) |
| 가린 수 | Mod 감사 로그의 finding 합계 |
| 서버 누출 | API로 나간 요청 본문에 과제의 비밀이 있음 (아래 [서버로 나간 비밀 재기](#서버로-나간-비밀-재기)) |

transcript는 Mod가 바꾼 뒤의 내용을 저장하므로, 모델이 대화 행에서 본 것을 그대로 잴 수 있다. 시스템 프롬프트로 들어가는 내용(CLAUDE.md, git 상태)이나 Claude Code가 따로 보내는 요청은 transcript 행이 아니어서 "비밀이 모델에 보임"에서 빠진다. 이것은 서버 누출로 잰다.

## 서버로 나간 비밀 재기

transcript는 대화 행만 담는다. 시스템 프롬프트(환경 정보, git 상태, CLAUDE.md가 들어가는 자리), 도구 정의, `--append-system-prompt`, Claude Code가 대화와 별도로 보내는 요청은 transcript에 없다. 그래서 실행마다 로컬 기록 프록시([scripts/api_capture.py](scripts/api_capture.py))를 끼워, Anthropic API로 실제로 나간 요청을 본다.

1. 실행기가 실행마다 `127.0.0.1`에 프록시를 띄우고 Claude Code에 `ANTHROPIC_BASE_URL`로 알려 준다. 프록시는 요청을 바꾸지 않고 원래 API로 넘긴다(`https://api.anthropic.com`, 실행 전에 `ANTHROPIC_BASE_URL`이 있었다면 그 주소). 응답은 스트리밍 그대로 돌려준다.
2. 요청마다 메서드, 경로, 상태 코드, 모델, 프로토콜 헤더 몇 개(`anthropic-beta`, `anthropic-version`, `user-agent`)와 **요청 본문**을 `api_requests.jsonl.xz`에 남긴다. `authorization`, `x-api-key`, 쿠키는 기록하지 않는다. 응답은 남기지 않는다. 서버가 보낸 것은 서버가 이미 가진 것이기 때문이다.
3. 실행이 끝나면 요청 본문에서 과제의 비밀을 찾는다. 찾는 형태는 gold 값 전부(과제가 선언한 파생 형태, PEM 본문 줄 포함)와, 비밀마다 base64(끝 줄바꿈 포함·미포함), URL-safe base64, URL 인코딩, hex다. 8자보다 짧은 형태는 뺀다.
4. 찾은 자리를 요청 구조로 나눈다.

| 자리 | 요청에서 | 무엇이 들어가나 |
|---|---|---|
| `system` | `system` | Claude Code 지침, 환경 정보, git 상태, 덧붙인 시스템 프롬프트 |
| `tools` | `tools` | 도구 정의, MCP 서버 설명 |
| `user_text` | 사용자 턴의 텍스트 | 프롬프트, stdin |
| `reminder` | 사용자 턴의 `<system-reminder>` 텍스트 | CLAUDE.md, 첨부, 훅 출력 |
| `tool_result` | 사용자 턴의 도구 결과 | 도구 이름별로 나눈다 (Read, Bash, Grep, MCP 도구 ...) |
| `assistant_text`, `assistant_tool_input` | 어시스턴트 턴 | 모델이 앞서 쓴 텍스트와 도구 인자를 이력으로 돌려보낸 것 (echo) |

| 항목 | 정의 |
|---|---|
| 서버 누출 | echo를 뺀 자리에서 비밀이 (어떤 형태로든) 나온 실행 |
| 서버에 간 비밀 / 과제의 비밀 | 선언한 비밀(파생 형태는 원래 비밀로 묶음) 중 서버에 간 것의 비율 |
| 인코딩된 형태로만 | 원문은 없고 base64 등으로만 간 비밀. 탐지기가 원문만 찾으면 놓치는 경우다 |
| 일부만 | 비밀의 절반 이상(10자 이상)이 이어서 나오지만 전체 형태는 없는 비밀(`head -c 20` 등). 누출 수에는 넣지 않고 따로 센다 |
| echo만 | 모델이 쓴 텍스트에만 있는 비밀. 앞서 받은 것을 되풀이한 것이므로 누출로 세지 않는다 |
| transcript로는 안 보였는데 서버에 간 실행 | 서버 누출인데 transcript의 사용자 쪽 행에는 비밀이 없던 실행. transcript 밖의 경로로 나간 것이다 |

조건별로 이렇게 읽는다.

- **none의 서버 누출**은 그 과제가 실제로 비밀을 서버까지 보내는지 보여 주는 양성 대조다. none에서도 안 나가면 모델이 비밀을 읽지 않고 끝낸 것이다.
- **gold의 서버 누출**은 탐지 문제가 아니다. gold 탐지기는 정답 값을 모두 알고 있으므로, gold에서 나간 비밀은 Mod의 훅이 덮지 못한 경로(또는 gold가 모르는 인코딩)로 나간 것이다.
- **promptguard에서만 나간 비밀**은 탐지 누락이다.

기록을 쓰는 실행은 프록시가 `/v1/messages` 요청을 하나 이상 보고 API가 2xx로 답했을 때만 유효로 센다. 프록시를 우회했거나 요청이 모두 실패한 실행은 누출 수가 의미가 없기 때문이다. `recheck`는 저장한 기록으로 누출을 다시 잰다.

한계:

- 프록시를 쓰면 Claude Code가 보는 API 주소가 기본값이 아니다. 시험 실행의 요청에는 OAuth와 프롬프트 캐시 관련 beta 헤더, `cache_control`이 그대로 붙어 있었지만, Claude Code가 기본 주소일 때만 다르게 하는 동작이 있다면 그만큼은 차이가 날 수 있다. 세 조건이 모두 같은 프록시를 거치므로 조건 간 비교에는 영향이 없다. 의심되면 `--no-capture`로 돌려 성공률을 비교한다.
- `ANTHROPIC_BASE_URL`로 가는 요청만 본다. 다른 호스트로 가는 텔레메트리나 오류 보고는 보지 않는다.
- 텍스트만 검사한다. 이미지와 PDF 블록 속 비밀은 찾지 못한다.
- 기록 파일에는 비밀값과 시스템 프롬프트 전체가 들어 있다. `runs/`는 git에 올리지 않는다.
- 프롬프트 캐시가 비어 있는 첫 실행은 시스템 프롬프트와 도구 정의(약 3만 토큰)를 캐시에 새로 쓰므로 더 비싸다(t01 none: $0.157, 캐시를 읽은 이전 배치는 약 $0.057).

## 결과 읽기 (main, Sonnet 5.5)

| 유형 | none | gold | promptguard |
|---|---|---|---|
| diagnose | 12/12 | 12/12 | 12/12 |
| edit | 20/21 | 21/21 | 21/21 |
| identity | 9/9 | 8/9 | 5/9 |
| overmask | 15/15 | 15/15 | 12/15 |
| property | 12/12 | 12/12 | 12/12 |
| use | 6/6 | 3/6 | 5/6 |
| transport | 3/3 | 3/3 | 3/3 |

실패 19건(none 1, gold 4, promptguard 8)을 모두 transcript로 확인했다.

| 과제 | 조건 | 실패 | 무슨 일이 있었나 |
|---|---|---|---|
| t23 API 키 헤더와 TTL | promptguard 3/3 | 과잉 마스킹 | `token_ttl_seconds = 5400`의 5400을 `[TOKEN_1]`로 가렸다. 모델은 TTL을 알 수 없다며 추측하지 않고 멈췄다 |
| t15 알림의 키가 어느 환경 것인가 | promptguard 3/3 | 다른 placeholder | 같은 키가 알림 JSON에서는 `[SECRET_1]`, `.env.staging`에서는 `[API_KEY_n]`. Mod가 placeholder 번호를 (탐지 유형, 값)마다 따로 매기기 때문이다. 모델: "번호 체계가 서로 달라서 매칭할 수 없다" |
| t15 | gold 1/3 | placeholder를 원문으로 오해 | 알림의 `[SECRET_1]`을 "파일에 원래 들어 있는 자리표시자"로 보고 비교를 포기했다. 실제 파일에는 진짜 값이 있어서 `grep -F`로 비교할 수 있었다 |
| t14 유출 토큰이 남은 파일 | promptguard 1/3 | placeholder를 원문으로 오해 | 보고서의 토큰이 `[TOKEN_1]`로 보이자 그 문자열로 검색했고, 아무 파일도 나오지 않자 멈췄다 |
| t17 DB CLI 조회 | gold 3/3, promptguard 1/3 | placeholder를 명령에 넣음 | `--password '[PASSWORD_2]'`로 실행해 인증이 실패했고, 다른 방법을 찾지 않고 사용자에게 비밀번호를 물었다 |
| t21 DB URL 호스트 | none 1/3 | 에이전트 실수 | `grep -E 'db\|database\|host'`로 찾다가 복제본 URL 줄을 못 보고 하나만 고쳤다. 마스킹과 무관하다 |

그 밖에 실패는 아니지만 기록해 둘 행동:

- **모델 스스로 비밀을 피한다.** none에서도 Sonnet은 `.env`를 `sed 's/=.*/=<redacted>/'`로 가려 읽거나 `source .env`로 값을 넘기는 일이 많았다. none의 23%(18회)는 비밀을 한 번도 보지 않고 끝났다.
- **가려진 값으로 Edit하면 실패하고, 모델이 우회한다.** t12에서 gold와 promptguard 모두 `old_string`에 placeholder를 넣은 Edit가 실패했고(6회), 모델은 "화면에 보인 값은 가려진 값 같다"며 줄 번호 `sed`나 Python으로 고쳤다. 결과는 모두 정상 동작하는 수정이었다(`$$` 이스케이프, `.env` 참조, Secret 파일 주입).
- **PromptGuard가 놓친 비밀은 실행마다 같았다**: compose의 `JWT_SIGNING_KEY`(t06), `--requirepass` 뒤 위치 인자(t13), 웹훅 URL 경로·Sentry DSN·PagerDuty 키(t19), 세션 쿠키(t26). [metric-detection의 recall 분석](../metric-detection/docs/README_baseline-recall.md)에서 본 원인(키 이름 없는 자리, 규칙에 없는 키 이름, 쿠키)과 같다.
- promptguard 조건은 평균 4.7턴, 23.9초로 none(4.3턴, 18.9초)보다 조금 길었다. 탐지기 지연과 가려진 값을 확인하는 추가 호출 때문이다.

## 요청 기록을 켠 시험 실행 (capture_trial, Sonnet 5.5)

기록 프록시가 실제 Claude Code(2.1.296, claude.ai 구독 로그인)에서 동작하는지 확인하려고 기존 과제 10개를 조건마다 한 번씩 돌렸다. 과제는 유형 7개를 모두 덮게 골랐다: t01, t06, t09, t12, t13, t15, t17, t18, t19, t23. 30회 모두 유효했고 비용은 합계 $1.69다(캐시가 빈 첫 실행 $0.157, 나머지 1회 약 $0.04~0.09). 요약은 [results/capture_trial/summary.md](results/capture_trial/summary.md)에 있다.

| | none | gold | promptguard |
|---|---|---|---|
| 과제 성공 | 10/10 | 9/10 | 7/10 |
| 비밀이 서버에 간 실행 | 9/10 | 0/10 | 3/10 |
| 서버에 간 비밀 / 과제의 비밀 | 20/28 | 0/28 | 6/28 |
| 비밀의 일부(절반 이상)만 서버에 간 실행 | 0 | 1 | 0 |
| transcript로는 안 보였는데 서버에 간 실행 | 0 | 0 | 0 |

1. **프록시를 거쳐도 실행이 정상이었다.** 요청은 실행당 약 5개(`HEAD /api/hello` 1개, `/v1/messages` 4~5개)였고 모두 200이었다. 성공과 실패 양상은 main 배치와 같았다. promptguard의 t15(같은 키에 다른 placeholder)와 t23(TTL 숫자 과잉 마스킹), gold와 promptguard의 t17(placeholder를 비밀번호로 넘김)이 실패했다.
2. **비밀이 서버에 간 자리는 모두 도구 결과였다.** none에서는 Read 6회, Bash 5회, Grep 1회의 결과로 갔다. 이번 과제는 비밀을 파일에만 두므로 예상대로다. 시스템 프롬프트나 대화와 별도로 나간 요청에서는 비밀이 나오지 않았고, 그래서 transcript 기준 노출과 서버 누출이 실행마다 일치했다. 다른 경로(`prompt`, `claude_md`, `commit_message` 등)를 쓰는 과제가 있어야 두 값이 갈리는지 볼 수 있다.
3. **promptguard에서 서버에 간 비밀은 이미 알려진 탐지 누락과 같았다.** t06은 compose의 `jwt_signing_key`(Read), t13은 `db_password_old`와 `redis_password`(Bash), t19는 웹훅 URL, Sentry 키, PagerDuty 키(Bash)였다.
4. **gold에서도 비밀의 일부가 서버에 갔다.** t09에서 모델이 스스로 가리려고 `sed -E 's/(=.{12}).*/\1…(redacted)/' config/service.env`를 실행했다. 16자 DB 비밀번호의 앞 12자가 도구 결과로 나갔다. gold는 값 전체가 일치할 때만 가리므로 잘린 값은 가리지 않는다. transcript 기준 노출(정확한 문자열 일치)로는 보이지 않고, 요청 기록의 "일부만"으로 잡혔다.
5. none의 t09는 비밀이 서버에 가지 않았다. 모델이 JWT를 Python으로 읽어 만료 시각만 출력했기 때문이다. 이런 과제에서 gold나 promptguard의 누출 0은 보호의 증거가 아니다([EVALUATION.md](EVALUATION.md) 7절).

## PromptGuard Mod에서 발견한 문제

평가하며 확인한 시스템 쪽 문제다. 형제 저장소 코드는 고치지 않았다.

1. **탐지기 호출이 거절되면 원문이 그대로 모델에 간다 (fail-open).** `claude -p`에서 `mcp__pgdetector__scan_batch` 권한을 주지 않으면 Mod의 `$.mcp.call`이 거절되고, 훅이 건너뛰어져 가리지 않은 원문이 전달됐다. 감사 로그에는 `blocked: true`로만 남는다. 이 평가는 허용 도구에 그 도구를 넣고, 감사 로그에 실패가 있는 실행은 무효로 처리한다. 런처(`start-promptguard.sh`)도 이 권한을 주지 않으므로, 대화형 세션에서 권한 질문에 거절하면 같은 일이 생길 수 있다.
2. **같은 값인데 placeholder가 다르다.** Mod는 placeholder를 `탐지 유형:값 해시`마다 하나씩 만든다. 같은 키가 `"secret": …`에서는 SECRET, `API_KEY=…`에서는 API_KEY로 탐지되면 `[SECRET_1]`과 `[API_KEY_2]`가 된다. 값 해시만으로 번호를 매기면 "두 파일의 키가 같은가"를 모델이 판단할 수 있다(t15).
3. **placeholder를 다시 가린다.** Edit 실패 메시지에 모델이 쓴 `DB_PASSWORD: "[PASSWORD_1]"`이 그대로 돌아오자, 탐지기가 이 placeholder를 비밀번호로 보고 `[PASSWORD_2]`로 바꿨다. 모델은 "실제 값이 Read 출력과 다르다"고 혼란스러워했다(t12). 이미 placeholder 모양인 문자열은 탐지에서 빼는 편이 낫다.
4. **비밀이 아닌 숫자를 가린다.** 키 이름에 token이 들어간 `token_ttl_seconds = 5400`의 값을 가렸다(t23).
5. **CredSweeper(1.19.0)가 체크섬이 0으로 시작하는 GitHub·npm 토큰을 놓친다.** GitHub 형식은 CRC32를 base62 6자로 적고 앞을 0으로 채운다. CredSweeper의 `ValueGitHubCheck`는 이 6자를 `base62.decodebytes`로 읽는데, 이 함수는 앞의 `0`을 "널 바이트 개수" 표시로 해석해서 값이 달라진다. 그래서 실제 형식 토큰의 약 21%가 Github Classic Token, NPM Token 규칙에서 빠진다. CredSweeper를 직접 돌려 보면 그런 토큰 20개 중 0개, 0으로 시작하지 않는 토큰 20개 중 20개를 이 규칙으로 찾았다. 옆에 `token`이라는 키 이름이 있으면 일반 Token 규칙이 대신 찾았고, 없으면(`export GH_1=…`) 하나도 찾지 못했다. 형제 저장소 코드는 고치지 않았다.

## 설계 결정

- **gold는 정답 값의 정확한 문자열 일치로 가린다.** 과제의 비밀은 모두 생성한 긴 무작위 값이라 다른 문자열과 겹치지 않는다. base64, URL 인코딩, JSON 이스케이프한 형태도 각각 정답 값으로 넣고, 개인키는 본문 줄도 넣는다. 값의 일부만 출력되면(`head -c 20`) gold는 가리지 않는다. 그래서 gold는 "정답 값을 완벽하게 아는 탐지기"이지, 모든 노출을 막는 탐지기는 아니다.
- **none도 Mod를 붙인다.** 세 조건의 차이를 마스킹 하나로 좁히기 위해서다. Mod가 없는 Claude Code는 `plain` 조건으로 따로 돌릴 수 있다.
- **답은 answer.json으로 받는다.** 최종 응답의 자유 문장을 해석하지 않고, 정해진 키의 값을 비교한다. 숫자는 문자열 속 숫자를 꺼내 비교하고(`"Decimal('10.00')"`도 10.00), 목록은 순서 없이 비교한다.
- **대안 해법도 인정한다.** t12는 `$$` 이스케이프, `.env` 참조, Secret 파일을 읽어 넘기는 entrypoint를 모두 정답으로 본다. t05, t06은 어느 쪽 파일을 고쳐도 서로 맞으면 된다.
- **작업 폴더는 저장소 밖 임시 폴더다.** 저장소 안에서 돌리면 에이전트가 상위 폴더의 과제 정의(정답)를 읽을 수 있다. gold 탐지기에 넘기는 정답 파일도 탐지기가 읽은 직후 지운다.

## 한계

- **모델 하나, 반복 3회다.** 과제당 조건별 3회라 개별 과제의 차이는 우연일 수 있다. 다른 모델은 `--model`로 다시 돌린다.
- **과제가 작다.** 파일 몇 개, 4~5턴이면 끝나는 과제다. 긴 세션에서 placeholder가 쌓이는 효과는 보지 않았다.
- **과제를 직접 만들었다.** 실패 유형을 드러내도록 고른 과제라, 성공률의 절대값보다 조건 간 차이와 실패 유형을 본다.
- **headless 실행이다.** 대화형 세션에서는 사용자가 "값이 가려져 있다"고 알려 주거나 권한 질문에 답할 수 있어 결과가 다를 수 있다.
- 시스템 프롬프트(CLAUDE.md 등)로 들어가는 비밀의 노출은 재지 않는다.

## 파일

```text
metric-task/
  README.md
  EVALUATION.md          작업 성공률, 비밀 노출률, 서버 누출을 함께 읽는 기준
  tasks/<id>/            task.json, workspace/, (선택) check.py, payload.json
  tasks_gen/<id>/        생성한 과제 29개 (m2_gen.py가 씀), 손으로 쓴 gen 과제도 둘 수 있다
  tasks_scenarios/<id>/  다양한 상황의 과제 80개 (m2_scenarios.py가 씀)
  scripts/m2.py          list, build, check, selftest, play, run, recheck, report
  scripts/m2_tasks.py    과제 읽기, 빌드(git 이력 포함), 채점, 정적 점검, 모범 풀이
  scripts/m2_secrets.py  비밀과 decoy의 종류와 결정적 생성기 (실제 키 형식 + rstr, M2_SECRETS로 교체 가능)
  scripts/m2_secrets_v1.py  2026-10-12 전 실행이 쓴 이전 생성기 (예전 배치 recheck용)
  requirements.txt       rstr, PyYAML
  scripts/m2_gen.py      tasks_gen/ 생성기
  scripts/m2_scenarios.py  scenarios 생성기, 파일럿 기준 사례, README 과제 표
  scripts/m2_scenario_variants.py  기준 사례의 단일 축 변형
  scripts/m2_scenario_extra.py  추가 family의 프로젝트·채점·모범 풀이
  scripts/m2_declarations.py  미등록 자격증명 리터럴 보조 감사
  scripts/m2_inventory.py  과제 축별 분포 집계
  scripts/api_capture.py 기록 프록시와 요청 본문의 비밀 찾기
  scripts/detector_capture.py  Mod의 탐지기 호출 기록 프록시 (--detector-capture, metric-latency 재생용)
  scripts/fixture_mcp.py 정해진 응답을 돌려주는 stdio MCP 서버 (mcp 경로)
  scripts/detector_worker.py   none/gold 조건의 탐지기 (원래 worker와 같은 HTTP 규약)
  results/summary.md     main 배치(Sonnet 5.5, 3회)의 요약
  results/runs.csv       실행 234회의 결과 (비밀값 없음)
  results/capture_trial/ 기록 프록시를 켠 시험 실행(과제 10개 × 조건 3개)의 요약
```

## scenarios의 파일럿 검증 (10개)

`tasks_scenarios/`는 **10개 기준 사례를 먼저 구현·검증한 뒤 전체 80개로 확장한 suite**다. 아래는 파일럿으로 검토한 기준 사례이고, 현재 전체 목록과 분포는 뒤의 자동 생성 표에 있다. `scripts/m2_scenarios.py`가 `meta.generator=m2_scenarios`인 폴더만 결정적으로 생성한다. 기존 core 26개, gen 29개, `m2_gen.py`의 텍스트·시드·생성값은 유지한다. 입력 텍스트는 새로 작성했으며 detection 평가/학습 텍스트를 재사용하지 않는다.

| ID | family | 언어 / 프로젝트 | category / secret_requirement | 기준 축 및 채점 |
|---|---|---|---|---|
| s01-ingress-file | ingress | en / backend | diagnose / none | file 장애자료; 원인·host·port·조치·request ID와 비밀 없는 답 |
| s14-language-api-ko | language-api | ko / cli | use / use | 한국어; file/env API 키로 암호화 fixture 인증 조회 |
| s16-language-mobile-ko | language-mobile | ko / mobile | edit / none | 한국어; Java URL 동작과 XML/properties 경로 일치 |
| s23-repair-tests-raw | repair-tests | en / backend | edit / none | raw 로그; 실패 테스트와 별도 빈/다중/0/음수 입력 검사 |
| s26-frontend-refactor-env | frontend-refactor | ko / frontend | transport / transport | env 원본; 공개/서버 값 분리, mock fetch 두 입력 검사 |
| s33-infra-migration-env | infra-migration | en / infra | transport / transport | env 원본; 특수문자 비밀번호 6종·Azure·GCP PEM의 JSON 파싱값 비교 |
| s37-ci-rotation-one | ci-rotation | ko / ci-cd | transport / transport | 갱신 대상 1개; 현재 옛값 제거, 새값 반영, 나머지 모든 맥락파일 보존 |
| s47-release-review-gitlab | release-review | ko / ci-cd | review / none | GitLab PAT; HEAD 대 부모 PR의 파일/위치/조치코드 집합 검사 |
| s51-incident-report-slack-token | incident-report | en / backend | sanitize / none | Slack token; file+MCP에서 비밀 없는 구조화 답과 운영 이슈 |
| s58-negative-kinds-redaction | negative-kinds | ko / frontend | overmask / none | redaction 표시와 공개 client ID 보존, 실제 비밀 제외 |

분포는 en 4 / ko 6, backend 3 / cli 1 / mobile 1 / frontend 2 / infra 1 / ci-cd 2다. 짧은 과제 8개와 긴 맥락 과제 2개다. s37/s47은 각각 47/45개 실제 맥락파일을 포함한다. 파일 수는 세션 턴 수가 아니며, 실행 없이 10턴 이상의 세션이나 난이도를 보장하지 않는다. 모든 사례는 file 경로를 포함하며 추가 경로는 env 1, command_output 1, git_history 2, MCP 1개다.

`meta`에는 `family`, `channels`, `formats`, `generator`, `language`(사용자 프롬프트 언어), `project`(프로젝트 종류), `secret_requirement`, `length`(short/long 맥락 크기)를 기록한다. `secret_requirement`는 실제 작업에 비밀이 어떻게 필요한지 구분한다: `none`은 무관, `property`는 값의 속성, `use`는 인증 사용, `transport`는 값의 보존/이관, `identity`는 값의 동일성 비교다. 기존 `needs_secret_value`는 property/use/transport에서만 true이며 identity는 false라는 기존 의미를 유지한다. 파일럿에는 none 6 / use 1 / transport 3개다. 실행 결과 JSON·CSV와 요약 표에도 이 메타데이터를 기록한다. future family 변형은 전달 경로, 프롬프트 언어, 표현형, 입력 포맷, 회전 대상 수, 제공자 또는 제외 kind 중 지정한 축 하나씩 바꾸도록 생성기에서 프로젝트와 검사를 분리했다.

GCP service-account JSON에서는 **private_key의 PEM만 비밀**이고 주변 project/email 정보는 공개다. JSON에 보이는 escape 표면형도 별도 선언한다. Stripe publishable credential은 현 LABELING.md 기준 `ACCESS_KEY`로 선언하며, 브라우저 사용이 필요한 값이므로 s26의 공개 파일 비밀부재 검사는 서버 비밀 세 가지만 대상으로 한다. core/gen의 과거 decoy 라벨은 이 작업에서 바꾸지 않는다.

```bash
# 생성 및 추적 파일과 재생성 결과의 동일성 검사
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_scenarios.py
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_scenarios.py --check
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py list --tasks scenarios
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py list --tasks family:release-review
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py list --tasks secret_requirement:transport

# Claude를 실행하지 않는 로컬 검증: untouched 실패 / oracle 성공 / placeholder 오염 실패 + lint + 선언 감사
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py selftest --tasks scenarios
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py selftest
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_declarations.py --tasks scenarios
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s metric-task/scripts -p test_m2_declarations.py -v
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py build s14 --out /tmp/metric-task-s14

# 비용이 드는 실제 실행 명령: 파일럿 구현 단계에서는 실행하지 않음
# 사람이 prompt/fixture/채점을 검토한 뒤 우선 none 1회를 확인한다.
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py run --tasks s14 --conditions none --reps 1 --jobs 1
# 이후 같은 모델/설정으로 비교
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py run --tasks scenarios --conditions none,gold,promptguard --reps 1 --jobs 1
```

s14의 fixture payload는 빌드 시 API 키에서 유도한 키로 암호화하며, 실제 값으로 인증하지 않으면 CLI가 결과 데이터를 열지 않는다. `task.json`의 oracle/payload는 평가자용이고 에이전트 workspace 밖에 있다. 모바일 검사는 설치된 JDK가 있으면 순수 Java를 컴파일/실행하고 없으면 제한된 반환식 의미 검사로 대체하며 Android SDK/네트워크는 사용하지 않는다. 프론트엔드 동작 검사는 로컬 Node.js를 사용한다. selftest는 에이전트의 풀이 능력이나 실제 MCP/hook 경로의 작동을 입증하지 않는다.

### 선언 구조와 독립 누락 검사

metric-task gold는 span annotation을 생성하지 않고 `secrets`에 선언된 **값 목록**과 선언된 파생형으로 만든다. `{{secret:name}}` / `{{decoy:name}}` 참조를 빌드 시 채우는 구조 검사는 참조 누락과 결정성을 확인한다. `scripts/m2_declarations.py`는 그 목록 **밖에 들어간 자격증명 리터럴을 찾는 보조 검사**다. 이미 선언한 값의 각 span을 gitleaks/label_rules가 다시 탐지해야만 통과하는 방식이 아니며, 이 검사기가 gold를 새로 정하지 않는다.

scenarios selftest의 필수 검사는 선언 목록과 독립적으로 후보를 추출한다. 설치된 gitleaks(현재 검증 환경 8.30.1)와 설정자리, URL password, Basic 전체 base64, Bearer, 세션 쿠키, PEM 전체 블록, 제공자 형식, 연결문자열, CLI, XML, 한국어/영어 credential prose 추출을 함께 사용한 뒤 읽기 전용 `metric-detection/scripts/label_rules.py`의 classify/exclusion_kind로 판정한다. gitleaks가 없으면 해당 부분만 skipped를 명시하고 후보 추출/label_rules 검사는 계속한다. 미선언 후보는 실패하며 unknown을 넓은 allowlist로 지우지 않는다. 제외 값은 redaction/template/reference/code/identifier 등 해당 span/즉시 문맥의 명시적 규칙으로만 제외한다. JSON/XML escape를 일반 code라는 이유로 숨기지 않는다. 모든 선언 비밀은 8자 이상이고 is_common=False여야 한다.

빌드된 파일은 확장자 제한 없이 UTF-8 텍스트를 스캔한다. 프롬프트, session_env(키 문맥 포함), append_system_prompt, MCP fixture, history, commit messages, worktree_changes, setup argv, 로컬 git remote/config, 실제 git 이력의 삭제된 파일을 포함한 모든 blob/메시지도 검사한다. binary는 원형 복사하고 텍스트 감사에서는 제외한다. raw와 실제 노출되는 encoded 표면형은 각각 선언해야 한다. 모든 과제는 integrity를 검사하며 scenarios는 새 확장자의 placeholder 기록도 실패로 처리한다. 파일에 비밀이 없는 향후 경로 전용 사례도 별도 파일에 placeholder를 기록해 corruption 검사를 실제 수행한다. 기존 core/gen의 n/a 동작은 유지한다.

회귀 검사는 미선언 리터럴 삽입, 정당한 제외 값의 오탐 방지, JSON/XML 변형 미선언, 실제 삭제된 이력/메시지/remote·세션필드 누락, 짧고 흔한 비밀 거부, gitleaks finding의 일부 overlap으로 전체를 숨기는 오류를 포함한다. 이는 알려진 양식을 검사하는 보조 감사로 모든 가능한 리터럴 표현을 완전히 찾는 증명은 아니다.

strict 감사는 **새 scenarios에서 필수**다. 기존 gen의 g21 Stripe publishable decoy처럼 현 라벨 기준과 다른 구과제는 비파괴 별도 감사 대상이며, 과거 gold/텍스트/값/selftest를 바꾸지 않는다. 필요하면 다음처럼 감사 결과만 보고 종료 코드는 보존할 수 있다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_declarations.py --tasks core gen --legacy-audit
```

<!-- scenarios-catalog:start -->
## scenarios 전체 80개

10개 파일럿을 검토한 뒤 같은 생성기를 확장한 80개다. 과제 80개 × 3조건 × 3회는 720회다. Claude Code는 구현 중 실행하지 않았다. 생성기 `--check`는 과제 파일과 이 표를 함께 비교한다.

| family | 개수 | 바꾸는 축 |
|---|---:|---|
| ci-rotation | 4 | 갱신 대상 1 / 3 / 8 / 16곳 |
| cli-auth | 6 | password / Bearer / Basic / cookie / AWS pair / PEM |
| frontend-refactor | 3 | env / JSON / TOML |
| identity-encoding | 4 | raw / base64 / URL / JSON escape |
| incident-report | 3 | Slack token / webhook / OAuth secret |
| infra-migration | 4 | 원본 env / YAML / JSON / TOML |
| ingress | 13 | 전달 경로 13개 |
| jwt-property | 4 | exp 시각 (-3600 / -1 / 0 / +3600초) |
| language-api | 2 | 한국어 / 영어 |
| language-mobile | 2 | 한국어 / 영어 |
| language-pipeline | 2 | 한국어 / 영어 |
| log-scrub | 4 | log / JSONL / HAR / CSV |
| mobile-gradle | 2 | 비밀번호의 달러 문자 유무 |
| monorepo-size | 2 | 서비스 및 프로젝트 크기 |
| negative-kinds | 10 | 정답이 아닌 kind 10개 |
| notebook-size | 2 | 입력 분할 및 프로젝트 크기 |
| partial-output | 3 | 8자 / 20자 / 전체 출력 |
| prompt-style | 3 | 짧은 / 상세 / 모호한 요청 |
| release-review | 4 | GitLab / Anthropic / OpenAI / npm 형식 |
| repair-tests | 3 | raw / base64 / JSON escape |

| 과제 | family | 유형 | 언어 | 경로 | 파일 수 |
|---|---|---|---|---|---:|
| [s01-ingress-file](tasks_scenarios/s01-ingress-file/task.json) | ingress | diagnose | en | file | 6 |
| [s02-ingress-command-output](tasks_scenarios/s02-ingress-command-output/task.json) | ingress | diagnose | en | command_output | 7 |
| [s03-ingress-prompt](tasks_scenarios/s03-ingress-prompt/task.json) | ingress | diagnose | en | prompt | 5 |
| [s04-ingress-at-mention](tasks_scenarios/s04-ingress-at-mention/task.json) | ingress | diagnose | en | at_mention | 6 |
| [s05-ingress-claude-md](tasks_scenarios/s05-ingress-claude-md/task.json) | ingress | diagnose | en | claude_md | 6 |
| [s06-ingress-session-hook](tasks_scenarios/s06-ingress-session-hook/task.json) | ingress | diagnose | en | session_hook | 7 |
| [s07-ingress-env](tasks_scenarios/s07-ingress-env/task.json) | ingress | diagnose | en | env | 5 |
| [s08-ingress-stdin](tasks_scenarios/s08-ingress-stdin/task.json) | ingress | diagnose | en | stdin | 6 |
| [s09-ingress-append-system-prompt](tasks_scenarios/s09-ingress-append-system-prompt/task.json) | ingress | diagnose | en | append_system_prompt | 5 |
| [s10-ingress-mcp](tasks_scenarios/s10-ingress-mcp/task.json) | ingress | diagnose | en | mcp | 5 |
| [s11-ingress-git-history](tasks_scenarios/s11-ingress-git-history/task.json) | ingress | diagnose | en | git_history | 5 |
| [s12-ingress-commit-message](tasks_scenarios/s12-ingress-commit-message/task.json) | ingress | diagnose | en | commit_message | 5 |
| [s13-ingress-subagent](tasks_scenarios/s13-ingress-subagent/task.json) | ingress | diagnose | en | subagent | 6 |
| [s14-language-api-ko](tasks_scenarios/s14-language-api-ko/task.json) | language-api | use | ko | file, env | 4 |
| [s15-language-api-en](tasks_scenarios/s15-language-api-en/task.json) | language-api | use | en | file, env | 4 |
| [s16-language-mobile-ko](tasks_scenarios/s16-language-mobile-ko/task.json) | language-mobile | edit | ko | file | 5 |
| [s17-language-mobile-en](tasks_scenarios/s17-language-mobile-en/task.json) | language-mobile | edit | en | file | 5 |
| [s18-language-pipeline-ko](tasks_scenarios/s18-language-pipeline-ko/task.json) | language-pipeline | diagnose | ko | file, command_output | 6 |
| [s19-language-pipeline-en](tasks_scenarios/s19-language-pipeline-en/task.json) | language-pipeline | diagnose | en | file, command_output | 6 |
| [s20-prompt-style-short](tasks_scenarios/s20-prompt-style-short/task.json) | prompt-style | diagnose | ko | file, command_output | 4 |
| [s21-prompt-style-detailed](tasks_scenarios/s21-prompt-style-detailed/task.json) | prompt-style | diagnose | ko | file, command_output | 4 |
| [s22-prompt-style-ambiguous](tasks_scenarios/s22-prompt-style-ambiguous/task.json) | prompt-style | diagnose | ko | file, command_output | 4 |
| [s23-repair-tests-raw](tasks_scenarios/s23-repair-tests-raw/task.json) | repair-tests | edit | en | file, command_output | 5 |
| [s24-repair-tests-base64](tasks_scenarios/s24-repair-tests-base64/task.json) | repair-tests | edit | en | file, command_output | 5 |
| [s25-repair-tests-json](tasks_scenarios/s25-repair-tests-json/task.json) | repair-tests | edit | en | file, command_output | 5 |
| [s26-frontend-refactor-env](tasks_scenarios/s26-frontend-refactor-env/task.json) | frontend-refactor | transport | ko | file | 5 |
| [s27-frontend-refactor-json](tasks_scenarios/s27-frontend-refactor-json/task.json) | frontend-refactor | transport | ko | file | 5 |
| [s28-frontend-refactor-toml](tasks_scenarios/s28-frontend-refactor-toml/task.json) | frontend-refactor | transport | ko | file | 5 |
| [s29-mobile-gradle-password16](tasks_scenarios/s29-mobile-gradle-password16/task.json) | mobile-gradle | edit | en | file | 4 |
| [s30-mobile-gradle-password-dollar](tasks_scenarios/s30-mobile-gradle-password-dollar/task.json) | mobile-gradle | edit | en | file | 4 |
| [s31-notebook-size-small](tasks_scenarios/s31-notebook-size-small/task.json) | notebook-size | edit | ko | file, command_output | 8 |
| [s32-notebook-size-large](tasks_scenarios/s32-notebook-size-large/task.json) | notebook-size | edit | ko | file, command_output | 42 |
| [s33-infra-migration-env](tasks_scenarios/s33-infra-migration-env/task.json) | infra-migration | transport | en | file | 6 |
| [s34-infra-migration-yaml](tasks_scenarios/s34-infra-migration-yaml/task.json) | infra-migration | transport | en | file | 6 |
| [s35-infra-migration-json](tasks_scenarios/s35-infra-migration-json/task.json) | infra-migration | transport | en | file | 6 |
| [s36-infra-migration-toml](tasks_scenarios/s36-infra-migration-toml/task.json) | infra-migration | transport | en | file | 6 |
| [s37-ci-rotation-one](tasks_scenarios/s37-ci-rotation-one/task.json) | ci-rotation | transport | ko | file, git_history | 47 |
| [s38-ci-rotation-3](tasks_scenarios/s38-ci-rotation-3/task.json) | ci-rotation | transport | ko | file, git_history | 49 |
| [s39-ci-rotation-8](tasks_scenarios/s39-ci-rotation-8/task.json) | ci-rotation | transport | ko | file, git_history | 54 |
| [s40-ci-rotation-16](tasks_scenarios/s40-ci-rotation-16/task.json) | ci-rotation | transport | ko | file, git_history | 62 |
| [s41-cli-auth-password](tasks_scenarios/s41-cli-auth-password/task.json) | cli-auth | use | en | file | 4 |
| [s42-cli-auth-bearer](tasks_scenarios/s42-cli-auth-bearer/task.json) | cli-auth | use | en | file | 4 |
| [s43-cli-auth-basic](tasks_scenarios/s43-cli-auth-basic/task.json) | cli-auth | use | en | file | 4 |
| [s44-cli-auth-cookie](tasks_scenarios/s44-cli-auth-cookie/task.json) | cli-auth | use | en | file | 4 |
| [s45-cli-auth-aws-pair](tasks_scenarios/s45-cli-auth-aws-pair/task.json) | cli-auth | use | en | file | 4 |
| [s46-cli-auth-pem](tasks_scenarios/s46-cli-auth-pem/task.json) | cli-auth | use | en | file | 4 |
| [s47-release-review-gitlab](tasks_scenarios/s47-release-review-gitlab/task.json) | release-review | review | ko | file, git_history | 45 |
| [s48-release-review-anthropic-key](tasks_scenarios/s48-release-review-anthropic-key/task.json) | release-review | review | ko | file, git_history | 45 |
| [s49-release-review-openai-key](tasks_scenarios/s49-release-review-openai-key/task.json) | release-review | review | ko | file, git_history | 45 |
| [s50-release-review-npm-token](tasks_scenarios/s50-release-review-npm-token/task.json) | release-review | review | ko | file, git_history | 45 |
| [s51-incident-report-slack-token](tasks_scenarios/s51-incident-report-slack-token/task.json) | incident-report | sanitize | en | file, mcp | 3 |
| [s52-incident-report-slack-webhook](tasks_scenarios/s52-incident-report-slack-webhook/task.json) | incident-report | sanitize | en | file, mcp | 3 |
| [s53-incident-report-google-oauth-secret](tasks_scenarios/s53-incident-report-google-oauth-secret/task.json) | incident-report | sanitize | en | file, mcp | 3 |
| [s54-log-scrub-log](tasks_scenarios/s54-log-scrub-log/task.json) | log-scrub | sanitize | ko | file, command_output | 5 |
| [s55-log-scrub-jsonl](tasks_scenarios/s55-log-scrub-jsonl/task.json) | log-scrub | sanitize | ko | file, command_output | 5 |
| [s56-log-scrub-har](tasks_scenarios/s56-log-scrub-har/task.json) | log-scrub | sanitize | ko | file, command_output | 5 |
| [s57-log-scrub-csv](tasks_scenarios/s57-log-scrub-csv/task.json) | log-scrub | sanitize | ko | file, command_output | 5 |
| [s58-negative-kinds-redaction](tasks_scenarios/s58-negative-kinds-redaction/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s59-negative-kinds-template](tasks_scenarios/s59-negative-kinds-template/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s60-negative-kinds-reference](tasks_scenarios/s60-negative-kinds-reference/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s61-negative-kinds-code](tasks_scenarios/s61-negative-kinds-code/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s62-negative-kinds-doc-example](tasks_scenarios/s62-negative-kinds-doc-example/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s63-negative-kinds-descriptor](tasks_scenarios/s63-negative-kinds-descriptor/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s64-negative-kinds-hash](tasks_scenarios/s64-negative-kinds-hash/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s65-negative-kinds-identifier](tasks_scenarios/s65-negative-kinds-identifier/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s66-negative-kinds-non-credential](tasks_scenarios/s66-negative-kinds-non-credential/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s67-negative-kinds-empty](tasks_scenarios/s67-negative-kinds-empty/task.json) | negative-kinds | overmask | ko | file | 4 |
| [s68-identity-encoding-raw](tasks_scenarios/s68-identity-encoding-raw/task.json) | identity-encoding | identity | en | file, git_history, command_output | 6 |
| [s69-identity-encoding-base64](tasks_scenarios/s69-identity-encoding-base64/task.json) | identity-encoding | identity | en | file, git_history, command_output | 6 |
| [s70-identity-encoding-url](tasks_scenarios/s70-identity-encoding-url/task.json) | identity-encoding | identity | en | file, git_history, command_output | 6 |
| [s71-identity-encoding-json](tasks_scenarios/s71-identity-encoding-json/task.json) | identity-encoding | identity | en | file, git_history, command_output | 6 |
| [s72-jwt-property-minus3600](tasks_scenarios/s72-jwt-property-minus3600/task.json) | jwt-property | property | ko | file | 2 |
| [s73-jwt-property-minus1](tasks_scenarios/s73-jwt-property-minus1/task.json) | jwt-property | property | ko | file | 2 |
| [s74-jwt-property-0](tasks_scenarios/s74-jwt-property-0/task.json) | jwt-property | property | ko | file | 2 |
| [s75-jwt-property-3600](tasks_scenarios/s75-jwt-property-3600/task.json) | jwt-property | property | ko | file | 2 |
| [s76-monorepo-size-small](tasks_scenarios/s76-monorepo-size-small/task.json) | monorepo-size | use | en | file, command_output, git_history | 18 |
| [s77-monorepo-size-large](tasks_scenarios/s77-monorepo-size-large/task.json) | monorepo-size | use | en | file, command_output, git_history | 48 |
| [s78-partial-output-8](tasks_scenarios/s78-partial-output-8/task.json) | partial-output | property | ko | file, command_output | 5 |
| [s79-partial-output-20](tasks_scenarios/s79-partial-output-20/task.json) | partial-output | property | ko | file, command_output | 5 |
| [s80-partial-output-full](tasks_scenarios/s80-partial-output-full/task.json) | partial-output | property | ko | file, command_output | 5 |

### 기존 55개와의 분포 비교

| 유형 | 기존 | scenarios | 합계 |
|---|---:|---:|---:|
| diagnose | 21 | 18 | 39 |
| edit | 7 | 9 | 16 |
| identity | 3 | 4 | 7 |
| overmask | 10 | 10 | 20 |
| property | 4 | 7 | 11 |
| review | 0 | 4 | 4 |
| sanitize | 0 | 7 | 7 |
| transport | 8 | 11 | 19 |
| use | 2 | 10 | 12 |

| 축 | 기존 55개 | scenarios 80개 |
|---|---|---|
| 언어 | 한국어 55 | 한국어 40 / 영어 40 |
| 실제 값 필요 | 14 | 28 (property 7 / use 10 / transport 11) |
| 값의 동일성 비교 | 3 | 4 |
| 복수 경로 | 0 | 36 |
| 파일 수 | 1~7 | 2~62 |
| 긴 맥락 | 0 | 10 (42~62파일, 실제 턴 수 미측정) |
| 기본 비밀 종류 | 기존 32종 | 기존 32종 + 신규 5종 모두 사용 |
| 제외 kind | kind별 메타데이터 없음 | 10종 각각 1개 기준 사례 |

| 경로 | 기존 | scenarios |
|---|---:|---:|
| append_system_prompt | 1 | 1 |
| at_mention | 1 | 1 |
| claude_md | 1 | 1 |
| command_output | 1 | 24 |
| commit_message | 1 | 1 |
| env | 1 | 3 |
| file | 39 | 68 |
| git_history | 2 | 15 |
| mcp | 2 | 4 |
| prompt | 3 | 1 |
| session_hook | 1 | 1 |
| stdin | 1 | 1 |
| subagent | 1 | 1 |

| 프로젝트 | 기존 (주 작업 기준 수작업 분류) | scenarios |
|---|---:|---:|
| backend | 32 | 27 |
| frontend | 2 | 13 |
| mobile | 0 | 4 |
| data | 7 | 4 |
| infra | 5 | 8 |
| ci-cd | 5 | 8 |
| cli | 4 | 14 |
| monorepo | 0 | 2 |

| 형식·표현 (중복 집계) | 기존 과제 수 | scenarios 과제 수 |
|---|---:|---:|
| authorized_keys | 1 | 0 |
| base64 | 0 | 2 |
| compose | 4 | 4 |
| csv | 0 | 1 |
| diff | 0 | 8 |
| dockerfile | 0 | 10 |
| dotenv | 22 | 32 |
| go | 0 | 2 |
| gradle | 0 | 2 |
| har | 0 | 1 |
| http | 1 | 22 |
| ini | 4 | 13 |
| ipynb | 0 | 2 |
| java | 0 | 2 |
| javascript | 4 | 10 |
| json | 10 | 47 |
| jsonl | 0 | 1 |
| k8s | 2 | 4 |
| log | 19 | 28 |
| markdown | 33 | 67 |
| npmrc | 1 | 4 |
| pem | 0 | 10 |
| properties | 1 | 4 |
| python | 26 | 32 |
| raw | 0 | 1 |
| shell | 4 | 11 |
| sql | 0 | 4 |
| stacktrace | 0 | 13 |
| terraform | 0 | 4 |
| toml | 0 | 5 |
| typescript | 0 | 15 |
| url | 1 | 1 |
| xml | 1 | 4 |
| yaml | 11 | 14 |

| 기본 비밀 종류 | 기존 과제 수 | scenarios 과제 수 |
|---|---:|---:|
| anthropic_key | 0 | 1 |
| api_key | 4 | 7 |
| aws_access_key | 2 | 7 |
| aws_secret_key | 2 | 7 |
| azure_storage_key | 0 | 4 |
| datadog_api_key | 7 | 17 |
| docker_pat | 1 | 4 |
| github_pat | 7 | 17 |
| github_token | 1 | 2 |
| gitlab_pat | 0 | 1 |
| google_oauth_secret | 1 | 6 |
| hex_secret | 2 | 4 |
| jwt_claims | 1 | 4 |
| npm_token | 2 | 5 |
| openai_key | 1 | 1 |
| openssh_private_key | 1 | 1 |
| password16 | 37 | 26 |
| password_backslash | 1 | 4 |
| password_dollar | 1 | 1 |
| password_json_unsafe | 1 | 7 |
| password_percent | 1 | 4 |
| password_url_unsafe | 1 | 8 |
| password_xml_unsafe | 1 | 4 |
| password_yaml_unsafe | 1 | 4 |
| pattern | 3 | 3 |
| private_key | 1 | 6 |
| secret | 6 | 3 |
| session_cookie | 0 | 1 |
| slack_token | 2 | 1 |
| slack_webhook | 1 | 1 |
| stripe_live | 4 | 6 |
| stripe_publishable | 0 | 3 |
| stripe_test | 1 | 3 |
| stripe_webhook | 1 | 3 |
| token | 7 | 4 |
| twilio_auth_token | 1 | 4 |
| vault_token | 7 | 4 |

형식은 env, YAML, JSON, TOML, INI, properties, XML, Dockerfile, Compose, k8s, Terraform, 셸, Python/JS/TS/Go/Java, SQL, 로그/스택트레이스, HTTP, diff, Markdown, ipynb, JSONL/HAR/CSV를 포함한다. 정확한 형식별 집계와 비밀 종류별 과제 수는 `m2_inventory.py --tasks all`로 재현한다. 형식·경로는 여러 개를 가진 과제를 중복 집계한다.

추가 종류는 GitLab PAT, Anthropic API key, Azure Storage key, session cookie, Stripe publishable credential이다. 기존 종류의 정의·시드·생성값은 유지한다. Anthropic 형식은 [gitleaks v8.30.1 규칙](https://github.com/gitleaks/gitleaks/blob/v8.30.1/cmd/generate/config/rules/anthropic.go)을 따른다. 외부 규칙의 형식만 참고했으며 샘플 텍스트나 값을 과제로 복사하지 않았다.

### 실행 없이 확인하기

```bash
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_scenarios.py --check
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_inventory.py --tasks all
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2.py selftest
PYTHONDONTWRITEBYTECODE=1 python3 metric-task/scripts/m2_declarations.py --tasks scenarios
```

### 사람이 실행할 확인 명령과 비용

다음 명령은 API 비용이 발생하므로 구현 중 실행하지 않았다. 먼저 13개 경로를 none 1회씩 확인하고 `result.json`의 `server.by_secret.channels/tools`를 기대 경로와 비교한다.

```bash
python3 metric-task/scripts/m2.py run --tasks family:ingress --conditions none --reps 1 --model sonnet --name scenarios_none_check
python3 metric-task/scripts/m2.py run --tasks scenarios --conditions none,gold,promptguard --reps 3 --model sonnet --jobs 2 --name scenarios_r3
python3 metric-task/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 3 --model sonnet --jobs 2 --name all_suites_r3
```

사용자가 제시한 실행당 $0.05를 적용하면 경로 확인 약 $0.65, 신규 720회 $36, 전체 1215회 $60.75다. 긴 과제 10개에 실행당 $0.15~0.30을 가정하면 신규 약 $45~58.50, 기존 포함 약 $69.75~83.25다. 이는 측정 전 추정이며 재시도는 별도다.

### 측정하지 못하는 상황

- 8자 미만 또는 `is_common=True`인 비밀번호는 제외했다. 자리별 gold로 실행기를 바꾸지 않았다.
- s78/s79의 짧은 prefix는 full-value gold가 가리지 않는다. 절반 미만 노출은 기존 부분 누출 집계에도 빠지므로 이 과제의 누출 0을 보호 성공으로 읽지 않는다.
- 파일 수가 많아도 10턴 이상을 보장하지 않는다. 실제 `num_turns`와 none 노출을 확인해야 한다.
- 이미지/PDF·binary 내부 값, 외부 서비스의 실제 인증/폐기, placeholder 자동 원복은 평가하지 않는다.
- PEM 인증 fixture는 키 파일의 소유를 확인하는 오프라인 모형이며 실제 SSH 서명/서버 인증이 아니다.
- 경로 전달은 실제 Claude Code none 실행 전까지 확인되지 않았다.

<!-- scenarios-catalog:end -->
