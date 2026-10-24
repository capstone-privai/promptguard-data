# 평가 대시보드

팀원이 PromptGuard의 현재 성능을 웹에서 바로 보는 화면이다. 서버 하나가 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)의 `main`을 주기적으로 받아, 새 커밋마다 metric-detection과 metric-latency를 돌리고 결과를 보여 준다. metric-task는 API 비용이 들어서 대시보드가 돌리지 않고, 사람이 돌린 배치를 읽어 같은 커밋 옆에 보여 준다.

| 패널 | 내용 | 평가 |
|---|---|---|
| 탐지 성능 | 선택한 커밋의 Precision, Recall, F1. 이전 탐지기 변경 대비 변화와 커밋별 추이 | 커밋마다 자동 |
| 커밋별 변화 | `main`이 거친 커밋마다 P, R, F1 (전체 또는 데이터셋 하나). 점을 누르면 그 커밋 결과로 바뀐다 | 위 결과를 모음 |
| 세부 사항 | 데이터셋, 비밀 유형, 채널, 하위 분류(데이터셋마다 다름)로 거른 P, R, F1과 축별 비교, 판정별 예시 row | 위 결과에서 계산 |
| 탐지 지연 | 텍스트 1개(1KB, 64KB) 지연, 문자열 하나당 늘어나는 시간, timeout 넘은 호출, 크기·batch별 곡선, 어댑터별 지연 | 커밋마다 자동 |
| 작업 성공 | 조건(마스킹 없음, 정답만 가림, PromptGuard)별 과제 성공률, 비밀 노출, 서버 누출, 유형별 성공률 | 사람이 돌린 배치만 |

설명 문구는 숫자를 누를 때(지표 타일, 데이터셋 옆 `i`, 예시 펼치기, 위쪽 커밋 버튼)만 보인다. 화면의 필터와 커밋은 주소의 `#` 뒤에 남으므로, 보고 있는 조각을 링크로 공유할 수 있다.

## 서버에서 돌리기

