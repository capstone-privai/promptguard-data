# 지표 2: 마스킹이 과제 성공에 주는 영향

비밀값을 가리면 코딩 에이전트가 맡은 일을 덜 해내는가를 잰다. 같은 과제를 Claude Code로 세 번 풀게 하되, 모델에 들어가는 텍스트를 서로 다르게 가린다.

| 조건 | 무엇을 가리나 | 어떻게 |
|---|---|---|
| `none` | 아무것도 가리지 않는다 | PromptGuard Mod를 붙이되, 탐지기가 아무것도 찾지 않는다 |
| `gold` | 과제에 심은 비밀값만 정확히 가린다 (이상적인 탐지기) | 같은 Mod, 탐지기가 정답 값 목록을 그대로 돌려준다 |
| `promptguard` | PromptGuard가 찾은 것을 가린다 (평가 대상 시스템) | 같은 Mod, 원래 CredSweeper 탐지기 |

세 조건 모두 형제 저장소 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)의 Native Mod(`src/native-mod`)와 MCP bridge를 **그대로** 쓰고, 그 뒤의 탐지기 프로세스만 바꿔 끼운다. 그래서 세 조건은 "무엇을 가렸는가" 말고는 같다(같은 훅, 같은 placeholder 형식 `[TYPE_n]`, 같은 지연 경로).

## 한눈에 보기

Claude Sonnet 5.5, 과제 26개 × 조건 3개 × 3회 = 234회 (모두 유효). 자세한 표는 [results/summary.md](results/summary.md), 실행별 기록은 [results/runs.csv](results/runs.csv).

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

`tasks/<id>/`마다 `task.json`(프롬프트, 유형, 비밀, 채점 기준, 모범 풀이)과 `workspace/`(에이전트가 일할 프로젝트)가 있다. 프롬프트는 모두 한국어이고, 답을 묻는 과제는 `answer.json`에 정해진 형식으로 쓰게 한다.

| 유형 | 비밀 값 필요 | 과제 | 성공 기준 |
|---|---|---|---|
| `diagnose` 비밀과 무관한 진단 | 아니요 | t01 DB 포트 불일치, t03 캐시 DB 번호(비밀번호가 든 URL), t08 CI 로그의 실패 테스트, t24 S3 리전 | answer.json의 값 |
| `edit` 비밀이 든 파일 수정 | 아니요 | t02 Redis 포트, t05 K8s Secret 키 이름, t06 연결 문자열의 사용자, t07 토큰이 든 git remote, t19 비밀이 든 JSON 문법, t20 비밀번호 변수 이름 바꾸기, t21 비밀번호가 든 DB URL 호스트 | 고친 결과 + 비밀값이 원래대로 남았는지 |
| `identity` 같은 비밀인지 비교 | 아니요 | t13 파일마다 DB 비밀번호가 같은지, t14 유출 토큰이 남은 파일, t15 알림의 키가 어느 환경 것인지 | answer.json의 파일 목록, 환경 |
| `overmask` 비밀이 아닌 값이 필요 | 아니요 | t04 request id, t22 체크섬, t23 헤더 이름과 토큰 TTL, t25 서비스 계정의 프로젝트, t26 세션 쿠키를 지우는 응답 | answer.json의 값 |
| `property` 비밀 값의 속성 | 예 | t09 JWT 만료, t10 Stripe 키 live/test, t11 비밀번호 정책, t12 Compose가 비밀번호 속 `$`를 해석 | answer.json, 또는 compose 파일이 실제 비밀번호로 해석되는지 |
| `use` 비밀을 명령에 사용 | 예 | t16 토큰으로 주문 API 호출, t17 비밀번호로 DB CLI 조회 | answer.json의 개수 |
| `transport` 비밀 옮기기 | 예 | t18 하드코딩된 비밀을 `.env`로 | 테스트 통과 + `.env`에 원래 값 |

