# 파이프라인 시연 화면

PromptGuard Native Mod가 모델로 가는 텍스트를 처리하는 과정을 실시간으로 보여 주는 시연용 화면이다. Mod가 탐지기를 부를 때마다 한 줄이 생기고, 왼쪽에서 오른쪽으로 네 단계를 보여 준다.

| 열 | 보여 주는 것 |
|---|---|
| 1 들어온 입력 | 채널(사용자 프롬프트, CLAUDE.md, 파일 읽기, Bash 출력 등)과 원문. 후보가 있는 줄과 그 위아래 한 줄만 보여 주고, 후보 자리에서 곡선이 나와 2열의 모듈로 갈라진다 |
| 2 탐지 모듈 → 3 모듈별 스팬 → 합집합 | 후보 자리마다 흐름 하나: 같은 텍스트를 받은 모듈(체크아웃 main 기준 credsweeper, gitleaks, promptguard-rules, shell-aware)이 찍었는지(✓/✕, 유형과 규칙), 초록 상자 안에 모듈마다 그 모듈이 찾은 스팬을 같은 글자 위에 칠한 줄(줄끼리 글자 위치가 같아 막대처럼 겹쳐 보인다), 오른쪽 끝 상자에 그 스팬들의 합집합, 곧 실제로 가린 최종 스팬. `--policy majority`로 띄우면 표가 모자라 통과한 자리도 "통과 · 1/3개만 찾아 기준 미달"로 보인다 |
| 4 모델로 보내는 텍스트 | 가린 뒤 Mod가 넘기는 텍스트. 자리표시자에 마우스를 올리면 원래 값이 보인다 |

탐지기가 이번에는 못 찾았지만 Mod가 앞에서 가린 값이라 다시 가린 자리(Mod의 re-mask)는 1열과 4열에 점선으로, 3열에 `↺` 한 줄로 표시한다. 아무것도 찾지 못한 호출(모델 출력 조각, 시스템 프롬프트 등, 한 세션에 100건 넘게 생긴다)과, 같은 채널에서 이미 보인 텍스트 안에 그대로 들어 있고 같은 자리표시자로 가려진 텍스트(Mod의 `prompt.context`가 CLAUDE.md를 프롬프트 블록으로 한 번, 지시 파일로 한 번 더 검사한다)는 기본으로 접어 두고 "그대로 통과·중복 N건 보기"로 펼친다. 중복은 접은 줄에 앞서 보인 시각을 적는다. 사용자 프롬프트는 찾은 것이 없어도 항상 보인다.

## 실행

준비물은 metric-task의 `play`와 같다: `claude` CLI, Node.js, 형제 폴더 `../promptguard-claude-demoV0`(설치 완료 상태, 위치가 다르면 `--system-root`). gitleaks가 없으면 그 모듈은 빠진다.

```bash
python3 demo/pipeline_demo.py play                    # 샘플 프로젝트 사본에서 Mod가 붙은 Claude Code를 연다
python3 demo/pipeline_demo.py play --project ~/work   # 다른 폴더에서
python3 demo/pipeline_demo.py play -- --model sonnet  # -- 뒤는 claude 인수
```

`play`는 브라우저에서 <http://127.0.0.1:18790>을 자동으로 열고 Claude Code를 띄운다. 그대로 Claude Code에서 작업하면 된다. 샘플 프로젝트에는 `.env`와 `CLAUDE.md`에 합성 비밀이 들어 있어서, 세션이 시작될 때 CLAUDE.md가 한 번 지나가고 "`.env` 읽어 줘"처럼 시키면 파일 읽기가 지나간다. 프롬프트에 `token_ttl_seconds = 5400`을 넣으면 credsweeper 하나만 찍은 값도 합집합에 들어가 가려지는 장면이 나온다(metric-task t23의 과잉 마스킹 사례). `--policy majority`로 띄우면 같은 값이 1/3로 기준에 못 미쳐 통과한다.

시연 서버는 플러그인과 같이 체크아웃의 `detector.json`에 적힌 기준으로 가린다. main의 `candidate_policy`는 `union`이라 한 모듈이라도 찾은 스팬을 모두 합쳐 가리고(`consensus` 값은 이때 쓰이지 않는다), `majority`이면 `consensus` 투표를 통과한 자리만 가리며 후보 전용 모듈(shell-aware)은 표가 없다. 다른 기준으로 보려면 `--policy union|majority`(`PG_DETECTOR_CANDIDATE_POLICY`와 같다)와, `majority`일 때 투표 규칙 `--consensus any|majority|unanimous|at_least:N`을 준다(`play`, `serve` 모두). 쓰는 기준은 3열 제목에 나오고, 최종 스팬은 탐지기가 Mod에 돌려준 findings(받아들인 스팬을 `normalize()`가 합친 것)를 그대로 그린다.