저장소를 받고 metric-detection 데이터셋을 만든 다음([metric-detection/README.md](../metric-detection/README.md#생성과-검증)) 실행한다. 표준 라이브러리만 쓰므로 따로 설치할 패키지는 없다.

```bash
python3 dashboard/serve.py --host 0.0.0.0 --port 8765 --auth team:비밀번호
```

- **필요한 것**: Python 3.10 이상, `git`, PATH의 `gitleaks`(시스템과 같은 8.30.1 권장. 없으면 시스템처럼 gitleaks 어댑터가 빠진 채로 평가된다), 평가 대상 커밋이 고정한 버전의 `credsweeper`. 서버의 Python에 그 버전이 없으면 `requirements.txt` 내용마다 가상 환경을 만들어 설치한다(인터넷 필요, `--no-auto-venv`로 끔).
- **PromptGuard 저장소**: 기본은 GitHub 주소다. 비공개라면 서버에 읽기 권한(SSH 키, 토큰이 든 URL)을 주고 `--repo`로 넘긴다. 화면과 `index.json`에는 URL의 인증 정보를 빼고 보여 준다.
- **데이터셋**: `metric-detection/data_test/sessions*.jsonl`과 짝이 되는 정답 파일을 모두 평가한다. 새로 만들거나 바꾸면 다음 확인 때 모든 커밋을 다시 평가한다.
- 처음 띄우면 `main`이 거친 커밋(first-parent 이력: PR 하나는 머지 커밋 하나) 중 탐지기가 있는 것(`src/detector/pgdetector`가 생긴 뒤)을 모두 평가한다. 머지된 브랜치 안의 커밋은 `main`이 거친 상태가 아니어서 넣지 않는다. 그 브랜치는 옛 `main`에서 갈라졌으므로, 넣으면 추이에 없던 변화가 그려진다. 탐지기 코드가 같은 커밋은 결과를 같이 쓴다. 지금 `main`은 커밋 2개(424df6a, 928c84c)에 탐지기 상태 2가지다. 8코어 노트북 기준 탐지 성능은 상태 하나에 약 20분(`--jobs 7`), 지연은 약 2분 걸렸다.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--host`, `--port` | `127.0.0.1`, `8765` | 받을 주소. 다른 기기에서 보려면 `0.0.0.0` |
| `--auth USER:PASSWORD` | `$DASHBOARD_AUTH` | 모든 경로에 HTTP Basic 인증 |
| `--repo URL` | GitHub 주소 (`$PROMPTGUARD_REPO`) | 평가할 PromptGuard 저장소. 로컬 경로도 된다 |
| `--branch` | `main` | 따라갈 브랜치 |
| `--poll-minutes` | `10` | 브랜치를 확인하는 간격 |
| `--jobs` | CPU 수 − 1 | 탐지 성능 평가에서 동시에 도는 샤드 프로세스 수 |
| `--python` | 이 Python | 평가기를 돌릴 Python |
| `--data-dir` | `runs/dashboard` | 결과와 작업 파일을 두는 곳 (git에 올리지 않는다) |
| `--no-latency` | | metric-latency를 재지 않는다 |
| `--latency-adapters` | `each` | 앙상블 다음에 어댑터마다 따로 잰다. `ensemble`이면 앙상블만 |
| `--latency-guard PATH…` | | metric-task 요청 기록을 Final Guard 호출로 재생한다([metric-latency](../metric-latency/README.md#워크로드)) |
| `--task-runs DIR…` | `runs/metric-task` | metric-task 배치 폴더를 찾을 곳 |
| `--no-task` | | 작업 성공 패널을 숨긴다 |
| `--notify-url URL` | `$DASHBOARD_NOTIFY_URL` | 실패 알림을 보낼 Discord 웹훅([알림](#알림)). 비밀이므로 환경 변수로 넘긴다 |
| `--dashboard-url URL` | `$DASHBOARD_URL` | 알림 아래에 붙일 대시보드 주소 |
| `--overdue-hours` | `24` | 평가 하나가 이 시간을 넘기면 한 번 알린다. `0`이면 알리지 않는다 |
| `--once` | | 빠진 평가만 돌리고 끝낸다(cron용) |
| `--serve-only` | | 평가 없이 데이터 폴더의 결과만 보여 준다 |
| `--export DIR` | | 화면과 결과를 정적 파일로 써서 아무 웹 서버로나 띄울 수 있게 한다 |

계속 띄워 두려면 systemd 같은 것에 맡긴다. 멈출 때(SIGTERM) 돌던 평가는 중단하고 실패로 남기지 않으므로, 다시 띄우면 그 작업부터 다시 한다. 평가 시작, 끝, 실패는 표준 출력에 한 줄씩 남는다(`journalctl -u pg-dashboard`).

같은 데이터 폴더에서는 한 프로세스만 평가한다. Linux/macOS에서 `<data_dir>/.lock`을 `fcntl.flock`으로 잠그고, 평가 루프가 끝날 때 푼다. 다른 프로세스가 잠금을 잡고 있으면 `--once`는 아무 작업 없이 이유와 보유 PID를 출력하고 종료 코드 3으로 끝난다. 서버 모드는 화면을 계속 제공하며 대기 상태를 표시하고, 최대 30초 간격으로 잠금을 다시 시도한다. `--serve-only`와 `--export`는 잠그지 않는다. 프로세스가 비정상 종료되어도 잠금은 풀리므로, 남은 `.lock` 파일은 지우지 않는다. Windows에서는 이 잠금이 적용되지 않으니 데이터 폴더마다 평가 프로세스를 하나만 띄운다.

코드를 `git pull`로 받으면 `systemctl restart pg-dashboard`로 다시 띄운다. 잊어도, 대시보드나 채점 코드(`metric-detection/evaluation`, `metric-latency/scripts`)가 바뀐 것을 다음 주기에 알아채고 종료 코드 75로 스스로 끝나며, `Restart=on-failure`가 새 코드로 다시 띄운다. 돌던 프로세스가 옛 코드로 새 결과 키를 만들어 모든 커밋을 헛되이 다시 평가하지 않게 하려는 것이다. `--once`도 같은 경우 75로 끝나고, 다음 실행이 이어 한다.

```ini
# /etc/systemd/system/pg-dashboard.service
[Service]
WorkingDirectory=/srv/promptguard-data
Environment=DASHBOARD_AUTH=team:비밀번호
Environment=DASHBOARD_NOTIFY_URL=https://discord.com/api/webhooks/…
Environment=DASHBOARD_URL=http://서버:8765/
ExecStart=/usr/bin/python3 dashboard/serve.py --host 0.0.0.0 --port 8765
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

cron으로 돌리고 정적 서버에 올리는 방법도 된다: `python3 dashboard/serve.py --once && python3 dashboard/serve.py --export /var/www/pg-dashboard`. 이때 위쪽 상태 표시는 `index.json`을 쓴 시점에 멈춰 있다.

### 알림

`--notify-url`(또는 `$DASHBOARD_NOTIFY_URL`)에 Discord 웹훅을 주면 대시보드를 열지 않아도 평가 진행과 결과, 문제를 알 수 있다. 웹훅은 Discord 채널 설정 > 연동 > 웹후크에서 만든다.

| 알림 | 언제 |
|---|---|
| 🆕 새 커밋 | 브랜치에서 처음 본 커밋이 생겼을 때(평가 중 확인 포함). 커밋마다 평가 대기에 올랐는지, 탐지기가 같아 이전 결과를 쓰는지 적는다. 새 데이터 폴더의 첫 확인은 전체 이력이라 알리지 않고, 다시 띄우면 마지막 `index.json`에 없던 커밋만 알린다 |
| ▶️ 평가 시작 | 탐지 성능 또는 탐지 지연 평가를 시작할 때. 뒤에 남은 작업 수를 붙인다 |
| ✅ 평가 완료 | 한 커밋의 모든 평가가 끝났을 때 한 번. Precision, Recall, F1과 이전 탐지기 변경 대비 변화(%p), 지연(1KB·64KB 텍스트 p50, 문자열당 증가, timeout 초과 횟수). 일부가 실패했으면 ⚠️로 바꾸고 그 평가를 '실패'로 적는다 |
| ❌ 평가 실패 | 평가 하나가 실패해 `failures.json`에 남았을 때. 오류 첫 500자와 다시 돌리는 방법을 붙인다 |
| ⚠️ 서비스 오류 / ✅ 복구 | 저장소 받기나 계획 같은 평가 루프 자체가 실패했을 때 한 번, 다시 성공했을 때 한 번. 주기마다 반복해 보내지 않는다 |
| ⏳ 오래 걸림 | 평가 하나가 `--overdue-hours`(기본 24시간)를 넘겼을 때 한 번 |

데이터셋이나 채점기가 바뀌어 모든 커밋을 다시 평가하면 커밋마다 시작·완료 알림이 간다.

웹훅 주소를 가진 사람은 누구나 그 채널에 글을 쓸 수 있으므로 명령줄 대신 환경 변수로 넘기고(`ps`에 보이지 않게), 로그와 오류 메시지에도 남기지 않는다. 알림에 오류를 옮길 때는 URL의 인증 정보(`user:token@`)를 지운다. 알림 전송이 실패해도 평가는 계속하고, 표준 출력에 `alert not sent`만 남긴다. 프로세스 자체가 죽는 경우는 systemd가 다시 띄우며, 이 알림으로는 알 수 없다.

## 숫자를 어떻게 셌나

- 채점은 metric-detection 채점기([evaluation/](../metric-detection/evaluation/README.md))를 그대로 쓴다: `--system promptguard`와 같은 어댑터, 같은 판정(정확히 비밀값만 가렸을 때만 성공), 같은 채점 채널(사용자 프롬프트, 지침, 도구 결과). 데이터셋을 샤드로 나눠 병렬로 돌리지만, 병합할 때 대시보드의 개수가 채점기의 `counts`와 한 개라도 다르면 결과를 쓰지 않는다. 2026-10-17에 `main`의 `928c84c`로 잰 9개 데이터셋의 recall과 precision은 `run_all.py`로 잰 기존 결과(`all_20261014-023225`의 majority)와 모두 같았다.
- **맨 위 숫자는 모든 데이터셋의 정답과 가린 곳을 합쳐 계산한다**(micro). 정답 수가 많은 CredData, privesc-llm-data, Nemotron-PII의 비중이 크다. 데이터셋끼리의 차이는 세부 사항에서 본다.
- **F1**은 `2PR / (P + R)`이다. metric-detection 문서의 보조 지표 F2와는 다르다.
- **비밀 유형으로 거른 precision**: 정답과 겹친 가림은 그 정답의 유형으로, 정답과 겹치지 않은 가림(과잉 마스킹)은 탐지기가 붙인 placeholder 유형을 정답 유형으로 옮겨 센다(`PASSWORD`→비밀번호, `TOKEN`·`JWT`·`GITHUB_TOKEN`·`SLACK_TOKEN`→토큰, `AWS_KEY`→액세스 키, `API_KEY`·`SECRET`→시크릿, `PRIVATE_KEY`→개인 키). 유형을 알 수 없는 `CREDENTIAL`은 '미분류'로 둔다. 유형 필터를 모두 합치면 전체 precision과 같다. 유형은 판정에는 쓰지 않는다.
- **예시 row**는 (하위 분류, 채널, 유형, 판정)마다 item id의 해시 순서로 3개씩 고른다. 샤드는 후보의 초점과 원문을 넘기고, 병합할 때 전체 상위 후보를 정한 뒤 그 초점으로 창을 자른다. 같은 데이터와 결과면 샤드 수와 무관하게 같은 예시와 태그가 나온다. item 전체가 아니라 비밀 주변의 창(앞뒤 약 200자)만 보여 준다.
- **지연**은 [metric-latency](../metric-latency/README.md)의 `m4.py run --synth`를 그 커밋의 worker에 돌린 값이다. timeout 기준은 그 커밋의 `promptguard.config.json`에 있는 `detectorTimeoutMs`이며, 양의 정수가 없으면 5000ms를 쓴다. 화면과 헤드라인의 timeout 초과 횟수는 앙상블 호출만 센다. 평가 기기가 바뀌면 숫자도 바뀌므로 같은 서버에서 잰 커밋끼리만 비교한다. 탐지 성능 평가가 끝난 뒤 다른 부하 없이 잰다.

## 평가가 도는 방식

예시의 `offset`, `length`, 정답·가림 범위는 Python `str`과 같은 Unicode 코드 포인트 단위다. 브라우저도 같은 단위로 강조, 마스킹, 잘림 표시와 위치 설명을 계산한다. 이모지가 있어도 UTF-16 길이를 위치로 사용하지 않으며, 기존에 저장된 예시에도 적용된다.

서비스는 한 번에 일 하나씩 한다. 매번 브랜치를 받고, 평가할 커밋 목록을 만들고, 빠진 결과 중 가장 급한 것(가장 새 커밋, 같은 커밋이면 탐지 성능 먼저)을 하나 돌린다.

탐지 평가 하나가 몇 시간 걸릴 수 있으므로, 서버 모드는 평가가 도는 동안에도 `--poll-minutes`마다 브랜치를 받는다. 그 사이 머지된 커밋은 `index.json`에 '대기'로 올라가고 표준 출력에 `fetched during the running job: <커밋> queued`가 남는다. 돌던 평가는 끝까지 마치고, 다음 작업으로 가장 새 커밋을 고른다. 이때 받기가 실패해도 돌던 평가는 실패로 남기지 않는다. `--once`는 평가 중에 브랜치를 받지 않지만, 한 작업이 끝날 때마다 다시 받아 그 사이 커밋까지 평가한다.

탐지 평가는 데이터·정답·채점 코드를 작업별 임시 사본으로 고정하고, 계획에 기록한 해시와 대조한 뒤 검증과 모든 샤드를 그 사본으로 실행한다. 실행 중 원본을 바꿔도 그 작업의 입력은 같다. 사본을 만들기 전에 바뀐 입력은 결과나 영구 실패로 남기지 않고 다음 주기에 다시 계획한다. 탐지 결과 버전은 2이며 기존 결과는 이전 기준으로 표시되고 재평가 대상이 된다. 사본은 작업 종료 때 삭제하므로 실행 중에는 데이터셋 크기만큼 추가 디스크 공간이 필요하다.

- **결과 재사용**: 결과는 커밋의 탐지기 지문(`src/detector` 트리와 `requirements.txt`)과, 숫자가 기대는 나머지(탐지 성능: 데이터셋 파일, 채점기 `metric-detection/evaluation/`, 이 폴더의 `taxonomy.py`·`collect.py`·`shard.py`, gitleaks 버전 / 지연: `m4.py`와 옵션, 기기, gitleaks 버전, `latency.py`의 `LATENCY_VERSION`, 커밋의 `detectorTimeoutMs`)로 키를 만든다. timeout만 바꾸면 지연 키만 달라지고 탐지 성능은 다시 돌리지 않는다. 문서만 바꾼 커밋은 앞 커밋의 결과를 그대로 쓴다. 데이터셋이나 채점기가 바뀌면 모든 커밋이 다시 평가 대상이 되고, 다시 돌 때까지는 이전 결과를 '이전 기준' 표시와 함께 보여 준다.
- **이름과 설명**(`catalog.py`)은 키에 들어가지 않는다. 서비스가 확인할 때마다 `index.json`에 지금 값을 써서 화면이 결과 위에 덮어 쓰므로, 고쳐도 다시 평가하지 않는다. 유형을 세는 규칙이나 데이터셋의 하위 분류 기준(`taxonomy.py`)을 바꾸면 개수가 달라지므로 다시 평가한다.
- **평가가 끝나기 전**에는 그 앞 커밋의 결과를 보여 주고, 위쪽에 어느 커밋을 평가 중인지 적는다.
- **실패**하면 그 작업을 `failures.json`에 남기고 다시 시도하지 않는다. 웹훅이 있으면 [알림](#알림)을 보낸다. 위쪽 커밋 버튼에서 이유를 보고 '실패한 평가 다시 돌리기'를 누르거나, `POST /api/refresh?retry=1`을 보낸다. 자세한 기록은 `runs/dashboard/logs/`에 있다.
- **결과 파일 요청 실패**는 평가 실패나 빈 데이터와 구분해 표시한다. 서버에서는 index가 그대로여도 다음 상태 폴링 때 실패한 요청을 다시 보낸다. 각 오류 표시의 ‘다시 시도’ 버튼은 정적 사본에서도 사용할 수 있다. 예시는 요청에 성공한 경우만 캐시하므로 일시적인 오류가 ‘예시 없음’으로 남지 않는다.
- 평가는 PromptGuard 체크아웃을 쓰지 않는다. 서버가 bare clone(`repo.git`)에서 그 커밋의 `src/detector`, `register.mjs`, `requirements.txt`만 꺼내 평가하고 지운다.

| 경로 (`runs/dashboard/` 아래) | 내용 |
|---|---|
| `.lock` | 평가 프로세스의 잠금 파일. 보유 PID를 적으며, 파일이 남아 있어도 잠금이 잡혀 있다는 뜻은 아니다 |
| `index.json` | 커밋 목록과 커밋마다 결과의 상태·요약. 화면이 처음 읽는 파일 |
| `results/detection/<키>/` | `summary.json`(데이터셋 × 하위 분류 × 채널 × 유형별 개수), `examples/<데이터셋>.json`(예시 창), `meta.json` |
| `results/latency/<키>/` | `latency.json`(요약), `m4/`(m4.py의 원래 표본. 텍스트 없음) |
| `results/task/<키>/` | `task.json`(metric-task 배치 요약) |
| `repo.git`, `checkouts/`, `venvs/`, `validated/`, `logs/` | 저장소 사본, 꺼낸 커밋, 고정 버전 CredSweeper 환경, 데이터셋 검증 캐시, 기록 |

Guard 재생 지연은 측정·실패·미측정 요청 수와 캐시 통과 수를 구분한다. 실패하거나 일부 호출의 시간이 없는 요청은 지연 백분위수에서 제외하고, 정상적인 캐시 통과는 0ms로 센다. 지연 결과 버전은 `LATENCY_VERSION=3`이며, 이전 결과는 다음 서비스 실행에서 재측정 대상이 된다.

Guard capture는 배치·과제·조건 이름과 실제 경로의 지문으로 구분하고 중복 지정한 같은 파일은 한 번만 재생한다. 환경 지문에는 capture 출처와 내용 해시를 함께 넣으므로, 내용이 같은 별도 파일도 서로 다른 결과 키를 사용한다.

## metric-task 결과 넣기

대시보드는 metric-task를 돌리지 않는다. 누군가 `main`을 체크아웃한 PromptGuard로 배치를 돌리면([metric-task/README.md](../metric-task/README.md#한꺼번에-돌리기)), 그 배치 폴더를 서버의 `runs/metric-task/` 아래(또는 `--task-runs`로 지정한 곳)에 둔다. 읽는 파일은 배치 폴더의 `batch.json`과 `runs.csv`뿐이다. 둘 다 비밀값이 없으므로 실행별 폴더(transcript, API 기록)는 서버에 올리지 않아도 된다.

```bash
python3 metric-task/scripts/m2.py run --tasks all --conditions none,gold,promptguard --reps 3 --model sonnet --name main_928c84c
scp -r runs/metric-task/main_928c84c/{batch.json,runs.csv} server:promptguard-data/runs/metric-task/main_928c84c/
```

`batch.json`의 `system_provenance`로 미커밋 변경이 없음을 확인한 배치만 `system_commit`의 대표 결과로 연결한다. 수정된 체크아웃은 ‘미커밋 변경 있음’, 출처 정보가 없는 과거 배치는 ‘이력 미확인’으로 표시한다. 선택한 커밋의 대표 배치가 없으면 가장 최근 배치를 그렇다는 표시와 함께 보여 주고, 패널 오른쪽 위에서 다른 배치를 고를 수 있다. `TASK_VERSION=3`으로 과거 요약 캐시를 다시 생성한다.

서버 누출률은 `runs.csv` 각 행의 `server_leaked`가 유효한 비음수 정수로 기록된 실행만 분모에 포함한다. 빈 값·누락·잘못된 값은 미측정이며, 화면에서 측정/미측정 실행 수를 따로 보여 준다. 과제 성공률은 전체 유효 실행을 기준으로 계산한다.

## 보안

예시 창에는 데이터셋 원문이 그대로 들어간다. 합성 데이터의 가짜 값뿐 아니라 CredData(원본 저장소의 라이선스를 따르는 파일 조각), openhands-feedback(실제 사용자 세션) 같은 외부 데이터의 값도 있다. 팀 밖에 열지 않는다.

- 루프백이 아닌 주소로 띄울 때는 `--auth`를 건다(없으면 경고를 낸다). HTTPS가 필요하면 앞에 리버스 프록시를 둔다.
- 서버가 내주는 것은 화면 파일, `index.json`, 결과 폴더의 `summary.json`·`examples/*.json`·`latency.json`·`task.json`뿐이다. 저장소 사본, 꺼낸 코드, 기록, `failures.json`, metric-task의 실행별 폴더는 내주지 않는다.
- `runs/`는 `.gitignore`에 있다. 결과 폴더를 저장소에 올리지 않는다.

## 테스트

```bash
python3 -m unittest discover -s dashboard/tests -t dashboard
node --test dashboard/tests/test_web.js
node --check dashboard/web/app.js
```

채점기 fixture로 정확·넓게·일부·놓침·과잉 마스킹이 모두 나오는 가짜 시스템을 돌려 대시보드 개수가 채점기와 같은지, 샤드로 나눠도 개수와 예시가 같은지 본다. 그 밖에 커밋 목록과 지문(임시 git 저장소), 작업 순서와 `index.json`의 상태, HTTP 경로 제한과 인증, m4.py의 null 탐지기로 지연 요약을 확인한다. PromptGuard 체크아웃은 쓰지 않는다.

## 파일

```text
dashboard/
  BUGS.md               버그 수정 이력과 별도 검토 항목
  serve.py              진입점: HTTP 서버 + 평가 루프, --once, --serve-only, --export
  pipeline/
    service.py          커밋 목록, 작업 순서, 결과 키, index.json
    repo.py             PromptGuard 저장소: fetch, 평가할 커밋, 탐지기 지문, 필요한 파일만 꺼내기, 고정 CredSweeper
    runner.py           탐지 성능: 데이터셋 찾기·검증, 샤드 계획과 실행, 병합, summary.json
    shard.py            샤드 하나를 평가하는 프로세스 (metric-detection 채점기 사용)
    collect.py          개수 칸과 예시 고르기, 채점기와의 일치 검사
    taxonomy.py         세는 축: 유형, 채널, 판정, placeholder 유형 → 정답 유형, 데이터셋별 하위 분류 기준
    catalog.py          화면에 보이는 이름과 설명 (바꿔도 다시 평가하지 않음)
    latency.py          탐지 지연: m4.py 실행과 요약
    task.py             metric-task 배치 읽기 (실행하지 않음)
    notify.py           Discord 웹훅 전송 (무엇을 언제 알릴지는 service.py)
    paths.py            경로
  web/                  index.html, app.js, style.css (빌드 없이 그대로 쓴다)
  tests/
```
