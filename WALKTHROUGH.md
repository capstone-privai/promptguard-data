# 2026-10-08 작업 따라가기

`metric2-utility-metric1-sources` 브랜치에서 한 일을 처음부터 따라가 보는 안내서다. 위에서부터 순서대로 읽고, 코드 블록의 명령을 그대로 치면 결과를 직접 확인할 수 있다. 모든 명령은 이 저장소 루트(`promptguard-data/`)에서 실행한다.

---

## 0. 한 장 요약

요청받은 일 세 가지와 결과물이다.

| 요청 | 만든 것 | 어디에 |
|---|---|---|
| 지표 2 평가 데이터 20~30문항 + 평가 스크립트, Claude Code만 켜면 바로 테스트 | 과제 **26개**, 실행기 `m2.py` (`play` 한 줄이면 Mod가 붙은 Claude Code가 과제와 함께 열림) | [metric-2/](metric-2/README.md) |
| 지표 2: 마스킹 정도(없음 / 정답 / 우리 시스템)에 따라 과제 성공이 바뀌는지 보여 주는 자료 | 234회 실행 결과와 실패 사례 분석 | [metric-2/results/summary.md](metric-2/results/summary.md), [metric-2/README.md](metric-2/README.md#한눈에-보기) |
| 지표 1: 다양한 소스로 `sessions_from_XX.jsonl` + `README_XX.md` | 새 소스 **4개** (Nemotron-PII, openhands-feedback, SWE-Gym, Nosey Parker) | [metric-1/README.md](metric-1/README.md#데이터셋), `metric-1/README_<소스>.md` |

가장 중요한 숫자 (Claude Sonnet 5.5, 과제 26개 × 3조건 × 3회):

| | 마스킹 없음 (none) | 정답만 마스킹 (gold) | PromptGuard |
|---|---|---|---|
| 과제 성공률 | 99% | 95% | 90% |
| 비밀 값이 필요 없는 과제 | 98% | **98%** | 88% |
| 모델에 비밀이 보인 실행 | 77% | 0% | 15% |

> 한 줄 결론: **비밀만 정확히 가리면 성능이 떨어지지 않는다.** PromptGuard의 손실은 비밀이 아닌 값을 가리거나(과잉 마스킹), 같은 값에 다른 placeholder를 붙인 데서 나왔다.

---

## 1. 지금 상태 확인하기

```bash
git log --oneline -6
```

새 커밋 4개가 보여야 한다(이 문서를 더한 커밋까지 5개).

| 커밋 | 내용 |
|---|---|
| 지표2: 과제 26개와 Claude Code 실행기·채점기 추가 | `metric-2/tasks/`, `metric-2/scripts/` |
| 지표2: 마스킹 조건별 과제 성공 결과와 문서 추가 | `metric-2/README.md`, `metric-2/results/`, 루트 `README.md` |
| 지표1: 외부 소스 4개 변환기와 후보 검토 도구 추가 | `convert_*.py` 4개, `review_candidates.py`, `metric-1/reviews/`, `dataset_verify.py`, `.gitignore` |
| 지표1: 새 외부 소스 4개의 README와 데이터셋 표 추가 | `README_<소스>.md` 4개, `metric-1/README.md`, `metric-1/evaluation/README.md` |

**git에 없는 것** (내 노트북에만 있음, 지워져도 다시 만들 수 있음):

| 위치 | 내용 | 크기 |
|---|---|---|
| `runs/metric-2/main_sonnet_r3/` | 지표 2 실행 234회의 원본 기록 (transcript, 감사 로그, 최종 작업 폴더) | 46MB |
| `runs/all_new_sources/` | 새 소스 4개에 기존 시스템을 돌린 지표 1 채점 결과 | 7MB |
| `runs/review/*.worksheet.jsonl` | 정답 검토 작업 파일 (값이 들어 있음) | 0.7MB |
| `metric-1/data_test/`, `data_answer/`, `labels_from_*.jsonl` | 새 소스 4개의 변환 결과 | 약 70MB |
| `../openhands-feedback/`, `../SWE-Gym-OpenHands-SFT-Trajectories/`, `../noseyparker/` | 새로 받은 원본 | 112MB, 10MB, 1MB |
| `../Nemotron-PII` | 이미 있던 `../pii_ref_stats/raw/nemotron`을 가리키는 링크 (새로 받지 않음) | 0 |

---

## 2. 지표 2 따라가기

### 2-1. 무엇을 비교하나 (그림 하나)

```
            ┌───────────────────── Claude Code ─────────────────────┐
 과제 폴더 → │  promptguard-claude-demoV0의 Native Mod (그대로 사용)   │ → 모델
            │        │ 모든 텍스트를 탐지기에 물어본다                │
            └────────┼──────────────────────────────────────────────┘
                     ▼
          탐지기만 조건별로 바꿔 끼운다
          none        : 아무것도 안 찾음          (detector_worker.py --mode none)
          gold        : 과제의 정답 비밀만 찾음    (detector_worker.py --mode gold)
          promptguard : 원래 CredSweeper 탐지기    (형제 저장소의 worker.py)
```

처음에는 정답 마스킹용 Mod를 새로 만들려 했는데, 형제 폴더의 Mod를 그대로 쓰고 **탐지기만 바꾸는 쪽**으로 바꿨다. 이렇게 하면 세 조건이 Mod 코드까지 같아서, 차이가 "무엇을 가렸나" 하나로 좁혀진다.

### 2-2. 과제 둘러보기

```bash
python3 metric-2/scripts/m2.py list
```

과제 26개가 유형별로 나온다. 과제 하나를 열어 보자.

```bash
cat metric-2/tasks/t01-env-port-mismatch/task.json
ls -a metric-2/tasks/t01-env-port-mismatch/workspace
cat metric-2/tasks/t01-env-port-mismatch/workspace/.env
```

- `task.json`: 프롬프트(한국어), 유형, 비밀 목록, 채점 기준, 모범 풀이
- `workspace/`: 에이전트가 일할 프로젝트. 비밀값 자리에 `{{secret:db_password}}`처럼 적혀 있다

진짜 값이 채워진 모습을 보려면 임시 폴더에 빌드한다.

```bash
python3 metric-2/scripts/m2.py build t01 --out /tmp/m2-t01
cat /tmp/m2-t01/.env
```

`DB_PASSWORD=` 뒤에 가짜 비밀번호가 채워져 있다. 값은 지표 1과 같은 생성기로 만들어서 매번 똑같다. 실제 형식의 키(`sk_live_…` 등)를 git에 올리면 GitHub가 push를 막기 때문에 저장소에는 `{{secret:…}}`만 둔다.

### 2-3. 채점기가 맞는지 Claude 없이 확인하기

```bash
python3 metric-2/scripts/m2.py selftest
```

과제마다 세 가지를 확인한다: 손대지 않으면 실패, 모범 풀이를 적용하면 통과, 비밀을 `[PASSWORD_1]`로 덮어쓰면 실패. 마지막 줄이 `0 problem(s)`이면 된다.

### 2-4. Claude Code로 한 과제 직접 풀어 보기 ("클코만 켜서 바로 테스트")

```bash
python3 metric-2/scripts/m2.py play t23 --condition promptguard
```

1. 화면에 과제와 프롬프트가 출력되고, PromptGuard Mod가 붙은 Claude Code가 열리며 프롬프트가 자동으로 들어간다.
2. Claude가 `config/client.ini`를 읽을 때 `token_ttl_seconds = [TOKEN_1]`처럼 **숫자가 가려진 것**을 볼 수 있다(t23은 PromptGuard가 실패하는 과제다).
3. 끝나면 `/exit`로 닫는다. 그 자리에서 채점 결과가 나온다.

같은 과제를 조건만 바꿔 비교해 보면 차이가 바로 보인다.

```bash
python3 metric-2/scripts/m2.py play t23 --condition gold     # 정답(api_key, client_secret)만 가림 → 성공
```

준비물: `claude` CLI, Node.js, 형제 폴더 `../promptguard-claude-demoV0`(설치 완료 상태). 위치가 다르면 `--system-root`로 알려 준다.

형제 저장소의 런처를 직접 쓰고 싶으면 이렇게 한다.

```bash
PG=$(cd ../promptguard-claude-demoV0 && pwd)
python3 metric-2/scripts/m2.py build t01 --out ~/m2-t01        # 프롬프트도 출력된다
(cd ~/m2-t01 && "$PG/start-promptguard.sh")                     # 출력된 프롬프트를 붙여 넣고 작업, 끝나면 /exit
python3 metric-2/scripts/m2.py check t01 ~/m2-t01
```

이때 Claude Code가 `mcp__pgdetector__scan_batch` 사용 권한을 물으면 **허용**해야 한다. 거절하면 Mod가 가리지 못하고 원문이 그대로 넘어간다(5절 1번). `play`는 이 권한을 미리 허용해 둔다.

### 2-5. 결과 읽기

```bash
cat metric-2/results/summary.md
```

표 네 개가 순서대로 나온다: 전체 성공률 → 비밀 값이 필요한 과제인지로 나눈 성공률 → 과제 유형별 → 과제별(O 성공, X 실패). 실패 19건은 모두 transcript로 확인했고, 정리는 [metric-2/README.md의 "결과 읽기"](metric-2/README.md#결과-읽기-main-sonnet-55)에 있다. 핵심 다섯 가지:

1. **정답만 가리면(gold) 비밀 값이 필요 없는 과제는 그대로 해낸다** (98% = 98%).
2. **값을 명령에 직접 넣어야 하면 gold도 실패할 수 있다.** t17에서 모델이 `--password '[PASSWORD_2]'`를 그대로 쳤다(3/3 실패). 같은 유형의 t16에서는 `source .env`로 넘겨 성공했다.
3. **값의 속성이 필요한 과제는 가려도 성공했다.** JWT 만료 시각, Stripe 키의 live/test, 비밀번호 정책, 비밀번호 속 `$`를 모델이 값을 보지 않고 도구로 계산했다.
4. **PromptGuard만의 손실 두 가지**: t23 과잉 마스킹(숫자 5400을 가림), t15 같은 키가 파일마다 `[SECRET_1]`과 `[API_KEY_2]`로 다르게 가려져 비교 불가.
5. **placeholder로 파일을 망가뜨린 경우는 0건.** Edit가 "String not found"로 실패하면 모델이 줄 번호 편집으로 우회했다.

### 2-6. 실패 사례를 원본으로 직접 보기

```bash
D=runs/metric-2/main_sonnet_r3/t23-api-key-header/promptguard-r1
cat $D/result.json | python3 -m json.tool | head -40          # 채점, 노출, Mod 통계
python3 - "$D/transcript.jsonl" <<'EOF'
import json, sys
for line in open(sys.argv[1]):
    row = json.loads(line); msg = row.get("message") or {}
    for b in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
        if b.get("type") == "tool_use": print("TOOL  ", json.dumps(b["input"], ensure_ascii=False)[:200])
        if b.get("type") == "tool_result": print("RESULT", str(b.get("content"))[:300].replace("\n", " | "))
        if b.get("type") == "text": print("TEXT  ", b["text"][:300].replace("\n", " "))
EOF
```

transcript에는 **모델이 실제로 받은 내용**(Mod가 가린 뒤)이 저장되므로, 무엇이 가려졌는지 그대로 보인다. 다른 사례도 같은 방식으로 볼 수 있다: `t15-which-env-leaked/promptguard-r1`(다른 placeholder), `t17-db-cli-query/gold-r1`(placeholder를 명령에 넣음), `t12-dollar-in-password/promptguard-r1`(placeholder를 다시 가림).

### 2-7. 처음부터 다시 돌리려면

```bash
python3 metric-2/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 3 --model sonnet --jobs 2 --name main2
python3 metric-2/scripts/m2.py report runs/metric-2/main2 --out metric-2/results
```

- 비용: Sonnet 5.5로 실행당 약 $0.05, 234회에 약 $12. 동시 2개면 1시간 정도 걸린다.
- **주의**: 처음에 동시 4개로 돌렸을 때 계정 사용량 제한(429 "You've hit your session limit")에 54회가 걸렸다. 지금은 이런 실행을 자동으로 무효 처리하고 2분, 4분 뒤 다시 시도한다. 그래도 동시 실행은 2개 정도로 두는 편이 안전하다.
- 채점 기준을 고쳤을 때는 Claude를 다시 돌릴 필요 없이 `m2.py recheck runs/metric-2/<batch>`만 하면 된다. 실제로 두 번 썼다(숫자 비교가 `"Decimal('10.00')"`를 못 읽던 것, t12의 다른 정답 풀이를 인정하지 않던 것).

---

## 3. 지표 1 따라가기

### 3-1. 새 소스 4개 한눈에

| 소스 | 시험하는 상황 | 세션 | 정답 | 정답 만드는 법 |
|---|---|---|---|---|
| [Nemotron-PII](metric-1/README_Nemotron-PII.md) | 업무 문서, 메일, 양식 속 비밀번호·API 키·세션 쿠키 (자연어). 절반은 `prompt` 채널 | 6,000 | 3,866 | 원본 라벨 + 기존 기준으로 거르기 |
| [openhands-feedback](metric-1/README_openhands-feedback.md) | 실제 사용자와 에이전트의 세션 (웹 브라우징, 패키지 설치 등) | 275 | 47 | 후보를 모아 하나씩 판정 |
| [SWE-Gym](metric-1/README_SWE-Gym.md) | 오픈소스 저장소를 고치는 코딩 에이전트 (거의 음성) | 491 | 2 | 후보를 모아 하나씩 판정 |
| [Nosey Parker](metric-1/README_noseyparker.md) | 189개 규칙의 예시: 수백 종 서비스의 토큰 형식 | 573 | 351 | 규칙의 캡처 그룹 + 기존 기준으로 거르기 |

쓰지 않은 소스와 이유(ai4privacy는 라이선스, SecretBench는 데이터 보호 계약 필요, 큰 궤적 데이터는 용량)는 [metric-1/README.md](metric-1/README.md#검토했지만-쓰지-않은-소스)에 있다.

### 3-2. 데이터 직접 만들어 보기

원본은 이미 저장소 옆 폴더에 받아 두었다. parquet을 읽는 변환기 3개는 `pyarrow`가 필요하다(이 노트북의 `promptguard-demo` 환경에는 설치해 두었다).

```bash
python3 metric-1/scripts/convert_noseyparker.py                 # 몇 초
python3 metric-1/scripts/convert_nemotron_pii.py                # 20초 정도
python3 metric-1/scripts/convert_swe_gym.py
python3 metric-1/scripts/convert_openhands_feedback.py
```

각 명령이 세션 수, 정답 수, 정답에서 뺀 이유별 개수를 JSON으로 출력한다. 그다음 검증한다. 마지막 줄의 `"reproduction": "passed"`는 "다시 만들어도 바이트 단위로 같은 파일"이라는 뜻이다.

```bash
python3 metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_noseyparker.jsonl --noseyparker ../noseyparker
python3 metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_Nemotron-PII.jsonl --nemotron ../Nemotron-PII
```

### 3-3. "정답 기준은 기존 두 파일과 최대한 같게" — 어떻게 맞췄나

기존 두 외부 데이터(CredData, privesc-llm-data)가 쓴 규칙을 뽑아 네 소스에 똑같이 적용했다.

| 기존 규칙 | 어디서 왔나 | 새 소스에서 |
|---|---|---|
| 9자 미만 비밀번호는 정답이 아니다 | privesc ("흔한 비밀번호 목록에서 온 값") | 네 소스 모두. Nemotron은 9자 이상인 흔한 비밀번호(`123456789` 등)도 뺐다 |
| 약한 테스트 값은 정답이 아니다 | CredData의 F | `testpassword`, `Password123!`, `mock-token` 등 |
| placeholder, 지운 흔적은 정답이 아니다 | CredData의 X, 지표 1 정의 | `ghp_-XXX`, `aaaa…`, `YOUR_API_KEY_HERE` |
| 문서 예시 값은 정답이 아니다 | 지표 1 정의 (`AKIAIOSFODNN7EXAMPLE`) | jwt.io 예시 JWT, RFC의 `open sesame` |
| 해시는 정답이 아니다 | privesc의 `password_hash` | Nosey Parker의 bcrypt 등, dask 해시 |
| 테스트 환경이어도 무작위로 실제 동작하는 값은 정답이다 | privesc가 시나리오 환경에 심은 값을 정답으로 둠 | Django 개발용 `SECRET_KEY`, moto 가짜 Cognito의 JWT |
| 같은 값의 모든 등장 위치가 정답이다 | privesc | 네 소스 모두 |

소스마다 더 정한 것(예: 쿠키는 값만 정답, PIN·CVV는 제외, AWS 액세스 키 id는 ACCESS_KEY)은 각 README의 "기존 두 데이터와 같은 기준으로 맞춘 점" 표에 있다.

### 3-4. 라벨이 없는 소스의 정답은 어떻게 만들었나 (검토)

openhands-feedback과 SWE-Gym은 원래 라벨이 없다. 그래서:

1. CredSweeper, gitleaks, 그리고 탐지기가 놓치는 자리(위치 인자, `Bearer`, URL 속 비밀번호 등)를 잡는 정규식으로 **후보 값**을 모은다.
2. 기계적으로 정해지는 것(placeholder, 변수 참조, 코드 표현식, 9자 미만 …)은 규칙으로 판정한다.
3. 남은 것(openhands 123개, SWE-Gym 65개)은 맥락을 보고 직접 판정했다.
4. 판정은 **값 없이** SHA-256과 위치만 [metric-1/reviews/](metric-1/reviews/README.md)에 남긴다. 변환기가 그 위치에서 값을 다시 읽고 해시로 확인한다.

판정 목록을 직접 보려면:

```bash
grep '"credential"' metric-1/reviews/openhands-feedback.jsonl | python3 -c "
import json, sys
for l in sys.stdin: r = json.loads(l); print(r['where'][0], r['type'], '-', r['reason'])"
```

### 3-5. 기존 시스템 점수 보기

```bash
cat runs/all_new_sources/summary.md
```

| 소스 | 무엇이 보이나 |
|---|---|
| Nemotron-PII | 모든 탐지기의 recall이 낮다 (CredSweeper 0.31, PromptGuard 0.21, gitleaks 0.10). 자연어 속 비밀은 `key=value` 꼴이 아니라서 못 찾는다 |
| openhands-feedback, SWE-Gym | 실제 에이전트 트래픽에서의 과잉 마스킹: CredSweeper(ML off)는 1,000줄당 0.85~1.2번, ML on은 0.2~0.4번, PromptGuard는 0.5~0.85번 비밀이 아닌 것을 가린다 |
| Nosey Parker | 형식별 recall: PromptGuard 0.78, gitleaks 0.63. 비밀번호 형식이 가장 약하다 |

다시 돌리려면:

```bash
python3 metric-1/scripts/run_all.py --no-sweep --jobs 3 \
  --datasets sessions_from_Nemotron-PII sessions_from_openhands-feedback sessions_from_SWE-Gym sessions_from_noseyparker
```

---

## 4. 작업하며 정한 것과 이유

| 질문 | 답 |
|---|---|
| 왜 정답 마스킹용 Mod를 새로 만들지 않았나? | 형제 폴더의 Mod는 탐지를 별도 프로세스(HTTP)에 맡긴다. 그 프로세스만 "정답 목록을 돌려주는 탐지기"로 바꾸면 Mod 코드가 세 조건에서 완전히 같아진다 |
| none 조건에도 왜 Mod를 붙였나? | 조건 사이의 차이를 마스킹 하나로 좁히려고. Mod 없는 Claude Code는 `--condition plain`으로 돌릴 수 있다 |
| 답을 왜 `answer.json`으로 받나? | 최종 응답의 문장을 해석하면 채점이 흔들린다. 정해진 키의 값만 비교한다 |
| 작업 폴더를 왜 저장소 밖에 만드나? | 저장소 안이면 에이전트가 상위 폴더의 과제 정의(정답)를 읽을 수 있다 |
| 과제 비밀값을 왜 git에 안 올리나? | 실제 형식의 가짜 키는 GitHub push protection에 막힌다. 지표 1 합성 데이터와 같은 이유다 |
| Nemotron 문서 일부를 왜 `prompt` 채널에 두나? | 기존 외부 데이터에는 `prompt` 채널 정답이 없었다. 비정형 문서(메일, 메모)는 사용자가 붙여 넣는 것이 자연스럽다. `--channel`로 바꿀 수 있다 |
| openhands-feedback의 recall은 왜 믿으면 안 되나? | 정답 후보를 CredSweeper와 gitleaks가 냈기 때문이다. 이 데이터는 과잉 마스킹을 보는 용도다 |

---

## 5. PromptGuard에서 발견한 문제 (팀 공유용)

형제 저장소의 코드는 고치지 않았다. 자세한 내용은 [metric-2/README.md](metric-2/README.md#promptguard-mod에서-발견한-문제).

1. **탐지기 호출이 거절되면 원문이 그대로 모델에 간다.** headless 실행에서 `mcp__pgdetector__scan_batch` 권한이 없으면 훅이 건너뛰어져 가리지 않은 원문이 전달됐다. 첫 시험 실행에서 실제로 비밀이 그대로 보였다. 평가에서는 이 도구를 허용 목록에 넣고, 감사 로그에 실패가 있으면 그 실행을 무효로 처리한다.
2. **같은 값인데 placeholder가 다르다.** 번호를 (탐지 유형, 값)마다 매겨서 `[SECRET_1]`과 `[API_KEY_2]`가 같은 키일 수 있다. 값만으로 번호를 매기면 해결된다.
3. **placeholder를 다시 가린다.** 오류 메시지에 돌아온 `[PASSWORD_1]`을 비밀번호로 보고 `[PASSWORD_2]`로 바꿨다.
4. **비밀이 아닌 숫자를 가린다.** `token_ttl_seconds = 5400`.

---

## 6. 용량 정리

작업 중에 지운 것: 시험 실행 기록(`runs/metric-2/pilot`, 가짜 `play` 기록), 후보 수집용 채점 폴더, 작업용 임시 파일. Claude Code가 `~/.claude/projects` 아래에 만든 실행별 폴더는 실행이 끝날 때마다 자동으로 지운다.

더 비워야 하면 아래는 지워도 된다(다시 만들 수 있다).

```bash
rm -rf runs/metric-2/main_sonnet_r3/*/*/workspace_after   # 4MB, 지우면 recheck를 못 한다
rm -rf ../openhands-feedback                                # 112MB, openhands-feedback을 다시 만들려면 다시 받아야 함
rm metric-1/labels_from_Nemotron-PII.jsonl                  # 8MB, 분석용 파일 (변환하면 다시 생김)
```

---

## 7. 다음에 해 볼 만한 것

- **지표 2를 다른 모델로**: `m2.py run --model opus --reps 1`. 평소 쓰는 기본 모델이 Opus라 그쪽 결과도 의미가 있다.
- **PromptGuard 개선 후 다시 재기**: 5절의 2번(placeholder 번호)과 4번(숫자 과잉 마스킹)을 고치면 t15, t23이 바로 확인 과제가 된다.
- **placeholder 되돌리기 기능 실험**: 도구 입력에 들어간 `[PASSWORD_2]`를 실제 값으로 바꿔 주면 t17 같은 실패가 없어지는지. 지표 3(KEEP 판단)과도 이어진다.
- **지표 1 새 소스로 PromptGuard 개선 확인**: Nemotron-PII의 `prompt` 채널과 자연어 비밀, SWE-Gym의 과잉 마스킹 수가 기준선이 된다.
