# 파이프라인 시연 화면

PromptGuard Native Mod가 모델로 가는 텍스트를 처리하는 과정을 실시간으로 보여 주는 시연용 화면이다. Mod가 탐지기를 부를 때마다 한 줄이 생기고, 왼쪽에서 오른쪽으로 네 단계를 보여 준다.

| 열 | 보여 주는 것 |
|---|---|
| 1 들어온 입력 | 채널(사용자 프롬프트, CLAUDE.md, 파일 읽기, Bash 출력 등)과 원문. 후보가 있는 줄과 그 위아래 한 줄만 보여 주고, 후보 자리에서 곡선이 나와 2열의 모듈로 갈라진다 |
| 2 탐지 모듈 → 3 앙상블 투표 | 후보 자리마다 흐름 하나: 같은 텍스트를 받은 모듈(credsweeper, gitleaks, promptguard-rules)이 찍었는지(✓/✕, 유형과 규칙), 찍은 모듈의 표가 판정 상자로 모이고, 합의 기준을 넘으면 가림, 못 넘으면 버림. 한 표만 받아 떨어진 후보도 보인다 |
| 4 모델로 보내는 텍스트 | 가린 뒤 Mod가 넘기는 텍스트. 자리표시자에 마우스를 올리면 원래 값이 보인다 |

탐지기가 이번에는 못 찾았지만 Mod가 앞에서 가린 값이라 다시 가린 자리(Mod의 re-mask)는 1열과 4열에 점선으로, 3열에 `↺` 한 줄로 표시한다. 아무것도 찾지 못한 호출(모델 출력 조각, 시스템 프롬프트 등, 한 세션에 100건 넘게 생긴다)은 기본으로 접어 두고 "그대로 통과 N건 보기"로 펼친다. 사용자 프롬프트는 찾은 것이 없어도 항상 보인다.

## 실행

준비물은 metric-task의 `play`와 같다: `claude` CLI, Node.js, 형제 폴더 `../promptguard-claude-demoV0`(설치 완료 상태, 위치가 다르면 `--system-root`). gitleaks가 없으면 그 모듈은 투표에서 빠진다.

```bash
python3 demo/pipeline_demo.py play                    # 샘플 프로젝트 사본에서 Mod가 붙은 Claude Code를 연다
python3 demo/pipeline_demo.py play --project ~/work   # 다른 폴더에서
python3 demo/pipeline_demo.py play -- --model sonnet  # -- 뒤는 claude 인수
```

브라우저로 <http://127.0.0.1:18790>을 열어 두고 Claude Code에서 작업하면 된다. 샘플 프로젝트에는 `.env`와 `CLAUDE.md`에 합성 비밀이 들어 있어서, 세션이 시작될 때 CLAUDE.md가 한 번 지나가고 "`.env` 읽어 줘"처럼 시키면 파일 읽기가 지나간다. 투표에서 떨어지는 장면은 프롬프트에 `token_ttl_seconds = 5400`을 넣으면 나온다(credsweeper만 찍어 1/3표로 통과, metric-task t23의 과잉 마스킹 사례).

합의 기준은 서버가 탐지기를 띄울 때 체크아웃의 `detector.json`(또는 `PG_DETECTOR_CONSENSUS`)에서 읽어 화면 제목과 판정 문구에 그대로 쓴다. 시연에서 기준을 바꿔 보려면 `--consensus any|majority|unanimous|at_least:N`을 준다(`play`, `serve` 모두).

`serve`는 Claude Code 없이 탐지기와 화면만 띄운다. 다른 방법으로 띄운 Mod의 브리지에 `PG_MOD_DETECTOR_URL=http://127.0.0.1:18790`을 주면 그 Mod의 호출이 보인다.

## 어떻게 보나

Mod는 모델로 가는 모든 텍스트를 MCP 브리지를 거쳐 탐지기(`POST /scan-batch`)에 보낸다. `pipeline_demo.py`가 그 탐지기 자리에 선다(metric-task가 조건마다 탐지기를 바꿔 끼우는 것과 같은 방식). 시스템 저장소는 고치지 않는다.

- 탐지: 체크아웃의 `src/detector/pgdetector`와 `detector.json`을 그대로 불러 `scan_many()`로 답한다. 모듈별 투표지만 따로 받아 두려고 `Detector.collect`를 감쌀 뿐이라, Mod가 받는 응답은 `worker.py`와 같다.
- 4열 텍스트: Mod의 자리표시자 규칙(`placeholder`, `redactText`, `remaskText`)을 탐지기 응답에 다시 적용해 만든다. Mod 프로세스 안을 들여다보는 것이 아니라 같은 규칙으로 재구성한 것이므로, `node --test demo/tests/mod_replica.test.mjs`가 체크아웃의 실제 Mod 훅을 이 서버에 붙여 돌리고 Mod가 낸 텍스트와 화면의 텍스트가 글자 단위로 같은지 확인한다. Mod의 규칙이 바뀌면 이 테스트가 깨진다.
- Mod 뒤의 Final Guard는 띄우지 않는다. `promptguard run`은 탐지기를 직접 띄워서 이 서버로 바꿔 끼울 수 없다.

## 주의

화면과 서버 메모리에 **원래 비밀값이 그대로** 있다. 서버는 127.0.0.1에서만 받고 다른 Host 이름은 거절하지만, 합성 비밀로만 시연한다. 서버를 끄면 기록은 사라진다(최근 300건만 메모리에 둔다).