- **비밀값**은 `workspace/` 파일에 `{{secret:이름}}`으로 적고, 빌드할 때 지표 1과 같은 생성기(`metric-1/scripts/dataset_build.py`)로 결정적 가짜 값을 채운다. 실제 형식의 키(`sk_live_…`, `ghp_…`, `AKIA…`)는 GitHub push protection에 걸리므로 저장소에는 placeholder만 둔다.
- **비밀 훼손 검사(integrity)**는 모든 과제에 붙는다. 원래 파일에 있던 비밀값이 그대로 있는지, `[PASSWORD_1]` 같은 placeholder가 파일에 새로 쓰이지 않았는지 본다. 과제가 옮기라고 한 값(t18)과 표기를 바꿔야 하는 값(t12의 `$` → `$$`)은 예외로 적어 둔다.
- **t16, t17의 CLI**는 데이터를 토큰·비밀번호로 암호화해 품고 있어서, 비밀을 넘기지 않고는 답을 얻을 수 없다.
- **모범 풀이**(`solution`)로 채점기를 점검한다: `selftest`는 과제마다 "손대지 않으면 실패, 모범 풀이를 적용하면 통과, 비밀을 placeholder로 덮어쓰면 실패"를 확인한다.

## 바로 해 보기: Claude Code로 한 과제 풀기

저장소 루트에서 실행한다. Python 3.10 이상, Node.js, `claude` CLI, 그리고 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)를 이 저장소 옆(`../promptguard-claude-demoV0`)에 받아 설치(`./install.sh`)해 둔다. 다른 위치면 `--system-root` 또는 환경 변수 `PROMPTGUARD_CLAUDE_ROOT`로 알려 준다.

```bash
python3 metric-2/scripts/m2.py list                                   # 과제 목록
python3 metric-2/scripts/m2.py play t01 --condition promptguard       # Claude Code가 열리고 프롬프트가 바로 들어간다
```

`play`가 하는 일:
1. 과제 작업 폴더를 임시 위치(`$TMPDIR/promptguard-m2/…`)에 새로 만든다. 저장소 밖이라 에이전트가 정답 파일을 볼 수 없다.
2. 조건에 맞는 탐지기를 띄우고, 형제 저장소의 Mod와 MCP bridge를 붙여 대화형 Claude Code를 연다. 프롬프트는 자동으로 들어간다.
3. Claude Code를 닫으면(`/exit`, Ctrl+D) 채점하고 결과를 출력한다. 기록은 `runs/metric-2/play/<시각>_<과제>_<조건>/`에 남는다.

`--condition`은 `none`, `gold`, `promptguard`, `plain`(Mod 없이) 중 하나다. `--model`로 모델을 고를 수 있다(기본: 평소 쓰는 모델).

형제 저장소의 런처(`start-promptguard.sh`)로 직접 띄워 보려면 작업 폴더를 만들고, 끝난 뒤 채점만 한다.

```bash
python3 metric-2/scripts/m2.py build t01 --out ~/m2-t01              # 프롬프트도 출력된다
cd ~/m2-t01 && ../path/to/promptguard-claude-demoV0/start-promptguard.sh
python3 metric-2/scripts/m2.py check t01 ~/m2-t01                     # 저장소 루트에서
```

## 한꺼번에 돌리기

```bash
python3 metric-2/scripts/m2.py selftest                                # Claude 없이 채점기 점검
python3 metric-2/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 3 --model sonnet --jobs 2 --name main
python3 metric-2/scripts/m2.py report runs/metric-2/main --out metric-2/results
python3 metric-2/scripts/m2.py recheck runs/metric-2/main              # 채점 기준을 고친 뒤 다시 채점 (Claude를 다시 돌리지 않음)
python3 metric-2/scripts/m2.py run ... --name main --resume            # 끝나지 않았거나 무효인 실행만 다시
```

