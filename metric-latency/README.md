# metric-latency: 탐지기 호출 지연

PromptGuard의 탐지기가 **그 순간 받은 텍스트**를 검사하는 데 얼마나 걸리는지 잰다. Native Mod는 훅마다 그 훅이 새로 받은 텍스트만 탐지기에 보내고, Final Guard는 요청 본문의 문자열 중 이미 깨끗하다고 판정한 것을 캐시해 두고 처음 보는 것만 보낸다. 그래서 재는 단위는 **탐지기 호출 한 번**(`POST /scan-batch` 한 번)이다. 호출마다 두 시간을 남긴다.

| 값 | 무엇 | 어디서 |
|---|---|---|
| `detector_ms` | 탐지기가 그 batch를 처리한 시간 | 탐지기가 응답에 적은 `items[].latency_ms`. 시스템의 worker는 batch 전체 시간을 모든 item에 똑같이 적는다 |
| `call_ms` | 평가기가 잰 HTTP 왕복 시간 | `detector_ms` + 로컬 HTTP와 JSON. 매 호출 새 연결을 연다(시스템의 클라이언트처럼) |

Mod의 훅 처리(placeholder 치환, remask, audit 쓰기), MCP bridge, Guard의 본문 파싱과 HMAC은 들어가지 않는다. 그런 비용이 얼마인지는 [재지 않는 것](#재지-않는-것)에 적었다.

평가기는 탐지기를 **worker의 HTTP 프로토콜을 말하는 블랙박스**로 다룬다. 시스템 코드도, metric-detection·metric-task 코드도 import하지 않는다. 시스템에 대해 아는 것은 [시스템에 기대는 것](#시스템에-기대는-것)에 모두 적었다.

## 한눈에 보기

2026-10-13, 시스템 커밋 `8973016`(앙상블: CredSweeper 1.19.0, gitleaks 8.30.1, 자체 규칙, 다수결), Apple Silicon 노트북(CPU 8개). 호출마다 5번 잰 warm 표본이다. 전체 표는 [results/first_20261013/summary.md](results/first_20261013/summary.md)에 있다.

| | 앙상블 | CredSweeper 단독 | gitleaks 단독 | 자체 규칙 단독 | null |
|---|---|---|---|---|---|
| 텍스트 1개, 1,024자 (p50) | 24ms | 0.7–0.8ms | 22–26ms | 0.1ms | 0.0ms |
| 텍스트 1개, 64K자 (p50) | 79–100ms | 39–49ms | 52–64ms | 4–6ms | 0.1ms |
| 문자열 1개가 늘 때마다 | +7.8ms | +0.7ms | +9.1ms | +0.08ms | - |
| Guard 재생: 요청 1개당 p50 / p95 / max | 82ms / 2.9s / 3.4s | 1.4ms / 41ms / 42ms | 80ms / 3.0s / 3.9s | 0.2ms / 5.7ms / 6.0ms | 0.0ms / 0.3ms / 0.3ms |
| 5초 넘은 호출 (Guard 재생, 750표본) | 0 | 0 | 2 (최대 7.0s) | 0 | 0 |
| worker 시작 | 1.4s | 1.2s | 0.2s | 0.2s | 0.1s |

1. **앙상블 지연의 대부분은 gitleaks다.** gitleaks 어댑터는 텍스트마다 `gitleaks` 프로세스를 띄워서(최대 4개 동시), 텍스트가 1개만 있어도 약 20ms가 들고 문자열이 하나 늘 때마다 약 9ms가 더 든다. CredSweeper는 문자열당 0.7ms, 자체 규칙은 0.08ms다. 글자 수는 덜 중요하다: 1KB당 앙상블 1.2ms.
2. **Mod처럼 텍스트 하나를 보내는 호출은 앙상블로 약 25ms**(수 KB 이하)다. 그중 20ms 넘게가 gitleaks 프로세스 시작 비용이다.
3. **Guard는 캐시 덕분에 요청 대부분이 가볍다.** 재생한 요청 120개의 문자열 중 86%가 캐시에 있었고, 세션의 두 번째 요청부터는 새 문자열이 중앙값 7개(90%가 10개 이하)라 요청당 약 80ms였다. 하지만 시스템 프롬프트와 도구 정의가 처음 들어가는 세션 첫 요청은 30세션 모두 새 문자열이 276개라 **2–3초**를 기다린다.
4. **gitleaks의 꼬리 지연이 시스템의 5초 timeout에 닿는다.** 문자열 256개짜리 batch 하나가 2–3.5초 걸리고, gitleaks 단독 재생에서는 750표본 중 2개가 5초를 넘었다(최대 7.0초). 시스템은 fail-closed라서 실제라면 그 요청이 막힌다.
5. **HTTP 왕복은 무시할 만하다**: `call_ms − detector_ms`의 중앙값이 0.3–1.1ms다. 지연은 거의 전부 탐지기 안에서 생긴다.

- "막힌 요청"은 재생한 탐지기가 Guard 재생에서 무언가를 찾아 막았을 요청 수다. 재생한 기록에는 none 조건(비밀을 가리지 않은 세션)도 들어 있어 막히는 것이 정상인 요청이 있다. 막힌 요청은 남은 batch를 보내지 않으므로, 막는 요청이 많은 탐지기(CredSweeper 단독 52개)는 그만큼 덜 보낸다.
- 아직 Mod 호출 기록(`--recorded`)으로는 재지 않았다. metric-task를 `--detector-capture`로 다시 돌려야 기록이 생긴다.

## 워크로드

| `--` 옵션 | 무엇을 보내나 | 상태 |
|---|---|---|
| `--synth` (기본) | 만든 텍스트. 크기 축(텍스트 1개, 128자부터 256K자까지 6단계)과 batch 축(1,024자 텍스트 1·4·16·64·256개), 각각 비밀이 없는 로그·코드(`plain`)와 약 20줄마다 비밀 한 줄이 든 것(`secrets`) | 없음. 같은 인자면 같은 텍스트 |
| `--guard 경로…` | metric-task 실행의 API 요청 기록(`api_requests.jsonl.xz`)을 Final Guard가 보냈을 호출로 바꿔 재생 | 기록 파일 하나가 Guard 프로세스 하나. 깨끗한 문자열 캐시를 재생 중에 쌓는다 |
| `--recorded 경로…` | metric-task 실행에서 Mod가 탐지기에 보낸 호출을 기록한 것(`detector_calls.jsonl.xz`)을 그대로 재생 | 없음(Mod는 캐시가 없다). 보낸 순서대로 |

- **Guard 재생**은 `POST /v1/messages`, `/v1/messages/count_tokens` 본문의 모든 문자열 값(키는 빼고)을 모으고, 한 요청 안의 중복을 없앤 뒤, 캐시에 없는 것만 256개씩 보낸다. 찾은 것이 없는 문자열만 캐시에 들어간다. 찾은 것이 있는 batch가 나오면 그 요청은 막히므로 남은 batch는 보내지 않는다. 호출이 실패해도 막힌다(fail-closed). 재생하는 탐지기가 실제로 찾은 것에 따라 캐시가 달라지므로, 어댑터마다 보내는 문자열이 조금씩 다를 수 있다.
- **기록 재생**용 파일은 metric-task를 `--detector-capture`로 돌리면 실행 폴더마다 생긴다. 실행기가 Mod의 bridge와 탐지기 사이에 기록 프록시([metric-task/scripts/detector_capture.py](../metric-task/scripts/detector_capture.py))를 끼운다. 파일에는 Mod가 본 그대로의 텍스트(과제의 비밀 포함)가 들어 있으므로 `runs/`에만 둔다.
- **세션 식별자**는 배치·과제·조건 이름과 capture의 실제 경로 지문을 함께 쓴다. 별도 배치나 다른 경로의 파일은 내용이 같아도 구분하고, 같은 파일을 폴더·직접 경로·symlink로 중복 지정하면 한 번만 재생한다. Guard와 Native Mod 기록 재생에 공통으로 적용한다. 예전 식별자로 기록한 표본은 출처를 복원할 수 없으므로 새로 재생해야 한다.

```bash
python3 metric-task/scripts/m2.py run --tasks core --conditions promptguard --reps 1 --jobs 1 --detector-capture --name pg_rec
```

## 탐지기

| `--detector` | 무엇 |
|---|---|
| `promptguard` (기본) | 시스템 체크아웃의 worker(`src/detector/worker.py`)를 그 `.venv` Python으로, 체크아웃에 설정된 그대로 띄운다 |
| `null` | 평가기에 든 탐지기. 아무것도 찾지 않는다. `call_ms`의 바닥(로컬 HTTP와 JSON 비용)을 본다 |
| `cmd:명령` | 아무 명령. `{port}`와 환경 변수 `PG_DETECTOR_PORT`에 포트가 들어간다. 예: `cmd:python3 my_detector.py --port {port}` |
| `url:주소` | 이미 떠 있는 탐지기. 예: Runtime V1의 `url:http://127.0.0.1:18771` |

평가기가 띄우는 탐지기는 부모 환경에서 `PG_`로 시작하는 변수를 모두 빼고 시작한다. 바깥 설정이 합의 규칙이나 설정 파일을 바꾸지 못하게 하려는 것이다.

## 실행

```bash
# 시스템 탐지기, 합성 입력과 Guard 재생
python3 metric-latency/scripts/m4.py run --name pg --detector promptguard --synth --guard runs/metric-task/capture_trial
# 비교용 바닥값
python3 metric-latency/scripts/m4.py run --name null --detector null --synth --guard runs/metric-task/capture_trial
# 여러 실행을 한 표로
python3 metric-latency/scripts/m4.py report runs/metric-latency/pg runs/metric-latency/null --out metric-latency/results/<이름>
# 테스트
python3 -m unittest discover -s metric-latency/tests
```

- 호출마다 `--repeat`번(기본 5) 연달아 잰다. 측정 전에 `--warmup`번(기본 3) 1,024자 텍스트를 보내고, 그 첫 호출은 **cold**로 따로 적는다.
- 클라이언트는 하나이고 호출을 순서대로 보낸다. 시스템도 Mod의 호출을 한 줄로 세우고(`detectorQueue`), Guard는 한 요청의 batch를 순서대로 보낸다.
- **다른 부하 없이 돌린다.** metric-task를 `--jobs`로 병렬로 돌리는 중이거나 테스트를 같이 돌리면 숫자가 오염된다.
- `run`은 `runs/metric-latency/<이름>/`에 `calls.jsonl`(표본마다 한 줄: 탐지기, 워크로드, item 수, 글자 수, 바이트, finding 수, `detector_ms`, `call_ms`), `requests.jsonl`(Guard 재생의 요청마다: 문자열 수, 보낸 수, 호출 수, finding), `run.json`(기기, 탐지기 설명과 버전, 시스템 커밋, 시작 시간, cold 호출)을 쓴다. 텍스트는 남기지 않는다.
- `report`는 `summary.md`와 `summary.csv`(탐지기 × 워크로드별 백분위수)를 쓴다.

## 결과 읽기

- **백분위수는 nearest rank**다: p95는 표본의 95%가 그 값 이하인 가장 작은 표본. warm 표본(모든 반복)으로 계산한다.
- **timeout 초과**는 `call_ms`가 `--timeout-ms`(기본 5,000ms, 시스템의 `detectorTimeoutMs`)를 넘은 표본 수다. 시스템은 fail-closed라서 실제로는 그 호출의 텍스트가 막힌다. 평가기는 끊지 않고 끝까지 잰다.
- **기울기**는 `detector_ms = 고정 비용 + 기울기 × KB`를 최소제곱으로 맞춘 값이다. 고정 비용은 크기와 상관없이 호출마다 드는 비용(하위 프로세스 시작 등)이다.
- **Guard 요청 시간**은 그 요청에서 보낸 모든 batch의 유효한 성공 `detector_ms`(반복 중앙값) 합이다. 실패한 요청과 batch 하나라도 시간이 없는 요청은 각각 실패·미측정으로 세고 요청 시간 백분위수에서 제외한다. 첫 반복의 실패로 차단된 요청은 이후 반복에 성공해도 실패로 유지한다. 검사 호출이 0개인 정상 요청은 0ms이며, 문자열이 전부 캐시에 있어 호출하지 않은 요청 수는 ‘캐시 통과’로 표시한다. 대시보드와 보고서는 같은 집계 함수를 사용한다.

## 시스템에 기대는 것

평가기가 시스템에 대해 아는 것은 아래뿐이다. 시스템이 이것을 바꾸면 평가기도 고친다.

1. **HTTP 프로토콜.** `GET /health`가 200이면 준비된 것이다. `POST /scan-batch`의 본문은 `{"request_id", "items": [{"id", "text", "source"}]}`이고, 응답은 `{"ok", "items": [{"id", "ok", "findings": [...], "latency_ms"}]}`이다. `GET /status`가 있으면 그 내용(어댑터 이름, 버전, 합의)을 탐지기 설명으로 남긴다. `url:`과 `cmd:` 탐지기는 이것만 맞으면 된다.
2. **worker를 띄우는 법** (`--detector promptguard`만): 체크아웃의 `src/detector/worker.py`, `.venv`의 Python, 환경 변수 `PG_DETECTOR_PORT`, `PG_DETECTOR_MODE=normal`.
3. **Final Guard의 캐시 규칙** (`--guard`만): 위 [워크로드](#워크로드)에 적은 것. 상수는 batch 256개다. 출처는 시스템의 `src/guard/lib.cjs`(`collectStringLeaves`, `scanLeaves`, `CleanScanCache`).
4. **timeout 기준**: `promptguard.config.json`의 `detectorTimeoutMs` 기본값 5,000ms.

## 재지 않는 것

- **Mod 쪽 비용**: 훅이 문자열을 모으고(`collectStrings`) placeholder로 바꾸고(`rebuild`), remask하고, audit 파일 전체를 다시 쓰는 시간. MCP bridge(stdin/stdout JSON-RPC, node 프로세스)를 거치는 시간. 이전 시스템(단일 CredSweeper)에서는 Mod audit의 `latency_ms`(bridge 포함) p50이 아무것도 찾지 않는 탐지기와 실제 탐지기 모두 4ms였다. 그때는 이 경로 비용이 탐지보다 컸다는 뜻이다.
- **Guard 쪽 비용**: 본문 읽기, JSON 파싱, 문자열 HMAC.
- **Guard 재생의 입력**: metric-task는 Final Guard 없이 Mod만 붙여 돌렸다. 재생하는 요청 본문은 Mod를 거쳐 Claude Code가 보낸 것이라 Guard가 받았을 것과 같다고 보지만, Guard가 요청을 막았다면 이후 세션은 달라졌을 것이다.
- 글자 수(`chars`)는 Python 문자열 길이(코드 포인트)다. 시스템의 오프셋 단위(UTF-16)와는 이모지 같은 문자에서 다르다.

## CredData-trajectory 행렬의 호출 지연 (matrix_latency.py)

[metric-detection/scripts/creddata_matrix.py](../metric-detection/scripts/creddata_matrix.py)의 행렬(시스템 커밋 8개 × base와 모델, 26칸)과 프로토타입(CredSweeper 1.19.0 기본 규칙, ML 꺼짐) 1칸, 모두 27칸에서 **4,096바이트 텍스트 하나에 대한 탐지기 호출 한 번**의 시간을 잰다. 행렬 정의는 그 스크립트를 import해서 쓴다.

- 재는 것: 체크아웃의 `pgdetector.load_detector()`로 만든 탐지기의 `detector.scan(text, source)` 한 번. 채점기(`promptguard_adapter.py`)가 부르는 것과 같다. 프로토타입은 채점기의 `CredSweeperAdapter(ml=False).detect(text)`다. Mod와 HTTP는 들어가지 않는다.
- 칸마다 프로세스를 하나 띄운다. 불러오기와 warmup(20회)은 시간에 넣지 않는다.
- ML 조합의 사본은 행렬과 같다: ML 어댑터 하나만 켜고 `required: true`, 모델 경로, `--device`(기본 `cpu`). timeout 등 나머지는 커밋 기본값이다.
- gitleaks는 시스템처럼 호출마다 프로세스를 띄운다. 대시보드의 gitleaks 캐시는 쓰지 않는다. PATH에 gitleaks 8.30.1이 없으면 실행을 멈춘다.
- 입력: `metric-detection/data_test/sessions_from_CredData-trajectory.jsonl`이 있으면 채점 채널(prompt, instructions, tool_output) 텍스트에서 줄 시작부터 자른 4,096바이트 창을 쓴다. 없으면 m4의 합성 텍스트(`secrets`, 4,096바이트)를 쓴다. 둘 다 seed가 고정이라 모든 칸이 같은 텍스트를 같은 순서로 받는다. 어느 쪽을 썼는지와 지문은 결과에 남는다. 지문이 다른 결과끼리는 비교하지 않는다.
- 기본값은 칸마다 1,000회다. 백분위수는 m4와 같은 nearest rank다.

### 집 PC 준비

필요한 것: Python 3.12, git, git-lfs, PATH의 gitleaks 8.30.1([릴리스](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)에서 OS에 맞는 파일을 받는다. Homebrew는 다른 버전을 줄 수 있다).

```bash
git clone https://github.com/capstone-privai/promptguard-data
cd promptguard-data
git checkout creddata-trajectory-data   # 이 스크립트가 있는 브랜치

# 시스템·모델 저장소를 옆에 clone하고, 모델 저장소를 1619e76에 맞추고, 행렬 모델 4개를 git lfs로 받아 sha256을 확인한다.
# --venv를 주면 venv를 만들고 고정 버전 패키지를 설치한다
# (torch 2.14.1, credsweeper 1.19.0, transformers 4.57.6, peft 0.21.2 등).
python3 metric-latency/scripts/matrix_latency.py setup --venv .venv-matrix --torch cpu    # NVIDIA: --torch cuda, macOS: --torch default
```

Windows(PowerShell)에서는 `python3` 대신 `py -3.12`를 쓰고, 이후 명령의 venv Python은 `.venv-matrix\Scripts\python.exe`다. Linux와 macOS에서는 `.venv-matrix/bin/python`이다.

평가 세트(`sessions_from_CredData-trajectory.jsonl`, sha256 `2c856d91…`)는 git에 없다. 비밀 형식 문자열이 들어 있으므로 서버에서 직접 복사해 `metric-detection/data_test/`에 둔다. 없으면 합성 입력으로 돈다.

### 토큰 분류기 bundle (mmbert-traj, qwen-traj)

이 두 칸의 모델은 어느 저장소에도 없다. Colab에서 Drive의 학습 결과로 만들었다(RUN_NOTES.md). 없으면 그 두 칸은 `skipped`로 남고 나머지는 돈다.

1. Colab 계정의 Google Drive에서 `promptguard-runs/token-span-creddata-mmbert/`와 `promptguard-runs/token-span-creddata-qwen/` 폴더를 통째로 받아 한 폴더(예: `drive-runs/`) 아래에 둔다. `config.json`, `selection.json`, `epoch-1/`(mmbert), `epoch-3/`(qwen)이 필요하다.
2. bundle을 만든다. Colab의 `build_bundles.py`와 같은 일을 하고, 받은 파일과 만든 `model.safetensors`의 sha256을 Colab 값과 비교한다. qwen은 Hugging Face에서 Qwen2.5-Coder-0.5B-Instruct(고정 revision)를 받아 LoRA를 합치므로 인터넷이 필요하다.

```bash
.venv-matrix/bin/python metric-latency/scripts/matrix_latency.py bundles --drive-runs drive-runs --out bundles
```

sha256이 다르면 그 칸은 `skipped`가 된다. 그래도 재려면 `run`에 `--no-model-check`를 준다(결과에 실제 sha256이 남는다).

### 실행

```bash
PY=.venv-matrix/bin/python                     # Windows: $PY = ".venv-matrix\Scripts\python.exe"
$PY metric-latency/scripts/matrix_latency.py run --token-bundles bundles --dry-run   # 칸 목록과 상태만
$PY metric-latency/scripts/matrix_latency.py run --token-bundles bundles             # 27칸, 칸마다 1,000회
$PY metric-latency/scripts/matrix_latency.py run --token-bundles bundles --device cuda --out metric-latency/results/creddata-matrix-cuda
$PY metric-latency/scripts/matrix_latency.py run --cells prototype 668c2c1/base 668c2c1/v10 --calls 200
$PY metric-latency/scripts/matrix_latency.py report metric-latency/results/creddata-matrix-<시각>
```

- `--cells`: `prototype`, 커밋(그 커밋의 모든 칸), `커밋/모델`, `*/모델`.
- 같은 `--out`으로 다시 돌리면 끝난 칸(`status: ok`)은 건너뛴다. 실패하거나 건너뛴 칸만 다시 돈다. 설정(`--calls`, `--warmup`, `--seed`, `--device`, 입력)이 처음과 다르면 멈춘다.
- 다른 부하 없이 돌린다. ML 칸은 CPU에서 느리다. 칸 하나에 1,000회면 수십 분이 걸릴 수 있다.
- ML 어댑터의 timeout(대개 4초)을 넘은 호출은 탐지기가 실패를 돌려준다. 시스템이라면 그 텍스트는 막힌다. 그 시간도 백분위수에 넣고, 실패 수는 따로 적는다.

### 결과

`--out`(기본 `metric-latency/results/creddata-matrix-<시각>/`):

| 파일 | 내용 | git |
|---|---|---|
| `summary.md` | summary.md와 같은 배치의 표: 행은 프로토타입과 커밋(날짜순), 열은 base와 모델, 칸은 p50 / p90 / p95 / p99(ms). 위에 기기, 버전, 입력 | 넣는다 |
| `summary.csv` | 칸마다 한 줄: 백분위수, 평균·최소·최대, 실패 수, 불러오기 시간, 상태 | 넣는다 |
| `cells/<칸>.json` | 칸마다 모든 호출 시간, 탐지기 설명, 모델 sha256, detector.json sha256. 텍스트는 없다 | 넣지 않는다 |
| `run.json` | 설정, 기기(CPU 모델, 코어, RAM, GPU, OS, Python, torch), 저장소 경로와 커밋 | 넣지 않는다 |

설정된 시스템 사본과 칸마다의 로그는 `runs/metric-latency/creddata-matrix-work/`(`--work`)에 있다.

## 파일

| 파일 | 내용 |
|---|---|
| [scripts/m4.py](scripts/m4.py) | 실행기(`run`), 리포트(`report`), null 탐지기 |
| [scripts/m4_workloads.py](scripts/m4_workloads.py) | 워크로드: 합성 텍스트, Guard 재생 규칙, 기록 재생 |
| [scripts/matrix_latency.py](scripts/matrix_latency.py) | CredData-trajectory 행렬의 칸마다 4 KB 호출 지연(`setup`, `bundles`, `run`, `report`) |
| [tests/test_matrix_latency.py](tests/test_matrix_latency.py) | 4 KB 입력, 백분위수, 칸 선택, 표 배치 |
| [tests/test_m4.py](tests/test_m4.py) | 워크로드, Guard 캐시 규칙, 통계, null 탐지기로 처음부터 끝까지 |
| [../metric-task/scripts/detector_capture.py](../metric-task/scripts/detector_capture.py) | metric-task 실행 중 Mod의 탐지기 호출을 기록하는 프록시 |
| `results/<이름>/` | `summary.md`, `summary.csv` (git에 넣는다. 텍스트는 없다) |