`serve`는 Claude Code 없이 탐지기와 화면만 띄운다. 다른 방법으로 띄운 Mod의 브리지에 `PG_MOD_DETECTOR_URL=http://127.0.0.1:18790`을 주면 그 Mod의 호출이 보인다.

## 정답 대조 (`--showcase`, `--truth`)

탐지기가 찾은 것만 보면 "못 찾은 건 없나"에 답할 수 없다. 정답 파일을 주면 Mod가 보낸 텍스트 안의 진짜 비밀을 하나하나 찾아, Mod가 실제로 넘긴 텍스트 기준으로 채점한다.

```bash
python3 demo/pipeline_demo.py play --showcase             # 시연용 .env를 넣은 샘플 사본 + 그 정답으로 채점
python3 demo/pipeline_demo.py play --truth my-truth.json  # 다른 정답 파일
```

| 색 | 뜻 |
|---|---|
| 초록 | 진짜 비밀이고 전부 자리표시자 안에 있다 (가림) |
| 빨강 점선 | 진짜 비밀인데 일부만 가려 나머지가 읽힌다 (부분 노출) |
| 빨강 | 진짜 비밀인데 전혀 가리지 않았다 (그대로 나감) |
| 주황 | 비밀이 아닌데 가렸다 (과잉 마스킹) |
| 회색 점선 | 탐지기 오류로 Mod가 가리지 못하고 예외를 냈다 (Final Guard가 막아야 하는 경우) |

- 진짜 비밀이 든 텍스트는 아무것도 찾지 못했어도 접지 않고 보여 준다. 정답 대조 칸은 그 줄의 맨 위에 원문 전체(6,000자 이하)를 칠해서 보여 준다.
- 상단 줄은 세션 전체 누계다. 비밀 하나가 여러 번 나오면 가장 나빴던 결과로 센다(한 번이라도 그대로 나갔으면 "그대로 나감").
- `demo/showcase/.env`는 샘플 프로젝트의 `.env`에 찾기 어려운 자리(URL 안, 공백 든 따옴표 값, 주석 속 옛 키, 명령어 인자, 한국어 문장)와 비밀처럼 보이기만 하는 값(TTL 숫자, 커밋 해시)을 더한 것이다. `play --showcase`는 체크아웃이 아니라 임시 사본의 `.env`만 바꾼다. `demo/showcase/truth.json`에는 이 `.env`와 샘플 프로젝트 다른 파일의 합성 비밀 16개가 있다.
- 정답 파일 형식: `{"secrets": [{"name": "DB_PASSWORD", "value": "..."}]}`. 위치가 아니라 값으로 찾기 때문에 파일 읽기, Bash 출력, 프롬프트 어디로 들어와도 같은 기준으로 채점한다.
- 시연용 예시다. 정답을 만든 사람이 파일도 만들었으므로 성능 수치로 쓰지 않는다(화면에도 그렇게 적힌다). 성능은 metric-detection 평가셋으로 잰다.
- 채점 로직 테스트: `python3 demo/tests/test_truth.py`

## 어떻게 보나

Mod는 모델로 가는 모든 텍스트를 MCP 브리지를 거쳐 탐지기(`POST /scan-batch`)에 보낸다. `pipeline_demo.py`가 그 탐지기 자리에 선다(metric-task가 조건마다 탐지기를 바꿔 끼우는 것과 같은 방식). 시스템 저장소는 고치지 않는다.

- 탐지: 체크아웃의 `src/detector/pgdetector`와 `detector.json`을 그대로 불러 `scan_many()`로 답한다. 모듈별 스팬을 따로 받아 두려고 `Detector.collect`를 감쌀 뿐이라, `--policy`나 `--consensus`를 주지 않으면 Mod가 받는 응답은 `worker.py`와 같다.
- 4열 텍스트: Mod의 자리표시자 규칙(`placeholder`, `redactText`, `remaskText`)을 탐지기 응답에 다시 적용해 만든다. Mod 프로세스 안을 들여다보는 것이 아니라 같은 규칙으로 재구성한 것이므로, `node --test demo/tests/mod_replica.test.mjs`가 체크아웃의 실제 Mod 훅을 이 서버에 붙여 `detector.json`의 기준과 `--policy majority`에서 각각 돌리고 Mod가 낸 텍스트와 화면의 텍스트가 글자 단위로 같은지 확인한다. Mod의 규칙이 바뀌면 이 테스트가 깨진다.
- Mod 뒤의 Final Guard는 띄우지 않는다. `promptguard run`은 탐지기를 직접 띄워서 이 서버로 바꿔 끼울 수 없다.

## 주의

화면과 서버 메모리에 **원래 비밀값이 그대로** 있다. 서버는 127.0.0.1에서만 받고 다른 Host 이름은 거절하지만, 합성 비밀로만 시연한다. 서버를 끄면 기록은 사라진다(최근 300건만 메모리에 둔다).