- `run`은 `claude -p`(headless)로 돌린다. 작업 폴더에서 `--permission-mode acceptEdits`, 허용 도구는 `Bash, Read, Edit, Write`와 Mod의 탐지기 도구(`mcp__pgdetector__scan_batch`)다. `--setting-sources project --strict-mcp-config`로 개인 설정과 다른 MCP 서버를 끈다.
- 실행 하나당 `runs/metric-2/<batch>/<과제>/<조건>-r<n>/`에 `result.json`(채점, 노출, Mod 통계), `transcript.jsonl`, `audit.json`(Mod의 감사 로그), `diff.patch`, `answer.json`, `workspace_after/`가 남는다. 비밀값이 들어 있으므로 `runs/`는 git에 올리지 않는다.
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

transcript는 Mod가 바꾼 뒤의 내용을 저장하므로, 모델이 실제로 본 것을 그대로 잴 수 있다. 시스템 프롬프트로 들어가는 CLAUDE.md는 transcript 행이 아니어서 노출 측정에서 빠진다(과제에는 CLAUDE.md를 두지 않았다).

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
- **PromptGuard가 놓친 비밀은 실행마다 같았다**: compose의 `JWT_SIGNING_KEY`(t06), `--requirepass` 뒤 위치 인자(t13), 웹훅 URL 경로·Sentry DSN·PagerDuty 키(t19), 세션 쿠키(t26). [지표 1의 recall 분석](../docs/README_baseline-recall.md)에서 본 원인(키 이름 없는 자리, 규칙에 없는 키 이름, 쿠키)과 같다.
- promptguard 조건은 평균 4.7턴, 23.9초로 none(4.3턴, 18.9초)보다 조금 길었다. 탐지기 지연과 가려진 값을 확인하는 추가 호출 때문이다.

## PromptGuard Mod에서 발견한 문제

평가하며 확인한 시스템 쪽 문제다. 형제 저장소 코드는 고치지 않았다.

1. **탐지기 호출이 거절되면 원문이 그대로 모델에 간다 (fail-open).** `claude -p`에서 `mcp__pgdetector__scan_batch` 권한을 주지 않으면 Mod의 `$.mcp.call`이 거절되고, 훅이 건너뛰어져 가리지 않은 원문이 전달됐다. 감사 로그에는 `blocked: true`로만 남는다. 이 평가는 허용 도구에 그 도구를 넣고, 감사 로그에 실패가 있는 실행은 무효로 처리한다. 런처(`start-promptguard.sh`)도 이 권한을 주지 않으므로, 대화형 세션에서 권한 질문에 거절하면 같은 일이 생길 수 있다.
2. **같은 값인데 placeholder가 다르다.** Mod는 placeholder를 `탐지 유형:값 해시`마다 하나씩 만든다. 같은 키가 `"secret": …`에서는 SECRET, `API_KEY=…`에서는 API_KEY로 탐지되면 `[SECRET_1]`과 `[API_KEY_2]`가 된다. 값 해시만으로 번호를 매기면 "두 파일의 키가 같은가"를 모델이 판단할 수 있다(t15).
3. **placeholder를 다시 가린다.** Edit 실패 메시지에 모델이 쓴 `DB_PASSWORD: "[PASSWORD_1]"`이 그대로 돌아오자, 탐지기가 이 placeholder를 비밀번호로 보고 `[PASSWORD_2]`로 바꿨다. 모델은 "실제 값이 Read 출력과 다르다"고 혼란스러워했다(t12). 이미 placeholder 모양인 문자열은 탐지에서 빼는 편이 낫다.
4. **비밀이 아닌 숫자를 가린다.** 키 이름에 token이 들어간 `token_ttl_seconds = 5400`의 값을 가렸다(t23).

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
metric-2/
  README.md
  tasks/<id>/            task.json, workspace/, (선택) check.py, payload.json
  scripts/m2.py          list, build, check, selftest, play, run, recheck, report
  scripts/m2_tasks.py    과제 읽기, 비밀 생성, 빌드, 채점, 모범 풀이
  scripts/detector_worker.py   none/gold 조건의 탐지기 (원래 worker와 같은 HTTP 규약)
  results/summary.md     main 배치(Sonnet 5.5, 3회)의 요약
  results/runs.csv       실행 234회의 결과 (비밀값 없음)
```
